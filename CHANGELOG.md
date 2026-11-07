# Changelog

All notable changes to GeLB are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The
compatibility promise covers the GeLB language and the command-line
interface of `gelbc`, `gelb-run` and `gelb-view`; the supported Python
versions follow upstream end of life and can change in any release.

## [Unreleased]

### Added

- `gelbc --version`.
- Two geometry-lint warnings: a node class with no cells, and a paint
  range that runs backwards (`nodes[40:30, :]`, which paints nothing).

### Changed

- The packaged installers for macOS and Ubuntu that the 1.0.0 notes
  announced for 1.0.1 move to a later release; the source checkout plus
  the bootstrap script remains the supported install.
- **Python 3.11 or newer is required** (was 3.10). Python 3.10 reaches
  its end of life in October 2026, and the fixed releases of Pillow, which
  matplotlib uses, no longer support it.
- Dependency updates for published security advisories: Pillow 13.0.0,
  certifi 2026.10.23 and setuptools 84.2.1 in `uv.lock`; the VS Code
  extension's test tooling pins serialize-javascript 7.1.3 or newer.
  GeLB itself never opens untrusted image files.
- **Gauges that share an output name must give it one type.** Outputs of
  the same name in several gauges are one field of the output file. Its
  type came from the gauge of the node class painted first, and the other
  gauges' values were converted to it in the file without a warning: with
  `-> (int v)` in that gauge, another gauge's `-> (real v)` with
  `v = x + 0.5` was stored as `x`. On `cpu_highway` with the SoA and CBT
  layouts (the default), a real gauge filling an integer, `real32` or
  `bool` field failed to build instead. `gelbc` now reports an error when
  two gauges declare an output of the same name with different types,
  whether or not a node class uses them. `int` and `int64` count as one
  type, and so do `real` and `real64`.

### Fixed

- **A local array keeps its own length in every block on `cpu_highway`
  and `gpu_cuda_cpp`.** The C++ and CUDA backends looked a local array's
  length up by name across every block of the program and took the
  first declaration, so when two blocks declared arrays of the same
  name with different lengths, the later block's `dot_prod` and
  whole-array assignment (`v = v * 2.0`) used the earlier block's
  length (`dot_prod(v, w)` over four elements gave the two-element
  result), `matmul` rejected the program ("M cols (4) != v len (2)"),
  and an array `tmp` in one dynamic made a scalar `tmp` of another
  dynamic fail to build. The lookup is now per block, as in Fortran.
- **Integer constant arrays and integer `dot_prod` are exact on
  `cpu_highway` and `gpu_cuda_cpp`.** The C++ and CUDA backends folded
  every constant array to binary64, so an `int` element above 2^53
  (`{2, 9007199254740993}`) lost its low bit when the array passed
  through a function, and so did `int` coefficients of a `dot_prod`
  with an integer result. A `dot_prod` of `int` coefficients with an
  `int8` or `int32` array was computed in the array's narrow type, so
  it wrapped at 127 or 2^31 (Fortran gave 20000 + x and 2^31), and one
  of five or more terms went through a fused multiply-add in double in
  a default build, so `{1, 1, 1, 1, 3}` against `{0, 0, 0, 0,
  3002399751580331}` gave 2^53 instead of 2^53 + 1. Every constant
  array now keeps its elements exactly, and an integer `dot_prod` is
  computed in its result's type, each element converted to it first,
  with no fused multiply-add, as the Fortran backend did and chapter 19
  says. A `dot_prod` whose coefficients are all -1 (`S * {1.0, 1.0,
  1.0}` with `-D S=-1`) with a per-cell real array also failed to build
  on `cpu_highway` with the SoA and CBT layouts; it builds, and negates
  as the other paths do. No example's generated code changes.
