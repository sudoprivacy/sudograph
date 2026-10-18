"""Bounded source-graph selection, shared by the reader and its HTTP transport."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, fields


@dataclass(frozen=True)
class Selection:
    root: str | None = field(default=None, metadata={
        "type": "identity", "description":
            "Source, object or field ID from the current catalogue; omit for overview."})
    hops: int = field(default=1, metadata={
        "type": "integer", "minimum": 0, "maximum": 5,
        "description": "Maximum undirected relationship distance from each selected root."})
    max_nodes: int = field(default=40, metadata={
        "type": "integer", "minimum": 1, "maximum": 200,
        "description": "Maximum displayed objects and component summaries per page."})
    component_offset: int = field(default=0, metadata={
        "type": "integer", "minimum": 0,
        "description": "Offset for independent component summaries; use next_component_offset."})


class SelectionError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.hint = subgraph_select.__doc__.partition("Failure:")[2].strip()
        self.retryable = False

    def as_dict(self):
        return {"error": self.code, "reason": str(self), "recovery": self.hint,
                "hint": self.hint, "retryable": self.retryable}


def contract():
    return {"description": subgraph_select.__doc__.partition("Failure:")[0].strip(),
            "parameters": {f.name: {**f.metadata, "default": f.default} for f in fields(Selection)},
            "relationships": ["source_fk", "source_view"],
            "llm_role": "Name or explain selected groups; propose new business relationships "
                        "through checked phase-two definitions, never by editing source links "
                        "or selection results."}


def _request(value):
    if not isinstance(value, dict) or set(value) - {f.name for f in fields(Selection)}:
        raise SelectionError("SUBGRAPH_INPUT", "selection contains unknown parameters")
    request = Selection(**value)
    for f in fields(Selection):
        v, m = getattr(request, f.name), f.metadata
        if m["type"] == "identity":
            valid = v is None or (isinstance(v, str) and bool(v))
        else:
            valid = type(v) is int and v >= m["minimum"] and v <= m.get("maximum", v)
        if not valid:
            raise SelectionError("SUBGRAPH_INPUT", f"invalid selection parameter: {f.name}")
    return request


def subgraph_select(schema, selection):
    """Use when a complete source graph is too large: select bounded related objects.

    Returns canonical node IDs, declared links, independent components, boundary
    counts and continuation parameters. Use these IDs for context/record reads;
    no second discovery call is needed to learn what was omitted. Algorithmic
    grouping is presentation, not a confirmed business domain. LLMs may explain
    or name a group; only declared foreign keys and source-SQL dependencies link
    source objects. Source-connector supply edges never merge unrelated regions.
    The caller must supply an already authorised schema; this grants no access.

    Failure:
        Read the current context catalogue and reuse a source/object/field ID.
        Use selection parameters from the subgraph contract; do not supply SQL,
        fabricated links or approval flags. Refresh context after a stale revision.
    """
    request = _request(selection)
    objects = {o["id"]: o for s in schema["sources"] for o in s["objects"]}
    sources = {s["id"]: {o["id"] for o in s["objects"]} for s in schema["sources"]}
    parents = {f["id"]: o["id"] for o in objects.values() for f in o["fields"]}
    adjacency = {key: set() for key in objects}
    edges = []
    for source in schema["sources"]:
        by_name = {o["name"]: o for o in source["objects"]}
        for obj in source["objects"]:
            for kind, names in [("source_view", obj["dependencies"]),
                                ("source_fk", sorted({f["table"] for f in obj["foreign_keys"]}))]:
                for name in names:
                    if name in by_name:
                        target = by_name[name]["id"]
                        edges.append({"kind": kind, "from": obj["id"], "to": target})
                        adjacency[obj["id"]].add(target)
                        adjacency[target].add(obj["id"])
    root = parents.get(request.root, request.root)
    if root is not None and root not in objects and root not in sources:
        raise SelectionError("SUBGRAPH_NOT_FOUND", "root is not in the authorised source catalogue")
    candidates = set(sources[root]) if root in sources else set(objects)
    components, pending = [], set(candidates)
    for first in sorted(candidates):
        if first not in pending:
            continue
        group, queue = {first}, deque([first])
        pending.remove(first)
        while queue:
            for neighbor in sorted(adjacency[queue.popleft()] & pending):
                pending.remove(neighbor)
                group.add(neighbor)
                queue.append(neighbor)
        components.append(sorted(group))
    if root in objects:
        components = [group for group in components if root in group]
        candidates = set(components[0])
    page = components[request.component_offset:request.component_offset + request.max_nodes]
    seeds = [root] if root in objects and page else [group[0] for group in page]
    selected, queue = set(seeds), deque((seed, 0) for seed in seeds)
    while queue:
        current, distance = queue.popleft()
        if distance >= request.hops:
            continue
        for neighbor in sorted(adjacency[current] & (candidates - selected)):
            if len(selected) >= request.max_nodes:
                break
            selected.add(neighbor)
            queue.append((neighbor, distance + 1))
    visible = [e for e in edges if e["from"] in selected and e["to"] in selected]
    crossing = [e for e in edges if e["from"] in candidates and e["to"] in candidates
                and ((e["from"] in selected) != (e["to"] in selected))]
    next_offset = request.component_offset + len(page)
    return {
        "scope": "authorised_source_structure", "algorithm": "weak_components_then_bounded_bfs",
        "selection": {f.name: getattr(request, f.name) for f in fields(Selection)},
        "focus": request.root, "objects_in_scope": len(candidates),
        "nodes": [{k: objects[key][k] for k in ("id", "name", "label", "object_kind")}
                  for key in sorted(selected)], "edges": visible,
        "partial": selected != candidates,
        "boundary": {"outside_objects": len(candidates - selected),
                     "crossing_edges": len(crossing),
                     "examples": crossing[:request.max_nodes]},
        "component_count": len(components),
        "components": [{"root": group[0], "objects": len(group)} for group in page],
        "next_component_offset": next_offset if next_offset < len(components) else None,
        "continuation": [{"root": group[0], "hops": request.hops, "max_nodes": request.max_nodes}
                         for group in page],
        "interpretation": "Structural presentation only; no meanings or source facts were added.",
    }
