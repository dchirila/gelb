"""C-family preparation preserves Stage 2 and registers typed, ordered lifts."""

import copy
import pickle

import pytest
from click.testing import CliRunner

from gelb import compiler_pipeline as pipeline
from gelb.frontend.ASTInvariantValidator import check_c_lowering, check_stage2
from gelb.gelb_ast import ASTNodes as A
from gelb.midware.c_family_lowering import prepare_c_family_ast, lift_matmul_args
from gelb.tests.test_utils import minimal_gelb_program_1d
from gelb.utils.exceptions import GeLBInternalInvariantError


def source(kind='real', body=None):
    body = body or f'''array[{kind}, N] a = {{ {kind}(x), {kind}(1) }};
        array[{kind}, N] r = matmul(M, matmul(M, a + a));
        r = matmul(M, a + a); val = int(r[0]);'''
    return minimal_gelb_program_1d(gauge_content=body) + f'''
        global_constants {{ const int N = 2;
          const array[{kind}, {{2, 2}}] M = {{{{1, 0}}, {{0, 1}}}}; }}
    '''


def stage2(text=None, **options):
    return pipeline.compile_source(text or source(), pipeline.PipelineProfile.CODEGEN,
                                   pipeline.PipelineOptions(**options)).ast


def temps(block):
    return [s for s in block.stmts if isinstance(s, A.VariableDeclarationStmt_N)
            and s.name.name.startswith('gelb_matmul_in_')]


@pytest.mark.parametrize('kind', ['real32', 'int32', 'int', 'real'])
def test_copy_postorder_types_and_symbols(kind):
    ast = stage2(source(kind))
    before = pickle.dumps(ast)
    captures = []
    lowered = prepare_c_family_ast(ast, capture_ast=lambda a, s: captures.append((a, s)))
    assert lowered is not ast and pickle.dumps(ast) == before
    assert pipeline.prepare_c_family_ast is prepare_c_family_ast
    assert 'prepare_c_family_ast' in pipeline.__all__
    assert captures == [(lowered, 'c_lowering')]
    block = lowered.gauges[0]
    lifted = temps(block)
    assert [d.name.name for d in lifted] == [f'gelb_matmul_in_{i}' for i in range(3)]
    assert isinstance(lifted[0].initial_value, A.Add_N)
    assert isinstance(lifted[1].initial_value, A.IntrinsicFunctionCall_N)
    assert lifted[1].initial_value.arguments[1].name == lifted[0].name.name
    for decl in lifted:
        assert decl.data_type.canonical_type.dtype == kind
        assert decl.data_type.canonical_type.dims == (2,)
        assert block.symbol_defs.get_symbol_definition(decl.name.name).value is decl
    check_c_lowering(lowered)
    check_stage2(lowered)
    with pytest.raises(GeLBInternalInvariantError, match='matmul vector'):
        check_c_lowering(ast)
    lifted[1].initial_value.arguments[1].name = 'missing'
    with pytest.raises(GeLBInternalInvariantError, match='matmul vector'):
        check_c_lowering(lowered)


def test_all_blocks_restart_and_avoid_collisions():
    ast = stage2()
    # Exercise identical statements in each executable block, including a
    # lexical name collision, independently of frontend restrictions.
    for block in (ast.initializers[0], ast.dynamics[0]):
        block.stmts = copy.deepcopy(ast.gauges[0].stmts)
        block.symbol_defs = copy.deepcopy(ast.gauges[0].symbol_defs)
    from gelb.midware.BlockMutationHelper import declare_temp
    for block in (ast.initializers[0], ast.dynamics[0], ast.gauges[0]):
        occupied = copy.deepcopy(block.stmts[0])
        occupied.name.name = 'gelb_matmul_in_0'
        declare_temp(block, occupied)
    lift_matmul_args(ast)
    for block in (ast.initializers[0], ast.dynamics[0], ast.gauges[0]):
        assert [d.name.name for d in temps(block)] == [f'gelb_matmul_in_{i}' for i in (1, 2, 3)]


def test_iterative_expression_walk():
    ast = stage2()
    block = ast.gauges[0]
    value = block.stmts[-1].rhs
    for _ in range(2500):
        value = A.Add_N(None, value, A.IntLiteral_N(None, 0))
    block.stmts[-1].rhs = value
    lift_matmul_args(ast)
    assert len(temps(block)) == 3


