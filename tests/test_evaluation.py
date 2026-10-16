"""Always-present source questions with separate, version-bound judge answers."""

import copy
import hashlib
import json
import sqlite3

import pytest
from test_business import base as business_fixture

from compiler import app, blind, business, evaluation
from compiler.context import Reader


@pytest.fixture
def prepared(tmp_path):
    model, doc = business_fixture.__wrapped__(tmp_path)
    model = business.build(doc, model)
    path = tmp_path / "unrelated.db"
    sources = [{"source": model["source_schema"]["sources"][0]["id"],
                "dsn": "sqlite:///" + path.as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
    return model, sources, path


def test_source_questions_survive_business_views_and_never_contain_an_oracle(prepared):
    model, _, _ = prepared
    challenge = model["challenge"]
    assert len(challenge["questions"]) > 3
    assert {q["source_object"] for q in challenge["questions"]} == {"Tickets", "Totals"}
    assert all(set(q) == {"id", "source_object", "target", "kind", "question"}
               for q in challenge["questions"])
    blind.public_only(challenge)
    assert Reader(model).read("evaluation") == {"status": "not_run", "challenge": challenge}
    for key in ["sql", "answer", "expected"]:
        tampered = copy.deepcopy(challenge)
        tampered["questions"][0][key] = "private"
        with pytest.raises(ValueError, match="public questions"):
            blind.public_only(tampered)
    for change in [lambda m: m.pop("challenge"),
                   lambda m: m["challenge"]["questions"].pop()]:
        tampered = copy.deepcopy(model)
        change(tampered)
        with pytest.raises(ValueError, match="evaluation questions"):
            app.render(tampered)


def test_source_answers_are_computed_from_pinned_raw_db_and_missing_answers_stay_scored(prepared):
    model, sources, _ = prepared
    oracle = blind.oracle_for_schema(model["source_schema"], sources)
    count = next(q for q in model["challenge"]["questions"]
                 if q["source_object"] == "Tickets" and q["kind"] == "count")
    assert oracle[count["id"]]["answer"] == 2
    chosen, private = evaluation.prepare(model, sources, count=3, seed=42)
    assert evaluation.prepare(model, sources, count=3, seed=42) == (chosen, private)
    assert len({q["id"] for q in chosen["questions"]}) == 3
    result = evaluation.grade(private, {"model_digest": private["model_digest"], "answers": {}})
    assert result["total"] == 3 and result["passed"] == 0
    submission = {"model_digest": private["model_digest"],
                  "answers": {qid: item["answer"] for qid, item in private["oracle"].items()}}
    assert evaluation.grade(private, submission)["passed"] == 3
    with pytest.raises(ValueError, match="model digest"):
        evaluation.grade(private, {**submission, "model_digest": "another-model"})


def test_judge_refuses_wrong_database_and_changed_source_hash(prepared):
    model, sources, path = prepared
    with pytest.raises(ValueError, match="register every source"):
        blind.oracle_for_schema(model["source_schema"], [{**sources[0], "source": "wrong"}])
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE Tickets SET amount=99 WHERE id=1")
    with pytest.raises(ValueError, match="registered hash"):
        blind.oracle_for_schema(model["source_schema"], sources)


def test_no_scores_are_invented_by_context_or_rendering(prepared):
    model, _, _ = prepared
    public = json.dumps(model["challenge"])
    assert '"answer"' not in public and '"sql"' not in public
    assert Reader(model).payload["evaluation"]["status"] == "not_run"
    html = app.render(model)
    assert 'id="openSourceQuestions"' in html
    assert "Database object type" in html


def test_automatic_questions_support_implicit_composite_foreign_keys(tmp_path):
    path = tmp_path / "implicit.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE Parent(a INTEGER,b INTEGER,PRIMARY KEY(a,b));
            CREATE TABLE Child(id INTEGER PRIMARY KEY,x INTEGER,y INTEGER,
              FOREIGN KEY(x,y) REFERENCES Parent);
            INSERT INTO Parent VALUES(1,2);
            INSERT INTO Child VALUES(1,1,2),(2,3,4),(3,NULL,4);
        """)
    challenge, oracle = blind.generate("sqlite:///" + path.as_posix())
    question = next(q for q in challenge["questions"] if q["kind"].startswith("missing-target:"))
    assert oracle[question["id"]]["answer"] == 1
    assert "populated x, y" in question["question"]


def test_judge_refuses_unhashed_wal_changes(prepared):
    model, sources, path = prepared
    with sqlite3.connect(path) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        sources[0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        writer.execute("UPDATE Tickets SET amount=99 WHERE id=1")
        writer.commit()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sources[0]["sha256"]
        with pytest.raises(ValueError, match="checkpointed source snapshot"):
            blind.oracle_for_schema(model["source_schema"], sources)
