"""Structured coordinates preserve symbolic spelling and resolve bound axes."""

import pytest

from gelb.backends.highway.addressing import (
    AxisOffset, ConstCoord, ExprCoord, LatticeAddress,
)
from gelb.backends.stage3_backend_cpu_highway import HighwayCodeGenerator
from gelb.compiler_pipeline import (
    PipelineOptions, PipelineProfile, compile_source, build_backend_context,
)
from gelb.gelb_ast import ASTNodes as A


def generator(periodic=True, reach=2):
    source = f"""
    simulation_description("addresses");
    global_constants {{ const array[int, 3] EX = {{0, {reach}, {-reach}}}; }}
    lattices {{ lattice f(1, 3, real, 64, {str(periodic).lower()}); }}
    initializer I {{ f.out[x | :] = 1.0; }}
    dynamic D {{ f.out[x | :] = bounce_back_dfs(f, x, EX); }}
    gauge G -> (real val) {{ val = sum(f.in[x | :]); }}
    node_classes {{ node_class B(I, D, G); }}
    geometry {{ nodes[:] = B; }}
    """
    result = compile_source(source, PipelineProfile.CODEGEN,
                            PipelineOptions(require_stencils=True, require_geometry=True))
    return HighwayCodeGenerator(result.ast, backend_context=build_backend_context(result),
                                 storage_layout='soa')


@pytest.mark.parametrize('layout,expected', [
    ('soa', '[2][(g_y) + 1][((g_x + (-1))) + 1]'),
    ('aos', '[(g_y) + 1][((g_x + (-1))) + 1][2]'),
    ('cbt', '[(g_y) + 1][(((g_x + (-1))) + 1) / 8][2][(((g_x + (-1))) + 1) % 8]'),
])
def test_symbolic_storage_spelling(layout, expected):
    addr = LatticeAddress('f', 'g_f_old', (AxisOffset('x', -1), AxisOffset('y')), '2', layout)
    assert addr.subscript() == expected
    assert str(addr) == 'g0_1_f_storage[g_f_old]' + expected


@pytest.mark.parametrize('layout,expected', [
    ('soa', '[2][1][248]'), ('aos', '[1][248][2]'), ('cbt', '[1][31][2][0]'),
])
def test_bound_storage(layout, expected):
    addr = LatticeAddress('f', 'buf', (ConstCoord(247), ConstCoord(0)), '2', layout)
    assert addr.subscript() == expected


def test_tile_alignment_is_structural():
    addr = LatticeAddress('f', 'buf', (AxisOffset('x'),), '2', 'cbt')
    assert addr.subscript() == '[((g_x) + 1) / 8][2][((g_x) + 1) % 8]'
    assert addr.aligned().subscript() == '[((g_x) + 1) / 8][2][0]'
    const = LatticeAddress('f', 'buf', (ConstCoord(9),), '2', 'cbt')
    assert const.subscript() == '[1][2][2]'
    assert const.aligned().subscript() == '[1][2][0]'
    assert ExprCoord('some_index()').storage() == '(some_index()) + 1'


@pytest.mark.parametrize('offset', [-65, -2, -1, 1, 2, 65])
@pytest.mark.parametrize('write', [False, True])
def test_bound_periodic_wrap(offset, write):
    gen = generator()
    gen._axis_bindings = {'x': 0}
    coord = gen._coordinate(A.Identifier_N(None, 'x'), 0, offset, for_write=write)
    assert coord == ConstCoord(offset % 64)


@pytest.mark.parametrize('start,offset,target', [(0, -2, 0), (0, -1, 0), (63, 2, 63), (3, -2, 1)])
def test_bound_nonperiodic_clamp(start, offset, target):
    gen = generator(False)
    gen._axis_bindings = {'x': start}
    assert gen._coordinate(A.Identifier_N(None, 'x'), 0, offset) == ConstCoord(target)