@pytest.mark.parametrize('profile', list(pipeline.PipelineProfile))
def test_profiles_do_not_prepare_c_ast(profile):
    ast = pipeline.compile_source(source(), profile).ast
    assert not temps(ast.gauges[0])


@pytest.mark.parametrize('backend', ['cpu_highway', 'gpu_cuda_cpp', 'cpu_fortran_serial'])
@pytest.mark.parametrize('stage', ['c_lowering', 'all'])
def test_cli_stage_capture_and_context(tmp_path, monkeypatch, backend, stage):
    import gelb.gelbc as driver
    path = tmp_path / 'p.gelb'
    path.write_text(source())
    captures, contexts = {}, []
    monkeypatch.setattr(driver, 'generate_ast_visualization',
                        lambda ast, *args: captures.update({args[-1]: ast}))
    original = driver.build_backend_context
    def build(result, **kw):
        context = original(result, **kw)
        contexts.append(context)
        return context
    monkeypatch.setattr(driver, 'build_backend_context', build)
    result = CliRunner().invoke(driver.cli, [str(path), '-b', backend,
        '-o', str(tmp_path / 'out'), '--visualize-ast', '--ast-stage', stage])
    if backend == 'cpu_fortran_serial' and stage == 'c_lowering':
        assert result.exit_code == 1 and 'C-family' in result.output
        assert not contexts and not (tmp_path / 'out').exists()
    else:
        assert result.exit_code == 0, result.output
        if backend == 'cpu_fortran_serial':
            assert 'c_lowering' not in captures
            assert contexts[0].ast is captures['midware']
        else:
            assert contexts[0].ast is captures['c_lowering']
            if stage == 'all':
                assert captures['midware'] is not captures['c_lowering']
                assert not temps(captures['midware'].gauges[0])


@pytest.mark.parametrize('report', ['--stencils', '--show-mapping'])
def test_cli_report_rejects_c_lowering(tmp_path, report):
    from gelb.gelbc import cli
    path = tmp_path / 'p.gelb'
    path.write_text(source())
    result = CliRunner().invoke(cli, [str(path), report, '--ast-stage', 'c_lowering'])
    assert result.exit_code == 1 and 'C-family' in result.output
    assert sorted(p.name for p in tmp_path.iterdir()) == ['p.gelb']


@pytest.mark.parametrize('size', [2, 9])
@pytest.mark.parametrize('role', ['slice_store', 'declaration'])
@pytest.mark.parametrize('form', ['bare', 'partial', 'shifted', 'negated', 'cast'])
def test_slice_vector_temporary_has_declared_shape(size, role, form):
    dtype = 'real32' if form == 'cast' else 'real'
    count = size + 2 if form == 'partial' else size
    vector = {
        'bare': 'f.in[x | :]',
        'partial': f'f.in[x | 1:{size}]',
        'shifted': 'f.in[x - 1 | :]',
        'negated': '-f.in[x | :]',
        'cast': 'real32(f.in[x | :])',
    }[form]
    call = f'matmul(M, {vector})'
    body = (f'array[{dtype}, {size}] r = {call}; g.out[x | :] = r;'
            if role == 'declaration' else f'g.out[x | :] = {call};')
    matrix = '{' + ','.join('{' + ','.join(
        '1.0' if i == j else '0.0' for j in range(size)) + '}'
        for i in range(size)) + '}'
    text = f'''simulation_description("slice vector shapes");
        global_constants {{ const array[{dtype}, {{{size}, {size}}}] M = {matrix}; }}
        lattices {{ lattice f(1, {count}, real, 16, true);
                    lattice g(1, {size}, {dtype}, 16, true); }}
        initializer I {{ f.out[x | :] = 1.0; g.out[x | :] = 0.0; }}
        dynamic D {{ {body} }}
        gauge G -> (real p) {{ p = real(g.in[x | 0]); }}
        node_classes {{ node_class B(I, D, G); }}
        geometry {{ nodes[:] = B; }}'''
    ast = stage2(text)
    before = pickle.dumps(ast)
    lowered = prepare_c_family_ast(ast)
    assert pickle.dumps(ast) == before
    block = lowered.dynamics[0]
    [decl] = temps(block)
    assert isinstance(decl.data_type.shape, A.IntLiteral_N)
    assert decl.data_type.shape.value == size
    assert decl.data_type.canonical_type.dtype == dtype
    assert decl.data_type.canonical_type.dims == (size,)
    assert vars(decl.data_type.code_range) == vars(decl.initial_value.inferred_type.code_range)
    assert block.symbol_defs.get_symbol_definition(decl.name.name).value is decl
    check_c_lowering(lowered)
    check_stage2(lowered)


