# CUDA C++ tuning conclusions

This note keeps the portable conclusions from a 2026-05-07
`gpu_cuda_cpp` knob sweep on an NVIDIA Ada `sm_89` laptop GPU. The
original run covered 6 anchors x 12 configurations with 3-sample median
MLUPS. Exact row-by-row host tables are local benchmark evidence and
should be re-run before being quoted in release or paper text.

## Knobs

- `--cuda-coarsening N`: each thread handles `N` cells along the
  outer-most spatial axis.
- `--cuda-ldg`: routes stencil reads through the read-only cache path.
- `--cuda-stwt`: emits streaming writes for the streaming step.
- `--cuda-tiled`: cooperative shared-memory tiling for the dynamic
  kernel, scope-guarded to simple periodic 2D cases.

## Stable Conclusions

| Observation | Consequence |
|---|---|
| `--cuda-ldg` is usually a small win, roughly +1 to +3%. | Safe optional tuning flag; not large enough to make a universal default compelling. |
| `--cuda-stwt` is only clearly useful together with coarsening on TGV-2D MRT. | Keep opt-in; avoid defaulting it globally. |
| `--cuda-coarsening 2` helps the compute-heavy TGV-2D MRT anchor by about +18% when paired with `--cuda-stwt`. | A future heuristic may key on collision operator / arithmetic intensity. |
| `--cuda-coarsening 4` loses across the tested anchors. | Do not use as a default; register pressure outweighs reuse. |
| `--cuda-tiled` did not improve the tested Ada cases. | Keep off by default; the current implementation is a starting point for future 3D tiling work, not a shipped default. |
| TGV-3D BGK moved by only about 1% under these knobs. | Real 3D gains need different codegen, such as slab/register tiling, not cache hints alone. |

## Default Recommendation

For the public default path, keep conservative CUDA settings:

```bash
./scripts/gelb-run -b gpu_cuda_cpp example.gelb
```

Users who are tuning a specific workload can test:

```bash
./scripts/gelb-run -b gpu_cuda_cpp --cuda-ldg example.gelb
./scripts/gelb-run -b gpu_cuda_cpp --cuda-coarsening 2 --cuda-stwt example.gelb
```

The second form is only known to be attractive for the MRT-heavy 2D
anchor measured in the original sweep.

## Reproduction Shape

```bash
./scripts/gelb-run -b gpu_cuda_cpp -n 500 -D N=512 -w 500 \
    --cuda-coarsening K --cuda-ldg --cuda-stwt \
    examples/lbm/2d/taylor_green_vortex_2d_bgk.gelb
```

When refreshing this benchmark, record the GeLB commit, dirty state,
toolchain, driver, GPU clock/warmup policy, and raw command output.
