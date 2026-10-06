"""Exercise the real Northwind SQLite through the authenticated HTTP boundary.

Run: python -m tools.check_northwind_access /absolute/path/northwind.db
Uses an isolated temporary operator directory and an ephemeral loopback port.
No credentials or DB copies are emitted. This is a local capability acceptance
test, not evidence of Nexus data-driver integration.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import secrets
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from compiler import bind
from compiler.gateway import FileCapabilities, Gateway, View
from compiler.serve import handler


def verify(database, *, authority=None, reader_token=None, manager_token=None, revoke=None):
    database = Path(database).resolve(strict=True)
    dsn = "sqlite:///" + database.as_posix()
    with bind.connect(dsn) as conn:
        total = conn.execute("SELECT COUNT(*) FROM Orders").fetchone()[0]
        count, freight = conn.execute(
            "SELECT COUNT(*), SUM(Freight) FROM Orders WHERE ShipCountry = 'Germany'"
        ).fetchone()
    doc = {
        "ontology": "Northwind authorised shipment projection",
        "dimensions": ["country"],
        "raw": {"R": {"dsn": dsn}},
        "types": {"Shipment": {
            "label": "Shipment", "dimensions": {"country": "country"},
            "backing": {"from": "R", "table": "Orders", "key": ["OrderID"]},
            "props": {
                "id": {"type": "number", "owner": "source", "column": "OrderID"},
                "country": {"type": "string", "owner": "source", "column": "ShipCountry",
                            "nullable": True, "absent": "none"},
                "freight": {"type": "money", "owner": "source", "column": "Freight"},
            },
        }},
        "nodes": {"count": {"op": "SELECT COUNT(*) FROM Shipment"},
                  "freight": {"op": "SELECT SUM(freight) FROM Shipment"}},
    }
    with TemporaryDirectory(prefix="sudograph-northwind-access-") as directory:
        root = Path(directory)
        public, private = root / "public.yaml", root / "manager.yaml"
        public.write_text(yaml.safe_dump(doc), encoding="utf-8")
        manager = copy.deepcopy(doc)
        manager["types"]["Shipment"]["props"]["address"] = {
            "type": "string", "owner": "source", "column": "ShipAddress",
            "nullable": True, "absent": "none",
        }
        private.write_text(yaml.safe_dump(manager), encoding="utf-8")
        reader_token = reader_token or secrets.token_urlsafe(32)
        manager_token = manager_token or secrets.token_urlsafe(32)
        credentials = [
            {"subject": "germany-reader",
             "sha256": hashlib.sha256(reader_token.encode()).hexdigest(),
             "grants": {"germany": ["read"]}},
            {"subject": "manager", "sha256": hashlib.sha256(manager_token.encode()).hexdigest(),
             "grants": {"all": ["read", "export"]}},
        ]
        policy = root / "policy.json"
        policy.write_text(json.dumps({"credentials": credentials}), encoding="utf-8")
        gateway = Gateway({"germany": View(str(public), at={"country": "Germany"}),
                           "all": View(str(private))}, authority or FileCapabilities(policy))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler(gateway))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(token, operation, view="germany", **params):
            body = {"operation": operation} if operation == "contract" else {
                "operation": operation, "view": view, "params": params,
            }
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/v1",
                data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {token}",
                                                       "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as response:
                return response.code, json.load(response)

        try:
            assert request("", "graph")[0] == 403
            assert request("invalid", "page", type="Shipment")[0] == 403
            status, result = request(reader_token, "contract")
            assert status == 200 and result["result"]["views"] == ["germany"]
            status, result = request(reader_token, "graph")
            assert status == 200, result
            graph = result["result"]
            group = next(g for g in graph["views"]["|"]["groups"] if g["type"] == "Shipment")
            assert group["count"] == count
            assert "ShipAddress" not in json.dumps(graph)
            assert "northwind.db" not in json.dumps(graph)
            assert graph["access"] == {"mode": "authorised", "view": "germany"}
            for offset in (0, max(count - 2, 0)):
                status, result = request(reader_token, "page", type="Shipment",
                                         offset=offset, limit=2)
                assert status == 200 and result["result"]["total"] == count, result
                assert all(r["country"] == "Germany" and "address" not in r
                           for r in result["result"]["rows"])
            for expression, expected in (("SELECT COUNT(*) FROM Shipment", count),
                                         ("SELECT SUM(freight) FROM Shipment", freight)):
                status, result = request(reader_token, "query", expression=expression)
                assert status == 200, result
                assert abs(result["result"]["value"] - expected) < 0.001
            assert request(reader_token, "query",
                           expression="SELECT MAX(address) FROM Shipment")[0] == 400
            assert request(reader_token, "page", type="Shipment", at={"country": "USA"})[0] == 400
            assert request(reader_token, "graph", view="all")[0] == 403
            assert request(reader_token, "export")[0] == 403
            status, result = request(manager_token, "query", view="all",
                                     expression="SELECT COUNT(*) FROM Shipment")
            assert status == 200 and result["result"]["value"] == total
            assert request(manager_token, "export", view="all")[0] == 200
            if revoke:
                revoke()
            else:
                policy.write_text(json.dumps({"credentials": credentials[1:]}), encoding="utf-8")
            assert request(reader_token, "page", type="Shipment")[0] == 403
            assert request(reader_token, "query",
                           expression="SELECT COUNT(*) FROM Shipment")[0] == 403
            return {"database": database.name, "transport": "loopback HTTP",
                    "authority": type(gateway.authority).__name__, "all_orders": total,
                    "germany_orders": count, "germany_freight": round(freight, 2),
                    "checks": ["authentication", "discovery", "graph scope", "page scope",
                               "aggregate scope", "column visibility", "scope tampering denied",
                               "cross-view denied", "export permission", "revocation"],
                    "passed": True}
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.database), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
