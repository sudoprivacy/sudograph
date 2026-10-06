"""Judge-side question generation from raw schema/data, independent of ontology.

Only the public half is delivered to the answerer. Do not place the private
oracle, database, source spec or server credentials in the answerer's sandbox.
The graph gateway is its sole data capability. This module never calls an LLM
and makes no claim that an agent run has happened.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import bind, catalog
from .query import quote


def generate(dsn, base="."):
    public, oracle = [], {}
    objects = catalog.scan(dsn, base)
    with bind.connect(dsn, base) as conn:

        def add(table, kind, prompt, sql):
            qid = hashlib.sha256((table + ":" + kind).encode()).hexdigest()[:16]
            public.append({"id": qid, "source_object": table, "kind": kind, "question": prompt})
            oracle[qid] = {"answer": conn.execute(sql).fetchone()[0], "sql": sql}

        for obj in objects:
            if obj["kind"] != "table":
                continue
            name, q = obj["name"], quote(obj["name"])
            add(
                name,
                "count",
                f"How many records of {name} are represented?",
                f"SELECT count(*) FROM {q}",
            )
            for c in obj["columns"]:
                col = quote(c["name"])
                add(
                    name,
                    "null:" + c["name"],
                    f"How many {name} records have no {c['name']}?",
                    f"SELECT count(*) FROM {q} WHERE {col} IS NULL",
                )
                if any(x in c["type"].upper() for x in ("INT", "NUM", "REAL", "DEC")):
                    for agg in ("min", "max"):
                        add(
                            name,
                            agg + ":" + c["name"],
                            f"What is the {agg}imum {c['name']} in {name}?",
                            f"SELECT {agg}({col}) FROM {q}",
                        )
            for f in obj["foreign_keys"]:
                if f["seq"] != 0:
                    continue
                peers = [x for x in obj["foreign_keys"] if x["id"] == f["id"]]
                condition = " AND ".join(
                    f"s.{quote(x['from'])} = t.{quote(x['to'])}" for x in peers
                )
                present = " AND ".join(f"s.{quote(x['from'])} IS NOT NULL" for x in peers)
                add(
                    name,
                    "missing-target:" + str(f["id"]),
                    f"How many {name} records have a populated {f['from']} "
                    f"without a matching {f['table']} record?",
                    f"SELECT count(*) FROM {q} s WHERE {present} AND NOT EXISTS "
                    f"(SELECT 1 FROM {quote(f['table'])} t WHERE {condition})",
                )
    return {"protocol": "raw-source / graph-only answerer", "questions": public}, oracle


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
        if set(question) != {'id', 'source_object', 'kind', 'question'}:
            raise ValueError('public questions must not contain answers, SQL or extra fields')
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
