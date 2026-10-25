"""Operator registration of a read-only SQLite source for ordinary model authoring."""

import argparse
import json

from compiler.registration import register


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="operator-owned SQLite DSN")
    parser.add_argument("--store", required=True, help="new canonical model store")
    parser.add_argument("--namespace", required=True, help="persistent business identity namespace")
    parser.add_argument("--lang", choices=("en", "zh"), default="zh")
    parser.add_argument("--operation-id", default="initial-registration")
    parser.add_argument("--actor", default="operator")
    parser.add_argument(
        "--snapshot-records",
        action="store_true",
        help="explicit frozen export; default registers structure without record rows",
    )
    args = parser.parse_args()
    store = register(args.store, source=args.source, namespace=args.namespace, language=args.lang,
                     snapshot_records=args.snapshot_records, operation_id=args.operation_id,
                     actor=args.actor)
    print(json.dumps(store.contract(), ensure_ascii=False))


if __name__ == "__main__":
    main()
