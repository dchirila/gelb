# Reproducing the paper's lbmpy table

The SoftwareX paper compares GeLB's `cpu_highway` backend with
[lbmpy](https://pycodegen.pages.i10git.cs.fau.de/lbmpy/) on two D2Q9 BGK
cases, each on a 512 x 512 grid at tau = 0.689:

- **TGV-2D**: a fully periodic Taylor-Green vortex;
- **LDC-2D**: a lid-driven cavity with bounce-back walls and a moving lid,
  U_LID = 0.1.

Both rows report compute MLUPS (million lattice updates per second) for a
timed run of 5000 time steps, counting the time loop only: code
generation, compilation, initialisation and output are excluded.  Each
script takes three samples and reports the median.  On the lbmpy side the
timed run follows an untimed warm-up of 100 steps, during which pystencils
generates and compiles the kernel; on the GeLB side the generated program
prints its `Compute MLUPS` line, and `benchmark_backends.py` passes
`--write-every 5000` so that the single gauge output falls outside the
timed loop.

**Conditions of the published measurement.** AMD Ryzen 9 7945HX (Zen 4,
16 physical cores, AVX-512), OpenMP at 16 threads with
`OMP_PROC_BIND=close OMP_PLACES=cores`, both tools on the same machine.
GeLB's C++ is built with `gelb-run`'s default flags
(g++ `-O3 -march=native`, OpenMP); pystencils compiles the lbmpy kernels
with its own default configuration (g++ `-O3 -march=native -fopenmp`),
with AVX-512 vectorisation and OpenMP requested explicitly by the scripts.
The lbmpy venv is built on Python 3.12 (the version `install_lbmpy.sh`
provisions through uv; the installer prints the exact release when it
verifies the install).  lbmpy and pystencils are installed unpinned, so
the versions that apply to a measurement are the ones recorded in its
results file, not a fixed pair.

**Commands**, run from the repository root, in this order:

```sh
# 1. lbmpy, pystencils and numpy into a separate venv (~/Soft/lbmpy/venv).
./scripts/install_lbmpy.sh

# 2. and 3. the lbmpy rows, with that venv's interpreter (not uv run);
#    both merge their result into docs/benchmarks/lbmpy_results.json.
OMP_NUM_THREADS=16 OMP_PROC_BIND=close OMP_PLACES=cores \
    ~/Soft/lbmpy/venv/bin/python scripts/benchmark_lbmpy_tgv.py
OMP_NUM_THREADS=16 OMP_PROC_BIND=close OMP_PLACES=cores \
    ~/Soft/lbmpy/venv/bin/python scripts/benchmark_lbmpy_ldc.py

# 4. the GeLB rows (cases tgv_2d and lid_cavity_2d of the harness; it
#    also runs poiseuille_2d, which the table does not use).
OMP_NUM_THREADS=16 OMP_PROC_BIND=close OMP_PLACES=cores \
    uv run python scripts/benchmark_backends.py --backend cpu_highway
```

The GeLB rows run `examples/lbm/2d/taylor_green_vortex_2d_bgk.gelb`
(TGV-2D) and `examples/lbm/2d/lid_driven_cavity_2d_bgk.gelb` (LDC-2D) with
`-D N=512`; `benchmark_backends.py` writes them to
`docs/user/figures/data/16_mlups_backend_comparison.json`.

The numbers in the paper's table are in `docs/benchmarks/lbmpy_results.json`,
which records for each lbmpy row the machine, the date (UTC timestamp), the
lbmpy and pystencils versions, the OpenMP thread count and the three
samples with their median.