def literal_source(body, *, q=3, dtype='real', gauge='p = f.in[x | 0];'):
    return f'''simulation_description("literal preparation");
    global_constants {{
        const array[real, 2] C = {{2.0, 0.5}};
        const array[real, {{2, 2}}] M = {{{{1.0, 2.0}}, {{0.5, -1.0}}}};
        const array[real, 3] EX = {{0.0, 1.0, -1.0}};
    }}
    lattices {{ lattice f(1, {q}, {dtype}, 64, true);
                lattice h(1, 1, real, 64, true); }}
    initializer I {{ f.out[x | :] = 1.0; h.out[x | :] = 2.0; }}
    dynamic D {{ {body} h.out[x | :] = h.in[x | :]; }}
    gauge G -> (real p) {{ {gauge} }}
    node_classes {{ node_class B(I, D, G); }}
    geometry {{ nodes[:] = B; }}'''


def prepared_unchanged(text, **options):
    ast = stage2(text, **options)
    before = pickle.dumps(ast)
    result = prepare_c_family_ast(ast)
    assert pickle.dumps(ast) == before
    check_c_lowering(result)
    check_stage2(result)
    return ast, result


def value_nodes(root):
    # Independent structural traversal, including type and name slots.
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, A.Node_N):
            yield node
            stack.extend(node.get_children())
        elif isinstance(node, (list, tuple)):
            stack.extend(node)


@pytest.mark.parametrize('expression,size,indices', [
    ('w[1:]', 2, [1, 2]), ('w[0:2]', 3, [0, 1, 2]),
    ('w[:]', 3, [0, 1, 2]), ('2.0 * w[1:]', 2, [1, 2]),
    ('matmul(M, w[1:])', 2, [1, 2]),
])
def test_desugared_slice_elements(expression, size, indices):
    before, after = prepared_unchanged(literal_source(f'''
        array[real, 3] w = f.in[x | :];
        array[real, {size}] u = {expression};
        f.out[x | 0] = u[0]; f.out[x | 1:2] = f.in[x | 1:2];'''))
    with pytest.raises(GeLBInternalInvariantError):
        check_c_lowering(before)
    literals = [n for n in value_nodes(after.dynamics[0]) if isinstance(n, A.Array1DLiteral_N)]
    [literal] = literals
    assert literal.canonical_type.dims == (size,)
    assert [n.element_ranges[0].low.value for n in literal.value] == indices
    assert all(n.canonical_type.is_scalar for n in literal.value)


@pytest.mark.parametrize('lhs', ['w[1]', 'w[0:1]'])
def test_array_store_lhs_and_scalar_reads_untouched(lhs):
    text = literal_source(f'''array[real, 3] w = f.in[x | :];
        {lhs} = 2.0; array[real, 1] w1 = h.in[x | :];
        f.out[x | :] = w[1] + w1[:];''')
    before, after = prepared_unchanged(text)
    assert str(before.dynamics[0]) == str(after.dynamics[0])


