"""Isolated nexusd-cluster authentication + Northwind gateway acceptance.

Requires the companion cluster change enabling --permission-policy zone-grants,
and `npm ci --prefix nexus-client`. Never restarts a shared daemon or mounts a
database in its VFS. The SQLite SQL driver remains outside this acceptance scope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from compiler.gateway import NexusAuthority
from compiler.nexus import NexusClient
from tools.check_northwind_access import verify as verify_northwind


def verify(binary, database):
    binary, database = Path(binary).resolve(strict=True), Path(database).resolve(strict=True)
    with TemporaryDirectory(prefix="sudograph-nexus-acceptance-") as directory:
        root = Path(directory)
        host = root / "rootfs"
        host.mkdir()
        (host / "operator-grant.json").write_text('{"fixture":true}', encoding="utf-8")
        env = {**os.environ, "NEXUS_API_KEY_SECRET": secrets.token_hex(32)}
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        endpoint = f"127.0.0.1:{port}"
        common = ["--data-dir", str(root / "data"), "--identity-dir", str(root / "identity"),
                  "--hostname", "sudograph-access-review", "--bind-addr", endpoint,
                  "--no-tls", "--root-path", str(host)]

        def mint(subject, zone):
            result = subprocess.run(
                [str(binary), "auth", "mint", *common, "--subject-type", "user",
                 "--subject-id", subject, "--zone", zone],
                env=env, capture_output=True, text=True, encoding="utf-8", timeout=90, check=False,
            )
            token = re.search(r"\bsk-[\w-]+", result.stdout)
            if result.returncode or not token:
                raise RuntimeError("isolated credential mint failed")
            return token.group(0)

        reader, other = mint("germany-reader", "root:r"), mint("other-reader", "elsewhere:r")
        manager = mint("manager", "root:r")
        for name, subject, token, actions in [
            ("germany", "germany-reader", reader, ["read"]),
            ("all", "manager", manager, ["read", "export"]),
        ]:
            (host / (name + ".json")).write_text(json.dumps({
                "resource": name, "subject": subject, "actions": actions,
                "credential_sha256": hashlib.sha256(token.encode()).hexdigest(),
            }), encoding="utf-8")
        with (root / "daemon.log").open("w", encoding="utf-8") as log:
            daemon = subprocess.Popen(
                [str(binary), *common, "--cluster-init", "root",
                 "--permission-policy", "zone-grants"],
                env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                client = NexusClient(endpoint, timeout=3)
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    if daemon.poll() is not None:
                        raise RuntimeError("isolated cluster exited; zone-grants support required")
                    try:
                        client.read("/operator-grant.json", credential=reader)
                        break
                    except (PermissionError, subprocess.TimeoutExpired):
                        time.sleep(0.25)
                else:
                    raise RuntimeError("isolated authenticated read did not become ready")
                probe = Path(__file__).resolve().parent.parent / "nexus-client" / "probe.mjs"
                result = subprocess.run(
                    ["node", str(probe)], input=json.dumps({"endpoint": endpoint,
                                                           "reader": reader, "other": other}),
                    capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
                )
                checks = json.loads(result.stdout)
                assert all(checks.values()), checks
                authority = NexusAuthority(client, {"germany": "/germany.json", "all": "/all.json"})
                northwind = verify_northwind(
                    database, authority=authority, reader_token=reader, manager_token=manager,
                    revoke=lambda: (host / "germany.json").write_text("{}", encoding="utf-8"),
                )
                return {"profile": "nexusd-cluster", "isolated": True,
                        "checks": checks, "northwind": northwind, "passed": True,
                        "raw_database_mounted": False, "sqlite_driver_integrated": False}
            finally:
                daemon.terminate()
                try:
                    daemon.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    daemon.kill()
                    daemon.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("database", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = json.dumps(verify(args.binary, args.database), ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(result + "\n", encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
