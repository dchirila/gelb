====================
Numerical Semantics
====================

This chapter states what a GeLB program's floating-point results are,
and which of them you can count on.  It is the authoritative statement
of GeLB's numerical semantics: where the compiler disagrees with it,
the compiler is wrong.  The rule it follows is *minimal surprise*: the
semantics are the conventional ones (IEEE 754 binary32 and binary64,
round to nearest with ties to even, evaluated as written, with no
program changing the rounding mode), each guarantee below is one the
compiler is tested for on every backend, and anything not promised
here is **unspecified**, not merely undocumented.

Each section ends with a note naming the tests that establish it
(:doc:`17_validation_and_convergence` describes the test families).
What this chapter leaves unspecified, in one place: results across
backends beyond what the section *What must agree* states (reductions,
real powers and library functions may differ between backends);
results across compilers, compiler versions, CPU and GPU models; a
NaN's sign and payload; the sign of an exactly zero reduction; the
order of a reduction's terms (fixed per backend, but not stated);
integer overflow, an integer zero divisor and an out-of-range
real-to-integer conversion at run time (a real divided by zero follows
IEEE 754); and anything a fast-math build does.

Three terms recur.  A **plain build** is a program compiled with
GeLB's two optional passes off (``--no-slice-simplify
--no-scalar-cse``); constant folding and
lowering still run, so a plain build is the reference for those
passes, not an independent semantics (the independent reference is the
C++ oracle of the test battery).  An **execution configuration** is the
backend, the native compilers and their flags, the target instruction
set and SIMD width, the storage layout, the thread count and the CUDA
launch options (block size, CUDA graphs, ``--cuda-coarsening``,
``--cuda-tiled``); the generated code is not part of it, since a
default and a plain build generate different code on purpose.  The
**IEEE basic operations** are ``+ - * /``, negation, ``sqrt``,
comparisons and conversions between numeric types; IEEE 754 defines
each of them exactly, correctly rounded.

Build modes
===========

Every backend has three build modes, chosen on the ``gelb-run`` command
line.  They differ in what the native compiler and GeLB's own runtime
helpers may do to your program's floating-point arithmetic.

**Default build.**  On the CPU backends (``cpu_highway``,
``cpu_fortran_serial``) the native compiler runs with contraction off
(``-ffp-contract=off``), so it never fuses a multiply and an addition on
its own: every ``+`` and ``*`` you wrote rounds once.  The one fusion
GeLB decides itself is inside its reduction helper (``dot_prod`` with
coefficients other than ±1), which uses a fused multiply-add on targets
that have one, and then on every code path alike: the SIMD body, the
peeled edges and the scalar tail of a ``cpu_highway`` loop round the
same way, so two cells with identical inputs give identical bits
whatever their position.  Every term of a reduction counts, including
those with a zero coefficient, so an infinity or a NaN in any direction
reaches the result.  On the CUDA backend a default build keeps nvcc's fusion,
because it is worth 7–15 % on the GPU; all threads of a kernel run the
same instructions, so identical cells agree, but a CUDA default build is
bitwise reproducible only against another build of the same kernel code
— not across ``--cuda-coarsening`` or ``--cuda-tiled``, and not against
the plain build below.

