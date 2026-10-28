#!/usr/bin/env python3
"""Lid-driven cavity validation against Ghia, Ghia & Shin (1982).

Compiles and runs ``examples/lbm/2d/lid_driven_cavity_2d_bgk.gelb``
at one or more Reynolds numbers, extracts the centerline velocity
profiles from the final NetCDF, interpolates onto Ghia's
non-uniform 17-point sampling, and reports relative L2 errors.

Also exports a compact JSON artifact at
``docs/user/figures/data/07_ldc_ghia_validation.json`` so the
Chapter 7 figure can be rendered later by
``scripts/gen_tutorial_figures.py --chapters 07`` without
re-running the simulations.

Usage
-----
    uv run python scripts/validate_ldc.py
    uv run python scripts/validate_ldc.py --re 100
    uv run python scripts/validate_ldc.py --re 100 1000 --n 129

The default grid is N=129 (Ghia's coarse multigrid grid).  At
Re=1000 this drives tau close to the stability limit (~0.54);
``--n 257`` gives more margin at the cost of longer wall time.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

from bench_common import machine_tag

REPO_ROOT = Path(__file__).resolve().parent.parent
GELB_RUN = REPO_ROOT / "scripts" / "gelb-run"
EXAMPLES = {
    "bgk": REPO_ROOT / "examples" / "lbm" / "2d" / "lid_driven_cavity_2d_bgk.gelb",
    "mrt": REPO_ROOT / "examples" / "lbm" / "2d" / "lid_driven_cavity_2d_mrt.gelb",
    "incomp_zou": REPO_ROOT / "examples" / "lbm" / "2d"
                  / "lid_driven_cavity_2d_incomp_zou.gelb",
}
DEFAULT_OUT = (REPO_ROOT / "docs" / "user" / "figures" / "data"
               / "07_ldc_ghia_validation.json")

DEFAULT_RES = [100, 1000]   # match Ghia data module + Guo Sec. 4.2 demos
DEFAULT_N = 129             # Ghia coarse-grid sampling
DEFAULT_U_LID = 0.1         # standard low-Mach lid speed
DEFAULT_COLLISION = "bgk"

SCHEMA_VERSION = 2          # v2: nests results under collision operator


def _compute_tau(re: float, n: int, u_lid: float) -> float:
    """tau from Re = u_lid * (n-2) / nu and nu = (tau - 0.5) / 3.

    Fluid cells occupy indices 1 through n-2. Half-way bounce-back
    places the walls at 0.5 and n-1.5, a distance n-2 apart; use the
    same length here and when sampling the centerlines.
    """
    nu = u_lid * (n - 2) / re
    return 3.0 * nu + 0.5


def _run_one(re: float, n: int, u_lid: float, num_steps: int,
             collision: str = DEFAULT_COLLISION,
             backend: str = "cpu_fortran_serial") -> dict | None:
    """Run the cavity example at the given Re/N/u_lid and return the
    last-timestep ``ux`` and ``uy`` fields (shape ``(N, N)``)."""
    if collision not in EXAMPLES:
        raise ValueError(f"Unknown collision {collision!r}; "
                         f"valid: {sorted(EXAMPLES)}")
    example = EXAMPLES[collision]
    tau = _compute_tau(re, n, u_lid)
    print(f"  [{collision}]  Re={re:5g}  N={n}  U_LID={u_lid}  τ={tau:.4f}  "
          f"steps={num_steps}")

    cmd = [str(GELB_RUN), "-b", backend,
           "-n", str(num_steps), "-w", str(num_steps),
           "-D", f"N={n}",
           "-D", f"U_LID={u_lid}",
           "-D", f"TAU={tau}",
           str(example)]

    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.stderr.write(f"[FAIL] {collision} Re={re}\n"
                         f"stderr:\n{proc.stderr[:500]}\n")
        return None

    nc_path = REPO_ROOT / f"{example.stem}.nc"
    if not nc_path.exists():
        sys.stderr.write(f"[FAIL] {collision} Re={re}: NetCDF not found\n")
        return None

    import netCDF4
    with netCDF4.Dataset(nc_path) as ds:
        ux = np.asarray(ds.variables["ux"][-1])  # shape (y, x)
        uy = np.asarray(ds.variables["uy"][-1])
        # Wall gauges prescribe rho=1. This is the fluid mass only;
        # full-way walls also hold reflected populations between steps.
        rho_initial = np.asarray(ds.variables["rho"][0])[1:-1, 1:-1]
        rho_final = np.asarray(ds.variables["rho"][-1])[1:-1, 1:-1]
        mass_initial = float(rho_initial.sum())
        mass_final = float(rho_final.sum())
    nc_path.unlink()  # tidy up -- the JSON keeps what we need

    if not all(np.isfinite(a).all() for a in (ux, uy, rho_final)):
        sys.stderr.write(f"[FAIL] {collision} Re={re}: non-finite fields\n")
        return None

    return {"tau": tau, "n": n, "u_lid": u_lid,
            "mass_initial": mass_initial, "mass_final": mass_final,
            "mass_rel_change": (mass_final - mass_initial) / mass_initial,
            "num_steps": num_steps, "collision": collision,
            "ux": ux, "uy": uy}


def _extract_centerlines(field: np.ndarray, axis_name: str,
                         u_lid: float) -> tuple[np.ndarray, np.ndarray]:
    """Return (positions in [0, 1], values normalised by u_lid).

    ``axis_name == 'y'`` returns u along the vertical centreline at
    x = (N-1)/2.  ``'x'`` returns v along the horizontal centreline
    at y = (N-1)/2.

    Cavity convention: link bounce-back walls sit *halfway*
    between the wall-cell and the first fluid cell, so the
    physical no-slip surfaces are at y_phys = 0.5 (bottom) and
    y_phys = N - 1.5 (top), giving an effective channel height
    H = N - 2. Drop the static boundary cells (indices 0 and N-1)
    from the sample and insert the prescribed velocities at the
    physical walls. For even N, average the two central grid lines
    to sample the geometric center rather than the lower grid line.
    """
    n = field.shape[0]   # field is square: (n, n)
    centre_lo, centre_hi = (n - 1) // 2, n // 2
    if axis_name == "y":
        fluid_line = (field[1:n - 1, centre_lo]
                      + field[1:n - 1, centre_hi]) / 2
    elif axis_name == "x":
        fluid_line = (field[centre_lo, 1:n - 1]
                      + field[centre_hi, 1:n - 1]) / 2
    else:
        raise ValueError(f"axis_name must be 'x' or 'y', got {axis_name!r}")

    # Map fluid cells to y/L using the half-way bounce-back convention.
    h = n - 2
    fluid_pos = (np.arange(1, n - 1) - 0.5) / h

    # Append the prescribed wall velocities at y/L=0 and y/L=1.
    if axis_name == "y":
        wall_lo, wall_hi = 0.0, u_lid     # bottom u=0; lid u=U_LID
    else:
        wall_lo, wall_hi = 0.0, 0.0       # both side walls v=0

    pos = np.concatenate([[0.0], fluid_pos, [1.0]])
    line = np.concatenate([[wall_lo], fluid_line, [wall_hi]])
    return pos, line / u_lid


def _interp_to_ghia(pos: np.ndarray, vals_norm: np.ndarray,
                    sample_pts: list[float]) -> np.ndarray:
    return np.interp(np.asarray(sample_pts, dtype=float), pos, vals_norm)


def _l2_relative(a: np.ndarray, b: np.ndarray) -> float:
    """Relative L2 norm of (a - b) vs b (Ghia reference)."""
    num = np.sqrt(np.sum((a - b) ** 2))
    den = np.sqrt(np.sum(b ** 2))
    return float(num / den) if den > 0 else float("nan")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--re", type=float, nargs="+", default=DEFAULT_RES,
        help=f"Reynolds numbers to validate (default: {DEFAULT_RES}).")
    parser.add_argument(
        "--collision", nargs="+", default=[DEFAULT_COLLISION],
        choices=sorted(EXAMPLES),
        help=f"Collision operator(s) to compare (default: "
             f"{[DEFAULT_COLLISION]}; pass 'bgk mrt' to overlay both).")
    parser.add_argument(
        "--n", type=int, default=DEFAULT_N,
        help=f"Grid size N (default: {DEFAULT_N}; Ghia uses 129 or 257).")
    parser.add_argument(
        "--u-lid", type=float, default=DEFAULT_U_LID,
        help=f"Lid velocity in lattice units (default: {DEFAULT_U_LID}).")
    parser.add_argument(
        "--num-steps", type=int, default=None,
        help="Override step count.  Default: max(50000, 5*N²/ν) — "
             "enough to reach steady state per Guo §3.6.")
    parser.add_argument(
        "--backend", default="cpu_fortran_serial",
        help="gelb-run backend (default: cpu_fortran_serial; "
             "use gpu_cuda_cpp on a CUDA host).")
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"JSON artifact path (default: "
             f"{DEFAULT_OUT.relative_to(REPO_ROOT)}).")
    parser.add_argument(
        "--no-merge", action="store_true",
        help="Overwrite the output JSON instead of merging with any "
             "existing schema-v2 results (useful for a clean rerun).")
    args = parser.parse_args()

    from gelb.tests.data.ghia_1982_ldc import GHIA_BY_RE

    # results[collision][str(Re)] = {...}.  When --no-merge is NOT
    # passed, we load any existing schema-v2 JSON at args.out and
    # update it in-place -- letting the user incrementally add a new
    # collision (e.g. "incomp_zou") to a JSON that already holds
    # bgk + mrt without re-running the previous backends.
    results: dict[str, dict[str, dict]] = {c: {} for c in args.collision}
    if not args.no_merge and args.out.exists():
        try:
            with args.out.open() as _f:
                _existing = json.load(_f)
            if _existing.get("schema_version") == SCHEMA_VERSION:
                _e_results = _existing.get("results") or {}
                if isinstance(_e_results, dict):
                    for _c, _runs in _e_results.items():
                        if isinstance(_runs, dict):
                            results.setdefault(_c, {}).update(_runs)
                    print(f"  (merged existing schema-v{SCHEMA_VERSION} "
                          f"results from {args.out.name}: "
                          f"{[c for c in results if results[c]]})")
        except (OSError, json.JSONDecodeError):
            pass
    print(f"Lid-driven cavity validation against Ghia et al. (1982)")
    print(f"Grid: N = {args.n}    U_LID = {args.u_lid}    "
          f"collisions = {args.collision}")

    failed = False
    for collision in args.collision:
        for re in args.re:
            if int(re) not in GHIA_BY_RE:
                print(f"[skip] Re={re}: no Ghia reference data "
                      f"(have: {sorted(GHIA_BY_RE)})")
                continue
            ghia = GHIA_BY_RE[int(re)]

            if args.num_steps is None:
                tau = _compute_tau(re, args.n, args.u_lid)
                nu = (tau - 0.5) / 3.0
                n_steps = max(50000, int(5 * args.n * args.n / nu))
            else:
                n_steps = args.num_steps

            sim = _run_one(re, args.n, args.u_lid, n_steps,
                           collision=collision,
                           backend=args.backend)
            if sim is None:
                failed = True
                continue

            # Vertical centerline u(y).
            y_pos, u_norm = _extract_centerlines(sim["ux"], "y", args.u_lid)
            u_at_ghia = _interp_to_ghia(y_pos, u_norm, ghia["y_over_L"])
            l2_u = _l2_relative(u_at_ghia, np.asarray(ghia["u_over_U"]))

            # Horizontal centerline v(x).
            x_pos, v_norm = _extract_centerlines(sim["uy"], "x", args.u_lid)
            v_at_ghia = _interp_to_ghia(x_pos, v_norm, ghia["x_over_L"])
            l2_v = _l2_relative(v_at_ghia, np.asarray(ghia["v_over_U"]))

            print(f"    L2(u_centerline)/Ghia = {l2_u:.4f}  "
                  f"L2(v_centerline)/Ghia = {l2_v:.4f}")

            results[collision][str(int(re))] = {
                "Re": int(re),
                "collision": collision,
                "tau": sim["tau"],
                "n": sim["n"],
                "u_lid": sim["u_lid"],
                "num_steps": sim["num_steps"],
                "boundary_scheme": "fullway_wall_bounce_back",
                # Wall cells temporarily store reflected populations; these
                # diagnostics measure only the fluid interior.
                "mass_domain": "fluid_cells_only",
                "cavity_height": args.n - 2,
                "mass_initial": sim["mass_initial"],
                "mass_final": sim["mass_final"],
                "mass_rel_change": sim["mass_rel_change"],
                "y_pos": y_pos.tolist(),
                "u_norm": u_norm.tolist(),
                "x_pos": x_pos.tolist(),
                "v_norm": v_norm.tolist(),
                "ghia_y": list(ghia["y_over_L"]),
                "ghia_u": list(ghia["u_over_U"]),
                "ghia_x": list(ghia["x_over_L"]),
                "ghia_v": list(ghia["v_over_U"]),
                "l2_rel_u_vs_ghia": l2_u,
                "l2_rel_v_vs_ghia": l2_v,
            }

    if failed:
        sys.stderr.write("Validation failed; output JSON left unchanged.\n")
        return 1

    if not any(results.values()):
        sys.stderr.write("No results — nothing to write.\n")
        return 1

    # The host name never goes into this tracked file; set
    # GELB_BENCH_MACHINE for a curated label (scripts/bench_common.py).
    machine = machine_tag()
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        sha = "unknown"

    doc = {
        "schema_version": SCHEMA_VERSION,
        "ghia_citation":
            "Ghia, Ghia & Shin (1982), J. Comput. Phys. 48: 387-411",
        "machine": machine,
        "commit_sha": sha,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "results": results,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    try:
        rel = args.out.resolve().relative_to(REPO_ROOT)
    except ValueError:
        rel = args.out
    n_runs = sum(len(v) for v in results.values())
    n_collisions = len([c for c in results if results[c]])
    print(f"\nWrote: {rel}  "
          f"({n_runs} runs across {n_collisions} collision(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
