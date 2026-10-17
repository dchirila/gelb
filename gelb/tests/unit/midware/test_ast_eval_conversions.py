"""Integer-to-real conversions round once, to the target width (user
manual, Numerical semantics: Types and promotion): 2^54 + 2^30 + 1 lies
just above a binary32 midpoint; through binary64 it would land on the
midpoint and the tie would round down."""

import numpy as np

from gelb.midware.ast_eval import convert_plain, narrow_scalar

_ABOVE_MIDPOINT = 2 ** 54 + 2 ** 30 + 1


def _direct_float32(value):
    """The C cast int64 -> float, which NumPy's array cast performs."""
    return float(np.array([value], dtype=np.int64).astype(np.float32)[0])


def test_an_integer_converts_to_real32_directly():
    expected = _direct_float32(_ABOVE_MIDPOINT)
    assert expected == 2.0 ** 54 + 2.0 ** 31             # rounded up
    assert float(np.float32(float(_ABOVE_MIDPOINT))) == 2.0 ** 54   # the double-rounding value
    assert convert_plain(_ABOVE_MIDPOINT, 'real32') == expected
    assert narrow_scalar(_ABOVE_MIDPOINT, 'real32') == expected
    assert convert_plain(-_ABOVE_MIDPOINT, 'real32') == -expected


def test_a_real_value_still_rounds_once_from_binary64():
    assert convert_plain(0.1, 'real32') == float(np.float32(0.1))
    assert convert_plain(2 ** 53 + 1, 'real') == float(2 ** 53 + 1)   # Python's own rounding