**Strict build** (``gelb-run --strict-fp``).  No multiply-add is fused
in the generated code or in GeLB's runtime helpers: ``gelb-run`` passes
``-ffp-contract=off`` to the CPU compilers and ``-fmad=false`` to nvcc,
and the generated C++ defines ``GELB_STRICT_FP`` before including the
runtime header, which then accumulates its reductions with a separate
multiply and addition.  No value-changing native flag is accepted
either: ``-F`` with ``--strict-fp`` is an error, and so is a
``GELB_CXXFLAGS``, ``GELB_FFLAGS`` or ``GELB_NVCC_FLAGS`` override that
carries ``-ffast-math``, ``-Ofast``, ``--use_fast_math``, a
flush-to-zero or an approximate-division flag — ``gelb-run`` names the
flag and stops rather than edit your flag string.  What a strict build
does *not* reach is the inside of the math library: ``sin``, ``exp`` and
the rest are each backend's implementation, and whatever they fuse
internally is part of that implementation.  Use a strict build when you
compare runs bit for bit on one backend — across launch configurations
on CUDA, or default against plain.  Strict mode removes GeLB's fusion
and the native compiler's contraction as sources of variation; it does
not by itself guarantee identical results across backends: the
section *What must agree* says which operations do, and reductions,
real powers and library functions may differ.  What a strict build
costs depends on the program
and the backend: on a Ryzen 9 7945HX (``cpu_highway``, five
interleaved rounds of 2000 steps) it was 1.3 % on channel flow with a
circle obstacle and indistinguishable from the default on a 64²
Taylor–Green vortex, whose run-to-run scatter is wider than any
difference; on CUDA it gives up nvcc's fusion, 7.5–30.6 % on the
examples measured (:doc:`16_performance_backends`).

**Fast math** (``gelb-run -F``).  The native compiler's fast-math mode
(``-ffast-math``, nvcc ``--use_fast_math``): re-association, reciprocal
approximations, no signed zeros, flushed subnormals, approximate
transcendentals on CUDA.  Not reproducible and not covered by anything
in this chapter.

Fusion rounds once instead of twice, so it is usually at least as
accurate; what it gives up is reproducibility and some symmetries.  In
``x*x - y*y`` with ``x == y``, fusing one product leaves the other's
rounding error, so the result can be a tiny non-zero — even negative,
so that its ``sqrt`` is NaN.  If a result like that must be exactly
zero, build strictly.

.. note::

   Tested by ``test_real_width_contract.py``: the default build runs
   the native compiler without contraction; the strict build reaches
   the compiler and the generated source; ``-F`` and ``--strict-fp``
   exclude each other; a strict build wins over an ordinary flag
   override and rejects fifteen value-changing spellings; the fusion
   probe (a ``dot_prod`` with coefficients ``1, 1, 1, 1, 1 + 2^-52,
   1, 1, 1, 1`` over ``-1, 0, 0, 0, 1 - 2^-52, 0, 0, 0, 0``, which is
   exactly ``-2^-104`` when its multiply-add is fused once and ``0``
   when it is not) fuses nothing in a strict build and gives identical
   cells in a default build on every target.

Types and promotion
===================

``real`` is binary64 and ``real32`` binary32; ``int`` is a 64-bit
integer, and ``int8``, ``int16`` and ``int32`` are as named.  An integer
literal is ``int`` and a real literal is ``real``, whatever the lattices'
type; a typed constant has its declared type.  ``real16`` (IEEE 754
binary16, half precision) is a **reserved keyword**: a declaration,
lattice type or cast spelled with it is rejected with a diagnostic.

One table gives the type of every arithmetic expression, and it is the
same table on every backend:

- If either operand is real, the result is real, of the widest real
  operand's width; an integer operand converts to that width, so
  ``int + real32`` is ``real32`` and is computed in binary32.
- Otherwise the result is integer, of the widest operand's width.  Narrow
  integers are not first widened: ``int8 + int8`` is ``int8``, while
  ``int8 + 1`` is ``int`` because the literal is.
- ``real32`` with ``real`` is ``real``; so is ``real32 * 1.0``, whose
  literal is ``real``.  To keep an expression in single precision, make
  its literals ``real32`` constants or write ``real32(1.0)``.
- In arithmetic, ``bool`` is 0 or 1: ``bool`` with a numeric type takes
  that type, and ``bool`` with ``bool`` gives ``int``.
- Comparisons give ``bool``.  Two ``bool`` values compare with ``==``
  and ``!=`` only: they have no order, so ``<``, ``>``, ``<=`` and
  ``>=`` on ``bool`` operands are type errors (order them as 0 and 1
  with ``int()`` if that is meant).  Integer division truncates toward
  zero.

