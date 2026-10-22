==================================================
Source Visualisation: ``gelb-view source``
==================================================

GeLB ships a single tool for inspecting the *compile-time* state of
a ``.gelb`` program: ``gelb-view source``.  It bundles two views:

- **Geometry** — the per-cell node-class layout (which block runs
  where).  This is what the geometry figures of the Part B
  chapters show.
- **Stencils** — the per-block I/O pattern (which DFs each
  ``dynamic`` / ``gauge`` block reads from and writes to,
  expressed as spatial offsets from the current cell).

Both views answer different questions about the same program, and
``gelb-view source`` lets you see them together.

Quick start
============

.. code-block:: bash

    # Geometry only (1D bar / 2D heatmap / 3D slices)
    gelb-view source examples/sukop/karman_vortex_street_2d_bgk.gelb \
        --show=geo -o geometry.png

    # Stencils only (per-block velocity-set diagrams)
    gelb-view source examples/sukop/karman_vortex_street_2d_bgk.gelb \
        --show=algo -o stencils.png

    # Side-by-side
    gelb-view source examples/sukop/karman_vortex_street_2d_bgk.gelb \
        --show=both -o both.png

    # Combined: geometry + arrows from one cell to its read neighbours
    gelb-view source examples/lbm/2d/rayleigh_benard_2d_mrt.gelb \
        --show=combined --cell 64,1 -o combined.png

    # ASCII text mode (useful over SSH or in CI logs)
    gelb-view source examples/lbm/1d/heat_diffusion_1d_dirichlet.gelb \
        --text

    # Statistics table
    gelb-view source examples/sukop/karman_vortex_street_2d_bgk.gelb \
        --stats

    # JSON export (for tooling — used by the VSCode extension)
    gelb-view source examples/lbm/2d/rayleigh_benard_2d_mrt.gelb \
        --export-json analysis.json

You can also drop the subcommand entirely — ``gelb-view`` auto-detects
the file type and routes ``.gelb`` → ``source``, ``.nc`` → ``data``:

.. code-block:: bash

    gelb-view examples/sukop/karman_vortex_street_2d_bgk.gelb

Single-view subcommands
=======================

Two subcommands open one view on its own:

- ``gelb-view geo file.gelb`` — same as ``source --show=geo``
- ``gelb-view algo file.gelb`` — opens the standalone PySide6 stencil
  viewer (``source`` is the recommended entry point)

Reading the combined view
==========================

The combined mode is the most informative — it shows
**which cells your dynamic block actually reads**.  Click (or pass
``--cell x,y``) to pick a cell; the figure draws an arrow from
that cell to each cell its block reads from, labelled with the DF
index.

This is invaluable for debugging boundary conditions.  If you write
a wall block that's supposed to bounce DF 5 (NE) but accidentally
reads ``f.in[x+1, y+1 | 7]`` instead of ``f.in[x+1, y+1 | 5]``,
the arrow points at the wrong DF — a visual mismatch that's much
easier to spot than a numerical bug in the output.

Lint warnings (``--lint``)
===========================

GeLB includes a set of geometry-lint checks that run over the
resolved node-class map and flag common mistakes:

.. code-block:: bash

    gelb-view source mygeometry.gelb --lint

Checks performed:

- **Disconnected NC regions** — a node class painted in many small
  pieces may indicate a paint mistake (using full 8/26-connectivity,
  warns at >4 components)
- **Unreachable fluid pockets** — fluid cells separated from the
  bulk by walls

Lint warnings are also surfaced by ``gelbc`` itself, so they
appear at compile time.

VSCode integration
===================

The ``vscode-gelb`` extension provides a live interactive preview pane
that re-renders the geometry / stencils on every save.  See
``vscode-gelb/README.md`` for setup and the full feature list.

Once installed:

- Open any ``.gelb`` file
- Run "GeLB: Show Source Preview" from the command palette (or click
  the *GeLB: Show Source Preview* button in the editor's title bar)
- An interactive webview opens beside the editor: pan / zoom in 2D,
  orbit / fly-through in 3D, click a cell to inspect it, press
  **Space** to animate the reads / writes stencil
- Edit the file → save → preview refreshes within ~1 sec

The extension calls ``gelb-view source --export-json`` and renders
the result in the webview.

The sidebar's **Run** view runs the file with ``gelb-run`` as a VS
Code task: the progress bar and the MLUPS report appear in a terminal
of the panel, and *Stop* ends the run with everything it started.  It
exposes the everyday parameters as rows
you click to edit: time steps (``-n``), write-every (``-w``), constant
overrides (``-D NAME=VALUE``, picked from the file's
``global_constants``), the seed (``-s``, shown only when the program
calls ``random()``), the backend (``-b``), whether to open the viewer
at the end (``--view``) and the output folder, i.e. the working
directory where ``<name>.nc`` lands (next to the source file by
default).  The values are remembered per file.  One run goes at a time,
numbered, with a *Status* row; pressing *Run* while a run is still
going (compiling, simulating, or with its viewer window open) asks
before stopping it.  Every other flag of ``gelb-run`` (``--keep``,
``--verbose``, ``--fast-math``, ``--output-mode stdout``, the
``--cuda-*`` knobs) is for the command line: the view's *Show Run
Log* gives the command line of each run, to copy into a terminal and
extend.  The same run is a play button in the
editor title bar and a *Run* CodeLens above
``simulation_description(...)``.  In a source checkout the view uses
its ``scripts/gelb-run``, in an installation its ``bin/gelb-run``,
with nothing to configure; the setting ``gelb.gelbRunCommand`` names
another ``gelb-run`` when needed.

When to use it
===============

- **Verify geometry layout** before running a long simulation —
  catch off-by-1 errors in paint statements, wrong border()
  inference, etc.  Use ``--show=geo``.
- **Debug a wall BC** — pick a wall cell and check the read
  footprint.  Use ``--show=combined --cell x,y``.
- **Quick stats** — count cells per node class, check periodicity
  flags.  Use ``--stats``.
- **Programmatic analysis** — integrate the geometry/stencils
  into your own tooling.  Use ``gelb-view source --export-json``
  for the full geometry + stencils bundle (the same JSON the
  VSCode extension consumes), or ``gelb-view geo --export-npy``
  for a raw numpy ``nc_map`` + sidecar metadata.

The ``gelb-view source`` command works on any ``.gelb`` file,
including programs that fail later in compilation (for example a
type error in an expression) as long as their structure is valid:
the geometry and stencil analysis runs before code generation.
