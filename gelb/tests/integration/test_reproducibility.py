"""Reproducibility across execution configurations (user manual,
Numerical semantics: Reproducibility).

Three programs on a 67 x 8 periodic two-dimensional grid, each with a
streaming step so that the CUDA tiled path has a stencil to tile:

- an ordinary D2Q9 program with a per-cell initial state, reductions
  (``sum``, ``dot_prod`` with zero coefficients) and library calls;
- the fusion probe (user manual, Validation and Convergence: Numerical
  conformance): a reduction with coefficients
  ``[1, 1, 1, 1, 1 + 2^-52, 1, 1, 1, 1]`` and inputs ``[-1, 0, 0, 0,
  1 - 2^-52, 0, 0, 0, 0]`` in every cell, whose result shows a fused
  multiply-add;
- the library-dispatch probe: ``sin(10.0)``, ``cos(20.0)``,
  ``tan(10.0)``, ``tanh(0.1)``, ``exp(0.1)`` and ``log(10.0)`` from
  lattice values that are uniform across the grid;
- the same two computed in the **dynamic** block from the streamed
  values and stored in the lattice (``fusion-dyn``, ``library-dyn``), since CUDA
  applies thread coarsening and tiling to the dynamic kernel only: the
  gauge versions prove the gauge kernel, these prove the coarsened and
  the tiled kernels run the sensitive arithmetic.  The generated
  code is checked to hold that arithmetic inside the dynamic kernel
  (the reduction helper, the library calls) together with the path
  taken (the coarsening loop, the shared-memory tile).

On ``cpu_highway`` each is run with 1, 2 and 4 OpenMP threads and the
``soa``, ``aos`` and ``cbt`` storage layouts (``cbt`` only where the
host compiles for AVX-512, as gelbc rejects it elsewhere), in a default
and in a strict build; on ``gpu_cuda_cpp`` with two block sizes, thread
coarsening 4 and shared-memory tiling, in strict builds, and with the
two block sizes in a default build.  Within one build mode every
configuration must give the same bits; for the sensitive programs every
cell must also give the same bits, within each variant of a default
CUDA build too, and in a strict build the fusion probe gives the
unfused value.  The default CUDA outcome across coarsening and tiling
is recorded (printed with ``-s``), not asserted (user manual, Numerical
semantics: Build modes).

A fourth program probes the default CUDA build: a product in the inner-axis coordinate
added to a cell value, whose fusion nvcc may decide differently once
the term is hoisted out of a coarsening loop.  Strict builds must agree
bitwise across coarsening 1 and 4; the default-build outcome is
recorded for the manual, not asserted.
"""

import itertools

import numpy as np
import pytest

from gelb.backends.highway.common import _detect_avx512_available
from gelb.tests.integration.test_real_width_contract import (
    _FUSION_PROBE_COEFF_4, _FUSION_PROBE_INPUT_4, _FUSION_PROBE_UNFUSED, _generated, _run,
    requires_cpp_highway_compiler, requires_gpu_cuda_cpp_compiler)

