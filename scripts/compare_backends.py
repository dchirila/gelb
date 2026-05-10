#!/usr/bin/env python3
"""Cross-backend numerical bit-equivalence validator.

Runs the same ``.gelb`` program through two backends, opens the
resulting NetCDF outputs, and asserts each variable matches within
``(rtol, atol)``.  Reports per-variable ``(max_abs_diff,
max_rel_diff, verdict)`` and emits a Markdown table suitable for
embedding in a per-host report.

Default reference: ``cpu_fortran_serial`` (gfortran).  Default
subject: ``cpu_highway`` (g++ + Google Highway).  Both deterministic
when ``--seed`` is supplied; we default to seed=42 for
reproducibility.

Usage (recommended -- runs cleanly with no uv warning even when the
shell's ``VIRTUAL_ENV`` points at the system Python)::

    ./scripts/compare_backends.py example.gelb [example.gelb...] \\
        [-n 50] [--rtol 1e-12 --atol 1e-14] [--markdown] [--json out.json]

Also works under ``uv run scripts/compare_backends.py ...`` for
back-compat, but that path may emit a one-line uv warning if the
shell has a stale ``VIRTUAL_ENV`` (typically because VSCode selected
the system Python interpreter).

Exits 0 on success (all variables within tolerance for all
examples), 1 if anything fails.

Prerequisites: the backend-specific toolchain (gfortran +
libnetcdff-dev for the Fortran reference; g++ + libnetcdf-dev for
the C++ subject).
"""

from __future__ import annotations

# -- uv re-exec bootstrap ---------------------------------------------
# Allows ``./scripts/compare_backends.py args`` to Just Work even when
# the shell's Python interpreter is the system one (``/usr/bin/python3``).
# We detect we're not inside the project venv via ``sys.prefix``, strip
# any stale ``VIRTUAL_ENV`` (which would otherwise make uv emit a noisy
# warning every invocation), and re-exec under ``uv run python``.
import os as _os
import sys as _sys
from pathlib import Path as _Path

_REPO_ROOT = _Path(__file__).resolve().parent.parent
_VENV_DIR = _REPO_ROOT / ".venv"
if (_Path(_sys.prefix).resolve() != _VENV_DIR.resolve()
        and _os.environ.get("_GELB_UV_REEXEC") != "1"):
    _env = _os.environ.copy()
    _env.pop("VIRTUAL_ENV", None)
    _env["_GELB_UV_REEXEC"] = "1"
    _os.execvpe(
        "uv",
        ["uv", "run", "python", "-u",
         str(_Path(__file__).resolve()), *_sys.argv[1:]],
        _env,
    )

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent
GELB_RUN = REPO_ROOT / "scripts" / "gelb-run"


def _gelb_dataset_class():
    """Late-import GeLBDataset so a missing netCDF4 surfaces here, not at top."""
    sys.path.insert(0, str(REPO_ROOT))
    from gelb.visualization.data_viewer import GeLBDataset  # noqa: WPS433
    return GeLBDataset


# --------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------


@dataclass
class VarComparison:
    """Result of comparing one variable across two backends."""
    name: str
    shape: tuple
    max_abs_diff: float
    max_rel_diff: float
    worst_index: tuple
    matches: bool
    nan_mismatch: bool = False


@dataclass
class ExampleResult:
    """Result of comparing one ``.gelb`` example across two backends."""
    example: str
    reference: str
    subject: str
    variables: list[VarComparison] = field(default_factory=list)
    overall_match: bool = True
    error: str | None = None  # set if either run failed


# --------------------------------------------------------------------
# Backend invocation
# --------------------------------------------------------------------


def run_backend(example: Path, backend: str, n_steps: int,
                seed: int | None, work_dir: Path) -> Path:
    """Run ``gelb-run`` for one (example, backend); return path to .nc output.

    Each backend is invoked in its own temp directory so the .nc
    outputs don't clobber each other (``gelb-run`` writes
    ``{basename}.nc`` in ``cwd``).
    """
    cmd = [str(GELB_RUN), "--backend", backend, "-n", str(n_steps)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    cmd += [str(example.resolve())]
    result = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True)
    if result.returncode != 0:
        # Truncate noisy compiler output.
        stderr = result.stderr
        if len(stderr) > 2000:
            stderr = stderr[:1500] + "\n  ... <truncated> ...\n" + stderr[-300:]
        raise RuntimeError(
            f"gelb-run failed (backend={backend}, example={example.name}):\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  stderr:\n{stderr}"
        )
    nc = work_dir / f"{example.stem}.nc"
    if not nc.is_file():
        raise RuntimeError(
            f"{backend} produced no NetCDF output at expected path {nc}\n"
            f"  stdout tail:\n{result.stdout[-500:]}"
        )
    return nc


