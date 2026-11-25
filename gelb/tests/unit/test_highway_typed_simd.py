"""Typed emission decides how a vector body is written and when a block has none."""

import dataclasses
import re

import pytest

from gelb.backends.highway.expr import ConstantOperand
from gelb.backends.highway.simd_types import (
    EmittedValue, ScalarFallbackRequired, SimdSymbolEnv,
)
from gelb.backends.stage3_backend_cpu_highway import HighwayCodeGenerator
from gelb.backends.stage3_backend_gpu_cuda_cpp import generate_cuda_cpp
from gelb.compiler_pipeline import (
    PipelineOptions, PipelineProfile, build_backend_context, compile_source,
    prepare_c_family_ast,
)
from gelb.gelb_ast import ASTNodes as A

LAYOUTS = ('soa', 'aos', 'cbt')
BANNER = re.compile(
    r"^[ \t]*// (Initialiser|Init \(2nd buffer\)|Dynamic|Gauge): "
    r"([A-Za-z0-9_]+) \(([A-Za-z0-9_]+)\)(?: \[rect bbox=[^\]]+\])?( -- SIMD)?", re.M)
STAGE = re.compile(r"^[ \t]*// ={10} ", re.M)
HOISTED = re.compile(r"static constexpr [A-Za-z0-9_]+ ([A-Za-z0-9_]+)\[\] =")
CONSTANTS = '''
    const array[real, 3] EX = {0.0, 1.0, -1.0};
    const array[real, 3] C3 = {1.0, 2.0, 0.5};
    const array[int, 3] KI = {1, 2, 3};
    const array[int32, 3] K32 = {1, 2, 3};
    const array[int32, 3] EX32 = {0, 1, -1};
    const array[real, {3, 3}] M3 = {{1.0, 0.0, 0.0}, {0.0, 1.0, 1.0}, {1.0, -1.0, 0.0}};
'''


def program(gauge='v = f.in[x | 0];', *, dynamic='f.out[x | :] = f.in[x | :];',
            init='f.out[x | :] = 1.0 + real(x);', geometry='nodes[:] = B;',
            classes='node_class B(I, D, G);', extra=''):
    return f'''
    simulation_description("typed vector emission");
    global_constants {{ {CONSTANTS} }}
    lattices {{ lattice f(1, 3, real, 64, true); }}
    initializer I {{ {init} }}
    dynamic D {{ {dynamic} }}
    gauge G -> (real v) {{ {gauge} }}
    {extra}
    node_classes {{ {classes} }}
    geometry {{ {geometry} }}
    '''


def compiled(source):
    result = compile_source(source, PipelineProfile.CODEGEN,
                            PipelineOptions(require_stencils=True, require_geometry=True))
    result.ast = prepare_c_family_ast(result.ast)
    return result


def highway(source, layout='soa'):
    result = compiled(source)
    return HighwayCodeGenerator(result.ast, backend_context=build_backend_context(result),
                                storage_layout=layout)


def sections(code, kind, name):
    """(banner says SIMD, text) for every emitted section of one block."""
    marks = list(BANNER.finditer(code))
    out = []
    for i, mark in enumerate(marks):
        if (mark.group(1), mark.group(2)) != (kind, name):
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(code)
        stage = STAGE.search(code, mark.end(), end)
        out.append((bool(mark.group(4)), code[mark.end():stage.start() if stage else end]))
    assert out, (kind, name)
    return out


def assert_path(code, layout, kind, name, vector):
    for simd, body in sections(code, kind, name):
        assert simd == vector
        assert ('hn::' in body) == (vector and layout != 'aos')


def typed(name, dtype):
    node = name if isinstance(name, A.Node_N) else A.Identifier_N(None, name)
    node.inferred_type = A.ArrayDataType_N(None, dtype, [])
    return node


def vector_body(declarations=''):
    """A generator inside a vector body of gauge G, after ``declarations``."""
    gen = highway(program(f'{declarations} v = f.in[x | 0];'))
    gen._simd_mode = 'vec8d'
    gen._current_block = gen.ast.gauges[0]
    gen._simd_env = SimdSymbolEnv()
    for statement in list(gen.ast.gauges[0].stmts)[:-1]:
        gen._emit_statement(statement, 'gauge')
    return gen


# ----------------------------------------------------------------------
# EmittedValue and SimdSymbolEnv
# ----------------------------------------------------------------------

def test_emitted_value_keeps_constant_operands_and_is_immutable():
    gen = vector_body()
    value = gen._emit_typed_expr(typed(A.IntLiteral_N(None, 7), 'int'))
    assert value == EmittedValue('7', 'int', 'int64_t', 'scalar', None)
    assert isinstance(value.code, ConstantOperand) and value.code.constant == 7
    operand = gen._emit_typed_operand(typed(A.IntLiteral_N(None, 7), 'int'), int64_op=True)
    assert (operand.code, operand.code.constant, operand.code.int64) == ('7LL', 7, True)
    real = gen._emit_typed_expr(typed(A.RealLiteral_N(None, 0.5), 'real'))
    assert (real.code.constant, real.cpp_type, real.lane_kind) == (0.5, 'double', 'scalar')
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.lane_kind = 'vec'
    assert gen._emit_expression(typed(A.IntLiteral_N(None, 7), 'int')) == '7'


