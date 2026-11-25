"""Typed values of cpu_highway expression emission.

An emitted expression carries how its C++ value is held: one value for
the whole vector iteration (``scalar``), a ``V`` with one binary64 value
per cell (``vec``), or an ``hn::Mask<D>`` with one truth value per cell
(``mask``).  Outside a vector body every value is ``scalar``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


class ScalarFallbackRequired(Exception):
    """The block has no vector form: it is emitted once, as scalar code."""


@dataclass(frozen=True)
class EmittedValue:
    """C++ source of an expression with the type it was emitted in.

    ``code`` keeps a ``ConstantOperand`` as it is, so the exact value of
    a scalar constant stays readable by the folding rules.  ``dtype`` is
    the GeLB element type of the node the source was written for (None
    when it carries none) and ``cpp_type`` the C++ type of one element of
    that type.  ``vec_int_origin`` is set
    on the two ``int`` values a vector holds exactly as binary64: the
    coordinate x (``coord_x``) and the integer of a per-cell truth value
    (``bool_int_cast``); a local declared from one of them reads back as
    ``local``.
    """
    code: str
    dtype: str | None
    cpp_type: str
    lane_kind: Literal['scalar', 'vec', 'mask'] = 'scalar'
    vec_int_origin: Literal['coord_x', 'bool_int_cast', 'local'] | None = None


class SimdSymbolEnv:
    """How each local of the block being emitted is held in a vector body.

    ``vec``: a ``V`` (a real scalar, a gauge output) or a ``V[N]`` (a
    real array); ``mask``: an ``hn::Mask<D>`` (a scalar ``bool``);
    ``vec_int``: a ``V`` holding an ``int`` declared from x or from the
    integer of a per-cell truth value, never assigned again; ``scalar``:
    an ``int64_t``, an ``int64_t[N]`` or a ``bool[N]``, one value for all
    cells of the iteration.  Empty outside a vector body.
    """

    def __init__(self) -> None:
        self._carriers: dict[str, str] = {}

    def declare(self, name: str, carrier: str) -> None:
        assert carrier in ('vec', 'mask', 'vec_int', 'scalar'), carrier
        self._carriers[name] = carrier

    def carrier(self, name: str) -> str | None:
        return self._carriers.get(name)

    def __len__(self) -> int:
        return len(self._carriers)
