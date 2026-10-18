==========
Why GeLB?
==========

The Lattice Boltzmann Method is one of the most widely used mesoscopic
fluid solvers in computational science.  It is also, in practice, one
of the most error-prone to implement from scratch.  A typical research
code is a few thousand lines of C++ or Fortran mixing a physics kernel
with boundary conditions, forcing terms, collision operators,
checkpoint I/O, and parallelisation directives; a single off-by-one
in a streaming step can silently break the mass balance or quietly
break second-order accuracy at walls.  Established frameworks
(OpenLB, Palabos, waLBerla, lbmpy) cut that cost, but they are
*libraries*: you still write C++ or Python, you still assemble
the framework's building blocks yourself, and the gap between "what
the textbook says" and "what compiles" is wide enough to hide bugs.

GeLB takes a different stance.  **GeLB is a language, not a library.**
You describe a lattice, an initialiser, a dynamic, a gauge, and a
geometry in a concise domain-specific syntax; the compiler decides
how to lay out memory, which pull/push scheme to use, how to
parallelise the loops over the cells, and how to handle ping-pong
buffers.  The same source compiles to OpenMP-parallel
portable-SIMD C++ via Google Highway (``cpu_highway``, the
default), to CUDA C++ (``gpu_cuda_cpp``), or to single-threaded
Fortran (``cpu_fortran_serial``, the educational reference) with
no source changes — you pick the backend when you run
``gelb-run -b``.  Compile-time validation catches lattice-shape
mismatches, missing distribution-function initialisation, and
out-of-bounds stencil reads *before* a single line of C++, CUDA or
Fortran is generated.  The result is a research workflow where the
code you write looks like the paper you read.

A concrete number: measured across the 67 examples in the
repository, the Fortran reference backend writes **5.6× more code**
than the GeLB source on a size-weighted SLOC basis — a GeLB program
is **82% shorter** than the generated Fortran, and the ratio stays
in that range whether you look at 1D diffusion (3.2×), 2D LBM
benchmarks (4.6×), or 3D flows (4.4×).  And the code you don't
write runs in parallel: the default ``cpu_highway`` backend uses
all cores and SIMD lanes, and the CUDA backend uses the GPU — same
``.gelb`` source, no code changes, no parallel directives written
by hand, no race conditions to debug.  Numbers are in
:doc:`16_performance_backends`.

How short is short?  Here is the complete 1D heat-diffusion
program from :doc:`05_1d_diffusion`; what the compiler generates
from it is described below.

GeLB source — 65 lines, one file, one kernel:

.. code-block:: gelb

    simulation_description("1D heat diffusion with Dirichlet BCs (D1Q3)");

    global_constants {
        const int GRID = 32;
        const array[real, 3] W  = {4.0/6.0, 1.0/6.0, 1.0/6.0};
        const array[real, 3] EX = {0.0, 1.0, -1.0};
        const real tau   = 0.75;
        const real omega = 1.0 / tau;
        const real T_left  = 1.0;
        const real T_right = 0.0;
    }

    lattices {
        lattice f(1, 3, real, GRID, false);
    }

    function DiffusionEq(real T) -> (array[real, 3] feq) {
        feq = W * T;
    }

    initializer InitBulk  { f.out[x | :] = DiffusionEq(T_left);  }
    initializer InitLeft  { f.out[x | :] = DiffusionEq(T_left);  }
    initializer InitRight { f.out[x | :] = DiffusionEq(T_right); }

    dynamic CollideAndStream {
        array[real, 3] fIn = upstream_dfs(f, x, EX);
        real T = sum(fIn);
        array[real, 3] feq = DiffusionEq(T);
        f.out[x | :] = (1.0 - omega) * fIn + omega * feq;
    }

    gauge Temperature -> (real temperature) {
        temperature = sum(f.in[x | :]);
    }

    node_classes {
        node_class BULK(InitBulk, CollideAndStream, Temperature);
        node_class LEFT_WALL(InitLeft, Temperature);
        node_class RIGHT_WALL(InitRight, Temperature);
    }

    geometry {
        nodes[:]        = BULK;
        nodes[0]        = LEFT_WALL;
        nodes[GRID - 1] = RIGHT_WALL;
    }

