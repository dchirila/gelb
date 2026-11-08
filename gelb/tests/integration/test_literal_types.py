"""Integer and real literals keep their type in C++ and CUDA: a zero
power, and every integer literal of an ``int`` operation.

A power with a literal exponent is a product of its base, and its type
comes from the type table (user manual, Numerical semantics: Types and
promotion), so ``v^0`` is that type's one: a real ``1.0`` for a real
``v``, an ``int`` 1 for an integer ``v`` (a narrow base with the ``int``
literal 0 gives an ``int``).  A quotient built only from real zero
powers is a real division, and a product of integer zero powers with
``int`` constants is exact in ``int`` (int64), past 2^31.  So is every
operation on integer literals: a literal the C++ emitter keeps after
dropping a factor of zero or one (``k * 0 + 2147483647``), the zero it
writes for such a product, whatever consumes them (a product, a
quotient, ``abs``, an unrolled power), a literal-only initializer
(``int q = 46341^2;``), an inlined function's literal argument and an
array literal, whatever the literal's own type.  Every backend and layout is checked against the
closed form of the program, exactly, zero signs included; the check on
the generated code pins the C++ spelling of the one, an implementation
choice the manual does not define.
"""

import os
import pathlib
import subprocess
import sys

import numpy as np
import pytest
from click.testing import CliRunner

from gelb.backends.highway import common
from gelb.gelbc import cli
from gelb.tests.integration._toolchain import (
    requires_compiler, requires_cpp_highway_compiler,
    requires_gpu_cuda_cpp_compiler)

netCDF4 = pytest.importorskip("netCDF4")

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_GELB_RUN = _ROOT / "scripts" / "gelb-run"

NX = 67   # a vector body of eight lanes and a remainder
NY = 4


