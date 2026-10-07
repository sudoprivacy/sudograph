"""Minimal JSON transport for Gateway. Operator config is outside ontology YAML."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .gateway import Denied, FileCapabilities, Gateway, NexusAuthority, View
from .nexus import NexusClient
from .spec import SpecError


def handler(gateway):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/v1":
                self.send_error(404)
                return
            auth = self.headers.get("Authorization", "")
            credential = auth[7:] if auth.startswith("Bearer ") else ""
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("request size must be 1..65536 bytes")
                body = json.loads(self.rfile.read(length))
                if body == {"operation": "contract"}:
                    result = gateway.discover(credential)
                else:
                    result = gateway.execute(
                        credential, body["view"], body["operation"], **body.get("params", {})
                    )
                self.reply(200, {"result": result})
            except Denied:
                self.reply(
                    403,
                    {
                        "error": "ACCESS_DENIED",
                        "reason": "Resource or operation unavailable",
                        "recovery": "Use an authorised view; changing YAML cannot grant access.",
                    },
                )
            except SpecError:
                # Registered specs are operator configuration. Their failures
                # can mention source-wide counts/columns and must not leak them.
                self.unavailable()
            except (ValueError, KeyError, TypeError) as error:
                self.reply(
                    400,
                    {
                        "error": "INVALID_REQUEST",
                        "reason": str(error),
                        "recovery": "Read the contract and graph; repair the expression.",
                    },
                )
            except Exception:
                self.unavailable()

        def unavailable(self):
            self.reply(503, {
                "error": "VIEW_UNAVAILABLE",
                "recovery": "Ask the operator to check the source and registered view.",
            })

        def reply(self, status, body):
            payload = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            pass  # Never log bearer credentials or answerer queries.

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="operator-owned JSON: policy path and named view specs")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    path = Path(args.config).resolve()
    config = json.loads(path.read_text(encoding="utf-8"))
    views = {
        name: View(str((path.parent / v["spec"]).resolve()), v.get("basis"), v.get("at"),
                   v.get("expected_mode"))
        for name, v in config["views"].items()
    }
    if nexus := config.get("nexus"):
        authority = NexusAuthority(NexusClient(nexus["endpoint"], tls=nexus.get("tls")),
                                   nexus["grant_paths"])
    else:
        authority = FileCapabilities(path.parent / config["policy"])
    gateway = Gateway(views, authority)
    # Loopback only: a TLS-authenticated deployment must supply its trusted ingress.
    ThreadingHTTPServer(("127.0.0.1", args.port), handler(gateway)).serve_forever()


if __name__ == "__main__":
    main()