# --------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------


def _compare_arrays(name: str, ref: np.ndarray, sub: np.ndarray,
                    rtol: float, atol: float) -> VarComparison:
    """Compare one variable's two arrays."""
    if ref.shape != sub.shape:
        return VarComparison(
            name=name, shape=ref.shape,
            max_abs_diff=float("inf"), max_rel_diff=float("inf"),
            worst_index=(), matches=False,
        )

    ref_nan = np.isnan(ref)
    sub_nan = np.isnan(sub)
    nan_mismatch = bool((ref_nan != sub_nan).any())
    both_finite = np.isfinite(ref) & np.isfinite(sub)

    if not both_finite.any():
        # Variable is entirely NaN/inf in at least one backend.
        return VarComparison(
            name=name, shape=ref.shape,
            max_abs_diff=0.0, max_rel_diff=0.0,
            worst_index=(), matches=not nan_mismatch,
            nan_mismatch=nan_mismatch,
        )

    abs_diff = np.zeros_like(ref, dtype=float)
    np.subtract(ref, sub, where=both_finite, out=abs_diff)
    np.abs(abs_diff, where=both_finite, out=abs_diff)

    # Relative diff with floor to avoid divide-by-zero on near-zero
    # baselines.  np.allclose-style: |ref - sub| <= atol + rtol*|ref|.
    rel_denom = np.maximum(np.abs(ref), atol / max(rtol, 1e-30))
    rel_diff = np.zeros_like(ref, dtype=float)
    np.divide(abs_diff, rel_denom, where=both_finite, out=rel_diff)

    matches = (not nan_mismatch) and np.allclose(
        ref[both_finite], sub[both_finite], rtol=rtol, atol=atol,
    )

    # Worst offender within the finite region.
    masked = np.where(both_finite, abs_diff, -np.inf)
    flat_idx = int(np.argmax(masked))
    worst = np.unravel_index(flat_idx, ref.shape)
    return VarComparison(
        name=name, shape=ref.shape,
        max_abs_diff=float(abs_diff[both_finite].max()),
        max_rel_diff=float(rel_diff[both_finite].max()),
        worst_index=tuple(int(x) for x in worst),
        matches=bool(matches),
        nan_mismatch=nan_mismatch,
    )


def compare_one(example: Path, reference: str, subject: str,
                n_steps: int, seed: int | None,
                rtol: float, atol: float) -> ExampleResult:
    """Run ``example`` on both backends and compare every variable."""
    GeLBDataset = _gelb_dataset_class()
    with tempfile.TemporaryDirectory(prefix="cmp_ref_") as ref_d, \
         tempfile.TemporaryDirectory(prefix="cmp_sub_") as sub_d:
        ref_dir, sub_dir = Path(ref_d), Path(sub_d)
        try:
            ref_nc = run_backend(example, reference, n_steps, seed, ref_dir)
            sub_nc = run_backend(example, subject, n_steps, seed, sub_dir)
        except RuntimeError as exc:
            return ExampleResult(
                example=str(example), reference=reference, subject=subject,
                overall_match=False, error=str(exc),
            )

        with GeLBDataset(str(ref_nc)) as r, GeLBDataset(str(sub_nc)) as s:
            ref_vars = set(r.variables)
            sub_vars = set(s.variables)
            if ref_vars != sub_vars:
                missing = ref_vars - sub_vars
                extra = sub_vars - ref_vars
                return ExampleResult(
                    example=str(example), reference=reference, subject=subject,
                    overall_match=False,
                    error=f"variable sets differ: missing in subject={missing!r}, extra={extra!r}",
                )

            comparisons = [
                _compare_arrays(
                    name,
                    np.asarray(r.get_variable(name)),
                    np.asarray(s.get_variable(name)),
                    rtol, atol,
                )
                for name in sorted(ref_vars)
            ]

        return ExampleResult(
            example=str(example), reference=reference, subject=subject,
            variables=comparisons,
            overall_match=all(c.matches for c in comparisons),
        )