What the default backend generates from it is one C++ file,
``heat_diffusion_1d_dirichlet.cpp``, of **285 lines**: the lattice
storage and the constants, one loop per node class for the
initializers, the gauge and its NetCDF output at the initial step,
then the time loop with the collision-and-streaming loop and the
gauge writes, and a timing report at the end.  You usually don't
have to read it, but ``gelb-run -k`` keeps it (and the binary) in
the current directory if you want to, and it is the file to attach
to a bug report.  The ratio of what-you-write to what-actually-runs
is something like one page of GeLB to four pages of generated code —
for a problem where every line of the generated code needs to be
correct for the physics to be correct.

What makes GeLB different
=========================

**A real language, not a library.**
    OpenLB, Palabos, waLBerla, and lbmpy are libraries.  You still
    write C++ or Python, and you assemble the framework's building
    blocks yourself, in the way the framework expects.  GeLB's
    building blocks are the notions of the method itself — lattice,
    initializer, dynamic, gauge, node class, geometry — written in a
    language with its own grammar, type system, and validation
    passes.  The user writes physics; the compiler decides backend
    strategy.  That is a different product, with a different
    workflow.

**Backend portability that actually works.**
    The same ``.gelb`` source compiles to OpenMP-parallel
    portable-SIMD C++ via Google Highway (``cpu_highway``, the
    default), to CUDA C++ (``gpu_cuda_cpp``), or to single-threaded
    Fortran (``cpu_fortran_serial``, the educational reference) with
    no source changes.  The ``f.in`` /
    ``f.out`` ping-pong illusion is documented as a
    *language-level guarantee*, so backends are free to drop the
    second buffer without breaking user code.  See
    :doc:`16_performance_backends`.

**A type system that catches LBM bugs early.**
    Implicit symbol scoping (``x``/``y``/``z`` are reserved in
    simulation blocks, but usable as function parameters),
    lattice-access context validation (``f.out`` is writable in
    ``initializer`` / ``dynamic``; ``f.in`` is readable in
    ``dynamic`` / ``gauge``; anything else is a compile-time error),
    function-recursion detection, ``masked`` keyword enforcement,
    stencil extraction driving boundary-access checks.  These are
    not generic compiler features — they target the mistakes LBM
    users actually make.

**End-to-end tooling.**
    ``gelbc`` (compiler), ``gelb-run`` (compile-and-run wrapper),
    ``gelb-view data``
    (interactive NetCDF viewer with vector fields, streamlines, and
    particle animation), ``gelb-view source`` (geometry heatmap +
    stencil diagrams + geometry-lint checks), a VSCode extension
    (``vscode-gelb``) with live preview, Problems-panel diagnostics,
    and an interactive 3D geometry explorer, NetCDF output,
    validation against analytical solutions
    (``scripts/validate_analytical.py``), MLUPS measurement.

**Algorithmic clarity as a headline feature.**
    The cascaded MRT collision operator in GeLB reads like the paper.
    The ``border()`` + ``nodes[where InCircle(x, y, ...)] =
    SOLID`` pattern reads like the textbook.  The Zou-He velocity BC
    reads like the derivation.  Part of the value proposition is the
    reproducibility of boundary-condition, forcing and collision
    combinations; GeLB tries to offer that to its users.

Errors at the domain level, not the generated-code level
=========================================================

When you make a mistake in a hand-written LBM code, the C++ or
Fortran compiler catches *some* of it — typos, undeclared variables, type
mismatches.  Everything else — wrong DF index, unwritten
distribution function, bounce-back on the wrong direction, a
boundary region whose index range silently clips at the grid edge
— shows up either as a ``NaN`` in the
NetCDF output several hours into the run, or (worse) as a
plausible-looking but physically wrong result.

GeLB rejects most of those mistakes before it emits a single line
of generated code.  The compiler understands the domain — distribution
functions, node classes, stencils, geometry — and its error
messages are phrased in the domain.  A few real examples from
deliberately broken programs:

*Mistake:* writing to ``f.in`` in a dynamic block (``f.in`` is
read-only by language contract):

.. code-block:: text

          ...
       6  }
       7  dynamic Collide {
       8->    f.in[x | 0] = 1.0;
                ^^
    [Problem] Your GeLB program contains a syntax error.
    [Hint] mismatched input 'in' expecting 'out'
       9  }
      10  gauge G -> (real v) { v = sum(f.in[x | :]); }
          ...

This one is caught by the parser itself, hence the generic
message; the hint names ``out`` as the required write target.

*Mistake:* an initializer that only writes some of the
distribution functions:

