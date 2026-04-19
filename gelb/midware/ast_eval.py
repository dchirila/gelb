"""Compile-time AST expression evaluator.

Evaluates constant expressions in the GeLB AST to Python values
(int, float, bool).  Used by geometry resolution, and available
to any analysis pass that needs to evaluate compile-time constants.

This module is backend-independent -- it works purely on the AST
and does not emit any target-language code.
"""

from __future__ import annotations

import math

import numpy as np

from gelb.gelb_ast.ASTNodes import (
    IntLiteral_N, RealLiteral_N, BoolLiteral_N,
    Add_N, Sub_N, Mul_N, Div_N, Pow_N,
    Less_N, Greater_N, LessEqual_N, GreaterEqual_N,
    Equal_N, NotEqual_N, And_N, Or_N, NotExpr_N,
    UnaryMinusExpr_N, Identifier_N,
    ConstantDefinitionStmt_N, List_N,
    LatticeInstaStmt_N,
    VariableAssignmentStmt_N, VariableDeclarationStmt_N,
    UserFunctionCall_N, IntrinsicFunctionCall_N,
    TypePromotionNode_N, Array1DLiteral_N, RectSelOfArrayElems_N,
    ArrayDataType_N,
)
from gelb.frontend.type_rules import (
    INTEGER_TYPES, REAL_TYPES, arithmetic_result_type, real_width_of)
from gelb.utils.exceptions import GeLBExStencilError


_DIM_SIZE_NAMES = ('Nx', 'Ny', 'Nz')


def _literal_value_or_expr(node):
    """Return literal payloads, preserving expression nodes for evaluation."""
    return node.value if hasattr(node, 'value') else node


def collect_lattice_info(ast) -> dict:
    """Extract lattice metadata from the AST.

    Returns a dict mapping lattice name to
    ``{d, q, dtype, grid_size, periodic}``.
    """
    info = {}
    for stmt in ast.lattices.stmts:
        if isinstance(stmt, LatticeInstaStmt_N):
            info[stmt.name.name] = {
                'd': stmt.d.value,
                'q': stmt.q.value,
                'dtype': stmt.df_type.element_dtype,
                'grid_size': _literal_value_or_expr(stmt.grid_size),
                'periodic': _literal_value_or_expr(stmt.periodicity),
            }
    return info


def get_max_dim(lattice_info: dict) -> int:
    """Return the maximum dimensionality across all lattices."""
    return max(v['d'] for v in lattice_info.values())


def get_grid_size(lattice_info: dict, dim_index: int, *, ast=None) -> int:
    """Return the resolved grid size for a specific dimension."""
    first = next(iter(lattice_info.values()))
    gs = first['grid_size']
    d = first['d']
    if d == 1:
        if isinstance(gs, int):
            return gs
        return int(eval_const_expr(
            gs, ast=ast, lattice_info=lattice_info))
    else:
        elem = gs.elements[dim_index]
        if isinstance(elem, int):
            return elem
        return int(eval_const_expr(
            elem, ast=ast, lattice_info=lattice_info))


def get_grid_sizes(lattice_info: dict, *, ast=None) -> tuple[int, ...]:
    """Return resolved grid sizes for all dimensions as a tuple."""
    d = get_max_dim(lattice_info)
    return tuple(get_grid_size(lattice_info, i, ast=ast) for i in range(d))


def is_periodic(lattice_info: dict, dim_index: int) -> bool:
    """Check if a dimension is periodic."""
    first = next(iter(lattice_info.values()))
    p = first['periodic']
    d = first['d']
    if d == 1:
        if isinstance(p, bool):
            return p
        if isinstance(p, str):
            return p.lower() == 'true'
        return bool(p)
    else:
        elem = p.elements[dim_index] if isinstance(p, List_N) else p[dim_index]
        if isinstance(elem, bool):
            return elem
        if isinstance(elem, str):
            return elem.lower() == 'true'
        if hasattr(elem, 'value'):
            v = elem.value
            if isinstance(v, bool):
                return v
            return str(v).lower() == 'true'
        return bool(elem)


