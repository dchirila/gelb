"""Exercise vector bodies, scalar fallbacks, peeled edges and 67-cell tails."""

import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from gelb.backends.highway.common import _detect_avx512_available
from gelb.tests.integration._toolchain import (
    requires_compiler, requires_cpp_highway_compiler, requires_gpu_cuda_cpp_compiler,
)

netCDF4 = pytest.importorskip("netCDF4")
ROOT = Path(__file__).resolve().parents[3]
CONFIGS = [
    pytest.param("fortran", marks=requires_compiler),
    pytest.param("soa", marks=requires_cpp_highway_compiler),
    pytest.param("aos", marks=requires_cpp_highway_compiler),
    pytest.param("cbt", marks=[requires_cpp_highway_compiler, pytest.mark.skipif(
        not _detect_avx512_available(), reason="CBT requires AVX-512")]),
    pytest.param("cuda", marks=[pytest.mark.gpu, requires_gpu_cuda_cpp_compiler]),
]
BACKENDS = {"fortran": "cpu_fortran_serial", "cuda": "gpu_cuda_cpp"}
BANNER = re.compile(
    r"^[ \t]*// (Initialiser|Init \(2nd buffer\)|Dynamic|Gauge): "
    r"([A-Za-z0-9_]+) \(([A-Za-z0-9_]+)\)(?: \[rect bbox=[^\]]+\])?( -- SIMD)?", re.M)


def program(dynamic, *, init="f.out[x | :] = 1.0;", constants="", q=3,
            gauge="a = f.in[x | 0];", outputs="real a"):
    return f'''simulation_description("vector body regression");
{('global_constants {' + constants + '}') if constants else ''}
lattices {{ lattice f(1, {q}, real, 67, true); }}
initializer I {{ {init} }}
dynamic D {{ {dynamic} }}
gauge G -> ({outputs}) {{ {gauge} }}
node_classes {{ node_class BULK(I, D, G); }}
geometry {{ nodes[:] = BULK; }}
'''


KEEP = "f.out[x | 1:2] = f.in[x | 1:2];"
BLOCKS = program('''
    f.out[x | 0] = f.in[x | 0] + f.in[x | 1] * 0.5;
    f.out[x | 1] = f.in[x | 1] * 0.75;
    f.out[x | 2] = f.in[x | 2] - f.in[x | 0];''',
    init="f.out[x | 0] = 0.5 * real(x); f.out[x | 1] = 1.0; f.out[x | 2] = 0.25;",
    gauge="a = f.in[x | 0] * f.in[x | 2]; b = f.in[x | 1] + 1.0;",
    outputs="real a, real b")
LOCALS = program('''
    real s;
    array[real, 3] arr;
    s = f.in[x | 0] * 2.0;
    arr = {s, 1.5, real(x)};
    bool p = f.in[x | 0] > 10.0;
    bool q = !p;
    bool c = f.in[x | 1] > 0.5;
    p = q && c;
    bool r = p || q;
    real nan_v = sqrt(f.in[x | 2]);
    bool ne = nan_v != nan_v;
    bool eq = s == s;
    f.out[x | 0] = arr[0] + arr[1] + arr[2] + real(r) + real(ne) + real(eq);
''' + KEEP, init="f.out[x | 0] = 0.5 * real(x); f.out[x | 1] = 1.0; f.out[x | 2] = -1.0;")
POWERS = program('''
    real v = f.in[x | 0];
    f.out[x | 0] = v^0 + v^1 + v^2 + v^3 + v^4 + v^5 + v^6 + v^7 + v^8;
    f.out[x | 1] = min(v, 0.5) + max(v, 0.25) + abs(v - 1.0) + -(v - f.in[x | 1]);
    f.out[x | 2] = f.in[x | 2];''',
    init="f.out[x | 0] = 0.01 * real(x); f.out[x | 1] = 0.5; f.out[x | 2] = 0.75;",
    gauge="a = f.in[x | 0]; b = f.in[x | 1]; c = f.in[x | 2];",
    outputs="real a, real b, real c")
