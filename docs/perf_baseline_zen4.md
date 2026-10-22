# Zen 4 AVX-512 `cpu_highway` performance reference

This is the public summary of a 2026-05-05 `cpu_highway` reference run on
an AMD Ryzen 9 7945HX-class Zen 4 system with AVX-512. The raw per-run
samples and host-specific execution notes are local benchmark evidence;
this file keeps the reusable conclusions.

## Conditions

- Backend: `cpu_highway`
- Compiler: `g++`, `-O3 -march=native`
- Threads: `OMP_NUM_THREADS=16` (physical cores)
- Samples: 3 per anchor, median reported
- Metric: compute MLUPS, excluding initialization and I/O

## Six-Anchor Summary

| Anchor | Size | `cpu_highway` MLUPS | Interpretation |
|---|---:|---:|---|
| TGV-2D BGK | N=512 | 4555 | L3-resident, compute/cache dominated |
| LDC-2D BGK | N=512 | 3573 | L3-resident, masked-wall overhead visible |
| TGV-2D MRT | N=512 | 3343 | compute-heavy collision, still cache friendly |
| channel_flow_circle | 1024 x 128 | 1270 | irregular mask and multi-region overhead |
| TGV-3D BGK | N=128 | 145 | spills to memory, bandwidth dominated |
| RB-2D BGK | 512 x 128 | 2224 | multi-lattice but still mostly cache friendly |

## Cache residency caveat

The 2D anchors at N=512 are **L3-resident** on this host: two D2Q9
double buffers at 512² are about 38 MB, and the Ryzen 9 7945HX has
64 MB of L3 (two CCDs). Those MLUPS figures therefore measure a
compute/cache regime and do not extrapolate to production grids.
Quote them together with a DRAM-resident anchor, never alone.

## CPU vs GPU on this host (2026-06-09, compute MLUPS)

| Anchor | Size | `cpu_highway` (16 cores) | `gpu_cuda_cpp` (RTX 4080 Laptop) | Ratio |
|---|---:|---:|---:|---:|
| TGV-2D BGK | N=512 | 4662 | 2356 | CPU 2.0x — L3-resident, see above |
| TGV-2D BGK | N=2048 | 327 | 2332 | GPU 7.1x — DRAM-resident |
| TGV-3D BGK | N=128 | 144 | 825 | GPU 5.7x — DRAM-resident |

The GPU runs at about 96 % of its GDDR6 bandwidth ceiling in FP64 on
these anchors; the small-2D CPU win is a cache artifact, not a GPU
weakness. (The N=512 CPU figure differs from the table above because
it comes from a later run; both are medians of three samples.)

## Reusable Conclusions

- For 2D D2Q9/D2Q9-like anchors that fit in cache, `cpu_highway` can be
  much faster than simple DRAM-bandwidth math predicts — and than the
  GPU. Any public CPU-vs-GPU comparison must include a DRAM-resident
  anchor (2D N=2048 or 3D N=128).
- For 3D D3Q19 at production-sized grids, the working set spills beyond
  cache and memory bandwidth becomes the controlling resource.
- Use physical cores for OpenMP on this class of CPU. SMT is not a free
  speedup for memory-bound LBM kernels.
- Record the commit, dirty state, compiler, thread count, and thermal/run
  length when refreshing these numbers.

## Reproduction Shape

```bash
OMP_NUM_THREADS=16 ./scripts/gelb-run -b cpu_highway -n 1000 \
  -D N=512 -w 1000 examples/lbm/2d/taylor_green_vortex_2d_bgk.gelb
```