def find_function(ast, name: str):
    """Look up a user-defined function block by name."""
    if ast.symbol_defs is not None:
        sdef = ast.symbol_defs.get_symbol_definition(name)
        if sdef is not None and sdef.tag == 'function':
            return sdef.value
    if ast.functions:
        funcs = ast.functions
        if isinstance(funcs, List_N):
            funcs = funcs.elements
        for func in funcs:
            if func.name.name == name:
                return func
    raise ValueError(f"Function '{name}' not found")


def eval_function_body(ast, func_block, bindings=None, *, lattice_info=None):
    """Evaluate a pure single-output function at compile time.

    ``bindings`` holds the parameter values.  Statements run in source
    order: a declaration with a value binds it, an assignment rebinds a
    local or the output, and the output's value when the body ends is
    the result (a later assignment overrides an earlier one).  Anything
    the evaluator cannot run is an error naming the function, not a
    silent default.
    """
    if bindings is None:
        bindings = {}
    outputs = func_block.outputs.elements
    fn_range = getattr(func_block, 'code_range', None)
    fn_lines = dict(
        source_line=(fn_range.start_line if fn_range is not None else None),
        source_end_line=(fn_range.stop_line if fn_range is not None else None))
    if len(outputs) != 1:
        raise GeLBExStencilError(
            f"Function '{func_block.name.name}' has {len(outputs)} outputs;"
            f" a function evaluated at compile time must have exactly one",
            "A paint predicate is a scalar bool; give it a single-output "
            "function.", **fn_lines)
    output_name = outputs[0].name.name
    # A value takes the width of the variable it is stored in (parameter,
    # output or local), as it does in the generated code.
    declared = {d.name.name: d.data_type
                for d in (*func_block.inputs.elements, *outputs)}
    local = {name: _typed(value, declared.get(name))
             for name, value in bindings.items()}
    assigned = False
    for stmt in func_block.stmts:
        if isinstance(stmt, VariableDeclarationStmt_N):
            declared[stmt.name.name] = stmt.data_type
            value = getattr(stmt, 'initial_value', None)
            if value is not None:
                local[stmt.name.name] = _typed(eval_const_expr(
                    value, local, ast=ast, lattice_info=lattice_info),
                    stmt.data_type)
        elif isinstance(stmt, VariableAssignmentStmt_N):
            target = stmt.lhs.name if isinstance(stmt.lhs, Identifier_N) \
                else None
            if target is None:
                raise GeLBExStencilError(
                    f"Function '{func_block.name.name}' contains an "
                    f"assignment the compile-time evaluator does not "
                    f"support", "Only scalar variables and the output may "
                    "be assigned in a function used by the geometry.",
                    **fn_lines)
            local[target] = _typed(eval_const_expr(
                stmt.rhs, local, ast=ast, lattice_info=lattice_info),
                declared.get(target))
            if target == output_name:
                assigned = True
        else:
            raise GeLBExStencilError(
                f"Function '{func_block.name.name}' contains a statement "
                f"the compile-time evaluator does not support "
                f"({type(stmt).__name__})",
                "A function evaluated at compile time may contain only "
                "scalar declarations and assignments.", **fn_lines)
    if not assigned:
        # Conditional-paint functions must assign their declared output so
        # the geometry resolver has a value to test.
        raise GeLBExStencilError(
            f"Function '{func_block.name.name}' does not assign its "
            f"output '{output_name}'",
            ("A user-defined function invoked from a geometry "
             "paint predicate must assign a value to its declared "
             "output (otherwise the predicate has no value to test)."),
            **fn_lines)
    return local[output_name]


