"""Publisher authority, revision binding and crash recovery on unrelated data."""

import copy
import hashlib
import json

import pytest
import yaml

from compiler import business, managed
from compiler.gitlab import Client, GitLabError
from tools.gitlab_stack import fixture_baseline
from tools.provision_gitlab import protect_main, provision

SEED, FIRST, SECOND = "a" * 40, "b" * 40, "c" * 40


def overlay(baseline, *, version=1, statement="Should refunds reduce ticket amounts?"):
    obj = next(
        o for o in baseline["source_schema"]["sources"][0]["objects"] if o["name"] == "Tickets"
    )
    return {
        "format": business.FORMAT,
        "namespace": "tickets",
        "baseline": {"manifest": "registered-source-baseline", "sha256": business.digest(baseline)},
        "definitions": {
            "refund": {
                "concept": "refund policy",
                "category": "meaning",
                "role": "business",
                "purpose": {
                    "stakeholder": "Support manager",
                    "decision": "Choose how refunds affect ticket spend.",
                },
                "label": "Refund policy",
                "statement": statement,
                "origin": "inferred",
                "contributor": "model",
                "version": version,
                "targets": [obj["id"]],
            }
        },
        "views": {"meaning": {"label": "Business meaning", "definitions": ["refund"]}},
    }


class GitLabFixture:
    """Protocol fake for unit boundaries; real deployment is checked separately."""

    def __init__(self, baseline):
        self.content = {
            SEED: json.dumps(
                {"format": managed.SOURCE_REQUEST, "baseline": overlay(baseline)["baseline"]}
            ),
            FIRST: yaml.safe_dump(overlay(baseline)),
        }
        self.head = SEED
        self.mr_value = {
            "iid": 1,
            "source_project_id": 1,
            "target_project_id": 1,
            "target_branch": "main",
            "author": {"id": 10},
            "sha": FIRST,
            "state": "opened",
            "draft": False,
            "head_pipeline": {"id": 30, "sha": FIRST, "status": "success"},
        }
        self.approved = [20]
        self.lose_merge_response = False
        self.merge_count = 0
        self.extra_file = False
        self.membership = 30
        self.reviewer_member = True

    def actor(self):
        return {"id": 10, "state": "active"}

    def request(self, path, *, method="GET", data=None, params=None):
        if path == "/projects/1":
            return {
                "visibility": "private",
                "ci_config_path": "pipeline.yml@operator/checks",
                "only_allow_merge_if_pipeline_succeeds": True,
                "allow_merge_on_skipped_pipeline": False,
                "merge_method": "ff",
                "permissions": {"project_access": {"access_level": self.membership}},
            }
        if path.endswith("/protected_branches/main"):
            return {
                "allow_force_push": False,
                "push_access_levels": [{"access_level": 0}],
                "merge_access_levels": [{"access_level": 40}],
            }
        if path.endswith("/repository/branches/main"):
            return {"commit": {"id": self.head}}
        if "/members/all/" in path:
            return {"access_level": 30 if self.reviewer_member else 0, "state": "active"}
        if path.endswith("/approvals"):
            return {"approved_by": [{"user": {"id": i}} for i in self.approved]}
        if path.endswith("/merge") and method == "PUT":
            assert data["sha"] == self.mr_value["sha"]
            self.merge_count += 1
            self.head = self.mr_value["sha"]
            self.mr_value.update(state="merged", merge_commit_sha=self.head)
            if self.lose_merge_response:
                raise GitLabError("remote response lost")
            return copy.deepcopy(self.mr_value)
        raise AssertionError(path)

    def file(self, project, name, ref):
        return "operator-owned pipeline" if project == 2 else self.content[ref]

    def pages(self, path, **params):
        if path.endswith("/tree"):
            result = [{"path": managed.MODEL_FILE, "mode": "100644"}]
            return result + ([{"path": "review.html", "mode": "100644"}] if self.extra_file else [])
        if path.endswith("/commits"):
            sha = params["ref_name"]
            ids = [SEED] if sha == SEED else [sha, SEED]
            return [{"id": i} for i in ids]
        if path.endswith("/jobs"):
            return [{"name": "sudograph-verify", "status": "success"}]
        raise AssertionError(path)

    def mr(self, project, iid):
        assert project == 1 and iid == 1
        return copy.deepcopy(self.mr_value)


