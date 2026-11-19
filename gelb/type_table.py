"""Computational type families, widths and target spellings shared by all stages."""

from types import MappingProxyType


class UnifiedTypeTable:
    """Immutable type metadata; aliases retain their target spelling."""

    aliases = MappingProxyType({'int64': 'int', 'real64': 'real'})
    canonical_types = ('bool', 'int8', 'int16', 'int32', 'int', 'real32', 'real')
    integer_types = ('int', 'int8', 'int16', 'int32', 'int64')
    narrow_integer_types = ('int8', 'int16', 'int32')
    real_types = ('real', 'real32', 'real64')
    wide_real_types = ('real', 'real64')
    wide_integer_types = ('int', 'int64')
    numeric_types = frozenset(integer_types + real_types)
    all_types = numeric_types | {'bool'}
    narrow_array_types = ('real32',) + narrow_integer_types
    width_casts = ('real32', 'real64') + narrow_integer_types + ('int64',)
    bits = MappingProxyType({
        'bool': 8, 'int8': 8, 'int16': 16, 'int32': 32, 'int': 64,
        'int64': 64, 'real32': 32, 'real': 64, 'real64': 64,
    })
    integer_bits = MappingProxyType({name: width for name, width in bits.items() if name.startswith('int')})
    integer_bounds = MappingProxyType({
        name: (-(1 << (width - 1)), (1 << (width - 1)) - 1)
        for name, width in integer_bits.items()
    })
    # Explicit aliases win ties in promotion, preserving the source's spelling.
    width_rank = MappingProxyType({
        'int8': 1, 'int16': 2, 'int32': 3, 'int': 4, 'int64': 5,
        'real32': 1, 'real': 2, 'real64': 3,
    })
    numeric_kind = MappingProxyType({
        'int': 'int64', 'int64': 'int64', 'int8': 'int8',
        'int16': 'int16', 'int32': 'int32', 'real': 'real64',
        'real64': 'real64', 'real32': 'real32',
    })
    cpp = MappingProxyType({
        'bool': 'bool', 'int': 'int64_t', 'int8': 'int8_t', 'int16': 'int16_t',
        'int32': 'int32_t', 'int64': 'int64_t', 'real': 'double',
        'real32': 'float', 'real64': 'double',
    })
    fortran = MappingProxyType({
        'bool': 'logical(1)', 'int': 'integer(8)', 'int8': 'integer(1)',
        'int16': 'integer(2)', 'int32': 'integer(4)', 'int64': 'integer(8)',
        'real': 'double precision', 'real32': 'real(4)', 'real64': 'real(8)',
    })
    fortran_format = MappingProxyType({
        'bool': "'(L1)'", 'int': "'(I0)'", 'int8': "'(I0)'", 'int16': "'(I0)'",
        'int32': "'(I0)'", 'int64': "'(I0)'", 'real': "'(ES23.16)'",
        'real32': "'(ES15.8)'", 'real64': "'(ES23.16)'",
    })
    fortran_integer_suffix = MappingProxyType({'int8': '_1', 'int16': '_2', 'int32': '_4'})
    netcdf_c = MappingProxyType({
        'bool': 'NC_BYTE', 'int': 'NC_INT64', 'int8': 'NC_BYTE',
        'int16': 'NC_SHORT', 'int32': 'NC_INT', 'int64': 'NC_INT64',
        'real': 'NC_DOUBLE', 'real32': 'NC_FLOAT', 'real64': 'NC_DOUBLE',
    })
    netcdf_fortran = MappingProxyType({
        name: value.replace('NC_', 'NF90_') for name, value in netcdf_c.items()
    })
