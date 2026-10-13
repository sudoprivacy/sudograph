"""Provision a private model project and operator-owned CI in an existing GitLab.

Only the deployment owner runs this command. Authors use the managed interface;
GitLab hooks and the publisher perform verification and publication automatically.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

from compiler import business
from compiler.gitlab import GitLabError
from compiler.managed import MODEL_FILE, SOURCE_REQUEST

ROOT = Path(__file__).resolve().parent.parent


def provision(client, *, config, baseline):
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
    # GitLab protects an initial default branch; replace that default explicitly.
    for project in projects:
        try:
            client.request(f"/projects/{project['id']}/protected_branches/main", method="DELETE")
        except GitLabError as exc:
            if exc.status != 404:
                raise
        client.request(
            f"/projects/{project['id']}/protected_branches",
            method="POST",
            data={
                "name": "main",
                "push_access_level": 0,
                "merge_access_level": 40,
                "allow_force_push": False,
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