Every operation rounds to its type: a ``real32`` product is one binary32
rounding, and no intermediate is kept wider.  A conversion happens where
the table says, and at a store into a narrower variable or lattice.
Each conversion is one rounding, the same on every backend:

- An integer converts to a real width directly, rounded once to that
  width and never through binary64 first: ``real32(2^54 + 2^30 + 1)``
  is ``2^54 + 2^31``, the nearest binary32, where rounding to binary64
  first would give ``2^54``.
- A real converts to an integer by truncation toward zero: ``int(-3.9)``
  is ``-3``.  A NaN, an infinity or a value outside the integer's range
  is a compile-time error where the compiler sees the conversion and
  undefined at run time, as in C and Fortran.
- An integer converts to a narrower integer by keeping its low bits:
  ``int8(300)`` is ``44``, as in C++20, Java and Rust's ``as``.
- A real converts to a narrower real by rounding to nearest, ties to
  even; a value past the narrower range becomes an infinity, at run
  time and in a folded constant alike (see *Constant folding*).

The intrinsics follow the same table.  ``min``, ``max`` and ``mod``
convert both arguments to their common type and return it, so
``min(w, 1)`` with ``w`` a ``real32`` is ``real32``.  ``atan2`` converts
both arguments to the common *real* type (``real`` for two integers) and
returns it.  ``abs`` returns its argument's type, integers included, so
``abs(x - 3) / 2`` is an integer quotient.  ``sqrt``, ``exp``, ``log``,
``sin``, ``cos``, ``tan`` and ``tanh`` return the width of their real
argument, ``sqrt`` of a ``real32`` being a ``real32``; an integer
argument is converted to ``real`` first.  These are the conventions of
Fortran's generic intrinsics, C++'s overloads, NumPy, Julia and CUDA.

At run time these intrinsics are one helper each, the same on every
backend and every code path (Highway's SIMD body and scalar tail, CUDA,
Fortran): ``mod`` is the truncated remainder with the sign of the
dividend, for integers and reals alike, so ``mod(-7, 2)`` is ``-1`` and
``mod(-7.5, 2.0)`` is ``-1.5`` (Fortran's ``MOD``, C's ``%`` and
``fmod``); integer ``min`` and ``max`` are integers; real ``min``
and ``max`` are IEEE 754-2019 minimum and maximum, so a NaN operand
gives NaN and ``-0.0`` is less than ``+0.0``; an integer raised to an
integer is exact integer arithmetic, with ``x^-n`` being ``1 / x^n`` in
integer division as in Fortran, so ``2^(-1)`` is ``0``; an integer
converted to a narrower integer (``int8(x)``) wraps.  An integer zero
divisor, ``0`` to a negative integer power and an integer overflow are
undefined at run time, as in C and Fortran; a real divided by zero, or
``mod`` of a real by zero, follows IEEE 754 (an infinity or a NaN), and
so does a real overflow.  The compiler rejects the zero divisors it can
see, for integers and reals, and the integer overflows it can see; a
real overflow it can see folds to the infinity (see *Constant folding*).

.. note::

   Tested by ``gelb/tests/unit/type_inference/test_type_rules.py`` (a
   test per row of the table, the passes' agreement on programs, the
   ``real16`` spellings) and by ``test_real_width_contract.py``:
   ``sqrt`` of a ``real32``, ``min`` of a ``real32`` and an integer,
   ``abs`` of an integer, ``real16`` rejected end to end, the integer
   intrinsics and casts on the coordinate, IEEE ``min``/``max`` with a
   NaN and a signed zero on every path; and by the battery's width,
   conversion and special-value cases against the C++ oracle.

Special values
==============