_NX, _NY = 67, 8
_D2Q9_HEADER = f"""global_constants {{
    const real TAU = 0.8;
    const real K = 0.09;
    const array[real, 9] EX = {{0.0, 1.0, 0.0, -1.0, 0.0, 1.0, -1.0, -1.0, 1.0}};
    const array[real, 9] EY = {{0.0, 0.0, 1.0, 0.0, -1.0, 1.0, 1.0, -1.0, -1.0}};
    const array[real, 9] W = {{4.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0,
                             1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0}};
    const array[real, 9] C = {{1.0, 1.0, 1.0, 1.0, {_FUSION_PROBE_COEFF_4!r}, 1.0, 1.0, 1.0, 1.0}};
}}
lattices {{ lattice f(2, 9, real, {{{_NX}, {_NY}}}, {{true, true}}); }}
"""
_FOOTER = """node_classes { node_class B(I, D, G); }
geometry { nodes[:, :] = B; }
"""
_ORDINARY = f"""simulation_description("reproducibility across configurations");
{_D2Q9_HEADER}function Eq(real rho, real ux, real uy) -> (array[real, 9] feq) {{
    real usq = ux * ux + uy * uy;
    array[real, 9] eu = EX * ux + EY * uy;
    feq = W * rho * (1.0 + 3.0 * eu + 4.5 * eu * eu - 1.5 * usq);
}}
initializer I {{
    real rho = 1.0 + 0.01 * sin(K * x) * cos(K * y);
    real ux = 0.02 * exp(-0.01 * x) * cos(K * y);
    real uy = -0.02 * sin(K * x);
    f.out[x, y | :] = Eq(rho, ux, uy);
}}
dynamic D {{
    array[real, 9] fIn = upstream_dfs(f, x, y, {{EX, EY}});
    real rho = sum(fIn);
    real ux = dot_prod(EX, fIn) / rho;
    real uy = dot_prod(EY, fIn) / rho;
    f.out[x, y | :] = fIn - (fIn - Eq(rho, ux, uy)) / TAU;
}}
gauge G -> (real rho, real ux, real uy) {{
    array[real, 9] a = f.in[x, y | :];
    rho = sum(a);
    ux = dot_prod(EX, a) / rho;
    uy = dot_prod(EY, a) / rho;
}}
{_FOOTER}"""
_STREAMING = """dynamic D {
    array[real, 9] fIn = upstream_dfs(f, x, y, {EX, EY});
    f.out[x, y | :] = fIn;
}
"""
_FUSION_PROBE_2D = f"""simulation_description("the fusion probe across configurations");
{_D2Q9_HEADER}initializer I {{
    f.out[x, y | :] = 0.0;
    f.out[x, y | 0] = -1.0;
    f.out[x, y | 4] = {_FUSION_PROBE_INPUT_4!r};
}}
{_STREAMING}gauge G -> (real v) {{
    array[real, 9] a = f.in[x, y | :];
    v = dot_prod(C, a);
}}
{_FOOTER}"""
_LIBRARY_PROBE_2D = f"""simulation_description("the library-dispatch probe across configurations");
{_D2Q9_HEADER}initializer I {{ f.out[x, y | :] = 10.0; }}
{_STREAMING}gauge G -> (real s, real c, real tn, real h, real e, real l) {{
    array[real, 9] a = f.in[x, y | :];
    s = sin(a[0]);
    c = cos(2.0 * a[1]);
    tn = tan(a[2]);
    h = tanh(0.01 * a[3]);
    e = exp(0.01 * a[4]);
    l = log(a[5]);
}}
{_FOOTER}"""
_FUSION_PROBE_DYN = f"""simulation_description("the fusion probe in the dynamic block, across configurations");
{_D2Q9_HEADER}initializer I {{
    f.out[x, y | :] = 0.0;
    f.out[x, y | 0] = -1.0;
    f.out[x, y | 4] = {_FUSION_PROBE_INPUT_4!r};
}}
dynamic D {{
    array[real, 9] fIn = upstream_dfs(f, x, y, {{EX, EY}});
    real v = dot_prod(C, fIn);
    f.out[x, y | :] = fIn;
    f.out[x, y | 0] = v;
}}
gauge G -> (real v) {{ v = f.in[x, y | 0]; }}
{_FOOTER}"""
_LIBRARY_PROBE_DYN = f"""simulation_description("the library-dispatch probe in the dynamic block, across configurations");
{_D2Q9_HEADER}initializer I {{ f.out[x, y | :] = 10.0; }}
dynamic D {{
    array[real, 9] fIn = upstream_dfs(f, x, y, {{EX, EY}});
    f.out[x, y | :] = fIn;
    f.out[x, y | 0] = sin(fIn[0]);
    f.out[x, y | 1] = cos(2.0 * fIn[1]);
    f.out[x, y | 2] = tan(fIn[2]);
    f.out[x, y | 3] = tanh(0.01 * fIn[3]);
    f.out[x, y | 4] = exp(0.01 * fIn[4]);
    f.out[x, y | 5] = log(fIn[5]);
}}
gauge G -> (real s, real c, real tn, real h, real e, real l) {{
    s = f.in[x, y | 0];
    c = f.in[x, y | 1];
    tn = f.in[x, y | 2];
    h = f.in[x, y | 3];
    e = f.in[x, y | 4];
    l = f.in[x, y | 5];
}}
{_FOOTER}"""
_PROGRAMS = {
    "d2q9": (_ORDINARY, ("rho", "ux", "uy")),
    "fusion": (_FUSION_PROBE_2D, ("v",)),
    "library": (_LIBRARY_PROBE_2D, ("s", "c", "tn", "h", "e", "l")),
    "fusion-dyn": (_FUSION_PROBE_DYN, ("v",)),
    "library-dyn": (_LIBRARY_PROBE_DYN, ("s", "c", "tn", "h", "e", "l")),
}
_SENSITIVE = ("fusion", "library", "fusion-dyn", "library-dyn")     # every cell must agree
# what the dynamic kernel must contain for the sensitive-in-dynamic programs
_IN_DYNAMIC_KERNEL = {
    "fusion-dyn": ("gelb_dot_prod_const(",),
    "library-dyn": ("sin(", "cos(", "tan(", "tanh(", "exp(", "log("),
}


