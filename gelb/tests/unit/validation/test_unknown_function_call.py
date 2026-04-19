#!/usr/bin/env python3
"""A call to a name that is neither an intrinsic nor a user-defined
function is an "Unknown function" error at the call.

The name is resolved before the arguments are checked, so a lattice
passed to it, as a wall written with a misspelt intrinsic passes one,
does not hide the real fault behind "Cannot use lattice 'f' directly as
a value".
"""

from gelb.tests.unit.validation.test_native_escapes import (
    _line_of, assert_error_at, diagnostics,
)

_WALL = """\
simulation_description("a D2Q9 channel wall");
global_constants {
    const array[real, 9] EX = {0.0, 1.0, 0.0, -1.0,  0.0, 1.0, -1.0, -1.0,  1.0};
    const array[real, 9] EY = {0.0, 0.0, 1.0,  0.0, -1.0, 1.0,  1.0, -1.0, -1.0};
    const array[real, 9] W  = {4.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0,
                               1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0};
}
lattices { lattice f(2, 9, real, {6, 4}, {true, false}); }
initializer I { f.out[x, y | :] = W; }
dynamic Fluid { f.out[x, y | :] = upstream_dfs(f, x, y, {EX, EY}); }
dynamic Wall { f.out[x, y | :] = no_such_wall(f, x, y, {EX, EY}); }
gauge G -> (real rho) { rho = sum(f.in[x, y | :]); }
node_classes {
    node_class FLUID(I, Fluid, G);
    node_class WALL(I, Wall, G);
}
geometry {
    nodes[:, :] = FLUID;
    nodes[:, 0] = WALL;
    nodes[:, 3] = WALL;
}
"""


def test_an_unknown_call_with_a_lattice_argument_names_the_function(tmp_path):
    error = diagnostics(tmp_path, _WALL)
    assert_error_at(error, _WALL, "no_such_wall(f",
                    "Unknown function 'no_such_wall'")
    line = _WALL.splitlines()[_line_of(_WALL, "no_such_wall(f") - 1]
    assert error["range"]["startCol"] == line.index("no_such_wall(f")
