"""Judge-side question generation from raw schema/data, independent of ontology.

Only the public half is delivered to the answerer. Do not place the private
oracle, database, source spec or server credentials in the answerer's sandbox.
The graph gateway is its sole data capability. This module never calls an LLM
and makes no claim that an agent run has happened.
"""

from __future__ import annotations

import hashlib
import json
import random
import secrets
from pathlib import Path

from . import bind, catalog, source_schema
from .query import quote


def _plan(objects, *, include_views=False):
    """One question grammar for source catalogues and independent raw SQL judges."""
    public, queries = [], {}
    by_name = {obj["name"]: obj for obj in objects}

    def add(table, kind, prompt, sql):
        qid = hashlib.sha256((table + ":" + kind).encode()).hexdigest()[:16]
        public.append({"id": qid, "source_object": table, "kind": kind, "question": prompt})
        queries[qid] = sql

    for obj in objects:
        if obj["kind"] != "table" and not include_views:
            continue
        name, q = obj["name"], quote(obj["name"])
        add(name, "count", f"How many records of {name} are represented?",
            f"SELECT count(*) FROM {q}")
        for c in obj["columns"]:
            col = quote(c["name"])
            add(name, "null:" + c["name"], f"How many {name} records have no {c['name']}?",
                f"SELECT count(*) FROM {q} WHERE {col} IS NULL")
            if any(x in (c["type"] or "").upper() for x in ("INT", "NUM", "REAL", "DEC")):
                for agg in ("min", "max"):
                    add(name, agg + ":" + c["name"],
                        f"What is the {agg}imum {c['name']} in {name}?",
                        f"SELECT {agg}({col}) FROM {q}")
        for f in obj["foreign_keys"]:
            if f["seq"] != 0:
                continue
            peers = [x for x in obj["foreign_keys"] if x["id"] == f["id"]]
            target = by_name.get(f["table"])
            if target is None:
                continue
            primary = sorted((c for c in target["columns"] if c.get("pk")), key=lambda c: c["pk"])
            if any(not p["to"] and p["seq"] >= len(primary) for p in peers):
                continue
            condition = " AND ".join(
                f"s.{quote(x['from'])} = t.{quote(x['to'] or primary[x['seq']]['name'])}"
                for x in peers
            )
            present = " AND ".join(f"s.{quote(x['from'])} IS NOT NULL" for x in peers)
            fields = ", ".join(x["from"] for x in sorted(peers, key=lambda x: x["seq"]))
            add(
                name, "missing-target:" + str(f["id"]),
                f"How many {name} records have a populated {fields} "
                f"without a matching {f['table']} record?",
                f"SELECT count(*) FROM {q} s WHERE {present} AND NOT EXISTS "
                f"(SELECT 1 FROM {quote(f['table'])} t WHERE {condition})",
            )
    return public, queries


def generate(dsn, base="."):
    with bind.connect(dsn, base) as conn:
        conn.execute("BEGIN")
        public, queries = _plan(catalog.inventory(conn))
        oracle = {qid: {"answer": conn.execute(sql).fetchone()[0], "sql": sql}
                  for qid, sql in queries.items()}
    return {"protocol": "raw-source / graph-only answerer", "questions": public}, oracle


def for_schema(schema):
    """Questions persist with the source projection, independently of authored metrics.

    Only the raw schema inventory collected by the scanner is used; no record
    values or answers are read here. The judge later evaluates SQL on pinned DBs.
    """
    public = []
    for source in schema["sources"]:
        objects = [{"name": o["name"], "kind": o["object_kind"],
                    "columns": [{"name": f["column"], "type": f["declared_type"],
                                 "pk": f["primary_key"]}
                                for f in o["fields"]], "foreign_keys": o["foreign_keys"]}
                   for o in source["objects"]]
        questions, _ = _plan(objects, include_views=True)
        targets = {o["name"]: o["id"] for o in source["objects"]}
        for question in questions:
            target = targets[question["source_object"]]
            public.append({**question, "target": target,
                           "id": hashlib.sha256((target + ":" + question["kind"]).encode())
                           .hexdigest()[:16]})
    return {"protocol": "source-catalog / graph-only answerer; raw-source oracle",
            "questions": public}


