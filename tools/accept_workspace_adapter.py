"""Exercise the actual Sudowork subprocess adapter against this compiler checkout.

This is a local host-boundary receipt, not Desktop/WebUI product acceptance.
No model provider, GitLab approval, production database or ShareOne is involved.
"""

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from compiler import business
from compiler.workspace import Workspace

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sudowork", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--bun", default="bun", help="Bun executable (not a shell function)")
    args = parser.parse_args()
    client = args.sudowork.resolve() / (
        "apps/desktop/src/process/services/ontology/SudographModelClient.ts"
    )
    if not client.is_file():
        parser.error("Sudowork checkout does not contain the canonical model adapter")
    with tempfile.TemporaryDirectory(prefix="sudograph-host-acceptance-") as folder:
        directory = Path(folder)
        database = directory / "source.sqlite"
        db = sqlite3.connect(database)
        with db:
            db.executescript("""
                CREATE TABLE Tickets (id INTEGER PRIMARY KEY, amount REAL);
                INSERT INTO Tickets VALUES (1, 7), (2, NULL);
                CREATE VIEW Totals AS SELECT SUM(amount) AS amount FROM Tickets;
            """)
        db.close()
        source_hash = hashlib.sha256(database.read_bytes()).hexdigest()
        registration = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.model_workspace",
                "--source",
                "sqlite:///" + database.as_posix(),
                "--store",
                str(directory / "registered.db"),
                "--namespace",
                "support",
                "--lang",
                "en",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf8",
            check=True,
        )
        contract = json.loads(registration.stdout)
        doc = {
            "format": business.FORMAT,
            "namespace": "support",
            "baseline": contract["baseline"],
            "definitions": {},
        }
        runtime = {
            "python": sys.executable,
            "compilerRoot": str(ROOT),
            "modelDirectory": str(directory),
        }
        script = directory / "accept.ts"
        script.write_text(
            "import assert from 'node:assert/strict';\n"
            f"import {{ SudographModelClient }} from {json.dumps(client.as_posix())};\n"
            f"const client = new SudographModelClient({json.dumps(runtime)});\n"
            f"const doc = {json.dumps(doc)};\n"
            """
            const invoke = (actor, operation) => client.invoke('registered', actor, operation);
            const contract = await invoke('alice', {operation: 'contract'});
            const yaml = (value) => JSON.stringify(value); // JSON is checked YAML, too.
            const definition = concept => ({concept, category:'meaning', role:'business',
              purpose:{stakeholder:'Support manager',decision:'Choose ticket policy'},
              label:concept,statement:'Needs business discussion',origin:'inferred',
              contributor:'model',version:1,targets:[]});
            const edits = ['refund','revenue'].map(key => ({base_revision:contract.revision,
              operation_id:key,model:yaml({...doc,definitions:{[key]:definition(key)}})}));
            const receipts = await Promise.all(edits.map((request,index) =>
              invoke(index ? 'bob' : 'alice', {operation:'apply',request})));
            assert.deepEqual(receipts.map(r => r.merged).sort(), [false,true]);
            const retry = await invoke('alice',{operation:'apply',request:edits[0]});
            assert.deepEqual(retry,receipts[0]);
            const current = await invoke('alice',{operation:'contract'});
            // Use a JSON model read so this acceptance driver needs no second YAML parser.
            const compiled = await invoke('alice',{operation:'read',product:'model'});
            const document = compiled.business.document;
            const changed = structuredClone(document);
            changed.definitions.refund.version = 2;
            changed.definitions.refund.statement = 'Exclude refunds';
            const request = {base_revision:current.revision,
              operation_id:'refund-v2',model:yaml(changed)};
            const receipt = await invoke('alice',{operation:'apply',request});
            const conflicting = structuredClone(changed);
            conflicting.definitions.refund.statement = 'Include refunds';
            await assert.rejects(invoke('bob',{operation:'apply',request:{...request,
              operation_id:'conflicting-refund',model:yaml(conflicting)}}),
              error => error.code === 'MODEL_CONFLICT');
            const context = await invoke('alice',{operation:'read',product:'context'});
            const html = await invoke('alice',{operation:'read',product:'html'});
            assert.equal(context.revision,receipt.revision);
            assert.equal(context.inventory.definitions,2);
            assert.equal(context.inventory.record_rows_preloaded,0);
            assert.ok(html.includes(receipt.revision));
            assert.ok(html.includes('Exclude refunds'));
            const object = compiled.source_schema.sources[0].objects
              .find(o => o.name === 'Tickets');
            const page = await invoke('alice',{operation:'context_read',request:{
              revision:context.revision,context_digest:context.context_digest,
              id:object.id,records:true,limit:1}});
            assert.equal(page.data_kind,'live_source_page');
            assert.equal(page.rows.length,1);
            assert.equal(page.total,2);
            assert.deepEqual(page.rows[0],[1,7]);
            assert.equal((await invoke('bob',{operation:'contract'})).revision,receipt.revision);
            await assert.rejects(client.invoke('../other','alice',{operation:'contract'}));
            console.log(JSON.stringify({status:'passed',actors:2,compatible_merge:true,
              incompatible_edit_refused:true,idempotent_retry:true,definitions:2,
              same_graph_context_revision:true,rows_preloaded:0,live_page_verified:true,
              revision:receipt.revision}));
            """,
            encoding="utf8",
        )
        result = subprocess.run(
            [shutil.which(args.bun) or args.bun, "run", str(script)],
            cwd=args.sudowork,
            text=True,
            encoding="utf8",
            capture_output=True,
            check=True,
        )
        receipt = json.loads(result.stdout)
        assert hashlib.sha256(database.read_bytes()).hexdigest() == source_hash
        model = Workspace(directory / "registered.db").read(product="model")
        assert not model["records"]
        receipt.update(
            source_unchanged=True,
            record_delivery="live_on_demand",
            compiler_root=str(ROOT),
            adapter=str(client),
        )
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf8")
        print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
