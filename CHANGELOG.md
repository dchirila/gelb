# Changelog

All notable changes to GeLB are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Python 3.11 or newer is required** (was 3.10). Python 3.10 reaches
  its end of life in October 2026, and the fixed releases of Pillow, which
  matplotlib uses, no longer support it.
- Dependency updates for published security advisories: Pillow 13.0.0,
  certifi 2026.10.23 and setuptools 84.2.1 in `uv.lock`; the VS Code
  extension's test tooling pins serialize-javascript 7.1.3 or newer.
  GeLB itself never opens untrusted image files.

### Fixed

- **The cell-block-tiled storage layout off AVX-512.** A `cpu_highway`
  program in this layout that was built for a target with fewer than
  eight double lanes (AVX2, NEON, or a generic x86 build) ran and gave
  wrong results, and `--storage-layout auto` could choose the layout
  there: its AVX-512 probe looked for `__AVX512F__` alone and ignored
  `GELB_CXXFLAGS`. Now `auto` asks Highway's own target detection,
  using `GELB_CXX` (default `g++`) and `GELB_CXXFLAGS` (default
  `-march=native`); `gelbc` rejects `--storage-layout cbt` when
  that finds no AVX-512 target (`GELB_HAS_AVX512=1` overrides it, for
  cross-compiling); and a program in this layout no longer compiles for
  a narrower target.
- **Tutorial chapter 3 and README.** The chapter listed `**` as the power
  operator (it is `^`), called the math intrinsics element-wise (they take
  scalars), destructured into typed targets (a syntax error) and left
  `determinant` out of its intrinsics table. The README's Quick Start wrote
  C++ into a file named `output.f90`, recommended a cleanup script that
  deletes tracked parser files, and described functions and literals
  wrongly.
- **Help texts.** `gelbc --help` no longer claims that `-o` defaults to
  `.f90` for every backend; `gelb-run --help` lists `GELB_NVCC`,
  `GELB_NVCC_ARCH`, `GELB_NVCC_FLAGS` and `GELBC_EXTRA`.
- `gelbc --visualize-ast --ast-stage midware` drew nothing; it now draws
  the tree after the midware passes.

## [1.0.0] — 2026-10-23

The release that accompanies the SoftwareX paper. Since 0.9.0 the
language, the numerics and the backends were settled, and a user
tutorial was written and reviewed chapter by chapter against the
compiler as shipped.

### Language

- **Multi-lattice programs.** A program declares as many lattices as it
  needs; the thermal examples couple a D2Q9 fluid with a D2Q5
  temperature lattice.
- **Functions and gauges with named outputs**, `function F(real z) ->
  (real y)` and `gauge G -> (real rho, real ux)`, with destructuring
  assignment from multi-output functions.
- **Predicate paints**, `nodes[where condition] = CLASS;`, and reserved
  words with "not in this version" diagnostics.
- **`bounce_back_dfs(f, x, y, {EX, EY})`**: a bounce-back wall in one
  line. Entry i is the population of the neighbour in direction i that
  points back at the cell, so the wall sends every arriving population
  back along its link (full-way bounce-back, the wall midway between the
  nodes). Allowed on the grid edge, where a link pointing outside yields
  the cell's own population.
- **`border()` inspects every neighbour**: the cells one step away along
  an axis or a diagonal (8 in 2D, 26 in 3D), wrapping across periodic
  seams. A wall layer painted by one `border()` rule now covers every
  link a fluid cell can follow.

### Numerics

- **A numerical-semantics contract** (user manual, *Numerical
  semantics*): what the three backends promise, the same answer to the
  last bit where the contract says so, documented as unspecified
  elsewhere. Constant folding is defined, including transcendentals of
  constants; division by zero and undefined reads are compile errors.
- **No population is ever read undefined**: a cross-node-class coverage
  check proves at compile time that every distribution function a block
  reads was written at that cell in that phase.