def test_nested_scopes_restore_and_hide_bindings():
    gen = generator()
    gen._emit_axis_loop_open('x', 0, 0)
    assert gen._emit_expression(A.Identifier_N(None, 'x')) == '0LL'
    gen._emit_axis_loop_open('x', 7, 7)
    assert gen._axis_bindings == {'x': 7}
    gen._emit_axis_loop_close()
    assert gen._axis_bindings == {'x': 0}
    gen._emit_axis_loop_open('x', 1, 8)
    assert gen._axis_bindings == {}
    gen._emit_axis_loop_close()
    assert gen._axis_bindings == {'x': 0}
    gen._emit_axis_loop_close()
    assert gen._axis_bindings == {}
    gen._emit_axis_loop_open('x', 9, 9)
    assert gen._axis_bindings == {'x': 9}
    gen._emit_axis_loop_close()


@pytest.mark.parametrize('start,df,expected', [(0, '2', '[1][1]'), (63, '1', '[2][64]'), (3, '2', '[1][2]')])
def test_bound_bounce_guard(start, df, expected):
    gen = generator(False)
    gen._axis_bindings = {'x': start}
    call = A.IntrinsicFunctionCall_N(None, 'bounce_back_dfs',
            [A.Identifier_N(None, 'f'), A.Identifier_N(None, 'x'), A.Identifier_N(None, 'EX')])
    text = gen._emit_intrinsic_bounce_back_dfs(call, df)
    assert text == 'g0_1_f_storage[g0_1_f_old]' + expected
    assert '?' not in text


def test_gauge_uses_bound_coordinate():
    gen = generator()
    gen._axis_bindings = {'x': 7}
    gauge = gen.backend_context.ast.gauges[0]
    gen._emit_gauge_buffer_fill(gauge)
    assert any('gelb_buf_val[7]' in line for line in gen._lines)


@pytest.mark.parametrize('start,df,expected', [(0, '2', '[1][1]'), (63, '1', '[2][64]'), (3, '2', '[1][3]')])
def test_bound_bounce_one_cell(start, df, expected):
    gen = generator(False, reach=1)
    gen._axis_bindings = {'x': start}
    call = A.IntrinsicFunctionCall_N(None, 'bounce_back_dfs',
            [A.Identifier_N(None, 'f'), A.Identifier_N(None, 'x'), A.Identifier_N(None, 'EX')])
    assert gen._emit_intrinsic_bounce_back_dfs(call, df) == 'g0_1_f_storage[g0_1_f_old]' + expected


def test_symbolic_wrap_clamp_and_upstream_spelling():
    node = A.Identifier_N(None, 'x')
    periodic = generator()
    assert str(periodic._coordinate(node, 0, -1)) == '(g_x + (-1))'
    assert str(periodic._coordinate(node, 0, 1, subtract=True)) == '(g_x - (-1))'
    assert str(periodic._coordinate(node, 0, -1, for_write=True)) == '(((g_x + (-1)) % 64 + 64) % 64)'
    assert str(generator(False)._coordinate(node, 0, -2)) == '((g_x + (-2) < 0) ? 0 : ((g_x + (-2) >= 64) ? 63 : (g_x + (-2))))'


@pytest.mark.parametrize('context', ['initializer', 'dynamic', 'gauge'])
@pytest.mark.parametrize('offset', [-1, -2])
def test_periodic_singleton_accesses_wrap_in_each_block(context, offset):
    read = f'f.in[x + ({offset}) | 0]'
    expressions = {name: read if name == context and context != 'initializer' else '1.0'
                   for name in ('initializer', 'dynamic', 'gauge')}
    write_coord = f'x + ({offset})' if context == 'initializer' else 'x'
    source = f"""
    simulation_description("periodic singleton accesses");
    lattices {{ lattice f(1, 1, real, 64, true); }}
    initializer I {{ f.out[{write_coord} | 0] = {expressions['initializer']}; }}
    dynamic D {{ f.out[x | 0] = {expressions['dynamic']}; }}
    gauge G -> (real val) {{ val = {expressions['gauge']}; }}
    node_classes {{ node_class B(I, D, G); node_class E(I, D, G); }}
    geometry {{ nodes[:] = E; nodes[0:0] = B; nodes[63:63] = B; }}
    """
    result = compile_source(source, PipelineProfile.CODEGEN,
                            PipelineOptions(require_stencils=True, require_geometry=True))
    gen = HighwayCodeGenerator(result.ast, backend_context=build_backend_context(result),
                               storage_layout='soa')
    text = gen.generate()
    block = text.split('{ int64_t g_x = 0;', 1)[1].split('\n  }', 1)[0] if context == 'initializer' else text
    assert f'g0_1_f_storage[g0_1_f_old][0][{offset % 64 + 1}]' in block


