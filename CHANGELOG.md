# Changelog

All notable changes to GeLB are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] — 2026-04-20

The first public release of GeLB.

### Why 0.9 and not 0.1

GeLB has been under development — and in productive use by its author
— since 2007. By the time of its first public tag, the compiler has:

- a full three-stage pipeline (frontend, midware, backend) with
  type inference, range/constant resolution, function inlining,
  stencil extraction, and geometry-lint checks;
- three working backends (serial CPU Fortran, OpenMP CPU Fortran,
  CUDA Fortran for GPU) with feature parity across 1-D, 2-D, and
  3-D grids;
- a 1,600+ test suite, 70 example programs, and a VSCode extension
  with live preview + Problems-panel diagnostics;
- a standalone visualisation tool (`gelb-view`) for both simulation
  output and compile-time geometry/stencil inspection.

Tagging this as `0.1.0` would signal "early alpha — expect it to
break" to a first-time visitor, which does not match the actual state
of the code. Tagging it as `1.0.0` would commit to SemVer API
stability before the companion SoftwareX paper has been accepted and
before multi-lattice support has landed (both of which may still
trigger syntax changes). `0.9.0` is the honest middle: feature-
complete, launch-ready, one minor release away from a stable 1.0.

### Highlights in this release

- **DSL frontend** — ANTLR4 grammar (`GeLB.g4`); full AST with type
  inference, constant folding, range resolution, and semantic
  validation; user-defined side-effect-free functions (single- and
  multi-output).
- **Compilation**:
  - `gelbc` driver with `--openmp`, `--backend {cpu_fortran_serial,cpu_highway,gpu_cuda_cpp}`,
    `-D NAME=VALUE` constant overrides, `--seed` for reproducible
    PRNGs, `--stencils` for a stencil report, and
    `--diagnostics-json` for machine-readable errors (consumed by the
    VSCode extension's Problems panel).
  - Explicit `real32` / `real64` support with precision-aware literal
    emission.
  - Intrinsics: `sin`, `cos`, `tan`, `tanh`, `sqrt`, `exp`, `log`,
    `abs`, `min`, `max`, `mod`, `atan2`, `sum`, `dot_prod`, `random`,
    `matmul`, `transpose`, `inverse`, `determinant`, `upstream_dfs`.
- **Backends**:
  - CPU Fortran 90 (`cpu_fortran_serial`, with optional OpenMP via
    `!$omp parallel do`); NetCDF or stdout output; pre-loop gauge
    pass for initial conditions; boundary-aware clamped index reads
    for wall-adjacent node classes; automatic MLUPS measurement.
  - CPU C++ SIMD (`cpu_highway`, default); Google Highway portable
    SIMD across x86 (SSE/AVX/AVX-512) and ARM (NEON); cell-block-
    tiled storage layout; OpenMP parallelization with thread pinning.
  - GPU CUDA C++ (`gpu_cuda_cpp`, via system `nvcc` + NetCDF-C);
    full feature parity with the CPU backends; `cudaGraph_t`
    capture/replay; auto-default thread block size based on grid
    dimensionality + periodicity; cuRAND device API for `random()`;
    device-side `nc_map`.
- **Geometry**:
  - Paint-by-node-class semantics, `border(NC) = …` wall-layer
    inference, single/line region loop-elision in the emitter,
    periodic boundary wrapping, masked node classes with NaN-filled
    gauge output.
  - Geometry-lint pass (disconnected NC regions, thin walls,
    unreachable fluid pockets, off-centre symmetric geometry).
- **Tooling**:
  - `gelb-run` one-step compile-and-run wrapper with progress bar;
    CPU and GPU modes; `--view` auto-launches the visualiser.
  - `gelb-view data` for simulation output (GUI + headless).
  - `gelb-view source` for geometry + stencils of a `.gelb` file
    (five render modes, JSON export consumed by the VSCode
    extension's interactive preview).
  - VSCode extension v0.3.0: syntax highlighting, live geometry /
    stencil preview, Problems-panel diagnostics, interactive 3-D
    geometry explorer.
- **Packaging**: installable via `pip install gelb` with the ANTLR-
  generated parser shipped in the wheel (no JDK required for
  end-user installs); `CITATION.cff`; MPL-2.0 licence.

### Known limitations

- Single-lattice programs only. Multi-lattice support is the
  headline feature planned for v1.0.
- No mesh refinement; uniform, isotropic, rectangular grids only.
- Finite-difference stencils only (no finite-volume / finite-element
  LBM).
- GPU backend requires the NVIDIA HPC SDK; no AMD/Intel GPU support
  yet.
