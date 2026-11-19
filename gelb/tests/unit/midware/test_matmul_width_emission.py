"""Promoted matmul arithmetic and the non-finite coefficient fallback."""

from types import MappingProxyType, SimpleNamespace

import pytest

from gelb.backends.stage3_backend_cpu_highway import HighwayCodeGenerator
from gelb.gelb_ast import ASTNodes as A
from gelb.gelb_ast.CanonicalType import CanonicalType
from gelb.compiler_pipeline import BackendContext, GlobalConstant, ProgramFacts
from gelb.frontend.SymbolsTable import SymbolsTable
from gelb.gelb_ast.SymbolDefinition import SymbolDefinition


def emitter(matrix_type, vector_type, result_type, values, simd=False):
    gen = object.__new__(HighwayCodeGenerator)
    gen._simd_mode = 'vec8d' if simd else None
    matrix = None if values is None else tuple(tuple(row) for row in values)
    gen.backend_context = BackendContext(
        None, {}, None, None,
        MappingProxyType({'M': GlobalConstant(matrix_type, (3, 3), matrix=matrix)}),
        MappingProxyType({}), None, ProgramFacts(False, False, False, False))
    symbols = SymbolsTable()
    vector = SymbolDefinition('v', 'variable', None)
    vector.canonical_type = CanonicalType(vector_type, (3,))
    symbols.append(vector)
    gen._current_block = SimpleNamespace(symbol_defs=symbols)
    lines = []
    gen._emit = lines.append
    args = A.List_N(None)
    for name, kind, dims in [('M', matrix_type, (3, 3)), ('v', vector_type, (3,))]:
        node = A.Identifier_N(None, name)
        node.canonical_type = CanonicalType(kind, dims)
        args.append(node)
    call = A.IntrinsicFunctionCall_N(None, 'matmul', args)
    call.canonical_type = CanonicalType(result_type, (3,))
    return gen, call, lines


@pytest.mark.parametrize('dtype,cpp', [('int8', 'int8_t'), ('int16', 'int16_t')])
@pytest.mark.parametrize('fallback', [False, True])
def test_narrow_row_conversion_in_both_routes(dtype, cpp, fallback):
    values = None if fallback else [[0, 0, 0], [1, -1, 0], [2, 3, 4]]
    gen, call, lines = emitter(dtype, dtype, dtype, values)
    gen._emit_matmul_into_array('out', 3, call)
    assert all(f'= static_cast<{cpp}>(' in line for line in lines)
    assert gen._emit_intrinsic_matmul(call, 'i').startswith(f'static_cast<{cpp}>(')


@pytest.mark.parametrize('matrix,vector,result,cast', [
    ('real', 'real32', 'real', 'static_cast<double>(g_v[0])'),
    ('real32', 'real', 'real', 'static_cast<double>(g_M[0][0])'),
    ('real32', 'int', 'real32', 'static_cast<float>(g_v[0])'),
])
def test_nonfinite_fallback_converts_operands(matrix, vector, result, cast):
    # The coefficient evaluator leaves no folded matrix for NaN/Inf entries.
    gen, call, lines = emitter(matrix, vector, result, None)
    gen._emit_matmul_into_array('out', 3, call)
    assert cast in lines[0]


def test_fallback_broadcasts_matrix_in_vector_body():
    gen, call, lines = emitter('real', 'real', 'real', None, simd=True)
    gen._emit_matmul_into_array('out', 3, call)
    assert 'hn::Set(d, g_M[0][0]) * g_v[0]' in lines[0]
    assert 'static_cast' not in ''.join(lines)


def test_integer_coefficient_rounds_once_to_float():
    value = 2**54 + 2**30 + 1
    text = HighwayCodeGenerator._matrix_entry_text(value, 'real32')
    assert text.endswith('f')
    assert int(float(text[:-1])) == 2**54 + 2**31


@pytest.mark.parametrize('kind,zero', [('real32', '0.0f'), ('int', '0LL'),
                                     ('int32', 'static_cast<int32_t>(0)')])
def test_zero_row_uses_call_width(kind, zero):
    gen, call, lines = emitter(kind, kind, kind, [[0]*3]*3)
    gen._emit_matmul_into_array('wide_destination', 3, call)
    assert lines[0] == f'wide_destination[0] = {zero};'
