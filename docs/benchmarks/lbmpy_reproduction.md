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
measurement takes three samples and reports the median.  On the lbmpy side
the timed run follows an untimed warm-up of 100 steps, during which
pystencils generates and compiles the kernel; on the GeLB side the
generated program prints its `Compute MLUPS` line, and `-w 5000` puts the
single gauge output outside the timed loop.  The table has three grid
sizes, N = 128, 256 and 512.

**Conditions of the published measurement.** AMD Ryzen 9 7945HX (Zen 4,
16 physical cores, AVX-512), OpenMP at 16 threads with
`OMP_PROC_BIND=close OMP_PLACES=cores`, both tools on the same machine.
Both sides are compiled with fast-math: pystencils builds the lbmpy
kernels with its default `-Ofast -DNDEBUG -fPIC -march=native -fopenmp`
(`-Ofast` is `-O3` plus `-ffast-math`), and the GeLB programs are built
with `gelb-run -F`, which adds `-ffast-math` to GeLB's default
`-O3 -march=native`.  GeLB's default build keeps strict IEEE semantics so
that the backends agree bit for bit where the numerical-semantics chapter
requires it; without `-F` the GeLB rows measure 8 to 18 % lower (ratios
TGV 1.13 / 1.54 / 1.54, cavity 0.85 / 0.68 / 0.73 on the same machine and
day).  The lbmpy venv is built on Python 3.12 (the version
`install_lbmpy.sh` provisions through uv; the installer prints the exact
release when it verifies the install).  lbmpy and pystencils are installed
unpinned, so the versions that apply to a measurement are the ones recorded
in its results file.

**Commands**, run from the repository root.  The install script never
deletes anything: it refuses an existing prefix unless `--keep` asks it to
install into it, so choose a fresh directory with `--prefix` (or
`LBMPY_PREFIX`) if `~/Soft/lbmpy` is already in use.

```sh
# 1. lbmpy, pystencils and numpy into a separate venv at <dir>/venv.
scripts/install_lbmpy.sh --prefix <dir>

# 2. the same thread settings for both sides.
export OMP_NUM_THREADS=16 OMP_PROC_BIND=close OMP_PLACES=cores

# 3. the lbmpy rows, with that venv's interpreter (not uv run); each run
#    prints its median and writes one JSON file.
for N in 128 256 512; do
    <dir>/venv/bin/python scripts/benchmark_lbmpy_tgv.py --domain-size $N --out <dir>/tgv_$N.json
    <dir>/venv/bin/python scripts/benchmark_lbmpy_ldc.py --domain-size $N --out <dir>/ldc_$N.json
done

# 4. the GeLB rows: three samples each, take the median of the
#    "Compute MLUPS" lines.  -D NU=0.063 gives the Taylor-Green program
#    tau = 0.689, the lbmpy default; the cavity program already has
#    tau = 0.689 and U_LID = 0.1.
for N in 128 256 512; do
    for s in 1 2 3; do
        gelb-run -b cpu_highway -F -n 5000 -w 5000 -D N=$N -D NU=0.063 \
            examples/lbm/2d/taylor_green_vortex_2d_bgk.gelb | grep 'Compute MLUPS'
        gelb-run -b cpu_highway -F -n 5000 -w 5000 -D N=$N \
            examples/lbm/2d/lid_driven_cavity_2d_bgk.gelb | grep 'Compute MLUPS'
    done
done
```

The ratio in the table is the GeLB median over the lbmpy median at each N.
The numbers behind the paper's table are in
`docs/benchmarks/lbmpy_results.json`: the machine, the date, the lbmpy and
pystencils versions, the thread count, the GeLB build flag, and for each
case the three samples of both tools with their medians.