# ---------------------------------------------------------------------------
# The one compile-time evaluator (user manual, Numerical semantics:
# Types and promotion; Library functions; Constant folding).
#
# Every pass that computes with constants calls the functions below:
# the constant folder (ConstantFoldingVisitor), this module's tree
# evaluator (eval_const_expr: geometry predicates, ranges, the slice
# expansion's constant arrays) and the exact simplifier (ast_simplify).
# The arithmetic is written once so that a constant means the same
# wherever it is evaluated, and the same as the generated code computes.
#
# A value carries its width, so a constant's declared width survives
# from its declaration to its use: the default widths (``int`` is
# 64-bit, ``real`` double precision) are Python's own int and float; the
# narrower ones are NumPy scalars, whose arithmetic rounds as the
# generated code does.  Mixed widths never meet after the type pass has
# inserted the promotions; should they (a hand-built tree), the result
# width is type_rules' table and both operands are converted first.
#
# What the numerical semantics make a compile-time error raises a
# ConstantEvaluationError (an integer result outside its width; a NaN,
# infinite or out-of-range real converted to an integer).  A
# zero divisor raises ZeroDivisionError, which the folder leaves for
# DivisionByZeroValidator to report.  A real overflow or domain error in
# a library function raises OverflowError or ValueError, as the math
# module does: the folder leaves such a call to run time, where it
# gives the IEEE value (Numerical semantics: Special values).
# ---------------------------------------------------------------------------

_INT_DTYPES = INTEGER_TYPES
_REAL_DTYPES = REAL_TYPES
_NARROW_INT = {'int8': np.int8, 'int16': np.int16, 'int32': np.int32}
_NARROW_REAL = {'real32': np.float32}
NARROW_INT_WIDTHS = frozenset(_NARROW_INT)
NARROW_REAL_WIDTHS = frozenset(_NARROW_REAL)
_INT_BITS = {'int8': 8, 'int16': 16, 'int32': 32, 'int': 64, 'int64': 64}
_INT_OF_NP = {np.int8: 'int8', np.int16: 'int16', np.int32: 'int32'}


class ConstantEvaluationError(Exception):
    """A constant expression the numerical contract makes a compile-time
    error.  The folder reports it at the expression's location."""


class IntegerOverflow(ConstantEvaluationError, OverflowError):
    """The integer result of an operation does not fit its width (a
    compile-time error in a constant expression)."""


class InvalidConversion(ConstantEvaluationError, ValueError):
    """A NaN, infinite or out-of-range real converted to an integer (a
    compile-time error in a constant expression)."""


def _is_bool(value):
    return isinstance(value, (bool, np.bool_))


def _is_int(value):
    return isinstance(value, (int, np.integer)) and not _is_bool(value)


def _is_real(value):
    return isinstance(value, (float, np.floating))


def width_of(value):
    """The GeLB width a value carries: ``bool``; ``int8``, ``int16``,
    ``int32`` or ``int`` for an integer; ``real32`` or ``real`` for a
    real."""
    if _is_bool(value):
        return 'bool'
    if isinstance(value, np.floating):
        return 'real32' if isinstance(value, np.float32) else 'real'
    if isinstance(value, float):
        return 'real'
    if isinstance(value, np.integer):
        return _INT_OF_NP.get(type(value), 'int')
    if isinstance(value, int):
        return 'int'
    raise ValueError(f"not a scalar value: {value!r}")


def _result_width(a, b):
    """The width of an arithmetic operation on two values: type_rules'
    table (user manual, Numerical semantics: Types and promotion)."""
    width = arithmetic_result_type(width_of(a), width_of(b))
    if width is None:
        raise ValueError(f"no arithmetic on {a!r} and {b!r}")
    return width


def _wrap_int(value, dtype):
    """``value`` (any integer) in the range of the integer width
    ``dtype``, wrapping as a narrowing conversion does."""
    bits = _INT_BITS[dtype]
    half = 1 << (bits - 1)
    return ((int(value) + half) % (1 << bits)) - half


def _as_int(value, dtype):
    """A Python int in the width's storage: a NumPy scalar for a narrow
    width, a Python int for ``int``."""
    np_type = _NARROW_INT.get(dtype)
    return int(value) if np_type is None else np_type(value)


def _as_real(value, dtype):
    """A binary64 value in the real width's storage, rounded once."""
    return np.float32(value) if dtype == 'real32' else float(value)


_IEEE_SPECIAL_VALUES = False


