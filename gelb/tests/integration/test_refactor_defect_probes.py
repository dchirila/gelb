"""Pin accepted contracts and narrowly identify current compiler defects."""

import json
import re
import shlex
import subprocess
import sys

import numpy as np
import pytest

from gelb.tests.integration._toolchain import NC_FFLAGS, requires_compiler
from gelb.tests.integration.test_simd_vector_body import BACKENDS, CONFIGS, run_program


class KnownDefect(AssertionError):
    """Only a reproduced, identified defect may satisfy a strict xfail."""


def expected_failure(reason):
    return pytest.mark.xfail(strict=True, raises=KnownDefect, reason=reason)


def source(gauge="v = u.in[x | 0];", *, constants="", functions="", q=1,
           kind="real", init="u.out[x | :] = 1.0 + real(x);",
           dynamic="u.out[x | :] = u.in[x | :];", outputs="real v", extra=""):
    return f'''simulation_description("compiler contract regression");
{('global_constants {' + constants + '}') if constants else ''}
{functions}
lattices {{ lattice u(1, {q}, {kind}, 4, false); {extra} }}
initializer I {{ {init} }}
dynamic D {{ {dynamic} }}
gauge G -> ({outputs}) {{ {gauge} }}
node_classes {{ node_class BULK(I, D, G); }}
geometry {{ nodes[:] = BULK; }}
'''


REJECTIONS = {
    "global_name_in_gauge": source("real S = u.in[x | 0]; v = S * 3.0;", constants="const real S = 2.0;"),
    "global_name_in_parameter": source("v = F(u.in[x | 0]);", constants="const real S = 2.0;",
        functions="function F(real S) -> (real r) { r = S * 3.0; }"),
    "global_name_in_function_local": source("v = F(u.in[x | 0]);", constants="const real S = 2.0;",
        functions="function F(real a) -> (real r) { real S = a; r = S * 3.0; }"),
    "long_array_literal_element": source("array[real, 2] a2 = {u.in[x | 0], 1.0}; array[real, 2] b = {a2, 5.0}; v = b[0] + b[1];"),
    "constant_element_zero_divisor": source("v = 7.0 / A[0];", constants="const array[real, 2] A = {0.0, 1.0};"),
}
PROGRAMS = {
    "singleton_local_element": source("array[real, 1] a1 = u.in[x | 0:0]; array[real, 2] b = {a1, 5.0}; v = b[0] + b[1];", q=2),
    "singleton_slice_element": source("array[real, 2] b = {u.in[x | :], 5.0}; v = b[0] + b[1];"),
    "singleton_element_store": source("v = h.in[x | 0];", extra="lattice h(1, 9, real, 4, false);",
        init="u.out[x | 0] = 1.0 + real(x); h.out[x | :] = 0.0;",
        dynamic="u.out[x | 0] = u.in[x | 0]; h.out[x | :] = {u.in[x | :], 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0};"),
    "narrow_overflow": source("real32 a = 1.0e300; v = real(a);"),
    "late_constants": source(dynamic="u.out[x | 0] = u.in[x | 0] * K;") + "global_constants { const real K = 2.0; }",
    "named_extent": source("array[real, Q] a = {u.in[x | 0], 1.0}; v = a[0] + a[1];", constants="const int Q = 2;"),
    "named_zero_slice": source("v = sum(u.in[x | Z:]);", constants="const int Z = 0;"),
    "named_nonzero_slice": source("array[real, 7] s = u.in[x | K:]; v = sum(s);", q=9, constants="const int K = 2;"),
    "integer_literal_division": source("a = u.in[x | 1]; b = u.in[x | 2];", q=3,
        init="u.out[x | :] = 0.0;", outputs="real a, real b",
        dynamic="int k = 3; u.out[x | 0] = u.in[x | 0]; u.out[x | 1:2] = real({k, 7} / {2, 2});"),
}
for route in ("local", "slice"):
    PROGRAMS[f"zero_matmul_{route}"] = source(
        "array[real, 2] v = {1.0, sqrt(u.in[x | 0])}; array[real, 2] p = matmul(M, v); p0 = p[0]; p1 = p[1];"
        if route == "local" else "p0 = h.in[x | 0]; p1 = h.in[x | 1];",
        constants="const array[real, {2, 2}] M = {{1.0, 0.0}, {0.0, 1.0}};",
        init="u.out[x | 0] = -1.0;" + ("h.out[x | :] = 0.0;" if route == "slice" else ""),
        dynamic="u.out[x | 0] = u.in[x | 0];" + ("array[real, 2] v = {1.0, sqrt(u.in[x | 0])}; h.out[x | :] = matmul(M, v);" if route == "slice" else ""),
        extra="lattice h(1, 2, real, 4, false);" if route == "slice" else "", outputs="real p0, real p1")
    PROGRAMS[f"narrow_matmul_{route}"] = source(
        "array[real32, 2] v = u.in[x | :]; array[real32, 2] p = matmul(M, v); p0 = p[0]; p1 = p[1];"
        if route == "local" else "p0 = h.in[x | 0]; p1 = h.in[x | 1];",
        constants="const array[real32, {2, 2}] M = {{0.1, 0.9}, {0.1, 2.3}};", q=2, kind="real32",
        init="u.out[x | :] = 0.1;" + ("h.out[x | :] = 0.0;" if route == "slice" else ""),
        dynamic="u.out[x | :] = u.in[x | :];" + ("h.out[x | :] = matmul(M, {u.in[x | 0], u.in[x | 1]});" if route == "slice" else ""),
        extra="lattice h(1, 2, real32, 4, false);" if route == "slice" else "", outputs="real32 p0, real32 p1")