@pytest.fixture
def installed(tmp_path, monkeypatch):
    baseline = fixture_baseline(tmp_path)
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf8")
    fake = GitLabFixture(baseline)
    monkeypatch.setattr(managed, "Client", lambda *args, **kwargs: fake)
    policy = {
        "gitlab_url": "https://gitlab.example",
        "allow_http": False,
        "token": "publisher",
        "webhook_secret": "s" * 48,
        "project_id": 1,
        "pipeline_project_id": 2,
        "ci_config_path": "pipeline.yml@operator/checks",
        "ci_config_sha256": hashlib.sha256(b"operator-owned pipeline").hexdigest(),
        "baseline_file": str(path),
        "state_dir": str(tmp_path / "state"),
        "authors": [10],
        "reviewers": [20],
        "language": "en",
        "bootstrap_sha": SEED,
        "namespace": "tickets",
    }
    return managed.Publisher(policy), fake, baseline


def approve(publisher, *, sha=FIRST, reviewer=20, secret=None):
    return publisher.review_event(
        secret or publisher.policy["webhook_secret"],
        {
            "object_kind": "merge_request",
            "project": {"id": 1},
            "user": {"id": reviewer},
            "object_attributes": {"iid": 1, "action": "approved", "last_commit": {"id": sha}},
        },
    )


def test_managed_contract_and_write_path_enforce_business_purpose(installed):
    publisher, _, baseline = installed
    contract = publisher.contract()
    assert contract["business_format"] == "sudograph-business-overlay/v4"
    assert "role" in contract["definition_required"]
    assert "stakeholder" in contract["definition_roles"]["business"]
    doc = overlay(baseline)
    del doc["definitions"]["refund"]["purpose"]
    with pytest.raises(ValueError, match="purpose"):
        managed.compile_model(yaml.safe_dump(doc), baseline, namespace="tickets")
    doc["format"] = "sudograph-business-overlay/v3"
    with pytest.raises(ValueError, match="use format"):
        managed.compile_model(yaml.safe_dump(doc), baseline, namespace="tickets")


def test_managed_source_review_requires_a_plan_and_is_separate_from_business(installed):
    publisher, _, baseline = installed
    contract = publisher.contract()
    assert "verification" in contract["definition_roles"]["source_review"]
    assert set(contract["authoring_guidance"]) == {
        "phase_one", "phase_two", "shared_identity", "review",
    }
    doc = overlay(baseline)
    question = doc["definitions"]["refund"]
    question.update(role="source_review", category="issue", statement="Are empty amounts expected?")
    question.pop("purpose")
    doc["views"] = {}
    with pytest.raises(ValueError, match="verification"):
        managed.compile_model(yaml.safe_dump(doc), baseline, namespace="tickets")
    question["verification"] = "Count source NULL amounts and inspect the affected ticket rows."
    model, registry = managed.compile_model(yaml.safe_dump(doc), baseline, namespace="tickets")
    assert model["business"]["views"] == {}
    assert model["business"]["source_review"]["definitions"] == list(registry["definitions"])
    assert model["source_schema"] == baseline["source_schema"]


def test_old_accepted_history_keeps_ids_and_versions_without_allowing_old_submissions(installed):
    publisher, fake, baseline = installed
    old = overlay(baseline)
    old["format"] = "sudograph-business-overlay/v3"
    for item in old["definitions"].values():
        del item["role"]
        del item["purpose"]
    fake.content[FIRST] = yaml.safe_dump(old)
    fake.head = FIRST
    previous = publisher.registry(FIRST)
    assert len(previous["definitions"]) == 1
    identity = next(iter(previous["definitions"]))
    assert previous["definitions"][identity]["version"] == 1
    contract = publisher.contract()
    assert contract["identity_registry"] == previous
    assert contract["business_format"] == business.FORMAT
    with pytest.raises(ValueError, match="use format"):
        managed.compile_model(fake.content[FIRST], baseline, previous, namespace="tickets")
    upgraded = overlay(baseline)
    with pytest.raises(ValueError, match="new version"):
        managed.compile_model(yaml.safe_dump(upgraded), baseline, previous, namespace="tickets")
    upgraded["definitions"]["refund"]["version"] = 2
    model, registry = managed.compile_model(
        yaml.safe_dump(upgraded), baseline, previous, namespace="tickets"
    )
    assert set(model["business"]["definitions"]) == {identity}
    assert registry["definitions"][identity]["version"] == 2


