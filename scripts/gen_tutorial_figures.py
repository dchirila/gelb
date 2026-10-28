#!/usr/bin/env python3
"""Regenerate every figure committed under ``docs/user/figures/``.

This script is the single source of truth for the GeLB user
tutorial's figures.  For every chapter in ``docs/usrman.rst`` that
carries one or more figures, this file contains one ``figure_NN_*``
function that:

1. Compiles the chapter's anchor ``.gelb`` example via ``gelbc``
   (invoked as a ``uv run`` subprocess -- no in-process imports, so
   the script does not depend on GeLB's Python package layout
   beyond the top-level ``uv`` command).
2. Links the generated Fortran with ``gfortran`` and NetCDF
   (detected via ``nf-config``).
3. Runs the binary to produce a NetCDF output file.
4. Reads the result via ``netCDF4.Dataset`` and renders one or
   more publication-quality PNG/SVG/GIF figures into
   ``docs/user/figures/``.

Caching is handled by a simple mtime check: a figure is only
regenerated if it is older than the corresponding ``.gelb`` example
or older than this script.  This keeps repeated invocations cheap
during iterative chapter writing while still guaranteeing a clean
full-regeneration path (just ``rm docs/user/figures/*.png`` first).

Usage::

    # Regenerate stale figures (default)
    python scripts/gen_tutorial_figures.py

    # Force full regeneration
    python scripts/gen_tutorial_figures.py --force

    # Only regenerate specific chapters (by number)
    python scripts/gen_tutorial_figures.py --chapters 05,08,11

    # Add CUDA backend to the performance chapter (requires nvcc)
    python scripts/gen_tutorial_figures.py --cuda

    # Higher DPI for publication quality (default: 150)
    python scripts/gen_tutorial_figures.py --dpi 300

The script writes a ``MANIFEST.txt`` into the figures directory
recording the git HEAD SHA and a timestamp for each figure, so
reviewers can tell whether the committed figures are in sync with
the repository.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from typing import Callable

# ---------------------------------------------------------------------------
# Paths -- anchor everything at the repo root so the script can be invoked
# from anywhere.
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_EXAMPLES_DIR = _REPO_ROOT / "examples"
_FIGURES_DIR = _REPO_ROOT / "docs" / "user" / "figures"

# Module-level DPI setting, overridden by --dpi CLI flag.
_DPI: int = 150


# ---------------------------------------------------------------------------
# Toolchain detection (mirrors gelb/tests/integration/test_examples_smoke.py)
# ---------------------------------------------------------------------------

def _detect_toolchain() -> tuple[str | None, str | None, str | None, str | None]:
    """Return (gfortran_path, nvcc_path, nc_fflags, nc_flibs)."""
    gfortran = shutil.which("gfortran")
    nvcc = shutil.which("nvcc")
    try:
        fflags = subprocess.check_output(
            ["nf-config", "--fflags"], text=True).strip().split("\n")[0]
        flibs = subprocess.check_output(
            ["nf-config", "--flibs"], text=True).strip().split("\n")[0]
        try:
            nc_prefix = subprocess.check_output(
                ["nc-config", "--prefix"], text=True).strip()
            c_libdir = f"-L{nc_prefix}/lib"
            if c_libdir not in flibs:
                flibs = f"{c_libdir} {flibs}"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    except (subprocess.CalledProcessError, FileNotFoundError):
        fflags, flibs = None, None
    return gfortran, nvcc, fflags, flibs


_GFORTRAN, _NVCC, _NC_FFLAGS, _NC_FLIBS = _detect_toolchain()


# ---------------------------------------------------------------------------
# Compile + run pipeline
# ---------------------------------------------------------------------------

def _gelbc_compile(
        example: pathlib.Path, out_f90: pathlib.Path,
        num_timesteps: int, write_every: int = 1,
        seed: int | None = None,
        nc_output: str = "out.nc") -> None:
    """Lower a .gelb file to Fortran 90 via gelbc.

    cpu_fortran_serial is single-threaded by design -- the figure
    generator uses it for determinism and for the small per-figure
    grid sizes where serial speed is fine.  It is named explicitly
    because gelbc's default backend is cpu_highway.
    """
    cmd = [
        "uv", "run", "--no-sync", "gelbc",
        str(example),
        "--backend", "cpu_fortran_serial",
        "-o", str(out_f90),
        "--num-timesteps", str(num_timesteps),
        "--write-every", str(write_every),
        "--nc-output", nc_output,
    ]
    if seed is not None:
        cmd.extend(["--seed", str(seed)])
    subprocess.run(cmd, check=True, capture_output=True, text=True,
                   cwd=str(_REPO_ROOT))


def _gfortran_link(src: pathlib.Path, exe: pathlib.Path) -> None:
    """Compile the generated Fortran with gfortran + NetCDF.

    cpu_fortran_serial is single-threaded by design; no -fopenmp.
    """
    if not _GFORTRAN or not _NC_FFLAGS or not _NC_FLIBS:
        raise RuntimeError(
            "gfortran or NetCDF-Fortran not found — install them before "
            "running the tutorial figure generator.")
    fflags = "-O2"
    cmd = f"{_GFORTRAN} {fflags} {_NC_FFLAGS} -o {exe} {src} {_NC_FLIBS}"
    subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)


def _run_binary(exe: pathlib.Path, cwd: pathlib.Path) -> None:
    """Execute the compiled simulation binary."""
    subprocess.run([str(exe)], check=True, capture_output=True, text=True,
                   cwd=str(cwd))


def _compile_and_run(
        example: pathlib.Path, num_timesteps: int,
        write_every: int = 1,
        seed: int | None = None) -> pathlib.Path:
    """Full pipeline: gelbc -> gfortran -> run.  Returns the NetCDF file path.

    The caller is responsible for copying or reading the NetCDF file
    before the temp directory is cleaned up.  Use the returned path
    inside a ``with`` block paired with the ``tempfile.TemporaryDirectory``
    that owns it, or copy the file out first.
    """
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="gelb_tutorial_"))
    src = tmpdir / "sim.f90"
    exe = tmpdir / "sim"
    nc = tmpdir / "out.nc"
    _gelbc_compile(example, src, num_timesteps=num_timesteps,
                   write_every=write_every, seed=seed,
                   nc_output="out.nc")
    _gfortran_link(src, exe)
    _run_binary(exe, cwd=tmpdir)
    return nc


# ---------------------------------------------------------------------------
# Per-figure definitions
# ---------------------------------------------------------------------------

@dataclass
class FigureSpec:
    """One tutorial figure and how to produce it.

    ``name`` is the basename (including extension) under
    ``docs/user/figures/``.  ``source_example`` points at the .gelb
    file the figure depends on -- its mtime drives the cache check.
    ``render`` is the actual plotting function; it receives the
    output directory path and writes ``<out_dir>/<name>``.
    """
    name: str
    source_example: pathlib.Path | None
    render: Callable[[pathlib.Path], None]
    extra_deps: list[pathlib.Path] = field(default_factory=list)

    def is_stale(self, out_dir: pathlib.Path, script_path: pathlib.Path) -> bool:
        target = out_dir / self.name
        if not target.exists():
            return True
        target_mtime = target.stat().st_mtime
        if script_path.stat().st_mtime > target_mtime:
            return True
        if self.source_example is not None \
                and self.source_example.stat().st_mtime > target_mtime:
            return True
        for dep in self.extra_deps:
            if dep.stat().st_mtime > target_mtime:
                return True
        return False


# ---------------------------------------------------------------------------
# Stub figure renderers -- a figure whose render function is not written
# yet raises NotImplementedError so running the script fails fast,
# making it obvious which figures are still placeholders.
# ---------------------------------------------------------------------------

def _not_yet_implemented(which: str):
    def _impl(out_dir: pathlib.Path) -> None:
        raise NotImplementedError(
            f"Figure '{which}' is a placeholder — its render function "
            f"will be filled in when chapter {which.split('_', 1)[0]} "
            f"is written.")
    return _impl


def _render_13_salmon_gyre(out_dir: pathlib.Path) -> None:
    """Chapter 13: Salmon ocean -- double-gyre layer depth."""
    import matplotlib.pyplot as plt
    import numpy as np
    import netCDF4

    example = _EXAMPLES_DIR / "lbm" / "2d" / "reduced_gravity_2d_sw_d2q9.gelb"
    nc_path = _compile_and_run(
        example, num_timesteps=100000, write_every=100000)
    try:
        ds = netCDF4.Dataset(nc_path)
        h = np.asarray(ds.variables["depth"][-1])  # (NY, NX)
        ds.close()
    finally:
        shutil.rmtree(nc_path.parent, ignore_errors=True)

    fig, ax = plt.subplots(figsize=(6, 5.5), dpi=_DPI)
    im = ax.imshow(
        h, origin="lower", cmap="RdBu_r", aspect="equal",
        interpolation="bilinear")
    ax.set_xlabel("x (grid cells)")
    ax.set_ylabel("y (grid cells)")
    ax.set_title(
        "Salmon (1999) double-gyre ocean — layer depth $h(x, y)$\n"
        "SW D2Q9, 100×100 basin, $t = 100000$",
        fontsize=10)
    fig.colorbar(im, ax=ax, label="layer depth $h$", shrink=0.85)
    fig.tight_layout()
    fig.savefig(out_dir / "13_salmon_gyre.png",
                dpi=_DPI, bbox_inches="tight")
    plt.close(fig)


def _render_12_gol_glider(out_dir: pathlib.Path) -> None:
    """Chapter 12: Game of Life -- a glider traversing the grid.

    Runs the Game of Life glider example at its default ``GRID = 32``,
    small enough that individual cells of the 5-cell glider are clearly
    visible across the domain.  A glider has period 4 in time
    and moves one cell diagonally (+1 in x, -1 in y) per period, so
    over 120 steps
    (30 periods) it traverses nearly a full diagonal of the 32x32
    doubly-periodic torus.

    Rendered as a 2x3 grid of snapshots at six equally spaced
    timesteps (t = 0, 24, 48, 72, 96, 120).
    """
    import matplotlib.pyplot as plt
    import numpy as np
    import netCDF4

    example = _EXAMPLES_DIR / "lgca" / "2d" / "game_of_life_glider.gelb"
    num_timesteps = 120
    write_every = 1
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="gelb_gol_"))
    src = tmpdir / "sim.f90"
    exe = tmpdir / "sim"
    cmd = [
        "uv", "run", "--no-sync", "gelbc",
        str(example),
        "--backend", "cpu_fortran_serial",
        "-o", str(src),
        "--num-timesteps", str(num_timesteps),
        "--write-every", str(write_every),
        "--nc-output", "out.nc",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True,
                   cwd=str(_REPO_ROOT))
    _gfortran_link(src, exe)
    _run_binary(exe, cwd=tmpdir)
    try:
        ds = netCDF4.Dataset(tmpdir / "out.nc")
        state = np.asarray(ds.variables["status"][:])  # (T+1, N, N)
        ds.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    grid = state.shape[-1]

    # Six equally spaced snapshots from t=0 to t=num_timesteps.
    t_marks = [0, 24, 48, 72, 96, 120]

    fig, axes = plt.subplots(2, 3, figsize=(9.6, 6.4), dpi=_DPI)
    for ax, t in zip(axes.flat, t_marks):
        rec_idx = t  # write_every = 1
        ax.imshow(
            state[rec_idx], origin="lower", cmap="gray_r",
            vmin=0, vmax=1, aspect="equal",
            extent=[-0.5, grid - 0.5, -0.5, grid - 0.5],
            interpolation="nearest")
        # Subtle cell grid so the 5-cell glider structure stands out
        ax.set_xticks(np.arange(-0.5, grid, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, grid, 1), minor=True)
        ax.grid(which="minor", color="#e6e6e6", linestyle="-", linewidth=0.4)
        ax.tick_params(which="minor", bottom=False, left=False)
        ax.set_xticks([0, 15, 31])
        ax.set_yticks([0, 15, 31])
        ax.tick_params(labelsize=8)
        ax.set_title(rf"$t = {t}$", fontsize=10)

    fig.suptitle(
        f"Conway's Game of Life in GeLB — glider on a {grid}×{grid} "
        "periodic torus",
        fontsize=11)
    fig.tight_layout()
    fig.savefig(out_dir / "12_gol_glider.png",
                dpi=_DPI, bbox_inches="tight")
    plt.close(fig)


def _render_11_shanchen_phase_separation(out_dir: pathlib.Path) -> None:
    """Chapter 11: Shan-Chen SCMP -- phase-separation evolution.

    Runs shan_chen_2d.gelb (at a reduced N=256 to keep the figure
    within the ~1-minute budget -- the default N=1024 is way too
    expensive for figure regeneration) with ``--seed 42`` for
    reproducibility, writing 4 snapshots covering the four stages
    Sukop's Fig. 46 identifies:

      1) random initial perturbation
      2) spinodal stripes (~100 steps)
      3) coarsening (~1000 steps)
      4) large blobs (~10000 steps)

    Rendered as a 2x2 grid of density heatmaps.
    """
    import matplotlib.pyplot as plt
    import numpy as np
    import netCDF4

    example = _EXAMPLES_DIR / "sukop" / "shan_chen_2d.gelb"
    num_timesteps = 10000
    write_every = 100
    # Override N to a smaller grid so the run fits in ~1 minute.
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="gelb_shanchen_"))
    src = tmpdir / "sim.f90"
    exe = tmpdir / "sim"
    cmd = [
        "uv", "run", "--no-sync", "gelbc",
        str(example),
        "--backend", "cpu_fortran_serial",
        "-o", str(src),
        "--num-timesteps", str(num_timesteps),
        "--write-every", str(write_every),
        "--nc-output", "out.nc",
        "-D", "N=256",
        "--seed", "42",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True,
                   cwd=str(_REPO_ROOT))
    _gfortran_link(src, exe)
    _run_binary(exe, cwd=tmpdir)
    try:
        ds = netCDF4.Dataset(tmpdir / "out.nc")
        rho = np.asarray(ds.variables["rho"][:])   # (T+1, Ny, Nx)
        ds.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    # Pick four snapshots: t=0 (initial), t=100 (spinodal),
    # t=1000 (coarsening), t=10000 (large blobs).
    def _rec(t_step):
        # NetCDF records are written at t = 0, write_every, 2*we, ...
        return t_step // write_every if t_step > 0 else 0

    snap_indices = [_rec(0), _rec(100), _rec(1000),
                    _rec(num_timesteps)]
    snap_labels = [
        r"$t = 0$  (random initial)",
        r"$t = 100$  (spinodal stripes)",
        r"$t = 1000$  (coarsening)",
        rf"$t = {num_timesteps}$  (large blobs)",
    ]

    # Shared colormap: use a stable vmin/vmax across all frames.
    # The final frame has the widest density range; use its 1st/99th
    # percentile to clip outliers.
    rho_final = rho[snap_indices[-1]]
    vmin = float(np.percentile(rho_final, 1))
    vmax = float(np.percentile(rho_final, 99))

    fig, axes = plt.subplots(2, 2, figsize=(9, 8), dpi=_DPI)
    for ax, idx, label in zip(axes.flat, snap_indices, snap_labels):
        im = ax.imshow(
            rho[idx], origin="lower", cmap="viridis",
            vmin=vmin, vmax=vmax, aspect="equal",
            interpolation="nearest")
        ax.set_title(label, fontsize=10)
        ax.set_xticks([])
        ax.set_yticks([])

    cbar = fig.colorbar(im, ax=axes.ravel().tolist(),
                        shrink=0.85, fraction=0.025, pad=0.02)
    cbar.set_label(r"density $\rho$  (lattice units)", fontsize=9)

    fig.suptitle(
        "Shan-Chen single-component multiphase separation — "
        rf"N = 256, BGK $\tau = 1$, G$_{{SC}}$ = $-120$",
        fontsize=11)
    fig.savefig(out_dir / "11_shanchen_phase_separation.png",
                dpi=_DPI, bbox_inches="tight")
    plt.close(fig)


_KARMAN_FIG_STEPS = 300000
_KARMAN_FIG_WRITE_EVERY = 2000
_KARMAN_FIG_TIMES = (150000, 230000, 300000)


def _run_10_karman(out_nc: pathlib.Path) -> None:
    """Run the Sukop disk example with the figure's settings.

    ``NY = 256`` and ``G = 4e-7`` (the defaults are ``NY = 200``,
    ``G = 2e-7``), 300 000 steps, a record every 2000.  About 80 s on
    ``gpu_cuda_cpp``; ``cpu_highway`` when ``nvcc`` is missing.
    """
    backend = "gpu_cuda_cpp" if _NVCC else "cpu_highway"
    example = _EXAMPLES_DIR / "sukop" / "karman_vortex_street_2d_bgk.gelb"
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="gelb_karman_"))
    try:
        subprocess.run(
            [str(_REPO_ROOT / "scripts" / "gelb-run"), "-b", backend,
             "-n", str(_KARMAN_FIG_STEPS),
             "-w", str(_KARMAN_FIG_WRITE_EVERY),
             "-D", "G=4.0e-7", "-D", "NY=256", str(example)],
            check=True, capture_output=True, text=True, cwd=str(tmpdir))
        shutil.move(str(tmpdir / f"{example.stem}.nc"), str(out_nc))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _plot_10_karman(nc_path: pathlib.Path, out_dir: pathlib.Path) -> None:
    """Spanwise vorticity behind the disk at ``_KARMAN_FIG_TIMES``."""
    import matplotlib.pyplot as plt
    import numpy as np
    import netCDF4

    ds = netCDF4.Dataset(nc_path)
    ds.set_auto_mask(False)
    times = np.asarray(ds.variables["time"][:]).astype(int).tolist()
    frames = [times.index(t) for t in _KARMAN_FIG_TIMES]
    all_ux = [np.asarray(ds.variables["ux"][k], dtype=float) for k in frames]
    all_uy = [np.asarray(ds.variables["uy"][k], dtype=float) for k in frames]
    ds.close()

    Ny, Nx = all_ux[0].shape
    cx, cy, r = Nx // 4, Ny // 2 - 1, 20      # the example's CX, CY, R
    wake_start = cx + 2 * r                   # one diameter behind the centre
    yy, xx = np.mgrid[0:Ny, 0:Nx]
    disk = (xx - cx) ** 2 + (yy - cy) ** 2 < r * r   # SOLID and its WALL ring

    def compute_vorticity(ux_frame, uy_frame):
        # A bounce-back wall cell holds populations in transit, so its
        # gauge is not a fluid velocity: give the wall cells (the disk's
        # ring, the channel's first and last rows) the no-slip value 0.
        ux_frame = np.where(disk, 0.0, ux_frame)
        uy_frame = np.where(disk, 0.0, uy_frame)
        ux_frame[[0, -1], :] = 0.0
        uy_frame[[0, -1], :] = 0.0
        omega = np.zeros_like(ux_frame)
        omega[1:-1, 1:-1] = (
            (uy_frame[1:-1, 2:] - uy_frame[1:-1, :-2]) / 2.0
            - (ux_frame[2:, 1:-1] - ux_frame[:-2, 1:-1]) / 2.0)
        omega = np.where(disk, 0.0, omega)
        return omega, disk

    # One colour scale for all panels, from the last (strongest) frame.
    omega_ref, _ = compute_vorticity(all_ux[-1], all_uy[-1])
    vmax = np.nanpercentile(np.abs(omega_ref[:, wake_start:]), 99.5) or 1.0

    fig, axes = plt.subplots(3, 1, figsize=(12, 6.5), dpi=_DPI)

    for ax, t_val, ux_f, uy_f in zip(axes, _KARMAN_FIG_TIMES, all_ux, all_uy):
        omega_f, smask = compute_vorticity(ux_f, uy_f)
        im = ax.imshow(
            omega_f, origin="lower", cmap="RdBu_r",
            vmin=-vmax, vmax=+vmax,
            extent=[0, Nx - 1, 0, Ny - 1], aspect="equal",
            interpolation="nearest")

        if smask.any():
            masked_overlay = np.ma.masked_where(
                ~smask, smask.astype(float))
            ax.imshow(
                masked_overlay, origin="lower",
                cmap="gray_r", vmin=0, vmax=1,
                extent=[0, Nx - 1, 0, Ny - 1], aspect="equal",
                alpha=1.0, interpolation="nearest")

        ax.set_ylabel("$y$")
        ax.set_title(rf"$t = {t_val}$", fontsize=9, loc="left")
        if ax is not axes[-1]:
            ax.set_xticks([])

    axes[-1].set_xlabel("cell index $x$")

    cbar = fig.colorbar(im, ax=axes.ravel().tolist(),
                        shrink=0.85, fraction=0.012, pad=0.015)
    cbar.set_label(r"$\omega_z$", fontsize=9)

    fig.suptitle(
        "Flow past a disk in a periodic channel — BGK D2Q9, "
        r"$N_y = 256$: the wake turns unstable and starts to shed",
        fontsize=10)
    fig.savefig(out_dir / "10_karman_vorticity.png",
                dpi=_DPI, bbox_inches="tight")
    plt.close(fig)


def _render_10_karman_vorticity(out_dir: pathlib.Path) -> None:
    """Chapter 10: flow past a disk -- the wake at three times.

    The channel spins up over its viscous time H^2/nu ~= 3.2 M steps; the
    symmetric wake turns unstable around t = 160 000 (centreline
    Re ~= 75) and sheds from about t = 250 000.
    """
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="gelb_karman_fig_"))
    try:
        nc = tmpdir / "karman.nc"
        _run_10_karman(nc)
        _plot_10_karman(nc, out_dir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _render_09_rb_temperature_rolls(out_dir: pathlib.Path) -> None:
    """Chapter 9: Rayleigh-Benard -- T heatmap with velocity arrows.

    Runs the RB-MRT example at the default Ra=10000, Pr=0.71 for
    enough steps to develop well-formed convection rolls.  The
    example uses a random initial perturbation (``--seed 42`` keeps
    this bit-reproducible).  The figure shows the full (NX, NY)
    temperature field at the final snapshot with a sparse grid of
    velocity arrows overlaid so the reader can see the rolls
    physically turning.
    """
    import matplotlib.pyplot as plt
    import numpy as np
    import netCDF4

    example = _EXAMPLES_DIR / "lbm" / "2d" / "rayleigh_benard_2d_mrt.gelb"
    num_timesteps = 30000
    write_every = 30000
    nc_path = _compile_and_run(
        example, num_timesteps=num_timesteps, write_every=write_every,
        seed=42)
    try:
        ds = netCDF4.Dataset(nc_path)
        T = np.asarray(ds.variables["T"][-1])       # (Ny, Nx)
        ux = np.asarray(ds.variables["uX"][-1])
        uy = np.asarray(ds.variables["uY"][-1])
        ds.close()
    finally:
        shutil.rmtree(nc_path.parent, ignore_errors=True)

    Ny, Nx = T.shape

    fig, ax = plt.subplots(figsize=(11, 4.0), dpi=_DPI)

    im = ax.imshow(
        T, origin="lower", cmap="RdBu_r", aspect="equal",
        extent=[0, Nx - 1, 0, Ny - 1])

    # Sparse arrow overlay -- subsample so the figure isn't cluttered
    stride_x = max(1, Nx // 48)
    stride_y = max(1, Ny // 16)
    x_c = np.arange(Nx)
    y_c = np.arange(Ny)
    X, Y = np.meshgrid(x_c[::stride_x], y_c[::stride_y])
    UX = ux[::stride_y, ::stride_x]
    UY = uy[::stride_y, ::stride_x]
    # Skip wall rows (uX = uY = 0 there anyway by bounce-back)
    ax.quiver(
        X, Y, UX, UY,
        color="black", alpha=0.85,
        scale=None, scale_units="xy",
        width=0.002, headwidth=4, headlength=4)

    ax.set_xlabel("cell index $x$")
    ax.set_ylabel("cell index $y$")
    ax.set_xlim(0, Nx - 1)
    ax.set_ylim(0, Ny - 1)

    cbar = fig.colorbar(im, ax=ax, shrink=0.85, fraction=0.025, pad=0.02)
    cbar.set_label("temperature $T$  (lattice units)", fontsize=9)

    fig.suptitle(
        "Rayleigh-Bénard convection (MRT, Ra = 10 000, Pr = 0.71) — "
        f"D2Q9 fluid + D2Q5 temperature, $t = {num_timesteps}$",
        fontsize=11)
    fig.tight_layout()
    fig.savefig(out_dir / "09_rb_temperature_rolls.png",
                dpi=_DPI, bbox_inches="tight")
    plt.close(fig)


def _render_16_mlups_backend_comparison(out_dir: pathlib.Path) -> None:
    """Chapter 16: cross-backend MLUPS bar chart (the three backends).

    Reads ``docs/user/figures/data/16_mlups_backend_comparison.json``
    (populated by ``scripts/benchmark_backends.py`` across one or more
    machines) and emits a grouped bar chart: N examples on the x-axis,
    3 backend bars per group.  A backend with no data is drawn as a
    hatched "no data" bar.

    Linear MLUPS y-axis is deliberate -- a log scale would hide the
    serial->CUDA payoff that is the figure's reason for existing.
    """
    import json as _json
    import matplotlib.pyplot as plt
    import numpy as np

    data_path = _FIGURES_DIR / "data" / "16_mlups_backend_comparison.json"
    if not data_path.exists():
        raise FileNotFoundError(
            f"{data_path} not found — run "
            f"`scripts/benchmark_backends.py --backend <b>` for each "
            f"backend before regenerating this figure.")
    with data_path.open() as f:
        doc = _json.load(f)

    cases = list(doc["cases"].keys())  # preserves JSON insertion order
    # benchmark_backends.py records the multi-threaded CPU backend as
    # "cpu_highway"; the tracked JSON from 1.0 still has the older key
    # "cpu_openmp" for the same backend.  Plot whichever is present.
    cpu_mt = "cpu_highway" if doc["results"].get("cpu_highway") else "cpu_openmp"
    backends = ["cpu_serial", cpu_mt, "cuda"]
    backend_labels = {
        "cpu_serial": "CPU serial",
        "cpu_openmp": "CPU OpenMP",
        "cpu_highway": "CPU OpenMP",
        "cuda": "CUDA",
    }
    # Colour-blind-safer palette (blue / orange / green) distinct from
    # the matplotlib default wheel used elsewhere in the tutorial.
    colours = {"cpu_serial": "#4C72B0",
               "cpu_openmp": "#DD8452",
               "cpu_highway": "#DD8452",
               "cuda": "#55A868"}

    n_cases = len(cases)
    n_backends = len(backends)
    bar_width = 0.8 / n_backends
    x_centres = np.arange(n_cases)

    fig, ax = plt.subplots(figsize=(8.5, 4.5), dpi=_DPI)

    machines: dict[str, str] = {}
    for b_idx, backend in enumerate(backends):
        results_b = doc["results"].get(backend, {}) or {}
        heights = []
        for case in cases:
            entry = results_b.get(case)
            if entry is None or entry.get("median") in (None, 0):
                heights.append(0.0)
            else:
                heights.append(float(entry["median"]))
        # One representative machine string per backend (first case's).
        for entry in results_b.values():
            if entry.get("machine"):
                machines[backend] = entry["machine"]
                break

        offsets = x_centres + (b_idx - (n_backends - 1) / 2) * bar_width
        bars = ax.bar(
            offsets, heights, width=bar_width * 0.92,
            label=backend_labels[backend], color=colours[backend],
            edgecolor="black", linewidth=0.5)

        # Hatch "no data" bars at a small visible placeholder height
        # (3% of the best real value, or 1 MLUPS if nothing is real).
        real_max = max((h for h in heights if h > 0), default=0.0)
        placeholder = max(real_max * 0.03, 1.0) if real_max > 0 else 1.0
        for bar, h in zip(bars, heights):
            if h <= 0:
                bar.set_height(placeholder)
                bar.set_color("#dddddd")
                bar.set_hatch("///")
                bar.set_edgecolor("#888888")
                ax.text(bar.get_x() + bar.get_width() / 2,
                        placeholder, "no data",
                        ha="center", va="bottom", fontsize=7,
                        color="#555555", rotation=0)
            else:
                ax.text(bar.get_x() + bar.get_width() / 2, h,
                        f"{h:.0f}", ha="center", va="bottom", fontsize=8)

    # Pretty case labels.
    pretty = {
        "lid_cavity_2d": "Lid-driven cavity (D2Q9 BGK, 512²)",
        "poiseuille_2d": "Poiseuille (D2Q9 MRT, 256²)",
        "tgv_2d": "Taylor-Green vortex (D2Q9 BGK, 512²)",
    }
    ax.set_xticks(x_centres)
    ax.set_xticklabels([pretty.get(c, c) for c in cases], fontsize=9)
    ax.set_ylabel("Compute MLUPS  (million lattice updates / second)")
    ax.set_title("Cross-backend performance  (median of 3 samples)",
                 fontsize=11)
    ax.legend(loc="upper left", fontsize=9, frameon=True)
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_axisbelow(True)

    # Host-attribution caption under the figure.
    cpu_host = machines.get(cpu_mt) or machines.get("cpu_serial")
    gpu_host = machines.get("cuda")
    host_bits = []
    if cpu_host:
        host_bits.append(f"CPU: {cpu_host}")
    if gpu_host:
        host_bits.append(f"GPU: {gpu_host}")
    caption = " | ".join(host_bits) if host_bits else ""
    if caption:
        fig.text(0.5, -0.01, caption, ha="center", va="top",
                 fontsize=7.5, color="#444444")

    fig.tight_layout()
    fig.savefig(out_dir / "16_mlups_backend_comparison.png",
                dpi=_DPI, bbox_inches="tight")
    plt.close(fig)


def _render_17_rb_onset_validation(out_dir: pathlib.Path) -> None:
    """Chapter 17: Rayleigh-Benard onset validation.

    Reads
    ``docs/user/figures/data/17_rb_onset_validation.json``
    (produced by ``scripts/rb_onset_collect.py`` after a
    ``scripts/find_ra_critical.py`` sweep) and plots
    ``max_{x,y}|u_y|(t)`` on a semi-log y axis -- one curve per Ra
    value, colour-coded by Ra.  Horizontal bands mark the decay
    floor and growth threshold; the caption cites the resulting
    bracket against the theoretical ``Ra_c ~= 1707.76``.
    """
    import json as _json
    import matplotlib.pyplot as plt
    import numpy as np

    data_path = _FIGURES_DIR / "data" / "17_rb_onset_validation.json"
    if not data_path.exists():
        raise FileNotFoundError(
            f"{data_path} not found — run "
            f"`scripts/find_ra_critical.py` and then "
            f"`scripts/rb_onset_collect.py` before regenerating "
            f"this figure.")
    with data_path.open() as f:
        doc = _json.load(f)

    # Curves are keyed by Ra-as-string; restore numeric ordering.
    ra_strs = sorted(doc["curves"].keys(), key=lambda s: float(s))
    ra_vals = [float(s) for s in ra_strs]

    decay_thr = float(doc["decay_threshold"])
    grow_thr = float(doc["grow_threshold"])
    ra_c = float(doc["ra_c_theory"])
    bracket = doc.get("bracket", {}) or {}

    # Sequential colour map spanning the Ra range -- darkest at low Ra
    # (decaying), brightest at high Ra (growing).
    cmap = plt.get_cmap("viridis")
    norm_vals = np.linspace(0.15, 0.95, len(ra_vals))

    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=_DPI)

    for ra_s, ra, c_pos in zip(ra_strs, ra_vals, norm_vals):
        curve = doc["curves"][ra_s]
        t = np.asarray(curve["time"], dtype=float)
        y = np.asarray(curve["max_uy"], dtype=float)
        ax.plot(t, y, linewidth=1.3, color=cmap(c_pos),
                label=f"Ra = {ra:g}")

    # Annotation bands.
    ax.axhspan(0.0, decay_thr, color="#4C72B0", alpha=0.06, zorder=0)
    ax.axhspan(grow_thr, 1.0, color="#C44E52", alpha=0.06, zorder=0)
    ax.axhline(decay_thr, color="#4C72B0", linestyle="--",
               linewidth=0.8, alpha=0.7)
    ax.axhline(grow_thr, color="#C44E52", linestyle="--",
               linewidth=0.8, alpha=0.7)
    ax.text(0.99, decay_thr, f"  decay ≤ {decay_thr:g}",
            transform=ax.get_yaxis_transform(),
            ha="right", va="bottom", fontsize=8, color="#4C72B0")
    ax.text(0.99, grow_thr, f"  grow ≥ {grow_thr:g}",
            transform=ax.get_yaxis_transform(),
            ha="right", va="bottom", fontsize=8, color="#C44E52")

    ax.set_yscale("log")
    ax.set_xlabel("timestep")
    ax.set_ylabel(r"$\max_{x,y}|u_y|$  (lattice units)")

    # Caption bracket summary.
    dec_max = bracket.get("decaying_max")
    gro_min = bracket.get("growing_min")
    if dec_max is not None and gro_min is not None:
        bracket_text = (f"GeLB bracket: "
                        f"$Ra_c \\in ({dec_max:g},\\,{gro_min:g})$; "
                        f"theory $Ra_c \\approx {ra_c}$")
    else:
        bracket_text = (f"GeLB sweep; theory $Ra_c \\approx {ra_c}$")

    ax.set_title(
        f"Rayleigh-Bénard onset validation  (NY = {doc.get('ny', 43)})",
        fontsize=11)
    fig.text(0.5, -0.01, bracket_text, ha="center", va="top",
             fontsize=9, color="#222222")

    ax.legend(loc="upper left", fontsize=8, ncol=2, frameon=True)
    ax.grid(True, which="both", alpha=0.3)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(out_dir / "17_rb_onset_validation.png",
                dpi=_DPI, bbox_inches="tight")
    plt.close(fig)


def _render_08_poiseuille_convergence(out_dir: pathlib.Path) -> None:
    """Chapter 8: Poiseuille MRT -- profile + O(h^2) convergence plot.

    Runs ``poiseuille_flow_2d_mrt.gelb`` at a single base resolution
    for the velocity-profile panel, then sweeps the grid resolution
    NY in {16, 32, 64, 128} to build a log-log L2-error convergence
    plot.  The example's body-force rescaling (G ~ 1/(NY-2)^2) keeps
    the peak velocity fixed as NY grows, so the comparison is apples
    to apples.
    """
    import matplotlib.pyplot as plt
    import numpy as np
    import netCDF4

    example = _EXAMPLES_DIR / "lbm" / "2d" / "poiseuille_flow_2d_mrt.gelb"

    def _run_at_NY(NY: int, num_timesteps: int):
        tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="gelb_poi_"))
        src = tmpdir / "sim.f90"
        exe = tmpdir / "sim"
        # Compile with the NY override on the gelbc command line
        cmd = [
            "uv", "run", "--no-sync", "gelbc",
            str(example),
            "--backend", "cpu_fortran_serial",
            "-o", str(src),
            "--num-timesteps", str(num_timesteps),
            "--write-every", str(num_timesteps),
            "--nc-output", "out.nc",
            "-D", f"NY={NY}",
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True,
                       cwd=str(_REPO_ROOT))
        _gfortran_link(src, exe)
        _run_binary(exe, cwd=tmpdir)
        ds = netCDF4.Dataset(tmpdir / "out.nc")
        ux = np.asarray(ds.variables["ux"][-1])
        ds.close()
        shutil.rmtree(tmpdir, ignore_errors=True)
        return ux

    # Parameters matching the example's defaults.
    tau = 0.54
    nu = (tau - 0.5) / 3.0
    G_BASE = 1e-5
    NY_BASE = 32

    def _analytical_profile(NY: int):
        """Analytical parabolic profile at a given NY, in lattice units.

        Uses the same half-way-wall convention as the example: the
        effective channel height is H = NY - 2, with the no-slip
        surfaces sitting at y = 0.5 and y = NY - 1.5.  Returns both
        the y-indices of the fluid cells and the analytical u(y)
        restricted to those cells.
        """
        H = NY - 2
        G_ny = G_BASE * (NY_BASE - 2) ** 2 / (NY - 2) ** 2
        y_fluid = np.arange(1, NY - 1)  # interior only
        y_eff = y_fluid - 0.5
        u_analytical = G_ny / (2.0 * nu) * y_eff * (H - y_eff)
        return y_fluid, u_analytical

    def _run_budget(NY: int) -> int:
        """Number of time steps needed to reach steady state at this NY.

        Matches ``scripts/validate_analytical.py``:
        ``t_diff = H^2 / nu`` and we run for 5 diffusion times or
        10 000 steps, whichever is larger.
        """
        H = NY - 2
        t_diff = int(H * H / nu)
        return max(5 * t_diff, 10000)

    # Panel A: profile at NY=32 vs the analytical parabola
    NY_prof = 32
    ux_prof = _run_at_NY(NY=NY_prof, num_timesteps=_run_budget(NY_prof))
    # Single-column sample at x=2, restricted to fluid nodes
    # (same as validate_analytical.py).  The flow is x-invariant.
    y_fluid_prof, u_ana_prof = _analytical_profile(NY_prof)
    u_sim_prof = ux_prof[1:NY_prof - 1, 2]

    # Panel B: convergence sweep
    NY_list = [16, 32, 64, 128]
    l2_errors = []
    for NY in NY_list:
        ux = _run_at_NY(NY=NY, num_timesteps=_run_budget(NY))
        u_sim = ux[1:NY - 1, 2]
        _, u_ana = _analytical_profile(NY)
        # Relative L2 error normalised by the analytical solution's
        # L2 norm -- matches validate_analytical.py exactly.
        err = np.sqrt(np.sum((u_sim - u_ana) ** 2) / np.sum(u_ana ** 2))
        l2_errors.append(err)
    l2_errors = np.array(l2_errors)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), dpi=_DPI)

    # Panel A: velocity profile vs analytical parabola
    axes[0].plot(y_fluid_prof, u_sim_prof,
                 "C0o", markersize=5, label=f"GeLB MRT, NY={NY_prof}")
    H_prof = NY_prof - 2
    y_dense = np.linspace(0.5, NY_prof - 1.5, 200)
    u_dense = G_BASE / (2.0 * nu) * (y_dense - 0.5) * (H_prof - (y_dense - 0.5))
    axes[0].plot(y_dense, u_dense, "k--", linewidth=1.3,
                 label="analytical parabola")
    axes[0].set_xlabel("cell index $y$")
    axes[0].set_ylabel(r"streamwise velocity $u_x$  (lattice units)")
    axes[0].set_title("Velocity profile vs analytical solution",
                      fontsize=10)
    axes[0].legend(fontsize=8, loc="upper right")
    axes[0].grid(True, alpha=0.3)

    # Panel B: log-log convergence plot
    h_vals = np.array([1.0 / (ny - 2) for ny in NY_list])  # h = 1/H
    axes[1].loglog(h_vals, l2_errors, "C0o-", markersize=7,
                   linewidth=1.5, label="measured $L_2$ error")
    # Reference slope: 2nd order
    h_ref = np.array([h_vals[0], h_vals[-1]])
    slope2 = l2_errors[0] * (h_ref / h_vals[0]) ** 2
    axes[1].loglog(h_ref, slope2, "k--", linewidth=1.0,
                   label=r"$\mathcal{O}(h^2)$ reference slope")
    axes[1].set_xlabel(r"grid spacing $h = 1/(N_y - 2)$")
    axes[1].set_ylabel(r"$L_2$ error vs analytical parabola")
    axes[1].set_title(
        f"Grid convergence study (NY = {', '.join(str(n) for n in NY_list)})",
        fontsize=10)
    for i, NY in enumerate(NY_list):
        axes[1].annotate(f"NY={NY}",
                         xy=(h_vals[i], l2_errors[i]),
                         xytext=(6, 6), textcoords="offset points",
                         fontsize=8)
    axes[1].legend(fontsize=8, loc="lower right")
    axes[1].grid(True, which="both", alpha=0.3)

    # Estimated convergence slope from log-log fit
    slope = np.polyfit(np.log(h_vals), np.log(l2_errors), 1)[0]
    fig.suptitle(
        f"Poiseuille flow (MRT, half-way BB + Strang force) — "
        rf"measured slope $\approx {slope:.2f}$",
        fontsize=11)
    fig.tight_layout()
    fig.savefig(out_dir / "08_poiseuille_convergence.png",
                dpi=_DPI, bbox_inches="tight")
    plt.close(fig)


def _render_07_ldc_ghia_validation(out_dir: pathlib.Path) -> None:
    """Chapter 7: lid-driven cavity validation against Ghia 1982.

    Reads the JSON artifact produced by ``scripts/validate_ldc.py``
    (schema v2, nested by collision operator) and emits a 2-panel
    figure: vertical centerline ``u(y)`` and horizontal centerline
    ``v(x)``.  When the JSON contains multiple collision operators
    (e.g. BGK and MRT) both are overlaid on Ghia points, with
    distinct line styles.

    Caption reports relative L2 errors vs Ghia for each (Re,
    collision) pair.
    """
    import json as _json
    import matplotlib.pyplot as plt
    import numpy as np

    data_path = _FIGURES_DIR / "data" / "07_ldc_ghia_validation.json"
    if not data_path.exists():
        raise FileNotFoundError(
            f"{data_path} not found — run "
            f"`scripts/validate_ldc.py` before regenerating "
            f"this figure.")
    with data_path.open() as f:
        doc = _json.load(f)

    raw = doc["results"]
    schema = doc.get("schema_version", 1)
    # Normalise schema v1 -> v2 (single implicit "bgk" bucket).
    if schema < 2:
        results = {"bgk": raw}
    else:
        results = raw
    if not any(results.values()):
        raise RuntimeError(
            f"{data_path} has no run entries — re-run validate_ldc.py.")

    # Collect all distinct Re values across collisions.
    all_re = sorted({int(k) for sub in results.values() for k in sub})
    cmap = plt.get_cmap("viridis")
    re_colour = {re: cmap(c) for re, c in
                 zip(all_re, np.linspace(0.15, 0.85, max(len(all_re), 1)))}

    # Distinct line styles per collision operator.
    coll_style = {"bgk": "--", "mrt": "-", "trt": ":", "incomp_zou": "-."}
    coll_label = {"bgk": "BGK", "mrt": "MRT", "trt": "TRT",
                  "incomp_zou": "BGK-incomp"}

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.0), dpi=_DPI)

    # Per-(Re, collision) L2 errors collected for the caption table.
    l2_table: dict[tuple[int, str], tuple[float, float]] = {}
    ghia_drawn = set()  # avoid drawing the same Ghia points multiple times
    for collision in sorted(results.keys()):
        for re_key in sorted(results[collision].keys(), key=int):
            r = results[collision][re_key]
            re = int(r["Re"])
            col = re_colour[re]
            ls = coll_style.get(collision, "-")
            lbl = f"{coll_label.get(collision, collision)}, Re={re}"

            axes[0].plot(r["y_pos"], r["u_norm"], ls,
                         color=col, linewidth=1.3, label=lbl)
            axes[1].plot(r["x_pos"], r["v_norm"], ls,
                         color=col, linewidth=1.3)

            ghia_key = ("y", re)
            if ghia_key not in ghia_drawn:
                axes[0].plot(r["ghia_y"], r["ghia_u"], "o",
                             markerfacecolor="none",
                             markeredgecolor=col, markersize=5.5,
                             label=f"Ghia 1982, Re={re}")
                ghia_drawn.add(ghia_key)
            ghia_key = ("x", re)
            if ghia_key not in ghia_drawn:
                axes[1].plot(r["ghia_x"], r["ghia_v"], "o",
                             markerfacecolor="none",
                             markeredgecolor=col, markersize=5.5)
                ghia_drawn.add(ghia_key)

            l2_table[(re, collision)] = (
                float(r["l2_rel_u_vs_ghia"]),
                float(r["l2_rel_v_vs_ghia"]))

    axes[0].set_xlabel(r"$y\,/\,L$")
    axes[0].set_ylabel(r"$u\,/\,U_\text{lid}$")
    axes[0].set_title("u along x = L/2", fontsize=10)
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(fontsize=7, loc="upper left", ncol=1, frameon=True)

    axes[1].set_xlabel(r"$x\,/\,L$")
    axes[1].set_ylabel(r"$v\,/\,U_\text{lid}$")
    axes[1].set_title("v along y = L/2", fontsize=10)
    axes[1].grid(True, alpha=0.3)

    fig.suptitle(
        "Lid-driven cavity — GeLB vs Ghia, Ghia & Shin (1982)",
        fontsize=11)

    # Build a compact, multi-line caption: one line per Re, listing
    # L2 errors per collision in a fixed order.
    caption_lines: list[str] = []
    res_in_table = sorted({re for (re, _c) in l2_table})
    coll_order = [c for c in ["bgk", "mrt", "incomp_zou", "trt"]
                  if any(c == cc for (_, cc) in l2_table)]
    for re in res_in_table:
        bits = []
        for cl in coll_order:
            if (re, cl) in l2_table:
                lu, lv = l2_table[(re, cl)]
                bits.append(
                    f"{coll_label.get(cl, cl)}: "
                    f"L₂(u)={lu*100:.1f}%, L₂(v)={lv*100:.1f}%")
        caption_lines.append(f"Re={re}   " + "    ".join(bits))
    fig.text(0.5, -0.04, "\n".join(caption_lines), ha="center",
             va="top", fontsize=8.5, color="#222222",
             family="monospace")

    fig.tight_layout()
    fig.savefig(out_dir / "07_ldc_ghia_validation.png",
                dpi=_DPI, bbox_inches="tight")
    plt.close(fig)


def _render_07_cavity_streamlines(out_dir: pathlib.Path) -> None:
    """Chapter 7: lid-driven cavity -- streamlines + velocity magnitude.

    Runs the Re = 1000 lid-driven cavity example (Re = 980 with the
    walls midway, L = N - 2) at its default resolution (100x100) but with a reduced time
    budget (~8000 steps) to keep figure regeneration fast.  The
    flow has not quite reached full steady state at that horizon
    but the primary vortex and the two lower-corner counter-rotating
    vortices are already clearly visible, which is the point of the
    figure.

    Two-panel figure: (a) velocity-magnitude heatmap with
    overlaid streamlines, (b) the same but showing only the
    streamlines against a white background -- the "pure topology"
    view.
    """
    import matplotlib.pyplot as plt
    import numpy as np
    import netCDF4

    example = _EXAMPLES_DIR / "lbm" / "2d" / "lid_driven_cavity_2d_bgk_re1000.gelb"
    num_timesteps = 8000
    write_every = 8000   # only need the final snapshot
    nc_path = _compile_and_run(
        example, num_timesteps=num_timesteps, write_every=write_every)
    try:
        ds = netCDF4.Dataset(nc_path)
        ux = np.asarray(ds.variables["ux"][-1])   # shape (Ny, Nx)
        uy = np.asarray(ds.variables["uy"][-1])
        ds.close()
    finally:
        shutil.rmtree(nc_path.parent, ignore_errors=True)

    Ny, Nx = ux.shape
    x = np.arange(Nx)
    y = np.arange(Ny)
    speed = np.sqrt(ux ** 2 + uy ** 2)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), dpi=_DPI)

    # Panel A: velocity magnitude heatmap + streamlines
    im = axes[0].imshow(
        speed, origin="lower", cmap="viridis",
        extent=[0, Nx - 1, 0, Ny - 1],
        vmin=0, vmax=np.max(speed))
    axes[0].streamplot(
        x, y, ux, uy,
        density=1.3, color="white", linewidth=0.8,
        arrowsize=0.8)
    axes[0].set_title(r"Velocity magnitude $|\mathbf{u}|$ + streamlines",
                      fontsize=10)
    axes[0].set_xlabel("cell index $x$")
    axes[0].set_ylabel("cell index $y$")
    axes[0].set_aspect("equal")
    cbar = fig.colorbar(im, ax=axes[0], shrink=0.85)
    cbar.set_label(r"$|\mathbf{u}|$  (lattice units)", fontsize=9)

    # Panel B: streamlines only, with the lid and walls marked
    axes[1].streamplot(
        x, y, ux, uy,
        density=1.6, color=speed, cmap="plasma",
        linewidth=1.0, arrowsize=0.9)
    # Mark the boundaries -- horizontal lid on top, walls on the other three sides
    axes[1].plot([0, Nx - 1], [Ny - 1, Ny - 1], "r-", linewidth=2.5,
                 label="moving lid")
    axes[1].plot([0, Nx - 1], [0, 0], "k-", linewidth=2.0, label="no-slip walls")
    axes[1].plot([0, 0], [0, Ny - 1], "k-", linewidth=2.0)
    axes[1].plot([Nx - 1, Nx - 1], [0, Ny - 1], "k-", linewidth=2.0)
    axes[1].set_title("Streamlines only (coloured by $|\\mathbf{u}|$)",
                      fontsize=10)
    axes[1].set_xlabel("cell index $x$")
    axes[1].set_ylabel("cell index $y$")
    axes[1].set_xlim(-1, Nx)
    axes[1].set_ylim(-1, Ny)
    axes[1].set_aspect("equal")
    axes[1].legend(fontsize=8, loc="lower left",
                   framealpha=0.9)

    fig.suptitle(
        r"Lid-driven cavity at $\mathrm{Re} = 980$ — D2Q9 BGK, "
        rf"$U_\mathrm{{lid}} = 0.1$, $\tau = 0.53$, "
        rf"$t = {num_timesteps}$",
        fontsize=11)
    fig.tight_layout()
    fig.savefig(out_dir / "07_cavity_streamlines.png",
                dpi=_DPI, bbox_inches="tight")
    plt.close(fig)


def _render_05_heat_diffusion_profile(out_dir: pathlib.Path) -> None:
    """Chapter 5: 1D heat diffusion -- T(x) profile at several times.

    Compiles and runs ``heat_diffusion_1d_dirichlet.gelb`` for a
    range of time steps from early transient through near-steady-
    state.  The static equilibrium walls impose their temperature
    ``1 - tau`` cells from the wall cell, towards the bulk, so the
    steady state is the straight line from ``T = 1`` at
    ``x = 1 - tau`` to ``T = 0`` at ``x = N - 2 + tau``; the bulk
    cells follow it to round-off.  We overlay that line as a dashed
    reference so the reader can see the simulation converge onto it.

    Two-panel figure: (a) superimposed T(x) profiles at several
    time slices, (b) convergence of the L2 error over the bulk
    cells against that steady state.
    """
    import matplotlib.pyplot as plt
    import numpy as np
    import netCDF4

    example = _EXAMPLES_DIR / "lbm" / "1d" / "heat_diffusion_1d_dirichlet.gelb"
    num_timesteps = 10000
    write_every = 100
    nc_path = _compile_and_run(
        example, num_timesteps=num_timesteps, write_every=write_every)
    try:
        ds = netCDF4.Dataset(nc_path)
        temp = np.asarray(ds.variables["temperature"][:])  # (T+1, N)
        ds.close()
    finally:
        shutil.rmtree(nc_path.parent, ignore_errors=True)

    N = temp.shape[1]
    x = np.arange(N)

    # Steady state: T = 1 at the effective left wall x = 1 - tau and
    # T = 0 at the effective right wall x = N - 2 + tau (the static
    # wall cells sit at 0 and N - 1).  tau is the example's constant.
    tau = 0.75
    x_left, x_right = 1.0 - tau, N - 2 + tau

    def T_steady(xx):
        return 1.0 - (xx - x_left) / (x_right - x_left)

    bulk = slice(1, N - 1)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), dpi=_DPI)

    # Panel A: a selection of time slices converging toward the analytical solution
    selected_records = [0, 1, 2, 5, 10, 20, 50, temp.shape[0] - 1]
    cmap = plt.get_cmap("plasma")
    for rank, rec_idx in enumerate(selected_records):
        if rec_idx >= temp.shape[0]:
            continue
        t_step = rec_idx * write_every if rec_idx > 0 else 0
        color = cmap(rank / max(1, len(selected_records) - 1))
        axes[0].plot(x, temp[rec_idx, :],
                     color=color, linewidth=1.3,
                     label=f"$t = {t_step}$")
    x_line = np.array([x_left, x_right])
    axes[0].plot(x_line, T_steady(x_line), "k--", linewidth=1.5,
                 label="steady state")
    axes[0].set_xlabel("cell index $x$")
    axes[0].set_ylabel("temperature $T$")
    axes[0].set_title("1D heat diffusion: $T(x)$ converging to the steady state",
                      fontsize=10)
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(fontsize=7, ncol=2, loc="upper right")

    # Panel B: L2 error of the bulk cells vs the steady state, over time
    l2_err = np.sqrt(np.mean(
        (temp[:, bulk] - T_steady(x[bulk])[None, :]) ** 2, axis=1))
    times = np.arange(temp.shape[0]) * write_every
    # Skip t=0 (initial condition is 1.0 everywhere -> large error)
    axes[1].semilogy(times[1:], l2_err[1:], "C0-", linewidth=1.5)
    axes[1].set_xlabel("time step $t$")
    axes[1].set_ylabel("$L_2$ error vs steady state (bulk cells)")
    axes[1].set_title("Convergence to steady state", fontsize=10)
    axes[1].grid(True, which="both", alpha=0.3)

    fig.suptitle(
        "heat_diffusion_1d_dirichlet.gelb — D1Q3 BGK diffusion, "
        r"$T_\mathrm{left}=1$, $T_\mathrm{right}=0$, " + rf"$\tau = {tau}$",
        fontsize=11)
    fig.tight_layout()
    fig.savefig(out_dir / "05_heat_diffusion_profile.png",
                dpi=_DPI, bbox_inches="tight")
    plt.close(fig)


def _render_05_setup_sketch(out_dir: pathlib.Path) -> None:
    """Chapter 5: schematic of a 1D bar in vacuum between two reservoirs."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, Rectangle
    import numpy as np

    # Drawn at the size it is shown (a third of the text width), so the
    # labels print at about 7 pt; twice the DPI keeps the same pixel
    # density as the full-width figures.
    fig, ax = plt.subplots(figsize=(2.3, 0.95), dpi=2 * _DPI)

    # Bar gradient from hot (left) to cold (right)
    grad = np.linspace(1.0, 0.0, 256).reshape(1, -1)
    ax.imshow(
        grad, extent=[0.0, 1.0, 0.32, 0.68],
        cmap="coolwarm", vmin=0.0, vmax=1.0,
        aspect="auto", alpha=0.65, zorder=1)
    ax.add_patch(Rectangle(
        (0.0, 0.32), 1.0, 0.36,
        facecolor="none", edgecolor="#222222", linewidth=0.8, zorder=3))

    # Left (hot) and right (cold) reservoirs
    ax.add_patch(Rectangle(
        (-0.24, 0.14), 0.24, 0.72,
        facecolor="#f4a582", edgecolor="#b2182b", linewidth=0.9, zorder=3))
    ax.text(-0.12, 0.50, "Hot\n" + r"$T_\mathrm{left}$",
            ha="center", va="center", fontsize=7, color="#67001f",
            weight="bold", zorder=4)

    ax.add_patch(Rectangle(
        (1.00, 0.14), 0.24, 0.72,
        facecolor="#92c5de", edgecolor="#2166ac", linewidth=0.9, zorder=3))
    ax.text(1.12, 0.50, "Cold\n" + r"$T_\mathrm{right}$",
            ha="center", va="center", fontsize=7, color="#053061",
            weight="bold", zorder=4)

    # Heat-flow arrow inside the bar
    arrow = FancyArrowPatch(
        (0.18, 0.50), (0.82, 0.50),
        arrowstyle="->,head_width=2.5,head_length=3.5",
        color="#222222", linewidth=0.8, zorder=4)
    ax.add_patch(arrow)
    ax.text(0.50, 0.53, r"heat flow  ($\alpha$)",
            ha="center", va="bottom", fontsize=7, color="#111111", zorder=4)

    # Vacuum / lateral insulation note
    ax.text(0.50, 0.76, "vacuum (no lateral heat loss)",
            ha="center", va="bottom", fontsize=6, color="#555555",
            style="italic")

    # x-axis ticks below the bar
    ax.plot([0.0, 1.0], [0.16, 0.16], color="#333333", linewidth=0.6)
    for xv, lbl in [(0.0, "$x = 0$"), (1.0, "$x = L$")]:
        ax.plot([xv, xv], [0.13, 0.19], color="#333333", linewidth=0.6)
        ax.text(xv, 0.09, lbl, ha="center", va="top", fontsize=7, color="#222222")

    ax.set_xlim(-0.28, 1.28)
    ax.set_ylim(-0.04, 0.94)
    ax.axis("off")

    fig.tight_layout(pad=0.2)
    fig.savefig(out_dir / "05_setup_sketch.png",
                dpi=2 * _DPI, bbox_inches="tight")
    plt.close(fig)