IEEE 754 semantics hold in default and strict builds: a zero keeps its
sign, infinities and NaNs propagate, and subnormals are preserved (no
backend flushes them in those builds).  A NaN's sign and payload are
unspecified, as in IEEE 754.  The floating-point exceptions (invalid,
division by zero, overflow) propagate silently into the output, as C,
Fortran and CUDA do by default; the one exception is the compile-time
error for a zero divisor the compiler can see.  Constant folding
follows the same rules: an operation on constants that overflows or is
invalid (``exp(1000.0)``, ``log(0.0)``, ``sqrt(-1.0)``, ``1.0e300 *
1.0e300``, ``real32(1.0e300)``) folds to the infinity or the NaN the
run time would give, and every backend writes that value explicitly
(Fortran's ``ieee_value``, C++'s ``std::numeric_limits``), never as a
spelled-out ``inf`` and never as the invalid call itself, which a
native compiler would reject (see *Constant folding*).

.. note::

   Tested by the battery's special-value cases (an infinite, a NaN
   and a negative-zero input through the operators, ``min``/``max``
   with a NaN and mixed zeros, a reduction with an infinity in a
   zero-coefficient direction), by ``test_real_width_contract.py`` (a
   real zero keeps its sign through the optimizer, a NaN or an
   infinity in a zero-coefficient direction propagates, a real
   narrowed past its range gives an infinity), by
   ``test_const_eval.py`` (the folder writes a non-finite result as its
   IEEE value) and by ``gelb/tests/unit/midware/test_nonfinite_folding.py``
   (the folded special values reach the output on three backends).

What the optimizer promises
===========================

Expressions are evaluated as written: parentheses and left-to-right
associativity decide the grouping, GeLB never re-associates in a
default build, and the native compilers run without re-association.
GeLB's own optimization passes never change a result.  A default build
is bitwise identical to a *plain* build on the CPU backends in default
and strict builds, and on CUDA in a strict build: the same values,
signed zeros, infinities and NaNs included (a NaN's sign and payload
aside).  This is checked on every backend against an independently
compiled C++ reference, at zero tolerance, by the compiler's test
suite.  The passes apply only identities that hold bit for bit
(``1*x``, ``-1*x``, ``x/1``, ``-(-x)``; a real zero only where its
sign cannot change, as in ``x + (-0)``, ``x - (+0)`` and ``(-0) - x``;
every zero identity in integer arithmetic), fold literal-only
``+ - * /`` in the expression's width (never to an infinity or a NaN,
which are left to run time), and share identical *ordered*
sub-expressions that have no side effects.  Three invariants hold in
every build: an array-valued expression stays array-valued and only
scalar statements take part in the scalar sharing; an expression is
shared only while every name it reads has one value, so a run of
shared expressions ends at an assignment to a name it has read; and a
subtree containing a stateful call (``random()``) is never shared,
dropped, duplicated or moved across another such call, inside the
arguments of intrinsics too.  Rewrites that re-associate
floating-point operations, such as the BGK collinearity rewrite of
``x - C*(x - y)`` into ``(1-C)*x + C*y``, which loses Sterbenz
exactness near ``x == y``, are not performed.

.. note::

   Tested by the battery (``gelb/tests/numeric``), which compares both
   pass modes with the oracle bit for bit on every backend, and by
   ``test_real_width_contract.py``: the scalar CSE does not share a
   value across a write, a shared ``real32`` subtree stays ``real32``,
   whole-array assignments stay arrays, and the pipeline test keeps
   the collinearity rewrite off.

Library functions
=================

``sin``, ``cos``, ``tan``, ``tanh``, ``exp``, ``log`` and ``atan2`` are
each backend's own implementation, at the argument's width, and one
implementation serves every code path of a backend, so two cells with
the same argument give the same bits whatever their position:

- ``cpu_fortran_serial`` and ``gpu_cuda_cpp`` call the platform's
  library (glibc's scalar ``libm``, the CUDA math library).  The
  generated Fortran marks a loop that calls a library function
  ``!GCC$ novector``, since gfortran would otherwise vectorize it
  through glibc's vector library, a different implementation (four
  ULP) in the vector body than in the loop's remainder.
