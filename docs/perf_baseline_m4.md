# Apple Silicon M4 `cpu_highway` performance reference

This is the public summary of a 2026-05-05 `cpu_highway` reference run on
an Apple M4 MacBook Air-class system. It documents the portability result
for Highway/NEON and the high-level performance picture; host-specific
raw samples and thermal/run-cadence notes are local benchmark evidence.

## Conditions

- Backend: `cpu_highway`
- Compiler: Homebrew GCC 15, `-O3 -march=native -fopenmp`
- Highway target: `NEON_WITHOUT_AES`, `Lanes(double) = 2`
- Threads: `OMP_NUM_THREADS=4` (P-cores only)
- Samples: 3 per anchor, median reported
- Metric: compute MLUPS, excluding initialization and I/O

`scripts/gelb-run` auto-detects Homebrew GCC, sets the macOS SDK
workaround when needed, and chooses P-core-only OpenMP on Apple Silicon.

## Six-Anchor Summary

| Anchor | Size | M4 MLUPS | Zen 4 AVX-512 reference | M4 / x86 |
|---|---:|---:|---:|---:|
| TGV-2D BGK | N=512 | 468 | 4555 | 0.10x |
| LDC-2D BGK | N=512 | 421 | 3573 | 0.12x |
| TGV-2D MRT | N=512 | 446 | 3343 | 0.13x |
| channel_flow_circle | 1024 x 128 | 304 | 1270 | 0.24x |
| TGV-3D BGK | N=128 | 172 | 145 | 1.19x |
| RB-2D BGK | 512 x 128 | 499 | 2224 | 0.22x |

## Interpretation

- The 2D anchors are slower than the AVX-512 reference because NEON has
  two double lanes versus eight on AVX-512, and the current CBT layout is
  AVX-512-oriented. The reference column is also flattered by cache
  residency: at N=512 the ~38 MB D2Q9 working set fits in the Zen 4
  host's 64 MB L3, whereas on this M4 it is served from unified memory
  (the 468 MLUPS TGV-2D figure is ~79 % of the ~85 GB/s bandwidth
  ceiling). Compare the DRAM-resident anchors in
  `perf_baseline_zen4.md` before drawing platform conclusions.
- The 3D BGK anchor is faster on M4 than on the Zen 4 reference because
  both systems spill 3D D3Q19 storage to memory, and M4 unified memory has
  a higher effective bandwidth for that workload.
- P-cores only are the right OpenMP default on this host class; adding
  E-cores hurts static memory-bound schedules.
- MacBook Air systems have no active cooling, so sustained benchmark
  claims should include run length and idle/thermal cadence.

## Correctness

The six anchors were compared against `cpu_fortran_serial` on the same
machine at `rtol=1e-12`, `atol=1e-14`. All output variables passed; the
largest observed relative drift was below `2e-13`, consistent with normal
floating-point reordering differences.

## Reproduction Shape

```bash
./scripts/gelb-run -b cpu_highway -D N=512 -n 1000 -w 100000 \
  examples/lbm/2d/taylor_green_vortex_2d_bgk.gelb
```

Refresh on-device before using exact MLUPS values in release material.
