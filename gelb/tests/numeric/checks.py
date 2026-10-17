"""Mismatch diagnostics shared by pipeline and runtime checks."""

import struct


class NumericMismatch(AssertionError):
    """Only a validated numerical mismatch, never a compiler/build failure."""


def _ordered_bits(value, dtype):
    floating, integer, sign = (">f", ">I", 1 << 31) if dtype == "float" else (">d", ">Q", 1 << 63)
    bits = struct.unpack(integer, struct.pack(floating, value))[0]
    return sign - bits if bits & sign else sign + bits


def check_values(actual, expected, *, case, context, source, ulps=0):
    actual, expected = list(actual), list(expected)
    def matches(a, e):
        if struct.pack(">d", float(a)) == struct.pack(">d", float(e)):
            return True
        # A NaN's sign and payload are unspecified: any NaN matches
        # any NaN; a zero's sign is compared by the bits above.
        if float(a) != float(a) and float(e) != float(e):
            return True
        # Preserve signed-zero checks even on paths allowing reassociation.
        return (ulps > 0 and a != 0 and e != 0
                and abs(_ordered_bits(a, case.cpp_type) - _ordered_bits(e, case.cpp_type)) <= ulps)

    if len(actual) == len(expected) and all(matches(a, e) for a, e in zip(actual, expected)):
        return
    raise NumericMismatch(
        f"{case.name} / {context}\n"
        f"C++: {case.expression}\ninput: {case.cpp_type} u = {case.initial}\nULP budget: {ulps}\n"
        f"expected: {expected}\nactual:   {actual}\n"
        f"expected hex: {[float(v).hex() for v in expected]}\n"
        f"actual hex:   {[float(v).hex() for v in actual]}\n"
        f"GeLB reproducer:\n{source}")
