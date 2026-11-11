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


def build_failure(case, config):
    if case == "singleton_local_element" and config != "fortran":
        return r'(cannot convert .*double \[1\].*double|a value of type "double \*" cannot be assigned)'
    if case == "singleton_element_store" and config == "fortran":
        return "Incompatible ranks 0 and 1"
    if case == "late_constants":
        return r"You reference K\. However, you only define it later"
    if case == "named_extent":
        return ("Expected a right parenthesis" if config == "fortran" else
                "Array1DLiteral_N as a free-standing expression is unsupported")
    if case == "named_zero_slice":
        return "expects an array argument, got scalar"
    return None


PARAMS = []
for case in PROGRAMS:
    for cfg in CONFIGS:
        config = cfg.values[0]
        marks = list(cfg.marks)
        if build_failure(case, config) or (config != "fortran" and (
                case.startswith(("narrow_matmul", "mixed_dot")) or case == "integer_literal_division")):
            marks.append(expected_failure(case.replace("_", " ")))
        PARAMS.append(pytest.param(case, config, marks=marks, id=f"{case}-{config}"))


@pytest.mark.parametrize("case,config", PARAMS)
def test_runtime_contract(tmp_path, case, config):
    result, data = run_program(tmp_path, config, PROGRAMS[case])
    log = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout + result.stderr)
    pattern = build_failure(case, config)
    if result.returncode and pattern and re.search(pattern, log):
        raise KnownDefect(pattern)
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


@pytest.mark.parametrize("case", REJECTIONS)
@expected_failure("invalid declarations or constant zero divisors are accepted")
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
@expected_failure("out-of-range real32 constant is not folded to infinity")
def test_narrow_overflow_unflagged_syntax(tmp_path):
    out = emit(tmp_path, "fortran", PROGRAMS["narrow_overflow"])
    result = subprocess.run(["gfortran", "-fsyntax-only", "-ffree-line-length-none",
                             *shlex.split(NC_FFLAGS), str(out)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=60)
    if result.returncode and "Arithmetic overflow converting REAL(8) to REAL(4)" in result.stderr:
        raise KnownDefect(result.stderr)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("config", CONFIGS)
@expected_failure("constant-index array elements remain runtime reads")
def test_constant_element_folded(tmp_path, config):
    out = emit(tmp_path, config, source("v = u.in[x | 0] * A[1];",
                                      constants="const array[real, 2] A = {0.0, 1.0};"))
    pattern = r"\bg__a\(1\)" if config == "fortran" else r"\bg_A\[1\]"
    if re.search(pattern, out.read_text()):
        raise KnownDefect("constant-array element read was emitted")