class ieee_special_values:
    """A context in which an operation, a conversion or a library call
    that overflows or is invalid gives the IEEE 754 value (an infinity,
    a NaN) instead of raising: what the same expression gives at run
    time.  The constant folder runs in it, so that ``exp(1000.0)``,
    ``sqrt(-1.0)``, ``1.0e300 * 1.0e300`` and ``real32(1.0e300)`` fold
    to the value the run time would compute, which the backends then
    write as an explicit special value (user manual, Numerical
    semantics: Constant folding).  Outside it (the geometry's ``where``
    predicates, the exact simplifier) such an operation raises, and the
    caller leaves the expression as it is."""

    def __enter__(self):
        global _IEEE_SPECIAL_VALUES
        self._saved = _IEEE_SPECIAL_VALUES
        _IEEE_SPECIAL_VALUES = True

    def __exit__(self, *exc):
        global _IEEE_SPECIAL_VALUES
        _IEEE_SPECIAL_VALUES = self._saved
        return False


def _finite(result, *operands):
    """``result`` if it is finite or an operand already was not; else
    the exception the math module would raise: an overflow to infinity
    is an OverflowError, an invalid operation (NaN) a ValueError.
    Inside ``ieee_special_values`` (the folder) the value is returned
    as it is: the IEEE 754 result the run time would give."""
    r = float(result)
    if math.isfinite(r) or not all(math.isfinite(float(o)) for o in operands):
        return result
    if _IEEE_SPECIAL_VALUES:
        return result
    if math.isnan(r):
        raise ValueError("invalid real operation (NaN) in a constant expression")
    raise OverflowError("real overflow in a constant expression")


def fit_int(value, dtype):
    """``value``, the exact integer result of an operation, in the width
    ``dtype``: an IntegerOverflow if it does not fit."""
    dtype = str(dtype)
    bits = _INT_BITS[dtype]
    iv = int(value)
    if not -(1 << (bits - 1)) <= iv < (1 << (bits - 1)):
        raise IntegerOverflow(f"integer overflow: {iv} does not fit {dtype}")
    return _as_int(iv, dtype)


def convert(value, dtype):
    """``value`` converted to the GeLB scalar type ``dtype``: an
    integer to a narrower integer wraps; a real to an integer truncates
    toward zero, and a NaN, an infinity or a value outside the target's
    range is an InvalidConversion; an integer to a real is rounded once,
    directly to the target width; a real to a narrower real rounds to
    nearest; ``bool`` is 0 or 1."""
    name = str(dtype)
    if name == 'bool':
        if not _is_bool(value):
            raise ValueError(f"cannot convert {value!r} to bool")
        return bool(value)
    if name in _INT_DTYPES:
        if _is_bool(value) or _is_int(value):
            return _as_int(_wrap_int(int(value), name), name)
        fv = float(value)
        if math.isnan(fv) or math.isinf(fv):
            raise InvalidConversion(f"cannot convert {fv!r} to {name}")
        iv = int(fv)                      # truncation toward zero
        bits = _INT_BITS[name]
        if not -(1 << (bits - 1)) <= iv < (1 << (bits - 1)):
            raise InvalidConversion(f"{fv!r} is out of range for {name}")
        return _as_int(iv, name)
    if name in _REAL_DTYPES:
        np_type = _NARROW_REAL.get(name)
        if _is_bool(value):
            value = int(value)
        if np_type is None:
            return _finite(float(value), value) if _is_real(value) else float(value)
        # An integer is converted to the narrow width directly, as the
        # backends' compilers do: through binary64 it would round twice
        # (2^54 + 2^30 + 1 is above the binary32 midpoint, its binary64
        # rounding is the midpoint, and the tie then rounds down).
        # Python's float() is itself correctly rounded, so a value
        # already real goes through it.
        if _is_int(value) and -2 ** 63 <= int(value) < 2 ** 63:
            return np_type(np.int64(int(value)))
        with np.errstate(over='ignore'):      # _finite reports the overflow
            narrowed = np_type(float(value))
        return _finite(narrowed, value)
    raise ValueError(f"unsupported conversion to {name}")


_convert = convert


