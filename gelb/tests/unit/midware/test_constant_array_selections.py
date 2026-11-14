"""Constant array reads preserve shape, width, bounds and call attribution."""
import math

import pytest

from gelb.compiler_pipeline import PipelineProfile, compile_source
from gelb.gelb_ast.ASTNodes import (
    Array1DLiteral_N, Array2DLiteral_N, ArraySelectionAssignmentStmt_N,
    Identifier_N, RealLiteral_N, RectSelOfArrayElems_N,
    TypePromotionNode_N, VariableDeclarationStmt_N)
from gelb.tests.unit.midware.test_nonfinite_folding import (
    program, _ast, _gauge_value, _unwrapped)
from gelb.utils.exceptions import GeLBException, GeLBExTypeError

ARRAYS = '''global_constants {
    const array[real, 3] W = {1.0, 2.0, 4.0};
    const array[real, {2, 3}] M = {{1.0, 2.0, 3.0}, {4.0, 5.0, 6.0}};
}'''


@pytest.mark.parametrize('bounds', [('', ''), ('0', '2')])
def test_global_slices_fold_before_matrix_intrinsics(bounds):
    lo, hi = bounds
    constants = ARRAYS[:-1] + f'''
        const real total = sum(W[{lo}:{hi}]);
        const real last = W[2:] + 1.0;
        const array[real, 2] tail = W[1:];
        const array[real, 3] row = M[1, :];
        const array[real, {{2, 2}}] sub = M[:, 1:];
        const real det = determinant(sub);
    }}'''
    ast = _ast(program('v = total + last + sum(tail) + sum(row) + det;', globals=constants))
    assert _gauge_value(ast, 'v').value == 30.0
    vals = {s.name.name: _unwrapped(s.value) for s in ast.global_constants.stmts}
    assert isinstance(vals['tail'], Array1DLiteral_N)
    assert isinstance(vals['sub'], Array2DLiteral_N)
    assert vals['sub'].canonical_type.dims == (2, 2)


@pytest.mark.parametrize('expr, expected', [('M[1, 2]', 6.0), ('sum(M[:, 0])', 5.0),
    ('sum(M[1, :])', 15.0), ('sum(W[1:2])', 6.0)])
def test_constant_selection_in_runtime_block(expr, expected):
    assert _gauge_value(_ast(program(f'v = {expr};', globals=ARRAYS)), 'v').value == expected


def test_constant_selection_folds_in_geometry_predicate():
    text = program('v = 0.0;', globals=ARRAYS).replace(
        'nodes[:] = BULK;', 'nodes[:] = BULK; nodes[where real(x) < W[1]] = BULK;')
    predicate = _ast(text).geometry.stmts[-1].predicate
    assert isinstance(predicate.right, RealLiteral_N) and predicate.right.value == 2.0


@pytest.mark.parametrize('dtype, elements, expr, expected', [
    ('int8', '300, 1', 'real(C[0])', 44.0),
    ('int16', '30000, 1', 'real(C[0] + C[1])', 30001.0),
    ('int16', '60000, 1', 'real(C[0])', -5536.0),
    ('real32', '0.1, 2.0', 'real(C[0])', 0.10000000149011612),
    ('bool', 'false, true', 'real(int(C[1]))', 1.0),
])
def test_selection_uses_declared_element_width(dtype, elements, expr, expected):
    constants = f'global_constants {{ const array[{dtype}, 2] C = {{{elements}}}; }}'
    assert _gauge_value(_ast(program(f'v = {expr};', globals=constants)), 'v').value == expected


@pytest.mark.parametrize('profile', list(PipelineProfile))
def test_constant_element_arithmetic_overflow_is_located(profile):
    text = program('int16 k = C[0] + C[0]; v = real(k);',
        globals='global_constants { const array[int16, 2] C = {30000, 1}; }')
    with pytest.raises(GeLBExTypeError, match='integer overflow.*int16') as err:
        compile_source(text, profile)
    assert err.value._source_location() is not None


def test_global_implicit_extent_still_rejected():
    with pytest.raises(GeLBException, match='implicit constant .*Nx.*global constants block'):
        _ast(program('v = 0.0;', globals='global_constants { const int K = Nx; }'))


@pytest.mark.parametrize('dtype, entries, expected', [
    ('real', '1.0, -1.0}, {1.0e-30, 0.0', 1e-30),
    ('real32', '1.0, -1.0}, {1.0e-9, 0.0', 9.999999717180685e-10),
    ('int', '1, 2}, {3, 4', 10),
])
def test_matrix_sum_is_row_major(dtype, entries, expected):
    constants = f'global_constants {{ const array[{dtype}, {{2, 2}}] C = {{{{{entries}}}}}; }}'
    assert _gauge_value(_ast(program('v = real(sum(C));', globals=constants)), 'v').value == expected


