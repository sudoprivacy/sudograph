"""Bounded structural selection cannot invent relationships or change authority."""

import ast
import copy
import json
import sqlite3
import subprocess
from inspect import cleandoc
from pathlib import Path

import pytest
import yaml

from compiler import app, project, spec
from compiler.context import Reader
from compiler.subgraph_select import SelectionError, contract, subgraph_select


@pytest.fixture
def catalogue(tmp_path):
    database = tmp_path / "unrelated.db"
    with sqlite3.connect(database) as conn:
        conn.executescript("""
          CREATE TABLE Team(id INTEGER PRIMARY KEY);
          CREATE TABLE Ticket(id INTEGER PRIMARY KEY,team INTEGER REFERENCES Team(id));
          CREATE TABLE Message(id INTEGER PRIMARY KEY,ticket INTEGER REFERENCES Ticket(id));
          CREATE TABLE Unrelated(id INTEGER PRIMARY KEY);
          CREATE TABLE Other(id INTEGER PRIMARY KEY);
          CREATE VIEW Summary AS SELECT count(*) AS n FROM Message;
        """)
    path = tmp_path / "model.yaml"
    path.write_text(yaml.safe_dump(project.draft("sqlite:///" + database.as_posix())),
                    encoding="utf8")
    return app.bundle(spec.load(str(path)))["source_schema"]


def test_source_connector_does_not_merge_independent_components(catalogue):
    before = copy.deepcopy(catalogue)
    result = subgraph_select(catalogue, {})
    assert result["component_count"] == 3
    assert sorted(g["objects"] for g in result["components"]) == [1, 1, 4]
    assert result == subgraph_select(catalogue, {})
    assert catalogue == before
    assert all(e["kind"] in {"source_fk", "source_view"} for e in result["edges"])
    reader = Reader({"source_schema": catalogue})
    assert reader.read("subgraph", selection={}) == result
    assert reader.read("subgraph_contract") == contract(include_recovery=False)
    assert "LLMs may explain" in contract()["description"]


def test_related_neighbourhood_is_bounded_and_preserves_field_focus(catalogue):
    objects = {o["name"]: o for o in catalogue["sources"][0]["objects"]}
    field = objects["Ticket"]["fields"][0]["id"]
    result = subgraph_select(catalogue, {"root": field, "hops": 1, "max_nodes": 2})
    assert result["focus"] == field and len(result["nodes"]) == 2
    assert objects["Ticket"]["id"] in {n["id"] for n in result["nodes"]}
    assert result["partial"] and result["objects_in_scope"] == 4
    assert result["boundary"]["outside_objects"] == 2
    assert result["boundary"]["crossing_edges"] > 0
    complete = subgraph_select(catalogue, {"root": field, "hops": 5})
    assert not complete["partial"] and len(complete["nodes"]) == 4
    assert objects["Unrelated"]["id"] not in {n["id"] for n in complete["nodes"]}


def test_component_continuation_and_selection_errors_have_actionable_contract(catalogue):
    first = subgraph_select(catalogue, {"max_nodes": 1})
    assert first["next_component_offset"] == 1
    second = subgraph_select(catalogue, {"max_nodes": 1, "component_offset": 1})
    assert first["components"] != second["components"]
    for value in [{"root": "invented"}, {"hops": True}, {"max_nodes": 10000},
                  {"component_offset": -1}, {"links": []}, {"approved": True}]:
        with pytest.raises(SelectionError) as refused:
            subgraph_select(catalogue, value)
        error = refused.value.as_dict()
        assert not error["retryable"] and "catalogue" in error["hint"]
        assert error["error"] in {"SUBGRAPH_INPUT", "SUBGRAPH_NOT_FOUND"}
    reader = Reader({"source_schema": catalogue})
    with pytest.raises(SelectionError):
        reader.read("catalog", selection={})


def test_offline_selector_matches_authorised_reader_for_every_catalogue_level(catalogue):
    roots = [None, catalogue['sources'][0]['id']]
    for obj in catalogue['sources'][0]['objects']:
        roots.extend([obj['id'], obj['fields'][0]['id']])
    requests = [{'root': root, 'hops': hops, 'max_nodes': limit}
                for root in roots for hops in [0, 1, 2, 5] for limit in [1, 2, 40]]
    requests += [{'component_offset': offset, 'max_nodes': 1} for offset in [0, 1, 2, 8]]
    requests += [{'root': 'unknown'}, {'hops': True}, {'hops': 1.5}, {'links': []},
                 {'max_nodes': 0}, {'component_offset': -1}, None]
    expected = []
    for request in requests:
        try:
            expected.append(subgraph_select(catalogue, request))
        except SelectionError as error:
            expected.append(error.as_dict())
    script = """
const fs=require('fs'),vm=require('vm');
vm.runInThisContext(fs.readFileSync('app/subgraph.js','utf8'));
const input=JSON.parse(fs.readFileSync(0,'utf8'));
Object.defineProperty(input.schema,'snapshots',{get(){throw new Error('Record access');}});
const result=input.requests.map(selection=>{
 try{return selectSourceSubgraph(input.schema,selection,input.contract);}
 catch(e){return {error:e.code,reason:e.message,recovery:e.hint,hint:e.hint,retryable:e.retryable};}
});
console.log(JSON.stringify(result));
"""
    result = subprocess.run(['node', '-e', script], cwd=Path(__file__).resolve().parents[1],
                            input=json.dumps({'schema': catalogue, 'requests': requests,
                                              'contract': contract()}),
                            capture_output=True, text=True, check=True, timeout=30)
    assert json.loads(result.stdout) == expected


def test_contract_and_export_ignore_python_docstring_indentation(catalogue, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'compiler/subgraph_select.py'
    node = next(n for n in ast.parse(path.read_text(encoding='utf8')).body
                if isinstance(n, ast.FunctionDef) and n.name == 'subgraph_select')
    raw = ast.get_docstring(node, clean=False)
    model = {'source_schema': catalogue}
    before = contract()
    export = app.render(model)
    for doc in [raw, cleandoc(raw)]:
        monkeypatch.setattr(subgraph_select, '__doc__', doc)
        assert contract() == before
        assert app.render(model) == export
        assert SelectionError('SUBGRAPH_INPUT', 'bad request').hint == before['recovery']