PROGRAMS = {
    "blocks": BLOCKS,
    "narrow_gauge": BLOCKS.replace("real b)", "real32 b)"),
    "locals": LOCALS,
    "coordinate_bool": LOCALS.replace("bool c = f.in[x | 1] > 0.5;", "bool c = x < 33;"),
    "inline_comparison": LOCALS.replace("bool c = f.in[x | 1] > 0.5;", "").replace(
        "q && c", "q && (f.in[x | 1] > 0.5)"),
    "integer_arithmetic": program("f.out[x | 0] = W[0] * (1 + int(x < 33));" + KEEP,
                                  constants="const array[real, 2] W = {2.0, 3.0};"),
    "real_arithmetic": program("f.out[x | 0] = W[0] * (1.0 + real(int(x < 33)));" + KEEP,
                               constants="const array[real, 2] W = {2.0, 3.0};"),
    "powers": POWERS,
}
for name, expression in (("real_power", "v ^ 0.5"), ("lane_power", "2.0 ^ v"),
                         ("mod", "mod(v, 0.3)")):
    PROGRAMS[name] = POWERS.replace("f.out[x | 2] = f.in[x | 2];",
                                   f"f.out[x | 2] = {expression};")

COEFFICIENTS = "0.5, 0.25, 0.125, 2.0, 3.0, 0.75, 1.5, 0.3, 0.7"
CONSTANTS = f"const array[real, 9] F0 = {{{COEFFICIENTS}}};"
INIT_ARRAY = "f.out[x | :] = F0 * (1.0 + 0.01 * real(x));"
for name in ("dot_constant", "dot_local", "sum_local", "sum_slice"):
    constants, declarations, terms = CONSTANTS, [], []
    for n in ((2, 4, 5, 9) if name in ("dot_constant", "sum_slice") else (1, 2, 4, 5, 9)):
        section = "f.in[x | :]" if n == 9 else f"f.in[x | 0:{n - 1}]"
        if name != "sum_slice":
            declarations.append(f"array[real, {n}] a{n} = {section};")
        if name == "dot_constant":
            constants += f"const array[real, {n}] coeff{n} = {{{', '.join(COEFFICIENTS.split(', ')[:n])}}};"
            terms.append(f"dot_prod(coeff{n}, a{n})")
        elif name == "dot_local":
            declarations.append(f"array[real, {n}] b{n} = a{n} * 0.5;")
            terms.append(f"dot_prod(a{n}, b{n})")
        else:
            terms.append(f"sum({section if name == 'sum_slice' else f'a{n}'})")
    PROGRAMS[name] = program("\n".join(declarations) + "f.out[x | 0] = " + " + ".join(terms)
                             + "; f.out[x | 1:8] = f.in[x | 1:8];",
                             constants=constants, init=INIT_ARRAY, q=9)
PROGRAMS["matmul"] = program('''
    array[real, 3] v = f.in[x | :];
    array[real, 3] p = matmul(M, v);
    f.out[x | :] = p * 0.125;''', init=INIT_ARRAY,
    constants='''const array[real, 3] F0 = {0.5, 0.25, 0.125};
    const array[real, {3, 3}] M = {{1.0, 2.0, 0.5}, {0.25, 1.0, 3.0}, {2.0, 0.5, 1.0}};''',
    gauge="a = f.in[x | 0]; b = f.in[x | 1]; c = f.in[x | 2];", outputs="real a, real b, real c")
PROGRAMS["slice_origin"] = program('''
    array[real, 3] s = f.in[x | 2:4];
    f.out[x | 0] = s[0] + 2.0 * s[1] + 3.0 * s[2];
    f.out[x | 1:8] = f.in[x | 1:8];''', constants=CONSTANTS, init=INIT_ARRAY, q=9)
PROGRAMS["singleton"] = program("array[real, 1] a = f.in[x | :]; f.out[x | :] = a * 0.5;",
    q=1, init="f.out[x | 0] = 1.0 + 0.01 * real(x);", gauge="a = sum(f.in[x | :]);")
PROGRAMS["streaming"] = '''simulation_description("streaming on 67 x 4");
global_constants {
    const array[real, 9] EX = {0.0, 1.0, 0.0, -1.0, 0.0, 1.0, -1.0, -1.0, 1.0};
    const array[real, 9] EY = {0.0, 0.0, 1.0, 0.0, -1.0, 1.0, 1.0, -1.0, -1.0};
    const array[real, 9] W = {4.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0};
    const real OMEGA = 1.25;
}
lattices { lattice f(2, 9, real, {67, 4}, {true, false}); }
initializer I { f.out[x, y | :] = W * (1.0 + 0.001 * real(x) + 0.01 * real(y)); }
dynamic Bulk {
    array[real, 9] fIn = upstream_dfs(f, x, y, {EX, EY});
    real rho = sum(fIn);
    f.out[x, y | :] = fIn - OMEGA * (fIn - W * rho);
}
dynamic Inlet { array[real, 9] fIn = upstream_dfs(f, x, y, {EX, EY}); f.out[x, y | :] = fIn; }
dynamic Wall { f.out[x, y | :] = bounce_back_dfs(f, x, y, {EX, EY}); }
gauge G -> (real rho) { rho = sum(f.in[x, y | :]); }
node_classes { node_class FLUID(I, Bulk, G); node_class INLET(I, Inlet, G); node_class WALL(I, Wall, G); }
geometry { nodes[:, :] = FLUID; nodes[30:32, 1:2] = INLET; nodes[:, 0] = WALL; nodes[:, 3] = WALL; }
'''