@pytest.mark.parametrize('q,lo', [(3, 0), (3, 1), (9, 0)])
def test_literal_stores_are_independent_scalar_directions(q, lo):
    n = q - lo
    literal = '{' + ','.join(f'int(w[{i}])' for i in range(n)) + '}'
    text = literal_source(f'''array[real, {q}] w = f.in[x | :];
        f.out[x | {lo}:{q-1}] = real({literal});''', q=q)
    before, after = prepared_unchanged(text, enable_slice_simplify=False, enable_scalar_cse=False)
    with pytest.raises(GeLBInternalInvariantError, match='Array1DLiteral'):
        check_c_lowering(before)
    stores = [s for s in after.dynamics[0].stmts if isinstance(s, A.LatticeOutSelectionAssignmentStmt_N)
              and s.lhs.lattice_name.name == 'f']
    assert len(stores) == n
    for i, s in enumerate(stores):
        assert s.lhs.canonical_type.is_scalar and s.rhs.canonical_type.is_scalar
        assert s.lhs.element_ranges[-1].low.value == lo + i
        [read] = [v for v in value_nodes(s.rhs) if isinstance(v, A.RectSelOfArrayElems_N)]
        assert read.element_ranges[0].low.value == i
    node_sets = [{id(v) for v in value_nodes(s.rhs)} for s in stores]
    assert all(not a.intersection(b) for i, a in enumerate(node_sets) for b in node_sets[i+1:])


@pytest.mark.parametrize('in_lo,out_lo', [(1, 0), (2, 1), (1, 2)])
def test_literal_store_reads_use_their_own_slice_origin(in_lo, out_lo):
    text = literal_source(f'''f.out[x | {out_lo}:{out_lo + 1}] =
        f.in[x | {in_lo}:{in_lo + 1}] * {{2.0, 3.0}};''', q=5)
    _, after = prepared_unchanged(text, enable_slice_simplify=False, enable_scalar_cse=False)
    stores = [s for s in after.dynamics[0].stmts if isinstance(s, A.LatticeOutSelectionAssignmentStmt_N)
              and s.lhs.lattice_name.name == 'f']
    assert len(stores) == 2
    for offset, stmt in enumerate(stores):
        out_range = stmt.lhs.element_ranges[-1]
        assert out_range.low.value == out_range.high.value == out_lo + offset
        [read] = [v for v in value_nodes(stmt.rhs) if isinstance(v, A.RectSelOfLatticeInDFs_N)]
        in_range = read.element_ranges[-1]
        assert in_range.low.value == in_range.high.value == in_lo + offset
        assert read.canonical_type.is_scalar


def test_synthetic_one_direction_full_slice():
    from gelb.midware.c_family_lowering import expand_literal_slice_stores
    from gelb.frontend.ASTInvariantValidator import canonicalize_types
    ast = stage2(literal_source('f.out[x | :] = f.in[x | :];', q=1))
    stmt = ast.dynamics[0].stmts[0]
    values = A.List_N(stmt.code_range)
    values.append(copy.deepcopy(stmt.rhs))
    stmt.rhs = A.Array1DLiteral_N(stmt.code_range, values)
    array_type = A.ArrayDataType_N(stmt.code_range, 'real', A.IntLiteral_N(stmt.code_range, 1))
    stmt.rhs.inferred_type = array_type
    stmt.lhs.inferred_type = copy.deepcopy(array_type)
    stmt.lhs.element_ranges[-1] = A.Range_N(stmt.code_range, None, None)
    expand_literal_slice_stores(ast)
    canonicalize_types(ast)
    check_c_lowering(ast)
    check_stage2(ast)
    stmt = ast.dynamics[0].stmts[0]
    assert stmt.lhs.canonical_type.is_scalar
    assert stmt.lhs.element_ranges[-1].low.value == 0


@pytest.mark.parametrize('call,q', [('matmul(M, w)', 2), ('bounce_back_dfs(f, x, EX)', 3)])
def test_store_call_is_registered_before_scalar_stores(call, q):
    literal = '{' + ','.join(f'w[{i}]' for i in range(q)) + '}'
    _, after = prepared_unchanged(literal_source(f'''array[real, {q}] w = f.in[x | :];
        real gelb_tmp_0 = 1.0;
        f.out[x | :] = {call} + {literal} * gelb_tmp_0;''', q=q))
    block = after.dynamics[0]
    [decl] = [s for s in block.stmts if isinstance(s, A.VariableDeclarationStmt_N)
              and s.name.name == 'gelb_tmp_1']
    assert decl.initial_value.function_name == call.split('(')[0]
    assert isinstance(decl.data_type.shape, A.IntLiteral_N) and decl.data_type.shape.value == q
    assert block.symbol_defs.get_symbol_definition('gelb_tmp_1').value is decl
    stores = [s for s in block.stmts if isinstance(s, A.LatticeOutSelectionAssignmentStmt_N)
              and s.lhs.lattice_name.name == 'f']
    for i, stmt in enumerate(stores):
        [read] = [v for v in value_nodes(stmt.rhs) if isinstance(v, A.RectSelOfArrayElems_N)
                  and v.array_name.name == 'gelb_tmp_1']
        assert read.element_ranges[0].low.value == i
        assert block.stmts.elements.index(decl) < block.stmts.elements.index(stmt)


