====================
GeLB in 10 Minutes
====================

This chapter is a language reference card.  It is deliberately
short: no physics, no examples, no prose — just the structural
skeleton of a GeLB program, the reserved symbols, and the built-in
intrinsics.  Read it once straight through, then come back to it
whenever you need to look something up.

.. note::

   Every GeLB feature in this chapter is used in at least one
   worked example in Part B, so you don't need to memorise any of
   it — just know where to find it.

The anatomy of a GeLB program
=============================

A GeLB source file is a sequence of top-level blocks, each
introduced by a keyword.  There are eight block kinds; every
program uses all of them except ``global_constants`` (optional).
They must appear in roughly this order because some blocks
reference declarations from earlier ones:

.. code-block:: gelb

    simulation_description("One-line description of the simulation");

    global_constants {               // optional
        const int N = 64;
        const real tau = 0.6;
        const array[real, 9] W = {4.0/9.0, 1.0/9.0, ... };
    }

    lattices {
        lattice f(2, 9, real, {N, N}, {true, true});
    }

    function ComputeRho(array[real, 9] dfs) -> (real rho) {
        rho = sum(dfs);
    }

    initializer Init { f.out[x, y | :] = W; }

    dynamic Collide {
        array[real, 9] fIn = upstream_dfs(f, x, y, {EX, EY});
        real rho = ComputeRho(fIn);
        f.out[x, y | :] = (1.0 - 1.0/tau) * fIn + (1.0/tau) * W * rho;
    }

    gauge Density -> (real rho) {
        rho = sum(f.in[x, y | :]);
    }

    node_classes {
        node_class BULK(Init, Collide, Density);
    }

    geometry {
        nodes[:, :] = BULK;
    }

The eight block kinds, from top to bottom:

============================ ====================================================
Block                        Purpose
============================ ====================================================
``simulation_description``   One-line string shown in tool output; required.
``global_constants``         Compile-time constants available throughout the program (optional); each can be overridden with the ``-D`` flag of ``gelb-run``.
``lattices``                 Declare one or more ``lattice(d, q, dtype, size, periodicity)``.
``function``                 User-defined pure, side-effect-free functions (optional).
``initializer``              Write initial values into ``f.out``.
``dynamic``                  Update ``f.out`` from ``f.in`` each timestep.
``gauge``                    Read values from ``f.in`` for output.
``node_classes``             Bind (initializer, dynamic, gauge) triples into named classes.
``geometry``                 Assign node classes to spatial regions of the grid.
============================ ====================================================

The first line of every program is a ``simulation_description(...)``
call — not a block, just a one-line metadata string.  It shows up in
tool output and NetCDF attributes.

Lattices
========

A lattice declaration has five positional arguments:

.. code-block:: gelb

    lattice <name>(
        <dimensionality>,     // 1, 2, or 3
        <Q>,                  // number of distribution functions (e.g. 3, 5, 9, 19)
        <dtype>,              // int / real / int32 / real32 / real64 / bool
        <grid_size>,          // scalar for 1D, {Nx, Ny} for 2D, {Nx, Ny, Nz} for 3D
        <periodicity>         // bool for 1D, {px, py} for 2D, ...
    );

All dimensions, Q values, dtype choices, grid sizes, and periodicity
flags must be compile-time constants (or arithmetic on compile-time
constants).  Common velocity sets:

================= ==== ==== =====================================
Name              d    Q    Typical use
================= ==== ==== =====================================
D1Q2              1    2    Advection
D1Q3              1    3    Diffusion, advection-diffusion
D2Q5              2    5    Diffusion, advection-diffusion
D2Q9              2    9    Incompressible Navier-Stokes
D3Q7              3    7    3D diffusion
D3Q19             3    19   Incompressible 3D Navier-Stokes
D3Q27             3    27   3D flows requiring full isotropy
================= ==== ==== =====================================

GeLB itself does not encode these names; you pass the number of DFs
as the ``q`` parameter and supply your own velocity and weight
arrays as global constants (``EX``, ``EY``, ``EZ``, ``W``).

Multi-lattice programs declare several lattices in the same block:

.. code-block:: gelb

    lattices {
        lattice f(2, 9, real, {N, N}, {false, false});   // fluid
        lattice g(2, 5, real, {N, N}, {false, false});   // temperature
    }

See :doc:`09_rayleigh_benard` for a working multi-lattice example.

Reserved implicit symbols
==========================

