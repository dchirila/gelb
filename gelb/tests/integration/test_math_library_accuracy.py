"""The library functions against an independent reference (user manual,
Numerical semantics: Library functions).

Each backend's implementation of sin, cos, tan, tanh, exp, log and sqrt
is compared with mpmath at 60 digits on 67 arguments, and so is the
compiler's fold of the same functions on constant arguments, in binary64
and in binary32.  Every result is measured two ways:

- *from the rounded result*: the distance, in ULPs of the function's
  width, from the correctly rounded value.  This is the metric of the
  CUDA Math API tables (CUDA 13.2, "the maximum observed absolute value
  of the difference in ULPs between the value returned by the function
  and a correctly rounded result", bounds "derived from extensive, though
  not exhaustive, testing" and "not guaranteed") and of glibc's manual
  (2.39, "Known Maximum Errors in Math Functions", round-to-nearest
  only; "functions not listed do not have known errors").
- *from the exact value*: the distance from the unrounded reference, in
  ULPs of the binary64 nearest it.  Recorded and printed with ``-s``, not
  asserted: no implementation states its bound in this metric.

Highway states its bound in a third metric.  ``math-inl.h`` (Highway
1.4.0, checked in under ``third_party/highway``) gives a "Max Error" in
ULPs per function, which ``math_test.cc`` measures as the ULP delta
between the vector result and the platform's ``std::`` function on
sampled inputs.  The cpu_highway results are therefore compared with
the host libm's value (Python's ``math`` module calls it) under
Highway's bound, and the host values themselves under glibc's bound.

The bounds asserted, binary64:

- glibc 2.39 on x86-64 (``cpu_fortran_serial``, the folds, Highway's
  lane-wise ``tan`` and the host values): sin 1, cos 1, exp 1, log 1,
  tanh 2.  ``tan`` is not listed, so the test keeps a ceiling of 1 ULP
  that is its own, not glibc's.
- CUDA 13.2 (``gpu_cuda_cpp``): sin 2, cos 2, tan 2, tanh 1, exp 1,
  log 1.
- Highway 1.4.0 (``cpu_highway``, from the host libm): exp 1, sin and
  cos 3, log 4, tanh 4.
- ``sqrt`` is correctly rounded everywhere (IEEE 754): 0 ULP from the
  rounded result, half an ULP from the exact value.

A binary32 fold is the binary64 fold rounded once to binary32 (user
manual, Numerical semantics: Constant folding).
The test asserts exactly that, and that the result is within 1 binary32
ULP of the correctly rounded binary32 value (one binary64 error of at
most one ULP, then one rounding).

These bounds are the implementations' measured maxima, stated by their
authors; the contract promises the bound of the documented
implementation, not the measurement, and no bound across backends.
glibc's bounds apply where the libm is glibc; on another libm the host
comparisons are recorded, not asserted.
"""

import math
import platform

import mpmath
import numpy as np
import pytest

from gelb.tests.integration.test_real_width_contract import BACKENDS, _run

