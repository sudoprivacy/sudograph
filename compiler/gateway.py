"""Authenticated view boundary. Run in the data owner's process, never the agent pod.

The operator registers view specs and an authority outside agent-editable YAML.
Every operation, including export and discovery, reauthorises. Different views
are separately compiled resources: no hidden rows/readings are sent to clients.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from . import app, bind, browse, expr
from .compile import compile_spec
from .dependencies import validate_names
from .query import link_resolver
from .spec import SpecError, load


class Denied(PermissionError):
    pass


class Authority(Protocol):
    def require(self, credential: str, resource: str, action: str) -> str:
        """Authenticate and authorise, returning the authenticated subject or raising."""


class FileCapabilities:
    """Local operator-managed bootstrap authority; not a substitute for Nexus ReBAC.

    Policy contains SHA-256 hashes of high-entropy bearer capabilities, not plaintext
    passwords. Read on every request so revocation applies to exports and paging too.
    The agent must not have access to this file, source DBs or the server process.
    """

    def __init__(self, path):
        self.path = Path(path)

    def require(self, credential, resource, action):
        if not credential:
            raise Denied("authorisation required")
        digest = hashlib.sha256(credential.encode()).hexdigest()
        try:
            policy = json.loads(self.path.read_text(encoding="utf-8"))
            for entry in policy["credentials"]:
                actions = entry.get("grants", {}).get(resource, [])
                if (isinstance(actions, list) and action in actions
                        and hmac.compare_digest(digest, entry["sha256"])):
                    return entry["subject"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        raise Denied("resource or operation unavailable")


class NexusAuthority:
    """Use a trusted Nexus client whose read propagates the caller's credential.

    `read(path, credential=...)` calls the typed Read RPC with the caller's
    credential. Nexus authenticates that credential; the operator-owned grant
    binds its SHA-256 digest to a subject and actions, because ReadResponse does
    not return an authenticated subject. The caller must be unable to WRITE the
    grant: arm nexusd-cluster's permission policy and issue read-only zone grants.
    No root service token, connection fallback or caller-supplied identity.
    """

    def __init__(self, client, grant_paths):
        self.client, self.grant_paths = client, dict(grant_paths)

    def require(self, credential, resource, action):
        if not credential or resource not in self.grant_paths:
            raise Denied("authorisation required")
        try:
            result = self.client.read(self.grant_paths[resource], credential=credential)
            grant = json.loads(result.content)
            if (
                grant["resource"] == resource
                and isinstance(grant["actions"], list)
                and action in grant["actions"]
                and isinstance(grant["subject"], str) and grant["subject"]
                and hmac.compare_digest(grant["credential_sha256"],
                                        hashlib.sha256(credential.encode()).hexdigest())
            ):
                return grant["subject"]
        except Exception:
            pass
        raise Denied("resource or operation unavailable")


@dataclass(frozen=True)
class View:
    spec: str
    basis: str | None = None
    at: dict | None = None


CONTRACT = {
    "version": 1,
    "expression_parser": "SQLGlot",
    "dialect": "sqlite",
    "aggregates": ["count", "sum", "avg", "min", "max"],
    "joins": "declared ref paths only; arbitrary JOIN, FROM subqueries and DDL refused",
    "operations": ["graph", "page", "query", "export"],
    "raw_database_access": False,
}


class Gateway:
    def __init__(self, views: dict[str, View], authority: Authority):
        if authority is None:
            raise ValueError("Gateway requires an authority; no anonymous fallback")
        self.views, self.authority = dict(views), authority

    def discover(self, credential):
        available = []
        for name in self.views:
            try:
                self.authority.require(credential, name, "read")
            except Denied:
                continue
            available.append(name)
        return {**CONTRACT, "views": available}

    def execute(self, credential, resource, operation, **params):
        if operation not in CONTRACT["operations"]:
            raise ValueError("unknown operation; read /contract for supported operations")
        self.authority.require(credential, resource, "export" if operation == "export" else "read")
        definition = self.views.get(resource)
        if definition is None:
            raise Denied("resource or operation unavailable")
        # The client cannot supply a file path, basis, source, SQL table or policy.
        s = load(definition.spec, scope=definition.at)
        if operation == "page":
            allowed = {"type", "offset", "limit", "where"}
            if set(params) - allowed:
                raise ValueError("unsupported page parameter")
            tn = params.pop("type")
            return browse.page(s, tn, basis=definition.basis, at=definition.at, **params)
        if operation == "query":
            if set(params) != {"expression"}:
                raise ValueError("query requires only expression")
            # The exact same parser as authoring. No raw SQL execution endpoint.
            expression = expr.parse(params["expression"])
            validate_names(s, expression)
            c = compile_spec(s, basis=definition.basis, at=definition.at)
            return {
                "value": expr.evaluate(
                    expression,
                    c.values,
                    c.rows,
                    agg=bind.answerer(s, definition.at, definition.basis),
                    resolve=link_resolver(s),
                )
            }
        if params:
            raise ValueError("graph/export takes no caller-selected scope")
        c = compile_spec(s, basis=definition.basis, at=definition.at)
        if not c.passed:
            raise SpecError("registered view failed its checks; ask the view owner to repair it")
        b = {
            "access": {"mode": "authorised", "view": resource},
            "translations": s.translations,
            "ontology": s.name,
            "axes": {},
            "bases": [definition.basis],
            "bridges": [],
            "views": {f"{definition.basis or ''}|": c.view},
            "diffs": {},
            "coverage": [],
            "records": {},
        }
        # A source connector can contain credentials or a local pathname. Neither
        # belongs in an answerer's graph or an authorised portable export.
        for node in c.view["nodes"]:
            node.pop("connector", None)
        if operation == "export":
            # Portable files cannot be revoked. Export is a separate grant, and
            # never includes other registered views or the source catalogue.
            return app.render(b)
        return b
