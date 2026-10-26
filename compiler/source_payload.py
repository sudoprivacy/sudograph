"""Keep live source catalogues separate from embedded source-record payloads."""


def has_source_rows(model):
    if model.get("records") or model.get("source_schema", {}).get("snapshots"):
        return True
    source_projection = model.get("projection", {}).get("mode") == "source_projection"
    for view in model.get("views", {}).values():
        bound = {g["type"] for g in view.get("groups", []) if g.get("backing")}
        if any(n.get("kind") == "instance" and (source_projection or n.get("type") in bound)
               for n in view.get("nodes", [])):
            return True
        if any((source_projection or g.get("type") in bound)
               and (g.get("members") or g.get("top") or g.get("completeness"))
               for g in view.get("groups", [])):
            return True
        if source_projection and any(c.get("sample") for c in view.get("checks", [])):
            return True
    return False


def without_source_rows(view):
    """Compile/check with source rows, then retain only structural presentation.

    The legacy scalar view embeds small tables as instance nodes and members,
    even when portable record export is disabled. A native source catalogue has
    its own version-bound record reader, so none of those row presentations are
    part of a live baseline. Explicit snapshot exports retain their old payload.
    """
    nodes = [node for node in view.get("nodes", []) if node.get("kind") != "instance"]
    identities = {node["id"] for node in nodes}
    return {
        **view,
        "nodes": nodes,
        "edges": [edge for edge in view.get("edges", [])
                  if edge["from"] in identities and edge["to"] in identities],
        "groups": [{**group, "members": [], "top": {}, "buckets": {}, "completeness": {}}
                   for group in view.get("groups", [])],
        "checks": [{**check, "sample": []} for check in view.get("checks", [])],
    }