Seven identifiers are reserved inside simulation blocks.  You
**cannot** use them for your own variables:

================== =====================================================
Symbol             Meaning
================== =====================================================
``x``              Current cell x-coordinate (integer, 0..Nx-1).
``y``              Current cell y-coordinate (2D/3D only).
``z``              Current cell z-coordinate (3D only).
``Nx``             Grid size in x (compile-time constant int).
``Ny``             Grid size in y (2D/3D).
``Nz``             Grid size in z (3D).
``t``              Time-step counter: ``0`` in the initial-condition
                   snapshot, ``1..num_timesteps`` in the time loop.
================== =====================================================

These names are *only* reserved inside ``initializer`` / ``dynamic`` /
``gauge`` blocks.  You are free to use ``x``, ``y``, ``z``, ``t``
etc. as parameter names inside user-defined ``function`` blocks —
functions see their caller's arguments, not the implicit coordinate
symbols.  Inside the ``geometry`` block, ``x``, ``y`` and ``z`` are
also available, but only within the condition of a ``where`` paint
(see :ref:`the geometry paragraph <geometry-paints>` below); ``t`` is not, because
the geometry is fixed for the whole run.

Reserved words
==============

The block keywords (``simulation_description``, ``global_constants``,
``lattices``, ``lattice``, ``initializer``, ``dynamic``, ``gauge``,
``function``, ``node_classes``, ``node_class``, ``masked``,
``geometry``, ``nodes``, ``where``, ``border``), the type names, the
intrinsic function names and ``in`` / ``out`` / ``const`` cannot be
used as identifiers.  Eight further words are reserved and cannot be
used as identifiers: ``enter``, ``leave``, ``reduce``, ``reduction``,
``update``, ``global_variables``, ``transition`` and ``zone``.

The ``f.in`` / ``f.out`` contract
==================================

Inside every ``dynamic`` block, GeLB guarantees two distinct logical
snapshots of every lattice:

- ``f.in[...]`` reads from the **previous** timestep's state
  (the "old" data, frozen for the whole step).
- ``f.out[...]`` writes into the **next** timestep's state
  (the "new" data, not yet visible to anyone).

A read from ``f.in`` cannot observe a write from ``f.out`` made
earlier in the same timestep, anywhere on the grid, by any worker,
in any order.  This is a language-level contract, not an
implementation detail.  It makes pull-streaming dynamics safe by
construction, lets the compiler parallelise freely across cells,
and allows future backends to drop the second buffer without
breaking user code.

The ``|`` separator in ``f.out[x, y | 3]`` is phase-space notation:
spatial coordinates on the left, DF index on the right.

.. code-block:: gelb

    f.out[x, y | :]        // all DFs at site (x, y)
    f.in[x, y | 0]         // DF index 0 at site (x, y)
    f.out[x, y | 1:4]      // DF slice, indices 1 to 4 (both bounds included)
    f.in[x - 1, y | 3]     // DF 3 at the western neighbour
    f.in[x + 1, y + 1 | :] // all DFs at the north-east neighbour

Each spatial index is relative to the current cell: its own
coordinate plus or minus a constant integer (``x``, ``x + 2``, or
an expression that simplifies to that form), with the coordinates
in the order ``x, y, z``.
The compiler rejects any other index (``2 * x``, ``N - 1 - x``,
``y`` in the ``x`` position) with a message pointing at it: a
stencil is a fixed displacement from the executing cell, and those
expressions would make the displacement depend on the cell.
Rectangle paints in the ``geometry`` block take constant bounds
instead; coordinate-dependent painting is written as
``nodes[where condition]``.

A write may also go to a neighbour: ``f.out[x + 1, y | 1] = ...``
executed for cell ``(x, y)`` sets DF 1 of the cell to its east
("push" streaming).  On a periodic axis the destination wraps around;
on a wall axis it must stay inside the grid, or the compiler rejects
the block.  A push lands in every cell the offset reaches, so it
applies to same-class neighbours too, and three rules follow:

- **one writer per cell and DF.**  In one time step (and, separately,
  in the initialization) at most one source cell may write a given DF
  of a given cell.  Several statements of one block that hit the same
  cell are fine, the later wins; two *different* source cells writing
  the same cell would race across threads, so the compiler rejects the
  program and names both writers and a cell.  In particular a block
  that pushes DF ``d`` must not also write DF ``d`` at its own cell.