def test_two_scalars_fold_and_a_vector_operand_keeps_the_operation_written():
    gen = vector_body('real r = f.in[x | 0];')
    one, two = (typed(A.RealLiteral_N(None, value), 'real') for value in (1.0, 2.0))
    folded = gen._emit_typed_expr(typed(A.Mul_N(None, one, two), 'real'))
    assert (folded.code, folded.code.constant, folded.lane_kind) == ('2.0', 2.0, 'scalar')
    written = gen._emit_typed_expr(typed(A.Mul_N(None, one, typed('r', 'real')), 'real'))
    assert (written.code, written.lane_kind) == ('(hn::Set(d, 1.0) * g_r)', 'vec')
    assert getattr(written.code, 'constant', None) is None


def test_coercions_broadcast_what_is_not_yet_a_vector_or_a_mask():
    scalar = EmittedValue('g_y', 'real', 'double')
    vector = EmittedValue('g_r', 'real', 'double', 'vec')
    mask = EmittedValue('g_b', 'bool', 'bool', 'mask')
    coerce = HighwayCodeGenerator._coerce_to_vec
    assert coerce(vector) == 'g_r'
    assert coerce(scalar) == 'hn::Set(d, g_y)'
    assert coerce(mask) == 'hn::IfThenElse(g_b, hn::Set(d, 1.0), hn::Set(d, 0.0))'
    coerce = HighwayCodeGenerator._coerce_to_mask
    assert coerce(mask) == 'g_b'
    assert coerce(EmittedValue('g_u', 'bool', 'bool')) == 'hn::FirstN(d, (g_u) ? hn::Lanes(d) : 0)'


def test_symbol_env_records_one_carrier_per_local():
    env = SimdSymbolEnv()
    assert len(env) == 0 and env.carrier('r') is None
    env.declare('r', 'vec')
    env.declare('b', 'mask')
    assert (env.carrier('r'), env.carrier('b'), len(env)) == ('vec', 'mask', 2)
    with pytest.raises(AssertionError):
        env.declare('q', 'vec8d')


def test_vector_body_carriers_and_declarations():
    """Each local of a vector body is held as the table says, and the table
    is the body's own: empty before it and after it."""
    gen = highway(program('''real r = f.in[x | 0]; bool b = r > 10.0; int k = x;
        int c = int(b); int u = 3; int late; array[real, 2] a = {r, 1.0};
        array[int, 2] ia = {1, 2}; array[bool, 2] ba = {t > 0, false};
        v = r + real(k) + real(c) + real(u) + a[0] + real(ia[0]) + real(ba[0]);'''))
    seen = []
    fill = gen._emit_gauge_buffer_fill

    def record(block):
        if gen._simd_mode == 'vec8d':
            seen.append({name: gen._simd_env.carrier(name) for name in
                         ('v', 'r', 'b', 'k', 'c', 'u', 'late', 'a', 'ia', 'ba')})
        else:
            assert len(gen._simd_env) == 0
        fill(block)

    gen._emit_gauge_buffer_fill = record
    code = gen.generate()
    assert seen and all(item == {
        'v': 'vec', 'r': 'vec', 'b': 'mask', 'k': 'vec_int', 'c': 'vec_int', 'u': 'scalar',
        'late': 'scalar', 'a': 'vec', 'ia': 'scalar', 'ba': 'scalar'} for item in seen)
    assert len(gen._simd_env) == 0
    for line in ('V g_r = hn::LoadU(', 'hn::Mask<D> g_b = hn::Gt(g_r, hn::Set(d, 10.0));',
                 'V g_k = gelb_xv;',
                 'V g_c = hn::IfThenElse(g_b, hn::Set(d, 1.0), hn::Set(d, 0.0));',
                 'int64_t g_u = 3;', 'int64_t g_late = 0;', 'V g_a[2];', 'int64_t g_ia[2];',
                 'bool g_ba[2];'):
        assert line in code, line


# ----------------------------------------------------------------------
# A scalar bool beside a mask
# ----------------------------------------------------------------------

UNIFORM = 'hn::FirstN(d, ((static_cast<int64_t>(gelb_timestep) > 0)) ? hn::Lanes(d) : 0)'
PER_CELL = 'hn::Gt(hn::LoadU(d, &g0_1_f_storage[g0_1_f_old][0][(g_x) + 1]), hn::Set(d, 10.0))'


@pytest.mark.parametrize('operator,form', [
    ('==', 'hn::Not(hn::Xor({}, {}))'), ('!=', 'hn::Xor({}, {})'),
    ('&&', 'hn::And({}, {})'), ('||', 'hn::Or({}, {})'),
])
@pytest.mark.parametrize('scalar_left', [True, False])
def test_every_boolean_operator_broadcasts_a_scalar_bool_beside_a_mask(
        operator, form, scalar_left):
    operands = ['(t > 0)', '(f.in[x | 0] > 10.0)']
    emitted = [UNIFORM, PER_CELL]
    if not scalar_left:
        operands.reverse()
        emitted.reverse()
    code = highway(program(f'v = real({operands[0]} {operator} {operands[1]});')).generate()
    assert_path(code, 'soa', 'Gauge', 'G', True)
    assert ('V g_v = hn::IfThenElse(' + form.format(*emitted)
            + ', hn::Set(d, 1.0), hn::Set(d, 0.0));') not in code  # an output is assigned, not declared
    assert ('g_v = hn::IfThenElse(' + form.format(*emitted)
            + ', hn::Set(d, 1.0), hn::Set(d, 0.0));') in code