def test_matrix_sum_reports_integer_overflow():
    with pytest.raises(GeLBExTypeError, match='overflow'):
        _ast(program('v = real(sum(C));', globals='global_constants { const array[int32, {2, 2}] C = {{2147483647, 1}, {0, 0}}; }'))


@pytest.mark.parametrize('gauge', ['const array[real, 2] b = {0.0, 1.0}; v = 7.0 / b[0];',
                                  'v = S({0.0, 1.0});', 'v = S(R());'])
def test_zero_element_is_a_visible_divisor(gauge):
    text = program(gauge) + 'function S(array[real, 2] a) -> (real r) { r = 7.0 / a[0]; }'
    text += 'function R() -> (array[real, 2] r) { r = {0.0, 1.0}; }'
    with pytest.raises(GeLBException, match='Division by zero') as err:
        _ast(text)
    if 'S(' in gauge:
        assert 'S(' in str(err.value)


def test_carried_array_is_pruned_but_local_constant_and_whole_read_stay():
    ast = _ast(program('const array[real, 2] b = {2.0, 3.0}; v = S(b);') +
               'function S(array[real, 2] a) -> (real r) { r = a[0]; }')
    assert _gauge_value(ast, 'v').value == 2.0
    decls = [s for s in ast.gauges[0].stmts if isinstance(s, VariableDeclarationStmt_N)]
    assert [s.name.name for s in decls] == ['b']
    assert ast.gauges[0].symbol_defs.get_symbol_definition('b').value is decls[0]
    ast = _ast(program('array[real, 3] w = W; v = w[0];', globals=ARRAYS))
    assert isinstance(ast.gauges[0].stmts[0].initial_value, Identifier_N)


@pytest.mark.parametrize('profile', [PipelineProfile.CODEGEN, PipelineProfile.DIAGNOSTICS])
@pytest.mark.parametrize('body', ['v = w[Ix(4)];', 'v = w[Ix(-1)];', 'v = W[Ix(4)];',
    'w[Ix(4)] = 9.0; v = 0.0;', 'v = sum(w[Ix(1):Ix(0)]);',
    'w[Ix(1):Ix(0)] = 9.0; v = 0.0;', 'v = w[Next(1)];', 'v = M[Ix(2), 0];'])
def test_bounds_exposed_by_inlining_are_located(profile, body):
    text = program('array[real, 2] w = {u.in[x | 0], 2.0}; ' + body, globals=ARRAYS)
    text += 'function Ix(int i) -> (int r) { r = i; }\nfunction Next(int i) -> (int r) { int j = i + 1; r = j; }'
    with pytest.raises(GeLBExTypeError, match=r'outside 0\.\.\d+ or reversed') as err:
        compile_source(text, profile)
    assert err.value._source_location() is not None


def test_array_store_remains_a_selection():
    ast = _ast(program('array[real, 2] w = {u.in[x | 0], 2.0}; w[Ix(1)] = 9.0; v = w[0];') +
               'function Ix(int i) -> (int r) { r = i; }')
    [store] = [s for s in ast.gauges[0].stmts if isinstance(s, ArraySelectionAssignmentStmt_N)]
    assert isinstance(store.lhs, RectSelOfArrayElems_N)
    assert store.lhs.element_ranges[0].low.value == 1


@pytest.mark.parametrize('value', ['1.0e300', '-1.0e300', '1.0e200 * 1.0e100', 'exp(1000.0)'])
def test_narrow_overflow_becomes_typed_infinity(value):
    ast = _ast(program(f'real32 a = {value}; v = real(a);'))
    literal = ast.gauges[0].stmts[0].initial_value
    assert isinstance(literal, RealLiteral_N) and math.isinf(literal.value)
    assert literal.canonical_type.dtype == 'real32'


@pytest.mark.parametrize('value', ['0.54', '1.0e30', '1.0e-300'])
def test_finite_narrow_promotion_is_preserved(value):
    ast = _ast(program(f'real32 a = {value}; v = real(a);'))
    assert isinstance(ast.gauges[0].stmts[0].initial_value, TypePromotionNode_N)


@pytest.mark.parametrize('shape, values', [('2', '{1.0e300, 0.54}'),
    ('{2, 2}', '{{1.0e300, 0.54}, {-1.0e300, 1.0e30}}')])
def test_narrow_array_promotion_keeps_finite_leaves(shape, values):
    ast = _ast(program(f'array[real32, {shape}] a = {values}; v = 0.0;'))
    promotion = ast.gauges[0].stmts[0].initial_value
    assert isinstance(promotion, TypePromotionNode_N)
    rows = (promotion.expr.value.elements if isinstance(promotion.expr, Array2DLiteral_N)
            else [promotion.expr])
    for row, sign in zip(rows, (1.0, -1.0)):
        overflow, finite = row.value.elements
        assert overflow.value == math.copysign(math.inf, sign)
        assert overflow.canonical_type.dtype == 'real32'
        assert math.isfinite(finite.value) and finite.canonical_type.dtype == 'real'