def _render_04_hello_world_spacetime(out_dir: pathlib.Path) -> None:
    """Chapter 4: Hello World -- space-time heatmap of the integer lattice.

    Compiles and runs ``ex0_int_vec_setto_one.gelb`` for 10 timesteps.
    The output NetCDF contains a (T+1, 32) array of integers where
    the first row is the t=0 pre-loop snapshot (all zeros) and rows
    1..10 are the post-dynamic snapshots (all ones).  We render a
    2-column subplot: (a) the single-row initial state as a tiny
    horizontal strip, and (b) the full space-time heatmap.  The
    figure teaches readers what a gelb-view data dump actually
    contains and how the t=0 pre-loop pass works.
    """
    import matplotlib.pyplot as plt
    import numpy as np
    import netCDF4

    example = _EXAMPLES_DIR / "basic" / "1d" / "ex0_int_vec_setto_one.gelb"
    nc_path = _compile_and_run(example, num_timesteps=10, write_every=1)
    try:
        ds = netCDF4.Dataset(nc_path)
        state = np.asarray(ds.variables["state"][:])  # shape (T+1, 32)
        ds.close()
    finally:
        shutil.rmtree(nc_path.parent, ignore_errors=True)

    fig, axes = plt.subplots(
        1, 2, figsize=(8, 3.2),
        gridspec_kw={"width_ratios": [1, 4]}, dpi=_DPI)

    # Left: the t=0 initial state as a thin row
    axes[0].imshow(
        state[0:1, :], cmap="viridis", vmin=0, vmax=1,
        aspect="auto", interpolation="nearest")
    axes[0].set_title("$t = 0$ (initial)", fontsize=10)
    axes[0].set_xlabel("cell index $x$")
    axes[0].set_yticks([])
    axes[0].set_xticks([0, 15, 31])

    # Right: full space-time heatmap
    im = axes[1].imshow(
        state, cmap="viridis", vmin=0, vmax=1,
        aspect="auto", interpolation="nearest", origin="lower")
    axes[1].set_title("Full space-time evolution", fontsize=10)
    axes[1].set_xlabel("cell index $x$")
    axes[1].set_ylabel("time step $t$")
    axes[1].set_xticks([0, 15, 31])
    axes[1].set_yticks(list(range(0, state.shape[0], 2)))

    cbar = fig.colorbar(im, ax=axes[1], ticks=[0, 1], shrink=0.85)
    cbar.set_label("state", rotation=0, labelpad=18, fontsize=9)

    fig.suptitle(
        "Hello World: ex0_int_vec_setto_one.gelb — 32-cell 1D integer lattice",
        fontsize=11, y=1.02)
    fig.tight_layout()
    fig.savefig(out_dir / "04_hello_world_spacetime.png",
                dpi=_DPI, bbox_inches="tight")
    plt.close(fig)