@pytest.mark.parametrize('operator', ['==', '!=', '&&', '||'])
def test_two_scalar_bools_stay_scalar_in_a_vector_body(operator):
    code = highway(program(f'v = f.in[x | 0] + real((t > 0) {operator} (t > 1));')).generate()
    assert_path(code, 'soa', 'Gauge', 'G', True)
    assert (f'hn::Set(d, static_cast<double>(((static_cast<int64_t>(gelb_timestep) > 0) '
            f'{operator} (static_cast<int64_t>(gelb_timestep) > 1))))') in code


def test_scalar_bool_stored_into_a_mask_local_is_broadcast():
    code = highway(program('bool u = t > 0; bool w; w = t > 1; '
                           'v = f.in[x | 0] + real(u) + real(w);')).generate()
    assert 'hn::Mask<D> g_u = ' + UNIFORM + ';' in code
    assert 'hn::Mask<D> g_w = hn::FirstN(d, 0);' in code
    assert 'g_w = ' + UNIFORM.replace('> 0', '> 1') + ';' in code


def test_not_of_a_mask_is_a_mask_operation():
    code = highway(program('bool m = f.in[x | 0] > 10.0; bool n = !m; '
                           'v = real(!m) + real(n) + real(!(t > 0));')).generate()
    assert 'hn::Mask<D> g_n = hn::Not(g_m);' in code
    assert 'hn::IfThenElse(hn::Not(g_m), hn::Set(d, 1.0), hn::Set(d, 0.0))' in code
    assert 'hn::Set(d, static_cast<double>((!(static_cast<int64_t>(gelb_timestep) > 0))))' in code


def test_scalar_stored_into_a_vector_local_is_broadcast():
    code = highway(program('real r = 2.5 * real(t); real s; s = 0.5; r = 1.5; '
                           'v = f.in[x | 0] + r + s;')).generate()
    for line in ('V g_r = hn::Set(d, (2.5 * static_cast<double>(static_cast<int64_t>(gelb_timestep))));',
                 'V g_s = hn::Zero(d);', 'g_s = hn::Set(d, 0.5);', 'g_r = hn::Set(d, 1.5);'):
        assert line in code, line


# ----------------------------------------------------------------------
# The right operand of && and ||
# ----------------------------------------------------------------------

DIVISION = '((10LL / static_cast<int64_t>(gelb_timestep)) > 2)'


def test_two_scalar_operands_with_a_division_stay_one_cpp_expression():
    """Between two scalars ``&&`` is the C++ operator, which does not
    evaluate the division when the left operand decides; the block keeps
    its vector body."""
    code = highway(program('v = f.in[x | 0] + real(t > 0 && 10 / t > 2);')).generate()
    assert_path(code, 'soa', 'Gauge', 'G', True)
    assert ('hn::Set(d, static_cast<double>(((static_cast<int64_t>(gelb_timestep) > 0) && '
            + DIVISION + ')))') in code


@pytest.mark.parametrize('layout', LAYOUTS)
@pytest.mark.parametrize('operator', ['&&', '||'])
def test_division_beside_a_mask_is_the_right_operand_of_the_cpp_operator(operator, layout):
    """With a per-cell operand the block is a scalar loop, where the
    division stays the right operand of the C++ ``&&`` or ``||``."""
    code = highway(program(f'v = real(f.in[x | 0] > 3.0 {operator} t > 0 {operator} 10 / t > 2);'),
                   layout).generate()
    assert_path(code, layout, 'Gauge', 'G', False)
    for _, body in sections(code, 'Gauge', 'G'):
        assert f'(static_cast<int64_t>(gelb_timestep) > 0)) {operator} {DIVISION}' in body


def test_right_operand_with_an_integer_division_has_no_vector_and_or():
    """The rule on single expressions: ``&&`` and ``||`` with a mask
    operand, the division anywhere in the right operand."""
    gen = vector_body('real r = f.in[x | 0]; bool b = r > 10.0; int u = 3;')
    r, b, u = typed('r', 'real'), typed('b', 'bool'), typed('u', 'int')
    ten, two = typed(A.IntLiteral_N(None, 10), 'int'), typed(A.IntLiteral_N(None, 2), 'int')
    half = typed(A.RealLiteral_N(None, 0.5), 'real')
    quotient = typed(A.Div_N(None, ten, u), 'int')
    uniform = typed(A.Greater_N(None, quotient, two), 'bool')
    per_cell = typed(A.Greater_N(None, r, call('real', quotient)), 'bool')
    real_quotient = typed(A.Greater_N(None, typed(A.Div_N(None, half, r), 'real'), half), 'bool')
    guard = typed(A.Greater_N(None, u, two), 'bool')

    for node in (quotient, uniform, per_cell, call('real', quotient)):
        assert gen._has_integer_division(node)
    for node in (real_quotient, guard, typed(A.Add_N(None, u, two), 'int'), b, half, None):
        assert not gen._has_integer_division(node)

    for operation, name in ((A.And_N, 'hn::And'), (A.Or_N, 'hn::Or')):
        # a mask on the left, the division in a scalar right operand
        raises_in_vector_body(gen, typed(operation(None, b, uniform), 'bool'))
        # a scalar on the left, the division inside a mask right operand
        raises_in_vector_body(gen, typed(operation(None, guard, per_cell), 'bool'))
        raises_in_vector_body(gen, typed(operation(None, b, per_cell), 'bool'))
        # the division in the left operand is evaluated in any case
        left = gen._emit_typed_expr(typed(operation(None, uniform, b), 'bool'))
        assert (left.lane_kind, left.code) == (
            'mask', f'{name}(hn::FirstN(d, (((10LL / g_u) > 2)) ? hn::Lanes(d) : 0), g_b)')
        # a real division does not stop the program
        assert gen._emit_typed_expr(typed(operation(None, b, real_quotient), 'bool')).lane_kind == 'mask'
        # two scalars: the C++ operator
        both = gen._emit_typed_expr(typed(operation(None, guard, uniform), 'bool'))
        assert both.lane_kind == 'scalar' and '10LL / g_u' in both.code
    # == and != evaluate both operands in every language
    for operation in (A.Equal_N, A.NotEqual_N):
        assert gen._emit_typed_expr(typed(operation(None, b, uniform), 'bool')).lane_kind == 'mask'