for n in (2, 9):
    PROGRAMS[f"mixed_dot_{n}"] = source(f"array[real32, {n}] a = u.in[x | :]; r = dot_prod(W, a);",
        constants=f"const array[real, {n}] W = {{{', '.join(['1.0'] + ['1.0e-10'] * (n - 1))}}};",
        q=n, kind="real32", init="u.out[x | :] = 1.0;", outputs="real r")


PARAMS = []
for case in PROGRAMS:
    for cfg in CONFIGS:
        config = cfg.values[0]
        marks = list(cfg.marks)
        if config != "fortran" and (
                case.startswith(("narrow_matmul", "mixed_dot")) or case == "integer_literal_division"):
            marks.append(expected_failure(case.replace("_", " ")))
        PARAMS.append(pytest.param(case, config, marks=marks, id=f"{case}-{config}"))


@pytest.mark.parametrize("case,config", PARAMS)
def test_runtime_contract(tmp_path, case, config):
    result, data = run_program(tmp_path, config, PROGRAMS[case])
    log = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout + result.stderr)
    assert result.returncode == 0, log
    values = {name: array[-1] for name, (dims, array) in data.items() if "time" in dims and name != "time"}
    if case.startswith("zero_matmul"):
        assert np.isnan(values["p1"]).all()
        assert (np.isnan(values["p0"]) | (values["p0"] == 1.0)).all()
        return
    if case.startswith("narrow_matmul"):
        assert all(values[name].dtype == np.dtype("float32") for name in ("p0", "p1"))
        expected = {"p0": np.float32(0.09999999403953552), "p1": np.float32(0.24000000953674316)}
        wrong = {"p0": np.float32(0.10000000149011612), "p1": np.float32(0.23999999463558197)}
    elif case.startswith("mixed_dot"):
        assert values["r"].dtype == np.dtype("float64")
        expected = {"r": 1.0000000001 if case.endswith("_2") else 1.0000000008}
        wrong = {"r": 1.0}
    elif case == "integer_literal_division":
        expected, wrong = {"a": 1.0, "b": 3.0}, {"a": 1.5, "b": 3.5}
    else:
        u = np.arange(1.0, 5.0)
        expected = {"v": {
            "singleton_local_element": u + 5, "singleton_slice_element": u + 5,
            "singleton_element_store": u, "narrow_overflow": np.inf,
            "late_constants": u * 2, "named_extent": u + 1,
            "named_zero_slice": u, "named_nonzero_slice": u * 7,
        }[case]}
        wrong = {}
    assert values.keys() == expected.keys()
    if config != "fortran" and wrong and all((values[k] == v).all() for k, v in wrong.items()):
        raise KnownDefect(f"{case}: reproduced incorrect arithmetic width")
    for name, value in expected.items():
        np.testing.assert_array_equal(values[name], np.broadcast_to(value, values[name].shape))