def binary(gen, operation, left, right, kind=None):
    expr = operation(None, left, right)
    if kind:
        expr.inferred_type = A.ArrayDataType_N(None, kind, [])
    return gen._emit_expression(expr)


@pytest.mark.parametrize('operation,expected', [(A.Add_N, '1'), (A.Sub_N, '(-1)'), (A.Mul_N, '0')])
def test_untyped_integer_operands_stay_integer(operation, expected):
    gen = generator()
    assert binary(gen, operation, A.IntLiteral_N(None, 0), A.IntLiteral_N(None, 1)) == expected


def test_large_integer_expression_is_not_rounded():
    gen = generator()
    text = binary(gen, A.Add_N, A.IntLiteral_N(None, 9007199254740993), A.IntLiteral_N(None, 2))
    assert text == '(9007199254740993 + 2)'
    assert binary(gen, A.Add_N, A.IntLiteral_N(None, 9007199254740993),
                  A.IntLiteral_N(None, 2), 'int') == '(9007199254740993LL + 2LL)'
    assert binary(gen, A.Mul_N, A.IntLiteral_N(None, 0), A.Identifier_N(None, 'x'), 'int') == '0LL'


def test_integer_zero_keeps_random_draw():
    gen = generator()
    call = A.IntrinsicFunctionCall_N(None, 'random', [])
    text = binary(gen, A.Mul_N, A.IntLiteral_N(None, 0), call, 'int')
    assert text == '(0LL * gelb::gelb_random())'


@pytest.mark.parametrize('operation,zero,expected', [
    (A.Add_N, -0.0, 'g_value'), (A.Add_N, 0.0, '(0.0 + g_value)'),
    (A.Sub_N, -0.0, '(-g_value)'), (A.Mul_N, 0.0, '(0.0 * g_value)'),
])
def test_real_zero_sign_rules(operation, zero, expected):
    gen = generator()
    assert binary(gen, operation, A.RealLiteral_N(None, zero), A.Identifier_N(None, 'value'), 'real') == expected


def test_recursive_binary64_and_nonfinite_fallback():
    gen = generator()
    inner = A.Add_N(None, A.RealLiteral_N(None, 1.0), A.RealLiteral_N(None, 2.0))
    assert binary(gen, A.Mul_N, inner, A.RealLiteral_N(None, 4.0), 'real') == '12.0'
    assert binary(gen, A.Mul_N, A.RealLiteral_N(None, 1e300), A.RealLiteral_N(None, 1e300), 'real') == '(1e+300 * 1e+300)'


def test_real32_operands_do_not_use_binary64_identities():
    gen = generator()
    one = A.RealLiteral_N(None, 1.0)
    one.inferred_type = A.ArrayDataType_N(None, 'real32', [])
    assert binary(gen, A.Mul_N, one, A.Identifier_N(None, 'value'), 'real32') == '(1.0f * g_value)'


