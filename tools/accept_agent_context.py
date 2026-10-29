"""Accept an installed compiler with a pinned, real Sudo Code ACP process.

The loopback provider captures actual model request bodies and returns fixed
responses. This checks integration, not model reasoning, production host
authorization, cloud login or review comments. Retain fixture evidence on failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import sqlite3
import subprocess
import tempfile
import threading
import time
from contextlib import ExitStack, closing, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WAIT = 30
CONTEXT_METHOD = "_sudocode/session/host_context"


def run(argv, *, cwd, payload=None):
    result = subprocess.run(
        [str(value) for value in argv], cwd=cwd, capture_output=True,
        input=None if payload is None else json.dumps(payload),
        encoding="utf8", timeout=WAIT, check=False,
        env={key: value for key, value in os.environ.items()
             if key.upper() not in {"PYTHONPATH", "PYTHONHOME"}},
    )
    if result.returncode:
        raise RuntimeError(f"Fixture process exited {result.returncode}: {result.stderr[-8000:]}")
    return result.stdout


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


class Provider(BaseHTTPRequestHandler):
    """A deterministic provider, never an agent or compiler replacement."""

    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.captured.append({"path": self.path, "body": body})
        events = [
            ("message_start", {"type": "message_start", "message": {
                "id": f"fixture-{len(self.server.captured)}", "type": "message",
                "role": "assistant", "content": [], "model": "context-probe",
                "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 0},
            }}),
            ("content_block_start", {"type": "content_block_start", "index": 0,
                                     "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                     "delta": {"type": "text_delta", "text": "Fixture response."}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_delta", {"type": "message_delta", "delta": {
                "stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 4}}),
            ("message_stop", {"type": "message_stop"}),
        ]
        payload = "".join(f"event: {event}\ndata: {json.dumps(value)}\n\n"
                          for event, value in events).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)


class AcpClient:
    def __init__(self, process, resolve_context):
        self.process = process
        self.resolve_context = resolve_context
        self.incoming = queue.Queue()
        self.transcript = []
        self.next_id = 0
        self.session = None
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.process.stdout:
            with suppress(json.JSONDecodeError):
                self.incoming.put(json.loads(line))
        self.incoming.put({"fixture_eof": True})

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def rpc(self, method, params):
        self.next_id += 1
        request_id = self.next_id
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + WAIT
        while True:
            try:
                message = self.incoming.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                raise AssertionError(
                    f"Timed out waiting for {method}; inspect engine-stderr.log") from None
            self.transcript.append(message)
            assert not message.get("fixture_eof"), "Engine exited; inspect engine-stderr.log"
            if message.get("method") == CONTEXT_METHOD:
                assert message["params"]["sessionId"] == self.session
                try:
                    context = self.resolve_context()
                except PermissionError:
                    self.send({"jsonrpc": "2.0", "id": message["id"], "error": {
                        "code": -32603, "message": "Fixture model grant revoked"}})
                else:
                    self.send({"jsonrpc": "2.0", "id": message["id"],
                               "result": {"appendSystemPrompt": context["text"]}})
            elif message.get("id") == request_id:
                return message
            assert time.monotonic() < deadline, f"Timed out waiting for {method}"

    def prompt(self, text):
        return self.rpc("session/prompt", {"sessionId": self.session,
                                          "prompt": [{"type": "text", "text": text}]})


def system_text(request):
    system = request["system"]
    return system if isinstance(system, str) else "\n".join(block["text"] for block in system)


def accept(engine, expected_sha256, python, case):
    actual_sha256 = hashlib.sha256(engine.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256.lower():
        raise ValueError("Engine checksum differs from the operator's pinned artifact")
    worker_directory, workspace, config, profile = [case / name for name in (
        "worker", "workspace", "config", "profile")]
    for directory in (worker_directory, workspace, config, profile):
        directory.mkdir()
    identity = json.loads(run([python, "-I", "-X", "utf8", "-c", """