def test_source_namespace_and_versions_are_checked_without_caller_commands(installed):
    publisher, _, baseline = installed
    doc = overlay(baseline)
    first, registry = managed.compile_model(yaml.safe_dump(doc), baseline, namespace="tickets")
    assert first["source_schema"] == baseline["source_schema"]
    doc["definitions"]["refund"]["statement"] = "A changed meaning"
    with pytest.raises(ValueError, match="new version"):
        managed.compile_model(yaml.safe_dump(doc), baseline, registry, namespace="tickets")
    doc["definitions"]["refund"]["version"] = 2
    second, _ = managed.compile_model(yaml.safe_dump(doc), baseline, registry, namespace="tickets")
    assert set(first["business"]["definitions"]) == set(second["business"]["definitions"])
    doc["namespace"] = "another-copy"
    with pytest.raises(managed.Refused, match="namespace"):
        managed.compile_model(yaml.safe_dump(doc), baseline, namespace="tickets")
    pin = publisher.pin
    with pytest.raises(managed.Refused, match="phase one"):
        managed.compile_model(
            json.dumps({"format": managed.SOURCE_REQUEST, "baseline": pin, "definitions": {}}),
            baseline,
        )


def test_false_or_stale_or_self_approval_cannot_publish(installed):
    publisher, fake, _ = installed
    with pytest.raises(managed.Refused, match="no authenticated approval"):
        publisher.release(1)
    with pytest.raises(managed.Refused, match="could not be authenticated"):
        approve(publisher, secret="forged")
    with pytest.raises(managed.Refused, match="authorised reviewer"):
        approve(publisher, reviewer=10)
    approve(publisher)
    fake.mr_value["sha"] = SECOND
    with pytest.raises(managed.Refused, match="no authenticated approval"):
        publisher.release(1)
    with pytest.raises(managed.Refused, match="current open proposal"):
        approve(publisher)
    assert fake.merge_count == 0


def test_withdrawn_approval_and_skipped_ci_are_not_authority(installed):
    publisher, fake, _ = installed
    approve(publisher)
    fake.approved = []
    with pytest.raises(managed.Refused, match="no authenticated approval"):
        publisher.release(1)
    fake.approved = [20]
    fake.mr_value["head_pipeline"]["status"] = "skipped"
    with pytest.raises(managed.Refused, match="successful pipeline"):
        publisher.release(1)
    fake.mr_value["head_pipeline"]["status"] = "success"
    fake.extra_file = True
    with pytest.raises(managed.Refused, match="unregistered files"):
        publisher.release(1)
    assert fake.merge_count == 0


def test_lost_merge_response_recovers_exact_prepared_release(installed):
    publisher, fake, baseline = installed
    approve(publisher)
    fake.lose_merge_response = True
    with pytest.raises(GitLabError, match="response lost"):
        publisher.release(1)
    restarted = managed.Publisher(publisher.policy)
    receipt = restarted.release(1)
    assert receipt["source_sha"] == FIRST == receipt["merge_sha"]
    assert receipt["baseline"]["sha256"] == business.digest(baseline)
    assert receipt["business_confirmation"] == "not inferred from merge approval"
    assert fake.merge_count == 1
    assert restarted.release(1) == receipt