def _typed(value, data_type):
    """``value`` as stored in a variable declared ``data_type``: a scalar
    takes the declared width, an array's elements take its element
    width."""
    if data_type is None:
        return value
    dtype = data_type.element_dtype \
        if isinstance(data_type, ArrayDataType_N) else data_type
    if isinstance(value, list):
        return [_typed(v, dtype) for v in value]
    return convert(value, dtype)


def narrow_scalar(value, dtype):
    """``value`` rounded or wrapped to the narrow GeLB width ``dtype``
    (``real32``, ``int8``, ``int16``, ``int32``) and returned as a plain
    Python value: what a literal of that width holds.  Any other width,
    or a bool, is returned as is.  For the constant folder, so that a
    folded constant means the same at compile time, in a paint predicate
    and in the generated code: the declared width is never lost."""
    name = str(dtype)
    if _is_bool(value):
        return value
    if isinstance(value, (int, np.integer)) and name in NARROW_INT_WIDTHS:
        return convert(value, name).item()
    if isinstance(value, (int, float, np.integer, np.floating)) \
            and name in NARROW_REAL_WIDTHS:
        return convert(value, name).item()
    return value


def convert_plain(value, dtype):
    """``value`` converted to the GeLB scalar type ``dtype``, as a plain
    Python value: what a promotion or an explicit conversion yields when
    the constant folder applies it."""
    return plain(convert(value, dtype))


def plain(value):
    """A NumPy scalar as the Python value it holds; a Python value as it
    is.  What a literal stores."""
    return value.item() if isinstance(value, np.generic) else value


def typed_literal_value(expr):
    """A literal's payload in its inferred width: a folded ``real32``
    literal is a NumPy float32, a plain ``real`` literal a float."""
    value = expr.value
    dtype = getattr(getattr(expr, 'inferred_type', None), 'element_dtype', None)
    if dtype is None or _is_bool(value):
        return value
    if isinstance(value, int) and dtype in NARROW_INT_WIDTHS:
        return convert(value, dtype)
    if isinstance(value, float) and dtype in NARROW_REAL_WIDTHS:
        return convert(value, dtype)
    return value


_literal_value = typed_literal_value


def _plain(value):
    """A NumPy scalar of a default width as the Python value it is (a
    narrow width keeps its NumPy type on purpose)."""
    if isinstance(value, np.float64):
        return float(value)
    if isinstance(value, np.int64):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


# --- the operations -------------------------------------------------------

def negate(a):
    """Unary minus, in the operand's width; an integer that does not fit
    (the minimum of its width) is an IntegerOverflow."""
    width = width_of(a)
    if width in _INT_DTYPES:
        return fit_int(-int(a), width)
    if width in _REAL_DTYPES:
        return -a
    raise ValueError(f"no unary minus on {a!r}")


def _integer_binary(operation, a, b, width):
    return fit_int(operation(int(a), int(b)), width)


def add(a, b):
    width = _result_width(a, b)
    a, b = convert(a, width), convert(b, width)
    if width in _INT_DTYPES:
        return _integer_binary(lambda x, y: x + y, a, b, width)
    with np.errstate(over='ignore', invalid='ignore'):   # _finite reports
        result = a + b
    return _finite(result, a, b)


def sub(a, b):
    width = _result_width(a, b)
    a, b = convert(a, width), convert(b, width)
    if width in _INT_DTYPES:
        return _integer_binary(lambda x, y: x - y, a, b, width)
    with np.errstate(over='ignore', invalid='ignore'):   # _finite reports
        result = a - b
    return _finite(result, a, b)


def mul(a, b):
    width = _result_width(a, b)
    a, b = convert(a, width), convert(b, width)
    if width in _INT_DTYPES:
        return _integer_binary(lambda x, y: x * y, a, b, width)
    with np.errstate(over='ignore', invalid='ignore'):   # _finite reports
        result = a * b
    return _finite(result, a, b)


def int_div(left, right):
    """Integer division truncating toward zero, in the operands'
    common width; a zero divisor is a ZeroDivisionError, and the one
    overflow (the minimum divided by -1) an IntegerOverflow."""
    if right == 0:
        raise ZeroDivisionError("integer division by zero")
    a, b = int(left), int(right)
    q = abs(a) // abs(b)
    q = q if (a >= 0) == (b >= 0) else -q
    return fit_int(q, _result_width(left, right))


