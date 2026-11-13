"""Keep local symbol entries attached to the live declarations of a block."""

from gelb.gelb_ast.CanonicalType import CanonicalType, canonical_from_ast
from gelb.gelb_ast.SymbolDefinition import SymbolDefinition
from gelb.utils.exceptions import GeLBInternalInvariantError


def _type(decl):
    canonical = canonical_from_ast(decl.data_type)
    if not isinstance(canonical, CanonicalType):
        raise GeLBInternalInvariantError(f'invalid temporary type for {decl.name.name}')
    decl.data_type.canonical_type = canonical
    return canonical


def declare_temp(block, decl):
    canonical = _type(decl)
    table = getattr(block, 'symbol_defs', None)
    if table is None:
        return None
    name = decl.name.name
    if table.contains_local(name):
        raise GeLBInternalInvariantError(f'duplicate local declaration: {name}')
    symbol = SymbolDefinition(name, 'variable declaration', decl)
    symbol.code_range = decl.code_range
    symbol.canonical_type = canonical
    table.symbol_defs.append(symbol)
    return symbol


def replace_decl(block, new_decl):
    canonical = _type(new_decl)
    table = getattr(block, 'symbol_defs', None)
    if table is None:
        return None
    name = new_decl.name.name
    symbol = table.get_symbol_definition_local(name)
    if symbol is None:
        raise GeLBInternalInvariantError(f'missing local declaration: {name}')
    symbol.tag = 'variable declaration'
    symbol.value = new_decl
    symbol.code_range = new_decl.code_range
    symbol.canonical_type = canonical
    return symbol


def remove_decl(block, name):
    table = getattr(block, 'symbol_defs', None)
    if table is None:
        return
    symbol = table.get_symbol_definition_local(name)
    if symbol is None:
        raise GeLBInternalInvariantError(f'missing local declaration: {name}')
    table.symbol_defs.remove(symbol)


def names_available(block, names):
    table = getattr(block, 'symbol_defs', None)
    return table is None or all(not table.contains(name) for name in names)


def fresh_name(block, prefix, counter, reserved=()):
    """Advance the existing pass counter only as far as needed for a free name."""
    while True:
        name = f'{prefix}{next(counter)}'
        if name not in reserved and names_available(block, (name,)):
            return name