# ----------------------------------------------------------------------
# What has no vector form
# ----------------------------------------------------------------------

FALLBACKS = {
    # narrow widths
    'narrow_local': 'int32 n; v = f.in[x | 0];',
    'narrow_cast': 'v = real(real32(f.in[x | 0]));',
    'narrow_expression': 'v = f.in[x | 0] + real(real32(0.5) * real32(t));',
    'narrow_constant_in_a_reduction': 'array[real, 3] w = f.in[x | :]; v = dot_prod(K32, w);',
    # intrinsics without a vector form, and a power that is not unrolled
    'mod': 'v = mod(f.in[x | 0], 3.0);',
    'mod_of_scalars': 'v = f.in[x | 0] + real(mod(t, 2));',
    'atan2': 'v = atan2(f.in[x | 0], 2.0);',
    'real64_cast': 'v = real64(f.in[x | 0]);',
    'int64_cast': 'v = f.in[x | 0] + real(int64(t));',
    'real_power': 'v = f.in[x | 0] ^ 0.5;',
    'ninth_power': 'v = f.in[x | 0] ^ 9;',
    # integers that vary from cell to cell
    'integer_arithmetic_on_x': 'v = real(x + 1);',
    'integer_negation_of_x': 'v = real(-x);',
    'integer_abs_of_x': 'v = real(abs(x));',
    'integer_min_with_x': 'v = real(min(x, 5));',
    'arithmetic_on_the_integer_of_a_mask': 'v = real(1 + int(f.in[x | 0] > 10.0));',
    'integer_power_zero_of_x': 'int k = x; v = real(k ^ 0);',
    'integer_cast_of_x': 'v = real(int(x) * 1);',
    'integer_cast_of_a_lattice_value': 'v = real(int(f.in[x | 0]));',
    'int_local_from_an_int_local': 'int k = x; int m = k; v = real(m);',
    'store_into_an_admitted_int_local': 'int k = x; k = 9007199254740993; v = real(k);',
    # per-cell values into locals that stay C++ scalars
    'x_into_an_int_local': 'int k; k = x; v = real(k);',
    'mask_integer_into_an_int_local': 'int k = 0; k = int(f.in[x | 0] > 10.0); v = real(k);',
    'x_into_an_int_array': 'array[int, 2] a = {x, 1}; v = real(a[0]);',
    'int_literal_with_x_into_a_real_array': 'array[real, 2] a = {x, 1}; v = a[0];',
    'real_cast_of_an_int_literal_with_x': 'array[real, 2] a = real({x, 1}); v = a[0];',
    'assigned_int_array': 'array[int, 2] a; a = {1, int(f.in[x | 0] > 10.0)}; v = real(a[1]);',
    'mask_into_a_bool_array': 'array[bool, 2] b = {f.in[x | 0] > 10.0, false}; v = real(b[0]);',
    'assigned_bool_array': 'array[bool, 2] b; b = {f.in[x | 0] > 10.0, false}; v = real(b[0]);',
    'bool_array_from_two_slices': 'array[bool, 2] b = f.in[x | 0:1] > f.in[x | 1:2]; v = real(b[0]);',
    'bool_array_copy_of_masks': 'bool m = f.in[x | 0] > 10.0; array[bool, 2] b = {m, !m}; v = real(b[1]);',
    # reductions over an integer array of the block
    'sum_of_a_local_int_array': 'array[int, 3] k = {1, 2, 3}; v = f.in[x | 0] + real(sum(k));',
    'dot_prod_with_a_local_int_array':
        'array[int, 3] k = {1, 2, 3}; v = f.in[x | 0] + real(dot_prod(KI, k));',
    'matmul_with_a_local_int_array':
        'array[int, 3] k = {1, 2, 3}; array[real, 3] m = matmul(M3, k); v = f.in[x | 0] + m[0];',
    # an integer division in the right operand of && or || beside a per-cell operand
    'and_with_a_division_in_a_scalar_right_operand':
        'v = real(f.in[x | 0] > 3.0 && t > 0 && 10 / t > 2);',
    'or_with_a_division_in_a_scalar_right_operand':
        'v = real(f.in[x | 0] > 70.0 || t == 0 || 10 / t > 2);',
    'and_of_bool_locals_with_a_division':
        'bool c1 = f.in[x | 0] > 3.0; bool c2 = t > 0; v = real(c1 && c2 && 10 / t > 2);',
    'and_with_a_division_in_a_mask_right_operand': 'v = real(t > 0 && f.in[x | 0] > real(10 / t));',
    'or_with_a_division_in_a_mask_right_operand': 'v = real(t == 0 || f.in[x | 0] > real(10 / t));',
    'and_with_the_guard_and_the_division_on_the_right':
        'v = real(f.in[x | 0] > 3.0 && (t > 0 && 10 / t > 2));',
    'and_with_a_division_in_an_intrinsic_on_the_right':
        'v = real(f.in[x | 0] > 3.0 && t > 0 && max(10 / t, 1) > 2);',
}
VECTOR_FORMS = {
    'int_local_from_x': 'int k = x; v = real(k);',
    'int_local_from_the_integer_of_a_mask': 'int c = int(f.in[x | 0] > 10.0); v = real(c);',
    'integer_of_a_mask_cast_back': 'v = real(int(x < 33));',
    'uniform_int_local': 'int u = 2 * t + 1; v = f.in[x | 0] + real(u);',
    'unrolled_powers': 'real r = f.in[x | 0]; v = r^0 + r^1 + r^8;',
    'real_of_x': 'v = real(x) + 1.0 * x;',
    'uniform_bool_array': 'array[bool, 2] b = {t > 0, false}; v = f.in[x | 0] + real(b[0]);',
    'bool_array_copy': 'array[bool, 2] b = {t > 0, false}; array[bool, 2] c = b; v = f.in[x | 0] + real(c[0]);',
    'dot_prod_with_a_constant_int_array':
        'array[real, 3] w = f.in[x | :]; v = dot_prod(KI, w);',
    'sum_of_a_real_array': 'array[real, 3] w = f.in[x | :]; v = sum(w);',
    'matmul_of_a_real_array':
        'array[real, 3] w = f.in[x | :]; array[real, 3] m = matmul(M3, w); v = m[0];',
    # && and || beside a per-cell operand, without an integer division on the right
    'and_with_a_real_division_on_the_right':
        'v = real(f.in[x | 0] > 3.0 && t > 0 && 10.0 / real(t) > 2.0);',
    'and_with_an_integer_division_on_the_left': 'v = real(10 / (t + 1) > 2 && f.in[x | 0] > 3.0);',
    'and_with_an_integer_sum_on_the_right': 'v = real(f.in[x | 0] > 3.0 && t + 1 > 2);',
    'equality_with_an_integer_division_on_the_right':
        'v = real((f.in[x | 0] > 3.0) == (10 / (t + 1) > 2));',
    # a draw is taken before its statement (Numerical semantics: Random numbers)
    'and_with_a_draw_on_the_left': 'v = real((random() < 0.5) && (t > 0));',
    'and_with_a_draw_on_the_right': 'v = real((t > 0) && (random() < 0.5));',
}