def divide(a, b):
    """``a / b``: integer division for two integers, else a real
    division in the common width; a zero divisor is a ZeroDivisionError
    for both (a compile-time error when the compiler can see it)."""
    width = _result_width(a, b)
    a, b = convert(a, width), convert(b, width)
    if width in _INT_DTYPES:
        return int_div(a, b)
    if b == 0:
        raise ZeroDivisionError("real division by zero")
    with np.errstate(over='ignore', invalid='ignore'):   # _finite reports
        result = a / b
    return _finite(result, a, b)


def int_pow(base, exponent):
    """An integer raised to an integer, exactly.  A negative
    exponent follows Fortran: ``x^-n`` is ``1 / x^n`` in integer
    division, so 0 unless ``x`` is 1 or -1; ``0^-n`` divides by zero."""
    base, exponent = int(base), int(exponent)
    if exponent >= 0:
        if abs(base) >= 2 and exponent >= 64:
            raise IntegerOverflow(
                f"integer overflow: {base}^{exponent} does not fit any integer width")
        return base ** exponent
    if base == 0:
        raise ZeroDivisionError("0 raised to a negative power")
    if base == 1:
        return 1
    if base == -1:
        return -1 if exponent % 2 else 1
    return 0


def power(a, b):
    """``a ^ b``: exact integer arithmetic for two integers; for a
    real base, the host's binary64 ``pow`` on the operands' values,
    rounded once to the expression's width (user manual, Numerical
    semantics: Library functions).  A domain error (a negative base
    with a fractional exponent) is a ValueError and an overflow an
    OverflowError, as the math module raises them, outside
    ``ieee_special_values``; inside it the IEEE 754 value (a NaN, an
    infinity)."""
    width = _result_width(a, b)
    if width in _INT_DTYPES:
        return fit_int(int_pow(a, b), width)
    try:
        result = math.pow(float(a), float(b))
    except (ValueError, OverflowError):
        result = _ieee_result(np.power, a, b)
    return convert(_finite(result, a, b), width)


def truncated_mod(a, b):
    """``mod(a, b)``: the truncated remainder, with the sign of the
    dividend, for integers and reals (Fortran MOD, C fmod)."""
    width = _result_width(a, b)
    a, b = convert(a, width), convert(b, width)
    if width in _INT_DTYPES:
        if b == 0:
            raise ZeroDivisionError("mod by zero")
        q = int_div(a, b)
        return fit_int(int(a) - int(q) * int(b), width)
    if b == 0:
        raise ZeroDivisionError("mod by zero")
    return convert(math.fmod(float(a), float(b)), width)


def _ieee_minmax(a, b, width, want_min):
    """IEEE 754-2019 minimum/maximum: a NaN operand gives NaN, and
    -0 is less than +0."""
    fa, fb = float(a), float(b)
    if math.isnan(fa) or math.isnan(fb):
        return convert(math.nan, width)
    if fa == fb:
        # equal values, possibly zeros of different sign: -0 is the
        # smaller
        a_negative = math.copysign(1.0, fa) < 0
        if want_min:
            return a if a_negative else b
        return b if a_negative else a
    if want_min:
        return a if fa < fb else b
    return a if fa > fb else b


def minimum(a, b):
    width = _result_width(a, b)
    a, b = convert(a, width), convert(b, width)
    if width in _INT_DTYPES:
        return a if int(a) <= int(b) else b
    return _ieee_minmax(a, b, width, want_min=True)


def maximum(a, b):
    width = _result_width(a, b)
    a, b = convert(a, width), convert(b, width)
    if width in _INT_DTYPES:
        return a if int(a) >= int(b) else b
    return _ieee_minmax(a, b, width, want_min=False)


def absolute(a):
    """``abs``, in the argument's type; the minimum integer's
    magnitude does not fit and is an IntegerOverflow."""
    width = width_of(a)
    if width in _INT_DTYPES:
        return fit_int(abs(int(a)), width)
    if width in _REAL_DTYPES:
        return convert(math.fabs(float(a)), width)
    raise ValueError(f"no abs of {a!r}")