def _render_geometry(out_dir: pathlib.Path, example: pathlib.Path,
                     out_name: str, title: str | None = None) -> None:
    """Generic geometry figure renderer using gelb-view geo."""
    from gelb.visualization.geo_viewer import compile_to_geometry, plot_geometry
    geo = compile_to_geometry(str(example))
    plot_geometry(geo, output=str(out_dir / out_name),
                  dpi=_DPI, title=title)


def _render_10_geometry(out_dir: pathlib.Path) -> None:
    """Karman geometry: full grid + zoomed cylinder inset."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    from gelb.visualization.geo_viewer import compile_to_geometry

    geo = compile_to_geometry(str(
        _EXAMPLES_DIR / "sukop" / "karman_vortex_street_2d_bgk.gelb"))

    colors = ['#66c2a5', '#fc8d62', '#8da0cb']
    cmap = ListedColormap(colors)
    norm = BoundaryNorm([1, 2, 3, 4], cmap.N)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3), dpi=_DPI,
                                    gridspec_kw={'width_ratios': [2, 1]})

    # Full grid
    ax1.imshow(geo.nc_map.T, origin='lower', cmap=cmap, norm=norm,
               aspect='equal', interpolation='nearest')
    ax1.set_xlabel('$x$', fontsize=8)
    ax1.set_ylabel('$y$', fontsize=8)
    ax1.set_title('Full domain', fontsize=9)

    # Zoomed cylinder region
    cx, cy, r = 300, 99, 20
    pad = 8
    region = geo.nc_map[cx - r - pad:cx + r + pad,
                        cy - r - pad:cy + r + pad]
    ax2.imshow(region.T, origin='lower', cmap=cmap, norm=norm,
               aspect='equal', interpolation='nearest')
    ax2.set_title('Zoomed: obstacle', fontsize=9)
    ax2.set_xlabel('$x$', fontsize=8)

    patches = [
        Patch(facecolor=colors[0], label='FLUID', edgecolor='#555', lw=0.5),
        Patch(facecolor=colors[1], label='WALL', edgecolor='#555', lw=0.5),
        Patch(facecolor=colors[2], label='SOLID (masked)',
              edgecolor='#555', lw=0.5, hatch='///'),
    ]
    ax2.legend(handles=patches, loc='upper right', fontsize=7,
               framealpha=0.85)

    fig.suptitle('Kármán vortex street — node classes', fontsize=10)
    fig.tight_layout()
    fig.savefig(out_dir / "10_geometry.png", dpi=_DPI, bbox_inches='tight')
    plt.close(fig)


def _render_13_geometry(out_dir: pathlib.Path) -> None:
    """Salmon ocean basin geometry, with the 9-class legend outside the axes so it does not cover the basin."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    from gelb.visualization.geo_viewer import (
        _MASKED_HATCH,
        _NC_COLORS,
        compile_to_geometry,
    )

    geo = compile_to_geometry(str(
        _EXAMPLES_DIR / "lbm" / "2d" / "reduced_gravity_2d_sw_d2q9.gelb"))

    n_nc = len(geo.nc_order)
    colors = [_NC_COLORS[i % len(_NC_COLORS)] for i in range(n_nc)]
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(list(range(1, n_nc + 2)), cmap.N)

    fig, ax = plt.subplots(figsize=(5.2, 2.8), dpi=_DPI)
    ax.imshow(geo.nc_map.T, origin="lower", cmap=cmap, norm=norm,
              aspect="equal", interpolation="nearest")
    ax.set_xlabel("$x$", fontsize=9)
    ax.set_ylabel("$y$", fontsize=9)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.tick_params(labelsize=8)
    ax.set_title("Salmon ocean basin — node classes", fontsize=9.5, pad=6)

    patches = []
    for i, nc_name in enumerate(geo.nc_order):
        info = geo.nc_info[nc_name]
        label = f"{nc_name} (masked)" if info.masked else nc_name
        p = Patch(facecolor=colors[i], label=label,
                  edgecolor="#555555", linewidth=0.5)
        if info.masked:
            p.set_hatch(_MASKED_HATCH)
        patches.append(p)

    ax.legend(handles=patches, loc="center left",
              bbox_to_anchor=(1.04, 0.5), fontsize=7.5,
              framealpha=0.9, handlelength=1.2, handleheight=0.85)

    fig.tight_layout()
    fig.savefig(out_dir / "13_geometry.png", dpi=_DPI, bbox_inches="tight")
    plt.close(fig)


