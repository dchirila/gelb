# CUDA `sm_89` microbenchmark summary

This note keeps the portable conclusions from a 2026-05-06 CUDA
microbenchmark on an NVIDIA Ada `sm_89` laptop GPU. The raw host logs are
local benchmark evidence; use this file for the reusable performance
intuition.

Source: [bench/cuda_microbench.cu](../bench/cuda_microbench.cu).

## Headline Measurements

| Probe | Result | Interpretation |
|---|---:|---|
| Empty-kernel launch latency | about 1.36 us | Per-timestep launch overhead is usually small, but many per-region kernels can still accumulate. |
| DRAM copy bandwidth | about 381 GB/s | Roughly 88% of the theoretical 432 GB/s device peak. |
| L2-resident read bandwidth | about 1170 GB/s | Around 3x DRAM bandwidth for working sets within L2. |
| Shared-memory bandwidth | about 655 GB/s | Useful, but not automatically faster than L2 reuse on this Ada part. |

## L2 Cliff

The read-only sweep showed a sharp transition between 32 MB and 64 MB of
working set. That matters for LBM:

- small 2D D2Q9 problems can sit near the L2-resident regime;
- large 2D and most 3D problems spill to DRAM;
- CUDA tuning decisions should consider stencil storage size, not only
  grid dimension.

## Implications For GeLB

- Cache hints (`--cuda-ldg`) can help, but are modest on Ada because L2
  already absorbs much of the reuse.
- Shared-memory tiling is not automatically a win. The simple 2D tiling
  implementation was neutral or slower on the measured anchors.
- Multi-node-class geometries can pay launch overhead when they emit many
  small kernels per timestep. Coalescing GPU region work is a better
  target than micro-optimizing launch latency.

## Reproduction Shape

```bash
nvcc -O3 -arch=sm_89 -std=c++17 -o /tmp/microbench \
     bench/cuda_microbench.cu
/tmp/microbench
```

Refresh the numbers on each new GPU generation before using them as a
backend heuristic.