# The library functions fold with the host's binary64 library (Python's
# math module, the platform's libm) on arguments already converted and
# rounded to their width, and the result is converted once to the
# expression's width (user manual, Numerical semantics: Library
# functions).  sqrt is correctly rounded everywhere; for a binary32
# argument the binary64 square root rounded to binary32 is the
# correctly rounded binary32 square root.
_LIBRARY = {
    'sqrt': math.sqrt, 'exp': math.exp, 'log': math.log,
    'sin': math.sin, 'cos': math.cos, 'tan': math.tan, 'tanh': math.tanh,
}


def _ieee_result(np_function, *args):
    """The IEEE 754 value of ``np_function`` on ``args`` where the math
    module raised: NaN for a domain error (``sqrt(-1.0)``, ``log(-1.0)``),
    a signed infinity for a pole or an overflow (``log(0.0)``,
    ``exp(1000.0)``)."""
    with np.errstate(all='ignore'):
        return float(np_function(*[np.float64(float(a)) for a in args]))


def library(name, a):
    """A library function of one argument (see ``_LIBRARY`` above): the
    host's binary64 library on the argument's value, rounded once to the
    argument's width.  Where the library raises (a domain error, a pole,
    an overflow) the result is the IEEE 754 special value, which
    ``_finite`` reports as the exception outside ``ieee_special_values``
    and returns inside it."""
    width = real_width_of(width_of(a))
    try:
        result = _LIBRARY[name](float(a))
    except (ValueError, OverflowError):
        result = _ieee_result(getattr(np, name), a)
    return convert(_finite(result, a), width)


def atan2(a, b):
    """``atan2`` of two arguments, in their common real width."""
    width = real_width_of(_result_width(a, b))
    return convert(math.atan2(float(a), float(b)), width)


_int_div = int_div


def _require_bool(value, what):
    if not _is_bool(value):
        raise ValueError(f"{what} needs a bool operand, got {value!r}")
    return bool(value)


_BINARY = {'+': add, '-': sub, '*': mul, '/': divide, '^': power}


def binary(operator, a, b):
    """The arithmetic operator ``operator`` (one of ``+ - * / ^``) on
    two values."""
    return _BINARY[operator](a, b)


def intrinsic(name, args):
    """A scalar intrinsic or a conversion of constant arguments."""
    for a in args:
        if isinstance(a, list):
            raise ValueError(f"{name}() of an array cannot be evaluated here")
    if name in _INT_DTYPES or name in _REAL_DTYPES or name == 'bool':
        if len(args) != 1:
            raise ValueError(f"{name}() takes one argument")
        return convert(args[0], name)
    if name in _LIBRARY:
        (a,) = args
        return library(name, a)
    if name == 'abs':
        (a,) = args
        return absolute(a)
    if name in ('min', 'max', 'mod', 'atan2'):
        a, b = args
        return {'min': minimum, 'max': maximum,
                'mod': truncated_mod, 'atan2': atan2}[name](a, b)
    raise ValueError(f"intrinsic {name}() cannot be evaluated at compile time")


_intrinsic = intrinsic


