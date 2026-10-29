"""Accept a built wheel outside the source tree using actual worker processes.

The isolated interpreter ignores PYTHONPATH and the working directory. It uses
the invoking Python's installed dependencies and a temporary wheel installation
for the compiler itself, without a network or a source-tree import.
"""

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from contextlib import closing
from pathlib import Path

from compiler import app, html_export
from compiler.managed import code_digest
from compiler.workspace import Workspace

ROOT = Path(__file__).resolve().parent.parent


def run(argv, *, cwd, payload=None):
    result = subprocess.run(
        [str(value) for value in argv], cwd=cwd,
        env={key: value for key, value in os.environ.items()
             if key not in {"PYTHONPATH", "PYTHONHOME"}},
        input=None if payload is None else json.dumps(payload) + "\n",
        text=True, encoding="utf8", capture_output=True, check=False, timeout=180,
    )
    if result.returncode:
        raise RuntimeError(f"{argv[1:]} failed: {result.stdout}\n{result.stderr}")
    return result.stdout


def accept(wheel, directory):
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf8"))["project"]
    dependencies = {line.strip().lower()
                    for line in (ROOT / "requirements.txt").read_text().splitlines()
                    if line.strip() and not line.startswith("#")}
    if {value.lower() for value in metadata["dependencies"]} != dependencies:
        raise AssertionError("Wheel dependencies drifted from pinned runtime requirements")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        contents = hashlib.sha256()
        for name in sorted(names):
            payload = archive.read(name)
            contents.update(name.encode() + b"\0" + len(payload).to_bytes(8, "big") + payload)
        if any(not name.startswith(("compiler/", "sudograph_compiler-")) for name in names):
            raise AssertionError("Wheel contains files outside its runtime/distribution")
        if any(name.endswith((".db", ".sqlite", ".yaml", ".pyc")) for name in names):
            raise AssertionError("Wheel contains source data, models or interpreter caches")
        expected_assets = {p.relative_to(ROOT / "app").as_posix(): p.read_bytes()
                           for p in (ROOT / "app").rglob("*") if p.is_file()}
        actual_assets = {name.removeprefix("compiler/_assets/"): archive.read(name)
                         for name in names if name.startswith("compiler/_assets/")}
        if expected_assets != actual_assets:
            raise AssertionError("Wheel renderer differs from the checked source renderer")
    # Windows CI uses short-name temporary paths (for example RUNNER~1).
    # Resource discovery resolves paths, so compare their physical identities.
    environment = (directory / "installed").resolve()
    python = sys.executable
    isolated = [python, "-I", "-X", "utf8", "-c",
                f"import sys, runpy; sys.path.insert(0, {str(environment)!r}); "
                "runpy.run_module(sys.argv.pop(1), run_name='__main__')"]
    empty = directory / "empty-working-directory"
    empty.mkdir()
    run([python, "-I", "-m", "pip", "install", "--no-index", "--no-deps",
         "--target", environment, wheel], cwd=empty)
    # The installed worker reports its own locations and resource digest.
    setup = f"import sys; sys.path.insert(0, {str(environment)!r});\n"
    identity = json.loads(run([python, "-I", "-X", "utf8", "-c", setup + """
import compiler, json
from importlib.metadata import requires, version
from compiler.managed import code_digest
from compiler.runtime_files import renderer_directory, nexus_directory
print(json.dumps({'module':compiler.__file__, 'version':version('sudograph-compiler'),
    'dependencies':requires('sudograph-compiler'),
    'digest':code_digest(), 'renderer':str(renderer_directory()),
    'nexusBridgePresent':(nexus_directory()/'read-grant.mjs').is_file()}))
"""], cwd=empty))
    checks = {
        "module location": Path(identity["module"]).resolve().is_relative_to(environment),
        "renderer location": Path(identity["renderer"]).resolve().is_relative_to(environment),
        "implementation digest": identity["digest"] == code_digest(),
        "Nexus bridge": identity["nexusBridgePresent"],
        "version": identity["version"] == metadata["version"],
        "dependencies": {value.lower() for value in identity["dependencies"]} == dependencies,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError("Installed runtime differs from this build: " + ", ".join(failed))
    source = directory / "source.sqlite"
    with closing(sqlite3.connect(source)) as database:
        database.executescript("""
            CREATE TABLE Tickets (id INTEGER PRIMARY KEY, amount REAL);
            INSERT INTO Tickets VALUES (1, 7), (2, NULL);
            CREATE VIEW Totals AS SELECT SUM(amount) AS amount FROM Tickets;
        """)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    store = directory / "model.db"

    def worker(module, request, *args):
        response = json.loads(run(
            [*isolated, module, "--store", store, "--actor", "installed-host", *args],
            cwd=empty, payload=request,
        ))
        if not response["ok"]:
            raise AssertionError(response)
        return response["result"]

    intake = {"source": "sqlite:///" + source.as_posix(), "namespace": "tickets",
              "operation_id": "install-source", "language": "en", "snapshot_records": False}
    receipt = worker("compiler.registration", intake)
    scan = receipt["registration"]["scan"]
    if not (scan["structure_complete"] and scan["objects"] == 2 and scan["fields"] == 3):
        raise AssertionError("Installed scanner did not enumerate the complete fixture")
    contract = worker("compiler.workspace", {"operation": "contract"})
    # The same discoverable authoring example a no-context agent receives.
    model = contract["write"]["document_schema"]["examples"][0]
    edit = {"operation": "apply", "request": {"base_revision": contract["revision"],
            "operation_id": "install-edit", "model": json.dumps(model)}}
    applied = worker("compiler.workspace", edit)
    if worker("compiler.workspace", edit) != applied:
        raise AssertionError("Installed worker lost idempotent write semantics")
    packet = worker("compiler.workspace", {"operation": "read", "product": "context"})
    compiled = worker("compiler.workspace", {"operation": "read", "product": "model"})
    plain = worker("compiler.workspace", {"operation": "read", "product": "html"})
    review = worker("compiler.review_host", {"operation": "html", "endpoint": "/v1"},
                    "--resource", "tickets")
    expected = Workspace(store)
    if (packet["revision"] != applied["revision"] or compiled != expected.read(product="model")
            or plain != expected.read(product="html")
            or review != expected.review({"endpoint": "/v1", "resource": "tickets"})):
        raise AssertionError("Installed graph/context diverged from the same canonical revision")
    # Stored JSON sorts object keys; compare both renderers on that exact same
    # decoded input rather than comparing a re-render to its earlier key order.
    rendered = run([python, "-I", "-X", "utf8", "-c", setup + """
import json, sys
from compiler.app import render
print(render(json.load(sys.stdin), language='en'), end='')
"""], cwd=empty, payload=compiled)
    if rendered != app.render(compiled, language="en"):
        raise AssertionError("Installed and source renderers produced different HTML")
    packed = run([python, "-I", "-X", "utf8", "-c", setup + """
import json, sys
from compiler.html_export import pack
print(pack(json.load(sys.stdin), language='en'), end='')
"""], cwd=empty, payload=plain)
    if packed != html_export.pack(plain, language="en") or html_export.unpack(packed) != plain:
        raise AssertionError("Installed packed renderer differs from the native renderer")
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise AssertionError("Worker changed its read-only source")
    return {"format": "sudograph-installed-runtime-acceptance/v1", "passed": True,
            "wheel": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "contents_digest": contents.hexdigest(),
            "version": identity["version"], "implementation_digest": identity["digest"],
            "source_objects": scan["objects"], "source_fields": scan["fields"],
            "revision": applied["revision"], "context_digest": packet["context_digest"],
            "records_embedded": 0, "source_unchanged": True,
            "scope": "Installed scanner, authoring, rendering, context and resource parity. "
                     "Not cloud tenant authorization or optional Nexus transport acceptance."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="sudograph-installed-") as folder:
        directory = Path(folder)
        wheel = args.wheel.resolve() if args.wheel else None
        if wheel is None:
            output = directory / "wheel"
            run([sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", output],
                cwd=ROOT)
            wheels = list(output.glob("*.whl"))
            if len(wheels) != 1:
                raise AssertionError("Expected one versioned compiler wheel")
            wheel = wheels[0]
            rebuilt = directory / "rebuilt"
            run([sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", rebuilt],
                cwd=ROOT)
            if wheel.read_bytes() != (rebuilt / wheel.name).read_bytes():
                raise AssertionError("Identical source produced different runtime wheel bytes")
        receipt = accept(wheel, directory)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
