"""Exercise the compiler against real source tables, including unloaded facts."""

import copy
import sqlite3

import pytest
import yaml

from compiler import app, bind, cli, diff, expr, measure, spec
from compiler.compile import compile_spec


def source_prop(column, kind='number', **extra):
    return {'type': kind, 'owner': 'source', 'column': column, **extra}


@pytest.fixture
def shop(tmp_path):
    db = tmp_path / 'shop.db'
    with sqlite3.connect(db) as c:
        c.executescript('''
            CREATE TABLE Category (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE Product (id INTEGER PRIMARY KEY, category INTEGER REFERENCES Category(id));
            CREATE TABLE Line (ord INTEGER, product INTEGER REFERENCES Product(id),
                               price NUMERIC, qty INTEGER, discount NUMERIC, market TEXT,
                               PRIMARY KEY (ord, product));
            INSERT INTO Category VALUES (1, 'Drinks'), (2, 'Food'), (3, 'Empty');
            INSERT INTO Product VALUES (10, 1), (11, 1), (20, 2);
            INSERT INTO Line VALUES (1, 10, 10, 2, 0, 'A'), (1, 11, 10, 1, 0.1, 'A'),
                                    (2, 20, 5, 4, 0, 'B'), (3, 10, 4, 1, 0, 'B');
        ''')
    doc = {
        'ontology': 'Shop', 'dimensions': ['market'],
        'raw': {'R': {'dsn': 'sqlite:///shop.db'}},
        'types': {
            'Category': {'label': 'Category', 'backing': {'from': 'R', 'table': 'Category',
                                                        'key': ['id']},
                         'props': {'id': source_prop('id'), 'name': source_prop('name', 'string'),
                                   'sales': {'type': 'money', 'scale': 2,
                                             'op': 'SELECT SUM(net) FROM Line '
                                                   'WHERE product.category = this'}}},
            'Product': {'label': 'Product', 'backing': {'from': 'R', 'table': 'Product',
                                                       'key': ['id']},
                        'props': {'id': source_prop('id'),
                                  'category': source_prop('category', 'ref', to='Category')}},
            'Line': {'label': 'Line', 'backing': {'from': 'R', 'table': 'Line',
                                                 'key': ['ord', 'product']},
                     'dimensions': {'market': 'market'},
                     'props': {'order': source_prop('ord'),
                               'product': source_prop('product', 'ref', to='Product'),
                               'price': source_prop('price', 'money'),
                               'qty': source_prop('qty'), 'discount': source_prop('discount'),
                               'market': source_prop('market', 'string'),
                               'net': {'type': 'money', 'scale': 2,
                                       'op': 'price * qty * (1 - discount)'}}},
        },
        'nodes': {'sales': {'label': 'Sales', 'op': 'SELECT SUM(net) FROM Line'},
                  'categories': {'label': 'Categories', 'op': 'SELECT SUM(sales) FROM Category'}},
        'checks': {'rollup': 'sales = categories'},
    }
    path = tmp_path / 'shop.yaml'

    def load(change=None):
        selected = copy.deepcopy(doc)
        if change:
            change(selected)
        path.write_text(yaml.safe_dump(selected), encoding='utf-8')
        return spec.load(str(path))

    return load, db, path


def test_relationship_rollup_works_for_loaded_and_unloaded_facts(shop, monkeypatch):
    load, _, _ = shop
    s = load()
    c = compile_spec(s)
    assert c.passed, c.checks
    assert c.values == {'sales': 53, 'categories': 53}
    assert [r['sales'] for r in c.rows['Category']] == [33, 20, 0]
    monkeypatch.setattr(bind, 'MAX_ROWS', 3)
    s = load()
    assert s.unloaded == {'Line': 4}
    for at, expected in (({}, [33, 20, 0]), ({'market': 'A'}, [29, 0, 0])):
        c = compile_spec(s, at=at)
        assert c.passed, c.checks
        assert [r['sales'] for r in c.rows['Category']] == expected
        assert c.values['sales'] == c.values['categories'] == sum(expected)
    assert 'Line' not in c.rows, 'aggregate pushdown must not fetch the large fact table'
    assert any(e['from'] == 'R' and e['to'] == 'Line' and e['rel'] == 'supplies'
               for e in c.view['edges']), 'unfetched facts still have a source'


@pytest.mark.parametrize('func,expected', [('avg', 13.25), ('min', 4), ('max', 20)])
def test_standard_aggregates_agree_between_routes_and_empty_sets(shop, func, expected):
    load, _, _ = shop
    def change(d):
        d['nodes']['probe'] = {'op': f'SELECT {func}(net) FROM Line'}
    s = load(change)
    c = compile_spec(s)
    assert c.values['probe'] == expected
    run = measure.correctness(s)
    assert run.score()[0] == run.score()[1], run.as_dict()
    assert not any(r.id == 'partition/probe' for r in run.results)
    empty = expr.parse(f'SELECT {func}(net) FROM Line WHERE qty < 0')
    assert bind.aggregate(s, empty, s.source_base) is None


def test_unknown_refs_and_composite_targets_refuse_instead_of_fanning_out(shop):
    load, _, _ = shop
    s = load()
    for sql in ['SELECT SUM(net) FROM Line WHERE qty.category = 1',
                'SELECT SUM(net) FROM Line WHERE product.missing = 1']:
        with pytest.raises((expr.ExprError, bind.NotPushable), match=r'ref|property'):
            bind.aggregate(s, expr.parse(sql), s.source_base)


