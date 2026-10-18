==============================
Boundary Conditions Cookbook
==============================

This chapter is a single-page reference for every boundary
condition pattern used in the tutorial.  Each entry gives the
GeLB code snippet, the physical BC it implements, and a pointer
to the chapter where it was first introduced.

Static Dirichlet (fixed value)
===============================

A node class with an initializer but **no dynamic block** holds
its DFs at the initialized values forever.  The gauge still
reports the cell's state, but nothing updates it.

.. code-block:: gelb

    initializer InitWall { f.out[x | :] = DiffusionEq(T_wall); }
    node_class WALL(InitWall, Temperature);   // no dynamic

This is the simplest Dirichlet BC.  The wall cell's temperature
stays at ``T_wall`` for all time because no dynamic block runs
on it.  The neighbouring cells see that temperature imposed
:math:`1 - \tau` cells from the wall cell, not at it;
``examples/lbm/1d/heat_diffusion_1d_antibounceback.gelb`` puts the
wall half a cell beyond the end cell instead, with the anti-bounce-back
rule.

First used in :doc:`05_1d_diffusion` (left and right walls).

Neumann flux (time-dependent)
==============================

To impose a heat flux :math:`q''(t)` at a wall, modify the
unknown incoming DF using the LBM Neumann formula (Krüger et al.
(2017) §8.5.3):

.. code-block:: gelb

    dynamic FluxWall {
        real f0 = f.in[x | 0];
        real f2 = f.in[x + 1 | 2];
        real I_now = FLUX_AMP * sin(PI * real(t) / PERIOD);
        f.out[x | 0] = f0;
        f.out[x | 2] = f2;
        f.out[x | 1] = f2 + I_now;
    }

The per-DF writes set DF 1 (the unknown incoming direction) to
the outgoing DF 2 plus the flux correction.  DFs 0 and 2 are
pulled from this cell and its right neighbour and copied through
unchanged.  The block reads them directly rather than through
``upstream_dfs``, which would also read DF 1 from ``x - 1``,
outside the grid: the compiler rejects that read at a wall.

Not used by a tutorial chapter; the ``t`` symbol is listed in the
cheat-sheet of :doc:`03_gelb_in_10_minutes`.

Moving-wall bounce-back
========================

A bounce-back wall sends every population that reaches it back
along its link; ``bounce_back_dfs`` makes that a one-liner.  For a
wall moving at velocity :math:`u_w`, add a momentum-transfer term to
each reflected DF:

.. code-block:: gelb

    dynamic MovingLid {
        f.out[x, y | :] = bounce_back_dfs(f, x, y, {EX, EY})
                          + 6.0 * W * (EX * U_LID);
    }

For each direction ``i``, ``bounce_back_dfs`` reads the population of
the neighbour in direction ``i`` that points back at this cell, and
the fluid neighbour pulls it on the next step.  This is full-way
bounce-back (Krüger et al. (2017) §5.3.3.2): the wall lies midway
between the wall node and the first fluid node.  The
``6 w_i (c_i · u_w)`` term injects the wall's momentum, with the wall
density taken as 1.  For a stationary wall, drop the second term
entirely.

First used in :doc:`07_lid_driven_cavity`.

Bounce-back written out per link
=================================

``bounce_back_dfs`` can also be written out one DF at a time.  At a
bottom wall cell, the three DFs that enter the fluid read the fluid
neighbours' populations travelling the other way:

.. code-block:: gelb

    dynamic WallBot {
        f.out[x, y | 2] = f.in[x,     y + 1 | 4];   // N ← S
        f.out[x, y | 5] = f.in[x + 1, y + 1 | 7];   // NE ← SW
        f.out[x, y | 6] = f.in[x - 1, y + 1 | 8];   // NW ← SE
        // ... remaining DFs set to 0 ...
    }

These are entries 2, 5 and 6 of ``bounce_back_dfs(f, x, y, {EX, EY})``
at a bottom wall; the fluid never pulls the other six, so setting them
to zero changes nothing for the flow.  When the fluid cell runs
``upstream_dfs`` on the next step, it pulls from the wall cell the
population it sent toward the wall two steps earlier; the effective
wall lies midway between the two cells.  Writing the links
out is useful when a wall needs its own rule per link, as the thermal
wall below does.

First used in :doc:`08_poiseuille_body_force`.  Also used
extensively in :doc:`09_rayleigh_benard` and
:doc:`13_salmon_ocean`.

Yoshida anti-bounce-back (fixed-T thermal wall)
=================================================

For the temperature lattice, the anti-bounce-back scheme
(Yoshida & Nagaoka 2010) sets the wall temperature to a fixed
value :math:`T_w` by reflecting with a sign change plus a
correction term:

.. code-block:: gelb

    // Temperature lattice g, hot bottom wall: the north-going DF
    g.out[x, y | 2] = -g.in[x, y + 1 | 4]
                      + 2.0 * sqrt(3.0) * DIFFUSIVITY * T_HOT;

The :math:`2\sqrt{3}\,\kappa\,T_w` correction term (with
``DIFFUSIVITY`` the thermal diffusivity :math:`\kappa`) enforces the
Dirichlet condition at the wall, midway between the nodes; the snippet is
from ``examples/lbm/2d/rayleigh_benard_2d_mrt.gelb``.

First used in :doc:`09_rayleigh_benard`.

Periodic boundaries
====================

Periodic boundaries are declared in the lattice definition,
not in a dynamic block:

.. code-block:: gelb

    lattice f(2, 9, real, {N, N}, {true, true});

No special wall node class is needed: a read past one edge
comes from the opposite edge, so the grid simply wraps around.

First used in :doc:`04_hello_world`.  Also used in
:doc:`11_shan_chen_multiphase` and :doc:`12_beyond_lbm_gol`.

Zou-He velocity / pressure
===========================

The Zou-He scheme (Zou & He 1997) imposes velocity or pressure
at an inlet/outlet by solving for the unknown DFs from the
known macroscopic constraint.  GeLB expresses this as a dynamic
block with per-DF writes derived from the constraint equations.

See ``examples/sukop/poiseuille_2d_bgk_pressure_zouhe.gelb``
for a pressure-driven Poiseuille flow using Zou-He pressure
BCs, and ``examples/lbm/2d/poiseuille_flow_2d_mrt_zouhe.gelb``
for the MRT variant.

Masked node classes (obstacle interiors)
=========================================

Cells inside a solid obstacle need no physics — they just need
to exist so wall cells can read from them.  No fluid cell may
reach them along any link, so the wall layer around them has to
cover the diagonals too, as the layer ``border()`` paints does (see
:doc:`10_karman_vortex`).  The ``masked``
modifier suppresses the gauge output of a node class (its cells
emit NaN in the NetCDF output, so visualisation tools render them
as blank space or a distinct colour) and disallows an attached
gauge; an initializer and a dynamic, when present, still run.  An
*empty* masked class holds defined zero DFs:

.. code-block:: gelb

    node_class SOLID() masked;

Other masked storage follows the ordinary initialization and
coverage rules.

First used in :doc:`10_karman_vortex`.