def sample(challenge, count=3, *, seed=None):
    public_only(challenge)
    if type(count) is not int or not 1 <= count <= len(challenge["questions"]):
        raise ValueError("sample size must be 1..question count")
    seed = secrets.randbits(64) if seed is None else seed
    return {"protocol": challenge["protocol"],
            "questions": random.Random(seed).sample(challenge["questions"], count)}, seed


def oracle_for_schema(schema, registrations, *, question_ids=None):
    """Judge-side only: exact source identities and file hashes bind the raw oracle.

    Registrations are operator-owned {source, dsn, sha256, base?} dictionaries.
    They must never be sent to an answerer or embedded into a reader/export.
    """
    if (len(registrations) != len(schema["sources"])
            or {r["source"] for r in registrations} != {s["id"] for s in schema["sources"]}):
        raise ValueError("register every source exactly once for the judge")
    questions = for_schema(schema)["questions"]
    known_ids = {q["id"] for q in questions}
    if question_ids is not None and set(question_ids) - known_ids:
        raise ValueError("judge question IDs are outside the registered source catalogue")
    oracle = {}
    for registration in registrations:
        dsn, base = registration["dsn"], registration.get("base", ".")
        sid = source_schema.source_id(dsn, base)
        path = Path(bind._path_of(dsn, base))

        def unchanged(path=path, registration=registration):
            wal = Path(str(path) + "-wal")
            if wal.exists() and wal.stat().st_size:
                raise ValueError("judge requires a checkpointed source snapshot without a WAL")
            if hashlib.sha256(path.read_bytes()).hexdigest() != registration["sha256"]:
                raise ValueError("judge source file differs from its registered hash")

        if sid != registration["source"]:
            raise ValueError("judge source identity differs from the registered projection")
        unchanged()
        with bind.connect(dsn, base) as conn:
            conn.execute("BEGIN")
            unchanged()
            inventory = catalog.inventory(conn)
            expected = next(s for s in schema["sources"] if s["id"] == sid)
            if {o["name"]: o["count"] for o in inventory} != {
                o["name"]: o["count"] for o in expected["objects"]
            }:
                raise ValueError("raw source counts differ from the registered projection")
            raw, queries = _plan(inventory, include_views=True)
            by_key = {(q["source_object"], q["kind"]): queries[q["id"]] for q in raw}
            selected = [q for q in questions if q["target"].startswith(sid + "/object/")]
            if {(q["source_object"], q["kind"]) for q in selected} != set(by_key):
                raise ValueError("raw source question inventory differs from the projection")
            for q in selected:
                if question_ids is not None and q["id"] not in question_ids:
                    continue
                sql = by_key[(q["source_object"], q["kind"])]
                oracle[q["id"]] = {"answer": source_schema.wire(conn.execute(sql).fetchone()[0]),
                                   "sql": sql}
        unchanged()
    return oracle


def grade(oracle, answers):
    """Missing/unanswerable remain visible; nothing is silently removed from denominator."""
    results = [
        {
            "id": qid,
            "expected": q["answer"],
            "got": answers.get(qid),
            "answered": qid in answers,
            "ok": qid in answers and answers[qid] == q["answer"],
        }
        for qid, q in oracle.items()
    ]
    return {"passed": sum(q["ok"] for q in results), "total": len(results), "results": results}


def public_only(challenge):
    """Reject an oracle accidentally supplied to a public export."""
    if set(challenge) != {'protocol', 'questions'} or not isinstance(challenge['questions'], list):
        raise ValueError('expected a public challenge, never a private oracle')
    for question in challenge['questions']:
        if (set(question) - {'target'} != {'id', 'source_object', 'kind', 'question'}
                or any(not isinstance(v, str) for v in question.values())):
            raise ValueError('public questions must not contain answers, SQL or extra fields')
    ids = [q['id'] for q in challenge['questions']]
    if len(set(ids)) != len(ids):
        raise ValueError('public questions must have unique IDs')
    return challenge


def write_challenge(dsn, public_path, private_path, base="."):
    if Path(public_path).resolve().parent == Path(private_path).resolve().parent:
        raise ValueError("public challenge and private oracle must be in separate directories")
    public, private = generate(dsn, base)
    for path, value in [(public_path, public), (private_path, private)]:
        Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dsn")
    parser.add_argument("public_questions")
    parser.add_argument("private_oracle")
    args = parser.parse_args()
    write_challenge(args.dsn, args.public_questions, args.private_oracle)