- ``cpu_highway`` uses Highway's vector math for binary64 in the SIMD
  body and, through a one-lane vector, in the scalar tail and the edge
  cells of a loop.  Highway's functions are valid on a range (Highway
  1.4.0: ``sin`` and ``cos`` for a magnitude up to 39000, ``exp`` for x up to
  +706, ``log`` on positive finite x); outside it, and for a NaN or an
  infinite argument, the platform's function serves that lane, chosen
  by the argument's value, never by the cell's position.  Highway has
  no ``tan``, so the platform's ``tan`` serves every lane.  A
  ``real32`` argument uses the platform's library.

Accuracy is that of the implementation, and no general bound is
promised.  What each implementation states is a measured maximum, in
its own metric, not a guarantee: the CUDA Math API tables (CUDA 13.2)
give the largest observed distance, in ULPs, from the correctly rounded
result (binary64: ``exp``, ``log`` and ``tanh`` 1; ``sin``, ``cos`` and
``tan`` 2) and say the figures come from extensive but not exhaustive
testing; glibc's manual (2.39) lists known maximum errors from the
correctly rounded result (x86-64 binary64: ``sin``, ``cos``, ``exp`` and
``log`` 1, ``tanh`` 2; ``tan`` has no listed error); Highway's
``math-inl.h`` (1.4.0) gives a maximum ULP delta from the platform's
``std::`` function on sampled inputs (``exp`` 1, ``sin`` and ``cos`` 3,
``log`` and ``tanh`` 4).  ``sqrt`` is correctly rounded everywhere
(IEEE 754).  The test suite measures each function on each backend
against a 60-digit reference in the implementation's own metric and
asserts that implementation's figure; the distance from the unrounded
value is recorded alongside, not asserted.  A function of a constant is
folded with the compiler host's library (next section), so a constant
argument and a variable one can differ in the last bits; the folded
values, in binary64 and in binary32, are measured against the same
reference.

.. note::

   Tested by ``test_real_width_contract.py`` (a uniform argument gives
   identical bits in every cell for the six functions on three
   backends; beyond Highway's range the platform's value serves the
   lane) and by ``test_math_library_accuracy.py`` (each function on
   each backend, and each folded value in binary64 and binary32,
   against a 60-digit reference, within the implementation's documented
   figure in its own metric).

Reproducibility
===============

Within one build of one program, the result does not depend on how
the run is configured, except where this chapter says so:

- **Cell position.** Two cells with identical inputs give identical
  bits whatever their position: in Highway's SIMD body, in a peeled
  edge or in the scalar tail of a loop, on any CUDA thread, in any
  Fortran loop iteration.  Reductions, library functions and the
  intrinsics are all covered (the sections above say how).
- **Threads and storage layouts.** On ``cpu_highway`` the same bits
  are produced with 1, 2 or 4 OpenMP threads and with each of the
  ``soa``, ``aos`` and ``cbt`` storage layouts, in default and strict
  builds alike.
- **CUDA launch configuration.** In a strict build the same bits are
  produced with any block size, with ``--cuda-coarsening 4`` and with
  ``--cuda-tiled``.  In a default build, which keeps nvcc's fusion, the
  promise is narrower: the same bits across block sizes, which run the
  same kernel code; across coarsening and tiling only within each
  variant, since nvcc may fuse differently in a restructured kernel.
  On the GPU the tests were run on, the coarsened and the tiled
  variants gave the same bits as the plain one, for an ordinary D2Q9
  program, for the fusion probe and the library probe described in
  the test note below, and for a program written to provoke a
  difference (a product in the inner-axis coordinate added to a cell
  value, which a coarsening loop may hoist); the default build did
  fuse the probe's reduction (every cell gave the fused value, alike
  in every variant).  That is an observation, not a promise.
- **Default and plain builds** of one program draw the same random
  numbers and, on the CPU backends and in CUDA strict builds, give
  the same bits; the optimizer section says why.