- **no pushes into static or empty masked cells.**  If a cell
  belongs to a static node class (explained below) its values are
  those its initializer set, and an empty masked class holds zero DFs
  by guarantee.
- **coverage is checked per cell.**  Every DF a block reads must be
  written at that cell, in the right phase (see below), by the cell's
  own blocks or by a push landing there.  In essence, this rules out
  ever reading uninitialised data.

The DF selection of a write must be known at compile time: a literal
or constant index, a constant slice such as ``0:2``, or ``:``.

Prefer local writes where you have the choice.  Reading from the
neighbours and writing the cell's own values ("pull" streaming) is
what the backends vectorize and lay out best: local stores are aligned
and can stream past the cache, and a pull program does not depend on
what its neighbours are.  Pushes are supported, but they force the
plain storage layout and unaligned stores.

Every DF a block reads must have a defined value, both at ``t = 0``
(written by the node class's initializer) and after every buffer
swap (written every step, by the cell's own dynamic or by a push
from a neighbour; a static node class keeps its initializer's
values).  A DF the initializer writes but the
dynamic does not is undefined after the first step, and the compiler
says so.  Storage of a ``masked`` node class starts at zero: a DF its
initializer does not write is zero at ``t = 0`` whatever its dynamic
writes later, and a DF nothing ever writes stays zero.

In ``initializer`` blocks, only ``f.out[...]`` is writable — there
is no previous timestep yet.  In ``gauge`` blocks, only ``f.in[...]``
is readable — gauges observe, they don't modify.  Each gauge output is
one scalar per cell, one field in the output file; an array-valued
output (``-> (array[real, 2] u)``) is not supported, so declare
one scalar per component (``-> (real ux, real uy)``).

Built-in intrinsics
===================

Math intrinsics (element-wise on arrays where applicable):

.. code-block:: gelb

    sin, cos, tan, tanh         // trig
    sqrt, exp, log              // elementary
    abs, min, max, mod, atan2   // utility

Reductions and linear algebra:

================== =====================================================
``sum(v)``         Reduce an array to a scalar via addition.
``dot_prod(a, b)`` Dot product of two arrays.  Maps to Fortran
                   ``dot_product``.
``matmul(A, B)``   Matrix product.  Constant matrices are preferred
                   by the backend.
``transpose(A)``   Matrix transpose.
``inverse(A)``     Compile-time-only — the argument must be a
                   compile-time constant.  Used for precomputed MRT
                   collision matrices.
================== =====================================================

Random numbers:

================== =====================================================
``random()``       Returns a ``real`` in ``[0, 1)``.  Use ``--seed N``
                   at compile time (``gelbc --seed 42``) for
                   reproducible runs.  See :doc:`11_shan_chen_multiphase`
                   for an example of random initial conditions.
================== =====================================================

Streaming intrinsics — not required, but they make the usual LBM
dynamic block much more compact:

``upstream_dfs(f, x, y, {EX, EY})``
   Pull-streaming read.  Returns an array of ``Q`` values, one per
   DF, where the ``i``\ -th entry is
   ``f.in[x - EX[i], y - EY[i] | i]``.  Wraps around periodic
   dimensions.  On a non-periodic dimension a read outside the grid
   is rejected at compile time, so a node class painted on the grid
   edge cannot use it.  This is what makes LBM streaming a one-liner.

``bounce_back_dfs(f, x, y, {EX, EY})``
   Bounce-back wall.  Returns an array of ``Q`` values where the
   ``i``\ -th entry is ``f.in[x + EX[i], y + EY[i] | opp[i]]``: the
   population of the neighbour in direction ``i`` that points back at
   this cell, where ``opp[i]`` is the DF with the opposite velocity,
   determined at compile time from the velocity set.  The fluid
   neighbour pulls it on the next step, so every population that
   reaches the wall goes back along its link (full-way bounce-back,
   the wall midway between the nodes).  Allowed on the grid edge: a
   link pointing outside a non-periodic grid gives the cell's own
   ``f.in[x, y | opp[i]]``, which nothing streams.

In 1D the velocity-set argument is a single 1D array: ``upstream_dfs(f, x, EX)``.
In 3D it is ``upstream_dfs(f, x, y, z, {EX, EY, EZ})``.
``bounce_back_dfs`` takes the same arguments.

User-defined functions
======================

GeLB functions are pure, side-effect-free, and cannot read or write
lattices (they take their inputs as arguments): the result depends on
the arguments alone, as in functional programming (Hughes, *Why
Functional Programming Matters*, The Computer Journal 32, 1989, is a
short, accessible introduction).  They come in two flavours depending
on output count:

.. code-block:: gelb

    // Single-output: called as an expression
    function ComputeRho(array[real, 9] dfs) -> (real rho) {
        rho = sum(dfs);
    }

    // Later: inline in an expression
    real rho = ComputeRho(fIn);

    // Multi-output: called via destructuring assignment
    function ComputeMacros(array[real, 9] dfs)
            -> (real rho, array[real, 2] u) {
        rho = sum(dfs);
        u = {dot_prod(dfs, EX) / rho, dot_prod(dfs, EY) / rho};
    }

    // Later: destructuring inside a dynamic block
    {real rho, array[real, 2] u} = ComputeMacros(fIn);

Functions can call other functions, but **not recursively** (the
compiler detects direct and indirect recursion and rejects it).  A
function is called from ``initializer``, ``dynamic``, ``gauge`` and
``function`` blocks; a call in ``global_constants`` is not in this
version, and the compiler says so at the call.

Node classes and geometry
==========================

A ``node_class`` binds up to three blocks into a named class:

.. code-block:: gelb

    node_classes {
        node_class BULK(Init, Collide, Density);        // full triple
        node_class WALL(InitWall, Density);             // static — no dynamic
        node_class GHOST() masked;                      // masked — no gauge
    }

The three positional arguments are ``(initializer, dynamic, gauge)``
in that order.  You can omit the dynamic (a "static" node class: for
a cell which belongs to it, the values are those its initializer set —
useful for Dirichlet walls) or use the ``masked`` keyword to hide a node
class from the gauge output (its cells are NaN-filled and it may not
carry a gauge; an initializer and a dynamic still run if present).
An empty masked class, ``node_class SOLID() masked;``, holds defined
zero DFs — useful for solid obstacles you don't want in your plots.
When node classes carry different gauges, the output file holds every
field any of them writes; at a cell whose class does not write a field,
a real field holds NaN and an integer field holds 0, as at masked cells.

.. _geometry-paints:

Geometry paints node classes onto spatial regions via array-slice
notation:

.. code-block:: gelb

    geometry {
        nodes[:, :] = BULK;               // default fill
        nodes[:, 0]       = BOT_WALL;     // horizontal bottom row
        nodes[:, N - 1]   = TOP_WALL;     // horizontal top row
        nodes[0, :]       = LEFT_WALL;    // vertical left column
        nodes[N - 1, :]   = RIGHT_WALL;   // vertical right column
        nodes[0, 0]       = SW_CORNER;    // single point

        // Predicate painting: every cell where the condition holds
        nodes[where InCircle(x, y, N/2, N/2, N/4)] = SOLID;

        // Auto-infer boundary layer around a solid region
        border(SOLID) = SOLID_WALL;
    }

Paint statements come in two forms.  ``nodes[ranges] = CLASS;`` paints
a rectangle (or a single cell) given by constant, inclusive bounds:
``nodes[1:3, :]`` paints columns 1, 2 and 3.
``nodes[where condition] = CLASS;`` is a *predicate paint*: the
condition is a ``bool`` expression in which ``x``, ``y`` and ``z``
(as many as the lattice has dimensions) stand for the cell being
considered; it may use constants, the scalar math intrinsics and pure
single-output functions (not recursive ones), and it is evaluated once
per cell at compile time, with the numeric widths the program declares:
``real32(...)`` rounds and ``int32(...)`` wraps there as they do at run
time.  The coordinates are available only inside a ``where``
condition; a rectangle paint takes constant bounds.

Ordinary and predicate paints apply in their source order, and a later
paint overrides an earlier one whatever its kind (CSS-like semantics).
Every cell must be painted by at least one statement or the compiler
rejects the program with "Geometry does not cover node ``(x, y)``".

``border(SOURCE) = TARGET;`` repaints the outermost layer of a
region: every cell of ``SOURCE`` with a neighbour of another class
becomes ``TARGET``.  The neighbours are all the cells one step away
along an axis or a diagonal, 8 in 2D and 26 in 3D, so the layer also
covers the cells reached only along a diagonal link; a periodic axis
wraps around its seam, and a non-periodic edge has no neighbour beyond
it.  The compiler applies the border rules after all paints, wherever
they are written, one after the other in their source order: a rule
reads one snapshot of the map and applies its replacements at once,
and the next rule sees its result.  This is how you get a bounce-back
wall around an arbitrary obstacle without painting it by hand.  See
:doc:`10_karman_vortex` for a working example.

The geometry is fixed for the whole run: it is resolved once, at
compile time, and a paint may not depend on the time step ``t`` or on
a lattice value.

Types
=====

GeLB has a fixed set of scalar types:

================= ============================================
Type              Description
================= ============================================
``int``           64-bit signed integer (alias for ``int64``).
``int8``          8-bit signed integer.
``int16``         16-bit signed integer.
``int32``         32-bit signed integer.
``int64``         64-bit signed integer.
``real``          Double precision (alias for ``real64``).
``real16``        Reserved keyword (16-bit half precision); rejected with a diagnostic.
``real32``        Single precision.
``real64``        Double precision.
``bool``          Boolean (Fortran ``logical``, 1 byte).
================= ============================================

``real`` is double precision in every backend, whatever the lattices'
type.  In a program whose lattices are ``real32``, a literal such as
``3.0`` is still ``real``, so ``3.0 * f`` is computed in double
precision and rounded when it is stored in a ``real32`` lattice or
variable.  To keep an expression in single precision, write
``real32(3.0)`` or use a ``real32`` constant (``const real32 THREE =
3.0;`` in ``global_constants``).  The full promotion table,
including what the intrinsics return, is in :doc:`19_numerical_semantics`.

Array types couple element type and shape into a single type:

.. code-block:: gelb

    array[real, 9]           // 9-element 1D array of real
    array[real, {3, 3}]      // 3x3 matrix
    array[int, 4]            // 4-element int vector

Each type name doubles as an explicit cast intrinsic:
``int(3.7)`` yields ``3``, ``real(n)`` promotes an int to real,
``int8(255)`` truncates to an 8-bit representation.

Expressions and control flow
=============================

GeLB expressions support the usual arithmetic (``+ - * / **``),
comparison (``< <= == != >= >``), and logical (``&& || !``)
operators, with C-style precedence.  Array arithmetic is
element-wise by default; ``matmul`` and ``dot_prod`` are the
explicit tensor operations.

**What GeLB does not have:**

- ``if`` / ``else`` statements.  Use node classes and geometry
  painting to branch on spatial position.  For a choice that depends
  on data, write arithmetic that encodes it: ``max(0.0, rho - rho_min)``
  clamps a value, ``min(1.0, real(t) / T_RAMP)`` ramps a forcing up
  and then holds it, and multiplying a term by ``real(v < 4.0)``
  switches it on (``1.0``) or off (``0.0``) depending on the
  comparison (write the comparison inline, as here).
- ``while`` / ``for`` loops.  Array operations and the implicit
  per-cell loop around every ``initializer`` / ``dynamic`` / ``gauge``
  block cover most situations where these would be needed (the Hughes
  paper cited above shows the general pattern).
- ``print`` / ``write``.  All output goes through ``gauge`` blocks
  and lands in NetCDF.

These are deliberate restrictions: they guarantee that every GeLB
program is easily parallelisable across cells, since there are no
data-dependent control-flow branches inside the per-cell kernel.

Command-line constants
=======================

Any ``const`` in ``global_constants`` can be overridden at compile
time with ``-D NAME=VALUE``:

.. code-block:: bash

    gelbc program.gelb -b cpu_fortran_serial -D N=128 -D tau=0.75 -o program.f90
    gelb-run -D N=256 -n 1000 program.gelb

This is how you do parameter sweeps without editing the source.

Two-minute "what just happened"
================================

Every GeLB program boils down to three things:

1. A **lattice** — where data lives.  Declared once in ``lattices``,
   with a fixed shape, dimensionality, and DF count.

2. A **per-cell kernel** — how data changes.  Expressed as one
   ``dynamic`` block per node class.  The compiler wraps it in an
   implicit loop over every cell in that node class and guarantees
   the ``f.in`` / ``f.out`` ping-pong contract.

3. A **geometry** — which cells run which kernel.  Node classes
   bind ``(initializer, dynamic, gauge)`` triples, and
   ``geometry { ... }`` paints them onto the grid with CSS-like
   override semantics.

Everything else — functions, intrinsics, global constants, multi-
lattice coupling — is syntactic sugar around those three ideas.

When you are stuck, re-read this page.  When you are really stuck,
read :doc:`04_hello_world` — it walks through every construct in
this chapter in the context of a concrete 30-line program.
