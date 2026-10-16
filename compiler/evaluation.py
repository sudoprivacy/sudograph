"""Prepare reproducible blind samples and grade answers on the private judge side.

No LLM is called. The public side contains questions only; oracle SQL, answers
and source registrations stay with the judge. A missing answer is still scored.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import blind, business

FORMAT = "sudograph-source-evaluation/v1"


def prepare(model, sources, *, count=3, seed=None):
    challenge = blind.for_schema(model["source_schema"])
    chosen, seed = blind.sample(challenge, count, seed=seed)
    oracle = blind.oracle_for_schema(model["source_schema"], sources,
                                     question_ids={q["id"] for q in chosen["questions"]})
    digest = business.digest({"source": model["source_schema"],
                              "business": model.get("business", {}).get("document")})
    private = {
        "format": FORMAT, "model_digest": digest,
        "source_digest": business.digest(model["source_schema"]),
        "seed": seed, "question_ids": [q["id"] for q in chosen["questions"]],
        "oracle": {q["id"]: oracle[q["id"]] for q in chosen["questions"]},
    }
    return chosen, private


def grade(private, submission):
    if (private.get("format") != FORMAT
            or set(private["question_ids"]) != set(private["oracle"])):
        raise ValueError("invalid registered judge run")
    if (set(submission) != {"model_digest", "answers"}
            or submission["model_digest"] != private["model_digest"]
            or not isinstance(submission["answers"], dict)
            or set(submission["answers"]) - set(private["question_ids"])):
        raise ValueError("answers require the registered model digest and question IDs")
    return {"format": FORMAT, "status": "graded", "model_digest": private["model_digest"],
            "source_digest": private["source_digest"], "seed": private["seed"],
            **blind.grade(private["oracle"], submission["answers"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    start = sub.add_parser("prepare")
    start.add_argument("model")
    start.add_argument("sources", help="operator-only JSON source registrations")
    start.add_argument("public_questions")
    start.add_argument("private_run")
    start.add_argument("--sample", type=int, default=3)
    start.add_argument("--seed", type=int)
    finish = sub.add_parser("grade")
    finish.add_argument("private_run")
    finish.add_argument("submission")
    args = parser.parse_args(argv)
    if args.operation == "prepare":
        public_path, private_path = Path(args.public_questions), Path(args.private_run)
        if public_path.resolve().parent == private_path.resolve().parent:
            parser.error("public questions and private judge run require separate directories")
        model = business.load(args.model)
        registry = Path(args.model).with_suffix(".registry.json")
        business.registry(model, json.loads(registry.read_text(encoding="utf8"))
                          if registry.exists() else {})
        chosen, private = prepare(model, json.loads(Path(args.sources).read_text(encoding="utf8")),
                                  count=args.sample, seed=args.seed)
        for path, value in [(public_path, chosen), (private_path, private)]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        print(json.dumps({"status": "prepared_not_run", "questions": len(chosen["questions"]),
                          "seed": private["seed"], "model_digest": private["model_digest"]}))
    else:
        private = json.loads(Path(args.private_run).read_text(encoding="utf8"))
        submission = json.loads(Path(args.submission).read_text(encoding="utf8"))
        print(json.dumps(grade(private, submission), ensure_ascii=False))


if __name__ == "__main__":
    main()