@pytest.mark.parametrize('layout', LAYOUTS)
@pytest.mark.parametrize('case', tuple(FALLBACKS))
def test_block_without_vector_form_is_scalar_in_every_layout(case, layout):
    """One statement without a vector form sends the whole block to the
    scalar path, in the three layouts alike; the other blocks keep theirs."""
    code = highway(program(FALLBACKS[case]), layout).generate()
    assert_path(code, layout, 'Gauge', 'G', False)
    assert_path(code, layout, 'Dynamic', 'D', True)
    assert_path(code, layout, 'Initialiser', 'I', True)


@pytest.mark.parametrize('layout', LAYOUTS)
@pytest.mark.parametrize('dynamic', [
    'array[real, 3] w = upstream_dfs(f, x, EX32); f.out[x | :] = w;',
    'f.out[x | :] = bounce_back_dfs(f, x, EX32);',
])
def test_streaming_with_a_narrow_velocity_set_is_scalar(dynamic, layout):
    code = highway(program(dynamic=dynamic), layout).generate()
    assert_path(code, layout, 'Dynamic', 'D', False)
    assert_path(code, layout, 'Gauge', 'G', True)
    wide = highway(program(dynamic=dynamic.replace('EX32', 'EX')), layout).generate()
    assert_path(wide, layout, 'Dynamic', 'D', True)


@pytest.mark.parametrize('layout', LAYOUTS)
@pytest.mark.parametrize('case', tuple(VECTOR_FORMS))
def test_block_with_vector_form_is_vector_in_every_layout(case, layout):
    code = highway(program(VECTOR_FORMS[case]), layout).generate()
    assert_path(code, layout, 'Gauge', 'G', True)


def raises_in_vector_body(gen, node):
    with pytest.raises(ScalarFallbackRequired):
        gen._emit_typed_expr(node)


def call(name, *arguments, dtype='real'):
    args = A.List_N(None)
    for argument in arguments:
        args.append(argument)
    return typed(A.IntrinsicFunctionCall_N(None, name, args), dtype)