def test_unary_constant_and_unrolled_integer_coefficient():
    gen = generator()
    value = A.UnaryMinusExpr_N(None, A.RealLiteral_N(None, 1.0))
    assert binary(gen, A.Mul_N, value, A.Identifier_N(None, 'value'), 'real') == '((-1.0) * g_value)'
    coeff = A.Identifier_N(None, 'EX')
    coeff.inferred_type = A.ArrayDataType_N(None, 'int', [3])
    expr = A.Mul_N(None, coeff, A.Identifier_N(None, 'x'))
    expr.inferred_type = A.ArrayDataType_N(None, 'int', [])
    assert gen._emit_expression(expr, '0') == '0LL'


@pytest.mark.parametrize('value', [0.01, 0.0, 0.25])
def test_parenthesized_real_negation_stays_written(value):
    gen = generator()
    negative = A.UnaryMinusExpr_N(None, A.RealLiteral_N(None, value))
    operand = gen._emit_expression(negative)
    assert getattr(operand, 'constant', None) is None
    assert binary(gen, A.Mul_N, A.RealLiteral_N(None, 2.0), negative, 'real') == f'(2.0 * {operand})'


@pytest.mark.parametrize('value', [-0.01, -0.0, -0.25])
def test_negative_real_literal_negation_remains_eligible(value):
    import math
    gen = generator()
    negative = A.UnaryMinusExpr_N(None, A.RealLiteral_N(None, value))
    operand = gen._emit_expression(negative)
    assert operand.constant == -value
    assert math.copysign(1.0, operand.constant) == 1.0
    assert binary(gen, A.Mul_N, A.RealLiteral_N(None, 2.0), negative, 'real') == str(-2.0 * value)


@pytest.mark.parametrize('kind,eligible', [(None, False), ('int32', False), ('int64', True)])
def test_integer_negation_eligibility_keeps_width(kind, eligible):
    gen = generator()
    negative = A.UnaryMinusExpr_N(None, A.IntLiteral_N(None, 1))
    if kind:
        negative.inferred_type = A.ArrayDataType_N(None, kind, [])
    operand = gen._emit_expression(negative)
    assert getattr(operand, 'constant', None) == (-1 if eligible else None)
    assert operand == ('(-1LL)' if eligible else '(-1)')
    assert binary(gen, A.Mul_N, negative, A.Identifier_N(None, 'value'), kind) == (
        '(-g_value)' if eligible else '((-1) * g_value)')


@pytest.mark.parametrize('kind,expected', [
    ('real', '1.0'), ('real32', '1.0f'),
    ('int32', 'static_cast<int32_t>(1)'), ('int64', 'static_cast<int64_t>(1)'),
])
def test_zero_power_preserves_literal_fold_provenance(kind, expected):
    gen = generator()
    power = A.Pow_N(None, A.Identifier_N(None, 'value'), A.IntLiteral_N(None, 0))
    power.inferred_type = A.ArrayDataType_N(None, kind, [])
    operand = gen._emit_expression(power)
    assert operand == expected
    assert getattr(operand, 'constant', None) == (1.0 if kind == 'real' else None)
    if kind == 'real':
        assert binary(gen, A.Add_N, power, A.RealLiteral_N(None, 1.0), 'real') == '2.0'


@pytest.mark.parametrize('operation,left,right,expected', [
    (A.Add_N, 2147483647, 1, 2147483648),
    (A.Sub_N, -9223372036854775807, 1, -9223372036854775808),
    (A.Mul_N, 3037000499, 3037000499, 9223372030926249001),
    (A.Add_N, 9223372036854775807, 1, None),
    (A.Sub_N, -9223372036854775808, 1, None),
    (A.Mul_N, 9223372036854775807, 2, None),
])
@pytest.mark.parametrize('bound', [False, True])
def test_singleton_integer_folding_respects_range(operation, left, right, expected, bound):
    from gelb.backends.highway.common import int64_typed_literal
    gen = generator()
    gen._axis_bindings = {'x': 0} if bound else {}
    result = binary(gen, operation, A.IntLiteral_N(None, left), A.IntLiteral_N(None, right), 'int64')
    if bound and expected is not None:
        assert result == int64_typed_literal(expected)
        assert result.constant == expected
        assert result.int64
    else:
        op = {A.Add_N: '+', A.Sub_N: '-', A.Mul_N: '*'}[operation]
        assert result == f'({int64_typed_literal(left)} {op} {int64_typed_literal(right)})'
        assert getattr(result, 'constant', None) is None


