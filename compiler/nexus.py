"""Official Nexus VFS Read transport, with credentials on stdin rather than argv."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit


class NexusClient:
    def __init__(self, endpoint, *, tls=None, node="node", timeout=15):
        host = urlsplit(endpoint if "://" in endpoint else "//" + endpoint).hostname
        if tls is not None or host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(
                "token-bound Nexus bootstrap requires authenticated loopback without TLS; "
                "certificate identity needs its own verified caller adapter"
            )
        self.endpoint, self.tls, self.node, self.timeout = endpoint, tls, node, timeout
        self.bridge = Path(__file__).resolve().parent.parent / "nexus-client" / "read-grant.mjs"

    def read(self, path, *, credential):
        result = subprocess.run(
            [self.node, str(self.bridge)],
            input=json.dumps({"endpoint": self.endpoint, "path": path,
                              "credential": credential, "tls": self.tls}),
            capture_output=True, text=True, encoding="utf-8", timeout=self.timeout,
            check=False,
        )
        if result.returncode:
            raise PermissionError("Nexus grant read refused or unavailable")
        response = json.loads(result.stdout)
        return SimpleNamespace(content=base64.b64decode(response["content"], validate=True))