def _bits(nc, fields):
    return {name: np.asarray(nc[name][1]).view(np.uint64).ravel().tolist() for name in fields}


def _same(a, b):
    return all(a[name] == b[name] for name in a)


def _uniform(bits):
    return all(len(set(values)) == 1 for values in bits.values())


def _check_cells(program, bits, strict):
    if program in _SENSITIVE:
        assert _uniform(bits), {k: sorted(set(v)) for k, v in bits.items()}
    if program in ("fusion", "fusion-dyn") and strict:
        assert set(bits["v"]) == {np.float64(_FUSION_PROBE_UNFUSED).view(np.uint64).item()}


def _dynamic_kernel(code):
    """The text of the generated CUDA dynamic kernel."""
    start = code.index("__global__ void gelb_k_dyn_")
    end = code.find("__global__", start + 1)
    return code[start:end if end > 0 else len(code)]


# --- cpu_highway: threads x layouts x build mode ----------------------------

_HIGHWAY_LAYOUTS = ("soa", "aos") + (("cbt",) if _detect_avx512_available() else ())
_HIGHWAY_RUNS = list(itertools.product((1, 2, 4), _HIGHWAY_LAYOUTS))


@requires_cpp_highway_compiler
@pytest.mark.parametrize("program", list(_PROGRAMS))
@pytest.mark.parametrize("strict", [False, True], ids=["default", "strict"])
def test_highway_threads_and_layouts_give_the_same_bits(tmp_path, strict, program):
    source, fields = _PROGRAMS[program]
    run_args = ("--strict-fp",) if strict else ()
    results = {}
    for threads, layout in _HIGHWAY_RUNS:
        nc = _run(tmp_path / f"t{threads}_{layout}", source, "cpu_highway",
                  extra=f"--storage-layout {layout}", threads=threads, run_args=run_args)
        results[(threads, layout)] = _bits(nc, fields)
    reference = results[(1, "soa")]
    for key, bits in results.items():
        assert _same(bits, reference), key
    _check_cells(program, reference, strict)
    # a multi-threaded run really ran the loop in parallel: the generated
    # code carries the OpenMP directive
    assert "omp parallel" in _generated(tmp_path / "t4_soa", "cpu_highway")


# --- gpu_cuda_cpp: block sizes x coarsening x tiling -----------------------

_CUDA_RUNS = [
    ("b64", ("--cuda-block-size", "64")),
    ("b256", ("--cuda-block-size", "256")),
    ("coarse4", ("--cuda-coarsening", "4")),
    ("tiled", ("--cuda-tiled",)),
]


def _assert_paths_taken(tmp_path, program):
    coarse = _dynamic_kernel(_generated(tmp_path / "coarse4", "gpu_cuda_cpp"))
    tiled = _dynamic_kernel(_generated(tmp_path / "tiled", "gpu_cuda_cpp"))
    assert "Coarsened dyn-kernel launch grid" in _generated(tmp_path / "coarse4", "gpu_cuda_cpp")
    assert "gelb_k < 4" in coarse          # the coarsening loop, inside the kernel
    assert "__shared__" in tiled           # the tile, inside the kernel
    for marker in _IN_DYNAMIC_KERNEL.get(program, ()):
        assert marker in coarse and marker in tiled, (program, marker)