def _run(directory, backend, source, layout=None):
    directory.mkdir()
    path = directory / "probe.gelb"
    path.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable)
    if layout is not None:
        env["GELBC_EXTRA"] = f"--storage-layout {layout}"
    result = subprocess.run(
        [str(_GELB_RUN), "-b", backend, "-n", "1", "-w", "1", str(path)],
        cwd=directory, env=env, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(next(directory.glob("*.nc"))) as nc:
        return np.asarray(nc.variables["s"][:])


CONFIGS = [
    pytest.param("cpu_fortran_serial", None, marks=requires_compiler,
                 id="fortran"),
    *(pytest.param("cpu_highway", layout, marks=requires_cpp_highway_compiler,
                   id=f"highway-{layout}")
      for layout in ("soa", "aos", "cbt")),
    pytest.param("gpu_cuda_cpp", None,
                 marks=[pytest.mark.gpu, requires_gpu_cuda_cpp_compiler],
                 id="cuda"),
]

# Each shape: the declarations, the value stored, its closed form at the
# last record, and optionally the program's functions.  F = x / 2 - 7.75
# is the per-cell lattice value.
_SHAPES = {
    # quotients built only from real zero powers: a real division
    "real_nested_quotient": ("", "(F^0)^2 / ((F^0)^2 + (F^0)^2)", 0.5),
    "real_abs_quotient": ("", "F^0 / (abs(F^0) + abs(F^0))", 0.5),
    "real32_quotient": ("real32 r = real32(F);",
                        "real((r^0)^2 / ((r^0)^2 + (r^0)^2))", 0.5),
    # integer zero powers times int constants: exact past 2^31
    "int_product": ("", "real(((int(F > 0.0)^0)^2) * 2147483647 * 2)",
                    4294967294.0),
    "int_product_plain": ("", "real((int(F > 0.0)^0) * 2147483647 * 2)",
                          4294967294.0),
    "int_product_negated": ("", "real(-(int(F > 0.0)^0) * 2147483647 * 2)",
                            -4294967294.0),
    "uniform_int_product": ("", "F * 0.0 + real(((t^0)^2) * 2147483647 * 2)",
                            4294967294.0),
    "int32_product": ("int32 a = int32(F > 0.0);",
                      "real(((a^0)^2) * 2147483647 * 2)", 4294967294.0),
    # literals that the emitter's folds bring together: int64, not int
    "int_literal_fold": ("", "real((int(F > 0.0) * 0 + 2147483647) * 2)",
                         4294967294.0),
    "uniform_int_literal_fold": ("", "F * 0.0 + real((t * 0 + 2147483647) * 2)",
                                 4294967294.0),
    # a kept literal reaches a quotient or an unrolled power: still int64
    "int_literal_fold_division": ("", "real(((int(F > 0.0) * 0 + 2147483647)"
                                      " / 1) * 2)", 4294967294.0),
    "int_literal_fold_square": ("", "real((int(F > 0.0) * 0 + 65536)^2)",
                                4294967296.0),
    "uniform_int_literal_fold_square": ("", "F * 0.0 + real((t * 0 + 65536)^2)",
                                        4294967296.0),
    # the zero a fold writes for k * 0 reaches a consumer first
    "zero_product_division": ("", "real(((int(F > 0.0) * 0) / 1"
                                  " + 2147483647) * 2)", 4294967294.0),
    "zero_product_abs": ("", "real((abs(int(F > 0.0) * 0) + 2147483647) * 2)",
                         4294967294.0),
    "zero_product_square": ("", "real(((int(F > 0.0) * 0)^2 + 2147483647)"
                                " * 2)", 4294967294.0),
    # literal-only arithmetic that reaches C++ unfolded
    "declared_literal_square": ("int q = 46341^2;", "real(q)", 2147488281.0),
    "declared_literal_quotient": ("int q = (2147483647 / 1) * 2;", "real(q)",
                                  4294967294.0),
    "declared_sum_with_square": ("int q = ((int(F > 0.0) * 0) / 1)"
                                 " + 65536^2;", "real(q)", 4294967296.0),
    "inlined_literal_argument": ("", "real(Sq(46341))", 2147488281.0,
                                 "function Sq(int a) -> (int b) { b = a^2; }"),
    # a narrower literal argument is an int64 operand in an int body
    "inlined_int32_constant_argument": (
        "", "real(Sq(H))", 2147488281.0,
        "global_constants { const int32 H = 46341; }\n"
        "function Sq(int a) -> (int b) { b = a * a; }"),
    "inlined_int32_cast_argument": (
        "", "real(Sq(int32(46341)))", 2147488281.0,
        "function Sq(int a) -> (int b) { b = a * a; }"),
    "array_literal_square": ("array[int, 2] a = {65536, 65536}^2;",
                             "real(a[1]) + F * 0.0", 4294967296.0),
    "array_literal_product": ("array[int, 2] a = {65536, 65536} * 65536;",
                              "real(sum(a)) + F * 0.0", 8589934592.0),
}


def _program(shape):
    decls, value, _, *functions = _SHAPES[shape]
    lattice_f = "f.in[x, y | 0]"
    decls = decls.replace("F", lattice_f)
    value = value.replace("F", lattice_f)
    return f"""\
simulation_description("literal types: {shape}");
{"".join(functions)}
lattices {{ lattice f(2, 2, real, {{{NX}, {NY}}}, {{false, false}}); }}
initializer Init {{
    f.out[x, y | 0] = real(x) * 0.5 - 7.75;
    f.out[x, y | 1] = 0.0;
}}
dynamic Step {{
    f.out[x, y | 0] = f.in[x, y | 0];
    {decls}
    f.out[x, y | 1] = {value};
}}
gauge G -> (real s) {{ s = f.in[x, y | 1]; }}
node_classes {{ node_class A(Init, Step, G); }}
geometry {{ nodes[:, :] = A; }}
"""


@pytest.mark.parametrize("backend, layout", CONFIGS)
@pytest.mark.parametrize("shape", sorted(_SHAPES))
def test_zero_power_keeps_its_type(tmp_path, backend, layout,
                                             shape):
    """Each shape gives its closed form in every cell, bit for bit."""
    if layout == "cbt" and not common._detect_avx512_available():
        pytest.skip("the cbt layout needs an AVX-512 host")
    field = _run(tmp_path / "run", backend, _program(shape), layout)[-1]
    expected = np.full(field.shape, _SHAPES[shape][2])
    np.testing.assert_array_equal(field, expected)
    np.testing.assert_array_equal(np.signbit(field), np.signbit(expected))


@pytest.mark.parametrize("shape, one", [
    ("real_nested_quotient", "1.0"),
    ("real32_quotient", "1.0f"),
    ("int_product", "static_cast<int64_t>(1)")])
def test_zero_power_is_spelled_in_its_type(tmp_path, shape, one):
    """The C++ source spells the one in the power's type, never as the
    bare ``int`` literal ``1`` (an integer one is a cast, which the
    emitter's literal folds keep)."""
    path = tmp_path / "prog.gelb"
    path.write_text(_program(shape))
    out = tmp_path / "prog.cpp"
    result = CliRunner().invoke(
        cli, [str(path), "-o", str(out), "-b", "cpu_highway",
              "--storage-layout", "aos"])
    assert result.exit_code == 0, result.output
    cpp = out.read_text()
    assert f"({one} * {one})" in cpp
    assert "(1 * 1)" not in cpp
