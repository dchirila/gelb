"""Tests for ``gelbc --poison-uninit`` and the masked-cell DF
zero-init language guarantee.

The flag is a debugging aid: lattice allocations are filled with NaN
instead of zeros, so any read of a lattice cell that no initializer or
update ever wrote surfaces as NaN in the gauge output instead of
hiding behind a benign zero.

The language guarantee (LANGUAGE_DESIGN.md "Masked cells hold zero
distribution functions") makes the one *legitimate* read of
never-initialized cells well-defined: every backend emits explicit
zeroing of masked-NC cells' DFs before the initializers run, so a
program's output must be IDENTICAL with and without --poison-uninit.
The emission-shape tests below run everywhere; the bitwise
poison-vs-default corpus check compiles and runs real binaries and is
gated behind ``--run-smoke``.
"""

import pathlib
import subprocess

import pytest

from gelb.gelbc import cli as gelbc_cli
from gelb.tests.integration._toolchain import (
    requires_compiler,
    requires_cpp_highway_compiler,
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_TGV_2D = (_REPO_ROOT / 'examples' / 'lbm' / '2d'
           / 'taylor_green_vortex_2d_bgk.gelb')
_CHANNEL = (_REPO_ROOT / 'examples' / 'lbm' / '2d'
            / 'channel_flow_circle_obstacle_2d_bgk.gelb')


def _generate(backend: str, out_src: pathlib.Path, *extra: str,
              example: pathlib.Path = _TGV_2D,
              num_timesteps: int = 1, define: str = 'N=16') -> str:
    args = [
        str(example),
        '--backend', backend,
        '-o', str(out_src),
        '--num-timesteps', str(num_timesteps),
        '--write-every', str(num_timesteps),
        '--nc-output', 'out.nc',
        *(['-D', define] if define else []),
        *extra,
    ]
    gelbc_cli.main(args=args, standalone_mode=False)
    return out_src.read_text()


class TestPoisonUninitEmission:

    def test_cpu_highway_default_zero_fills(self, tmp_path):
        src = _generate('cpu_highway', tmp_path / 'a.cpp')
        assert 'gelb_alloc_lattice(sizeof(g0_1_f_storage_t), 0)' in src

    def test_cpu_highway_poison_fills_0xff(self, tmp_path):
        src = _generate('cpu_highway', tmp_path / 'a.cpp', '--poison-uninit')
        assert 'gelb_alloc_lattice(sizeof(g0_1_f_storage_t), 0xFF)' in src

    def test_gpu_cuda_cpp_default_zero_fills(self, tmp_path):
        src = _generate('gpu_cuda_cpp', tmp_path / 'a.cu')
        assert ('cudaMemset(gelb_f_storage_p,'
                ' 0, 2 * sizeof(g0_1_f_buf_t))') in src

    def test_gpu_cuda_cpp_poison_fills_0xff(self, tmp_path):
        src = _generate('gpu_cuda_cpp', tmp_path / 'a.cu', '--poison-uninit')
        assert ('cudaMemset(gelb_f_storage_p,'
                ' 0xFF, 2 * sizeof(g0_1_f_buf_t))') in src

    def test_fortran_default_has_no_nan_fill(self, tmp_path):
        src = _generate('cpu_fortran_serial', tmp_path / 'a.f90')
        assert 'g_f = ieee_value' not in src

    def test_fortran_poison_nan_fills_lattice(self, tmp_path):
        src = _generate('cpu_fortran_serial', tmp_path / 'a.f90',
                        '--poison-uninit')
        assert 'use ieee_arithmetic' in src
        assert 'g_f = ieee_value(0.0d0, ieee_quiet_nan)' in src


class TestMaskedZeroInitEmission:
    """The masked-cell DF zero-init language guarantee is emitted by
    every backend for masked-NC programs, and not at all otherwise."""

    def test_cpu_highway_emits_masked_zero_init(self, tmp_path):
        src = _generate('cpu_highway', tmp_path / 'c.cpp',
                        example=_CHANNEL, define=None)
        assert 'Masked-cell DF zero-init' in src
        assert 'g0_1_f_storage[gelb_buf]' in src

    def test_gpu_cuda_cpp_emits_masked_zero_init_kernel(self, tmp_path):
        src = _generate('gpu_cuda_cpp', tmp_path / 'c.cu',
                        example=_CHANNEL, define=None)
        assert '__global__ void gelb_masked_zero_init()' in src
        assert 'gelb_masked_zero_init<<<gelb_grid, gelb_block>>>();' in src

    def test_fortran_emits_masked_zero_init(self, tmp_path):
        src = _generate('cpu_fortran_serial', tmp_path / 'c.f90',
                        example=_CHANNEL, define=None)
        assert 'Masked-cell DF zero-init' in src
        assert 'g_f(:, g_x, g_y, :) = 0.0d0' in src

    def test_unmasked_program_has_no_zero_init(self, tmp_path):
        for backend, ext in (('cpu_highway', 'cpp'),
                             ('gpu_cuda_cpp', 'cu'),
                             ('cpu_fortran_serial', 'f90')):
            src = _generate(backend, tmp_path / f't.{ext}')
            assert 'Masked-cell DF zero-init' not in src
            assert 'gelb_masked_zero_init' not in src


# ---------------------------------------------------------------------------
# Poison-vs-default bitwise corpus (opt-in: compiles and runs binaries)
# ---------------------------------------------------------------------------

def _read_nc_vars(path: pathlib.Path) -> dict:
    import netCDF4
    import numpy as np
    with netCDF4.Dataset(path) as ds:
        return {v: np.asarray(ds.variables[v][:]) for v in ds.variables}


@pytest.mark.smoke
class TestPoisonCorpusBitwise:
    """Compile + run each corpus program with and without
    --poison-uninit; outputs must be bitwise identical (NaN-aware).
    A difference means the program read genuinely undefined lattice
    memory -- exactly the regression class the masked-cell zero
    guarantee exists to prevent."""

    CORPUS = [
        pytest.param(_TGV_2D, 'N=32', id='tgv2d'),
        pytest.param(_CHANNEL, None, id='channel-masked'),
    ]

    def _run_pair(self, backend, example, define, tmp_path,
                  compile_fn, openmp):
        import numpy as np
        from gelb.tests.integration.test_examples_smoke import _run_exe
        outputs = {}
        for mode, extra in (('default', ()),
                            ('poison', ('--poison-uninit',))):
            workdir = tmp_path / mode
            workdir.mkdir()
            ext = {'cpu_fortran_serial': 'f90',
                   'cpu_highway': 'cpp',
                   'gpu_cuda_cpp': 'cu'}[backend]
            src = workdir / f'sim.{ext}'
            _generate(backend, src, *extra, example=example,
                      num_timesteps=20, define=define)
            exe = workdir / 'sim'
            rc = compile_fn(src, exe)
            assert rc.returncode == 0, rc.stderr.decode()[:600]
            rc = _run_exe(exe, cwd=workdir, openmp=openmp)
            assert rc.returncode == 0, rc.stderr.decode()[:600]
            outputs[mode] = _read_nc_vars(workdir / 'out.nc')
        for v, a in outputs['default'].items():
            p = outputs['poison'][v]
            assert a.shape == p.shape and np.array_equal(
                a, p, equal_nan=True), (
                f'{v}: poison output differs from default '
                f'(extra NaNs: {np.isnan(p).sum() - np.isnan(a).sum()})'
                ' — a read of undefined lattice memory')

    @requires_compiler
    @pytest.mark.parametrize('example,define', CORPUS)
    def test_cpu_fortran_serial(self, example, define, tmp_path):
        from gelb.tests.integration.test_examples_smoke import (
            _gfortran_compile)
        self._run_pair('cpu_fortran_serial', example, define, tmp_path,
                       _gfortran_compile, openmp=False)

    @requires_cpp_highway_compiler
    @pytest.mark.parametrize('example,define', CORPUS)
    def test_cpu_highway(self, example, define, tmp_path):
        from gelb.tests.integration._toolchain import (
            CPP_HIGHWAY_INCLUDES, CPP_HIGHWAY_SUPPORT)
        from gelb.tests.integration.test_examples_smoke import (
            _gpp_compile)
        self._run_pair(
            'cpu_highway', example, define, tmp_path,
            lambda s, e: _gpp_compile(s, e,
                                      includes=CPP_HIGHWAY_INCLUDES,
                                      extra_sources=CPP_HIGHWAY_SUPPORT),
            openmp=True)

    @pytest.mark.parametrize('example,define', CORPUS)
    @pytest.mark.skipif(
        subprocess.run('command -v nvcc', shell=True,
                       capture_output=True).returncode != 0,
        reason='nvcc not on PATH')
    def test_gpu_cuda_cpp(self, example, define, tmp_path):
        from gelb.tests.integration._toolchain import (
            GPU_CUDA_CPP_INCLUDES)
        from gelb.tests.integration.test_examples_smoke import (
            _nvcc_compile)
        self._run_pair(
            'gpu_cuda_cpp', example, define, tmp_path,
            lambda s, e: _nvcc_compile(s, e,
                                       includes=GPU_CUDA_CPP_INCLUDES),
            openmp=False)
