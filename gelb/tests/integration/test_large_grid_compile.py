"""Large-grid storage regression tests.

Lattice ping-pong storage used to be emitted as ``static`` arrays
(``.bss``): host-side ``alignas(64) static double g_<l>_storage[...]``
in ``cpu_highway``, ``__device__ double g_<l>_storage[...]`` in
``gpu_cuda_cpp``.  Past ~2 GB of static data the link step fails with
cryptic relocation errors (``relocation truncated to fit:
R_X86_64_PC32 against .bss`` from g++; ``failed to convert GOTPCREL
relocation; relink with --no-relax`` from nvcc) -- a first-time user
with a production-sized grid hit a wall with no actionable message.

Storage is now heap-allocated (``gelb_alloc`` on the CPU,
``cudaMalloc`` + ``__device__`` base pointer on the GPU).  Two layers
of guard:

* **Emission-shape tests** (always run, no toolchain needed): generate
  a >2 GB-storage program and assert the heap-allocation shape is
  present and no per-cell ``static`` array remains.
* **Compile-only smoke tests** (opt-in via ``--run-smoke``, gated on
  the same toolchain detection as ``test_examples_smoke``): actually
  link the >2 GB program with g++ / nvcc.  No execution -- allocating
  the storage needs more RAM/VRAM than CI guarantees; the regression
  being guarded is a *link-time* property.
"""

import pathlib
import re
import subprocess
import tempfile

import pytest

from gelb.tests.integration._toolchain import (
    CPP_HIGHWAY_INCLUDES,
    CPP_HIGHWAY_SUPPORT,
    GPU_CUDA_CPP_INCLUDES,
    requires_cpp_highway_compiler,
)
from gelb.tests.integration.test_examples_smoke import (
    _gpp_compile,
    _nvcc_compile,
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_TGV_2D = (_REPO_ROOT / 'examples' / 'lbm' / '2d'
           / 'taylor_green_vortex_2d_bgk.gelb')

# N=4096, D2Q9, FP64, ping-pong: 2 * 9 * 4098^2 * 8 B ~= 2.4 GB --
# just past the 2 GB small-code-model limit that broke the old
# static emission.
_BIG_N = 4096


def _generate(backend: str, out_src: pathlib.Path) -> str:
    """Lower TGV-2D at N=4096 via the gelbc CLI (in-process); return
    the generated source text."""
    from gelb.gelbc import cli as gelbc_cli

    args = [
        str(_TGV_2D),
        '--backend', backend,
        '-o', str(out_src),
        '--num-timesteps', '1',
        '--write-every', '1',
        '--nc-output', 'big.nc',
        '-D', f'N={_BIG_N}',
    ]
    gelbc_cli.main(args=args, standalone_mode=False)
    assert out_src.is_file(), f'gelbc did not produce {out_src}'
    return out_src.read_text()


# ---------------------------------------------------------------------------
# Emission shape (always run)
# ---------------------------------------------------------------------------

class TestLargeGridEmissionShape:

    def test_cpu_highway_heap_allocates_lattice_storage(self, tmp_path):
        src = _generate('cpu_highway', tmp_path / 'big.cpp')
        assert 'gelb_alloc_lattice(sizeof(g0_1_f_storage_t), 0)' in src
        # No static per-cell lattice array may remain (.bss regression).
        assert not re.search(
            r'(alignas\(64\) )?static (double|float) g_\w+_storage\[', src)

    def test_gpu_cuda_cpp_heap_allocates_lattice_storage(self, tmp_path):
        src = _generate('gpu_cuda_cpp', tmp_path / 'big.cu')
        assert '__device__ g0_1_f_buf_t* g0_1_f_storage;' in src
        assert 'cudaMalloc(&gelb_f_storage_p, 2 * sizeof(g0_1_f_buf_t))' in src
        assert 'cudaMemcpyToSymbol(g0_1_f_storage' in src
        assert not re.search(
            r'__device__ (double|float) g_\w+_storage\[', src)


# ---------------------------------------------------------------------------
# Compile-only link smoke (opt-in)
# ---------------------------------------------------------------------------

@pytest.mark.smoke
class TestLargeGridLinks:
    """Link (do not run) a >2 GB-storage program per C++ backend."""

    @requires_cpp_highway_compiler
    def test_cpu_highway_large_grid_links(self, tmp_path):
        src = tmp_path / 'big.cpp'
        _generate('cpu_highway', src)
        rc = _gpp_compile(src, tmp_path / 'big',
                          includes=CPP_HIGHWAY_INCLUDES,
                          extra_sources=CPP_HIGHWAY_SUPPORT)
        assert rc.returncode == 0, (
            f'g++ link failed at N={_BIG_N} (static-storage '
            f'regression?):\n{rc.stderr.decode()[:800]}')

    @pytest.mark.skipif(
        subprocess.run('command -v nvcc', shell=True,
                       capture_output=True).returncode != 0,
        reason='nvcc not on PATH')
    def test_gpu_cuda_cpp_large_grid_links(self, tmp_path):
        src = tmp_path / 'big.cu'
        _generate('gpu_cuda_cpp', src)
        rc = _nvcc_compile(src, tmp_path / 'big',
                           includes=GPU_CUDA_CPP_INCLUDES)
        assert rc.returncode == 0, (
            f'nvcc link failed at N={_BIG_N} (static-storage '
            f'regression?):\n{rc.stderr.decode()[:800]}')
