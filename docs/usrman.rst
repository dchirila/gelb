=======================
GeLB User Tutorial
=======================

A guided tour through the Lattice Boltzmann Method using GeLB.

This manual teaches you how to write, run, and visualise LBM simulations
in GeLB.  It assumes some prior exposure to the Lattice Boltzmann
Method — if BGK collision and streaming are unfamiliar, work through
chapters 1–3 of Krüger, Kusumaatmaja, Kuzmin, Shardt, Silva & Viggen,
*The Lattice Boltzmann Method: Principles and Practice* (Springer,
2017) before starting here.  Everything else you need to know about
GeLB is in these pages.

The tutorial is organised in three parts:

**Part A — Orientation.**  Why GeLB exists, how to install it, and a
two-page language cheat-sheet ("GeLB in 10 minutes") that you can
return to as a reference.

**Part B — A guided tour through LBM with GeLB.**  Nine worked
examples, each anchored by one ``.gelb`` file from the repository.
Chapters build on each other: every new GeLB feature is introduced
exactly once.  The physics goes from 1D diffusion through 2D
Navier-Stokes, MRT collision, multi-lattice Rayleigh-Bénard
convection, obstacle flows and Shan-Chen multiphase to a
reduced-gravity ocean model.  One chapter steps outside LBM: Conway's
Game of Life, written in GeLB, shows that GeLB compiles stencil
updates in general, not only lattice Boltzmann models.

**Part C — Reference material.**  Boundary condition cookbook, stencil
visualisation, performance and backends, validation and convergence,
numerical semantics, and a cross-reference table mapping each tutorial
chapter to the relevant sections of Krüger et al. and Mohamad (2nd ed.).

.. note::

   All tutorial figures are reproducible from scratch by running
   ``python scripts/gen_tutorial_figures.py`` from the repository
   root, and the VS Code screenshots by
   ``node scripts/gen_vscode_screenshots.mjs`` (Linux, under ``xvfb``).  Committed figures under ``docs/user/figures/`` come with a
   ``MANIFEST.txt`` recording the git commit they were rendered at.

**Acknowledgements.**  GeLB grew out of research supervised by Gerrit
Lohmann (Alfred Wegener Institute, Bremerhaven), who secured its funding
and whose questions and feedback shaped both the language and this
tutorial.

.. only:: html

   Part A — Orientation
   --------------------

.. only:: latex

   .. raw:: latex

      \renewcommand{\thepart}{\Alph{part}}
      \part{Orientation}

.. toctree::
   :maxdepth: 2

   user/01_why_gelb
   user/02_getting_started
   user/03_gelb_in_10_minutes

.. only:: html

   Part B — A guided tour
   ----------------------

.. only:: latex

   .. raw:: latex

      \part{A guided tour}

.. toctree::
   :maxdepth: 2

   user/04_hello_world
   user/05_1d_diffusion
   user/07_lid_driven_cavity
   user/08_poiseuille_body_force
   user/09_rayleigh_benard
   user/10_karman_vortex
   user/11_shan_chen_multiphase
   user/12_beyond_lbm_gol
   user/13_salmon_ocean

.. only:: html

   Part C — Reference material
   ---------------------------

.. only:: latex

   .. raw:: latex

      \part{Reference material}

.. toctree::
   :maxdepth: 2

   user/14_boundary_conditions_cookbook
   user/15_stencil_visualisation
   user/16_performance_backends
   user/17_validation_and_convergence
   user/19_numerical_semantics
   user/18_further_reading