def eval_const_expr(expr, bindings=None, *, ast=None, lattice_info=None):
    """Evaluate an AST expression to an int, a float or a bool.

    Values of the default widths are Python's int and float; a value
    converted to or declared with a narrower width (``real32``, ``int8``
    ...) is a NumPy scalar of that width, so that rounding and wrapping
    match the generated code.  Comparisons give a Python bool.

    Parameters
    ----------
    expr : AST node
        The expression to evaluate.
    bindings : dict, optional
        Maps identifier names to Python values (for function
        parameter substitution during conditional paint evaluation).
    ast : Program_N, optional
        The program AST, used to look up global constants.
    lattice_info : dict, optional
        Lattice metadata from ``collect_lattice_info()``, used to
        resolve implicit dimension constants (Nx, Ny, Nz).
    """
    if bindings is None:
        bindings = {}
    e = lambda node: eval_const_expr(
        node, bindings, ast=ast, lattice_info=lattice_info)

    if isinstance(expr, (IntLiteral_N, RealLiteral_N)):
        return _literal_value(expr)
    if isinstance(expr, BoolLiteral_N):
        return expr.value == 'true'

    if isinstance(expr, Add_N):
        return add(e(expr.left), e(expr.right))
    if isinstance(expr, Sub_N):
        return sub(e(expr.left), e(expr.right))
    if isinstance(expr, Mul_N):
        return mul(e(expr.left), e(expr.right))
    if isinstance(expr, Div_N):
        return divide(e(expr.left), e(expr.right))
    if isinstance(expr, Pow_N):
        return power(e(expr.left), e(expr.right))

    if isinstance(expr, Less_N):
        return bool(e(expr.left) < e(expr.right))
    if isinstance(expr, Greater_N):
        return bool(e(expr.left) > e(expr.right))
    if isinstance(expr, LessEqual_N):
        return bool(e(expr.left) <= e(expr.right))
    if isinstance(expr, GreaterEqual_N):
        return bool(e(expr.left) >= e(expr.right))
    if isinstance(expr, Equal_N):
        return bool(e(expr.left) == e(expr.right))
    if isinstance(expr, NotEqual_N):
        return bool(e(expr.left) != e(expr.right))

    if isinstance(expr, And_N):
        left = _require_bool(e(expr.left), "'&&'")
        return left and _require_bool(e(expr.right), "'&&'")
    if isinstance(expr, Or_N):
        left = _require_bool(e(expr.left), "'||'")
        return left or _require_bool(e(expr.right), "'||'")
    if isinstance(expr, NotExpr_N):
        return not _require_bool(e(expr.value), "'!'")

    if isinstance(expr, TypePromotionNode_N):
        # a promoted array converts element by element
        return _typed(e(expr.expr), expr.target_type)

    if isinstance(expr, UserFunctionCall_N):
        func = find_function(ast, expr.function_name.name)
        params = [p.name.name for p in func.inputs.elements]
        args = [e(a) for a in expr.arguments.elements]
        if len(args) != len(params):
            raise ValueError(
                f"function '{func.name.name}' expects {len(params)} "
                f"arguments, got {len(args)}")
        return eval_function_body(ast, func, dict(zip(params, args)),
                                  lattice_info=lattice_info)

    if isinstance(expr, IntrinsicFunctionCall_N):
        return intrinsic(str(expr.function_name),
                         [e(a) for a in expr.arguments.elements])

    if isinstance(expr, Array1DLiteral_N):
        return [e(el) for el in expr.value]

    if isinstance(expr, RectSelOfArrayElems_N):
        base = e(expr.array_name)
        if not isinstance(base, list):
            raise ValueError("indexing a non-array value")
        ranges = expr.element_ranges
        if len(ranges) != 1:
            raise ValueError("only one-dimensional array indexing is supported here")
        r = ranges[0]
        lo = e(r.low)
        if r.high is not None and r.high is not r.low and e(r.high) != lo:
            raise ValueError("array slices cannot be evaluated here; index one element")
        return base[lo]

    if isinstance(expr, UnaryMinusExpr_N):
        return negate(e(expr.value))

    if isinstance(expr, Identifier_N):
        name = expr.name
        if name in bindings:
            return bindings[name]
        if name in _DIM_SIZE_NAMES and lattice_info is not None:
            dim_idx = _DIM_SIZE_NAMES.index(name)
            return get_grid_size(lattice_info, dim_idx, ast=ast)
        if ast is not None and ast.global_constants is not None:
            for stmt in ast.global_constants.stmts:
                if isinstance(stmt, ConstantDefinitionStmt_N) and \
                        stmt.name.name == name:
                    # a global constant sees no local bindings, and
                    # has the width it is declared with
                    return _typed(eval_const_expr(
                        stmt.value, {}, ast=ast, lattice_info=lattice_info),
                        stmt.data_type)
        raise ValueError(
            f"Cannot evaluate identifier '{name}' in constant expression")

    raise ValueError(
        f"Cannot evaluate expression type {type(expr).__name__}")
