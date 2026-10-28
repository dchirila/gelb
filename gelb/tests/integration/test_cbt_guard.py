"""The cell-block-tiled storage layout (CBT) works only with eight double
lanes, that is where Highway compiles for one of its 512-bit targets;
with fewer its tile shuffles give wrong results.  So gelbc rejects
``--storage-layout cbt`` when Highway, compiled with ``GELB_CXX`` and
``GELB_CXXFLAGS`` as gelb-run would, does not select such a target,
``auto`` does not pick CBT
there, and every CBT program carries a ``static_assert`` on the lane
count, so that one built for a narrower target fails to compile instead
of running (developer manual, Design decisions)."""

import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys

from click.testing import CliRunner
import pytest

from gelb.backends.highway import common
from gelb.gelbc import cli
from gelb.tests.integration._toolchain import (
    CPP_HIGHWAY_INCLUDES, NC_CFLAGS, requires_cpp_highway_compiler)

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples/lbm/2d/taylor_green_vortex_2d_bgk.gelb"
ASSERT = "static_assert(!HWY_HAVE_SCALABLE && ::gelb_simd::d.MaxLanes() == 8,"
# x86-64-v3 has no AES or PCLMUL, so GCC builds Highway's two-lane
# SSSE3 target with it
_V3_CXXFLAGS = ("-std=c++17 -O3 -march=x86-64-v3 -ffp-contract=off"
                " -fno-trapping-math -fno-unroll-loops -DNDEBUG")
requires_x86 = pytest.mark.skipif(platform.machine() not in ("x86_64", "AMD64"),
                                  reason="x86 ISA flags")


@pytest.fixture(autouse=True)
def fresh_probe(monkeypatch):
    """The probe caches its answer per process; every test starts afresh,
    with the g++ that _runtime_has_eight_fixed_lanes compiles with."""
    monkeypatch.delenv("GELB_HAS_AVX512", raising=False)
    monkeypatch.delenv("GELB_CXXFLAGS", raising=False)
    monkeypatch.setenv("GELB_CXX", "g++")
    monkeypatch.setattr(common._detect_avx512_available, "_cached", None, raising=False)
    yield
    common._detect_avx512_available._cached = None


def _gelbc(tmp_path, *args):
    out = tmp_path / "prog.cpp"
    result = CliRunner().invoke(cli, [str(EXAMPLE), "-o", str(out), *args])
    return result, out


def test_cbt_is_rejected_without_avx512(tmp_path, monkeypatch):
    monkeypatch.setenv("GELB_HAS_AVX512", "0")
    result, out = _gelbc(tmp_path, "--storage-layout", "cbt")
    assert result.exit_code == 1
    assert "--storage-layout cbt needs AVX-512" in result.output
    assert not out.exists()


@pytest.mark.parametrize("backend", ["cpu_fortran_serial", "gpu_cuda_cpp"])
def test_cbt_is_ignored_by_the_other_backends(tmp_path, monkeypatch, backend):
    monkeypatch.setenv("GELB_HAS_AVX512", "0")
    result, _ = _gelbc(tmp_path, "-b", backend, "--storage-layout", "cbt")
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("layout,avx512,has_assert", [
    ("cbt", "1", True),
    ("auto", "1", True),
    ("auto", "0", False),
    ("soa", "1", False),
    ("aos", "1", False),
])
def test_every_cbt_program_asserts_eight_lanes(tmp_path, monkeypatch, layout, avx512, has_assert):
    monkeypatch.setenv("GELB_HAS_AVX512", avx512)
    result, out = _gelbc(tmp_path, "--storage-layout", layout)
    assert result.exit_code == 0, result.output
    assert (ASSERT in out.read_text()) == has_assert


