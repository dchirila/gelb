"""A reproducible C++ expression corpus and a deliberately small translator.

The oracle compiles the C++ source below, never a GeLB AST or generated backend
file. This parser translates only our documented C++ subset; it rejects any
unrecognized syntax rather than guessing at its semantics.
"""

import os
import random
import re
from dataclasses import dataclass

SEED = 0xD13D17
CPP_TYPES = {
    "float": "real32", "double": "real", "int8_t": "int8",
    "int16_t": "int16", "int32_t": "int32", "int64_t": "int",
}
_TOKEN = re.compile(
    r"\s*(?:(?P<number>(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][+-]?\d+)?(?:LL|f)?)"
    r"|(?P<word>[A-Za-z_]\w*)|(?P<op>==|!=|<=|>=|[()+*/<>,-]))")
_PRECEDENCE = {"==": 1, "!=": 1, "<": 2, "<=": 2, ">": 2, ">=": 2,
               "+": 3, "-": 3, "*": 4, "/": 4}
_INTRINSICS = {"gelb_min": "min", "gelb_max": "max"}


def tokens(source):
    result, pos = [], 0
    source = source.strip()
    while pos < len(source):
        match = _TOKEN.match(source, pos)
        if match is None:
            raise ValueError(f"unsupported C++ syntax at {source[pos:]!r}")
        result.append(match.group(match.lastgroup))
        pos = match.end()
    return result


def translate(source, names=None, hoist=None):
    """Translate literals, named inputs, casts, parentheses and binary ops.

    ``hoist`` optionally names constant casts and literal floats in a GeLB
    constants block. This permits local-array initializers to use them without
    depending on backend support for an unfolded real32() intrinsic.
    """
    stream, pos = tokens(source), 0
    names = {"u": "u", "x": "x"} if names is None else names

    def take(expected=None):
        nonlocal pos
        if pos == len(stream):
            raise ValueError("incomplete C++ expression")
        value = stream[pos]
        if expected is not None and value != expected:
            raise ValueError(f"expected {expected!r}, got {value!r}")
        pos += 1
        return value

    def primary():
        value = take()
        if value in ("+", "-"):
            return f"({value}{primary()})"
        if value == "(":
            inner = expression(0)
            take(")")
            return f"({inner})"
        if value == "static_cast":
            take("<")
            dtype = take()
            if dtype not in CPP_TYPES:
                raise ValueError(f"unsupported C++ cast {dtype!r}")
            take(">")
            take("(")
            begin = pos
            inner = expression(0)
            constant = not any(t in names for t in stream[begin:pos])
            take(")")
            if hoist is not None and constant:
                return hoist(CPP_TYPES[dtype], inner)
            return f"{CPP_TYPES[dtype]}({inner})"
        if re.fullmatch(r"(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][+-]?\d+)?(?:LL|f)?", value):
            if value.endswith("f"):
                if hoist is not None:
                    return hoist("real32", value[:-1])
                return f"real32({value[:-1]})"
            return value.removesuffix("LL")
        if value in names:
            return f"({names[value]})"
        if value in _INTRINSICS:
            # gelb_min(a, b) / gelb_max(a, b): GeLB's min / max, defined in
            # the oracle by the manual's words (Numerical semantics, Types
            # and promotion: IEEE 754-2019 minimum / maximum).
            take("(")
            first = expression(0)
            take(",")
            second = expression(0)
            take(")")
            return f"{_INTRINSICS[value]}({first}, {second})"
        raise ValueError(f"unsupported C++ input/token {value!r}")

    def expression(minimum):
        left = primary()
        while pos < len(stream) and _PRECEDENCE.get(stream[pos], -1) >= minimum:
            op = take()
            right = expression(_PRECEDENCE[op] + 1)
            left = f"({left} {op} {right})"
        return left

    result = expression(0)
    if pos != len(stream):
        raise ValueError(f"unconsumed C++ tokens: {stream[pos:]}")
    return result


@dataclass(frozen=True)
class Case:
    name: str
    expression: str
    initial: str = "1.1"
    cpp_type: str = "float"
    runtime: bool = True
    reassociation_ulps: int = 0
    cells: int = 4          # lattice size; 1 collapses the axis, 67 enters Highway's SIMD body with a tail
    constant: bool = True   # also checked as a folded constant and a where-predicate (not for a non-finite input)
    scalar_only: bool = False   # min/max take scalars: the array surfaces broadcast the scalar form

    @property
    def gelb_type(self):
        return CPP_TYPES[self.cpp_type]