- **Seeds.** The same seed, program, options and configuration
  reproduce a random program; a different thread count, layout, SIMD
  width or backend draws a different stream.

Nothing is promised across backends beyond what *What must agree*
states, nor across compilers, compiler versions, or CPU and GPU
models.

.. note::

   Tested by ``test_reproducibility.py`` (the configuration matrix on
   ``cpu_highway`` and ``gpu_cuda_cpp``, for an ordinary D2Q9 program
   and for two sensitive programs on a two-dimensional grid with
   identical inputs in every cell: the *fusion probe*, a ``dot_prod``
   with coefficients ``1, 1, 1, 1, 1 + 2^-52, 1, 1, 1, 1`` over ``-1,
   0, 0, 0, 1 - 2^-52, 0, 0, 0, 0``, whose result is ``-2^-104`` when
   fused once and ``0`` when not, and the *library probe*, ``sin``,
   ``cos``, ``tan``, ``tanh``, ``exp`` and ``log`` at one argument each
   — computed in the gauge and, in a second pair, in the dynamic block
   so that CUDA's coarsened and tiled kernels run the sensitive
   arithmetic, which the generated kernel is checked to contain; every
   cell agreeing; and the coordinate-product probe) and by the same
   two programs in ``test_real_width_contract.py`` (identical bits by
   cell position on three backends).

What must agree
===============

The table below says which results must be bitwise identical.
Comparisons apply to the same typed operand values and defined inputs;
a difference introduced upstream by a library function or a real power
may propagate, and integer overflow and invalid real-to-integer
conversions are undefined, not compared.

.. list-table::
   :header-rows: 1
   :widths: 26 26 24 24

   * - Operation
     - Default vs plain build, same execution configuration
     - Across backends, strict builds
     - Across backends, default builds
   * - IEEE basic operations
     - bitwise (CUDA: strict builds)
     - bitwise
     - may differ (fusion)
   * - folded constants
     - bitwise
     - bitwise
     - bitwise (same compiler host and toolchain)
   * - ``min``, ``max``, ``mod``
     - bitwise
     - bitwise
     - bitwise
   * - integer powers
     - bitwise
     - bitwise
     - bitwise
   * - real powers ``x^n``
     - bitwise
     - may differ
     - may differ
   * - reductions
     - bitwise (CUDA: strict builds)
     - may differ (order)
     - may differ
   * - library functions
     - bitwise
     - may differ
     - may differ
   * - ``random()``
     - bitwise, same seed
     - not compared
     - not compared

A real raised to a power is backend-defined: ``x^n`` with a
compile-time integer exponent from 0 to 8 is multiplied left to right
on Highway and CUDA, a variable exponent is not unrolled, and Fortran
uses ``**``; no bound on the difference between backends is promised,
and within a backend default and plain builds agree because GeLB never
rewrites a power.  Within one backend and build, identical inputs give
identical results whatever the cell's position, for arithmetic,
reductions and library functions; for non-random programs the same
holds across the execution configurations of one backend, except that
CUDA default builds agree only where the kernel code is the same (see
*Reproducibility*).

Random numbers
==============

``random()`` returns a ``real`` in [0, 1); each call draws the next
number of the stream.  In a slice or array expression it draws once
per element, in element index order, as NumPy's ``rng.random(9)`` or a
C loop would; to use one draw for a whole slice, draw into a scalar
first (``real r = random(); f.out[x | :] = W * r;``).  Several calls in
one expression draw left to right, and a call in an array expression
draws all its elements before the next call: ``random() - random()``
over nine elements draws nine numbers and then nine more.  The compiler
sequences the draws of a statement itself, so this holds on every
backend, whatever C++ or Fortran leave unspecified, and in a default
and a plain build alike.

