"""Start and provision an isolated, complete GitLab/runner/publisher deployment.

Credentials stay in the operator's private directory. The acceptance profile
creates synthetic author/reviewer accounts; it never impersonates a customer.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sqlite3
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import yaml

from compiler import app, project, spec
from compiler.gitlab import Client
from tools.provision_gitlab import provision

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "infra/gitlab/compose.yaml"


def command(args, *, data=None, timeout=900):
    deadline = time.monotonic() + timeout
    with subprocess.Popen(
        args, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ) as process:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.communicate()
                raise RuntimeError("deployment command exceeded its deadline: " + args[0])
            try:
                output, _ = process.communicate(input=data, timeout=min(30, remaining))
                break
            except subprocess.TimeoutExpired:
                data = None
                print("Waiting for deployment command: " + " ".join(args[:2]), flush=True)
        if process.returncode:
            for line in output.decode("utf8", errors="replace").splitlines():
                if line.startswith("SUDOGRAPH_BOOTSTRAP_ERROR="):
                    print(line, flush=True)
            # Bootstrap stdout may contain a credential; never echo it on failure.
            raise RuntimeError(f"deployment command failed (exit {process.returncode}): {args[:3]}")
        return output


def wait_for(url, *, timeout=900):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError, OSError):
            pass
        time.sleep(2)
    raise RuntimeError("deployed service did not become ready before its deadline")


def fixture_baseline(folder):
    database = folder / "source.db"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE Tickets(id INTEGER PRIMARY KEY, amount REAL);
            INSERT INTO Tickets VALUES (1,7),(2,NULL);
            CREATE VIEW Totals AS SELECT SUM(amount) total FROM Tickets;
        """)
    source = folder / "source.yaml"
    source.write_text(
        yaml.safe_dump(project.draft("sqlite:///" + database.as_posix())), encoding="utf8"
    )
    return app.bundle(spec.load(str(source)), records=True)


BOOTSTRAP = """require 'securerandom'
begin
$sudograph_step = 'local isolated hook configuration'
ApplicationSetting.current.update!(allow_local_requests_from_web_hooks_and_services: true)
root = User.find_by!(username: 'root')
def credential(user)
  $sudograph_step = 'credential allocation'
  token = user.personal_access_tokens.create!(
    name: 'sudograph-isolated-acceptance', scopes: ['api'], expires_at: Date.today + 7)
  token.set_token(SecureRandom.hex(32)); token.save!
  {id: user.id, token: token.token}
end
actors = {}
['author', 'reviewer', 'publisher'].each do |role|
  $sudograph_step = 'synthetic ' + role + ' creation'
  user = User.new(username: "sudograph-#{role}", name: "Sudograph acceptance #{role}",
    email: "#{role}@acceptance.invalid", password: SecureRandom.base64(48))
  user.skip_confirmation!; user.save!
  actors[role] = credential(user)
end
actors['operator'] = credential(root)
puts 'SUDOGRAPH_BOOTSTRAP=' + actors.to_json
rescue ActiveRecord::RecordInvalid => error
  puts 'SUDOGRAPH_BOOTSTRAP_ERROR=' + {
    code: error.class.name, step: $sudograph_step, record: error.record.class.name,
    fields: error.record.errors.attribute_names
  }.to_json
  exit 1
rescue NoMethodError => error
  puts 'SUDOGRAPH_BOOTSTRAP_ERROR=' + {
    code: error.class.name, step: $sudograph_step, method: error.name.to_s
  }.to_json
  exit 1
rescue => error
  puts 'SUDOGRAPH_BOOTSTRAP_ERROR=' + {
    code: error.class.name, step: $sudograph_step
  }.to_json
  exit 1
end
"""