def corpus(seed=SEED, random_count=32):
    """Boundary anchors plus seeded compositions; no undefined C++ arithmetic.

    Integer arithmetic stays within int64, divisors are nonzero, and no cast
    converts an out-of-range float to integer. Native operations, including
    their intermediate rounding, supply the expected result.
    """
    if random_count < 0:
        raise ValueError("GELB_NUMERIC_RANDOM_CASES must be nonnegative")
    cases = [
        Case("double_literal", "0.1 * u"),
        Case("narrow_composite", "3.0 * (u * u)", "2.3"),
        Case("integer_conversion", "u * (x + 16777217LL)", "0.5"),
        Case("negative_integer_conversion", "u * (x - 16777217LL)", "0.5"),
        Case("integer_quotient", "u * ((x - 7LL) / 2LL)", "0.5"),
        # Literal conversion before algebra; the minimum int64 literal (a
        # native literal must carry its kind, and the minimum is spelled
        # as the negative maximum minus one); int64 coordinate arithmetic
        # (x is int64 throughout, collapsed axes and SIMD included).
        Case("literal_conversion_before_algebra", "(u + 16777217LL) - 16777216LL", "0.0"),
        Case("minimum_int64", "u * (-9223372036854775807LL - 1LL)", "0.5", "double"),
        Case("coordinate_sum", "u + (x + 2147483647LL)", "0.0", "double"),
        Case("coordinate_product", "u + x * 1073741824LL", "0.0", "double"),
        # Direct integer-to-real32 rounding above a binary32
        # midpoint, literal terms never combined across a variable, a
        # collapsed axis, and the SIMD body with a scalar tail.
        Case("literal_double_round", "u * 18014399583223809LL", "0.5"),
        Case("promoted_double_round", "u + 18014399583223809LL", "0.0"),
        Case("cast_double_round", "static_cast<float>(18014399583223809LL)", runtime=False),
        Case("cancellation_nonzero", "(u + 16777217LL) - 16777216LL", "0.5"),
        Case("coordinate_sum_singleton", "u + ((x + 2147483647LL) + 1LL)", "0.0", "double", cells=1),
        Case("coordinate_sum_simd", "u + (x + 2147483647LL)", "0.0", "double", cells=67),
        Case("coordinate_division_simd", "u + ((x - 7LL) / 2LL)", "0.0", "double", cells=67),
        # A shared real32 subtree keeps its width; a real zero
        # keeps its sign (u*0.0 is -0 for u = -1, u + 0.0 is +0 for
        # u = -0, 0.0 - u is +0 for u = +0), and an exact cancellation
        # of two negated operands is +0.
        Case("repeated_narrow_square", "3.0 * ((u * u) * (u * u))", "1.1"),
        Case("repeated_narrow_sum", "(((u * u) * u) + (u * u)) * 0.1", "2.3"),
        Case("zero_product_sign", "u * 0.0", "-1.0", "double"),
        Case("zero_product_sign_float", "u * 0.0f", "-1.0"),
        Case("zero_sum_sign", "u + 0.0", "-0.0", "double"),
        Case("zero_difference_sign", "0.0 - u", "0.0", "double"),
        Case("negated_cancellation", "(-u) + (-(0.0 - u))", "0.5", "double"),
        Case("float_chain", "(u * 0.1f) * 0.1f", "1.3"),
        Case("real_alias", "(static_cast<double>(u) + 1.0) - static_cast<double>(u)", "16777216.0", runtime=False),
        Case("plain_widening", "(u + 1.0) - u", "16777216.0"),
        Case("float_add_boundary", "u + (x + 1LL)", "16777216.0"),
        Case("comparison_conversion", "(x + 16777217LL) == 16777216.0f"),
        Case("signed_division", "(static_cast<int8_t>(-7LL) / static_cast<int16_t>(2LL)) * 2LL"),
        Case("positive_division", "(static_cast<int8_t>(7LL) / static_cast<int16_t>(2LL)) * 2LL"),
        Case("negative_divisor", "(7LL / -2LL) * 2LL"),
        Case("int32_real_division", "static_cast<int32_t>(7LL) / 2.0"),
        Case("nested_constant_cast", "static_cast<double>(static_cast<float>(16777217.0))"),
        Case("explicit_input_narrowing", "static_cast<double>(static_cast<float>(u))", "16777217.0", "double", False),
        Case("double_exact_integer", "u + x", "9007199254740992.0", "double"),
        Case("double_integer_conversion", "u * (x + 9007199254740993LL)", "0.5", "double"),
        Case("negative_zero", "u * 1.0", "-0.0"),
        Case("small_float", "u * 0.5f", "1.1754943508222875e-38"),
    ]
    # Special values (user manual, Numerical semantics: Special values):
    # an infinite, a NaN and a negative-zero input through the arithmetic,
    # a comparison, and the IEEE minimum / maximum, at run time only: the
    # folder leaves a non-finite result to run time, so the constant forms
    # do not apply.
    inf, nan = "1.0e308 * 10.0", "(1.0e308 * 10.0) - (1.0e308 * 10.0)"
    for name, expression, initial, cpp_type in (
            ("inf_times_zero", "u * 0.0", inf, "double"),
            ("inf_minus_inf", "u - u", inf, "double"),
            ("inf_plus_one", "u + 1.0", inf, "double"),
            ("inf_times_negative", "u * (-2.0)", inf, "double"),
            ("one_over_inf", "1.0 / u", inf, "double"),
            ("one_over_negative_zero", "1.0 / u", "-0.0", "double"),
            ("negative_zero_product", "u * 3.0", "-0.0", "double"),
            ("negative_zero_sum", "u + u", "-0.0", "double"),
            ("nan_propagates", "u + 1.0", nan, "double"),
            ("nan_compares_unequal", "u == u", nan, "double"),
            ("min_with_nan", "gelb_min(u, 1.0)", nan, "double"),
            ("max_with_nan_second", "gelb_max(1.0, u)", nan, "double"),
            ("min_mixed_zeros", "gelb_min(u, 0.0)", "-0.0", "double"),
            ("min_zero_first", "gelb_min(0.0, u)", "-0.0", "double"),
            ("max_mixed_zeros", "gelb_max(u, 0.0)", "-0.0", "double"),
            ("inf_times_zero_float", "u * 0.0f", "1.0e38f * 10.0f", "float"),
            ("negative_zero_float", "u * 0.5f", "-0.0f", "float"),
            ("min_with_nan_float", "gelb_min(u, 1.0f)", "(1.0e38f * 10.0f) - (1.0e38f * 10.0f)", "float")):
        cases.append(Case(name, expression, initial, cpp_type, constant=False,
                          scalar_only="gelb_m" in expression))
    # Exercise both sides of the float32 exact-integer boundary and signs.
    for i, value in enumerate((16777215, 16777216, 16777217, 16777218, -16777217)):
        cases.append(Case(f"store_boundary_{i}", "u", f"{value}.0"))
    # All signed width pairs and sign combinations. Values fit every type:
    # C++ integer promotions differ from GeLB's narrow-integer rules, but
    # these operands cannot overflow either intermediate representation.
    for left_width in (8, 16, 32, 64):
        for right_width in (8, 16, 32, 64):
            for a, b in ((7, 2), (-7, 2), (7, -2), (-7, -2)):
                name = f"division_i{left_width}_i{right_width}_{a}_{b}"
                expr = f"static_cast<int{left_width}_t>({a}LL) / static_cast<int{right_width}_t>({b}LL)"
                cases.append(Case(name, expr, runtime=False))
    for width in (8, 16, 32, 64):
        for value in ("3.9", "-3.9"):
            cases.append(Case(f"truncate_i{width}_{value}",
                              f"static_cast<int{width}_t>({value})", runtime=False))
    rng = random.Random(seed)
    small = ("0.1", "0.3", "0.5", "1.1", "1.3", "2.3", "3.0")
    integers = ("2LL", "7LL", "16777215LL", "16777217LL")
    for index in range(random_count):
        a, b, k = rng.choice(small), rng.choice(small), rng.choice(integers)
        initial = rng.choice(small)
        forms = (
            f"{a} * u", f"{a} * (u * u)", f"u * (x + {k})",
            f"(u + {a}f) * {b}f", f"(u * {a}f) / {b}f",
            f"((u * 1.0) * u) + {a}",
            "u * ((x - 7LL) / 2LL)",
            f"(u + {a}) / {b}",
        )
        # Cycle families so every seed covers every operation category.
        family = index % len(forms)
        # The optimizer is exact against the unsimplified form;
        # no family carries a reassociation budget any more.
        cases.append(Case(f"seed_{seed:x}_{index:03d}", forms[family], initial))
    return tuple(cases)