.. code-block:: text

          ...
       2  lattices { lattice f(1, 3, real, 16, false); }
       3
       4->initializer Init {
                      ^^
    [Problem] Initializer 'Init' (for node class 'BULK') does not write all DFs of lattice 'f': missing DFs [1, 2]
    [Hint] Add write statements for the missing distribution functions, or use the full-range syntax f.out[...|:] to write all DFs at once.
       5      f.out[x | 0] = 0.5;
       6  }
          ...

*Mistake:* a geometry paint range that extends past the grid
(this one bites beginners from Python backgrounds, because
GeLB's paint ranges are inclusive on both ends):

.. code-block:: text

          ...
      11  geometry {
      12      nodes[:, :] = BULK;
      13->    nodes[:, 0:N] = WALL;
                              ^^
    [Problem] Geometry paint to 'WALL' is out of bounds: y-range [0, 16] extends outside [0, 15]
    [Hint] GeLB paint ranges are INCLUSIVE on both ends.
      14  }

*Mistake:* referencing a node class that wasn't declared
(here a copy-paste typo):

.. code-block:: text

          ...
      10  gauge G -> (real v) { v = sum(f.in[x | :]); }
      11  node_classes { node_class BULK(Init, Collide, G); }
      12->geometry { nodes[:] = WALL_TYPO; }
                                ^^
    [Problem] You mention WALL_TYPO. However, you did not define it.
    [Hint] Define WALL_TYPO.

Every error quoted above is what ``gelbc`` prints for the program
in question, with two lines of context on each side.  The pattern
is the same for every compile-time check GeLB performs: the
offending token is underlined, the problem is described in domain
terms, and a hint tells you how to fix it.  The goal is that a wrong program fails quickly and
informatively, so the expensive feedback loop of "compile →
run simulation → stare at NaN → diff against analytical solution
→ guess what went wrong" is replaced by a sub-second round-trip
with a helpful error message.

This is the second main value proposition, alongside compactness.
The compiler is not just a translator — it is a reviewer that
checks your LBM program in the language of LBM.

Restrictive on the surface, expressive underneath
===================================================

GeLB looks like a smaller language than it is.  On first contact
the list of "missing" features is conspicuous:

- **No explicit loops** — no ``for``, no ``while``.  The per-cell
  loop around every ``initializer`` / ``dynamic`` / ``gauge``
  block is implicit; you never write it.
- **No data-dependent branches** — no ``if``, no ``else``, no
  ``switch``.  Branching on spatial position is expressed by
  painting different node classes onto different regions of the
  geometry; branching on a field value is expressed via the
  ``min`` / ``max`` / ``abs`` intrinsics or the multiplicative
  ``real(cond)`` cast, the same on every backend.
- **No mutable state outside lattices** — the only objects that
  persist across time steps are lattices (and the outer loop
  counter ``t``).  Function-local variables exist but are scoped
  to a single cell and die at the end of the block.
- **No side effects in user functions** — they cannot read or
  write lattices, cannot call ``random()``, cannot recurse.
- **No ``print`` / ``write``** — every output goes through a
  gauge block and lands in NetCDF.

Each of these restrictions is there for a single reason:
**so that the compiler can parallelise every kernel across every
cell with no synchronisation, no race conditions, and no
hand-tuned directives.**  The per-cell kernel has no control-
flow branches that depend on other cells' state, which means
the same source compiles unchanged to the multi-threaded SIMD C++
backend, to CUDA, to the single-threaded Fortran reference, and to
any future MPI backend.  You get the parallel speed reported in
:doc:`16_performance_backends` for free, precisely because you
cannot write the kind of code that would break it.

It would be fair to worry that the restrictions are too strict.
In practice they aren't.  LBM is already a data-parallel method
by construction — every cell's collision and streaming step is a
pure function of its own and its neighbours' previous-timestep
state — and every common LBM idiom can be written as a closed-form
expression of that state.  A few concrete examples of "how do I do X without
``if``?":

*Obstacles and solid boundaries.*  Paint a ``SOLID`` node class
onto the obstacle region, and use a different dynamic block
(bounce-back, or no dynamic at all) for that class.  The
``border()`` geometry statement and conditional paints
(``nodes[where InCircle(x, y, cx, cy, r)] = SOLID``) cover anything
from a single point to an arbitrary pixel-mask geometry.  See
:doc:`10_karman_vortex` for flow past a circular obstacle.

*Multiple collision operators in one simulation.*  Use BGK in
the bulk and MRT near walls, or LES in high-shear regions and
plain BGK elsewhere.  Each is its own node class with its own
``dynamic`` block; geometry paints decide which cells run
which.  The LES example in
``examples/lbm/2d/lid_driven_cavity_2d_bgk_smagorinsky.gelb``
recomputes :math:`\tau` per cell per time step from the local
non-equilibrium stress tensor — all in one branch-free dynamic
block.

*Branch on a scalar value.*  You cannot write
``if (rho < 0.0) { abort(); }``.  GeLB does not stop on NaNs or
prove physical constraints such as a positive density; inspect
the simulation's output.  For domain-boundary smoothing, use
``max(0.0, rho - rho_min)`` or an equivalent branch-free
expression.  For a choice between two finite values, convert each
condition with ``real(...)`` and use it as a 0/1 weight:
``real(v < 4.0) * a + real(v >= 4.0) * b`` (both branches are
evaluated).

*Multi-lattice coupling.*  Two lattices (fluid + temperature,
or fluid + species), read each other's ``f.in`` in a dynamic
block, coupled via a source term that uses both.  No
synchronisation primitives, no parallel constructs: the language
presents every block as if it ran sequentially over the cells,
reading the previous time step and writing the next (currently
backed by a pair of ping-pong buffers).  See
:doc:`09_rayleigh_benard` for Boussinesq-coupled thermal
convection.

*Multiphase flow.*  Shan-Chen pseudopotentials, free-energy
models, phase-field: all expressible via a single
non-local force term in the dynamic block that reads ``f.in``
at eight neighbours and computes a local force.  See
:doc:`11_shan_chen_multiphase`.

*Non-LBM kernels.*  GeLB's per-cell model is stencil-kernel-
general, not LBM-specific.  The chapter
:doc:`12_beyond_lbm_gol` implements Conway's Game of Life —
where the "DF" is a single integer, the "equilibrium" is the
neighbour-count rule, and the "streaming" is an 8-neighbour
Moore stencil (the cell's eight surrounding cells, the
neighbourhood of cellular-automata theory) — in 37 lines of GeLB,
using exactly the same
language constructs as every LBM example in the tutorial.

The pattern across all of these is the same: describe the
per-cell kernel as a closed-form expression in the previous
time step's data plus compile-time constants, and let the
compiler materialise the implicit loop (readers who know
functional programming will recognise the style).  When you come
from a C or C++ background the missing control-flow features feel
restrictive at first.  Two or three chapters into this
tutorial, you will hopefully stop noticing — they turn out not to
have been needed.

Who this tutorial is for
========================

**If you know LBM already** — you have read Krüger et al. or Mohamad
or Sukop, and you have implemented a D2Q9 kernel by hand at least
once — this tutorial will get you productive in an afternoon.  Parts
A and B take you through every language feature via worked examples
from the repository; Part C is reference material you can come back
to when you need to look up a boundary condition idiom or a
performance tuning hint.

**If you do not know LBM yet**, this tutorial will teach you GeLB
but it will not teach you the physics.  Read Krüger *et al.*,
*The Lattice Boltzmann Method: Principles and Practice* (Springer,
2017), chapters 1–5, first.  Chapters 1–2 cover the hydrodynamic
and kinetic-theory background, chapter 3 introduces the Lattice
Boltzmann equation proper, chapter 4 does the Chapman-Enskog
analysis, and chapter 5 covers boundary conditions — after which
the :doc:`04_hello_world` chapter of *this* tutorial will feel
natural.  Mohamad's *Lattice Boltzmann Method: Fundamentals and
Engineering Applications with Computer Codes* (2nd ed., Springer
2019) is a gentler, more applied alternative.

Where to next
=============

- :doc:`02_getting_started` — install GeLB, compile and run your first simulation.
- :doc:`03_gelb_in_10_minutes` — the language cheat-sheet; bookmark it.
- :doc:`04_hello_world` — the simplest possible GeLB program, annotated line by line.

.. seealso::

   The LOC numbers above are generated by
   ``scripts/measure_loc_savings.py``, which compiles every
   ``.gelb`` file under ``examples/`` with the ``cpu_fortran_serial``
   backend and counts source and generated lines (raw ``wc -l`` and
   SLOC, size-weighted and per-example).  Run it yourself to see the
   breakdown by example category::

       uv run python scripts/measure_loc_savings.py --backend cpu
