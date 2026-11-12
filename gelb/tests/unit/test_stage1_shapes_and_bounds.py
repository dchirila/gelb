"""Declaration scopes, concrete shapes, and constant selection boundaries."""

import pytest

from gelb.compiler_pipeline import compile_source, PipelineOptions, PipelineProfile
from gelb.frontend.ASTInvariantValidator import _walk
from gelb.gelb_ast import ASTNodes as A
from gelb.midware.ast_eval import eval_const_expr
from gelb.midware.ast_simplify import hoist_common_subtrees
from gelb.tests.integration.test_refactor_defect_probes import source
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_2d, minimal_gelb_program_3d
from gelb.utils.exceptions import GeLBExSyntaxError, GeLBExSymbolRefBeforeDef, GeLBExTypeError


@pytest.mark.parametrize('profile', list(PipelineProfile))
@pytest.mark.parametrize('scope', ['initializer', 'dynamic', 'gauge', 'constant',
                                  'input', 'output', 'function', 'gauge_output'])
def test_global_constant_names_are_reserved(profile, scope):
    kwargs = {'constants': 'const real S = 2.0;'}
    if scope == 'initializer':
        kwargs['init'] = 'real S = 1.0; u.out[x | :] = S;'
    elif scope in ('dynamic', 'constant'):
        kwargs['dynamic'] = ('const ' if scope == 'constant' else '') + 'real S = 1.0; u.out[x | :] = S;'
    elif scope == 'gauge':
        kwargs['gauge'] = 'real S = 1.0; v = S;'
    elif scope == 'gauge_output':
        kwargs.update(outputs='real S', gauge='S = 1.0;')
    else:
        kwargs['functions'] = {
            'input': 'function F(real S) -> (real r) { r = S; }',
            'output': 'function F(real a) -> (real S) { S = a; }',
            'function': 'function F(real a) -> (real r) { real S = a; r = S; }',
        }[scope]
    with pytest.raises(GeLBExSyntaxError, match='S.*global_constants') as error:
        compile_source(source(**kwargs), profile)
    assert error.value._source_location()[0] > 0
    assert 'constant is defined on line' in error.value.hint


@pytest.mark.parametrize('profile', list(PipelineProfile))
def test_late_constants_and_unrelated_local_names(profile):
    text = source('real u = 3.0; v = F(u);',
                  functions='function F(real a) -> (real r) { r = a + K; }')
    compile_source(text + 'global_constants { const real K = 2.0; }', profile)


@pytest.mark.parametrize('text', [
    source(constants='const int B = A + 1; const int A = 2;'),
    source('real b = a; real a = 2.0; v = b;'),
])
def test_local_reference_before_definition_is_still_rejected(text):
    with pytest.raises(GeLBExSymbolRefBeforeDef):
        compile_source(text, PipelineProfile.DIAGNOSTICS)


@pytest.mark.parametrize('value,defines', [('0', ()), ('-4', ()), ('4', ('N=0',))])
def test_named_grid_extent_is_validated(value, defines):
    text = minimal_gelb_program_2d(global_constants_content=f'const int N = {value};')
    with pytest.raises(GeLBExTypeError):
        compile_source(text, PipelineProfile.DIAGNOSTICS, PipelineOptions(defines=defines))


@pytest.mark.parametrize('kind,value', [('bool', 'true'), ('int', '1')])
def test_lattice_parameter_elements_resolve(kind, value):
    text = minimal_gelb_program_2d(global_constants_content=f'const int N = 4; const {kind} P = {value};')
    text = text.replace('{N, N}', '{2*N, N+1}').replace('{false, false}', '{P, P}')
    ast = get_typed_ast(text)
    lattice = ast.lattices.stmts[0]
    assert [eval_const_expr(x) for x in lattice.grid_size.value] == [8, 5]
    assert all(isinstance(x, (A.BoolLiteral_N, A.IntLiteral_N)) for x in lattice.periodicity.value)


@pytest.mark.parametrize('extent', ['0', '-1', '1/0', '2.0', 'n'])
def test_invalid_extent_is_rejected_before_use(extent):
    with pytest.raises(GeLBExTypeError):
        get_typed_ast(source(f'int n = 2; array[real, {extent}] unused; v = 1.0;'))


@pytest.mark.parametrize('rank', [1, 2, 3, 4])
def test_constant_array_indices_resolve_shapes(rank):
    literal = '{2, 3}'
    for _ in range(rank - 1):
        literal = '{' + literal + ', ' + literal + '}'
    shape = '2' if rank == 1 else '{' + ', '.join(['2'] * rank) + '}'
    index = ', '.join(['0'] * (rank - 1) + ['1'])
    ast = get_typed_ast(source(f'array[real, SZ[{index}]] a = {{1.0, 2.0, 3.0}}; v = a[0];',
                              constants=f'const array[int, {shape}] SZ = {literal};'))
    assert ast.gauges[0].stmts[0].data_type.shape.value == 3


@pytest.mark.parametrize('index', ['-1', '3', '2:1'])
def test_constant_bounds_are_checked(index):
    with pytest.raises(GeLBExTypeError):
        get_typed_ast(source(f'array[real, 3] a; v = a[{index}];'))