import compiler, json
from importlib.metadata import distribution
from pathlib import Path
from compiler.managed import code_digest
package = distribution('sudograph-compiler')
assert Path(compiler.__file__).resolve() == package.locate_file('compiler/__init__.py').resolve()
print(json.dumps({'version': package.version, 'digest': code_digest()}))
"""], cwd=worker_directory))
    source, store = case / "source.sqlite", case / "model.db"
    with closing(sqlite3.connect(source)) as database:
        database.executescript("""
            CREATE TABLE Tickets(id INTEGER PRIMARY KEY, amount REAL);
            INSERT INTO Tickets VALUES (1,7),(2,NULL);
        """)
    before = hashlib.sha256(source.read_bytes()).hexdigest()

    def worker(module, request):
        response = json.loads(run([
            python, "-I", "-X", "utf8", "-m", module, "--store", store,
            "--actor", "fixture-host"], cwd=worker_directory, payload=request))
        assert response["ok"], response
        return response["result"]

    registered = worker("compiler.registration", {
        "source": "sqlite:///" + source.as_posix(), "namespace": "support",
        "operation_id": "source", "language": "en", "snapshot_records": False,
    })
    assert registered["registration"]["scan"]["structure_complete"]
    document = {"format": "sudograph-business-overlay/v5", "namespace": "support",
                "baseline": registered["contract"]["baseline"], "definitions": {"revenue": {
                    "concept": "revenue", "category": "meaning", "role": "business",
                    "purpose": {"stakeholder": "Support manager",
                                "decision": "Choose revenue policy"},
                    "label": "Revenue policy", "statement": "CONTEXT_A_USE_ORDER_DATE",
                    "origin": "inferred", "contributor": "model", "version": 1, "targets": [],
                }}}

    def apply(operation):
        contract = worker("compiler.workspace", {"operation": "contract"})
        return worker("compiler.workspace", {"operation": "apply", "request": {
            "base_revision": contract["revision"], "operation_id": operation,
            "model": json.dumps(document),
        }})

    apply("revision-a")
    contexts, captured = [], []
    allowed = True

    def resolve_context():
        if not allowed:
            raise PermissionError("Fixture model grant revoked")
        context = worker("compiler.workspace", {"operation": "read", "product": "context"})
        contexts.append(context)
        return context

    client = None
    try:
        with ExitStack() as cleanup:
            server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
            server.captured = captured
            threading.Thread(target=server.serve_forever, daemon=True).start()
            cleanup.callback(server.server_close)
            cleanup.callback(server.shutdown)
            settings = {"auth_modes": {"api-key": {"anthropic": {
                "baseUrl": f"http://127.0.0.1:{server.server_port}", "apiKey": "fixture-only-key",
            }}}, "models": {"context-probe": {"name": "Context probe", "providers": {
                "api-key": {"provider": "anthropic", "model": "context-probe"},
            }}}}
            (config / "sudocode.json").write_text(json.dumps(settings), encoding="utf8")
            environment = {key: value for key, value in os.environ.items() if key.upper() in {
                "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATHEXT"}}
            environment.update(SUDO_CODE_CONFIG_HOME=str(config), HOME=str(profile),
                               USERPROFILE=str(profile), NO_COLOR="1")
            stderr = cleanup.enter_context((case / "engine-stderr.log").open("w", encoding="utf8"))
            process = subprocess.Popen([
                str(engine), "--auth", "api-key", "--model", "context-probe",
                "--permission-mode", "read-only", "acp"], cwd=workspace, env=environment,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, encoding="utf8",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            cleanup.callback(stop, process)
            client = AcpClient(process, resolve_context)
            initialized = client.rpc("initialize", {"protocolVersion": 1})
            sudocode = initialized.get("result", {}).get("_meta", {}).get("sudocode", {})
            capability = sudocode.get("hostContext", {})
            assert capability.get("version") == 1, (
                "The pinned engine must advertise hostContext v1; no stale-context fallback")
            created = client.rpc("session/new", {"cwd": str(workspace), "mcpServers": [],
                "_meta": {"sudocode": {"hostContext": {"version": 1},
                                      "appendSystemPrompt": "INITIAL_CONTEXT_MUST_BE_REPLACED"}}})
            assert "error" not in created, created
            client.session = created["result"]["sessionId"]
            first = client.prompt("FIRST_USER_TURN")
            assert "error" not in first, first
            assert len(captured) == len(contexts) == 1
            assert captured[0]["path"].rstrip("/").endswith("/v1/messages")
            assert contexts[0]["text"] in system_text(captured[0]["body"])
            assert "CONTEXT_A_USE_ORDER_DATE" in system_text(captured[0]["body"])
            assert "INITIAL_CONTEXT_MUST_BE_REPLACED" not in system_text(captured[0]["body"])
            document["definitions"]["revenue"].update(
                version=2, statement="CONTEXT_B_USE_SHIPMENT_DATE")
            updated = apply("revision-b")
            second = client.prompt("SECOND_USER_TURN")
            assert "error" not in second, second
            assert len(captured) == len(contexts) == 2
            assert contexts[1]["revision"] == updated["revision"] != contexts[0]["revision"]
            body = captured[1]["body"]
            assert contexts[1]["text"] in system_text(body)
            assert "CONTEXT_B_USE_SHIPMENT_DATE" in system_text(body)
            assert "CONTEXT_A_USE_ORDER_DATE" not in system_text(body)
            assert "FIRST_USER_TURN" in json.dumps(body["messages"])
            assert "CONTEXT_A_USE_ORDER_DATE" not in json.dumps(body["messages"])
            html = worker("compiler.workspace", {"operation": "read", "product": "html"})
            assert updated["revision"] in html and "CONTEXT_B_USE_SHIPMENT_DATE" in html
            allowed = False
            denied = client.prompt("DENIED_TURN")
            assert "error" in denied, denied
            assert len(captured) == len(contexts) == 2
    finally:
        (case / "transcript.json").write_text(
            json.dumps(client.transcript if client else [], indent=2), encoding="utf8")
        (case / "requests.json").write_text(json.dumps(captured, indent=2), encoding="utf8")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    return {"format": "sudograph-agent-context-acceptance/v1", "passed": True,
            "engine_sha256": actual_sha256, "compiler": identity,
            "canonical_revisions": [context["revision"] for context in contexts],
            "real_acp_process": True, "installed_compiler": True,
            "exact_compiled_context_in_requests": True, "same_graph_context_revision": True,
            "history_preserved": True, "context_not_in_user_history": True,
            "denied_model_requests": 0, "source_unchanged": True,
            "scope": "Explicit pinned engine and deterministic provider capture. "
                     "Not engine publication, model business quality, production host ACL, "
                     "cloud login, Sudowork UI or ShareOne comments."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--engine-sha256", required=True)
    parser.add_argument("--runtime-python", required=True, type=Path)
    parser.add_argument("--evidence-directory", required=True, type=Path)
    args = parser.parse_args()
    args.evidence_directory.mkdir(parents=True, exist_ok=True)
    case = Path(tempfile.mkdtemp(prefix="agent-context-", dir=args.evidence_directory)).resolve()
    print(f"Acceptance evidence: {case}", flush=True)
    receipt = accept(args.engine.resolve(), args.engine_sha256, args.runtime_python.resolve(), case)
    (case / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
