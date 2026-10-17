"""Strict, enumerated expected failures for diagnosed defects.

None are recorded.  The two former entries -- an integer conversion and
an integer division rebuilt as real arithmetic in optimized slices, and
an int64 literal written without its kind in Fortran -- were fixed and
removed.
The mechanism stays: a diagnosed defect is recorded in
``KNOWN_MISMATCHES`` by case name, C++ expression and input, then by
backend, mode and form, and is marked ``strict=True`` with the narrowest
exception it raises, so a repaired case fails as an unexpected pass
until its entry is removed, and an unrelated build error still fails.
Never bless arbitrary generated cases: a new seed or composition must
stand on its own.  ``--runxfail`` exposes recorded failures while they
are being fixed.
"""

import pytest

from .checks import NumericMismatch

# (case name, C++ expression, input) -> {(backend, mode, form): reason}
KNOWN_MISMATCHES = {}


def mark_known_failure(node, case, backend, mode, surface):
    reasons = KNOWN_MISMATCHES.get((case.name, case.expression, case.initial), {})
    reason = reasons.get((backend, mode, surface))
    if reason is not None:
        node.add_marker(pytest.mark.xfail(
            strict=True, raises=NumericMismatch, reason=reason))


def check_build(result, case, backend):
    """A program that did not build is a failure, never a numerical
    mismatch that an entry above could expect."""
    if "error" in result:
        raise AssertionError(f"{result['source']}\n{result['error']}")