The same seed (``gelb-run --seed``), the same program, the same GeLB
options and the same execution configuration reproduce the same
numbers.  Nothing is promised across execution configurations: a
different thread count, storage layout, SIMD width or backend draws a
different stream (each backend has its own generator: xoshiro256+ on
``cpu_highway``, one vector of lanes per draw; cuRAND's XORWOW per
thread on ``gpu_cuda_cpp``; Fortran's ``random_number`` on
``cpu_fortran_serial``).

.. note::

   Tested by ``test_real_width_contract.py``: a slice draws once per
   element in every build; several draws in one expression equal
   their hand-sequenced form bit for bit, inside an intrinsic argument
   too; draws inside and around user-function calls (an argument, a
   function body, nested calls) keep their source order; an array
   constructor's elements are scalar draws, and a broadcast ``sqrt``
   or ``min`` of a draw draws once per element; a draw whose
   contribution simplifies away still happens; a seed reproduces;
   default and plain builds draw alike.

Constant folding
================

An expression whose operands are all constants (literals, constants, and
intrinsics of such) is evaluated once at compile time, by one evaluator
shared by the folder, the geometry's ``where`` predicates and the
optimizer.  A folded value is the value the same expression has in the
same width at run time, with these rules:

- Arithmetic, conversions, ``abs``, ``min``, ``max``, ``mod``, ``sqrt``
  and integer powers are exact or correctly rounded in the expression's
  width: ``mod(-7, 2)`` is ``-1`` (the truncated remainder, as at run
  time), ``2^(-1)`` is ``0`` (an integer power with a negative exponent
  is ``1 / x^n`` in integer division, as in Fortran), ``int(-3.9)`` is
  ``-3``, ``min(0.0, -0.0)`` is ``-0.0``.
- An integer result that does not fit its width (``9223372036854775807 +
  1``, ``2^63``, ``abs`` of the minimum integer) is a compile-time
  error, and so is a real converted to an integer when it is NaN,
  infinite or out of range (``int(1.0e300)``, ``int8(300.0)``).  A
  conversion between integer widths wraps (``int8(300)`` is ``44``).
  Division or ``mod`` by a zero the compiler can see, for integers and
  reals, and ``0`` raised to a negative integer power, are errors too.
  At run time the integer operations are undefined, as they are in C
  and Fortran, and the real ones follow IEEE 754.
- The library functions (``exp``, ``log``, ``sin``, ``cos``, ``tan``,
  ``tanh``, ``atan2``, and a real raised to a power) fold with the
  compiler host's binary64 library, on arguments already rounded to
  their width, and the result is rounded once to the expression's
  width: ``sin(W)`` with ``W`` a ``real32`` is the binary64 sine of
  ``W``'s value rounded to binary32.  For one host and toolchain every
  backend shares the folded value.  The same function of a *variable*
  is the backend's own implementation (see *Library functions*), so a
  constant argument and a variable one can differ in the last bits; no
  bound on that difference is promised.  A call outside the function's
  domain or range (``sqrt(-1.0)``, ``log(0.0)``, ``exp(1000.0)``, a
  real base raised to a power that overflows) folds to its IEEE 754
  result, a NaN, ``-Inf`` or ``+Inf``, the value the run time gives;
  the backends write it as an explicit special value, so no native
  compiler sees ``sqrt(-1.0)`` as a constant argument.
- A reduction of constants (``sum``, ``dot_prod``) and ``matmul`` of
  constants are evaluated term by term in the expression's width, by
  the rules above: an integer sum is exact and its overflow an error; a
  ``real32`` dot product rounds each product and each sum to binary32;
  a real result that overflows is the infinity.
  ``inverse`` and ``determinant`` of constants are evaluated by SymPy at
  binary64 precision and rounded once to the declared width.
- A real narrowed past its range (``real32(1.0e300)``, or a ``real32``
  declared from a binary64 value that large) folds to the ``real32``
  infinity, the value the conversion gives at run time.  A real
  converted to an integer is still an error when it is NaN, infinite or
  out of range, a folded infinity included (``int(1.0e300 * 1.0e300)``).
- A block-local ``const`` is, after folding, a typed local declaration
  holding its value, a special value included; its immutability is
  checked before, by the frontend.
