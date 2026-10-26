"""Accept canonical review in an isolated real browser, without customer data.

Requires playwright==1.61.0 and its Chromium runtime. --ai-dev-browser-port
additionally checks the same owned execution browser through ai-dev-browser.
The test credential represents a synthetic complete-resource grant, not a cloud
login, field policy or production permission acceptance.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import secrets
import shutil
import sqlite3
import sys
import tempfile
import threading
from contextlib import asynccontextmanager, closing
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml

from compiler import app, business, project, spec
from compiler.gateway import FileCapabilities
from compiler.review import ReviewGateway
from compiler.serve import handler
from compiler.workspace import Workspace


@asynccontextmanager
async def host_review(folder, store, policy, sudowork, bun):
    """Real host server/client; the fixture installs its cookie, not a host UI."""
    client = sudowork.resolve() / (
        "apps/desktop/src/process/services/ontology/SudographModelClient.ts"
    )
    host = client.parent / "SudographReviewHost.ts"
    if not client.is_file() or not host.is_file():
        raise ValueError("Sudowork checkout must contain the authenticated review adapter")
    script = folder / "review-host.ts"
    runtime = {"python": sys.executable, "compilerRoot": str(Path(__file__).resolve().parents[1]),
               "modelDirectory": str(store.path.parent)}
    script.write_text(
        "import {readFileSync} from 'node:fs';\n"
        f"import {{SudographModelClient}} from {json.dumps(client.as_posix())};\n"
        f"import {{SudographReviewHost}} from {json.dumps(host.as_posix())};\n"
        f"const policy={json.dumps(policy.as_posix())};\n"
        f"const client=new SudographModelClient({json.dumps(runtime)});\n"
        """
        const host = new SudographReviewHost({
          authorize: binding => {
            if(binding.workspaceId!=='support'||binding.conversationId!=='fixture-chat'||
               !JSON.parse(readFileSync(policy,'utf8')).credentials.length)
              throw new Error('Review revoked');
          },
          read: (_resource,request)=>client.review('model','fixture-host','support',request),
        });
        try {
          const launch=await host.createSession({workspaceId:'support',
                                                conversationId:'fixture-chat'});
          console.log(JSON.stringify({url:launch.url,cookie:launch.cookie}));
          for await (const _ of process.stdin) { /* EOF closes the owned host. */ }
        } finally { await host.close(); }
        """, encoding="utf8",
    )
    process = await asyncio.create_subprocess_exec(
        shutil.which(bun) or bun, "run", str(script), stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        # This private pipe contains the one-time handoff. Never log its payload.
        line = await asyncio.wait_for(process.stdout.readline(), timeout=30)
        if not line:
            raise RuntimeError("Host review fixture did not start")
        launch = json.loads(line)
        yield launch
    finally:
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except TimeoutError:
            process.kill()
            await process.wait()


async def accept(folder, evidence, *, sdk_port=None, sudowork=None, bun="bun"):
    from playwright.async_api import async_playwright  # noqa: PLC0415 — optional browser dependency

    evidence.mkdir(parents=True, exist_ok=True)
    database = folder / "source #registered.db"
    with closing(sqlite3.connect(database)) as db, db:
        db.executescript("""
            CREATE TABLE Tickets(id INTEGER PRIMARY KEY, note TEXT, picture BLOB);
            CREATE VIEW Notes AS SELECT note FROM Tickets;
        """)
        db.executemany("INSERT INTO Tickets VALUES (?, ?, X'00FF')",
                       [(i, f"unembedded-row-{i}") for i in range(1, 112)])
        db.execute("UPDATE Tickets SET note = NULL WHERE id = 2")
    dsn = "sqlite:///" + database.as_posix()
    source = folder / "source.yaml"
    source.write_text(yaml.safe_dump(project.draft(dsn)), encoding="utf8")
    baseline = app.bundle(spec.load(str(source)), records=False)
    schema = baseline["source_schema"]["sources"][0]
    objects = {obj["name"]: obj["id"] for obj in schema["objects"]}
    store = Workspace.create(folder / "model.db", baseline, namespace="support", language="en",
                             record_sources={schema["id"]: dsn})
    token = secrets.token_urlsafe(32)
    policy = folder / "policy.json"
    policy.write_text(json.dumps({"credentials": [{
        "sha256": hashlib.sha256(token.encode()).hexdigest(), "subject": "synthetic-reviewer",
        "grants": {"support": ["read"]},
    }]}), encoding="utf8")
    gateway = ReviewGateway({"support": store}, FileCapabilities(policy))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(gateway))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    errors = []
    host_scope = None
    try:
        review_url = base + "/review/support"
        launch = None
        if sudowork is not None:
            host_scope = host_review(folder, store, policy, sudowork, bun)
            launch = await host_scope.__aenter__()
            review_url = launch["url"]
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                args=[] if sdk_port is None else [f"--remote-debugging-port={sdk_port}"]
            )
            try:
                context = await browser.new_context(
                    extra_http_headers={} if launch else {"Authorization": "Bearer " + token},
                    viewport={"width": 1440, "height": 1000},
                )
                if launch:
                    cookie = launch["cookie"]
                    await context.add_cookies([{
                        "name": cookie["name"], "value": cookie["value"],
                        "domain": "127.0.0.1", "path": cookie["path"],
                        "httpOnly": cookie["httpOnly"], "sameSite": cookie["sameSite"],
                        "expires": cookie["expires"],
                    }])
                page = await context.new_page()
                page.on("pageerror", lambda error: errors.append(error.stack or str(error)))
                response = await page.goto(review_url)
                assert response.status == 200
                html = await response.text()
                assert "unembedded-row-1" not in html and token not in html
                assert str(database) not in html
                if launch:
                    assert launch["cookie"]["value"] not in html
                    assert launch["cookie"]["value"] not in await page.evaluate("document.cookie")
                await page.wait_for_function(
                    "!!cy && document.querySelectorAll('.canvas-label').length > 0"
                )
                preloaded = await page.evaluate(
                    "BUNDLE.ui.agent_context.inventory.record_rows_preloaded"
                )
                assert preloaded == 0
                # A readable live graph is not proof of a working comment service.
                notice = page.locator('#commentNotice')
                assert await notice.is_visible()
                assert 'Comments are not connected' in await notice.text_content()
                assert 'select text to comment' not in await page.locator(
                    '#interactionHint'
                ).text_content()
                await page.select_option('#language', 'zh')
                assert '尚未接入评论服务' in await notice.text_content()
                await page.select_option('#language', 'en')
                # A delayed SDK stub must not advertise a connected composer.
                # This simulates bridge readiness only, not submitting comments.
                await page.evaluate("""() => {
                  window.__SHAREONE__={anchors:{__pending:{},select(){},report(){},on(){}}};
                  document.dispatchEvent(new Event('shareone:ready'));
                }""")
                assert await notice.is_visible()
                assert 'has not connected' in await notice.text_content()
                await page.evaluate("""() => {
                  delete window.__SHAREONE__.anchors.__pending;
                  document.dispatchEvent(new Event('shareone:ready'));
                }""")
                assert not await notice.is_visible()
                assert 'select text to comment' in await page.locator(
                    '#interactionHint'
                ).text_content()
                # Reload restores the actual unconnected host before record acceptance.
                await page.reload()
                await page.wait_for_function('!!cy')
                assert await notice.is_visible()
                # Use the existing catalogue/field/record buttons, not injected record rows.
                async def open_records(name):
                    identity = objects[name]
                    await page.locator("#catalogueBtn").click()
                    await page.locator(
                        f'.source-catalogue details button[data-catalogue-id="{identity}"]'
                    ).click()
                    await page.locator(f'.canvas-label[data-node-id="{identity}"]').click()
                    await page.locator("[data-source-records]").click()

                await open_records("Tickets")
                rows = page.locator("[data-source-record]")
                await rows.first.wait_for()
                assert await rows.count() == 50
                assert await rows.first.locator("summary").text_content() == "1"
                assert "unembedded-row-1" in await rows.first.text_content()
                assert "NULL" in await rows.nth(1).text_content()
                await page.get_by_role("button", name="Next", exact=True).click()
                await page.wait_for_function(
                    "document.querySelector('[data-source-record]')?.dataset.sourceRecord==='50'"
                )
                assert await rows.first.locator("summary").text_content() == "51"
                assert await page.locator("[data-binary-download]").count() == 50
                await page.screenshot(path=str(evidence / "records-desktop.png"))
                assert hashlib.sha256(database.read_bytes()).hexdigest() == before
                # Only this fixture writer changes the source, independently of the model.
                with closing(sqlite3.connect(database)) as db, db:
                    db.execute("INSERT INTO Tickets VALUES (112, 'new-source-row', NULL)")
                await page.get_by_role("button", name="Next", exact=True).click()
                await page.wait_for_function(
                    "document.querySelector('[data-source-record]')?.dataset.sourceRecord==='100'"
                )
                assert await rows.count() == 12
                assert "new-source-row" in await rows.last.text_content()
                assert "112" in await page.locator(".schema-actions").last.text_content()
                # Keyless source views retain request-local positions.
                await open_records("Notes")
                await page.locator("[data-live-records]").wait_for()
                assert "within this read only" in await page.locator("#panel").text_content()
                # A successful ordinary edit changes the next review, using the shared renderer.
                contract = store.contract()
                document = {"format": business.FORMAT, "namespace": "support",
                            "baseline": contract["baseline"], "definitions": {"policy": {
                                "concept": "refund policy", "category": "meaning",
                                "role": "business",
                                "purpose": {"stakeholder": "Support", "decision": "Review refunds"},
                                "label": "Refund policy", "statement": "Refunds need review",
                                "origin": "inferred", "contributor": "model", "version": 1,
                                "targets": [],
                            }}}
                receipt = store.apply({
                    "base_revision": contract["revision"], "operation_id": "review-edit",
                    "model": yaml.safe_dump(document),
                }, actor="synthetic-host-actor")
                await page.reload()
                revision = await page.evaluate("BUNDLE.projection.model_revision")
                assert revision == receipt["revision"]
                assert "Refunds need review" in await page.content()
                await open_records("Tickets")
                await rows.first.wait_for()
                await page.set_viewport_size({"width": 390, "height": 844})
                await page.screenshot(path=str(evidence / "records-mobile.png"))
                if sdk_port is not None:
                    await check_sdk(sdk_port, review_url, evidence)
                policy.write_text('{"credentials":[]}', encoding="utf8")
                await page.get_by_role("button", name="Next", exact=True).click()
                await page.get_by_text("Unable to read source records.", exact=False).wait_for()
                assert await rows.count() == 0
                # Already received bytes cannot be revoked. Subsequent reads are denied.
                denied = await page.reload()
                assert denied.status == 403
                assert "unembedded-row" not in await page.content()
                anonymous = await browser.new_context()
                other = await anonymous.new_page()
                assert (await other.goto(review_url)).status == 403
                assert not errors, errors
            finally:
                await browser.close()
    finally:
        if host_scope is not None:
            await host_scope.__aexit__(None, None, None)
        server.shutdown()
        server.server_close()
        thread.join()
    return {
        "format": "sudograph-review-acceptance/v1", "status": "passed",
        "record_rows_preloaded": 0, "real_browser_record_paging": True,
        "binary_and_null_preserved": True, "live_source_update_observed": True,
        "source_unchanged_by_review": True, "keyless_positions_labeled": True,
        "checked_edit_visible_after_reload": True, "revocation_blocks_subsequent_reads": True,
        "anonymous_access_denied": True, "page_errors": errors,
        "ai_dev_browser_checked": sdk_port is not None,
        "real_sudowork_host_transport": sudowork is not None,
        "http_only_host_cookie": sudowork is not None,
        "unconnected_comments_reported": True,
        "comment_bridge_readiness_fixture": True,
        "real_comment_submission_verified": False,
        "comment_to_agent_delivery_verified": False,
        "standalone_browser_launch_verified": False,
        "authorization_scope": "synthetic complete resource; not cloud or row/field acceptance",
    }


async def check_sdk(port, review_url, evidence):
    from ai_dev_browser.core import (  # noqa: PLC0415 — optional same-browser acceptance
        connect_browser,
        get_active_tab,
        js_evaluate,
        page_screenshot,
    )

    tab = await get_active_tab(await connect_browser(port=port))
    location = (await js_evaluate(tab, "location.href"))["result"]
    assert location == review_url
    records = await js_evaluate(tab, "document.querySelectorAll('[data-source-record]').length")
    records = records["result"]
    assert records == 50
    await page_screenshot(tab, path=str(evidence / "records-ai-dev-browser.png"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--ai-dev-browser-port", type=int)
    parser.add_argument("--sudowork", type=Path, help="accept the real host HTTP/worker adapter")
    parser.add_argument("--bun", default="bun")
    args = parser.parse_args()
    if args.ai_dev_browser_port is not None and not 1 <= args.ai_dev_browser_port <= 65535:
        parser.error("ai-dev-browser port must be 1..65535")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps({"status": "running"}) + "\n", encoding="utf8")
    try:
        with tempfile.TemporaryDirectory(prefix="sudograph-review-acceptance-") as temporary:
            receipt = asyncio.run(accept(Path(temporary), args.receipt.with_suffix(""),
                                         sdk_port=args.ai_dev_browser_port,
                                         sudowork=args.sudowork, bun=args.bun))
    except BaseException as error:
        # Never leave a previous passing receipt after a failure or interruption.
        args.receipt.write_text(json.dumps({
            "format": "sudograph-review-acceptance/v1", "status": "incomplete",
            "error_type": type(error).__name__,
        }) + "\n", encoding="utf8")
        raise
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
