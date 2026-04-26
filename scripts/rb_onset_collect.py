#!/usr/bin/env python3
"""Collect Rayleigh-Benard onset sweep results into a committable JSON.

Takes a directory of NetCDF files produced by
``scripts/find_ra_critical.py`` (one file per Ra value, named
``rb_ra_<ra>.nc``), extracts the time series of ``max_{x,y}|u_y|``
for each Ra, and writes the summary to a small JSON artifact that
the Chapter 17 figure renderer consumes.

The NetCDFs themselves are multi-hundred-MB each; the JSON is a few
dozen KB -- small enough to commit and reproducibly reuse without
re-running the 3.5-hour sweep.

Usage
-----
    # After a sweep completes:
    uv run python scripts/rb_onset_collect.py

Or with explicit paths:
    uv run python scripts/rb_onset_collect.py \\
        --in-dir rb_sweep_results_2d \\
        --out docs/user/figures/data/17_rb_onset_validation.json
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np

from bench_common import (
    collect_run_metadata,
    display_path,
    write_json_artifact,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IN_DIR = REPO_ROOT / "rb_sweep_results_2d"
DEFAULT_OUT = (REPO_ROOT / "docs" / "user" / "figures" / "data"
               / "17_rb_onset_validation.json")

SCHEMA_VERSION = 1

# Defaults from the RB-MRT example + find_ra_critical.py.
DEFAULT_DECAY_THR = 2e-4
DEFAULT_GROW_THR = 5e-4
RA_C_THEORY = 1707.76  # Shan 1997, rigid-rigid walls

_RA_FILENAME_RE = re.compile(r"^rb_ra_([0-9]+(?:\.[0-9]+)?)\.nc$")


def _extract_max_uy_series(
        nc_path: Path) -> tuple[list[float], list[float], int]:
    """Return (time_series, max_abs_uy_series, spatial_dim) from an rb
    sweep NetCDF."""
    import netCDF4  # local import -- not needed if no NCs present

    with netCDF4.Dataset(nc_path) as ds:
        if "uY" not in ds.variables:
            raise KeyError(
                f"{nc_path} has no 'uY' variable (found {list(ds.variables)})")
        uY = np.asarray(ds.variables["uY"][:])
        time = np.asarray(ds.variables["time"][:]).astype(int)
    # uY has NaNs on wall rows (masked node classes).  nanmax collapses
    # over all spatial dims regardless of ndim.
    spatial_axes = tuple(range(1, uY.ndim))
    max_uy = np.nanmax(np.abs(uY), axis=spatial_axes)
    return time.tolist(), max_uy.tolist(), uY.ndim - 1


def _ra_from_filename(name: str) -> float | None:
    match = _RA_FILENAME_RE.match(name)
    if match is None:
        return None
    return float(match.group(1))


def _bracket(curves: dict[float, list[float]],
             decay_thr: float, grow_thr: float
             ) -> tuple[float | None, float | None]:
    """Return (largest Ra still decaying, smallest Ra already growing)."""
    decaying_max: float | None = None
    growing_min: float | None = None
    for ra in sorted(curves.keys()):
        final = curves[ra][-1] if curves[ra] else float("nan")
        if final < decay_thr:
            decaying_max = ra if decaying_max is None else max(decaying_max, ra)
        elif final > grow_thr:
            growing_min = ra if growing_min is None else min(growing_min, ra)
    return decaying_max, growing_min


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect RB onset sweep results into a JSON artifact.")
    parser.add_argument(
        "--in-dir", type=Path, default=DEFAULT_IN_DIR,
        help=f"Directory containing rb_ra_*.nc "
             f"(default {DEFAULT_IN_DIR.relative_to(REPO_ROOT)}).")
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"JSON artifact path "
             f"(default {DEFAULT_OUT.relative_to(REPO_ROOT)}).")
    parser.add_argument(
        "--decay-threshold", type=float, default=DEFAULT_DECAY_THR,
        help="uY_inf below this at t_end → decaying (default %(default)s).")
    parser.add_argument(
        "--grow-threshold", type=float, default=DEFAULT_GROW_THR,
        help="uY_inf above this at t_end → growing (default %(default)s).")
    parser.add_argument(
        "--ny", type=int, default=43,
        help="RB grid rows, for metadata (default %(default)s).")
    parser.add_argument(
        "--nx", type=int, default=83,
        help="RB grid columns, for metadata (default %(default)s).")
    parser.add_argument(
        "--pr", type=float, default=0.71,
        help="Prandtl number, for metadata (default %(default)s).")
    parser.add_argument(
        "--max-mach", type=float, default=0.1,
        help="Mach number budget, for metadata (default %(default)s).")
    args = parser.parse_args()

    if not args.in_dir.exists():
        raise SystemExit(f"Input directory {args.in_dir} not found. "
                         f"Run scripts/find_ra_critical.py first.")

    nc_files = sorted(args.in_dir.glob("rb_ra_*.nc"))
    if not nc_files:
        raise SystemExit(f"No rb_ra_*.nc files found in {args.in_dir}.")

    curves: dict[float, dict] = {}
    dimension = 2
    for nc_path in nc_files:
        ra = _ra_from_filename(nc_path.name)
        if ra is None:
            print(f"  skipping (unexpected name): {nc_path.name}")
            continue
        print(f"  reading {nc_path.name}  (Ra = {ra})")
        time_series, max_uy, dimension = _extract_max_uy_series(nc_path)
        curves[ra] = {"time": time_series, "max_uy": max_uy}

    # Derive the bracket from the loaded curves.
    decaying_max, growing_min = _bracket(
        {ra: c["max_uy"] for ra, c in curves.items()},
        args.decay_threshold, args.grow_threshold)

    # Write JSON.  Use string Ra keys (json.dump doesn't like float keys)
    # but in insertion/sort order so the renderer sees them ascending.
    curves_out = {f"{ra:g}": curves[ra]
                  for ra in sorted(curves.keys())}

    metadata = collect_run_metadata(REPO_ROOT)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "dimension": dimension,
        "ny": args.ny,
        "nx": args.nx,
        "pr": args.pr,
        "max_mach": args.max_mach,
        "decay_threshold": args.decay_threshold,
        "grow_threshold": args.grow_threshold,
        "ra_c_theory": RA_C_THEORY,
        "bracket": {
            "decaying_max": decaying_max,
            "growing_min": growing_min,
        },
        "curves": curves_out,
        **metadata.as_result_fields(),
    }

    write_json_artifact(args.out, doc)
    rel = display_path(args.out, REPO_ROOT)
    print(f"\nBracket: decaying ≤ {decaying_max}, growing ≥ {growing_min}  "
          f"(theory Ra_c ≈ {RA_C_THEORY})")
    print(f"Wrote: {rel}  ({len(curves_out)} curves)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
