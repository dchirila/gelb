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


def run_literal_source(tmp_path, config, source, monkeypatch, *, plain=False, strict=True):
    """Run an isolated literal/slice case with the requested build flags."""
    path = tmp_path / 'probe.gelb'
    path.write_text(source)
    extra = ['--storage-layout', config] if config in ('soa', 'aos', 'cbt') else []
    if plain:
        extra += ['--no-slice-simplify', '--no-scalar-cse']
    env = dict(os.environ, GELB_PYTHON=sys.executable, OMP_NUM_THREADS='4')
    for key in ('GELB_FFLAGS', 'GELB_CXXFLAGS', 'GELB_NVCC_FLAGS', 'GELBC_EXTRA'):
        env.pop(key, None)
    env['GELBC_EXTRA'] = ' '.join(extra)
    flags = ['--strict-fp'] if strict else []
    result = subprocess.run([str(ROOT / 'scripts/gelb-run'), '--keep', *flags,
                             '-b', BACKENDS.get(config, 'cpu_highway'), '-n', '1', '-w', '1',
                             str(path)], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=600)
    (tmp_path / 'run.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    with netCDF4.Dataset(tmp_path / 'probe.nc') as nc:
        nc.set_auto_mask(False)
        values = {name: np.asarray(var[:]) for name, var in nc.variables.items()}
    cpp = (tmp_path / 'probe.cpp').read_text() if config in ('soa', 'aos', 'cbt') else ''
    return values, cpp


def assert_literal_vector_block(cpp, config, kind='Dynamic', name='D'):
    if config not in ('soa', 'aos', 'cbt'):
        return
    matches = list(BANNER.finditer(cpp))
    found = False
    for i, match in enumerate(matches):
        if match.group(1) != kind or match.group(2) != name:
            continue
        found = True
        body = cpp[match.end():matches[i+1].start() if i+1 < len(matches) else len(cpp)]
        if config != 'aos':
            assert match.group(4), match.group()
        assert ('hn::' in body) == (config != 'aos')
    assert found


@pytest.mark.parametrize('config', CONFIGS)
@pytest.mark.parametrize('cells', [4, 64])
def test_local_slice_expressions_all_blocks(tmp_path, monkeypatch, config, cells):
    source = program('''
        array[real, 3] w = f.in[x | :];
        array[real, 2] u = 2.0 * w[1:];
        array[real, 2] v; v = -w[0:1];
        array[real, 2] math_values = 2.0 * {sqrt(w[0] * w[0]), min(w[2], 10.0)};
        array[real, 2] pw = w[0:1] ^ 2;
        array[real, 2] c = real(w[0:1] > {10.0, 40.0});
        real d = dot_prod(C, w[1:]);
        array[real, 2] m = matmul(M, w[1:]);
        f.out[x | 0] = u[0] + v[1] + math_values[0] + pw[0] + c[0] + d + m[0];
        f.out[x | 1:2] = w[1:];''',
        init='''array[real, 3] wi = {1.0 + real(x), 2.0 + real(x), 3.0 + real(x)};
            f.out[x | 0] = wi[0]; f.out[x | 1:2] = wi[1:];''',
        constants='''const array[real, 2] C = {2.0, 0.5};
            const array[real, {2, 2}] M = {{1.0, 2.0}, {0.5, -1.0}};''',
        gauge='''array[real, 3] wg = f.in[x | :]; array[real, 3] a = wg[:];
            array[real, 2] b; b = wg[0:1]; p0 = a[0]; p1 = b[1]; p2 = a[2];''',
        outputs='real p0, real p1, real p2').replace('67, true', f'{cells}, true')
    values, cpp = run_literal_source(tmp_path, config, source, monkeypatch)
    x = np.arange(cells)
    np.testing.assert_array_equal(values['p0'][0], x + 1)
    np.testing.assert_array_equal(values['p0'][-1],
        (x+2) + 2*(x+1) + (x+1)**2 + (x+1 > 10) + 2*(x+2) + .5*(x+3) + (x+2) + 2*(x+3))
    np.testing.assert_array_equal(values['p1'][-1], x + 2)
    np.testing.assert_array_equal(values['p2'][-1], x + 3)
    if cells == 64:
        for kind, name in [('Initialiser', 'I'), ('Dynamic', 'D'), ('Gauge', 'G')]:
            assert_literal_vector_block(cpp, config, kind, name)


@pytest.mark.parametrize('config', CONFIGS)
@pytest.mark.parametrize('q,plain', [(3, False), (9, True)])
def test_literal_store_reductions_and_plain_expansion(tmp_path, monkeypatch, config, q, plain):
    elements = ['dot_prod(C, v)', 'v[1]', 'v[2]'] + [f'v[{i}]' for i in range(3, q)]
    source = program(f'''array[real, {q}] v = f.in[x | :];
        f.out[x | :] = 2.0 * {{{', '.join(elements)}}};''', q=q,
        constants=f"const array[real, {q}] C = {{{', '.join(['1.0'] * q)}}};",
        init=' '.join(f'f.out[x | {i}] = {i+1}.0 + real(x);' for i in range(q)),
        gauge='p0 = f.in[x | 0]; p1 = f.in[x | 1];', outputs='real p0, real p1').replace('67, true', '64, true')
    values, cpp = run_literal_source(tmp_path, config, source, monkeypatch, plain=plain)
    x = np.arange(64)
    np.testing.assert_array_equal(values['p0'][-1], 2*(q*x + q*(q+1)//2))
    np.testing.assert_array_equal(values['p1'][-1], 2*(x+2))
    assert_literal_vector_block(cpp, config)


@pytest.mark.parametrize('config', CONFIGS)
@pytest.mark.parametrize('kind', ['int', 'int32', 'int16', 'int8', 'real32', 'bool'])
def test_literal_store_element_widths(tmp_path, monkeypatch, config, kind):
    if kind.startswith('int'):
        start = 9007199254740993 if kind == 'int' else 3
        local = f'{kind} k = {kind}({start} + x);'
        expr = '{k, ' + kind + '(7)} / {' + kind + '(3), ' + kind + '(2)}'
        lattice_type = kind
        expected = (start + np.arange(64, dtype=np.int64)) // 3
        other = 3
    elif kind == 'real32':
        local = 'int k = 18014399583223809 + x;'
        expr, lattice_type = '{k, 7}', 'real32'
        expected, other = np.full(64, 18014400656965632, dtype=np.float32), 7
    else:
        local = 'real k = f.in[x | 0];'
        expr, lattice_type = 'real({k > 10.0, false})', 'real'
        expected, other = np.arange(64) + 1 > 10, 0
    output_type = 'int' if kind.startswith('int') else 'real'
    source = f'''simulation_description("literal element widths");
        lattices {{ lattice f(1, 3, {lattice_type}, 64, true); }}
        initializer I {{ f.out[x | :] = x + 1; }}
        dynamic D {{ {local} f.out[x | 0] = f.in[x | 0]; f.out[x | 1:2] = {expr}; }}
        gauge G -> ({output_type} p0, {output_type} p1) {{ p0 = f.in[x | 1]; p1 = f.in[x | 2]; }}
        node_classes {{ node_class B(I, D, G); }} geometry {{ nodes[:] = B; }}'''
    values, cpp = run_literal_source(tmp_path, config, source, monkeypatch)
    np.testing.assert_array_equal(values['p0'][-1], expected)
    np.testing.assert_array_equal(values['p1'][-1], np.full(64, other))
    if kind == 'int':
        assert values['p0'].dtype == np.dtype('int64')
    if kind == 'bool':
        assert_literal_vector_block(cpp, config)


@pytest.mark.parametrize('config', CONFIGS)
def test_bounce_back_beside_local_slice(tmp_path, monkeypatch, config):
    source = program('''array[real, 3] w = f.in[x | :];
        f.out[x | :] = bounce_back_dfs(f, x, EX) + w[:];''',
        constants='const array[real, 3] EX = {0.0, 1.0, -1.0};',
        init='f.out[x | 0] = 1.0 + real(x); f.out[x | 1] = 2.0 + real(x); f.out[x | 2] = 3.0 + real(x);',
        gauge='p0 = f.in[x | 0]; p1 = f.in[x | 1]; p2 = f.in[x | 2];',
        outputs='real p0, real p1, real p2').replace('67, true', '64, true')
    values, cpp = run_literal_source(tmp_path, config, source, monkeypatch)
    x = np.arange(64)
    for name, expected in [('p0', 2*(x+1)), ('p1', (x+1)%64 + 3 + x + 2), ('p2', (x-1)%64 + 2 + x + 3)]:
        np.testing.assert_array_equal(values[name][-1], expected)
    assert_literal_vector_block(cpp, config)


@pytest.mark.parametrize('config', CONFIGS)
@pytest.mark.parametrize('strict', [False, True])
def test_literal_matmul_uses_bound_row_order(tmp_path, monkeypatch, config, strict):
    # Inexact mixed-sign rows discriminate left-to-right from grouped sums.
    constants = '''const array[real, {5, 5}] M = {
        {1.0, 0.0, 0.0, 0.0, 0.0}, {0.0, 1.0, 0.0, 0.0, 0.0},
        {0.0, 0.0, 1.0, 0.0, 0.0}, {0.0, 0.0, 0.0, 1.0, 0.0},
        {0.0, 1.0, -1.0, 1.0, -1.0}};'''
    template = program('''array[real, 5] v = f.in[x | :];
        STORE''', q=5, constants=constants,
        init=' '.join(f'f.out[x | {i}] = {i+1}.0 + 0.001 * real(x);' for i in range(5)),
        gauge='p0 = f.in[x | 0]; p4 = f.in[x | 4];', outputs='real p0, real p4').replace('67, true', '64, true')
    literal = '{v[0], 2.0, 3.0, 4.0, 5.0}'
    inline = template.replace('STORE', f'f.out[x | :] = matmul(M, v) + {literal};')
    bound = template.replace('STORE', 'array[real, 5] tm = matmul(M, v); ' +
        ' '.join(f'f.out[x | {i}] = tm[{i}] + ' + ('v[0]' if i == 0 else f'{i+1}.0') + ';' for i in range(5)))
    actual_dir, control_dir = tmp_path / 'inline', tmp_path / 'bound'
    actual_dir.mkdir(); control_dir.mkdir()
    actual, cpp = run_literal_source(actual_dir, config, inline, monkeypatch, strict=strict)
    expected, _ = run_literal_source(control_dir, config, bound, monkeypatch, strict=strict)
    for name in ('p0', 'p4'):
        assert actual[name].dtype == expected[name].dtype
        assert actual[name].tobytes() == expected[name].tobytes()
    assert_literal_vector_block(cpp, config)


@pytest.mark.parametrize('operand', ['W', 'A * B'])
@pytest.mark.parametrize('backend,layout', [
    pytest.param('cpu_fortran_serial', None, marks=requires_compiler),
    pytest.param('cpu_highway', 'soa', marks=requires_cpp_highway_compiler),
    pytest.param('cpu_highway', 'aos', marks=requires_cpp_highway_compiler),
    pytest.param('cpu_highway', 'cbt', marks=requires_cpp_highway_compiler),
    pytest.param('gpu_cuda_cpp', None, marks=requires_gpu_cuda_cpp_compiler),
])
def test_dot_product_hoisted_slice_and_expression(tmp_path, monkeypatch, backend, layout, operand):
    from gelb.tests.integration.test_tutorial_regressions import (
        configure_initialization_run, run_source,
    )
    configure_initialization_run(monkeypatch, layout)
    source = program(
        f'f.out[x|0] = dot_prod({operand}, f.in[x|:]);' + KEEP,
        constants='''const array[real,3] W={2.0,6.0,12.0};
        const array[real,3] A={1.0,2.0,3.0};
        const array[real,3] B={2.0,3.0,4.0};''',
        init='f.out[x|:]={real(x),2.0,3.0};')
    data = run_source(tmp_path, backend, source)
    np.testing.assert_array_equal(data['a'][-1], 2.0 * np.arange(67) + 48.0)
