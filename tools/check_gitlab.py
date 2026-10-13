"""Accept a real isolated GitLab, runner and publisher; never substitutes mocks.

The private deployment directory contains disposable credentials. Only the
explicit report file contains evidence suitable for a public CI artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import yaml

from compiler import app, business
from compiler.gitlab import Client, GitLabError
from compiler.managed import compile_model
from tools.gitlab_stack import COMPOSE, command, deploy


def service(token, body=None, *, path="/v1"):
    payload = None if body is None else json.dumps(body).encode()
    request = Request(
        "http://127.0.0.1:8788" + path,
        payload,
        {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            value = response.read()
            return response.status, json.loads(value) if body is not None else value
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def wait(check, label, *, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(2)
    raise RuntimeError("acceptance deadline: " + label)


def document(contract, *, version=1, statement="Should refunds reduce ticket amounts?"):
    obj = next(
        o for o in contract["source_schema"]["sources"][0]["objects"] if o["name"] == "Tickets"
    )
    return {
        "format": business.FORMAT,
        "namespace": contract["namespace"],
        "baseline": contract["baseline"],
        "definitions": {
            "refund": {
                "concept": "refund policy",
                "category": "meaning",
                "label": "Refund policy",
                "statement": statement,
                "origin": "inferred",
                "contributor": "model",
                "version": version,
                "targets": [obj["id"]],
            }
        },
        "views": {
            "meaning": {"label": "Business meaning", "definitions": ["refund"]},
            "questions": {"label": "Review questions", "definitions": ["refund"]},
        },
    }


def acceptance(folder):
    installation = deploy(folder)
    actors = installation["actors"]
    author, reviewer = actors["author"]["token"], actors["reviewer"]["token"]
    client = Client("http://127.0.0.1:8088", author, allow_http=True)
    review = Client(client.url, reviewer, allow_http=True)
    project = installation["model_project"]
    source_digest = hashlib.sha256((folder / "source.db").read_bytes()).hexdigest()
    checks = []

    def record(name):
        checks.append(name)
        print("PASS " + name, flush=True)

    def status(iid):
        code, response = service(author, {"operation": "status", "proposal": iid})
        if code != 200:
            raise RuntimeError("managed status refused")
        return response["result"]

    def submit(doc, intent):
        code, response = service(
            author, {"operation": "submit", "model": yaml.safe_dump(doc), "intent": intent}
        )
        if code != 200:
            raise RuntimeError("managed submit refused: " + str(response.get("reason")))
        return response["result"]

    def pipeline(iid, *, expected="success"):
        def ready():
            mr = client.mr(project, iid)
            value = mr.get("head_pipeline") or {}
            if value.get("status") in ("failed", "canceled", "skipped") and expected == "success":
                raise RuntimeError("native compiler pipeline did not succeed")
            return mr if value.get("sha") == mr["sha"] and value.get("status") == expected else None

        return wait(ready, "native pipeline " + expected)

    def approve(iid, sha):
        wait(
            lambda: (
                client.mr(project, iid).get("detailed_merge_status")
                not in ("checking", "approvals_syncing")
            ),
            "GitLab diff processing",
        )
        review.request(
            f"/projects/{project}/merge_requests/{iid}/approve", method="POST", data={"sha": sha}
        )

    code, _ = service("unregistered", {"operation": "contract"})
    assert code == 403
    code, answer = service(author, {"operation": "contract"})
    assert code == 200
    contract = answer["result"]
    record("GitLab authenticates the managed author; anonymous and unknown tokens are refused")
    doc = document(contract)
    bad = document(contract)
    bad["definitions"]["refund"]["targets"] = ["invented-field"]
    code, answer = service(
        author,
        {"operation": "submit", "model": yaml.safe_dump(bad), "intent": "Invalid source reference"},
    )
    assert code == 400 and answer["recovery"]
    code, _ = service(
        author,
        {
            "operation": "submit",
            "model": yaml.safe_dump(doc),
            "intent": "False authority",
            "approved": True,
        },
    )
    assert code == 400
    code, _ = service(author, {"operation": "publish", "html": "<h1>hand edited</h1>"})
    assert code == 400
    record("Invalid source IDs, caller approval flags and HTML fail through the same interface")

    proposal = submit(doc, "Propose the refund interpretation")
    iid = proposal["proposal"]
    mr = pipeline(iid)
    assert status(iid)["release"] is None
    assert not status(iid)["approval_for_current_sha"]
    record("A submission automatically runs real GitLab CI; successful compilation is not approval")
    # Author credentials cannot write the protected target or merge a proposal.
    for path, data in [
        (
            f"/projects/{project}/repository/commits",
            {
                "branch": "main",
                "commit_message": "Bypass review",
                "actions": [
                    {"action": "update", "file_path": "model.yaml", "content": yaml.safe_dump(doc)}
                ],
            },
        ),
        (f"/projects/{project}/merge_requests/{iid}/merge", {"sha": mr["sha"]}),
    ]:
        try:
            client.request(path, method="PUT" if path.endswith("/merge") else "POST", data=data)
        except GitLabError as exc:
            assert exc.status in (400, 401, 403, 405)
        else:
            raise AssertionError("author bypassed protected review")
    record("Native GitLab protections refuse author direct pushes and merges")
    approve(iid, mr["sha"])
    release = wait(lambda: status(iid)["release"], "authenticated hook and automatic publication")
    assert release["source_sha"] == mr["sha"]
    assert release["reviewers"] == [actors["reviewer"]["id"]]
    assert release["business_confirmation"] == "not inferred from merge approval"
    code, html = service(author, path="/releases/" + mr["sha"] + ".html")
    assert code == 200 and hashlib.sha256(html).hexdigest() == release["artifact_sha256"]
    path = folder / "released.html"
    path.write_bytes(html)
    model, _ = compile_model(
        yaml.safe_dump(doc), installation["baseline"], namespace=contract["namespace"]
    )
    app.check_export(path, model, language="en")
    assert model["source_schema"] == installation["baseline"]["source_schema"]
    identities = set(model["business"]["definitions"])
    views = model["business"]["views"]
    assert views["meaning"]["definitions"] == views["questions"]["definitions"]
    record("A GitLab review event causes automatic independent compile, merge and release")
    record(
        "Two business views reuse one canonical definition and all source facts remain unchanged"
    )

    next_doc = document(contract, version=2, statement="A second unconfirmed interpretation")
    next_proposal = submit(next_doc, "Draft: revise the interpretation")
    second = next_proposal["proposal"]
    mr2 = pipeline(second)
    approve(second, mr2["sha"])
    wait(lambda: status(second)["approval_for_current_sha"], "SHA-bound draft review event")
    assert status(second)["release"] is None
    next_doc["definitions"]["refund"].update(version=3, statement="A changed interpretation")
    changed = client.request(
        f"/projects/{project}/repository/commits",
        method="POST",
        data={
            "branch": mr2["source_branch"],
            "commit_message": "Change after review",
            "actions": [
                {"action": "update", "file_path": "model.yaml", "content": yaml.safe_dump(next_doc)}
            ],
        },
    )
    client.request(
        f"/projects/{project}/merge_requests/{second}",
        method="PUT",
        data={"title": "Revised interpretation"},
    )
    pipeline(second)
    assert not status(second)["approval_for_current_sha"] and status(second)["release"] is None
    record("Adding a commit invalidates old SHA-bound approval even when native CI succeeds")
    review.request(f"/projects/{project}/merge_requests/{second}/unapprove", method="POST")
    approve(second, changed["id"])
    release2 = wait(lambda: status(second)["release"], "fresh review of changed revision")
    next_model = business.build(next_doc, installation["baseline"])
    assert set(next_model["business"]["definitions"]) == identities
    assert release2["source_sha"] == changed["id"]
    record(
        "A fresh authenticated approval releases the new version without reallocating identities"
    )

    rollback_doc = document(contract, version=4)
    rollback = submit(rollback_doc, "Restore the earlier wording with a new reviewed version")
    rollback_mr = pipeline(rollback["proposal"])
    approve(rollback["proposal"], rollback_mr["sha"])
    release3 = wait(lambda: status(rollback["proposal"])["release"], "reviewed content rollback")
    assert (
        set(business.build(rollback_doc, installation["baseline"])["business"]["definitions"])
        == identities
    )
    code, historical = service(author, path="/releases/" + release["source_sha"] + ".html")
    assert code == 200 and historical == html
    record(
        "Reviewed content rollback keeps identities; the verified historical reader remains exact"
    )

    artifact = "/state/" + release["source_sha"] + ".html"
    writer = (
        "import sys;from pathlib import Path;Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())"
    )
    args = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE),
        "exec",
        "-T",
        "publisher",
        "python",
        "-c",
        writer,
        artifact,
    ]
    command(args, data=b"changed fixture artifact")
    code, response = service(author, path="/releases/" + release["source_sha"] + ".html")
    assert code == 503 and response["error"] == "ARTIFACT_CHANGED"
    command(args, data=html)
    record("Changing stored HTML is refused on read by the persisted artifact hash")

    # Direct Git commits are possible on proposal branches, but an added HTML file
    # fails the deployed trusted job rather than becoming publishable content.
    commit = client.request(
        f"/projects/{project}/repository/commits",
        method="POST",
        data={
            "branch": "attempt-html",
            "start_sha": release3["source_sha"],
            "commit_message": "Attempt HTML input",
            "actions": [{"action": "create", "file_path": "review.html", "content": "edited"}],
        },
    )
    invalid = client.request(
        f"/projects/{project}/merge_requests",
        method="POST",
        data={
            "source_branch": "attempt-html",
            "target_branch": "main",
            "title": "Invalid HTML input",
        },
    )
    pipeline(invalid["iid"], expected="failed")
    assert status(invalid["iid"])["release"] is None
    record("Hand-edited HTML committed directly to GitLab fails the real trusted CI job")
    assert hashlib.sha256((folder / "source.db").read_bytes()).hexdigest() == source_digest
    record("No step writes to the registered source database")
    operator = Client(client.url, actors["operator"]["token"], allow_http=True)
    operator.request(f"/projects/{project}/members/{actors['author']['id']}", method="DELETE")
    code, _ = service(author, {"operation": "contract"})
    assert code == 403
    code, _ = service(author, path="/releases/" + release["source_sha"] + ".html")
    assert code == 403
    operator.request(
        f"/projects/{project}/members",
        method="POST",
        data={
            "user_id": actors["author"]["id"],
            "access_level": 30,
        },
    )
    record("GitLab membership revocation blocks model and artifact reads immediately")
    return {
        "format": "sudograph-managed-acceptance/v1",
        "environment": "isolated Docker deployment",
        "synthetic_accounts": True,
        "checks": checks,
        "releases": [release, release2, release3],
        "invalid_proposal": {"source_sha": commit["id"], "pipeline": "failed"},
        "source_sha256": source_digest,
        "scope": "model review and publication; source write-back and Nexus SSO are separate",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_directory")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report = acceptance(Path(args.private_directory).resolve())
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
