"""Provision a private model project and operator-owned CI in an existing GitLab.

Only the deployment owner runs this command. Authors use the managed interface;
GitLab hooks and the publisher perform verification and publication automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from pathlib import Path

from compiler import business
from compiler.gitlab import Client
from compiler.managed import MODEL_FILE, SOURCE_REQUEST, compile_model

ROOT = Path(__file__).resolve().parent.parent


def protect_main(client, project):
    """Install protection before the first commit can trigger GitLab defaults."""
    path = f"/projects/{project['id']}/protected_branches"
    client.request(
        path,
        method="POST",
        data={
            "name": "main",
            "push_access_level": 0,
            "merge_access_level": 40,
            "allow_force_push": False,
        },
    )
    checked = client.request(path + "/main")
    if (
        checked.get("allow_force_push") is not False
        or [row.get("access_level") for row in checked.get("push_access_levels", [])] != [0]
        or [row.get("access_level") for row in checked.get("merge_access_levels", [])] != [40]
    ):
        raise ValueError("GitLab did not install the required main-branch protection")


def provision(client, *, config, baseline):
    allowed = {
        "pipeline_name",
        "model_name",
        "publisher_id",
        "publisher_token",
        "authors",
        "reviewers",
        "worker_gitlab_url",
        "allow_http",
        "image",
        "language",
        "webhook_url",
    }
    if set(config) != allowed or config["language"] not in ("en", "zh"):
        raise ValueError("register the complete deployment configuration")
    people = [*config["authors"], *config["reviewers"], config["publisher_id"]]
    if (
        not config["authors"]
        or not config["reviewers"]
        or any(type(i) is not int or i < 1 for i in people)
        or set(config["authors"]) & set(config["reviewers"])
        or config["publisher_id"] in [*config["authors"], *config["reviewers"]]
    ):
        raise ValueError("author, reviewer and publisher must be separate registered identities")
    pin = {"manifest": "registered-source-baseline", "sha256": business.digest(baseline)}
    compile_model(json.dumps({"format": SOURCE_REQUEST, "baseline": pin}), baseline)
    publisher = Client(
        client.url, config["publisher_token"], allow_http=config["allow_http"]
    ).actor()
    if publisher["id"] != config["publisher_id"]:
        raise ValueError("publisher credential does not match its registered identity")
    owner = client.actor()
    names = [config["pipeline_name"], config["model_name"]]
    projects = [
        client.request(
            "/projects",
            method="POST",
            data={
                "name": name,
                "path": name,
                "visibility": "private",
                "initialize_with_readme": False,
                "shared_runners_enabled": False,
            },
        )
        for name in names
    ]
    infrastructure, model = projects
    # Empty repositories can have protected branch names. Install the rules
    # before GitLab's first-push worker or a registered author can write main.
    for project in projects:
        protect_main(client, project)
    pipeline = (
        (ROOT / "infra/gitlab/pipeline.yml")
        .read_text(encoding="utf8")
        .replace("__WORKER_IMAGE__", config["image"])
    )
    client.request(
        f"/projects/{infrastructure['id']}/repository/commits",
        method="POST",
        data={
            "branch": "main",
            "commit_message": "Install the operator-owned Sudograph pipeline",
            "actions": [{"action": "create", "file_path": "pipeline.yml", "content": pipeline}],
        },
    )
    path = f"pipeline.yml@{infrastructure['path_with_namespace']}"
    client.request(
        f"/projects/{model['id']}",
        method="PUT",
        data={
            "ci_config_path": path,
            "only_allow_merge_if_pipeline_succeeds": True,
            "allow_merge_on_skipped_pipeline": False,
            "merge_method": "ff",
        },
    )
    for project in projects:
        for user in [*config["authors"], *config["reviewers"]]:
            client.request(
                f"/projects/{project['id']}/members",
                method="POST",
                data={"user_id": user, "access_level": 30 if project == model else 20},
            )
        if owner["id"] != config["publisher_id"]:
            client.request(
                f"/projects/{project['id']}/members",
                method="POST",
                data={"user_id": config["publisher_id"], "access_level": 40},
            )
    pin = {"manifest": "registered-source-baseline", "sha256": business.digest(baseline)}
    seed = client.request(
        f"/projects/{model['id']}/repository/commits",
        method="POST",
        data={
            "branch": "main",
            "commit_message": "Register the read-only source projection",
            "actions": [
                {
                    "action": "create",
                    "file_path": MODEL_FILE,
                    "content": json.dumps({"format": SOURCE_REQUEST, "baseline": pin}),
                }
            ],
        },
    )
    webhook_secret = secrets.token_urlsafe(48)
    client.request(
        f"/projects/{model['id']}/hooks",
        method="POST",
        data={
            "url": config["webhook_url"],
            "token": webhook_secret,
            "merge_requests_events": True,
            "enable_ssl_verification": not config["allow_http"],
        },
    )
    runner = client.request(
        "/user/runners",
        method="POST",
        data={
            "runner_type": "project_type",
            "project_id": model["id"],
            "description": "Sudograph managed compiler",
            "tag_list": ["sudograph"],
            "run_untagged": False,
            "locked": True,
        },
    )
    policy = {
        "gitlab_url": config["worker_gitlab_url"],
        "allow_http": config["allow_http"],
        "token": config["publisher_token"],
        "webhook_secret": webhook_secret,
        "project_id": model["id"],
        "pipeline_project_id": infrastructure["id"],
        "ci_config_path": path,
        "ci_config_sha256": hashlib.sha256(pipeline.encode()).hexdigest(),
        "baseline_file": "/trusted/baseline.json",
        "state_dir": "/state",
        "authors": config["authors"],
        "reviewers": config["reviewers"],
        "language": config["language"],
        "bootstrap_sha": seed["id"],
        "namespace": config["model_name"],
    }
    worker = {
        key: policy[key]
        for key in (
            "gitlab_url",
            "allow_http",
            "project_id",
            "language",
            "namespace",
            "bootstrap_sha",
        )
    }
    toml = f"""concurrent = 1
