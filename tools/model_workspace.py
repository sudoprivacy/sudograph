"""Operator registration of a read-only SQLite source for ordinary model authoring."""

import argparse
import json
import tempfile
from pathlib import Path

import yaml

from compiler import app, bind, project, spec
from compiler.workspace import Workspace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="operator-owned SQLite DSN")
    parser.add_argument("--store", required=True, help="new canonical model store")
    parser.add_argument("--namespace", required=True, help="persistent business identity namespace")
    parser.add_argument("--lang", choices=("en", "zh"), default="zh")
    parser.add_argument(
        "--snapshot-records",
        action="store_true",
        help="explicit frozen export; default registers structure without record rows",
    )
    args = parser.parse_args()
    dsn = "sqlite:///" + Path(bind._path_of(args.source, ".")).resolve().as_posix()
    with tempfile.TemporaryDirectory(prefix="sudograph-register-") as folder:
        source = Path(folder) / "source.yaml"
        source.write_text(yaml.safe_dump(project.draft(dsn)), encoding="utf8")
        baseline = app.bundle(spec.load(str(source)), records=args.snapshot_records)
    store = Workspace.create(args.store, baseline, namespace=args.namespace, language=args.lang)
    print(json.dumps(store.contract(), ensure_ascii=False))


if __name__ == "__main__":
    main()
