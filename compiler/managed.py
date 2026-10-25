"""Managed model submissions, GitLab review events and verified publication.

The model repository never supplies compiler code, policy, credentials or HTML.
GitLab owns revision history and authenticates reviewers. An authenticated GitLab event
binds its approval to a revision; the publisher independently compiles that
revision before it may merge or serve an artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import app, business
from .context import Reader, registered_pointers
from .gitlab import Client, GitLabError
from .model_contract import MODEL_FILE, SOURCE_REQUEST, Refused, compile_model
from .subgraph_select import SelectionError
from .subgraph_select import contract as subgraph_contract

SHA = re.compile(r"^[0-9a-f]{40}$")
ROOT = Path(__file__).resolve().parent.parent


def code_digest():
    digest = hashlib.sha256()
    for folder in (ROOT / "compiler", ROOT / "app"):
        for path in sorted(folder.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                digest.update(path.relative_to(ROOT).as_posix().encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


class Publisher:
    def __init__(self, policy):
        allowed = {
            "gitlab_url",
            "allow_http",
            "token",
            "webhook_secret",
            "project_id",
            "pipeline_project_id",
            "ci_config_path",
            "ci_config_sha256",
            "baseline_file",
            "state_dir",
            "authors",
            "reviewers",
            "language",
            "bootstrap_sha",
            "namespace",
        }
        if set(policy) - {"knowledge_pointers"} != allowed:
            raise ValueError("operator policy has missing or unknown fields")
        self.knowledge_pointers = registered_pointers(policy.get("knowledge_pointers", []))
        if (
            not policy["authors"]
            or not policy["reviewers"]
            or set(policy["authors"]) & set(policy["reviewers"])
            or any(type(i) is not int or i < 1 for i in [*policy["authors"], *policy["reviewers"]])
            or len(policy["webhook_secret"]) < 32
            or not SHA.fullmatch(policy["bootstrap_sha"])
        ):
            raise ValueError(
                "register separate author/reviewer identities and a strong webhook credential"
            )
        self.policy = policy
        self.client = Client(policy["gitlab_url"], policy["token"], allow_http=policy["allow_http"])
        self.baseline = json.loads(Path(policy["baseline_file"]).read_text(encoding="utf8"))
        self.pin = {
            "manifest": "registered-source-baseline",
            "sha256": business.digest(self.baseline),
        }
        self.compiler = code_digest()
        self.context = business.digest(
            {
                "baseline": self.pin,
                "compiler": self.compiler,
                "project": policy["project_id"],
                "language": policy["language"],
                "authors": policy["authors"],
                "reviewers": policy["reviewers"],
                "namespace": policy["namespace"],
            }
        )
        self.state = Path(policy["state_dir"])
        self.state.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.registry_cache = {}
        with self.database() as database:
            database.execute(
                "CREATE TABLE IF NOT EXISTS approvals "
                "(iid INTEGER, sha TEXT, reviewer INTEGER, context TEXT, "
                "PRIMARY KEY(iid,sha,reviewer))"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS releases "
                "(iid INTEGER PRIMARY KEY, sha TEXT, receipt TEXT)"
            )
            database.execute(
                "CREATE TABLE IF NOT EXISTS prepared "
                "(iid INTEGER PRIMARY KEY, sha TEXT, context TEXT, receipt TEXT)"
            )
        compile_model(json.dumps({"format": SOURCE_REQUEST, "baseline": self.pin}), self.baseline)

    def database(self):
        return sqlite3.connect(self.state / "publication.db", timeout=10)

    @property
    def project(self):
        return self.policy["project_id"]

    def actor(self, token, roles=("authors", "reviewers")):
        try:
            caller = Client(self.policy["gitlab_url"], token, allow_http=self.policy["allow_http"])
            actor = caller.actor()
            project = caller.request(f"/projects/{self.project}")
            permission = project.get("permissions", {})
            levels = [
                (permission.get(key) or {}).get("access_level", 0)
                for key in ("project_access", "group_access")
            ]
            if max(levels) < 30:
                raise GitLabError("GitLab project membership is no longer authorised")
        except GitLabError:
            raise Refused(
                "ACTOR_DENIED",
                "GitLab identity or current project access could not be authorised",
                "Use an authorised account",
                403,
            ) from None
        if not any(actor["id"] in self.policy[role] for role in roles):
            raise Refused(
                "ACTOR_DENIED",
                "identity has no registered model authority",
                "Use an authorised account; model YAML cannot grant permissions",
                403,
            )
        return actor

    def target(self):
        return self.client.request(f"/projects/{self.project}/repository/branches/main")["commit"][
            "id"
        ]

    def audit(self):
        project = self.client.request(f"/projects/{self.project}")
        if (
            project.get("visibility") != "private"
            or project.get("ci_config_path") != self.policy["ci_config_path"]
            or not project.get("only_allow_merge_if_pipeline_succeeds")
            or project.get("allow_merge_on_skipped_pipeline")
            or project.get("merge_method") != "ff"
        ):
            raise Refused(
                "DEPLOYMENT_DRIFT",
                "GitLab project lost its managed checks",
                "Ask the deployment owner to restore project settings",
                503,
            )
        protection = self.client.request(f"/projects/{self.project}/protected_branches/main")
        if (
            protection.get("allow_force_push")
            or not protection.get("push_access_levels")
            or not protection.get("merge_access_levels")
            or any(a["access_level"] != 0 for a in protection["push_access_levels"])
            or any(a["access_level"] < 40 for a in protection["merge_access_levels"])
        ):
            raise Refused(
                "DEPLOYMENT_DRIFT",
                "target branch permits an unguarded update",
                "Restore no direct pushes and maintainer-only merges",
                503,
            )
        config = self.client.file(self.policy["pipeline_project_id"], "pipeline.yml", "main")
        if hashlib.sha256(config.encode()).hexdigest() != self.policy["ci_config_sha256"]:
            raise Refused(
                "DEPLOYMENT_DRIFT",
                "operator pipeline differs from its registered version",
                "Review and deploy the intended pipeline version",
                503,
            )

    def document(self, sha):
        if not SHA.fullmatch(sha):
            raise Refused(
                "REVISION_REQUIRED",
                "request does not name an immutable Git revision",
                "Use the proposal's exact source SHA",
            )
        tree = self.client.pages(
            f"/projects/{self.project}/repository/tree", ref=sha, recursive=True
        )
        if len(tree) != 1 or tree[0].get("path") != MODEL_FILE or tree[0].get("mode") != "100644":
            raise Refused(
                "INPUT_INVENTORY",
                "model repository contains unregistered files or links",
                "Submit model.yaml only; compiler, policy, CI and HTML belong to deployment",
            )
        return self.client.file(self.project, MODEL_FILE, sha)

    def registry(self, head):
        if head in self.registry_cache:
            return self.registry_cache[head]
        commits = self.client.pages(
            f"/projects/{self.project}/repository/commits", ref_name=head, first_parent=True
        )
        history = []
        for commit in commits:
            history.append(commit["id"])
            if commit["id"] == self.policy["bootstrap_sha"]:
                break
        else:
            raise Refused(
                "HISTORY_DIVERGED",
                "target history lost its registered bootstrap",
                "Have the operator review the history; do not invent a registry",
                503,
            )
        previous = {}
        for sha in reversed(history):
            _, previous = compile_model(
                self.document(sha), self.baseline, previous,
                namespace=self.policy["namespace"], _history=True,
            )
        self.registry_cache[head] = previous
        return previous

    def checked(self, sha, target=None):
        content = self.document(sha)
        model, registry = compile_model(
            content,
            self.baseline,
            self.registry(target or self.target()),
            namespace=self.policy["namespace"],
        )
        return content, model, registry

    def proposal(self, iid):
        mr = self.client.mr(self.project, iid)
        if (
            mr.get("target_project_id") != self.project
            or mr.get("source_project_id") != self.project
            or mr.get("target_branch") != "main"
            or mr.get("author", {}).get("id") not in self.policy["authors"]
        ):
            raise Refused(
                "PROPOSAL_SCOPE",
                "proposal is outside the registered model/review scope",
                "Submit through the registered project and author interface",
                403,
            )
        return mr

    def reviewer_current(self, identity):
        try:
            member = self.client.request(f"/projects/{self.project}/members/all/{identity}")
        except GitLabError as error:
            if error.status in (403, 404):
                return False
            raise
        return member.get("state") == "active" and member.get("access_level", 0) >= 30

    def contract(self):
        self.audit()
        target = self.target()
        return {
            "model_file": MODEL_FILE,
            "knowledge_operations": ["context", "context_read"],
            "subgraph": subgraph_contract(include_recovery=False),
            "evaluation": {"read": "context_read with id: evaluation",
                           "questions": "automatic source-catalog questions; private raw-DB oracle",
                           "score": "not_run until isolated answerer responses are graded"},
            "source_format": SOURCE_REQUEST,
            "business_format": business.FORMAT,
            "baseline": self.pin,
            "namespace": self.policy["namespace"],
            "source_schema": self.baseline["source_schema"],
            "target_sha": target,
            "current_model": self.document(target),
            "identity_registry": self.registry(target),
            "source_binding": {
                "pending": "v5 business definitions may use targets: []; source reviews may not",
                "identity": "concept identity is reserved independently of source bindings",
                "metric": "unbound metrics retain scope; grain is empty until source fields bind; "
                          "source references do not establish executability or business approval",
            },
            "submit": {
                "operation": "submit",
                "model": "complete YAML text",
                "intent": "1..255 character review intent",
            },
            "definition_required": [
                "concept",
                "category",
                "role",
                "label",
                "statement",
                "origin",
                "contributor",
                "targets",
                "version",
            ],
            "definition_categories": ["meaning", "metric", "rule", "issue"],
            "definition_roles": {
                "business": "meanings/metrics require purpose: stakeholder and decision; "
                "rules/issues require a named business subject",
                "source_review": "phase-one data question; category: issue; source targets and "
                "a verification plan required; no business dependencies or view entries",
                "source_evidence": "provided source observation with a checked quote; "
                "attach through applies_to; details only",
                "implementation_note": "supporting calculation/implementation detail; "
                "attach through applies_to; details only",
            },
            "authoring_guidance": {
                "phase_one": "Preserve the complete source projection. Put questions about source "
                "precision, missing values, keys or source-view time coverage in source_review, "
                "with a verification plan. A question is not proof of a source defect.",
                "phase_two": "Propose what the business means and how people use it: stakeholders, "
                "decisions, metrics, policies and business relationships. "
                "Renaming source SQL or adding a data-quality question does not "
                "establish business meaning.",
                "shared_identity": "Reuse current_model and identity_registry. Edit an existing "
                "definition with its version incremented; views reference it without copying it.",
                "review": "Structure and exact evidence are enforced; prose meaning requires human "
                "review. Mark model deductions inferred, not source facts or confirmed decisions.",
            },
            "origin_rules": {
                "provided": "cite exact registered source or document evidence",
                "inferred": "model deduction; remains unreviewed",
            },
            "workflow": (
                "submit inputs; CI runs automatically; GitLab reviewer approves; service publishes"
            ),
            "model_change": {
                "trigger": "submitted model revision, not each chat message or camera movement",
                "derived_outputs": ["checked model", "rendered HTML", "agent context"],
                "failure": "return compiler diagnostics; retain the last published revision",
                "publication": "verified CI artifact after the configured GitLab review gate",
                "source_writeback": False,
                "host_chat_adapter": "not_deployed",
            },
            "html_inputs": "refused",
            "self_approval": "refused",
        }

    def knowledge(self, credential, request):
        """Exact project-scoped knowledge; reuse the existing authenticated boundary.

        This does not widen project membership or implement field-level grants.
        Source records come from the operator's pinned snapshot, not caller SQL.
        """
        self.actor(credential)
        self.audit()
        target = self.target()
        _, model, _ = self.checked(target)
        reader = Reader(model, revision=target, pointers=self.knowledge_pointers)
        if request == {"operation": "context"}:
            return reader.pack()
        allowed = {"operation", "revision", "context_digest", "id", "records", "offset",
                   "limit", "selection"}
        if (set(request) - allowed or request.get("operation") != "context_read"
                or not {"revision", "context_digest", "id"} <= request.keys()):
            raise ValueError("context_read requires revision, context_digest and canonical id")
        if request["revision"] != target or request["context_digest"] != reader.digest:
            raise Refused(
                "CONTEXT_STALE", "knowledge revision changed",
                "Refresh with operation context; do not combine model revisions", 409,
            )
        if type(request.get("records", False)) is not bool:
            raise ValueError("records must be a boolean")
        parameters = {k: request[k] for k in ("records", "offset", "limit", "selection")
                      if k in request}
        return {"revision": target, "context_digest": reader.digest,
                "result": reader.read(request["id"], **parameters)}

    def submit(self, token, body):
        self.actor(token, ("authors",))
        if (
            not isinstance(body, dict)
            or set(body) != {"operation", "model", "intent"}
            or not isinstance(body["intent"], str)
            or not 1 <= len(body["intent"].strip()) <= 255
        ):
            raise Refused(
                "INPUT_REQUIRED",
                "submit requires model YAML and an intent",
                "Use the contract; no source path, CI code or HTML can be submitted",
            )
        with self.lock:
            self.audit()
            target = self.target()
            compile_model(
                body["model"],
                self.baseline,
                self.registry(target),
                namespace=self.policy["namespace"],
            )
            author = Client(self.policy["gitlab_url"], token, allow_http=self.policy["allow_http"])
            branch = "proposal-" + uuid.uuid4().hex
            commit = author.request(
                f"/projects/{self.project}/repository/commits",
                method="POST",
                data={
                    "branch": branch,
                    "start_sha": target,
                    "commit_message": body["intent"],
                    "actions": [
                        {"action": "update", "file_path": MODEL_FILE, "content": body["model"]}
                    ],
                },
            )
            mr = author.request(
                f"/projects/{self.project}/merge_requests",
                method="POST",
                data={"source_branch": branch, "target_branch": "main", "title": body["intent"]},
            )
            return {"proposal": mr["iid"], "source_sha": commit["id"], "url": mr["web_url"]}

    def review_event(self, secret, event):
        if not hmac.compare_digest(secret, self.policy["webhook_secret"]):
            raise Refused(
                "HOOK_DENIED",
                "GitLab event could not be authenticated",
                "Use the operator-registered GitLab hook",
                403,
            )
        attributes = event.get("object_attributes", {})
        if event.get("object_kind") != "merge_request" or attributes.get("action") not in {
            "approved",
            "approval",
        }:
            return {"accepted": True, "approval_recorded": False}
        iid, sha, reviewer = (
            attributes.get("iid"),
            attributes.get("last_commit", {}).get("id"),
            event.get("user", {}).get("id"),
        )
        if (
            event.get("project", {}).get("id") != self.project
            or reviewer not in self.policy["reviewers"]
        ):
            raise Refused(
                "REVIEWER_DENIED",
                "event is not an authorised reviewer decision",
                "A registered reviewer must approve in GitLab",
                403,
            )
        with self.lock:
            mr = self.proposal(iid)
            if sha != mr["sha"] or reviewer == mr["author"]["id"] or mr["state"] != "opened":
                raise Refused(
                    "STALE_APPROVAL",
                    "approval is not for the current open proposal",
                    "Review and approve the exact current SHA",
                    409,
                )
            self.checked(sha)
            if not self.reviewer_current(reviewer):
                raise Refused(
                    "REVIEWER_DENIED",
                    "reviewer has no current project authority",
                    "Ask a current registered project reviewer to approve",
                    403,
                )
            approval = self.client.request(
                f"/projects/{self.project}/merge_requests/{iid}/approvals"
            )
            if reviewer not in {a["user"]["id"] for a in approval.get("approved_by", [])}:
                raise Refused(
                    "APPROVAL_ABSENT",
                    "GitLab does not report the reviewer approval",
                    "Wait for GitLab's authenticated approval event",
                    409,
                )
            with self.database() as database:
                database.execute(
                    "INSERT OR REPLACE INTO approvals VALUES (?,?,?,?)",
                    (iid, sha, reviewer, self.context),
                )
            return {"accepted": True, "approval_recorded": True, "source_sha": sha}

    def release(self, iid):
        with self.lock:
            mr = self.proposal(iid)
            with self.database() as database:
                old = database.execute(
                    "SELECT receipt FROM releases WHERE iid=?", (iid,)
                ).fetchone()
                evidence = database.execute(
                    "SELECT reviewer FROM approvals WHERE iid=? AND sha=? AND context=?",
                    (iid, mr["sha"], self.context),
                ).fetchall()
                prepared = database.execute(
                    "SELECT sha,context,receipt FROM prepared WHERE iid=?", (iid,)
                ).fetchone()
            if old:
                return json.loads(old[0])
            self.audit()
            if mr["state"] == "merged" and prepared:
                sha, context, encoded = prepared
                receipt = json.loads(encoded)
                merge_sha = mr.get("merge_commit_sha") or mr["sha"]
                if (
                    sha != mr["sha"]
                    or context != self.context
                    or self.document(merge_sha) != self.document(sha)
                    or hashlib.sha256((self.state / (sha + ".html")).read_bytes()).hexdigest()
                    != receipt["artifact_sha256"]
                ):
                    raise Refused(
                        "RELEASE_RECOVERY",
                        "merged revision differs from prepared release",
                        "Ask the operator to inspect the persisted merge receipt",
                        503,
                    )
                receipt["merge_sha"] = merge_sha
                with self.database() as database:
                    database.execute(
                        "INSERT INTO releases VALUES (?,?,?)", (iid, sha, json.dumps(receipt))
                    )
                return receipt
            if mr["state"] != "opened" or mr.get("draft"):
                raise Refused(
                    "PROPOSAL_NOT_READY",
                    "proposal is closed or still a draft",
                    "Review an open proposal",
                    409,
                )
            approval = self.client.request(
                f"/projects/{self.project}/merge_requests/{iid}/approvals"
            )
            active = {a["user"]["id"] for a in approval.get("approved_by", [])}
            reviewers = {e[0] for e in evidence} & active & set(self.policy["reviewers"])
            reviewers.discard(mr["author"]["id"])
            reviewers = {r for r in reviewers if self.reviewer_current(r)}
            if not reviewers:
                raise Refused(
                    "APPROVAL_REQUIRED",
                    "no authenticated approval for this exact revision",
                    "Have a registered reviewer approve in GitLab; YAML flags do not count",
                    409,
                )
            pipeline = mr.get("head_pipeline") or {}
            if pipeline.get("sha") != mr["sha"] or pipeline.get("status") != "success":
                raise Refused(
                    "PIPELINE_REQUIRED",
                    "the exact proposal has no successful pipeline",
                    "Wait for automatic CI or fix its reported error",
                    409,
                )
            jobs = self.client.pages(f"/projects/{self.project}/pipelines/{pipeline['id']}/jobs")
            if not any(
                j.get("name") == "sudograph-verify" and j.get("status") == "success" for j in jobs
            ):
                raise Refused(
                    "GATE_REQUIRED",
                    "required compiler job did not succeed",
                    "Restore the operator pipeline and rerun verification",
                    409,
                )
            target = self.target()
            # Fast-forward-only merging binds the target to this proposal's history.
            # Validate every new commit so intermediate revisions cannot corrupt IDs.
            history = self.client.pages(
                f"/projects/{self.project}/repository/commits",
                ref_name=mr["sha"],
                first_parent=True,
            )
            ids = [commit["id"] for commit in history]
            if target not in ids:
                raise Refused(
                    "TARGET_CHANGED",
                    "proposal is not based on the current target",
                    "Resubmit against current main and obtain a fresh approval",
                    409,
                )
            previous = self.registry(target)
            for sha in reversed(ids[: ids.index(target)]):
                model, previous = compile_model(
                    self.document(sha), self.baseline, previous, namespace=self.policy["namespace"]
                )
            if not ids[: ids.index(target)]:
                raise Refused("NO_CHANGE", "proposal has no new revision", "Submit a change", 409)
            html = app.render(model, language=self.policy["language"])
            artifact = self.state / (mr["sha"] + ".html")
            business.write(artifact, html.encode("utf8"))
            app.check_export(artifact, model, language=self.policy["language"])
            fresh = self.proposal(iid)
            if fresh["sha"] != mr["sha"] or self.target() != target:
                raise Refused(
                    "STALE_PROPOSAL",
                    "proposal changed during compilation",
                    "Review and approve the new revision",
                    409,
                )
            active = self.client.request(f"/projects/{self.project}/merge_requests/{iid}/approvals")
            reviewers &= {a["user"]["id"] for a in active.get("approved_by", [])}
            reviewers = {r for r in reviewers if self.reviewer_current(r)}
            if not reviewers:
                raise Refused(
                    "APPROVAL_REQUIRED",
                    "reviewer approval was withdrawn during compilation",
                    "Ask a registered reviewer to review the revision again",
                    409,
                )
            receipt = {
                "format": "sudograph-release/v1",
                "proposal": iid,
                "source_sha": mr["sha"],
                "merge_sha": None,
                "project": self.project,
                "pipeline": pipeline["id"],
                "reviewers": sorted(reviewers),
                "baseline": self.pin,
                "compiler_sha256": self.compiler,
                "model_sha256": business.digest(model),
                "artifact_sha256": hashlib.sha256(html.encode("utf8")).hexdigest(),
                "business_confirmation": "not inferred from merge approval",
            }
            # Durable preparation precedes the remote merge. If its response is
            # lost or the process restarts, recover only these exact verified bytes.
            with self.database() as database:
                database.execute(
                    "INSERT OR REPLACE INTO prepared VALUES (?,?,?,?)",
                    (iid, mr["sha"], self.context, json.dumps(receipt)),
                )
            merged = self.client.request(
                f"/projects/{self.project}/merge_requests/{iid}/merge",
                method="PUT",
                data={"sha": mr["sha"], "squash": False},
            )
            if merged.get("state") != "merged":
                raise Refused(
                    "MERGE_PENDING",
                    "GitLab has not completed the guarded merge",
                    "Wait for the exact revision to merge",
                    409,
                )
            merge_sha = merged.get("merge_commit_sha") or merged["sha"]
            if self.document(merge_sha) != self.document(mr["sha"]):
                raise Refused(
                    "MERGE_CONTENT",
                    "merged model differs from approved inputs",
                    "Ask the operator to inspect the merge",
                    503,
                )
            receipt["merge_sha"] = merge_sha
            with self.database() as database:
                database.execute(
                    "INSERT INTO releases VALUES (?,?,?)", (iid, mr["sha"], json.dumps(receipt))
                )
            return receipt

    def poll(self, stopped):
        last = {}
        while not stopped.wait(1):
            try:
                with self.database() as database:
                    pending = database.execute(
                        "SELECT DISTINCT iid FROM approvals WHERE iid NOT IN "
                        "(SELECT iid FROM releases)"
                    ).fetchall()
                for (iid,) in pending:
                    try:
                        receipt = self.release(iid)
                        print(
                            json.dumps({"published": iid, "sha": receipt["source_sha"]}), flush=True
                        )
                    except (Refused, GitLabError, ValueError) as exc:
                        code = getattr(exc, "code", type(exc).__name__)
                        if last.get(iid) != code:
                            last[iid] = code
                            print(json.dumps({"proposal": iid, "pending": code}), flush=True)
            except (sqlite3.Error, GitLabError):
                pass


def handler(publisher):
    class Handler(BaseHTTPRequestHandler):
        def credential(self):
            value = self.headers.get("Authorization", "")
            return value[7:] if value.startswith("Bearer ") else ""

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 2 * 1024 * 1024:
                    raise ValueError("request must be 1..2 MiB")
                body = json.loads(self.rfile.read(size))
                if self.path == "/hooks/gitlab":
                    result = publisher.review_event(self.headers.get("X-Gitlab-Token", ""), body)
                elif self.path == "/v1":
                    publisher.actor(self.credential())
                    if body == {"operation": "contract"}:
                        result = publisher.contract()
                    elif body.get("operation") in {"context", "context_read"}:
                        result = publisher.knowledge(self.credential(), body)
                    elif body.get("operation") == "submit":
                        result = publisher.submit(self.credential(), body)
                    elif set(body) == {"operation", "proposal"} and body["operation"] == "status":
                        with publisher.database() as database:
                            row = database.execute(
                                "SELECT receipt FROM releases WHERE iid=?", (body["proposal"],)
                            ).fetchone()
                        mr = publisher.proposal(body["proposal"])
                        with publisher.database() as database:
                            bound = database.execute(
                                "SELECT 1 FROM approvals WHERE iid=? AND sha=? AND context=?",
                                (body["proposal"], mr["sha"], publisher.context),
                            ).fetchone()
                        result = {
                            "state": mr["state"],
                            "sha": mr["sha"],
                            "pipeline": (mr.get("head_pipeline") or {}).get("status"),
                            "release": json.loads(row[0]) if row else None,
                            "approval_for_current_sha": bool(bound),
                        }
                    else:
                        raise ValueError(
                            "use contract, submit or status; HTML/policy inputs are refused"
                        )
                else:
                    self.send_error(404)
                    return
                self.reply(200, {"result": result})
            except SelectionError as exc:
                self.reply(404 if exc.code == "SUBGRAPH_NOT_FOUND" else 400, exc.as_dict())
            except Refused as exc:
                self.reply(
                    exc.status, {"error": exc.code, "reason": exc.reason, "recovery": exc.recovery}
                )
            except (GitLabError, ValueError, KeyError, TypeError) as exc:
                self.reply(
                    400,
                    {
                        "error": "REQUEST_REFUSED",
                        "reason": str(exc),
                        "recovery": "Read the contract and repair checked inputs",
                    },
                )
            except Exception:
                self.reply(
                    503,
                    {
                        "error": "SERVICE_UNAVAILABLE",
                        "recovery": "Ask the operator to check deployment",
                    },
                )

        def do_GET(self):
            if self.path == "/health":
                self.reply(200, {"ready": True})
                return
            try:
                publisher.actor(self.credential())
                match = re.fullmatch(r"/releases/([0-9a-f]{40})\.html", self.path)
                if not match:
                    self.send_error(404)
                    return
                with publisher.database() as database:
                    release = database.execute(
                        "SELECT receipt FROM releases WHERE sha=?", (match[1],)
                    ).fetchone()
                if not release:
                    self.send_error(404)
                    return
                payload = (publisher.state / (match[1] + ".html")).read_bytes()
                if hashlib.sha256(payload).hexdigest() != json.loads(release[0])["artifact_sha256"]:
                    raise Refused(
                        "ARTIFACT_CHANGED",
                        "published bytes no longer match their receipt",
                        "Restore the verified artifact through the operator",
                        503,
                    )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
            except (Refused, GitLabError) as exc:
                self.reply(
                    getattr(exc, "status", None) or 403,
                    {"error": getattr(exc, "code", "ACTOR_DENIED")},
                )
            except (OSError, sqlite3.Error, ValueError):
                self.reply(503, {"error": "SERVICE_UNAVAILABLE"})

        def reply(self, status, result):
            payload = json.dumps(result, ensure_ascii=False).encode("utf8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--wait-config", action="store_true")
    args = parser.parse_args()
    while args.wait_config and not Path(args.policy).exists():
        time.sleep(1)
    publisher = Publisher(json.loads(Path(args.policy).read_text(encoding="utf8")))
    stopped = threading.Event()
    worker = threading.Thread(target=publisher.poll, args=(stopped,), daemon=True)
    worker.start()
    server = ThreadingHTTPServer((args.bind, args.port), handler(publisher))
    try:
        server.serve_forever()
    finally:
        stopped.set()
        server.server_close()


if __name__ == "__main__":
    main()