@pytest.mark.gpu
@requires_gpu_cuda_cpp_compiler
@pytest.mark.parametrize("program", list(_PROGRAMS))
def test_cuda_block_sizes_coarsening_and_tiling_agree_in_strict_builds(tmp_path, program):
    source, fields = _PROGRAMS[program]
    results = {}
    for name, args in _CUDA_RUNS:
        nc = _run(tmp_path / name, source, "gpu_cuda_cpp", run_args=("--strict-fp", *args))
        results[name] = _bits(nc, fields)
    reference = results["b64"]
    for name, bits in results.items():
        assert _same(bits, reference), name
    _check_cells(program, reference, strict=True)
    _assert_paths_taken(tmp_path, program)


@pytest.mark.gpu
@requires_gpu_cuda_cpp_compiler
@pytest.mark.parametrize("program", list(_PROGRAMS))
def test_cuda_block_sizes_agree_in_a_default_build(tmp_path, capsys, program):
    # A default build is reproducible across block sizes (the same
    # kernel code); across coarsening and tiling only within each
    # variant.  The latter is observed and recorded, not promised.
    source, fields = _PROGRAMS[program]
    results = {}
    for name, args in _CUDA_RUNS:
        nc = _run(tmp_path / name, source, "gpu_cuda_cpp", run_args=args, strict_cuda=False)
        results[name] = _bits(nc, fields)
    assert _same(results["b256"], results["b64"])
    for name, bits in results.items():      # uniform cells within each variant
        _check_cells(program, bits, strict=False)
    _assert_paths_taken(tmp_path, program)
    with capsys.disabled():
        for name in ("coarse4", "tiled"):
            verdict = "the same bits as" if _same(results[name], results["b64"]) else "different bits from"
            print(f"\ngpu_cuda_cpp default build, {program}: {name} gives {verdict} coarsening 1")
        if program in ("fusion", "fusion-dyn"):
            for name in ("b64", "coarse4", "tiled"):
                value = np.array(results[name]["v"][:1], dtype=np.uint64).view(np.float64).item()
                print(f"gpu_cuda_cpp default build, {program}, {name}: every cell gives {value!r} "
                      f"({'unfused' if value == _FUSION_PROBE_UNFUSED else 'fused'})")


# --- The coarsening probe --------------------------------------------------------

_PROBE = f"""simulation_description("a product in the inner coordinate, hoisted by coarsening");
lattices {{ lattice u(2, 1, real, {{{_NX}, {_NY}}}, {{true, true}}); }}
initializer I {{ u.out[x, y | 0] = 0.1 + 0.001 * y; }}
dynamic D {{ u.out[x, y | 0] = u.in[x, y | 0] + (1.1 * x) * 0.7; }}
gauge G -> (real v) {{ v = u.in[x, y | 0]; }}
node_classes {{ node_class B(I, D, G); }}
geometry {{ nodes[:, :] = B; }}
"""


@pytest.mark.gpu
@requires_gpu_cuda_cpp_compiler
def test_coordinate_product_probe_across_coarsening(tmp_path, capsys):
    strict = {k: _run(tmp_path / f"strict{k}", _PROBE, "gpu_cuda_cpp",
                      run_args=("--strict-fp", "--cuda-coarsening", str(k)))
              for k in (1, 4)}
    assert np.asarray(strict[1]["v"][1]).view(np.uint64).tolist() == \
        np.asarray(strict[4]["v"][1]).view(np.uint64).tolist()
    default = {k: _run(tmp_path / f"default{k}", _PROBE, "gpu_cuda_cpp",
                       run_args=("--cuda-coarsening", str(k)), strict_cuda=False)
               for k in (1, 4)}
    same = np.asarray(default[1]["v"][1]).view(np.uint64).tolist() == \
        np.asarray(default[4]["v"][1]).view(np.uint64).tolist()
    with capsys.disabled():
        print(f"\nCoordinate-product probe, gpu_cuda_cpp default build: coarsening 1 and 4 give "
              f"{'the same' if same else 'different'} bits")
