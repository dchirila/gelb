"""Highway code generation of integer widths: a native literal expresses
its GeLB value and type, and a coordinate is int64 throughout user
expressions, on a collapsed axis too.  No compiler needed, the generated
C++ is inspected."""

from gelb.backends.stage3_backend_cpu_highway import generate_cpu_highway
from gelb.tests.test_utils import get_fully_validated_ast


def _generate(source):
    return generate_cpu_highway(get_fully_validated_ast(source), num_timesteps=1)


_IMPLICIT_INTEGERS = """
simulation_description("implicit integers");
lattices { lattice f(1, 1, real, 4, false); }
initializer Init { f.out[x | 0] = 0.0; }
dynamic Dyn { f.out[x | 0] = f.in[x | 0] + (Nx + t) * 1073741824 + x; }
gauge Out -> (real val) { val = f.in[x | 0]; }
node_classes { node_class BULK(Init, Dyn, Out); }
geometry { nodes[:] = BULK; }
"""

_MINIMUM = """
simulation_description("minimum int64");
lattices { lattice f(1, 1, real, 4, false); }
initializer Init { f.out[x | 0] = 0.5; }
dynamic Dyn { f.out[x | 0] = f.in[x | 0] * (-9223372036854775807 - 1); }
gauge Out -> (real val) { val = f.in[x | 0]; }
node_classes { node_class BULK(Init, Dyn, Out); }
geometry { nodes[:] = BULK; }
"""


def test_coordinates_are_int64_in_the_loops_that_evaluate_user_code():
    code = _generate(_IMPLICIT_INTEGERS)
    assert 'for (int64_t g_x = ' in code
    assert 'for (int g_x = 0; g_x < g__nx; ++g_x)' in code   # the coordinate-variable output loop stays int


def test_timestep_and_grid_size_are_widened_where_read():
    code = _generate(_IMPLICIT_INTEGERS)
    assert '((static_cast<int64_t>(g__nx) + static_cast<int64_t>(gelb_timestep)) * 1073741824)' in code
    assert 'g_Nx' not in code
    assert 'int gelb_timestep = 0;' in code


_SINGLETON = _IMPLICIT_INTEGERS.replace(
    "lattice f(1, 1, real, 4, false)", "lattice f(1, 1, real, 1, false)").replace(
    "(Nx + t) * 1073741824 + x", "((x + 2147483647) + 1)")

_INTEGER_DIVISION_ON_X = """
simulation_description("integer division on x");
lattices { lattice f(1, 1, real, 67, false); }
initializer Init { f.out[x | 0] = 0.5; }
dynamic Dyn { f.out[x | 0] = (x - 7) / 2; }
gauge Out -> (real val) { val = f.in[x | 0]; }
node_classes { node_class BULK(Init, Dyn, Out); }
geometry { nodes[:] = BULK; }
"""


def test_a_collapsed_axis_substitutes_an_int64_literal():
    # The substituted coordinate carries `LL`, and the codegen
    # folder keeps the suffix when it folds the literal arithmetic.
    code = _generate(_SINGLETON)
    assert "int64_t g_x = 0;" in code
    assert "2147483648LL" in code


def test_integer_arithmetic_on_x_takes_the_scalar_path():
    # In the SIMD body x is a double vector, and `(x - 7) / 2`
    # would be a real division; the block is emitted as a scalar loop.
    code = _generate(_INTEGER_DIVISION_ON_X)
    assert "((g_x - 7) / 2)" in code
    assert "/ hn::Set(d, 2)" not in code
    control = _generate(_INTEGER_DIVISION_ON_X.replace("(x - 7) / 2", "x * 0.5"))
    assert "hn::Iota(d, static_cast<double>(g_x))" in control


def test_the_minimum_int64_literal_is_the_negative_maximum_minus_one(tmp_path):
    # The midware folds `-9223372036854775807 - 1` into one literal, so
    # this goes through gelbc rather than the frontend-only helper.
    from click.testing import CliRunner
    from gelb.gelbc import cli as gelbc_cli
    source = tmp_path / "minimum.gelb"
    source.write_text(_MINIMUM)
    out = tmp_path / "minimum.cpp"
    result = CliRunner().invoke(
        gelbc_cli, [str(source), "--backend", "cpu_highway", "--output", str(out)])
    assert result.exit_code == 0, result.output
    code = out.read_text()
    assert '(-9223372036854775807LL - 1LL)' in code
    assert '9223372036854775808' not in code