check_interval = 1
[[runners]]
  name = "sudograph"
  url = {json.dumps(config["worker_gitlab_url"])}
  token = {json.dumps(runner["token"])}
  clone_url = {json.dumps(config["worker_gitlab_url"])}
  executor = "docker"
  [runners.docker]
    image = {json.dumps(config["image"])}
    network_mode = "sudograph-gitlab"
    pull_policy = "if-not-present"
    volumes = ["/cache", "sudograph-gitlab-trusted:/trusted:ro"]
"""
    return {
        "policy": policy,
        "worker": worker,
        "runner": toml,
        "project": model,
        "pipeline_project": infrastructure,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_configuration", help="operator credential and deployment fields")
    parser.add_argument("--baseline", required=True, help="operator-checked phase-one model JSON")
    parser.add_argument("--output", required=True, help="new private deployment directory")
    args = parser.parse_args()
    config = json.loads(Path(args.private_configuration).read_text(encoding="utf8"))
    operator = config.pop("operator")
    folder = Path(args.output).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if any(folder.iterdir()):
        raise ValueError("deployment output must be empty; existing identities are not re-created")
    client = Client(operator["url"], operator["token"], allow_http=config["allow_http"])
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf8"))
    prepared = provision(client, config=config, baseline=baseline)
    for name, value in [
        ("baseline.json", baseline),
        ("policy.json", prepared["policy"]),
        ("worker.json", prepared["worker"]),
    ]:
        (folder / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf8")
    (folder / "runner.toml").write_text(prepared["runner"], encoding="utf8")
    print(
        json.dumps(
            {
                "project": prepared["project"]["web_url"],
                "pipeline_project": prepared["pipeline_project"]["web_url"],
            }
        )
    )


if __name__ == "__main__":
    main()