@pytest.mark.parametrize('value,depth,expected', [
    (0, 1, '0LL'), (0, 2, '0LL'), (1, 2, '1LL'),
    (5, 1, '(-5LL)'), (5, 2, '5LL'), (5, 3, '(-5LL)'),
    (-9223372036854775807, 1, '9223372036854775807LL'),
    (9223372036854775807, 2, '9223372036854775807LL'),
])
def test_int64_negation_normalizes_constants(value, depth, expected):
    gen = generator()
    expr = A.IntLiteral_N(None, value)
    for _ in range(depth):
        expr = A.UnaryMinusExpr_N(None, expr)
        expr.inferred_type = A.ArrayDataType_N(None, 'int64', [])
    result = gen._emit_expression(expr)
    assert result == expected
    assert result.constant == value * (-1) ** depth
    assert result.int64


def test_negated_two_to_the_63_is_the_int64_minimum():
    """A negative element of a constant array is unrolled as the negation of
    its magnitude, so the int64 minimum arrives as -(2^63): it is the native
    minimum with its value, and negating it once more stays written."""
    gen = generator()
    int64 = A.ArrayDataType_N(None, 'int64', [])
    magnitude = A.IntLiteral_N(None, 1 << 63)
    magnitude.inferred_type = int64
    minimum = A.UnaryMinusExpr_N(None, magnitude)
    minimum.inferred_type = int64
    result = gen._emit_expression(minimum)
    assert result == '(-9223372036854775807LL - 1LL)'
    assert result.constant == -(1 << 63)
    assert result.int64
    negated = A.UnaryMinusExpr_N(None, minimum)
    negated.inferred_type = int64
    result = gen._emit_expression(negated)
    assert result == '(-(-9223372036854775807LL - 1LL))'
    assert getattr(result, 'constant', None) is None


@pytest.mark.parametrize('value,kind,expected', [
    (-(1 << 63), 'int64', '(-(-9223372036854775807LL - 1LL))'),
    (-5, 'int32', '(-(-5))'),
])
def test_unsafe_or_narrow_negation_stays_written(value, kind, expected):
    gen = generator()
    expr = A.UnaryMinusExpr_N(None, A.IntLiteral_N(None, value))
    expr.inferred_type = A.ArrayDataType_N(None, kind, [])
    result = gen._emit_expression(expr)
    assert result == expected
    assert getattr(result, 'constant', None) is None


def test_singleton_nonzero_coordinate_keeps_int64_fold_width():
    gen = generator()
    gen._axis_bindings = {'x': 9}
    inner = A.Add_N(None, A.Identifier_N(None, 'x'), A.IntLiteral_N(None, 2147483647))
    inner.inferred_type = A.ArrayDataType_N(None, 'int64', [])
    result = binary(gen, A.Add_N, inner, A.IntLiteral_N(None, 1), 'int64')
    assert result == '2147483657LL'
    assert result.constant == 2147483657
    assert result.int64


