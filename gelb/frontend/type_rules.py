#!/usr/bin/env python3
"""One rule for GeLB's numeric types (user manual, Numerical semantics:
Types and promotion).

Every pass that needs to know what type a mixed expression has asks
here: type inference for the result of an arithmetic operator,
type promotion for the type both operands are converted to, and the
intrinsic table for the argument and result types of the scalar
intrinsics.  The rule is written once so the three cannot disagree.

The table:

- If either operand is real, the result is real, of the widest real
  operand's width; an integer operand converts to that width
  (``int + real32`` is ``real32``).
- Otherwise the result is integer, of the widest operand's width.
  Narrow integers are not widened first: ``int8 + int8`` is ``int8``,
  while ``int8 + 1`` is ``int``, because the literal is ``int``.
- ``bool`` with a numeric type takes that type; ``bool`` with ``bool``
  gives ``int`` in arithmetic.

Intrinsic result types: ``min``, ``max`` and ``mod`` return the
common type of the table; ``atan2`` converts both arguments to the
common *real* type and returns it; ``abs`` returns its argument's type,
integers included; the library functions (``sqrt``, ``exp``, ``log``,
``sin``, ``cos``, ``tan``, ``tanh``) return the width of their real
argument, and an integer argument gives ``real``.

``real64`` is an alias of ``real`` and ``int64`` of ``int``; where two
aliases meet, the explicit spelling wins, which is what the backends'
type maps treat identically anyway.  ``real16`` is not in this version
(Numerical semantics: Not in this version): the parser rejects it
where it builds the type.
"""

from gelb.utils.exceptions import GeLBExTypeError

# Display order; the backends and the cast intrinsics iterate these.
INTEGER_TYPES = ('int', 'int8', 'int16', 'int32', 'int64')
REAL_TYPES = ('real', 'real32', 'real64')
NUMERIC_TYPES = frozenset(INTEGER_TYPES + REAL_TYPES)
ARITHMETIC_TYPES = NUMERIC_TYPES | {'bool'}

# Widths, narrowest first.  ``int`` is ``int64`` and ``real`` is
# ``real64``; the alias ranks just above its bare spelling so that a
# tie between the two keeps the explicit one.
_WIDTH_RANK = {
    'int8': 1, 'int16': 2, 'int32': 3, 'int': 4, 'int64': 5,
    'real32': 1, 'real': 2, 'real64': 3,
}

# Types a later version may add.  The parser rejects them where the
# type is built, with the diagnostic below, so no pass ever sees one.
NOT_IN_THIS_VERSION = {
    'real16': ("Use real32 or real; cast with real32() or real(). "
               "Half precision is planned for a later version."),
}

LIBRARY_FUNCTIONS = frozenset({'sqrt', 'exp', 'log', 'sin', 'cos', 'tan', 'tanh'})
TABLE_FUNCTIONS = frozenset({'min', 'max', 'mod'})
SCALAR_INTRINSICS = LIBRARY_FUNCTIONS | TABLE_FUNCTIONS | {'abs', 'atan2'}


def is_integer(type_name):
    return type_name in INTEGER_TYPES


def is_real(type_name):
    return type_name in REAL_TYPES


def widest(a, b):
    """The wider of two types of one family; the first on a tie."""
    return a if _WIDTH_RANK[a] >= _WIDTH_RANK[b] else b


def common_type(a, b):
    """The table above: the type two operands are converted to, or ``None``
    when either takes no part in arithmetic (a string, an unknown).
    ``bool`` with ``bool`` is ``bool`` here; an arithmetic operator
    makes that ``int`` (``arithmetic_result_type``), a comparison
    compares the two as they are."""
    if a not in ARITHMETIC_TYPES or b not in ARITHMETIC_TYPES:
        return None
    if is_real(a) or is_real(b):
        if is_real(a) and is_real(b):
            return widest(a, b)
        return a if is_real(a) else b
    if is_integer(a) or is_integer(b):
        if is_integer(a) and is_integer(b):
            return widest(a, b)
        return a if is_integer(a) else b
    return 'bool'


def arithmetic_result_type(a, b):
    """The type of ``a + b``, ``a - b``, ``a * b``, ``a / b`` and
    ``a ^ b``: the common type, with ``bool`` with ``bool`` giving
    ``int`` (in arithmetic, ``bool`` is 0 or 1)."""
    common = common_type(a, b)
    return 'int' if common == 'bool' else common


def real_width_of(type_name):
    """The real type a library function computes in for an argument of
    this type: the argument's own width if it is real, else ``real``."""
    return type_name if is_real(type_name) else 'real'


def intrinsic_argument_types(name, arg_types):
    """The types the arguments of a scalar intrinsic are converted to
    before the call, one entry per argument, ``None`` for an argument
    left as it is.  Names outside the scalar set convert nothing."""
    if name in LIBRARY_FUNCTIONS:
        return (real_width_of(arg_types[0]),)
    if name in TABLE_FUNCTIONS:
        common = common_type(arg_types[0], arg_types[1])
        return (common, common)
    if name == 'atan2':
        common = common_type(arg_types[0], arg_types[1])
        width = real_width_of(common) if common is not None else None
        return (width, width)
    return tuple(None for _ in arg_types)


def intrinsic_result_type(name, arg_types):
    """The result type of a scalar intrinsic for these argument types."""
    if name in LIBRARY_FUNCTIONS:
        return real_width_of(arg_types[0])
    if name == 'abs':
        return arg_types[0]
    if name in TABLE_FUNCTIONS:
        return common_type(arg_types[0], arg_types[1])
    if name == 'atan2':
        return real_width_of(common_type(arg_types[0], arg_types[1]))
    raise ValueError(f"{name!r} is not a scalar intrinsic")


def reject_if_not_in_this_version(type_name, node):
    """Raise the "not in this version" diagnostic for a type a later
    version may add.  ``node`` carries the source location."""
    hint = NOT_IN_THIS_VERSION.get(type_name)
    if hint is not None:
        raise GeLBExTypeError(
            node,
            f"The type '{type_name}' is not in this version of GeLB",
            hint)
