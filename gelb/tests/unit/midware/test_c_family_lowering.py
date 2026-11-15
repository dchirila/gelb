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