@pytest.mark.parametrize("case", list(REJECTIONS))
def test_required_diagnostic(tmp_path, case):
    path = tmp_path / "probe.gelb"
    path.write_text(REJECTIONS[case])
    result = subprocess.run([sys.executable, "-P", "-m", "gelb.gelbc", str(path), "--diagnostics-json"],
                            capture_output=True, text=True, cwd=tmp_path, timeout=60)
    diagnostics = json.loads(result.stdout)["diagnostics"]
    errors = [d for d in diagnostics if d["severity"] == "error"]
    if result.returncode == 0 and not errors:
        raise KnownDefect("program accepted without the required diagnostic")
    assert result.returncode == 1 and errors, result.stdout + result.stderr
    assert not any("internal" in d.get("code", "").lower() for d in errors)


def emit(tmp_path, config, text):
    path = tmp_path / "probe.gelb"
    path.write_text(text)
    out = path.with_suffix({"fortran": ".f90", "cuda": ".cu"}.get(config, ".cpp"))
    args = [sys.executable, "-P", "-m", "gelb.gelbc", str(path), "-b", BACKENDS.get(config, "cpu_highway"), "-o", str(out)]
    if config in ("soa", "aos", "cbt"):
        args += ["--storage-layout", config]
    result = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return out


@requires_compiler
def test_narrow_overflow_unflagged_syntax(tmp_path):
    out = emit(tmp_path, "fortran", PROGRAMS["narrow_overflow"])
    result = subprocess.run(["gfortran", "-fsyntax-only", "-ffree-line-length-none",
                             *shlex.split(NC_FFLAGS), str(out)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("config", CONFIGS)
def test_constant_element_folded(tmp_path, config):
    out = emit(tmp_path, config, source("v = u.in[x | 0] * A[1];",
                                      constants="const array[real, 2] A = {0.0, 1.0};"))
    pattern = r"\bg__a\(1\)" if config == "fortran" else r"\bg_A\[1\]"
    assert not re.search(pattern, out.read_text())


@pytest.mark.parametrize('config', CONFIGS)
def test_shapes_indices_and_late_constants(tmp_path, config):
    text = source('''
        const int K = 2;
        array[real, Nx/2] a = F(u.in[x | 0]);
        array[real, SZ[0, 1]] b = {1.0, 2.0, 3.0};
        array[real, K] c = {b[1+1], b[2:1+1]};
        v = dot_prod(a, c) + Y;
        ''', functions='''
        function F(real z) -> (array[real, Q] r) { r = Later(z); }
        function Later(real z) -> (array[real, Q] r) { r = {z, z}; }
        ''') + '''global_constants {
            const int Q = 2;
            const array[int, {2, 2}] SZ = {{2, 3}, {3, 2}};
            const array[real, 2] W = {1.0, 2.0};
            const real Y = W[0] + 1.0;
        }'''
    result, data = run_program(tmp_path, config, text)
    assert result.returncode == 0, result.stdout + result.stderr
    np.testing.assert_array_equal(data['v'][1][-1], np.arange(1.0, 5.0) * 6 + 2)


@pytest.mark.parametrize('config', CONFIGS)
def test_singleton_values_widths_and_assignments(tmp_path, config):
    text = source('''
        array[real, 1] a = u.in[x | :];
        array[real32, 1] s = real32(1.0/3.0);
        array[int16, 1] k = int16(3);
        array[bool, 1] p = true;
        array[real, 8] b = {a, 2.0*a, real(k), F(a[0]), a[:], s, real(p), 5.0};
        array[real, 2] assigned;
        assigned = {a, a};
        v = sum(b) + sum(assigned);
        sign = b[0];
        array[bool, 2] flags = {p, false};
        truth = flags[0];
        ''', functions='function F(real z) -> (array[real, 1] r) { r = z; }',
        init='u.out[x | 0] = -0.0;', outputs='real v, real sign, bool truth')
    result, data = run_program(tmp_path, config, text)
    assert result.returncode == 0, result.stdout + result.stderr
    assert np.signbit(data['sign'][1]).all()
    assert data['truth'][1].all()
    np.testing.assert_array_equal(data['v'][1], np.full((2, 4), 9.0 + float(np.float32(1.0/3.0))))


@pytest.mark.parametrize('config', CONFIGS)
@pytest.mark.parametrize('element', ['a', 'u.in[x | :]'])
def test_repeated_singleton_arithmetic_in_expanded_store(tmp_path, config, element):
    text = source('v = h.in[x | 0] + h.in[x | 1];',
        extra='lattice h(1, 9, real, 4, false);',
        init='u.out[x | 0] = 1.5; h.out[x | :] = 0.0;',
        dynamic=f'''array[real, 1] a = u.in[x | :]; u.out[x | 0] = u.in[x | 0];
            h.out[x | :] = {{2.0*{element}, 2.0*{element}, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0}};''')
    text = text.replace('4, false', '64, false')
    control = text.replace(f'2.0*{element}', '2.0*a[0]' if element == 'a' else '2.0*u.in[x | 0]')
    values = []
    for label, program in [('candidate', text), ('control', control)]:
        folder = tmp_path / label
        folder.mkdir()
        result, data = run_program(folder, config, program)
        assert result.returncode == 0, result.stdout + result.stderr
        values.append(data['v'][1][-1])
    np.testing.assert_array_equal(values[0], values[1])
    np.testing.assert_array_equal(values[0], np.full(64, 6.0))


@pytest.mark.parametrize('config', CONFIGS)
@pytest.mark.parametrize('global_array,grid,offset', [(False, 4, 2), (True, 4, 2), (False, 8, 6)])
def test_explicit_grid_constant_array_index(tmp_path, config, global_array, grid, offset):
    declaration = 'array[real, 3] w = {1.0, 2.0, 3.0};'
    text = source(('' if global_array else declaration) + f'v = w[Nx-{offset}];',
                  constants='const ' + declaration if global_array else '').replace('4, false', f'{grid}, false')
    result, data = run_program(tmp_path, config, text)
    assert result.returncode == 0, result.stdout + result.stderr
    np.testing.assert_array_equal(data['v'][1], np.full((2, grid), 3.0))


@pytest.mark.parametrize('config', CONFIGS)
@pytest.mark.parametrize('case', ['input_coordinate', 'input_constant', 'negative_extent'])
def test_array_indices_rejected_before_backend_emission(tmp_path, config, case):
    if case == 'negative_extent':
        text = source('array[real, SZ[-1]] a = {1.0, 2.0, 3.0}; v = a[0];',
                      constants='const array[int, 2] SZ = {2, 3};')
        context = 'array shape'
    else:
        text = source('v = F(x);' if case == 'input_coordinate' else 'v = F(3);',
            functions='function F(int i) -> (real r) { array[real, 3] w = {1.0, 2.0, 3.0}; r = w[i]; }')
        context = 'array index'
    path = tmp_path / 'invalid.gelb'
    path.write_text(text)
    args = [sys.executable, '-P', '-m', 'gelb.gelbc', str(path), '--diagnostics-json',
            '-b', BACKENDS.get(config, 'cpu_highway')]
    if config in ('soa', 'aos', 'cbt'):
        args += ['--storage-layout', config]
    result = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 1, result.stdout + result.stderr
    errors = [d for d in json.loads(result.stdout)['diagnostics'] if d['severity'] == 'error']
    assert len(errors) == 1 and context in errors[0]['message']
    line = errors[0]['range']['startLine']
    assert ('SZ[-1]' if case == 'negative_extent' else 'w[i]') in text.splitlines()[line]


@pytest.mark.parametrize('config', CONFIGS)
def test_constant_array_slices_and_carried_matrix_sum(tmp_path, config):
    text = source('v = S(W[1:]) + det; ordered = SM(M);', constants='''
        const array[real, 3] W = {1.0, 2.0, 4.0};
        const array[real, {2, 2}] M = {{1.0, -1.0}, {1.0e-30, 0.0}};
        const array[real, {2, 3}] A = {{1.0, 2.0, 3.0}, {4.0, 5.0, 6.0}};
        const array[real, {2, 2}] sub = A[:, 1:];
        const real det = determinant(sub);
        ''', functions='''
        function S(array[real, 2] a) -> (real r) { r = a[0] + a[1]; }
        function SM(array[real, {2, 2}] m) -> (real r) { r = sum(m); }
        ''', outputs='real v, real ordered')
    result, data = run_program(tmp_path, config, text)
    assert result.returncode == 0, result.stdout + result.stderr
    np.testing.assert_array_equal(data['v'][1], 3.0)
    np.testing.assert_array_equal(data['ordered'][1], 1.0e-30)


@pytest.mark.parametrize('config', CONFIGS)
def test_folded_zero_boundary_preserves_sign(tmp_path, config):
    text = source('v = u.in[x | 0];', q=2, init='u.out[x | :] = 0.0;',
        constants='const array[real, 2] W = {1.0/6.0, 1.0/6.0}; const real TR = 0.0;',
        dynamic='u.out[x | 0] = -u.in[x | 1] + 2.0 * W[1] * TR; u.out[x | 1] = u.in[x | 0];')
    text = text.replace('real, 4, false', 'real, 64, false')
    result, data = run_program(tmp_path, config, text)
    assert result.returncode == 0, result.stdout + result.stderr
    values = data['v'][1]
    assert (values == 0.0).all() and not np.signbit(values).any()


NARROW_STORES = source('''
    real32 a = 1.0e300;
    real32 b = 0.0; b = -1.0e300;
    array[real32, 2] c = {1.0e300, -1.0e300};
    array[real32, 2] d = 1.0e300;
    const real32 local = 1.0e300;
    real32 product = 1.0e200 * 1.0e100;
    v = real(a); neg = real(b); elem = real(c[0]); broadcast = real(d[0]);
    stored = real(u.in[x | 0]); named = real(R); arrayelem = real(AR[0]);
    folded = real(product); block = real(local); arg = F(1.0e300);
    ''', kind='real32', init='u.out[x | 0] = 1.0e300;',
    constants='const real32 R = 1.0e300; const array[real32, 2] AR = {1.0e300, 1.0};',
    functions='function F(real32 a) -> (real r) { r = real(a); }',
    outputs='real v, real neg, real elem, real broadcast, real stored, real named, real arrayelem, real folded, real block, real arg')


@requires_compiler
def test_narrow_constant_stores_pass_unflagged_fortran(tmp_path):
    out = emit(tmp_path, 'fortran', NARROW_STORES)
    result = subprocess.run(['gfortran', '-fsyntax-only', '-ffree-line-length-none',
        *shlex.split(NC_FFLAGS), str(out)], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('config', CONFIGS)
def test_narrow_constant_stores_execute_as_infinities(tmp_path, config):
    result, data = run_program(tmp_path, config, NARROW_STORES)
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ('v', 'neg', 'elem', 'broadcast', 'stored', 'named', 'arrayelem', 'folded', 'block', 'arg'):
        np.testing.assert_array_equal(data[name][1], -np.inf if name == 'neg' else np.inf)