@pytest.mark.parametrize('backend', ['cpu_highway', 'gpu_cuda_cpp'])
@pytest.mark.parametrize('depth,expected', [
    (1, ['0LL', '(-g_k)', 'g_k', '((-2LL) * g_k)']),
    (2, ['0LL', 'g_k', '(-g_k)', '(2LL * g_k)']),
    (3, ['0LL', '(-g_k)', 'g_k', '((-2LL) * g_k)']),
])
def test_unrolled_integer_negations_normalize_products(backend, depth, expected):
    from gelb.backends.stage3_backend_cpu_highway import generate_cpu_highway
    from gelb.backends.stage3_backend_gpu_cuda_cpp import generate_cuda_cpp
    from gelb.midware.c_family_lowering import prepare_c_family_ast
    expression = 'E'
    for _ in range(depth):
        expression = f'-({expression})'
    values = ', '.join(map(str, [0, 1, -1, 2] + [1] * 12))
    source = f'''
    simulation_description("integer negation");
    global_constants {{ const array[int, 16] E = {{{values}}}; }}
    lattices {{ lattice f(1, 16, real, 16, true); }}
    initializer I {{ f.out[x | :] = 1.0; }}
    dynamic D {{
        int k = int(f.in[x | 0]) + x;
        f.out[x | :] = real({expression} * k) + f.in[x | :];
    }}
    gauge G -> (real v) {{ v = f.in[x | 0]; }}
    node_classes {{ node_class B(I, D, G); }}
    geometry {{ nodes[:] = B; }}
    '''
    result = compile_source(source, PipelineProfile.CODEGEN, PipelineOptions(
        require_stencils=True, require_geometry=True,
        enable_slice_simplify=False, enable_scalar_cse=False))
    result.ast = prepare_c_family_ast(result.ast)
    emit = generate_cpu_highway if backend == 'cpu_highway' else generate_cuda_cpp
    code = emit(result.ast, backend_context=build_backend_context(result))
    for index, product in enumerate(expected):
        store = f'g0_1_f_storage[g0_1_f_new][{index}][(g_x) + 1] = '
        line = next(line for line in code.splitlines() if store in line)
        assert f'static_cast<double>({product})' in line


@pytest.mark.parametrize('backend', ['cpu_highway', 'gpu_cuda_cpp'])
def test_unrolled_int64_minimum_element_keeps_native_spelling(backend):
    """With the default passes, an int64 minimum element of a constant array
    is written into unrolled arithmetic as the native minimum on both
    C-family backends, never as the literal 9223372036854775808, which no
    signed 64-bit type holds."""
    from gelb.backends.stage3_backend_cpu_highway import generate_cpu_highway
    from gelb.backends.stage3_backend_gpu_cuda_cpp import generate_cuda_cpp
    from gelb.midware.c_family_lowering import prepare_c_family_ast
    values = ', '.join(['-9223372036854775807 - 1', '0', '-9223372036854775807'] + ['1'] * 13)
    source = f'''
    simulation_description("int64 minimum element");
    global_constants {{ const array[int, 16] EM = {{{values}}}; }}
    lattices {{ lattice f(1, 16, real, 16, true); }}
    initializer I {{ f.out[x | :] = 1.0; }}
    dynamic D {{ f.out[x | :] = real(EM + x) + 0.0 * f.in[x | :]; }}
    gauge G -> (real v) {{ v = f.in[x | 0]; }}
    node_classes {{ node_class B(I, D, G); }}
    geometry {{ nodes[:] = B; }}
    '''
    result = compile_source(source, PipelineProfile.CODEGEN,
                            PipelineOptions(require_stencils=True, require_geometry=True))
    result.ast = prepare_c_family_ast(result.ast)
    emit = generate_cpu_highway if backend == 'cpu_highway' else generate_cuda_cpp
    code = emit(result.ast, backend_context=build_backend_context(result))
    for index, element in [(0, '(-9223372036854775807LL - 1LL)'), (2, '(-9223372036854775807LL)')]:
        store = f'g0_1_f_storage[g0_1_f_new][{index}][(g_x) + 1] = '
        line = next(line for line in code.splitlines() if store in line)
        assert f'static_cast<double>(({element} + g_x))' in line
    assert '9223372036854775808' not in code


@pytest.mark.parametrize('kind', ['real', 'real32'])
@pytest.mark.parametrize('value', [2.0, float('inf'), -float('inf'), float('nan')])
def test_unrolled_float_eligibility_is_finite_binary64(monkeypatch, kind, value):
    import math
    gen = generator()
    monkeypatch.setattr(gen, '_constant_values', lambda name: [value])
    expr = A.Identifier_N(None, 'EX')
    expr.inferred_type = A.ArrayDataType_N(None, kind, [1])
    result = gen._emit_expression(expr, '0')
    assert getattr(result, 'constant', None) == (value if kind == 'real' and math.isfinite(value) else None)