_CELLS = 67
# arguments inside every implementation's valid range, never zero
_PROGRAM = f"""simulation_description("library accuracy");
lattices {{ lattice u(1, 1, real, {_CELLS}, false); }}
initializer I {{ u.out[x | 0] = 0.37 + 0.1 * x; }}
dynamic D {{ u.out[x | 0] = u.in[x | 0]; }}
gauge G -> (real s, real c, real tn, real h, real e, real l, real q) {{
    s = sin(u.in[x | 0]);
    c = cos(u.in[x | 0]);
    tn = tan(u.in[x | 0]);
    h = tanh(u.in[x | 0]);
    e = exp(u.in[x | 0]);
    l = log(u.in[x | 0]);
    q = sqrt(u.in[x | 0]);
}}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""
_FUNCTIONS = {"s": "sin", "c": "cos", "tn": "tan", "h": "tanh", "e": "exp", "l": "log", "q": "sqrt"}
_REFERENCE = {"sin": mpmath.sin, "cos": mpmath.cos, "tan": mpmath.tan, "tanh": mpmath.tanh,
              "exp": mpmath.exp, "log": mpmath.log, "sqrt": mpmath.sqrt}
_HOST = {"sin": math.sin, "cos": math.cos, "tan": math.tan, "tanh": math.tanh,
         "exp": math.exp, "log": math.log, "sqrt": math.sqrt}

# documented maximum errors, from the correctly rounded result
_GLIBC = {"sin": 1, "cos": 1, "tan": 1, "tanh": 2, "exp": 1, "log": 1, "sqrt": 0}   # tan: the test's ceiling
_CUDA = {"sin": 2, "cos": 2, "tan": 2, "tanh": 1, "exp": 1, "log": 1, "sqrt": 0}
# Highway's, from the platform's std:: function; tan and sqrt are not Highway's
_HIGHWAY = {"sin": 3, "cos": 3, "tanh": 4, "exp": 1, "log": 4}

_LIBM_IS_GLIBC = platform.libc_ver()[0] == "glibc"


def _rounded(reference, width):
    """``reference`` correctly rounded to ``width`` bits of precision
    (53: binary64, 24: binary32), as an mpf."""
    with mpmath.workprec(width):
        return +reference


def _ulp(value, width):
    if width == 53:
        return mpmath.mpf(math.ulp(float(value)))
    return mpmath.mpf(float(abs(np.spacing(np.float32(float(value))))))


def ulps_from_rounded(value, reference, width=53):
    """|value - rounded(reference)| in ULPs of the rounded result (the
    CUDA and glibc metric)."""
    nearest = _rounded(reference, width)
    return float(abs(mpmath.mpf(value) - nearest) / _ulp(nearest, width))


def ulps_from_exact(value, reference):
    """|value - reference| in ULPs of the binary64 nearest the reference."""
    return float(abs(mpmath.mpf(value) - reference) / mpmath.mpf(math.ulp(float(reference))))


def _ordered(value):
    i = int(np.float64(value).view(np.int64))
    return i if i >= 0 else -(2 ** 63) - i


def ulps_apart(a, b):
    """The number of binary64 values between ``a`` and ``b`` (Highway's
    ULP delta)."""
    return abs(_ordered(a) - _ordered(b))


@pytest.mark.parametrize("backend", BACKENDS)
def test_each_library_function_is_within_its_documented_bound(tmp_path, backend, capsys):
    mpmath.mp.dps = 60
    nc = _run(tmp_path, _PROGRAM, backend)
    arguments = [0.37 + 0.1 * x for x in range(_CELLS)]
    report = []
    for key, fname in _FUNCTIONS.items():
        values = np.asarray(nc[key][1]).tolist()
        references = [_REFERENCE[fname](mpmath.mpf(a)) for a in arguments]
        from_rounded = max(ulps_from_rounded(v, r) for v, r in zip(values, references))
        from_exact = max(ulps_from_exact(v, r) for v, r in zip(values, references))
        line = f"{fname} {from_rounded:.2f} from rounded, {from_exact:.2f} from exact"
        if backend == "cpu_highway" and fname in _HIGHWAY:
            host = [_HOST[fname](a) for a in arguments]
            delta = max(ulps_apart(v, h) for v, h in zip(values, host))
            assert delta <= _HIGHWAY[fname], (fname, delta, _HIGHWAY[fname])
            line += f", {delta} from the host libm"
            if _LIBM_IS_GLIBC:
                host_error = max(ulps_from_rounded(h, r) for h, r in zip(host, references))
                assert host_error <= _GLIBC[fname], (fname, "host", host_error, _GLIBC[fname])
        elif backend == "gpu_cuda_cpp":
            assert from_rounded <= _CUDA[fname], (fname, from_rounded, _CUDA[fname])
        elif _LIBM_IS_GLIBC:
            assert from_rounded <= _GLIBC[fname], (fname, from_rounded, _GLIBC[fname])
        report.append(line)
    with capsys.disabled():
        print(f"\n{backend}: measured max ULP error: " + "; ".join(report))


# --- the folds ---------------------------------------------------------------

_FOLD_ARGUMENTS = (0.37, 2.9, 11.3)


def _folded_program():
    constants, outputs, body = [], [], []
    for i, a in enumerate(_FOLD_ARGUMENTS):
        constants.append(f"const real A{i} = {a!r};")
        constants.append(f"const real32 S{i} = {a!r};")
        for key, fname in _FUNCTIONS.items():
            for width, cname in (("64", f"A{i}"), ("32", f"S{i}")):
                out = f"{key}{width}_{i}"
                outputs.append(f"real {out}")
                body.append(f"{out} = {fname}({cname});")
    return f"""simulation_description("folded library accuracy");
global_constants {{ {' '.join(constants)} }}
lattices {{ lattice u(1, 1, real, 4, false); }}
initializer I {{ u.out[x | 0] = 0.0; }}
dynamic D {{ u.out[x | 0] = u.in[x | 0]; }}
gauge G -> ({', '.join(outputs)}) {{ {' '.join(body)} }}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:] = B; }}
"""


@pytest.mark.parametrize("backend", BACKENDS)
def test_folded_library_values_are_the_hosts_within_its_bound(tmp_path, backend, capsys):
    """Every backend carries the host's binary64 fold bit for bit, and its
    binary32 fold is that value rounded once; both are measured
    against the 60-digit reference."""
    mpmath.mp.dps = 60
    nc = _run(tmp_path, _folded_program(), backend)
    report = {}
    for i, a in enumerate(_FOLD_ARGUMENTS):
        for key, fname in _FUNCTIONS.items():
            value = float(np.asarray(nc[f"{key}64_{i}"][1]).tolist()[0])
            assert value == _HOST[fname](a), (fname, a, value)
            reference = _REFERENCE[fname](mpmath.mpf(a))
            report[fname] = max(report.get(fname, 0.0), ulps_from_exact(value, reference))
            if _LIBM_IS_GLIBC:
                from_rounded = ulps_from_rounded(value, reference)
                assert from_rounded <= _GLIBC[fname], (fname, a, from_rounded, _GLIBC[fname])
            # binary32: the binary64 fold of the rounded argument, rounded once
            a32 = float(np.float32(a))
            value32 = float(np.asarray(nc[f"{key}32_{i}"][1]).tolist()[0])
            assert value32 == float(np.float32(_HOST[fname](a32))), (fname, a32, value32)
            reference32 = _REFERENCE[fname](mpmath.mpf(a32))
            from_rounded32 = ulps_from_rounded(value32, reference32, width=24)
            assert from_rounded32 <= 1, (fname, a32, from_rounded32)
    with capsys.disabled():
        print(f"\n{backend}: folded binary64 values, measured max ULP from exact: "
              + ", ".join(f"{n} {m:.2f}" for n, m in report.items()))