- A constant array's elements are the values its declared width
  stores, on every backend and in every reading: ``const array[int8,
  2] A = {300, 1}`` holds 44 and 1, a ``real32`` array holds the
  binary32 roundings of its literals.  An element a narrow real width
  cannot hold, written as a literal (``1.0e300`` in a ``real32`` array),
  as a conversion (``real32(1.0e300)``) or as an expression that
  overflows (``1.0e300 * 1.0e300``), is an infinity, and a reduction or
  ``matmul`` over such an array folds with it (``sum`` of it is the
  infinity).  ``inverse`` and ``determinant`` of a matrix with such an
  element are errors: they are evaluated exactly and have no run-time
  form.

.. note::

   Tested by ``gelb/tests/unit/midware/test_const_eval.py`` (a rule
   per test on the evaluator; the folder, the geometry evaluator and
   the simplifier agree; the diagnostics) and by
   ``test_real_width_contract.py``: folded ``mod``, powers and
   ``real32`` library calls on three backends, reductions of constants
   in their width (an exact integer sum, a ``real32`` dot product, an
   overflowing sum giving the infinity), a real narrowed past its range
   giving the infinity, constant arrays holding their declared width
   (``int8``, ``int16`` and ``real32`` elements, an overflowing
   ``real32`` element written as a literal, a conversion or a product,
   in a 1-D and a 2-D array, read, summed and multiplied), five constants
   this chapter makes errors rejected by ``gelbc``; by
   ``gelb/tests/unit/midware/test_nonfinite_folding.py`` (programs
   with ``sqrt(-1.0)``, ``log(0.0)``, ``exp(1000.0)``, an
   overflowing product and a narrowed ``real32``, as literals, global
   constants, constant arrays and block-local constants, folded to
   their special values and read back from the output on three
   backends); and by the battery's constant forms.

Not in this version
===================

Some controls are planned and deliberately absent, so that nothing here
is promised before it is implemented and tested on every backend:

- ``real16``: a declaration, lattice type or cast spelled with it is
  rejected with a diagnostic that says so.
- A user function called in a ``global_constants`` initializer; the
  call is rejected with a diagnostic that says so.  A global constant
  is an expression of literals, constants and intrinsics.
- An array-valued gauge output (``-> (array[real, 2] u)``), rejected
  with a diagnostic that says so; a gauge writes one scalar field per
  declared output.
- Opt-in relaxations, each meaning exactly what its name says, as gcc's
  do: ``--reciprocal-math`` (``a/r; b/r`` as ``t = 1/r; a*t; b*t``),
  ``--no-signed-zeros`` (``x + 0`` as ``x``), ``--finite-math-only``
  (no infinity or NaN assumed; with ``--no-signed-zeros``, ``0*x`` as
  ``0``; zero-coefficient reduction terms skipped),
  ``--associative-math`` (regrouping, the collinearity rewrite,
  combining literals) and ``--flush-subnormals`` (FTZ/DAZ on the CPU
  backends, nvcc ``--ftz=true``, which flushes ``real32`` only); a
  ``--fast-math`` that sets all of them, passing the matching native
  flags but not nvcc's ``--use_fast_math``, which also selects
  approximate division, ``sqrt`` and math functions.  A strict build
  with any relaxation will be rejected with an error naming both
  flags, and the optimizer's three invariants above hold under every
  relaxation.
- ``--wide-intermediates``, evaluating ``real32`` subexpressions in
  binary64 and rounding at the store; ``--fpe-trap``, trapping the
  first floating-point exception where the platform supports it (not
  on CUDA); ``--check-overflow``, trapping integer overflow at run time
  as gcc's ``-ftrapv`` does; ``--no-fold-transcendentals``, evaluating
  a library function of constants at run time instead of on the
  compiler host.
- A reduction across cells, which must use a fixed-shape tree, not
  atomics, so that the guarantees above extend to it.