def test_typed_expression_raises_for_each_form_without_vector_equivalent():
    """The rules, on single expressions inside a vector body."""
    gen = vector_body('''real r = f.in[x | 0]; bool b = r > 10.0; int k = x;
        array[int, 3] ia = {1, 2, 3}; int u = 3;''')
    x, r, b, k = typed('x', 'int'), typed('r', 'real'), typed('b', 'bool'), typed('k', 'int')
    one, two = typed(A.IntLiteral_N(None, 1), 'int'), typed(A.IntLiteral_N(None, 2), 'int')
    half = typed(A.RealLiteral_N(None, 0.5), 'real')
    nine = typed(A.IntLiteral_N(None, 9), 'int')
    zero = typed(A.IntLiteral_N(None, 0), 'int')

    # The two integers a vector holds exactly, and what reads them back.
    assert gen._emit_typed_expr(x) == EmittedValue('gelb_xv', 'int', 'int64_t', 'vec', 'coord_x')
    assert gen._emit_typed_expr(k) == EmittedValue('g_k', 'int', 'int64_t', 'vec', 'local')
    cast = gen._emit_typed_expr(call('int', b, dtype='int'))
    assert (cast.lane_kind, cast.vec_int_origin) == ('vec', 'bool_int_cast')
    assert gen._emit_typed_expr(call('real', x)).code == 'gelb_xv'
    assert gen._emit_typed_expr(typed('u', 'int')).lane_kind == 'scalar'

    # Narrow widths: a value, a cast, a promotion.
    raises_in_vector_body(gen, typed('r', 'real32'))
    raises_in_vector_body(gen, call('real32', half, dtype='real32'))
    raises_in_vector_body(gen, typed(A.TypePromotionNode_N(
        None, one, A.ArrayDataType_N(None, 'int32', [])), 'int32'))
    # Intrinsics without a vector form, whatever their arguments.
    raises_in_vector_body(gen, call('mod', half, half))
    raises_in_vector_body(gen, call('atan2', half, half))
    raises_in_vector_body(gen, call('int64', one, dtype='int'))
    raises_in_vector_body(gen, typed(A.Pow_N(None, r, half), 'real'))
    raises_in_vector_body(gen, typed(A.Pow_N(None, r, nine), 'real'))
    # Integer operations on a per-cell operand.
    for operation in (A.Add_N, A.Sub_N, A.Mul_N, A.Div_N):
        raises_in_vector_body(gen, typed(operation(None, x, one), 'int'))
        raises_in_vector_body(gen, typed(operation(None, one, k), 'int'))
    raises_in_vector_body(gen, typed(A.Add_N(None, call('int', b, dtype='int'), one), 'int'))
    raises_in_vector_body(gen, typed(A.Pow_N(None, x, two), 'int'))
    raises_in_vector_body(gen, typed(A.Pow_N(None, x, one), 'int'))
    raises_in_vector_body(gen, typed(A.Pow_N(None, x, zero), 'int'))
    raises_in_vector_body(gen, typed(A.UnaryMinusExpr_N(None, x), 'int'))
    raises_in_vector_body(gen, call('abs', x, dtype='int'))
    raises_in_vector_body(gen, call('min', x, one, dtype='int'))
    raises_in_vector_body(gen, call('max', one, x, dtype='int'))
    # A real power 0 of a per-cell value is the scalar one.
    unit = gen._emit_typed_expr(typed(A.Pow_N(None, r, zero), 'real'))
    assert (unit.code, unit.lane_kind) == ('1.0', 'scalar')
    # Integer casts of a vector, x included; only a mask converts.
    raises_in_vector_body(gen, call('int', x, dtype='int'))
    raises_in_vector_body(gen, call('int', r, dtype='int'))
    raises_in_vector_body(gen, typed(A.TypePromotionNode_N(
        None, r, A.ArrayDataType_N(None, 'int', [])), 'int'))
    # A reduction over an integer array of the block.
    raises_in_vector_body(gen, call('sum', typed('ia', 'int'), dtype='int'))
    raises_in_vector_body(gen, call('dot_prod', typed('KI', 'int'), typed('ia', 'int'), dtype='int'))
    # Outside a vector body none of this raises.
    gen._simd_mode = 'scalar'
    assert gen._emit_typed_expr(typed(A.Add_N(None, x, one), 'int')).code == '(g_x + 1LL)'
    assert gen._emit_typed_expr(call('mod', half, half)).lane_kind == 'scalar'


# ----------------------------------------------------------------------
# The speculative vector emission leaves nothing behind
# ----------------------------------------------------------------------

TRIGGER = 'array[bool, 2] b = {m > 10.0, false}; v = real(b[0]) + m;'
ROLLBACKS = {
    # a hoisted index array of dot_prod before the statement that has no vector form
    'after_dot_prod': (program('array[real, 3] w = f.in[x | :]; real m = dot_prod(EX, w); ' + TRIGGER),
                       'Gauge', 'G'),
    # the same after upstream_dfs: on CBT its cross-tile reads hoist their index arrays
    'after_upstream': (program(dynamic='array[real, 3] w = upstream_dfs(f, x, EX); real m = w[1]; '
                                       'array[bool, 2] b = {m > 10.0, false}; '
                                       'f.out[x | :] = w + real(b[0]);'), 'Dynamic', 'D'),
}
TWO_D = '''
    simulation_description("a peeled row before the vector body");
    global_constants { const array[real, 3] EY2 = {0.0, 2.0, -2.0}; const array[real, 3] EX0 = {0.0, 0.0, 0.0}; }
    lattices { lattice f(2, 3, real, {64, 8}, {true, true}); }
    initializer I { f.out[x, y | :] = 1.0 + real(x); }
    dynamic D {
        array[real, 3] w = upstream_dfs(f, x, y, {EX0, EY2});
        real m = dot_prod(EY2, w);
        array[bool, 2] b = {m > 10.0, false};
        f.out[x, y | :] = w + real(b[0]);
    }
    gauge G -> (real v) { v = f.in[x, y | 0]; }
    node_classes { node_class B(I, D, G); }
    geometry { nodes[:, :] = B; }
'''
ROLLBACKS['after_a_peeled_row'] = (TWO_D, 'Dynamic', 'D')


