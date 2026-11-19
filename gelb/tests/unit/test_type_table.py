"""Type metadata preserves language widths and each target's spellings."""

import pytest

from gelb.type_table import UnifiedTypeTable as Types
from gelb.gelb_ast.CanonicalType import CanonicalType
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d
from gelb.utils.exceptions import GeLBExTypeError


@pytest.mark.parametrize('name,canonical,bits,cpp,fortran,format_,nc', [
    ('bool', 'bool', 8, 'bool', 'logical(1)', "'(L1)'", 'BYTE'),
    ('int8', 'int8', 8, 'int8_t', 'integer(1)', "'(I0)'", 'BYTE'),
    ('int16', 'int16', 16, 'int16_t', 'integer(2)', "'(I0)'", 'SHORT'),
    ('int32', 'int32', 32, 'int32_t', 'integer(4)', "'(I0)'", 'INT'),
    ('int', 'int', 64, 'int64_t', 'integer(8)', "'(I0)'", 'INT64'),
    ('int64', 'int', 64, 'int64_t', 'integer(8)', "'(I0)'", 'INT64'),
    ('real32', 'real32', 32, 'float', 'real(4)', "'(ES15.8)'", 'FLOAT'),
    ('real', 'real', 64, 'double', 'double precision', "'(ES23.16)'", 'DOUBLE'),
    ('real64', 'real', 64, 'double', 'real(8)', "'(ES23.16)'", 'DOUBLE'),
])
def test_target_metadata(name, canonical, bits, cpp, fortran, format_, nc):
    assert Types.aliases.get(name, name) == canonical
    assert CanonicalType(name, ()).dtype == canonical
    assert Types.bits[name] == bits
    assert Types.cpp[name] == cpp
    assert Types.fortran[name] == fortran
    assert Types.fortran_format[name] == format_
    assert Types.netcdf_c[name] == 'NC_' + nc
    assert Types.netcdf_fortran[name] == 'NF90_' + nc
    if name.startswith('int'):
        assert Types.integer_bounds[name] == (-2 ** (bits - 1), 2 ** (bits - 1) - 1)
        assert Types.integer_bits[name] == bits
        if bits < 64:
            assert Types.fortran_integer_suffix[name] == '_' + str(bits // 8)


def test_families_and_promotion():
    assert len(Types.all_types) == 9
    assert len(Types.canonical_types) == 7
    assert set(Types.canonical_types) == Types.all_types - Types.aliases.keys()
    assert Types.numeric_types == set(Types.integer_types + Types.real_types)
    assert Types.narrow_array_types == ('real32', 'int8', 'int16', 'int32')
    assert Types.wide_integer_types == ('int', 'int64')
    assert Types.wide_real_types == ('real', 'real64')
    assert [Types.width_rank[k] for k in ('int8', 'int16', 'int32', 'int', 'int64')] == [1, 2, 3, 4, 5]
    assert [Types.width_rank[k] for k in ('real32', 'real', 'real64')] == [1, 2, 3]
    for value in vars(Types).values():
        if isinstance(value, (dict, tuple, frozenset)) or hasattr(value, 'keys'):
            assert 'real16' not in value
    with pytest.raises(TypeError):
        Types.cpp['real'] = 'float'


@pytest.mark.parametrize('statement', ['real16 h = 0.0;', 'real h = real16(x);'])
def test_half_precision_keeps_frontend_diagnostic(statement):
    with pytest.raises(GeLBExTypeError, match='not in this version'):
        get_typed_ast(minimal_gelb_program_1d(initializer_content=statement))


def test_geometry_predicate_hint_lists_supported_numeric_types():
    from gelb.compiler_pipeline import compile_source, PipelineProfile, PipelineOptions
    source = minimal_gelb_program_1d(geometry_content='nodes[:] = BULK; nodes[where Select(real(x))] = BULK;')
    source += '''
    function Select(real a) -> (bool r) {
        array[real,2] v={a,a}; r=sum(v)>0.0;
    }
    '''
    with pytest.raises(GeLBExTypeError) as error:
        compile_source(source, PipelineProfile.CODEGEN, PipelineOptions(require_geometry=True))
    message = str(error.value)
    assert 'Supported here:' in message
    assert 'real32' in message and 'real64' in message
    assert 'real16' not in message