- Periodic reads more than one cell away wrap their index; ghost cells
  are refreshed before gauges that read neighbours; the wall check runs
  on the resolved class map on every compilation path.

### Backends

- `cpu_fortran_serial`: single-threaded by design, the source-level
  reference and the bitwise reference for the other two.
- `cpu_highway` (default): Google Highway portable SIMD, OpenMP across
  cores, cell-block tiling.
- `gpu_cuda_cpp`: CUDA C++ with device-side node-class maps and CUDA
  graph replay.
- Retired: `cpu_cpp_vcl`, OpenMP in the Fortran backend, CUDA Fortran.

### Validation shipped with the examples

- Lid-driven cavity against Ghia, Ghia & Shin (1982) at N = 129,
  U = 0.05: relative L2 of the centreline profiles 0.5 % (u) and 2.4 %
  (v) at Re = 100, 1.5 % and 2.2 % at Re = 1000, for BGK, MRT and the
  incompressible model alike.
- The cavity examples and the Poiseuille MRT example report the
  prescribed density and velocity on their wall and lid cells; the fluid
  gauge sums populations only where the fluid is.
- The D3Q19 MRT examples (Taylor–Green, Poiseuille, Rayleigh–Bénard in
  3-D) use the orthogonal moment matrix: three ghost-moment rows had
  sign errors that made the transform non-orthogonal and the runs
  unstable. The Sukop Zou–He Poiseuille example collides its Zou–He
  cells and bounces back the corner links; its profile matches the
  parabola to 8e-4.
- Poiseuille (MRT, Strang-split forcing) at second order; Couette BGK
  exact to round-off; Taylor–Green decay at second order; the critical
  Rayleigh number of Rayleigh–Bénard convection within 0.02 % of linear
  stability theory.

### Tutorial and tooling

- **The GeLB User Tutorial**, 18 chapters from installation to a
  reduced-gravity ocean model, every example run on the three backends,
  with a boundary-condition cookbook, a validation chapter and a
  numerical-semantics chapter.
- **The commands are `gelbc`, `gelb-run` and `gelb-view`** wherever GeLB
  is installed: `gelb-run` is an installed command of the package, and
  the bootstrap puts the checkout's commands on PATH with one line in
  the shell's startup file (`scripts/gelb-shell-setup`: zsh, bash,
  tcsh/csh, fish), so the tutorial's commands work as written.
- `gelb-run`: `-D NAME=VALUE`, `--strict-fp`, `-k` to keep the build,
  `--view` to open the result.
- **A developer manual** (`docs/dev/`): the repository map, the
  compilation pipeline pass by pass, the AST and its visitors, the
  three backends, checklists for adding an intrinsic, a validation pass
  or a backend, the test suites, and the design decisions a contributor
  must not undo.
- `docs/benchmarks/lbmpy_reproduction.md` and
  `docs/benchmarks/lbmpy_results.json`: how the paper's lbmpy table is
  measured and the numbers measured on 2026-10-23, with the scripts that
  reproduce them.
- Release 1.0 is installed from a source checkout (git clone and the
  bootstrap); packaged installers for macOS and Ubuntu follow in 1.0.1.
- VS Code extension 0.6.3: Run as a task the extension owns, with a
  "GeLB Run" output channel; diagnostics as you type; geometry preview;
  highlighting and snippets for every intrinsic.

### Known limitations

- The forced periodic Kármán example in the tutorial is a demonstration
  of obstacle geometry; its vortex street appears only with the wider,
  harder-driven settings the chapter gives.
- Couette with MRT collision converges at about order 1.5, the Zou–He
  variant at order 1; the cause is open.
- The TRT Poiseuille example counts its body force twice and sits 9.6 %
  above the parabola.
- Some legal programs still fail in the native compiler rather than in
  `gelbc` (Boolean comparisons on the Fortran backend, an apostrophe in
  a description string, a local name reused with another type in a
  second block).

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
