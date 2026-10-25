"""Read-only review transport for registered canonical authoring stores.

The host supplies registration and the existing Gateway authority. A resource
grant currently authorizes its complete registered model/source scope; this is
not a row/field policy adapter. No paths, actors or model writes are HTTP inputs.
"""

from .gateway import Denied
from .model_contract import Refused
from .workspace import Workspace

OPERATIONS = ["head", "graph", "context", "page", "export"]
CONTRACT = {
    "format": "sudograph-review/v1",
    "operations": OPERATIONS,
    "source_access": "complete registered resource scope; host-authorized on every operation",
    "model_writes": False,
}


class ReviewGateway:
    def __init__(self, workspaces, authority):
        if authority is None:
            raise ValueError("ReviewGateway requires an authority")
        if any(not isinstance(store, Workspace) for store in workspaces.values()):
            raise ValueError("review resources must be operator-registered workspaces")
        self.workspaces, self.authority = dict(workspaces), authority

    def _authorize(self, credential, resource, action="read"):
        self.authority.require(credential, resource, action)
        if resource not in self.workspaces:
            raise Denied("resource or operation unavailable")
        return self.workspaces[resource]

    def discover(self, credential):
        available = []
        for resource in self.workspaces:
            try:
                self._authorize(credential, resource)
            except Denied:
                continue
            available.append(resource)
        return {**CONTRACT, "views": available}

    def html(self, credential, resource, *, endpoint="/v1"):
        store = self._authorize(credential, resource)
        head = store.head()
        self._check_embedded_export(credential, resource, store, head["revision"])
        return store.review({"endpoint": endpoint, "resource": resource}, revision=head["revision"])

    def _check_embedded_export(self, credential, resource, store, revision):
        model = store.read(revision=revision, product="model")
        if model.get("records") or model.get("source_schema", {}).get("snapshots"):
            # Frozen record bytes must not become an implicit bulk export via
            # a graph or HTML read. Normal live review contains neither payload.
            self.authority.require(credential, resource, "export")
        return model

    def execute(self, credential, resource, operation, **params):
        # Authorize before any store lookup, including unsupported operations.
        store = self._authorize(credential, resource, "export" if operation == "export" else "read")
        if operation not in OPERATIONS:
            raise Refused("READ_CONTRACT", "Unsupported review operation", "Read the contract")
        if operation == "page":
            if not {"revision", "context_digest", "id"} <= params.keys() or params.keys() - {
                "revision", "context_digest", "id", "offset", "limit"
            }:
                raise Refused(
                    "READ_CONTRACT", "Expected a version-bound source object page",
                    "Use revision, context_digest and an object id from the graph",
                )
            result = store.context_read({**params, "records": True})
            return {**result, "revision": params["revision"],
                    "context_digest": params["context_digest"]}
        if params:
            raise Refused(
                "READ_CONTRACT", "This operation takes no parameters", "Read the contract"
            )
        if operation == "head":
            return store.head()
        # Pin before reading: a concurrent edit cannot mix graph and context.
        head = store.head()
        if operation == "export":
            return store.read(revision=head["revision"], product="html")
        if operation == "graph":
            return self._check_embedded_export(credential, resource, store, head["revision"])
        return store.read(revision=head["revision"], product="context")
