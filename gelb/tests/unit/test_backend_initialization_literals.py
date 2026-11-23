"""Literal spelling and initialization order in generated programs."""

import shlex
import subprocess

from click.testing import CliRunner
import pytest

from gelb.backends.stage3_backend_cpu_highway import HighwayCodeGenerator
from gelb.gelbc import cli
from gelb.tests.integration._toolchain import NC_FFLAGS, requires_compiler


def emit_fortran(tmp_path, source):
    path, out = tmp_path / "literal.gelb", tmp_path / "literal.f90"
    path.write_text(source)
    run = CliRunner().invoke(cli, [str(path), "-b", "cpu_fortran_serial",
                                  "-o", str(out), "--nc-output", "out.nc"])
    assert run.exit_code == 0, run.output
    return out


@requires_compiler
@pytest.mark.parametrize("expression,spelling", [
    ("real(abs(x - 5))", "std::abs("),
    ("real(abs(x + 5))", "std::abs("),
    ("real(abs(x))", "std::abs(0LL)"),
    ("real(x)", "static_cast<double>(0LL)"),
    ("real(-(x - 1))", "(-"),
    ("real(-(-1))", "1.0"),
    ("real(f_1(x))", "std::abs("),
    ("f.in[x - 1 | 0]", "g0_1_f_storage[g0_1_f_old][0][64]"),
    ("sqrt(real(x))", "sqrt("),
])
def test_singleton_expression_call_parentheses(tmp_path, expression, spelling):
    from pathlib import Path
    from gelb.tests.integration._toolchain import NC_CFLAGS
    source = f"""
simulation_description("singleton expressions");
lattices {{ lattice f(1, 1, real, 64, true); }}
function f_1(int a) -> (int result) {{ result = abs(a - 5); }}
initializer I {{ f.out[x | 0] = 1.0; }}
dynamic D {{ f.out[x | 0] = {expression}; }}
dynamic Copy {{ f.out[x | 0] = f.in[x | 0]; }}
gauge G -> (real val) {{ val = f.in[x | 0]; }}
node_classes {{ node_class B(I, D, G); node_class E(I, Copy, G); }}
geometry {{ nodes[:] = E; nodes[0:0] = B; nodes[63:63] = B; }}
"""
    path, out = tmp_path / "literal.gelb", tmp_path / "literal.cpp"
    path.write_text(source)
    run = CliRunner().invoke(cli, [str(path), "-b", "cpu_highway", "-o", str(out),
                                  "--storage-layout", "soa", "--nc-output", "out.nc"])
    assert run.exit_code == 0, run.output
    assert spelling in out.read_text()
    root = Path(__file__).resolve().parents[3]
    run = subprocess.run(["g++", "-std=c++17", "-fsyntax-only", "-fopenmp",
                          *shlex.split(NC_CFLAGS), "-I", str(root / "third_party/highway"),
                          "-I", str(root / "gelb/backends"), str(out)],
                         cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


@requires_compiler
@pytest.mark.parametrize("kind,minimum,spelling", [
    ("int8", -128, "(-127_1 - 1_1)"),
    ("int16", -32768, "(-32767_2 - 1_2)"),
    ("int32", -2147483648, "(-2147483647_4 - 1_4)"),
])
def test_narrow_array_minima_pass_unflagged_fortran_syntax(
        tmp_path, kind, minimum, spelling):
    source = f"""
simulation_description("narrow array minima");
global_constants {{
    const array[{kind}, 2] K = {{{minimum}, 1}};
    const array[{kind}, {{2, 2}}] K2 = {{{{{minimum}, 1}}, {{2, 3}}}};
}}
lattices {{ lattice f(1, 1, real, 17, false); }}
initializer I {{ f.out[x | 0] = 1.0; }}
dynamic D {{ f.out[x | 0] = f.in[x | 0]; }}
gauge G -> (int one, int two) {{
    array[{kind}, 2] local = K;
    array[{kind}, 2] basis = {{1, 0}};
    array[{kind}, 2] product = matmul(K2, basis);
    one = local[0]; two = product[0];
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""
    out = emit_fortran(tmp_path, source)
    assert out.read_text().count(spelling) >= 2
    run = subprocess.run(["gfortran", "-fsyntax-only", *shlex.split(NC_FFLAGS), str(out)],
                         cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


def test_timestep_is_set_before_any_fortran_initializer(tmp_path):
    out = emit_fortran(tmp_path, """
simulation_description("initializer timestep");
lattices { lattice f(1, 1, real, 17, false); }
initializer I { f.out[x | 0] = real(t); }
dynamic D { f.out[x | 0] = f.in[x | 0]; }
gauge G -> (real value) { value = f.in[x | 0]; }
node_classes { node_class B(I, D, G); }
geometry { nodes[:] = B; }
""")
    text = out.read_text()
    assert text.count("gelb_timestep = 0") == 1
    assert text.index("gelb_timestep = 0") < text.index("! ========== Initializer:")