ACTIVE_SEED = int(os.environ.get("GELB_NUMERIC_SEED", str(SEED)), 0)
RANDOM_COUNT = int(os.environ.get("GELB_NUMERIC_RANDOM_CASES", "32"))
CASES = corpus(ACTIVE_SEED, RANDOM_COUNT)


def oracle_source(cases):
    blocks = []
    for case in cases:
        blocks.append(f"""{{
  volatile {case.cpp_type} u = {case.initial};
  for (int64_t x = 0; x < {case.cells}; ++x) {{
    const double raw = static_cast<double>({case.expression});
    const {case.cpp_type} stored = ({case.expression});
    std::cout << "{case.name} " << x << " " << std::hexfloat
              << raw << " " << static_cast<double>(stored) << " "
              << (static_cast<double>(u) + 0.0) << "\\n";
  }}
}}""")
    return """#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
static_assert(sizeof(float) == 4 && sizeof(double) == 8);
static_assert(std::numeric_limits<float>::is_iec559 && std::numeric_limits<double>::is_iec559);
// GeLB's min / max of reals, from the manual's words: IEEE
// 754-2019 minimum / maximum -- a NaN operand gives NaN, -0 < +0.
template <typename T> T gelb_min(T a, T b) {
    if (std::isnan(a) || std::isnan(b)) return std::numeric_limits<T>::quiet_NaN();
    if (a == b) return std::signbit(a) ? a : b;
    return a < b ? a : b;
}
template <typename T> T gelb_max(T a, T b) {
    if (std::isnan(a) || std::isnan(b)) return std::numeric_limits<T>::quiet_NaN();
    if (a == b) return std::signbit(a) ? b : a;
    return a > b ? a : b;
}
int main() {
""" + "\n".join(blocks) + "\n}\n"