- **`gelb-run -n` and `-w` are validated.** `-w 0`, `-w 08` or a
  negative `-n` made bash print an arithmetic error and exit 0 without
  running anything, leaving the previous `.nc` in place. Both options
  now take a whole number (`-n` from 0 to 2 147 483 646, `-w` from 1 to
  2 147 483 647, the programs' step counters being 32-bit), a leading
  zero means decimal, and anything else is an error before any step
  runs; `gelbc` applies the same ranges. A later release will lift the
  cap on `-n`.
- **A failed run looks failed.** When the program exits with a nonzero
  status, `gelb-run` now exits with that status and says so (and with
  `-n` above 1 its output is still shown; before, the message was lost
  behind the progress bar and the run ended with status 0). The
  previous run's `.nc` is removed only after a successful build, so a
  failed translation or build keeps it, and a read-only `.nc` stops the
  run before anything is generated. A `GELBC_EXTRA` option that writes
  no source (`--stencils`) is an error instead of a run of a stale
  program. The progress bar says "ended" rather than "done" when the
  program stops, and no longer reports every record written when it
  could not count them.
- **Contraction stays off under a flag override.** `GELB_CXXFLAGS` or
  `GELB_FFLAGS` without `-ffp-contract=off` (an `-O2` build, say, or the
  default string plus `-g`) let the native compiler fuse multiplies and
  additions, against the default build's contract: `sqrt(a*a - b*b)`
  with `a == b` gave NaN in most cells. `gelb-run` now puts
  `-ffp-contract=off` in front of the flags, default or override; an
  explicit `-ffp-contract=fast` of your own still wins.
- **Small `gelb-run` guards.** `-s ""` (a script's unset seed variable)
  ran clock-seeded as if `-s` had been omitted; a seed that is given must
  now be an integer. Arguments after `--` were ignored, generated
  programs taking none; they are now an error, and the usage line no
  longer offers them. Python modules start with `python -P`, so a file
  in the working directory (a `gelb/` directory, a stray `click.py`)
  cannot shadow an installed package.
  `--help` says that `GELBC_EXTRA` is for gelbc-only options.
- **A diagnostic on a `-D` value no longer crashes `gelbc`.** An error
  caused by an overridden constant (a division by it with `-D N=0`, a
  grid size of 0) ended in `AttributeError: 'NoneType' object has no
  attribute 'start_line'` in text mode, because the override carried no
  source position. It now stands where the declared value stood: the
  message points at the declaration line, in the terminal and in
  `--diagnostics-json`, and a diagnostic on a node without a position
  prints without a source excerpt instead of a traceback.
- **DF slices with a nonzero lower bound.** `array[real, 4] v =
  f.in[x, y | 2:5]` gave different numbers per backend: Fortran read
  DFs 2..5, Highway and CUDA read DFs 1..4, both silently, because the
  frontend typed the slice as a scalar and the C++ emitters indexed it
  from 0. A slice `| lo:hi` is now `array[T, hi-lo+1]` on both sides of
  an assignment, element `i` being DF `lo+i`, with the declared length
  checked; an open end with a lower bound (`| 2:`), which was typed as
  the full set, is a slice of the remaining DFs; `sum` and arithmetic
  take a slice directly, `dot_prod` takes it through a local array, as
  for `| :` on the default backend. A single DF read inside a slice
  expression (`f.in[x, y | 2:5] + f.in[x, y | 0]`) was read at the loop
  index on Highway and CUDA; bounds that are constants (`| LO:HI`) are
  folded; a DF index outside the lattice or a reversed range is a
  located error, on both sides, and so is a range with run-time bounds.
  A single DF index computed at run time (`| mod(x, 9)`) is rejected
  with a located message on the C++ backends, which cannot vectorise it
  (inside a slice it used to be read at the loop index, silently;
  outside, it stopped with an internal error); the Fortran backend runs
  it. Verified bit-for-bit across Fortran,
  Highway (SoA and CBT) and CUDA on a probe that reads and writes such
  slices; the emission of every example is unchanged, as none uses one.
- **`gelbc` never overwrites the program.** `-o` and `--nc-output` reject
  a name ending in `.gelb` and a path that is the input file, before any
  code is generated (an alias that only resolves at run time is not
  detected). Before, `gelbc prog.gelb -o prog.gelb` replaced the program
  with its translation.
- **pip installations.** The installed `gelb-run` command needed `uv` on
  the PATH or `GELB_PYTHON` set by hand to find `gelbc`; it now uses its
  own interpreter. Selecting the default `cpu_highway` backend in such an
  installation, which has no Highway sources, now stops with one line
  saying so and naming `-b cpu_fortran_serial`, instead of advice about
  a git submodule.
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
- **The gelb-view window, 3D data.** Every step of the time slider or the
  slice controls added another colour bar, so the plot shrank step by
  step. A 3D slice now keeps one colour bar and, as a 2D heatmap does, one
  colour range: the variable's minimum and maximum over all records. The
  viewer now reads such ranges one record at a time, also for the
  *Sources* tree, so opening a large 3D output needs much less memory.
- **gelb-view's figures.** The headless viewer (`gelb-view data.nc -o
  fig.png`) titled the figure with the file's full path; now with its
  name. Every colour bar, headless or in the window, is now as tall as
  the image it belongs to; it used to span the whole axes box, which an
  equal-aspect image of a non-square grid leaves largely empty.
- **gelb-view's vorticity plot forgot the chosen colormap.** It redrew
  with its own diverging colormap on every animation frame or time step,
  whatever the *cmap* box said. The box now starts at that colormap
  (`RdBu_r`) and the plot keeps the user's choice.
- **The gelb-view *Sources* menu, 3D data.** It offered "New
  Cross-Section" and, for a multi-variable selection, the composite plots
  (Vector Field, Streamlines, Magnitude, Particle Animation,
  Side-by-Side) for 3D variables too, and choosing one opened no plot
  (the traceback went to the terminal). A 3D variable now gets the plots
  that open, heatmap and animation, which show one slice at a time, and
  the menu says "Use ParaView for 3D visualizations".
- **gelb-view drew large integers in a few colours.** matplotlib draws an
  integer image of small range at single precision, which rounds values
  above 2^24, so an `int64` field such as `3000000000 + x + 100*y` showed
  one or two colours per row of 64 cells instead of about 21. Every
  heatmap, slice and animation frame, headless or in the window, now
  gets the values at double precision, which holds every integer up to
  2^53 exactly.
- **The paper-examples README** (`examples/softwarex-2026-paper/`). Two
  benchmark commands named programs that do not exist in the repo root,
  and the convergence command needed an NVIDIA GPU and ran resolutions it
  had not asked for: `scripts/validate_analytical.py` ignored
  `--resolutions` for most cases, and its default backend was
  `gpu_cuda_cpp`. The script now honours `--resolutions` for every case
  and defaults to `cpu_highway`, as `gelb-run` does, and the README's
  *Figures* section points at the Colab notebooks.
- **A local constant that refers to another constant.** `const int START
  = 2; const int END = START + 3;` inside an initializer, a dynamic or a
  gauge was rejected on every backend with "You are using the implicit
  variable x for initializing a constant", naming `x` or `y` at random,
  as soon as the block used a coordinate anywhere: the check rejected
  every symbol a local constant referred to, not only `x`, `y`, `z` and
  `t`. A local constant may now refer to global and local constants; one
  initialised from an implicit variable is still rejected, with a located
  message that names that variable and suggests a variable instead.
- **A local constant keeps its declared type at compile time.** When a
  local constant was used in a DF index, a DF range or an array index
  or slice, the compiler evaluated it with the type of its initializer
  instead of its declared type: `const real P = 7;` made `(P / 2) * 2`
  an integer division, so `f.in[x, y | int((P / 2) * 2)]` read DF 6
  while the same expression computed at run time gave 7, on every
  backend. Global constants were evaluated correctly.
- **An integer gauge output on a real lattice failed to build on the default
  backend.** `gauge G -> (int tt) { tt = x; }` compiled on Fortran and CUDA but
  not on `cpu_highway` with the SoA and CBT layouts (the default): the vector
  gauge path stored a double vector into the `int64_t` output buffer. A
  gauge whose output is not binary64 now takes the scalar path, as a `bool`
  output already did.
- **`dot_prod` of real coefficients with an integer array gave a wrong
  result on `cpu_highway` and CUDA.** With `W = {0.5, 0.25, 0.125}` a
  constant array and `k = {1, 2, 3}` an `int` array, `dot_prod(W, k)` gave 0
  instead of 1.375 on `gpu_cuda_cpp` and on `cpu_highway` wherever the block
  was not vectorized (the AoS layout, for example): the C++ reduction
  helper computed in the array's integer type and truncated the
  coefficients. With coefficients of ±1, an `int8` array wrapped, and a
  `real32` sum was an exact integer sum instead of rounding to binary32
  after every addition. Fortran was right. Each integer element is now
  converted to the result's width, as the type rules say, whichever
  operand comes first; integer coefficients with a `real32` array convert
  to binary32 directly, not through binary64 (this mattered above 2^53).
  In a block that the SoA or CBT layout vectorizes,
  such a `dot_prod` still fails to build, as before.
- **A node class with no cells overwrote the others on `cpu_highway`.** A
  class whose paints were all overridden, whose `where` matched no cell,
  or that `border()` left empty (the paper's cylinder with `-D R=0`
  empties its wall class) ran its initializer, dynamic and gauge over the
  whole grid on every storage layout, so the run silently held that
  class's values everywhere. Fortran and CUDA were right. Such a class
  now runs nothing on every backend, and the compiler warns about it.
- **`int` gauge outputs were 32-bit in the Fortran backend's NetCDF
  file.** `int` is `int64`, and `cpu_highway` and CUDA store it so, but
  `cpu_fortran_serial` declared `int` and `int64` outputs as 32-bit
  NetCDF integers. A value outside the 32-bit range stopped the run with
  "NetCDF: Numeric conversion not representable", after writing that
  output's field for the record wrapped (`3000000000` as `-1294967296`),
  and `-2147483647` read back as missing. `int` and `int64` outputs are
  now 64-bit NetCDF integers on every backend; values in the 32-bit
  range read back unchanged.
- **A gauge output named `time`.** The output file stores each record's
  time step in a variable named `time`, so such an output compiled and
  then stopped every backend's run when it created the file ("NetCDF:
  String match to name in use"). `gelbc` now reports an error at the
  output's declaration.
- **A negative wall velocity broke the C++ and CUDA builds.** With
  `-D U_LID=-0.1`, any lid-driven cavity example, the paper's included,
  failed to compile on `cpu_highway` and `gpu_cuda_cpp`, and so did the
  bounce-back Couette flows with a negative `U_WALL`: the code negated a
  negative constant as `(--0.1)`, which C++ reads as a decrement. A
  negative constant that a program negates, multiplies by -1 (an `EX`
  entry) or subtracts from zero could do the same, and with
  `--no-slice-simplify --no-scalar-cse` the paper's four Zou-He
  programs failed even with their own values. Fortran was right. The
  negation is now written as one, with the same value.
- **A negative power base lost its sign on `cpu_fortran_serial`.**
  `(-0.5) ^ real(t)` and `(-2) ^ t`, a negative constant raised to a
  power known only at run time, were written as `-0.5d0 ** n`, which
  Fortran reads as `-(0.5d0 ** n)`: `(-0.5)^2` gave -0.25 and `(-2)^2`
  gave -4. The other backends were right, and no example does this. The
  base is now parenthesized, and so is a negative constant after an
  operator (`x * -0.05d0` is a GNU extension, rejected with
  `-std=f2008`); the results of the examples do not change.

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
