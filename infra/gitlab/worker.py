"""Operator-owned CI entry point; never imports code from the model checkout."""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/sudograph")
from compiler import app, business
from compiler.managed import MODEL_FILE, compile_model

policy = json.loads(Path("/trusted/worker.json").read_text(encoding="utf8"))
checkout = Path(os.environ["CI_PROJECT_DIR"])
if str(policy["project_id"]) != os.environ["CI_PROJECT_ID"]:
    raise ValueError("worker is not registered for this project")
files = []
for folder, dirs, names in os.walk(checkout):
    dirs[:] = [d for d in dirs if d != ".git"]
    if any((Path(folder) / d).is_symlink() for d in dirs):
        raise ValueError("model input must not contain symbolic links")
    for name in names:
        path = Path(folder) / name
        if path.is_symlink():
            raise ValueError("model input must not be a symbolic link")
        files.append(path.relative_to(checkout).as_posix())
if files != [MODEL_FILE]:
    raise ValueError("model.yaml is the only registered input; deployment owns CI and HTML")
baseline = json.loads(Path("/trusted/baseline.json").read_text(encoding="utf8"))
previous = {}


def git(*args):
    result = subprocess.run(
        ["git", "-C", str(checkout), *args], capture_output=True, check=False, timeout=60
    )
    if result.returncode:
        raise ValueError("registered Git history could not be read")
    return result.stdout.decode("utf8")


# GitLab job tokens support Git fetch, but not the list-commits or JSON-files APIs.
# The runner's clone credentials remain in its checkout; never print its URL.
git("fetch", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main")
commits = git("rev-list", "--first-parent", "origin/main").splitlines()
if policy["bootstrap_sha"] not in commits:
    raise ValueError("registered source bootstrap is absent from target history")
for sha in reversed(commits[: commits.index(policy["bootstrap_sha"]) + 1]):
    _, previous = compile_model(
        git("show", f"{sha}:{MODEL_FILE}"), baseline, previous, namespace=policy["namespace"]
    )
model, _ = compile_model(
    (checkout / MODEL_FILE).read_text(encoding="utf8"),
    baseline,
    previous,
    namespace=policy["namespace"],
)
output = checkout / "review.html"
business.write(output, app.render(model, language=policy["language"]).encode("utf8"))
app.check_export(output, model, language=policy["language"])
print(
    json.dumps(
        {
            "reader": "verified",
            "baseline": business.digest(baseline),
            "business_approval": "not inferred from compiler checks",
        }
    )
)