_FIGURES: list[FigureSpec] = [
    FigureSpec(
        name="04_hello_world_spacetime.png",
        source_example=_EXAMPLES_DIR / "basic" / "1d"
                        / "ex0_int_vec_setto_one.gelb",
        render=_render_04_hello_world_spacetime,
    ),
    FigureSpec(
        name="05_setup_sketch.png",
        source_example=None,
        render=lambda out_dir: _render_05_setup_sketch(out_dir),
    ),
    FigureSpec(
        name="05_heat_diffusion_profile.png",
        source_example=_EXAMPLES_DIR / "lbm" / "1d"
                        / "heat_diffusion_1d_dirichlet.gelb",
        render=lambda out_dir: _render_05_heat_diffusion_profile(out_dir),
    ),
    FigureSpec(
        name="07_cavity_streamlines.png",
        source_example=_EXAMPLES_DIR / "lbm" / "2d"
                        / "lid_driven_cavity_2d_bgk_re1000.gelb",
        render=lambda out_dir: _render_07_cavity_streamlines(out_dir),
    ),
    FigureSpec(
        name="07_ldc_ghia_validation.png",
        source_example=None,  # synthesised from validate_ldc.py runs
        render=lambda out_dir: _render_07_ldc_ghia_validation(out_dir),
        extra_deps=[_FIGURES_DIR / "data"
                    / "07_ldc_ghia_validation.json"],
    ),
    FigureSpec(
        name="08_poiseuille_convergence.png",
        source_example=_EXAMPLES_DIR / "lbm" / "2d"
                        / "poiseuille_flow_2d_mrt.gelb",
        render=lambda out_dir: _render_08_poiseuille_convergence(out_dir),
    ),
    FigureSpec(
        name="09_rb_temperature_rolls.png",
        source_example=_EXAMPLES_DIR / "lbm" / "2d"
                        / "rayleigh_benard_2d_mrt.gelb",
        render=lambda out_dir: _render_09_rb_temperature_rolls(out_dir),
    ),
    FigureSpec(
        name="10_karman_vorticity.png",
        source_example=_EXAMPLES_DIR / "sukop"
                        / "karman_vortex_street_2d_bgk.gelb",
        render=lambda out_dir: _render_10_karman_vorticity(out_dir),
    ),
    FigureSpec(
        name="11_shanchen_phase_separation.png",
        source_example=_EXAMPLES_DIR / "sukop" / "shan_chen_2d.gelb",
        render=lambda out_dir: _render_11_shanchen_phase_separation(out_dir),
    ),
    FigureSpec(
        name="12_gol_glider.png",
        source_example=_EXAMPLES_DIR / "lgca" / "2d"
                        / "game_of_life_glider.gelb",
        render=lambda out_dir: _render_12_gol_glider(out_dir),
    ),
    FigureSpec(
        name="13_salmon_gyre.png",
        source_example=_EXAMPLES_DIR / "lbm" / "2d"
                        / "reduced_gravity_2d_sw_d2q9.gelb",
        render=lambda out_dir: _render_13_salmon_gyre(out_dir),
    ),
    # --- Geometry figures ---
    FigureSpec(
        name="05_geometry.png",
        source_example=_EXAMPLES_DIR / "lbm" / "1d"
                        / "heat_diffusion_1d_dirichlet.gelb",
        render=lambda out_dir: _render_geometry(
            out_dir,
            _EXAMPLES_DIR / "lbm" / "1d" / "heat_diffusion_1d_dirichlet.gelb",
            "05_geometry.png", "1D heat diffusion — node classes"),
    ),
    FigureSpec(
        name="07_geometry.png",
        source_example=_EXAMPLES_DIR / "lbm" / "2d"
                        / "lid_driven_cavity_2d_bgk_re1000.gelb",
        render=lambda out_dir: _render_geometry(
            out_dir,
            _EXAMPLES_DIR / "lbm" / "2d" / "lid_driven_cavity_2d_bgk_re1000.gelb",
            "07_geometry.png", "Lid-driven cavity — node classes"),
    ),
    FigureSpec(
        name="09_geometry.png",
        source_example=_EXAMPLES_DIR / "lbm" / "2d"
                        / "rayleigh_benard_2d_mrt.gelb",
        render=lambda out_dir: _render_geometry(
            out_dir,
            _EXAMPLES_DIR / "lbm" / "2d" / "rayleigh_benard_2d_mrt.gelb",
            "09_geometry.png", "Rayleigh-Bénard — node classes"),
    ),
    FigureSpec(
        name="10_geometry.png",
        source_example=_EXAMPLES_DIR / "sukop"
                        / "karman_vortex_street_2d_bgk.gelb",
        render=lambda out_dir: _render_10_geometry(out_dir),
    ),
    FigureSpec(
        name="13_geometry.png",
        source_example=_EXAMPLES_DIR / "lbm" / "2d"
                        / "reduced_gravity_2d_sw_d2q9.gelb",
        render=lambda out_dir: _render_13_geometry(out_dir),
    ),
    FigureSpec(
        name="15_stencil_bgk_d2q9.svg",
        source_example=_EXAMPLES_DIR / "lbm" / "2d"
                        / "lid_driven_cavity_2d_bgk_re1000.gelb",
        render=_not_yet_implemented("15_stencil_bgk_d2q9"),
    ),
    FigureSpec(
        name="16_mlups_backend_comparison.png",
        source_example=None,  # synthesised from benchmark runs, not one example
        render=lambda out_dir: _render_16_mlups_backend_comparison(out_dir),
        extra_deps=[_FIGURES_DIR / "data"
                    / "16_mlups_backend_comparison.json"],
    ),
    FigureSpec(
        name="17_rb_onset_validation.png",
        source_example=None,  # synthesised from RB onset sweep, not one example
        render=lambda out_dir: _render_17_rb_onset_validation(out_dir),
        extra_deps=[_FIGURES_DIR / "data"
                    / "17_rb_onset_validation.json"],
    ),
]


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def _current_git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(_REPO_ROOT),
            text=True).strip()[:12]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _write_manifest(results: list[tuple[str, str]]) -> None:
    """Write ``MANIFEST.txt`` into the figures dir.

    ``results`` is a list of ``(figure_name, status)`` tuples where
    ``status`` is one of ``"generated"``, ``"cached"``, or ``"skipped:...".
    """
    sha = _current_git_sha()
    lines = [
        "GeLB User Tutorial — Figure Manifest",
        "=====================================",
        "",
        f"Regenerated at: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"Git HEAD:       {sha}",
        "",
        "Per-figure status:",
        "",
    ]
    for name, status in results:
        lines.append(f"  {name:45s}  {status}")
    lines.append("")
    lines.append(
        textwrap.dedent(
            """\
            Regenerate from scratch with:
                rm docs/user/figures/*.png docs/user/figures/*.gif \\
                   docs/user/figures/*.svg
                python scripts/gen_tutorial_figures.py
                node scripts/gen_vscode_screenshots.mjs   # vscode_*.png
            """
        ).strip()
    )
    manifest = _FIGURES_DIR / "MANIFEST.txt"
    manifest.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Regenerate GeLB user tutorial figures.")
    ap.add_argument(
        "--force", action="store_true",
        help="Regenerate even cached figures (ignore mtime cache).")
    ap.add_argument(
        "--chapters", type=str, default=None,
        help="Comma-separated chapter numbers to regenerate "
             "(e.g. '05,08,11').  Default: all.")
    ap.add_argument(
        "--cuda", action="store_true",
        help="Include the CUDA column in the performance comparison "
             "figure.  Requires nvcc on $PATH.")
    ap.add_argument(
        "--dpi", type=int, default=150,
        help="DPI for rasterised figures (default: 150).  Use 300 for "
             "publication quality.")
    args = ap.parse_args(argv)

    global _DPI
    _DPI = args.dpi

    if not _FIGURES_DIR.is_dir():
        _FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    chapter_filter: set[str] | None = None
    if args.chapters:
        chapter_filter = {c.strip().zfill(2) for c in args.chapters.split(",")}

    script_path = pathlib.Path(__file__).resolve()
    results: list[tuple[str, str]] = []

    for fig in _FIGURES:
        chapter = fig.name.split("_", 1)[0]
        if chapter_filter is not None and chapter not in chapter_filter:
            results.append((fig.name, "skipped: --chapters filter"))
            continue

        # Skip the CUDA-dependent figure if nvcc is missing.
        if fig.name == "15_mlups_backend_comparison.png" and args.cuda \
                and _NVCC is None:
            results.append((fig.name, "skipped: nvcc not found"))
            continue

        if not args.force and not fig.is_stale(_FIGURES_DIR, script_path):
            results.append((fig.name, "cached"))
            continue

        print(f"  rendering {fig.name} ...", flush=True)
        try:
            fig.render(_FIGURES_DIR)
            results.append((fig.name, "generated"))
        except NotImplementedError as e:
            results.append((fig.name, f"stub: {e}"))
            print(f"    (stub — not yet implemented)", flush=True)
        except Exception as e:
            results.append((fig.name, f"FAILED: {e}"))
            print(f"    FAILED: {e}", file=sys.stderr, flush=True)

    _write_manifest(results)

    print()
    print(f"Wrote manifest: {_FIGURES_DIR / 'MANIFEST.txt'}")
    failed = [r for r in results if r[1].startswith("FAILED")]
    stubs = [r for r in results if r[1].startswith("stub")]
    generated = [r for r in results if r[1] == "generated"]
    cached = [r for r in results if r[1] == "cached"]
    print(f"  generated: {len(generated)}")
    print(f"  cached:    {len(cached)}")
    print(f"  stubs:     {len(stubs)}")
    print(f"  failed:    {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