def deploy(folder, *, baseline=None):
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    password = folder / "root-password.txt"
    reused = (folder / "deployment.json").exists()
    if reused:
        registered = json.loads((folder / "baseline.json").read_text(encoding="utf8"))
        if baseline is not None and baseline != registered:
            raise RuntimeError("new source baseline requires a separate reviewed registration")
    elif (folder / "actors.json").exists() or password.exists():
        raise RuntimeError("partial deployment retained; inspect it before resuming bootstrap")
    else:
        password.write_text(secrets.token_urlsafe(48), encoding="utf8")
    os.environ["SUDOGRAPH_ROOT_PASSWORD_FILE"] = str(password)
    compose = ["docker", "compose", "-f", str(COMPOSE)]
    command([*compose, "up", "-d", "--build"])
    if reused:
        wait_for("http://127.0.0.1:8788/health", timeout=120)
        return {
            **json.loads((folder / "deployment.json").read_text(encoding="utf8")),
            "actors": json.loads((folder / "actors.json").read_text(encoding="utf8")),
            "baseline": registered,
            "policy": json.loads((folder / "policy.json").read_text(encoding="utf8")),
        }
    print("Waiting for the isolated GitLab service", flush=True)
    # A host-side Docker request is not container localhost. Monitoring probes
    # have a loopback IP allowlist; the public sign-in page exercises Rails
    # without weakening that allowlist.
    wait_for("http://127.0.0.1:8088/users/sign_in")
    output = command(
        [*compose, "exec", "-T", "gitlab", "gitlab-rails", "runner", "-"], data=BOOTSTRAP.encode()
    )
    lines = output.decode("utf8").splitlines()
    actors = json.loads(
        next(line.split("=", 1)[1] for line in lines if line.startswith("SUDOGRAPH_BOOTSTRAP="))
    )
    (folder / "actors.json").write_text(json.dumps(actors), encoding="utf8")
    client = Client("http://127.0.0.1:8088", actors["operator"]["token"], allow_http=True)
    baseline = baseline or fixture_baseline(folder)
    config = {
        "pipeline_name": "sudograph-pipeline",
        "model_name": "sudograph-model",
        "publisher_id": actors["publisher"]["id"],
        "publisher_token": actors["publisher"]["token"],
        "authors": [actors["author"]["id"]],
        "reviewers": [actors["reviewer"]["id"]],
        "worker_gitlab_url": "http://gitlab:8088",
        "allow_http": True,
        "image": "sudograph-managed:gitlab",
        "language": "en",
        "webhook_url": "http://publisher:8765/hooks/gitlab",
    }
    prepared = provision(client, config=config, baseline=baseline)
    for name, value in [
        ("baseline.json", baseline),
        ("worker.json", prepared["worker"]),
        ("policy.json", prepared["policy"]),
    ]:
        path = folder / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf8")
        destination = "/state/policy.json" if name == "policy.json" else "/trusted/" + name
        # The publisher's trusted volume is read-only at runtime. Copy through a
        # separate operator-owned container; no job receives this Docker socket.
        if name == "policy.json":
            command([*compose, "cp", str(path), "publisher:/state/policy.pending"])
            command(
                [
                    *compose,
                    "exec",
                    "-T",
                    "publisher",
                    "python",
                    "-c",
                    "from pathlib import Path;"
                    "Path('/state/policy.pending').replace('/state/policy.json')",
                ]
            )
        else:
            command(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-i",
                    "-v",
                    "sudograph-gitlab-trusted:/trusted",
                    "sudograph-managed:gitlab",
                    "python",
                    "-c",
                    "import sys;from pathlib import Path;"
                    "Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())",
                    destination,
                ],
                data=path.read_bytes(),
            )
    command(
        [
            *compose,
            "exec",
            "-T",
            "runner",
            "sh",
            "-c",
            "cat > /etc/gitlab-runner/config.pending && "
            "mv /etc/gitlab-runner/config.pending /etc/gitlab-runner/config.toml",
        ],
        data=prepared["runner"].encode(),
    )
    wait_for("http://127.0.0.1:8788/health", timeout=120)
    public = {
        "model_project": prepared["project"]["id"],
        "pipeline_project": prepared["pipeline_project"]["id"],
        "model_url": prepared["project"]["web_url"],
        "publisher_url": "http://127.0.0.1:8788",
        "synthetic_acceptance_actors": True,
    }
    (folder / "deployment.json").write_text(json.dumps(public, indent=2), encoding="utf8")
    print(json.dumps(public), flush=True)
    return {**public, "actors": actors, "baseline": baseline, "policy": prepared["policy"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_directory")
    parser.add_argument("--baseline", help="operator-checked phase-one model JSON")
    args = parser.parse_args()
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf8")) if args.baseline else None
    deploy(args.private_directory, baseline=baseline)


if __name__ == "__main__":
    main()