# --------------------------------------------------------------------
# Output formatting
# --------------------------------------------------------------------


def emit_markdown(results: list[ExampleResult], rtol: float, atol: float) -> str:
    out = [f"_Tolerance: `rtol={rtol:.0e}, atol={atol:.0e}`._\n"]
    out.append("| Example | Variable | Shape | Max abs diff | Max rel diff | Verdict |")
    out.append("|---|---|---|---|---|---|")
    for r in results:
        if r.error:
            err = r.error.replace("\n", " ").strip()
            if len(err) > 90:
                err = err[:87] + "..."
            ex_label = Path(r.example).name
            out.append(f"| `{ex_label}` | — | — | — | — | ❌ {err} |")
            continue
        ex_label = Path(r.example).name
        for v in r.variables:
            verdict = "✅" if v.matches else "❌"
            if v.nan_mismatch:
                verdict += " (NaN positions disagree)"
            out.append(
                f"| `{ex_label}` | `{v.name}` | `{v.shape}` "
                f"| {v.max_abs_diff:.2e} | {v.max_rel_diff:.2e} | {verdict} |"
            )
    return "\n".join(out)


def emit_human(results: list[ExampleResult]) -> None:
    """Live progress to stderr."""
    for r in results:
        ex_label = Path(r.example).name
        if r.error:
            print(f"  {ex_label}: ERROR — {r.error.splitlines()[0]}",
                  file=sys.stderr)
            continue
        verdict = "PASS" if r.overall_match else "FAIL"
        print(f"  {ex_label}: {verdict}", file=sys.stderr)
        for v in r.variables:
            status = "ok" if v.matches else "FAIL"
            extra = " (NaN positions disagree)" if v.nan_mismatch else ""
            print(
                f"    {v.name:25} shape={str(v.shape):20} "
                f"max_abs={v.max_abs_diff:.2e}  max_rel={v.max_rel_diff:.2e} "
                f"[{status}]{extra}",
                file=sys.stderr,
            )


# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("examples", nargs="+", type=Path,
                   help=".gelb file(s) to validate")
    p.add_argument("--reference", default="cpu_fortran_serial",
                   help="reference backend (default: %(default)s)")
    p.add_argument("--subject", default="cpu_highway",
                   help="subject backend (default: %(default)s)")
    p.add_argument("-n", "--num-timesteps", type=int, default=50,
                   help="timesteps to run on each backend (default: %(default)d)")
    p.add_argument("--seed", type=int, default=42,
                   help="PRNG seed for reproducibility "
                        "(default: %(default)d; pass 0 to omit)")
    p.add_argument("--rtol", type=float, default=1e-12)
    p.add_argument("--atol", type=float, default=1e-14)
    p.add_argument("--markdown", action="store_true",
                   help="emit a Markdown comparison table to stdout")
    p.add_argument("--json", type=Path,
                   help="dump full results as JSON to this path")
    args = p.parse_args()

    results: list[ExampleResult] = []
    seed = args.seed if args.seed != 0 else None
    for example in args.examples:
        if not example.is_file():
            print(f"ERROR: {example} is not a file", file=sys.stderr)
            return 2
        print(
            f"# {example.name}: {args.reference} vs {args.subject} "
            f"(n={args.num_timesteps}, seed={seed})",
            file=sys.stderr,
        )
        result = compare_one(
            example, args.reference, args.subject, args.num_timesteps,
            seed, args.rtol, args.atol,
        )
        results.append(result)
        emit_human([result])

    if args.markdown:
        print(emit_markdown(results, args.rtol, args.atol))

    if args.json:
        args.json.write_text(json.dumps(
            [
                {
                    "example": r.example,
                    "reference": r.reference,
                    "subject": r.subject,
                    "error": r.error,
                    "overall_match": r.overall_match,
                    "variables": [
                        {
                            "name": v.name, "shape": list(v.shape),
                            "max_abs_diff": v.max_abs_diff,
                            "max_rel_diff": v.max_rel_diff,
                            "worst_index": list(v.worst_index),
                            "matches": v.matches,
                            "nan_mismatch": v.nan_mismatch,
                        }
                        for v in r.variables
                    ],
                }
                for r in results
            ],
            indent=2,
        ))

    return 0 if all(r.overall_match for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