def block_and_rectangle(gen, kind, name):
    container = {'Dynamic': gen.ast.dynamics, 'Gauge': gen.ast.gauges}[kind]
    block = gen._find_block(container, name)
    info = gen._geom.nc_info['B']
    (rect, synthetic), = gen._iter_dispatch_rects(info)
    assert not synthetic
    return block, rect


@pytest.mark.parametrize('layout', LAYOUTS)
@pytest.mark.parametrize('case', tuple(ROLLBACKS))
def test_fallback_rolls_the_whole_attempt_back(case, layout):
    """After a vector attempt is given up, the generator is where a
    generator that never tried is: the same lines, the same hoisted arrays
    with the same numbers, and every piece of emission state as before."""
    source, kind, name = ROLLBACKS[case]
    context = kind.lower()
    tried, plain = highway(source, layout), highway(source, layout)
    block, rect = block_and_rectangle(tried, kind, name)
    assert tried._block_simd_eligible(block, rect)
    before = tried._emission_state()

    raised = []
    statement = tried._emit_statement

    def watch(stmt, ctx):
        try:
            statement(stmt, ctx)
        except ScalarFallbackRequired:
            # What the attempt had written and registered when it stopped.
            raised.append((len(tried._lines), tried._indent, tried._simd_mode,
                           len(tried._deferred_constexpr_decls)))
            raise

    tried._emit_statement = watch
    tried._emit_block_dispatch(kind, block, 'B', rect, '', context)

    plain_block, plain_rect = block_and_rectangle(plain, kind, name)
    plain._emit(f'// {kind}: {name} (B)')
    plain._emit_spatial_loop_open(plain_rect)
    plain._emit_block_body(plain_block, context=context)
    plain._emit_spatial_loop_close()

    assert len(raised) == 1
    lines, indent, mode, hoisted = raised[0]
    assert mode == 'vec8d' and lines > before[0]
    assert (indent > 0) == (layout != 'aos')    # AoS learns the path from a probe at the end
    if case != 'after_upstream' or layout == 'cbt':
        assert hoisted > 0      # the attempt had registered arrays of its own
    assert tried._lines == plain._lines
    assert tried._deferred_constexpr_decls == plain._deferred_constexpr_decls
    assert tried._deferred_constexpr_dedup == plain._deferred_constexpr_dedup
    assert tried._deferred_constexpr_counter == plain._deferred_constexpr_counter
    after = tried._emission_state()
    assert after[1:9] == before[1:9]        # indent, mode, table, axes, bindings, block, index flag
    assert (tried._indent, tried._simd_mode, tried._wrap_safe_axes, tried._axis_bindings,
            tried._axis_binding_stack, tried._current_block, tried._in_coord_scalar,
            len(tried._simd_env)) == (0, 'scalar', set(), {}, [], None, False, 0)


@pytest.mark.parametrize('layout', LAYOUTS)
@pytest.mark.parametrize('case', tuple(ROLLBACKS))
def test_no_hoisted_array_is_left_unused(case, layout):
    code = highway(ROLLBACKS[case][0], layout).generate()
    names = HOISTED.findall(code)
    assert [int(name.rsplit('_', 1)[1]) for name in names] == list(range(1, len(names) + 1))
    for name in names:
        assert len(re.findall(rf'\b{name}\b', code)) > 1, name
    assert_path(code, layout, ROLLBACKS[case][1], ROLLBACKS[case][2], False)


NARROW_CLASS = dict(
    classes='node_class B(I, D, G); node_class S(I, D, GS);',
    geometry='nodes[:] = B; nodes[3:12] = S;')


@pytest.mark.parametrize('layout', LAYOUTS)
@pytest.mark.parametrize('statements,vector', [
    ('array[bool, 2] b = {f.in[x | 0] > 10.0, false}; v = real(b[0]) + real(b[1]);', False),
    ('bool b0 = f.in[x | 0] > 10.0; bool b1 = false; v = real(b0) + real(b1);', True),
])
def test_path_does_not_depend_on_the_layout_or_the_rectangle(layout, statements, vector):
    """In a class ten cells wide CBT has no full tile and writes scalar code
    under the banner, as AoS does everywhere; the banner still says which
    path the block has, the same one in the three layouts."""
    code = highway(program(extra=f'gauge GS -> (real v) {{ {statements} }}', **NARROW_CLASS),
                   layout).generate()
    for simd, body in sections(code, 'Gauge', 'GS'):
        assert simd == vector
        assert ('hn::' in body) == (vector and layout == 'soa')
        assert ('x = scalar' in body) == (vector and layout != 'soa')


