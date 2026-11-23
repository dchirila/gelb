"""Coordinates and halo storage addresses, resolved before C++ rendering."""

from dataclasses import dataclass, replace

from gelb.backends.highway.common import _lname, _CBT_TILE


@dataclass(frozen=True)
class ConstCoord:
    value: int

    def __str__(self):
        return str(self.value)

    def storage(self):
        return str(self.value + 1)


@dataclass(frozen=True)
class ExprCoord:
    text: str

    def __str__(self):
        return self.text

    def storage(self):
        return f'({self}) + 1'


@dataclass(frozen=True)
class AxisOffset:
    axis: str
    offset: int = 0
    size: int = 0
    periodic: bool = False
    policy: str = 'plain'
    subtract: bool = False

    def resolve(self, bindings):
        if self.axis not in bindings:
            return self
        value = bindings[self.axis] + self.offset
        # Bound periodic accesses always use the interior, including
        # one-cell reads which could otherwise use a ghost cell.
        if self.periodic:
            value %= self.size
        elif self.policy == 'clamp':
            value = max(0, min(self.size - 1, value))
        return ConstCoord(value)

    def __str__(self):
        base = f'g_{self.axis}'
        if not self.offset:
            return base
        op, offset = ('-', -self.offset) if self.subtract else ('+', self.offset)
        inner = f'{base} {op} ({offset})'
        if self.policy == 'wrap':
            return f'((({inner}) % {self.size} + {self.size}) % {self.size})'
        if self.policy == 'clamp':
            return (f'(({inner} < 0) ? 0 : '
                    f'(({inner} >= {self.size}) ? {self.size - 1} : ({inner})))')
        return f'({inner})'

    def storage(self):
        return f'({self}) + 1'


def spatial_subscript(coords):
    return ''.join(f'[{c.storage()}]' for c in reversed(coords))


@dataclass(frozen=True)
class LatticeAddress:
    lattice: str
    buffer: str
    coords: tuple
    df: str | None
    layout: str = 'soa'
    aligned_tile_start: bool = False

    def aligned(self):
        return replace(self, aligned_tile_start=True)

    def subscript(self):
        if self.df is None:
            return spatial_subscript(self.coords)
        if self.layout == 'cbt':
            x = self.coords[0]
            storage = x.storage()
            tile = str((x.value + 1) // _CBT_TILE) if isinstance(x, ConstCoord) else f'({storage}) / {_CBT_TILE}'
            lane = str((x.value + 1) % _CBT_TILE) if isinstance(x, ConstCoord) else f'({storage}) % {_CBT_TILE}'
            if self.aligned_tile_start:
                lane = '0'
            return f'{spatial_subscript(self.coords[1:])}[{tile}][{self.df}][{lane}]'
        spatial = spatial_subscript(self.coords)
        return f'{spatial}[{self.df}]' if self.layout == 'aos' else f'[{self.df}]{spatial}'

    def __str__(self):
        return f'{_lname(self.lattice)}_storage[{self.buffer}]{self.subscript()}'
