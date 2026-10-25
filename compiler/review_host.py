"""Private stdin adapter for an authenticated host's read-only review route.

The host chooses the registered store, subject, resource and export permission.
This is not an HTTP server or an agent tool. Browser input cannot select any of
those arguments. The host must authorize each request before invoking it.
"""

import argparse
import json
import sys

from .gateway import Denied
from .model_contract import Refused
from .review import ReviewGateway
from .workspace import Workspace


class InvocationAuthority:
    """The already authorized invocation is valid for one exact host resource."""

    def __init__(self, actor, resource, *, export=False):
        if not actor.strip() or not resource:
            raise ValueError("host actor and registered resource are required")
        self.actor, self.resource, self.export = actor, resource, export

    def require(self, credential, resource, action):
        if (credential == self.actor and resource == self.resource
                and (action == "read" or (action == "export" and self.export))):
            return self.actor
        raise Denied("resource or operation unavailable")


def execute(store, actor, resource, request, *, export=False):
    authority = InvocationAuthority(actor, resource, export=export)
    gateway = ReviewGateway({resource: store}, authority)
    if not isinstance(request, dict):
        raise ValueError("expected a review request")
    if request.get("operation") == "html" and set(request) == {"operation", "endpoint"}:
        return gateway.html(actor, resource, endpoint=request["endpoint"])
    if set(request) - {"operation", "params"} or "operation" not in request:
        raise ValueError("expected operation and optional params")
    params = request.get("params", {})
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    return gateway.execute(actor, resource, request["operation"], **params)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--resource", required=True)
    parser.add_argument("--allow-export", action="store_true")
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(65537)
        if not raw or len(raw) > 65536:
            raise ValueError("review request size must be 1..65536 bytes")
        result = execute(Workspace(args.store), args.actor, args.resource,
                         json.loads(raw), export=args.allow_export)
        response = {"ok": True, "result": result}
    except Denied:
        response = {"ok": False, "error": {
            "code": "ACCESS_DENIED", "reason": "Resource or operation unavailable",
            "recovery": "Use the host's authorized review entry.",
        }}
    except (ValueError, KeyError, TypeError) as error:
        response = {"ok": False, "error": {
            "code": error.code if isinstance(error, Refused) else "READ_CONTRACT",
            "reason": str(error) if isinstance(error, Refused) else "Invalid review request",
            "recovery": (error.recovery if isinstance(error, Refused)
                         else "Read the review contract."),
        }}
    except Exception:
        # Private source paths and database diagnostics are not HTTP responses.
        response = {"ok": False, "error": {
            "code": "VIEW_UNAVAILABLE", "reason": "Registered review is unavailable",
            "recovery": "Ask the host operator to check this registered model.",
        }}
    print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