def test_scalar_reductions_singletons_globals_and_store_conversion():
    text = literal_source('''array[real, 2] w = f.in[x | :];
        f.out[x | :] = C * {h.in[x | :], dot_prod(C, w)} + sum(w);''', q=2)
    _, after = prepared_unchanged(text)
    stores = [s for s in after.dynamics[0].stmts if isinstance(s, A.LatticeOutSelectionAssignmentStmt_N)
              and s.lhs.lattice_name.name == 'f']
    coercions = [v for v in value_nodes(stores[0].rhs)
                 if isinstance(v, A.TypePromotionNode_N) and v.is_singleton_coercion()]
    assert len(coercions) == 1
    for stmt in stores:
        for call in value_nodes(stmt.rhs):
            if isinstance(call, A.IntrinsicFunctionCall_N) and call.function_name in ('sum', 'dot_prod'):
                assert all(isinstance(a, A.Identifier_N) and a.canonical_type.is_array for a in call.arguments)
    _, narrow = prepared_unchanged(literal_source('''int k = x + 18014399583223809;
        f.out[x | :] = {k, 7};''', q=2, dtype='real32'))
    for stmt in narrow.dynamics[0].stmts:
        if isinstance(stmt, A.LatticeOutSelectionAssignmentStmt_N) and stmt.lhs.lattice_name.name == 'f':
            assert stmt.lhs.canonical_type.dtype == 'real32'
            assert stmt.rhs.canonical_type.dtype in ('int', 'real32')
            assert all(n.canonical_type is None or n.canonical_type.dtype != 'real'
                       for n in value_nodes(stmt.rhs))


@pytest.mark.parametrize('body', [
    'real s = sum({w[0], 2.0});', 'real s = sum(w[1:]);', 'real s = sum(2.0 * w[1:]);',
    'array[real, 3] u = upstream_dfs(f, x, EX) + {1.0, 2.0, 3.0};',
    'array[real, 3] u; u = upstream_dfs(f, x, EX) + {1.0, 2.0, 3.0};',
    'w[0:1] = w[1:];', 'w[0:1] = {w[2], 2.0};',
])
def test_unsupported_inline_literals_are_located(body):
    from gelb.utils.exceptions import GeLBExTypeError
    ast = stage2(literal_source(f'array[real, 3] w = f.in[x | :];\n{body}\nf.out[x | :] = w;'))
    before = pickle.dumps(ast)
    with pytest.raises(GeLBExTypeError) as error:
        prepare_c_family_ast(ast)
    line, col = error.value._source_location()
    assert line > 0 and col >= 0
    assert 'local array[...] variable' in error.value.hint
    assert pickle.dumps(ast) == before


def test_multidimensional_syntax_rows_are_not_value_literals():
    before, after = prepared_unchanged(literal_source('''array[real, 3] w = f.in[x | :];
        array[real, {2, 2}] m = {{w[0], 1.0}, {2.0, w[1]}};
        f.out[x | :] = w;'''))
    assert str(after.dynamics[0]) == str(before.dynamics[0])


def test_preparation_walks_deep_expression_iteratively():
    from gelb.midware.c_family_lowering import desugar_local_array_slices, expand_literal_slice_stores
    ast = stage2(literal_source('array[real, 3] w = f.in[x | :]; f.out[x | 1:2] = w[1:];'))
    stmt = ast.dynamics[0].stmts[1]
    for _ in range(2500):
        node = A.Add_N(stmt.code_range, stmt.rhs, A.RealLiteral_N(stmt.code_range, 0.0))
        node.inferred_type = stmt.rhs.inferred_type
        stmt.rhs = node
    # Only the traversal is under test; deepcopy itself is Python-recursive.
    desugar_local_array_slices(ast)
    with pytest.raises(GeLBInternalInvariantError, match='Array1DLiteral'):
        check_c_lowering(ast)
