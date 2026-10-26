"""Host transport is private; models cannot select endpoints or write source data."""

import io
import json
from decimal import Decimal

import pytest
import sqlglot

from compiler import bind, source_schema
from compiler.registered_source import Connection


def test_registered_binding_needs_an_exact_host_transport(monkeypatch):
    monkeypatch.delenv("SUDOGRAPH_REGISTERED_SOURCE", raising=False)
    with pytest.raises(bind.SourceUnavailable):
        bind.connect("registered://source-a")
    for endpoint in ("https://example.com/source", "http://127.0.0.1:1/other"):
        monkeypatch.setenv("SUDOGRAPH_REGISTERED_SOURCE", json.dumps({
            "source": "registered://source-a", "endpoint": endpoint,
            "token": "private-host-token", "provider": "postgresql",
        }))
        with pytest.raises(bind.SourceUnavailable):
            bind.connect("registered://source-a")
    assert source_schema.source_id("registered://source-a", ".") == source_schema.source_id(
        "registered://source-a", "/unrelated")


def test_provider_reads_keep_exact_values_and_bind_literals(monkeypatch):
    requests = []
    class Transport:
        def open(self, request, timeout):
            assert timeout == 30
            assert request.get_header("Authorization") == "Bearer private-host-token"
            body = json.loads(request.data)
            requests.append(body)
            result = {"session": "lease"} if body["operation"] == "open" else {
                "columns": ["id", "amount", "payload"], "rows": [[
                    {"$integer": "9007199254740993"}, {"$decimal": "12345.6789"},
                    {"$binary": "AAH/"},
                ]],
            }
            return io.BytesIO(json.dumps({"ok": True, "result": result}).encode())
    monkeypatch.setattr("compiler.registered_source.build_opener", lambda *_: Transport())
    monkeypatch.setenv("SUDOGRAPH_REGISTERED_SOURCE", json.dumps({
        "source": "registered://source-a", "endpoint": "http://127.0.0.1:1234/source",
        "token": "private-host-token", "provider": "postgresql",
    }))
    conn = Connection("registered://source-a")
    value = "a'); DROP TABLE orders; --"
    row = conn.execute('SELECT id,amount,payload FROM orders WHERE name=?', [value]).fetchone()
    assert row["id"] == 9007199254740993
    assert row["amount"] == Decimal("12345.6789")
    assert row["payload"] == b"\x00\x01\xff"
    tree = sqlglot.parse_one(requests[-1]["sql"], read="postgres")
    assert tree.args["where"].this.expression.this == value
    assert source_schema.wire(row["amount"]) == {"$decimal": "12345.6789"}
    for sql in ("DELETE FROM orders", "CREATE TABLE stolen(id INT)", "PRAGMA writable_schema=ON"):
        before = len(requests)
        with pytest.raises(ValueError, match="SELECT"):
            conn.execute(sql)
        assert len(requests) == before
    conn.close()
    assert requests[-1] == {"operation": "close", "session": "lease"}


def test_remote_view_dependencies_do_not_silently_drop_out_of_scope_sources():
    assert source_schema._dependencies(
        'SELECT * FROM public.orders', {'orders'}, 'postgres', 'public'
    ) == (['orders'], None)
    for sql in ('SELECT * FROM other.orders', 'SELECT * FROM public.missing'):
        found, error = source_schema._dependencies(sql, {'orders'}, 'postgres', 'public')
        assert found == [] and 'outside' in error