def test_changed_prepared_artifact_is_not_recovered(installed):
    publisher, fake, _ = installed
    approve(publisher)
    fake.lose_merge_response = True
    with pytest.raises(GitLabError):
        publisher.release(1)
    (publisher.state / (FIRST + ".html")).write_text("edited HTML", encoding="utf8")
    with pytest.raises(managed.Refused, match="differs from prepared release"):
        managed.Publisher(publisher.policy).release(1)


def test_gitlab_credentials_require_a_canonical_trusted_url():
    for url in [
        "http://gitlab.example",
        "https://token@gitlab.example",
        "https://gitlab.example?token=secret",
        "file:///tmp/gitlab",
    ]:
        with pytest.raises(GitLabError):
            Client(url, "credential")
    with pytest.raises(GitLabError, match="credential"):
        Client("https://gitlab.example", "credential\r\nInjected: true")


def test_registered_identity_cannot_outlive_its_gitlab_membership(installed):
    publisher, fake, _ = installed
    assert publisher.actor("author")["id"] == 10
    fake.membership = 0
    with pytest.raises(managed.Refused) as error:
        publisher.actor("author")
    assert error.value.code == "ACTOR_DENIED"


def test_native_approval_does_not_outlive_reviewer_membership(installed):
    publisher, fake, _ = installed
    approve(publisher)
    fake.reviewer_member = False
    with pytest.raises(managed.Refused, match="no authenticated approval"):
        publisher.release(1)
    assert fake.merge_count == 0


def test_provision_protects_empty_projects_before_first_push_or_membership(installed, monkeypatch):
    _, _, baseline = installed

    class FirstPushDefaults:
        url = "https://gitlab.example"

        def __init__(self):
            self.protected = {}
            self.projects = 0
            self.defaults_created = 0

        def actor(self):
            return {"id": 1}

        def request(self, path, *, method="GET", data=None):
            if path == "/projects":
                self.projects += 1
                return {"id": self.projects, "path_with_namespace": "owner/" + data["name"]}
            if path == "/user/runners":
                return {"token": "synthetic-runner"}
            project = int(path.split("/")[2])
            if path.endswith("/protected_branches"):
                if project in self.protected:
                    raise GitLabError("default protection already exists", status=409)
                self.protected[project] = {
                    "allow_force_push": data["allow_force_push"],
                    "push_access_levels": [{"access_level": data["push_access_level"]}],
                    "merge_access_levels": [{"access_level": data["merge_access_level"]}],
                }
                return self.protected[project]
            if path.endswith("/protected_branches/main"):
                assert method == "GET", "initial protection must never be removed"
                return self.protected[project]
            if path.endswith("/repository/commits"):
                if project not in self.protected:
                    self.defaults_created += 1
                    self.protected[project] = {"push_access_levels": [{"access_level": 30}]}
                return {"id": SEED}
            if path.endswith("/members"):
                assert self.protected[project]["push_access_levels"] == [{"access_level": 0}]
                return {}
            if path.endswith("/hooks") or path == f"/projects/{project}":
                return {}
            raise AssertionError(path)

    class PublisherIdentity:
        def actor(self):
            return {"id": 40}

    monkeypatch.setattr(
        "tools.provision_gitlab.Client", lambda *args, **kwargs: PublisherIdentity()
    )
    client = FirstPushDefaults()
    provision(
        client,
        config={
            "pipeline_name": "checks", "model_name": "tickets", "publisher_id": 40,
            "publisher_token": "synthetic", "authors": [10], "reviewers": [20],
            "worker_gitlab_url": "https://gitlab.example", "allow_http": False,
            "image": "operator-compiler", "language": "en",
            "webhook_url": "https://publisher.example/hooks/gitlab",
        },
        baseline=baseline,
    )
    assert client.defaults_created == 0
    assert len(client.protected) == 2


def test_provision_refuses_a_protection_response_that_still_allows_pushes():
    class PermissiveProtection:
        def request(self, path, *, method="GET", data=None):
            return {
                "allow_force_push": False,
                "push_access_levels": [{"access_level": 0}, {"access_level": 30}],
                "merge_access_levels": [{"access_level": 40}],
            }

    with pytest.raises(ValueError, match="required main-branch protection"):
        protect_main(PermissiveProtection(), {"id": 1})
