"""Immutable computational types, independent of the AST's shape spelling."""

from dataclasses import dataclass
from math import prod


@dataclass(frozen=True)
class CanonicalType:
    dtype: str
    dims: tuple[int, ...]

    def __post_init__(self):
        object.__setattr__(self, 'dtype', {'int64': 'int', 'real64': 'real'}.get(self.dtype, self.dtype))
        if self.dtype not in {'bool', 'int8', 'int16', 'int32', 'int', 'real32', 'real'}:
            raise ValueError(f'unknown computational type: {self.dtype}')
        if not isinstance(self.dims, tuple) or any(type(n) is not int or n <= 0 for n in self.dims):
            raise ValueError('dimensions must be a tuple of positive Python integers')

    @property
    def is_scalar(self):
        return self.dims == ()

    @property
    def is_array(self):
        return bool(self.dims)

    @property
    def rank(self):
        return len(self.dims)

    @property
    def size(self):
        return prod(self.dims)


def canonical_from_ast(data_type, evaluate=None):
    """Read a type without rewriting it; unresolved shapes have no type yet."""
    from gelb.gelb_ast.ASTNodes import ArrayDataType_N, Array1DLiteral_N, IntLiteral_N, List_N
    if not isinstance(data_type, ArrayDataType_N):
        return None
    shape = data_type.shape
    if isinstance(shape, Array1DLiteral_N):
        shape = shape.value
    extents = () if shape is None else shape.elements if isinstance(shape, List_N) else (shape,)
    dims = []
    for extent in extents:
        if isinstance(extent, IntLiteral_N):
            value = extent.value
        elif evaluate is not None:
            value = evaluate(extent)
        else:
            return None
        # The evaluator may return a NumPy integer; bool and real extents
        # are not integer dimensions, even when numerically integral.
        from numbers import Integral
        if isinstance(value, bool) or not isinstance(value, Integral):
            if evaluate is None:
                return None
            raise ValueError('array extent is not an integer')
        dims.append(int(value))
    try:
        return CanonicalType(data_type.element_dtype, tuple(dims))
    except ValueError:
        # Construction precedes user-facing type validation. Leave invalid
        # declarations for that validator; stage-boundary checks are strict.
        if evaluate is not None:
            raise
        return None
