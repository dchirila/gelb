"""A local constant may refer to other constants, not to x, y, z or t.

A ``const`` statement inside an initializer, a dynamic or a gauge takes a
constant value and keeps its declared type (user manual, chapter 3,
Reserved implicit symbols and Types).  A chain of local constants,
``const int START = 2; const int END = START + 3;``, is legal, compiles
on every backend, and folds with the declared types (``const real P =
7;`` makes ``P / 2`` a real division, as for a global constant).  A local
constant initialized from an implicit variable, directly or through a
function argument, a cast, an array literal or a lattice read, is
rejected with a located error that names that variable.  The check used
to reject every symbol referenced by a local constant as soon as the
block used a coordinate anywhere, named the coordinate instead of the
offending symbol, so the message changed from run to run, and the
compile-time value of a local constant had the type of its initializer.
"""
import click
import pytest

from gelb.frontend.stage1_frontend import (
    get_ast, prevent_clashes_of_symbol_refs_with_implicits)
from gelb.tests.integration.test_tutorial_regressions import BACKENDS, run_source
from gelb.tests.test_utils import (
    get_typed_ast, minimal_gelb_program_2d, minimal_gelb_program_3d)
from gelb.utils import config
from gelb.utils.exceptions import GeLBExSymbolNotAllowedHere, GeLBExTypeError

CHAIN = """
simulation_description("chains of local constants");
global_constants { const int BASE = 2; }
lattices { lattice f(2, 9, real, {16, 4}, {true, true}); }
initializer Init {
    const int K = BASE * 3;
    f.out[x, y | :] = real(K);
    f.out[x, y | 2:5] = {10.0, 20.0, 30.0, 40.0};
    f.out[x, y | 7] = 70.0;
}
dynamic Step {
    const int LO = BASE;
    const int HI = LO + 3;
    f.out[x, y | :] = f.in[x, y | :];
    f.out[x, y | LO:HI] = f.in[x, y | LO:HI] * 2.0;
}
gauge G -> (real s, real slice, real typed, real narrow) {
    const int START = BASE;
    const int END = START + 3;
    const real SCALE = real(END - START) * 0.5;
    s = f.in[x, y | 0] * SCALE;
    array[real, 4] v = f.in[x, y | START:END];
    slice = sum(v);
    const real P = 7;
    const int IDX = int((P / 2) * 2);
    typed = f.in[x, y | IDX];
    const int32 LO32 = 2;
    const int32 HI32 = 5;
    const int16 I16 = 1;
    const array[real, 3] A = {10.0, 20.0, 30.0};
    narrow = sum(f.in[x, y | LO32:HI32]) + f.in[x, y | int8(7)] + A[I16];
}
node_classes { node_class BULK(Init, Step, G); }
geometry { nodes[:, :] = BULK; }
"""


def _check(source):
    config.GELB_SRC_RAW = source
    prevent_clashes_of_symbol_refs_with_implicits(get_ast("gelb_program", source))


@pytest.mark.parametrize("block", ["initializer_content", "dynamic_content", "gauge_content"])
def test_a_local_constant_may_refer_to_another_constant(block):
    body = "const int START = N - 6; const int END = START + 3; "
    body += {"initializer_content": "f.out[x, y | :] = END;",
             "dynamic_content": "f.out[x, y | :] = f.in[x, y | :] + END;",
             "gauge_content": "val = f.in[x, y | 0] + END;"}[block]
    _check(minimal_gelb_program_2d(**{block: body}))
    get_typed_ast(minimal_gelb_program_2d(**{block: body}))


@pytest.mark.parametrize("backend", BACKENDS)
def test_chains_of_local_constants_run(tmp_path, backend):
    data = run_source(tmp_path, backend, CHAIN, timesteps=1)
    assert (data["s"] == 6 * 1.5).all()                 # K = 6, SCALE = (5 - 2) / 2
    assert (data["slice"][0] == 100).all()              # DFs 2..5 at t = 0
    assert (data["slice"][1] == 200).all()              # doubled by Step through LO:HI
    assert (data["typed"] == 70).all()                  # P / 2 is 3.5, IDX = 7, not DF 6
    assert (data["narrow"][0] == 100 + 70 + 20).all()   # int32/int16 constants fold like int ones


@pytest.mark.parametrize(("value", "name"), [
    ("x", "x"), ("y", "y"), ("t", "t"), ("N + x", "x"), ("x + y", "x"), ("2 * y - x", "y"),
    ("F(x)", "x"), ("int(real(y) * 0.5)", "y"), ("f.in[x, y | 1]", "x")])
def test_a_local_constant_from_an_implicit_variable_is_rejected(value, name):
    source = minimal_gelb_program_2d(
        gauge_content=f"const int K = {value}; val = f.in[x, y | 0] + K;").replace(
        "initializer Init", "function F(int a) -> (int r) { r = a + 1; }\n    initializer Init")
    with pytest.raises(GeLBExSymbolNotAllowedHere) as excinfo:
        _check(source)
    assert excinfo.value.symbol_ref.name == name
    assert f"implicit variable {name} for initializing a constant" in click.unstyle(excinfo.value.error)
    assert "Declare K as a variable instead" in click.unstyle(excinfo.value.hint)


def test_an_array_constant_and_a_3d_coordinate_are_rejected():
    source = minimal_gelb_program_2d(
        gauge_content="const array[int, 2] K = {1, y}; val = f.in[x, y | 0] + K[0];")
    with pytest.raises(GeLBExSymbolNotAllowedHere) as excinfo:
        _check(source)
    assert excinfo.value.symbol_ref.name == "y"
    source = minimal_gelb_program_3d(
        gauge_content="const int K = z + 1; val = f.in[x, y, z | 0] + K;")
    with pytest.raises(GeLBExSymbolNotAllowedHere) as excinfo:
        _check(source)
    assert excinfo.value.symbol_ref.name == "z"


def test_the_first_problem_in_source_order_is_reported():
    # An overwrite of x on one line and a bad constant on the next: the
    # overwrite comes first, whatever the hash seed.
    source = minimal_gelb_program_2d(
        gauge_content="x = 1;\n const int K = y;\n val = f.in[x, y | 0] + K;")
    with pytest.raises(GeLBExSymbolNotAllowedHere) as excinfo:
        _check(source)
    assert "overwrite the implicit variable x" in click.unstyle(excinfo.value.error)


@pytest.mark.parametrize("decl", ["const int32 IDX = 99;", "const int8 IDX = 100;", "const int IDX = 99;"])
def test_a_narrow_constant_df_index_outside_the_lattice_is_rejected(decl):
    with pytest.raises(GeLBExTypeError, match="outside lattice"):
        get_typed_ast(minimal_gelb_program_2d(gauge_content=f"{decl} val = f.in[x, y | IDX];"))
