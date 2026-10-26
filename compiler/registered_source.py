"""Private DB-API adapter for host-registered, read-only database providers.

The host owns drivers and credentials. YAML holds an opaque registration only;
neither a model author nor the review browser can select a transport endpoint.
"""

from __future__ import annotations

import base64
import json
import os
from copy import deepcopy
from decimal import Decimal
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

import sqlglot
from sqlglot import exp


class Row(list):
    def __init__(self, columns, values):
        super().__init__(values)
        self.columns = columns

    def __getitem__(self, key):
        return super().__getitem__(self.columns.index(key) if isinstance(key, str) else key)

    def keys(self):
        return self.columns


class Cursor:
    def __init__(self, columns, rows):
        self.rows = iter(Row(columns, [_decode(v) for v in row]) for row in rows)

    def __iter__(self):
        return self.rows

    def fetchone(self):
        return next(self.rows, None)

    def fetchall(self):
        return list(self.rows)


def _decode(value):
    if isinstance(value, dict):
        if "$binary" in value:
            return base64.b64decode(value["$binary"], validate=True)
        if "$integer" in value:
            return int(value["$integer"])
        if "$decimal" in value:
            return Decimal(value["$decimal"])
    return value


class Connection:
    def __init__(self, dsn):
        from .bind import SourceUnavailable  # noqa: PLC0415 -- optional provider/bind cycle

        self.dsn = dsn
        self.in_transaction = False
        self.is_closed = False
        try:
            binding = json.loads(os.environ["SUDOGRAPH_REGISTERED_SOURCE"])
            parsed = urlsplit(binding["endpoint"])
            if (binding["source"] != dsn or parsed.scheme != "http"
                    or parsed.hostname != "127.0.0.1" or parsed.username
                    or parsed.password or parsed.path != "/source"
                    or parsed.query or parsed.fragment):
                raise ValueError("invalid source transport")
            self.endpoint, self.token = binding["endpoint"], binding["token"]
            self.provider = binding["provider"]
            self.schema = binding.get("schema")
            if self.provider not in {"postgresql", "mysql"}:
                raise ValueError("unsupported source provider")
            self.dialect = "postgres" if self.provider == "postgresql" else "mysql"
            self.session = self._request({"operation": "open"})["session"]
        except (KeyError, ValueError, OSError) as error:
            raise SourceUnavailable("Registered source transport is unavailable") from error

    def _request(self, body):
        request = Request(self.endpoint, data=json.dumps(body).encode(), method="POST",
                          headers={"Authorization": "Bearer " + self.token,
                                   "Content-Type": "application/json"})
        with build_opener(ProxyHandler({})).open(request, timeout=30) as response:
            raw = response.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError("Registered source response exceeds the read limit")
        result = json.loads(raw)
        if not result.get("ok"):
            code = result.get("code", "PROVIDER_ERROR")
            raise ValueError("Registered source read failed: " + code)
        return result["result"]

    def _call(self, operation, **params):
        if self.is_closed:
            raise ValueError("Registered source connection is closed")
        return self._request({"operation": operation, "session": self.session, **params})

    def execute(self, sql, params=()):
        if sql.strip().upper() == "BEGIN":
            if not self.in_transaction:
                self.proof = self._call("begin")
                self.in_transaction = True
            return Cursor([], [])
        tree = sqlglot.parse_one(sql, read="sqlite")
        if not isinstance(tree, exp.Query):
            raise ValueError("Registered sources accept compiler SELECT queries only")
        values = iter(params)
        def bind_parameter(node):
            if isinstance(node, exp.Placeholder):
                try:
                    return exp.convert(next(values))
                except StopIteration as error:
                    raise ValueError("Missing source query parameter") from error
            return node
        tree = tree.transform(bind_parameter)
        sentinel = object()
        if next(values, sentinel) is not sentinel:
            raise ValueError("Extra source query parameters")
        # Database-specific functions without an exact provider implementation
        # must fail; do not substitute approximate financial arithmetic.
        if any(isinstance(node, exp.Anonymous) and node.name.lower().startswith("sg_")
               for node in tree.walk()):
            raise ValueError("This provider does not implement the requested exact arithmetic")
        result = self._call("query", sql=tree.sql(dialect=self.dialect))
        return Cursor(result["columns"], result["rows"])

    def inventory(self):
        if not hasattr(self, "catalog"):
            self.catalog = self._call("inventory")
        return deepcopy(self.catalog)

    def describe(self, name):
        return deepcopy(next(obj for obj in self.inventory() if obj["name"] == name))

    def close(self):
        if not self.is_closed:
            try:
                self._call("close")
            finally:
                self.is_closed = True
                self.in_transaction = False