def test_bounds_fold_before_scalar_classification_and_calls_stay_deferred():
    ast = get_typed_ast(source('const int I = 2; array[real, 3] a; v = a[I:1+1] + a[F(5)];',
                              functions='function F(int i) -> (int r) { r = i; }'))
    selections = [n for n, _, _, _ in _walk(ast) if isinstance(n, A.RectSelOfArrayElems_N)]
    assert all(n.canonical_type.is_scalar for n in selections)
    assert any(isinstance(n.element_ranges[0].low, A.UserFunctionCall_N) for n in selections)
    folded = next(n for n in selections if isinstance(n.element_ranges[0].low, A.IntLiteral_N))
    assert folded.element_ranges[0].low.value == folded.element_ranges[0].high.value == 2


@pytest.mark.parametrize('selection,array', [('Z:', True), (':', True), ('Z', False), ('Z:Z', False), (':Z', False)])
def test_single_df_slice_rank(selection, array):
    ast = get_typed_ast(source(f'v = u.in[x | {selection}];', constants='const int Z = 0;'))
    assert ast.gauges[0].stmts[0].rhs.canonical_type.is_array == array


@pytest.mark.parametrize('shape', ['2', '{1, 1}'])
def test_non_scalar_literal_element_has_its_own_error(shape):
    with pytest.raises(GeLBExTypeError, match='Non-scalar array element'):
        get_typed_ast(source(f'array[real, {shape}] a; array[real, 2] b = {{a, 1.0}}; v = b[0];'))


def test_width_aware_local_shapes_and_late_function_signature():
    text = source('const real32 K = 16777217; array[int, int(K)-16777214] a = F(3); v = real(a[0]);',
                  functions='function F(int z) -> (array[int, Q] r) { r = {z, z}; }')
    ast = get_typed_ast(text + 'global_constants { const int Q = 2; }')
    assert ast.gauges[0].stmts[1].data_type.shape.value == 2
    assert ast.functions[0].outputs[0].data_type.shape.value == 2


@pytest.mark.parametrize('dimension', ['Nx', 'Ny', 'Nz'])
@pytest.mark.parametrize('bounds,lo,hi', [('{d}-2', 2, 2), ('0:{d}-3', 0, 1), ('{d}-3:', 1, 2)])
def test_written_grid_bounds_and_synthesized_open_high(dimension, bounds, lo, hi):
    text = minimal_gelb_program_3d(global_constants_content='const int N = 4;',
        gauge_content=f'array[int, 3] w = {{1, 2, 3}}; array[int, {hi-lo+1}] a = w[{bounds.format(d=dimension)}]; val = a[0];')
    ast = get_typed_ast(text)
    selection = next(n for n, _, _, _ in _walk(ast)
                     if isinstance(n, A.RectSelOfArrayElems_N) and n.array_name.name == 'w')
    assert (selection.element_ranges[0].low.value, selection.element_ranges[0].high.value) == (lo, hi)


@pytest.mark.parametrize('profile', list(PipelineProfile))
@pytest.mark.parametrize('bound', ['i', '0:i', 'ID(i)'])
def test_function_input_array_bounds_remain_rejected(profile, bound):
    text = source('v = F(x);', functions=f'''
        function ID(int a) -> (int r) {{ r = a; }}
        function F(int i) -> (real r) {{ array[real, 3] w = {{1.0, 2.0, 3.0}}; r = w[{bound}]; }}''')
    with pytest.raises(GeLBExTypeError, match='must be compile-time evaluable') as error:
        compile_source(text, profile)
    assert "'i' is not a compile-time constant" in error.value.hint
    assert error.value._source_location()[0] > 0


@pytest.mark.parametrize('index', [-1, 2])
@pytest.mark.parametrize('scope', ['global', 'local'])
def test_constant_array_extent_indices_do_not_wrap(index, scope):
    declaration = f'const array[real, SZ[{index}]] a = {{1.0, 2.0, 3.0}};'
    constants = 'const array[int, 2] SZ = {2, 3};'
    text = source('v = a[0];' if scope == 'global' else declaration + 'v = a[0];',
                  constants=constants + (declaration if scope == 'global' else ''))
    with pytest.raises(GeLBExTypeError, match='array shape') as error:
        get_typed_ast(text)
    assert error.value._source_location()[0] > 0


def test_cse_keeps_singleton_array_arithmetic_inside_scalar_coercions():
    ast = get_typed_ast(source('array[real, 1] a = u.in[x | :]; array[real, 2] b = {2.0*a, 2.0*a}; v = b[0];'))
    elements = [n for n, _, _, _ in _walk(ast)
                if isinstance(n, A.TypePromotionNode_N) and n.is_singleton_coercion()]
    assert len(elements) == 2
    temps, rewritten = hoist_common_subtrees(elements, lambda i: f'tmp_{i}')
    assert all(body.canonical_type.is_scalar for _, body in temps)
    assert all(node.canonical_type.is_scalar for node in rewritten)


def test_empty_synthetic_array_literal_has_a_type_error():
    from gelb.frontend.TypeInferenceVisitor import TypeInferenceVisitor
    with pytest.raises(GeLBExTypeError, match='Array literal cannot be empty'):
        TypeInferenceVisitor().visitArray1DLiteral_N(A.Array1DLiteral_N(None, A.List_N(None)), None)
