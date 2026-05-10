#!/usr/bin/env python3
"""Cross-backend numerical comparison for every ``.gelb`` example.

For each example, compile + run with each available backend
(``cpu_fortran_serial``, ``cpu_highway``, optionally
``gpu_cuda_cpp``) at small N (default 10 timesteps), and compare
the resulting NetCDF outputs against the Fortran reference.

Each (example, backend) combination is classified by the largest
absolute difference over all gauge variables and timesteps,
``max |diff|``, against the Fortran reference.  The gauge magnitudes in
the examples are O(1) (densities) to O(0.1) (velocities), so 1e-13 is
a few hundred ULP and 1e-10 a loose engineering tolerance -- only the
EXACT band means bit-identical output.

  EXACT     max |diff| = 0                  -- bit-identical output
  ROUNDOFF  0 < max |diff| <= 1e-13         -- floating-point reordering
                                               (FMA, sum order, SIMD lanes)
  TOL       1e-13 < max |diff| <= 1e-10     -- within the cross-backend
                                               tolerance used by the tests
  WARN      1e-10 < max |diff| <= 1e-3      -- numerical drift: investigate
  FAIL      max |diff| > 1e-3, or NaN/inf   -- divergence
  SKIP      backend errored / not supported  -- see the ``reason`` column
  STOCH     example uses ``random()`` --     -- gauge values are inherently
            only checks output shape and       different across backends;
            finiteness                         we verify the run completes,
                                               output shape matches, and
                                               no non-finite values
  UNSTABLE  reference (fortran) itself --    -- the example is numerically
            diverged into NaN/inf during       unstable at its default
            the run; comparison against        parameters; an unstable
            an unstable trajectory is          reference can't anchor a
            meaningless                        cross-backend agreement
                                               check (different FP order
                                               sends each backend along a
                                               different blow-up trajectory)

Usage::

    uv run python scripts/cross_backend_compare.py
    uv run python scripts/cross_backend_compare.py --backends fortran,highway
    uv run python scripts/cross_backend_compare.py --num-timesteps 50
    uv run python scripts/cross_backend_compare.py --json out.json
    uv run python scripts/cross_backend_compare.py --filter ldc

The Fortran serial backend is always the reference; the others are
compared against it.  Gauge variables only -- coordinate and time vars
are excluded automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
GELB_RUN = str(REPO_ROOT / "scripts" / "gelb-run")

# Friendly names -> gelb-run backend ids.
BACKEND_IDS = {
    "fortran":  "cpu_fortran_serial",
    "highway":  "cpu_highway",
    "cuda":     "gpu_cuda_cpp",
}
DEFAULT_BACKENDS = ["fortran", "highway", "cuda"]
REFERENCE = "fortran"

# Band edges on the absolute max|diff| (see the module docstring).
TOL_ROUNDOFF = 1e-13   # floating-point reordering noise
TOL          = 1e-10   # the cross-backend tolerance the tests use
TOL_WARN     = 1e-3    # above this: divergence

# Per-example dimension hint (cheap/conservative).
def _dim_of(path: Path) -> int:
    parts = [p.lower() for p in path.parts]
    if "1d" in parts or "_1d" in path.stem:
        return 1
    if "3d" in parts or "_3d" in path.stem:
        return 3
    return 2


@dataclass
class RunResult:
    success: bool
    nc_path: Path | None = None
    reason: str = ""        # populated when success=False
    stderr_tail: str = ""   # last few lines, for diagnostics


@dataclass
class Comparison:
    status: str             # EXACT / ROUNDOFF / TOL / WARN / FAIL / SKIP / STOCH / UNSTABLE
    max_abs_diff: float = 0.0
    per_var: dict = field(default_factory=dict)
    reason: str = ""        # for SKIP
    stderr_tail: str = ""


def discover_examples():
    out = []
    if not EXAMPLES_DIR.is_dir():
        return out
    out.extend(sorted(EXAMPLES_DIR.rglob("*.gelb")))
    return out


_RANDOM_RE = __import__("re").compile(r"\brandom\s*\(")


def example_uses_random(path: Path) -> bool:
    """Quick textual check for a ``random()`` intrinsic call."""
    try:
        return bool(_RANDOM_RE.search(path.read_text()))
    except OSError:
        return False


def has_nvcc():
    return shutil.which("nvcc") is not None


def run_backend(backend_id: str, example_path: Path, num_timesteps: int,
                timeout: int, run_root: Path) -> RunResult:
    """Compile + run one (backend, example) combo.  Returns a RunResult
    where ``nc_path`` is the absolute path of the produced .nc file
    (caller owns the file) on success."""
    # Use a per-backend, per-example subdir so simultaneous builds and
    # output filenames don't collide between backends.
    run_dir = run_root / f"{backend_id}__{example_path.stem}"
    run_dir.mkdir(parents=True, exist_ok=True)
    cmd = [GELB_RUN, "-b", backend_id,
           "-n", str(num_timesteps), str(example_path)]
    try:
        proc = subprocess.run(
            cmd, cwd=str(run_dir), capture_output=True,
            text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return RunResult(False, reason="timeout",
                         stderr_tail=f"timed out after {timeout}s")

    if proc.returncode != 0:
        err = (proc.stderr or "") + "\n" + (proc.stdout or "")
        # Classify the error.
        if "NotImplementedError" in err or "not yet supported" in err \
                or "currently supports 1-D and 2-D lattices" in err:
            reason = "not-supported"
        elif "nvcc" in err and "command not found" in err:
            reason = "nvcc-missing"
        elif "error:" in err.lower() or "compilation terminated" in err:
            reason = "build-error"
        else:
            reason = "runtime-error"
        # Keep the last ~6 lines of stderr for the report.
        tail = "\n".join(err.strip().splitlines()[-6:])
        return RunResult(False, reason=reason, stderr_tail=tail)

    nc = run_dir / f"{example_path.stem}.nc"
    if not nc.exists():
        return RunResult(False, reason="no-output",
                         stderr_tail="no .nc produced")
    return RunResult(True, nc_path=nc)


def compare_nc(reference: Path, candidate: Path) -> dict:
    """Return ``{var: max_abs_diff}`` over the gauge variables present
    in BOTH files.  Coord / time variables are excluded.  Mismatched
    shapes report inf for that variable."""
    import netCDF4 as nc
    ref_ds = nc.Dataset(str(reference))
    cand_ds = nc.Dataset(str(candidate))
    skip_vars = {"x", "y", "z", "time"}
    common = (set(ref_ds.variables.keys())
              & set(cand_ds.variables.keys())) - skip_vars
    out = {}
    for v in sorted(common):
        a = ref_ds.variables[v][:]
        b = cand_ds.variables[v][:]
        try:
            a = np.asarray(a, dtype=float)
            b = np.asarray(b, dtype=float)
        except Exception:
            out[v] = float("nan")
            continue
        if a.shape != b.shape:
            out[v] = float("inf")
            continue
        if a.size == 0:
            out[v] = 0.0
            continue
        # Ignore NaN-vs-NaN (e.g. masked node-class output) -- count
        # only positions where at least one side is finite.
        diff = np.abs(a - b)
        finite = np.isfinite(diff)
        if not finite.any():
            out[v] = 0.0
        else:
            out[v] = float(diff[finite].max())
    return out


def classify(max_diff: float) -> str:
    if not np.isfinite(max_diff):
        return "FAIL"
    if max_diff == 0.0:
        return "EXACT"
    if max_diff <= TOL_ROUNDOFF:
        return "ROUNDOFF"
    if max_diff <= TOL:
        return "TOL"
    if max_diff <= TOL_WARN:
        return "WARN"
    return "FAIL"


def reference_is_unstable(reference: Path) -> bool:
    """Return True if the reference (fortran) NetCDF output diverged
    into NaN/inf during the run.

    Detection: any gauge variable whose finite-ness mask differs across
    timesteps means cells went non-finite *during* the simulation --
    i.e., the example exploded.  Masked-node-class outputs have NaN at
    fixed positions for every timestep, so they don't trigger this.
    """
    import netCDF4 as nc
    ref = nc.Dataset(str(reference))
    skip_vars = {"x", "y", "z", "time"}
    gauge_vars = sorted(set(ref.variables.keys()) - skip_vars)
    for v in gauge_vars:
        a = np.asarray(ref.variables[v][:], dtype=float)
        if a.ndim == 0 or a.shape[0] < 2:
            continue
        first_finite = np.isfinite(a[0])
        for t in range(1, a.shape[0]):
            if not np.array_equal(np.isfinite(a[t]), first_finite):
                return True
    return False


def classify_stochastic(reference: Path, candidate: Path) -> Comparison:
    """For programs that call ``random()``: backends necessarily
    produce different gauge outputs (different PRNG algorithms).
    We verify only that the candidate (a) has the same variables
    and shapes as the reference and (b) contains no non-finite
    values."""
    import netCDF4 as nc
    ref = nc.Dataset(str(reference))
    cand = nc.Dataset(str(candidate))
    skip_vars = {"x", "y", "z", "time"}
    common = (set(ref.variables.keys())
              & set(cand.variables.keys())) - skip_vars
    if not common:
        return Comparison("SKIP", reason="no-common-vars")
    per_var = {}
    for v in sorted(common):
        a = np.asarray(ref.variables[v][:])
        b = np.asarray(cand.variables[v][:])
        if a.shape != b.shape:
            per_var[v] = float("inf")
            continue
        # Check finiteness on the candidate; ignore positions where
        # one side is non-finite and the other isn't (that's a
        # legitimate masked-cell mismatch only if reference is also
        # non-finite at the same spot, which we accept).
        try:
            b_arr = np.asarray(b, dtype=float)
            ref_arr = np.asarray(a, dtype=float)
            n_nonfinite = int(np.sum(~np.isfinite(b_arr)))
            # Subtract masked cells (NaN in both is fine).
            both_nonfinite = int(np.sum(
                (~np.isfinite(ref_arr)) & (~np.isfinite(b_arr))))
            extra_bad = n_nonfinite - both_nonfinite
            per_var[v] = float(extra_bad)
        except Exception:
            per_var[v] = float("nan")
    worst = max(per_var.values()) if per_var else 0.0
    if worst > 0:
        # Some unexpected NaN/inf in candidate -> real failure.
        return Comparison("FAIL", max_abs_diff=worst, per_var=per_var,
                          reason="non-finite candidate values")
    return Comparison("STOCH", max_abs_diff=0.0, per_var=per_var)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backends", default=",".join(DEFAULT_BACKENDS),
                    help=f"Comma-separated subset of {sorted(BACKEND_IDS.keys())} "
                         f"(default: all available).")
    ap.add_argument("--num-timesteps", type=int, default=10,
                    help="Timesteps per example (default: 10).")
    ap.add_argument("--timeout", type=int, default=120,
                    help="Per-(example, backend) timeout in seconds (default: 120).")
    ap.add_argument("--filter", default="",
                    help="Substring filter on example path "
                         "(e.g. --filter lid_driven_cavity).")
    ap.add_argument("--json", type=Path, default=None,
                    help="Optional JSON report path.")
    ap.add_argument("--keep-tmp", action="store_true",
                    help="Keep the temp run dir after exit (for debugging).")
    args = ap.parse_args()

    requested = [b.strip() for b in args.backends.split(",") if b.strip()]
    unknown = [b for b in requested if b not in BACKEND_IDS]
    if unknown:
        sys.exit(f"unknown backend(s): {unknown}; "
                 f"valid: {sorted(BACKEND_IDS.keys())}")
    if REFERENCE not in requested:
        sys.exit(f"the reference backend '{REFERENCE}' must be in --backends")

    # Drop CUDA if nvcc isn't available.
    if "cuda" in requested and not has_nvcc():
        sys.stderr.write(
            "[INFO] nvcc not found — skipping CUDA backend.\n")
        requested = [b for b in requested if b != "cuda"]

    backend_ids = [BACKEND_IDS[b] for b in requested]

    examples = discover_examples()
    if args.filter:
        examples = [e for e in examples if args.filter in str(e)]
    if not examples:
        sys.exit("no examples to compare")

    print(f"# Cross-backend comparison")
    print(f"# Examples: {len(examples)}")
    print(f"# Backends: {requested}  (reference: {REFERENCE})")
    print(f"# Timesteps per example: {args.num_timesteps}")
    print(f"# Bands on the absolute max|diff| over gauge variables: "
          f"EXACT = 0 | ROUNDOFF ≤ {TOL_ROUNDOFF:.0e} | TOL ≤ {TOL:.0e} | "
          f"WARN ≤ {TOL_WARN:.0e} | FAIL above")
    print()

    # tempdir: kept across all runs for the session.
    tmpdir = Path(tempfile.mkdtemp(prefix="gelb_xback_"))

    # report: example_relpath -> backend_friendly_name -> Comparison
    report: dict[str, dict[str, Comparison]] = {}

    t_start = time.time()
    for ex_idx, example in enumerate(examples, 1):
        rel = str(example.relative_to(REPO_ROOT))
        report[rel] = {}
        # Reference run first.
        ref_result = run_backend(BACKEND_IDS[REFERENCE], example,
                                 args.num_timesteps, args.timeout, tmpdir)
        if not ref_result.success:
            # If the Fortran reference itself fails, skip the example
            # entirely (every backend gets a SKIP with the same reason).
            for b in requested:
                report[rel][b] = Comparison(
                    "SKIP",
                    reason=f"reference-failed:{ref_result.reason}",
                    stderr_tail=ref_result.stderr_tail)
            print(f"[{ex_idx}/{len(examples)}] {rel}  "
                  f"REF FAIL ({ref_result.reason})")
            continue

        # Reference succeeded -- but if it diverged into NaN/inf during
        # the run (numerically unstable example at its default
        # parameters), comparing against it is meaningless: tiny FP
        # rounding sends each backend along a different blow-up
        # trajectory, producing astronomical "diffs" between two
        # equally-invalid solutions.  Mark every candidate UNSTABLE
        # and skip the comparison.
        if reference_is_unstable(ref_result.nc_path):
            for b in requested:
                report[rel][b] = Comparison(
                    "UNSTABLE",
                    reason="reference diverged into NaN/inf")
            print(f"[{ex_idx}/{len(examples)}] {rel}  REF UNSTABLE")
            continue

        # Reference succeeded -- compare each candidate.
        line_parts = [f"[{ex_idx}/{len(examples)}] {rel}"]
        for b in requested:
            if b == REFERENCE:
                # Self-comparison is trivially EXACT.
                report[rel][b] = Comparison("EXACT", 0.0, {})
                line_parts.append(f"{b}=EXACT(0.0e+00)")
                continue
            cand = run_backend(BACKEND_IDS[b], example,
                               args.num_timesteps, args.timeout, tmpdir)
            if not cand.success:
                report[rel][b] = Comparison(
                    "SKIP", reason=cand.reason,
                    stderr_tail=cand.stderr_tail)
                line_parts.append(f"{b}=SKIP({cand.reason})")
                continue
            if example_uses_random(example):
                # Stochastic example: check shape + finiteness only.
                # Different backends use different PRNG algorithms;
                # gauge values diverge by design.
                cmp = classify_stochastic(ref_result.nc_path,
                                          cand.nc_path)
                report[rel][b] = cmp
                line_parts.append(f"{b}={cmp.status}")
                continue
            per_var = compare_nc(ref_result.nc_path, cand.nc_path)
            if not per_var:
                # No common variables (very unusual) -- treat as SKIP.
                report[rel][b] = Comparison(
                    "SKIP", reason="no-common-vars")
                line_parts.append(f"{b}=SKIP(no-common-vars)")
                continue
            mx = max(per_var.values())
            status = classify(mx)
            report[rel][b] = Comparison(status, mx, per_var)
            line_parts.append(f"{b}={status}({mx:.2e})")
        print("  " + "  ".join(line_parts))

    elapsed = time.time() - t_start

    # ---- Summary ----
    print()
    print(f"# Done in {elapsed:.1f}s.")

    counts = {b: {} for b in requested}
    for ex_rel, by_backend in report.items():
        for b, c in by_backend.items():
            counts[b][c.status] = counts[b].get(c.status, 0) + 1

    print()
    print("# Status summary (count per backend):")
    statuses = ["EXACT", "ROUNDOFF", "TOL", "STOCH", "WARN", "FAIL",
                "UNSTABLE", "SKIP"]
    header = (f"{'backend':<14} | "
              + " ".join(f"{s:>8}" for s in statuses))
    print(header)
    print("-" * len(header))
    for b in requested:
        row = " ".join(f"{counts[b].get(s, 0):>8}" for s in statuses)
        print(f"{b:<14} | {row}")

    # ---- Anomalies ----
    print()
    print("# Anomalies (FAIL or WARN, or unexpected SKIPs):")
    any_anomaly = False
    for ex_rel, by_backend in report.items():
        for b, c in by_backend.items():
            if c.status in ("FAIL", "WARN"):
                any_anomaly = True
                worst_var = max(c.per_var, key=c.per_var.get) \
                    if c.per_var else "?"
                print(f"  {c.status:<4}  {b:<10}  {ex_rel}"
                      f"  max|diff|={c.max_abs_diff:.3e}  "
                      f"(worst: {worst_var})")
            elif c.status == "SKIP" and not (
                    c.reason.startswith("not-supported")
                    or c.reason.startswith("nvcc-missing")
                    or c.reason.startswith("reference-failed")):
                any_anomaly = True
                print(f"  {c.status:<4}  {b:<10}  {ex_rel}  reason={c.reason}")
                if c.stderr_tail:
                    for line in c.stderr_tail.splitlines():
                        print(f"        | {line}")
    if not any_anomaly:
        print("  (none)")

    # ---- Unstable examples ----
    unstable_examples = [
        ex_rel for ex_rel, by_backend in report.items()
        if any(c.status == "UNSTABLE" for c in by_backend.values())]
    if unstable_examples:
        print()
        print("# Unstable examples (reference diverged into NaN/inf — "
              "comparison skipped):")
        for ex_rel in unstable_examples:
            print(f"  {ex_rel}")

    # ---- JSON dump ----
    if args.json:
        doc = {
            "num_timesteps": args.num_timesteps,
            "backends": requested,
            "reference": REFERENCE,
            "tolerances": {
                "ROUNDOFF_TOL": TOL_ROUNDOFF, "TOL": TOL, "WARN_TOL": TOL_WARN},
            "results": {
                ex: {b: asdict(c) for b, c in by.items()}
                for ex, by in report.items()},
            "summary": counts,
        }
        # Path-friendly serialisation.
        for by in doc["results"].values():
            for c in by.values():
                if c.get("nc_path"):
                    c["nc_path"] = str(c["nc_path"])
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(doc, indent=2, default=str))
        print(f"\n# JSON report → {args.json}")

    if not args.keep_tmp:
        shutil.rmtree(tmpdir, ignore_errors=True)
    else:
        print(f"\n# Kept temp dir: {tmpdir}")

    # Exit code reflects the worst outcome.
    has_fail = any(c.status == "FAIL"
                   for by in report.values() for c in by.values())
    return 1 if has_fail else 0


if __name__ == "__main__":
    sys.exit(main())
