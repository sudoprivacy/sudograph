"""Minimal JSON transport for Gateway. Operator config is outside ontology YAML."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from .gateway import Denied, FileCapabilities, Gateway, NexusAuthority, View
from .model_contract import Refused
from .nexus import NexusClient
from .review import ReviewGateway
from .spec import SpecError
from .workspace import Workspace


def bearer_credential(request):
    auth = request.headers.get("Authorization", "")
    return auth[7:] if auth.startswith("Bearer ") else ""


def handler(gateway, *, credential_resolver=bearer_credential):
    """The trusted host may reuse its session resolver; no credential in URL/YAML."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if not isinstance(gateway, ReviewGateway) or not self.path.startswith("/review/"):
                self.send_error(404)
                return
            if "?" in self.path or "#" in self.path:
                self.send_error(400)
                return
            try:
                resource = unquote(self.path[len("/review/"):], errors="strict")
                payload = gateway.html(credential_resolver(self), resource).encode("utf8")
                self.send_payload(200, payload, "text/html; charset=utf-8")
            except Denied:
                self.denied()
            except Exception:
                self.unavailable()

        def do_POST(self):
            if self.path != "/v1":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("request size must be 1..65536 bytes")
                body = json.loads(self.rfile.read(length))
                credential = credential_resolver(self)
                if body == {"operation": "contract"}:
                    result = gateway.discover(credential)
                else:
                    if not isinstance(body, dict) or set(body) - {"view", "operation", "params"}:
                        raise ValueError("expected view, operation and optional params")
                    result = gateway.execute(
                        credential, body["view"], body["operation"], **body.get("params", {})
                    )
                self.reply(200, {"result": result})
            except Denied:
                self.denied()
            except Refused as error:
                self.reply(error.status, {
                    "error": error.code, "reason": error.reason, "recovery": error.recovery,
                })
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

        def denied(self):
            self.reply(403, {
                "error": "ACCESS_DENIED",
                "reason": "Resource or operation unavailable",
                "recovery": "Use an authorised view; changing YAML cannot grant access.",
            })

        def unavailable(self):
            self.reply(503, {
                "error": "VIEW_UNAVAILABLE",
                "recovery": "Ask the operator to check the source and registered view.",
            })

        def reply(self, status, body):
            payload = json.dumps(body, ensure_ascii=False).encode()
            self.send_payload(status, payload, "application/json; charset=utf-8")

        def send_payload(self, status, payload, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
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
    if nexus := config.get("nexus"):
        authority = NexusAuthority(NexusClient(nexus["endpoint"], tls=nexus.get("tls")),
                                   nexus["grant_paths"])
    else:
        authority = FileCapabilities(path.parent / config["policy"])
    if "workspaces" in config:
        if "views" in config:
            raise ValueError("register workspaces or legacy views, not both")
        gateway = ReviewGateway({
            name: Workspace((path.parent / store).resolve())
            for name, store in config["workspaces"].items()
        }, authority)
    else:
        views = {
            name: View(str((path.parent / v["spec"]).resolve()), v.get("basis"), v.get("at"),
                       v.get("expected_mode"))
            for name, v in config["views"].items()
        }
        gateway = Gateway(views, authority)
    # Loopback only: a TLS-authenticated deployment must supply its trusted ingress.
    ThreadingHTTPServer(("127.0.0.1", args.port), handler(gateway)).serve_forever()


if __name__ == "__main__":
    main()