@pytest.mark.parametrize('value', [float('inf'), -float('inf'), float('nan')])
def test_nonfinite_literals_remain_written(value):
    gen = generator()
    literal = A.RealLiteral_N(None, value)
    operand = gen._emit_expression(literal)
    assert getattr(operand, 'constant', None) is None
    assert binary(gen, A.Mul_N, literal, A.RealLiteral_N(None, 0.0), 'real') == f'({operand} * 0.0)'
    negative = A.UnaryMinusExpr_N(None, literal)
    assert getattr(gen._emit_expression(negative), 'constant', None) is None


@pytest.mark.parametrize('backend', ['cpu_highway', 'gpu_cuda_cpp'])
@pytest.mark.parametrize('expression,entry,written', [
    ('W * 0.0', '1.0e300 * 1.0e300', '(std::numeric_limits<double>::infinity() * 0.0)'),
    ('W - W', '1.0e300 * 1.0e300', '(std::numeric_limits<double>::infinity() - std::numeric_limits<double>::infinity())'),
    ('-W', '-1.0e300 * 1.0e300', '(-(-std::numeric_limits<double>::infinity()))'),
])
def test_unrolled_nonfinite_array_operations_stay_written(backend, expression, entry, written):
    from gelb.backends.stage3_backend_cpu_highway import generate_cpu_highway
    from gelb.backends.stage3_backend_gpu_cuda_cpp import generate_cuda_cpp
    from gelb.midware.c_family_lowering import prepare_c_family_ast
    values = ', '.join([entry] + ['1.0'] * 15)
    source = f'''
    simulation_description("non-finite coefficients");
    global_constants {{ const array[real, 16] W = {{{values}}}; }}
    lattices {{ lattice f(1, 16, real, 16, false); }}
    initializer I {{ f.out[x | :] = 0.0; }}
    dynamic D {{ f.out[x | :] = ({expression}) + f.in[x | :]; }}
    gauge G -> (real v) {{ v = f.in[x | 0]; }}
    node_classes {{ node_class B(I, D, G); }}
    geometry {{ nodes[:] = B; }}
    '''
    result = compile_source(source, PipelineProfile.CODEGEN, PipelineOptions(
        require_stencils=True, require_geometry=True,
        enable_slice_simplify=False, enable_scalar_cse=False))
    result.ast = prepare_c_family_ast(result.ast)
    emit = generate_cpu_highway if backend == 'cpu_highway' else generate_cuda_cpp
    code = emit(result.ast, backend_context=build_backend_context(result))
    assert written in code
    assert 'quiet_NaN()' not in code


@pytest.mark.parametrize('kind,left_width,right_width', [
    ('int32', True, True), ('int64', False, True), ('int64', True, False),
])
def test_singleton_folding_requires_two_int64_operands(kind, left_width, right_width):
    from gelb.backends.highway.expr import ConstantOperand
    gen = generator()
    gen._axis_bindings = {'x': 0}
    expr = A.Add_N(None, A.IntLiteral_N(None, 2), A.IntLiteral_N(None, 3))
    a = ConstantOperand('2LL', 2, int64=left_width)
    b = ConstantOperand('3LL', 3, int64=right_width)
    assert gen._constant_binop(expr, a, b, kind) == '(2LL + 3LL)'


def test_nonfinite_evaluator_result_stays_written(monkeypatch):
    from gelb.backends.highway import statements
    gen = generator()
    monkeypatch.setattr(statements, 'ev_add', lambda a, b: float('inf'))
    assert binary(gen, A.Add_N, A.RealLiteral_N(None, 2.0), A.RealLiteral_N(None, 3.0), 'real') == '(2.0 + 3.0)'
