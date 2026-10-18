===========================
Validation and Convergence
===========================

A simulation that looks right is not necessarily right.  This
chapter describes how to validate GeLB simulations against
analytical solutions, using the convergence-rate methodology
from :doc:`08_poiseuille_body_force` and the validation script
``scripts/validate_analytical.py``.

The validation script
======================

.. code-block:: bash

    uv run python scripts/validate_analytical.py

This script runs several GeLB examples at multiple grid
resolutions, compares the numerical output against exact
analytical solutions, computes L2 error norms, and plots
convergence curves.  Its default run covers three families of
cases (``--cases`` selects a subset):

1. **Poiseuille flow**: parabolic velocity profile in a channel —
   in 2D (MRT, body force) and in 3D with full-way bounce-back walls
   (the wall midway between the nodes), and in 2D with Zou-He walls
   (the wall on the boundary node).  Expected convergence: O(h²).
2. **Taylor-Green vortex decay** (2D BGK and MRT): exponential
   decay of a sinusoidal velocity field.  Expected: O(h²) until
   the time-discretization floor is hit around N=256.
3. **Couette flow** (2D BGK and MRT, with bounce-back or Zou-He
   walls): linear velocity profile between two walls moving in
   opposite directions.

Two further cases, ``ra_critical_2d`` and ``ra_critical_3d``, sweep
the critical Rayleigh number of :doc:`09_rayleigh_benard`; they are
expensive and run only when asked for.

Poiseuille convergence — the reference result
===============================================

The Poiseuille MRT convergence study from :doc:`08_poiseuille_body_force`
is the cleanest validation in GeLB.  The figure in that chapter
shows:

- L2 error decreasing as :math:`h^2` on a log-log plot (slope ≈ 2.0)
- The error is measured against the exact parabolic profile
  :math:`u(y) = G/(2\nu) \, y(H-y)` at a single x-column in
  the fluid interior
- The simulation is run long enough for the flow to reach steady
  state: :math:`t > 5 H^2 / \nu`

This second-order convergence is the hallmark of a correct MRT
implementation with bounce-back walls and Strang-split
Guo body forcing.

Taylor-Green vortex decay
==========================

The Taylor-Green vortex is an exact solution of the
incompressible Navier-Stokes equations:

.. math::

   u_x(x, y, t) &= -u_0 \cos(k_x x) \sin(k_y y) \,
                     e^{-\nu(k_x^2 + k_y^2) t} \\
   u_y(x, y, t) &= +u_0 \sin(k_x x) \cos(k_y y) \,
                     e^{-\nu(k_x^2 + k_y^2) t}

where :math:`k_x = k_y = 2\pi / N` and the domain is doubly
periodic.  The velocity amplitude decays exponentially, and the
LBM should reproduce the decay rate to within its spatial
discretization error.

At coarse grids (N < 64), the L2 error decreases as :math:`h^2`.
At finer grids (N > 256), the error plateaus because the
time-discretization error of the LBM (which is first-order in
:math:`\Delta t`) becomes dominant.  This floor is a known
property of single-relaxation-time LBM and is not a GeLB bug.

Numerical conformance
=====================

Physical validation says the model is right; the tests below say the
compiler is.  They establish every guarantee of
:doc:`19_numerical_semantics`, on all three backends, and run with the
rest of the test suite (``uv run pytest``; the CUDA cases need a GPU
and are marked ``gpu``).  Four families:

- **The expression battery** (``gelb/tests/numeric``): a corpus of
  C++ expressions, translated to GeLB, is compiled strictly and run on
  each backend in four surfaces (a scalar, a slice, an array
  declaration, an array assignment) and in both pass modes, and every
  stored value is compared *bit for bit* with an independently
  compiled C++ oracle of the same expression; the same expressions are
  also folded as constants and compared.  It covers the widths and
  conversions, integer and real arithmetic, signed zeros, and the
  special values (an infinity, a NaN, a negative zero, IEEE ``min`` and
  ``max``).
- **Per-decision programs**
  (``gelb/tests/integration/test_real_width_contract.py``): one small
  program per rule of :doc:`19_numerical_semantics`, run on three
  backends and compared with the rule's value — the build modes and
  the rejected flags, the promotion table and the intrinsic widths, the
  exact ``mod``, ``min``/``max`` and integer powers, folding, constant
  arrays in their declared width, the library functions' identical bits
  in every cell, the random-number draw order and count, and one
  regression per optimizer invariant.
- **Reproducibility** (``test_reproducibility.py``): an ordinary D2Q9
  program and two sensitive programs (a reduction whose fused and
  unfused results differ, the six library functions at one argument)
  across thread counts, storage layouts, CUDA block sizes, thread
  coarsening and tiling, compared bit for bit within a build mode, with
  the paths and the sensitive arithmetic verified inside the generated
  kernels.
- **Accuracy** (``test_math_library_accuracy.py``): each library
  function on each backend against a 60-digit reference, asserted
  within that implementation's documented bound; the measured maxima
  are printed with ``-s``.

Known limitations
==================

**Couette flow with MRT.**  The BGK Couette cases reproduce the
linear profile to round-off, but the MRT ones converge more slowly
than second order: at about order 1.5 with bounce-back walls and
order 1 with Zou-He walls, from relative errors of
:math:`5 \times 10^{-7}` and :math:`2.5 \times 10^{-6}` at
:math:`N_y = 16` (``examples/VALIDATION.md``).

Adding your own validation
===========================

To add a new analytical test case to the validation script:

1. Write a function that returns the exact solution at a given
   grid resolution, timestep count, and physical parameters.
2. Write a function that compiles and runs the corresponding
   ``.gelb`` example at those parameters, reads the NetCDF
   output, and returns the numerical solution.
3. Compute the L2 error:
   :math:`\|u - u_\mathrm{exact}\|_2 / \|u_\mathrm{exact}\|_2`.
4. Run at 4–5 grid resolutions (e.g. N = 16, 32, 64, 128, 256)
   and plot the error vs h on a log-log scale.  The slope
   gives the convergence order.

The existing functions in ``validate_analytical.py``
(``run_poiseuille``, ``run_taylor_green``) serve as templates.