def test_probe_of_a_rectangle_without_vector_body_is_discarded():
    """On AoS the vector form is emitted once to learn the block's path and
    then dropped: the output is the scalar interior, and nothing of the
    probe remains."""
    source = program('array[real, 3] w = f.in[x | :]; v = dot_prod(EX, w);')
    gen = highway(source, 'aos')
    modes = []
    body = gen._emit_block_body_inner
    gen._emit_block_body_inner = lambda block, context: (
        modes.append((block.name.name, gen._simd_mode)), body(block, context=context))[1]
    code = gen.generate()
    assert ('G', 'vec8d') in modes and ('G', 'scalar') in modes
    assert 'hn::' not in ''.join(text for _, text in sections(code, 'Gauge', 'G'))
    assert 'gelb::gelb_signed_sum(d, ' not in code
    names = HOISTED.findall(code)
    assert names and all(len(re.findall(rf'\b{name}\b', code)) > 1 for name in names)


def test_guarded_reads_of_a_block_shape_its_vector_emission():
    """A block that reads through ``bounce_back_dfs`` keeps the cells at the
    edges of a non-periodic grid out of the vector body, peels the partial
    first tile on CBT, and stays scalar on CBT when a link is as long as a
    tile."""
    bounce = program(dynamic='f.out[x | :] = bounce_back_dfs(f, x, EX);').replace('64, true', '64, false')
    plain = program().replace('64, true', '64, false')
    (_, body), = sections(highway(bounce, 'soa').generate(), 'Dynamic', 'D')
    assert 'x = scalar head' in body and 'x = scalar tail' in body
    assert 'for (; g_x + VW <= 63; g_x += VW) {' in body
    (_, body), = sections(highway(plain, 'soa').generate(), 'Dynamic', 'D')
    assert 'x = scalar' not in body and 'for (; g_x + VW <= 64; g_x += VW) {' in body
    (_, body), = sections(highway(bounce, 'cbt').generate(), 'Dynamic', 'D')
    assert 'x = scalar head' in body and 'CBT partial first tile' in body
    assert 'for (int g_x_tile = 1; g_x_tile <= 7; ++g_x_tile) {' in body
    (_, body), = sections(highway(plain, 'cbt').generate(), 'Dynamic', 'D')
    assert 'CBT partial' not in body and 'for (int g_x_tile = 0; g_x_tile <= 8; ++g_x_tile) {' in body
    # Inside a larger right-hand side the call is found as well: the store
    # is written one DF at a time, never as a loop over the DF index.
    nested = program(dynamic='f.out[x | :] = bounce_back_dfs(f, x, EX) + 0.5 * C3;')
    (_, body), = sections(highway(nested, 'soa').generate(), 'Dynamic', 'D')
    assert 'gelb_df' not in body and body.count('hn::StoreU(gelb_v, d, ') == 3
    long_link = bounce.replace('const array[real, 3] EX = {0.0, 1.0, -1.0};',
                               'const array[real, 3] EX = {0.0, 8.0, -8.0};')
    assert_path(highway(long_link, 'cbt').generate(), 'cbt', 'Dynamic', 'D', False)
    assert_path(highway(long_link, 'soa').generate(), 'soa', 'Dynamic', 'D', True)


# ----------------------------------------------------------------------
# The implicit timestep, and a dot product of two constants
# ----------------------------------------------------------------------

TIME = program('bool c = t > 0; v = sin(real(t)) + real(t + 1) + real(c) + f.in[x | 0];')


def test_cuda_kernels_read_the_device_timestep():
    result = compiled(TIME)
    code = generate_cuda_cpp(result.ast, backend_context=build_backend_context(result))
    assert code.count('static_cast<int64_t>(gelb_timestep_d)') >= 3
    assert 'sin(static_cast<double>(static_cast<int64_t>(gelb_timestep_d)))' in code
    assert '(static_cast<int64_t>(gelb_timestep_d) + 1LL)' in code
    assert '(static_cast<int64_t>(gelb_timestep_d) > 0)' in code
    assert not re.search(r'static_cast<int64_t>\(gelb_timestep\)', code)


def test_highway_reads_the_host_timestep():
    gen = highway(TIME)
    assert gen._emit_implicit_timestep() == 'static_cast<int64_t>(gelb_timestep)'
    code = gen.generate()
    assert '(static_cast<int64_t>(gelb_timestep) + 1LL)' in code
    assert 'gelb_timestep_d' not in code


@pytest.mark.parametrize('declarations,product', [
    ('', 'dot_prod(C3, EX)'),
    ('const array[real, 3] LA = {2.0, 4.0, 8.0}; const array[real, 3] LB = {1.0, 0.5, 0.25};',
     'dot_prod(LA, LB)'),
    ('const array[real, 3] LA = {2.0, 4.0, 8.0};', 'dot_prod(LA, C3)'),
])
def test_dot_product_of_two_constant_arrays_is_folded_before_emission(declarations, product):
    """Both operands constant: the product is a literal on Highway and on
    CUDA, with no helper call and no hoisted coefficient array."""
    source = program(f'{declarations} v = f.in[x | 0] + {product};')
    result = compiled(source)
    context = build_backend_context(result)
    highway_code = HighwayCodeGenerator(result.ast, backend_context=context,
                                        storage_layout='soa').generate()
    cuda_code = generate_cuda_cpp(result.ast, backend_context=context)
    literal = {'dot_prod(C3, EX)': '1.5', 'dot_prod(LA, LB)': '6.0', 'dot_prod(LA, C3)': '14.0'}[product]
    for code in (highway_code, cuda_code):
        assert 'gelb_dot_prod' not in code.split('int main()')[1]
        assert 'gelb_dp_' not in code
    assert f'hn::Set(d, {literal})' in highway_code
    assert f' + {literal})' in cuda_code
