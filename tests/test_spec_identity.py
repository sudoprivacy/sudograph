"""Identity collisions must fail before a definition is lost or data is read."""

import itertools

import pytest

from compiler import cli, gateway, spec
from tools import check_examples


@pytest.mark.parametrize('document', [
    'ontology: First\nontology: Second\ntypes: {}\n',
    'ontology: Example\ntypes: {}\nnodes:\n  Total: {op: "1"}\n  Total: {op: "2"}\n',
    'ontology: Example\ntypes:\n  Item:\n    props:\n      amount: {type: number}\n'
    '      amount: {type: money}\n',
    'ontology: Example\ntypes: {}\nnodes:\n  Total:\n    <<: {op: "1"}\n'
    '    <<: {op: "2"}\n',
])
def test_duplicate_definitions_refused_with_both_locations(tmp_path, document):
    path = tmp_path / 'duplicate.yaml'
    path.write_text(document, encoding='utf8')
    with pytest.raises(spec.SpecError) as error:
        spec.load(str(path))
    message = str(error.value)
    assert 'duplicate key' in message and 'first definition' in message
    assert message.count('line ') == 2
    assert 'keep one definition and reference it' in message


def test_merge_defaults_and_same_property_in_different_objects_remain_valid(tmp_path):
    path = tmp_path / 'defaults.yaml'
    path.write_text('''ontology: Example
types: {}
raw:
  Source: {value: 1, connector: fixture}
nodes:
  First: &defaults {op: "Source", label: First}
  Second: {<<: *defaults, op: "Source + 1", label: Second}
''', encoding='utf8')
    loaded = spec.load(str(path))
    assert loaded.nodes['First']['op'] == 'Source'
    assert loaded.nodes['Second']['op'] == 'Source + 1'
    path.write_text('''ontology: Example
types:
  A: {label: A, id: value, props: {value: {type: number, owner: ontology}}}
  B: {label: B, id: value, props: {value: {type: number, owner: ontology}}}
''', encoding='utf8')
    assert set(spec.load(str(path)).types) == {'A', 'B'}


@pytest.mark.parametrize(
    'blocks', list(itertools.combinations(('raw', 'hooks', 'types', 'nodes'), 2)),
)
def test_graph_identity_cannot_be_defined_in_two_blocks(blocks):
    definitions = {
        'raw': {'label': 'Source', 'connector': 'read-only fixture'},
        'hooks': {'label': 'Gap', 'resolve_when': 'reviewed', 'owner': 'reviewer', 'affects': []},
        'types': {'props': {}},
        'nodes': {'op': '1'},
    }
    kwargs = {block: {'Same': definitions[block]} for block in blocks}
    model = spec.Spec(name='Example', **{'types': {}, **kwargs})
    assert any('identity' in p and 'both' in p for p in spec.check(model))


def test_duplicate_refused_by_cli_gateway_and_example_gate(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'duplicate.yaml'
    path.write_text('ontology: Example\ntypes: {}\nnodes:\n  Total: {op: "1"}\n'
                    '  Total: {op: "2"}\n', encoding='utf8')
    assert cli.main([str(path)]) == 2
    assert 'duplicate key' in capsys.readouterr().err

    class Authority:
        def require(self, *args):
            return 'reader'

    service = gateway.Gateway({'example': gateway.View(str(path))}, Authority())
    for operation in ('graph', 'page', 'query', 'export'):
        with pytest.raises(spec.SpecError, match='duplicate key'):
            service.execute('credential', 'example', operation)

    monkeypatch.setattr(check_examples, 'EXAMPLES', str(tmp_path))
    assert check_examples.main() == 1
    assert 'duplicate key' in capsys.readouterr().err


def test_unsafe_yaml_tags_still_refused(tmp_path):
    path = tmp_path / 'unsafe.yaml'
    path.write_text('ontology: !!python/object:builtins.object {}\ntypes: {}', encoding='utf8')
    with pytest.raises(spec.SpecError, match='invalid YAML'):
        spec.load(str(path))