def run_program(directory, config, source):
    """Run one isolated strict build; retain diagnostics for expected build failures."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "probe.gelb"
    path.write_text(source)
    env = dict(os.environ, GELB_PYTHON=sys.executable, OMP_NUM_THREADS="4")
    for key in ("GELB_FFLAGS", "GELB_CXXFLAGS", "GELB_NVCC_FLAGS", "GELBC_EXTRA"):
        env.pop(key, None)
    if config in ("soa", "aos", "cbt"):
        env["GELBC_EXTRA"] = f"--storage-layout {config}"
    result = subprocess.run([str(ROOT / "scripts/gelb-run"), "--keep", "--strict-fp",
                             "-b", BACKENDS.get(config, "cpu_highway"), "-n", "1", "-w", "1",
                             "-s", "42", str(path)], cwd=directory, env=env,
                            capture_output=True, text=True, timeout=600)
    (directory / "run.log").write_text(result.stdout + result.stderr)
    values = {}
    if result.returncode == 0:
        with netCDF4.Dataset(directory / "probe.nc") as nc:
            nc.set_auto_mask(False)
            values = {name: (var.dimensions, np.asarray(var[:])) for name, var in nc.variables.items()}
    return result, values


def assert_blocks(source, case, config):
    marks = list(BANNER.finditer(source))
    assert marks, "no block banners"
    targets = []
    for i, match in enumerate(marks):
        kind, name, node_class, simd = match.groups()
        if kind != "Dynamic" and case not in ("blocks", "narrow_gauge"):
            continue
        body = source[match.end():marks[i + 1].start() if i + 1 < len(marks) else len(source)]
        vector = case not in ("inline_comparison", "integer_arithmetic", "real_power", "lane_power", "mod")
        vector &= not (case == "narrow_gauge" and kind == "Gauge")
        vector &= node_class != "INLET"
        if config != "aos":
            assert bool(simd) == vector, match.group()
        assert ("hn::" in body) == (vector and config != "aos"), match.group()
        targets.append((kind, name))
    if case == "streaming":
        assert sorted(targets) == [("Dynamic", "Bulk")] * 2 + [("Dynamic", "Inlet")] + [("Dynamic", "Wall")] * 2
    elif case in ("blocks", "narrow_gauge"):
        assert sorted(targets) == [("Dynamic", "D"), ("Gauge", "G"), ("Gauge", "G"), ("Initialiser", "I")]
    else:
        assert targets == [("Dynamic", "D")]


@pytest.fixture(scope="module", params=tuple(PROGRAMS))
def case(request):
    return request.param


@pytest.fixture(scope="module")
def reference(case, tmp_path_factory):
    directory = tmp_path_factory.mktemp("vector_soa")
    result, values = run_program(directory, "soa", PROGRAMS[case])
    assert result.returncode == 0, result.stdout + result.stderr
    assert_blocks((directory / "probe.cpp").read_text(), case, "soa")
    return directory, values


@requires_cpp_highway_compiler
@pytest.mark.parametrize("config", CONFIGS)
def test_vector_body(case, config, reference, tmp_path):
    if config == "soa":
        directory, actual = reference
    else:
        directory = tmp_path
        result, actual = run_program(directory, config, PROGRAMS[case])
        assert result.returncode == 0, result.stdout + result.stderr
    if config in ("soa", "aos", "cbt"):
        assert_blocks((directory / "probe.cpp").read_text(), case, config)
    expected = reference[1]
    assert actual.keys() == expected.keys()
    for name, (dims, a) in actual.items():
        other_dims, b = expected[name]
        assert (dims, a.shape, a.dtype) == (other_dims, b.shape, b.dtype), name
        approximate = config == "fortran" and (
            case in ("dot_constant", "sum_local", "streaming")
            or (case in ("powers", "real_power", "lane_power", "mod") and name == "a"))
        approximate |= config in ("fortran", "cuda") and case in ("real_power", "lane_power") and name == "c"
        if approximate:
            np.testing.assert_allclose(a, b, rtol=1e-13, atol=1e-14, equal_nan=True, err_msg=name)
        else:
            assert np.array_equal(a, b, equal_nan=True), (case, config, name)
            if np.issubdtype(a.dtype, np.floating):
                assert np.array_equal(np.signbit(a), np.signbit(b)), (case, config, name)