@pytest.mark.parametrize("returncode,expected", [(0, True), (1, False)])
def test_the_probe_preprocesses_highway_with_the_build_flags(monkeypatch, returncode, expected):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("GELB_CXX", "")
    monkeypatch.setenv("GELB_CXXFLAGS", "-O2 -march=x86-64-v4")
    assert common._detect_avx512_available() is expected
    # the compiler and flags gelb-run will build with (an empty GELB_CXX
    # means g++), and the vendored Highway
    assert seen["cmd"][:3] == ["g++", "-O2", "-march=x86-64-v4"]
    assert f"-I{ROOT / 'third_party' / 'highway'}" in seen["cmd"]


def _runtime_has_eight_fixed_lanes(flags):
    """Whether cpu_highway_runtime.hpp, compiled with these flags, gives
    the fixed eight-lane descriptor a CBT program asserts."""
    source = ('#include "cpu_highway_runtime.hpp"\n'
              'static_assert(!HWY_HAVE_SCALABLE && ::gelb_simd::d.MaxLanes() == 8, "");\n')
    cmd = ["g++", "-std=c++17", *flags, *shlex.split(CPP_HIGHWAY_INCLUDES),
           *shlex.split(NC_CFLAGS), "-fsyntax-only", "-x", "c++", "-"]
    return subprocess.run(cmd, input=source, text=True, capture_output=True).returncode == 0


@requires_cpp_highway_compiler
@requires_x86
@pytest.mark.parametrize("cxxflags", [
    None,  # unset or empty: the probe and the build use -march=native
    "",
    "   ",  # set, but no flags at all
    "-O3 -march=native",
    "-O2",
    "-march=x86-64-v3",
    "-march=x86-64-v4",
    "-march=x86-64-v4 -DHWY_DISABLE_PCLMUL_AES",
    "-mavx512f",
    "-march=x86-64-v4 -mno-fma",
    "-march=native -DHWY_COMPILE_ONLY_EMU128",
])
def test_the_probe_agrees_with_the_compiled_runtime(monkeypatch, cxxflags):
    if cxxflags is not None:
        monkeypatch.setenv("GELB_CXXFLAGS", cxxflags)
    # gelb-run's ${GELB_CXXFLAGS:-default}, split on whitespace
    flags = (cxxflags or "-march=native").split()
    assert common._detect_avx512_available() == _runtime_has_eight_fixed_lanes(flags)


@requires_cpp_highway_compiler
@requires_x86
@pytest.mark.parametrize("cxxflags,expected", [
    ("-march=x86-64-v3", False),
    # with AES and PCLMUL waived, x86-64-v4 reaches the AVX3 target
    ("-march=x86-64-v4 -DHWY_DISABLE_PCLMUL_AES", True),
])
def test_the_probe_knows_targets_that_do_not_depend_on_the_host(monkeypatch, cxxflags, expected):
    monkeypatch.setenv("GELB_CXXFLAGS", cxxflags)
    assert common._detect_avx512_available() is expected


@requires_cpp_highway_compiler
@requires_x86
@pytest.mark.parametrize("avx512,message", [
    # gelbc probes with GELB_CXXFLAGS and rejects the layout
    (None, "--storage-layout cbt needs AVX-512"),
    # told otherwise, it generates CBT, and the C++ compiler stops it
    ("1", "the cell-block-tiled storage layout needs AVX-512"),
])
def test_a_cbt_program_built_without_avx512_does_not_run(tmp_path, avx512, message):
    env = dict(os.environ, GELB_PYTHON=sys.executable, GELB_CXXFLAGS=_V3_CXXFLAGS,
               GELBC_EXTRA="--storage-layout cbt")
    env.pop("GELB_HAS_AVX512", None)
    if avx512 is not None:
        env["GELB_HAS_AVX512"] = avx512
    result = subprocess.run(
        [str(ROOT / "scripts/gelb-run"), "-b", "cpu_highway", "-n", "1",
         "-D", "N=16", str(EXAMPLE)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=600)
    assert result.returncode != 0
    assert message in result.stdout + result.stderr
    assert not list(tmp_path.glob("*.nc"))