def runtime_source(cases):
    """Batch cases into one run; four observation paths per case at t=1.
    The cases share one lattice size (``cells``)."""
    (cells,) = {case.cells for case in cases}
    constants, lattices, init, dynamic, outputs, gauge = [], [], [], [], [], []
    for index, case in enumerate(cases):
        constant_names = {}

        def hoist(dtype, expression, constant_names=constant_names, index=index):
            key = (dtype, expression)
            if key not in constant_names:
                name = f"K{index}F{len(constant_names)}"
                constant_names[key] = name
                constants.append(f"const {dtype} {name} = {expression};")
            return constant_names[key]

        lattice = f"a{index}"
        lattices.append(f"lattice {lattice}(1,9,{case.gelb_type},{cells},false);")
        init.append(f"{lattice}.out[x | :] = {translate(case.initial, {})};")
        scalar = translate(case.expression, {"u": f"{lattice}.in[x | 0]", "x": "x"}, hoist=hoist)
        vector = (scalar if case.scalar_only else
                  translate(case.expression, {"u": f"{lattice}.in[x | :]", "x": "x"}, hoist=hoist))
        dynamic.extend([
            f"array[{case.gelb_type},9] tmp{index} = {vector};",
            f"array[{case.gelb_type},9] assigned{index};",
            f"assigned{index} = {vector};",
            f"{lattice}.out[x | :] = {vector};",
            f"{lattice}.out[x | 0] = {scalar};",
            f"{lattice}.out[x | 2] = tmp{index}[2];",
            f"{lattice}.out[x | 3] = assigned{index}[3];",
        ])
        for direction, surface in enumerate(("scalar", "slice", "declaration", "assignment")):
            name = f"case{index}_{surface}"
            outputs.append(f"real {name}")
            gauge.append(f"{name} = {lattice}.in[x | {direction}];")
    return "\n".join([
        'simulation_description("generated numeric conformance");',
        "global_constants {" + "\n".join(constants) + "}" if constants else "",
        "lattices {" + "\n".join(lattices) + "}",
        "initializer I {" + "\n".join(init) + "}",
        "dynamic D {" + "\n".join(dynamic) + "}",
        "gauge G -> (" + ", ".join(outputs) + ") {" + "\n".join(gauge) + "}",
        "node_classes {node_class BULK(I,D,G);}",
        "geometry {nodes[:] = BULK;}",
    ])