def test_unloaded_dangling_refs_are_reported_without_dropping_the_fact(shop, monkeypatch):
    load, db, _ = shop
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO Line VALUES (4, 999, 7, 1, 0, 'A')")
    monkeypatch.setattr(bind, 'MAX_ROWS', 3)
    c = compile_spec(load())
    assert c.values['sales'] == 60
    assert not c.passed
    failure = next(k for k in c.checks if k.name == 'link/Line/product')
    assert failure.affected == 1 and failure.sample == ['4·999']
    assert not next(k for k in c.checks if k.name == 'articulation/rollup').ok


def test_bound_hook_owner_resolves_against_real_rows(shop):
    load, _, _ = shop
    def change(d):
        d['hooks'] = {'H': {'owner': 'Product/10', 'resolve_when': 'reviewed',
                            'affects': ['sales']}}
    assert load(change).hooks['H']['owner'] == 'Product/10'
    def invalid(d):
        change(d)
        d['hooks']['H']['owner'] = 'Product/999'
    with pytest.raises(spec.SpecError, match='no Product with id'):
        load(invalid)


def test_nonnullable_and_enum_claims_are_checked_against_bound_rows(shop):
    load, db, _ = shop
    with sqlite3.connect(db) as c:
        c.execute('UPDATE Line SET market = NULL WHERE ord = 2')
    with pytest.raises(spec.SpecError, match='not nullable'):
        load()
    def change(d):
        d['types']['Line']['props']['market'].update(type='enum', values=['A'], nullable=True)
    with pytest.raises(spec.SpecError, match='declared enum'):
        load(change)


def test_bound_decision_without_storage_gets_the_right_recovery_advice(shop):
    load, _, _ = shop
    def change(d):
        d['types']['Product']['props']['approved'] = {'type': 'bool', 'owner': 'ontology'}
    with pytest.raises(spec.SpecError, match='related ontology-owned type'):
        load(change)


def test_backed_readings_and_bridge_already_have_a_working_path(shop):
    load, _, _ = shop
    def change(d):
        d['bases'] = ['all', 'market A']
        d['nodes'] = {'sales': {'label': 'Sales',
                               'op@all': 'SELECT SUM(net) FROM Line',
                               'op@market A': "SELECT SUM(net) FROM Line WHERE market = 'A'",
                               'because': 'R', 'entry': {}}}
        d['checks'] = {}
    s = load(change)
    result = diff.diff(s, 'all', 'market A')
    assert result.explained and result.entries[0].amount == -24


def test_generated_measurements_travel_with_the_view_and_its_slice(shop):
    load, _, path = shop
    s = load()
    b = app.bundle(s)
    whole = b['views']['|']['measurement']
    sliced = b['views']['|market=A']['measurement']
    assert whole['gates'] is False
    assert next(r for r in whole['results'] if r['id'] == 'routes/categories')['got'] == 53
    assert next(r for r in sliced['results'] if r['id'] == 'routes/categories')['got'] == 29
    assert cli.main([str(path), '--at', 'market=A', '--measure']) == 0


def test_sql_parser_cannot_expand_the_execution_surface():
    for source in ['DELETE FROM x', 'SELECT load_extension(x) FROM T',
                   'SELECT COUNT(*) FROM T; DELETE FROM T',
                   'SELECT SUM(x) FROM T JOIN U ON T.id = U.id',
                   "__import__('os').system('x')"]:
        with pytest.raises(expr.ExprError):
            expr.parse(source)


def test_dependencies_follow_used_properties_and_names_inside_filters(shop):
    load, _, _ = shop
    def change(d):
        d['nodes']['threshold'] = {'op': 'SELECT MIN(qty) FROM Line'}
        d['nodes']['selected'] = {'op': 'SELECT SUM(net) FROM Line WHERE qty > threshold'}
        # This depends on the aggregate, but the aggregate does not read this
        # column. Depending on every computed column invents a cycle.
        d['types']['Line']['props']['share'] = {'type': 'number', 'op': 'net / sales'}
    s = load(change)
    c = compile_spec(s)
    assert c.passed and c.values['selected'] == 40
    selected = next(n for n in c.view['nodes'] if n['id'] == 'selected')
    assert selected['lineage']['inputs'] == ['threshold']


def test_computed_values_cannot_also_claim_a_source_column(shop):
    load, _, _ = shop
    def change(d):
        d['types']['Line']['props']['net']['column'] = 'price'
    with pytest.raises(spec.SpecError, match="drop 'column'"):
        load(change)


def test_money_rounds_decimal_half_cents_the_same_in_sql_and_rows(shop, monkeypatch):
    load, db, _ = shop
    with sqlite3.connect(db) as c:
        c.execute('UPDATE Line SET price = 0.35, qty = 1, discount = 0.1')
    s = load()
    compiled = compile_spec(s)
    assert [r['net'] for r in compiled.rows['Line']] == [0.32] * 4
    assert compiled.values['sales'] == 1.28
    assert measure.correctness(s).score()[0] == measure.correctness(s).score()[1]
    monkeypatch.setattr(bind, 'MAX_ROWS', 3)
    assert compile_spec(load()).values['sales'] == 1.28


def test_null_boolean_semantics_match_sqlite():
    for source in ['NOT (x > 0)', '(x > 0) OR (y > 0)', '(x > 0) AND (y > 0)']:
        ast = expr.parse(source)
        with sqlite3.connect(':memory:') as conn:
            for x in (None, -1, 1):
                for y in (None, -1, 1):
                    expected = conn.execute(f'SELECT {source} FROM (SELECT ? x, ? y)',
                                            [x, y]).fetchone()[0]
                    assert expr.evaluate(ast, {'x': x, 'y': y}, {}) == expected
