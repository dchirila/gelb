#!/usr/bin/env python3
"""Cross-backend MLUPS benchmark for the SoftwareX paper.

Runs a fixed set of canonical 2D examples under one backend at a time
(``cpu_serial``, ``cpu_highway``, or ``cuda``) and writes the median
Compute-MLUPS per case into a shared committable JSON artifact.

Cross-machine workflow
----------------------
The CUDA runs happen on a separate host than the CPU runs.  Each
invocation rewrites *only* its own ``results.<backend>`` sub-dict of
the JSON, preserving any data already present from other hosts.
Commit the JSON between invocations so each machine's contribution
is persisted on the shared branch.

Usage
-----
    uv run python scripts/benchmark_backends.py --backend cpu_serial
    uv run python scripts/benchmark_backends.py --backend cpu_highway
    uv run python scripts/benchmark_backends.py --backend cuda

Options
-------
    --samples N   Number of runs per case (default 3; median reported).
    --out PATH    JSON artifact path (default:
                  docs/user/figures/data/16_mlups_backend_comparison.json).

The figure itself is rendered by
``scripts/gen_tutorial_figures.py --chapters 16`` once the JSON
contains data for all three backends.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from bench_common import (
    collect_run_metadata,
    display_path,
    mlups_result,
    write_json_artifact,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GELB_RUN = REPO_ROOT / "scripts" / "gelb-run"
DEFAULT_OUT = (REPO_ROOT / "docs" / "user" / "figures" / "data"
               / "16_mlups_backend_comparison.json")

SCHEMA_VERSION = 1
BACKENDS = ("cpu_serial", "cpu_highway", "cuda")


@dataclass(frozen=True)
class Case:
    label: str
    gelb_file: str
    num_steps: int
    defines: dict[str, str]


CASES: list[Case] = [
    Case(
        label="lid_cavity_2d",
        gelb_file="examples/lbm/2d/lid_driven_cavity_2d_bgk.gelb",
        num_steps=5000,
        defines={"N": "512"},
    ),
    Case(
        label="poiseuille_2d",
        gelb_file="examples/lbm/2d/poiseuille_flow_2d_mrt.gelb",
        num_steps=10000,
        defines={"NY": "256", "NX": "256"},
    ),
    Case(
        label="tgv_2d",
        gelb_file="examples/lbm/2d/taylor_green_vortex_2d_bgk.gelb",
        num_steps=5000,
        defines={"N": "512"},
    ),
]

COMPUTE_RE = re.compile(r"Compute MLUPS:\s*([0-9.]+)")


def _case_spec(case: Case) -> dict:
    return {
        "gelb_file": case.gelb_file,
        "steps": case.num_steps,
        "defines": dict(case.defines),
    }


def _build_cmd(case: Case, backend: str) -> list[str]:
    cmd: list[str] = [str(GELB_RUN)]
    if backend == "cpu_serial":
        cmd += ["-b", "cpu_fortran_serial"]
    elif backend == "cuda":
        cmd += ["-b", "gpu_cuda_cpp"]
    # cpu_highway is the gelb-run default -- no extra flag.
    cmd += ["-n", str(case.num_steps), "-w", str(case.num_steps)]
    for name, value in case.defines.items():
        cmd += ["-D", f"{name}={value}"]
    cmd.append(case.gelb_file)
    return cmd


def _run_once(case: Case, backend: str) -> float:
    cmd = _build_cmd(case, backend)
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.stderr.write(
            f"[FAIL] {case.label} ({backend})\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}\n")
        return float("nan")
    match = COMPUTE_RE.search(proc.stdout + proc.stderr)
    if not match:
        sys.stderr.write(
            f"[NO MLUPS] {case.label} ({backend})\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}\n")
        return float("nan")
    return float(match.group(1))


def _load_or_init(out_path: Path) -> dict:
    expected_cases = {c.label: _case_spec(c) for c in CASES}
    if out_path.exists():
        with out_path.open() as f:
            doc = json.load(f)
        if doc.get("schema_version") != SCHEMA_VERSION:
            raise SystemExit(
                f"schema_version mismatch in {out_path}: "
                f"expected {SCHEMA_VERSION}, got {doc.get('schema_version')}")
        if doc.get("cases") != expected_cases:
            raise SystemExit(
                f"'cases' section in {out_path} disagrees with hardcoded "
                f"CASES — resolve manually (benchmark definitions must be "
                f"identical across machines).")
        # Ensure every backend has a sub-dict (may be empty).
        doc.setdefault("results", {})
        for backend in BACKENDS:
            doc["results"].setdefault(backend, {})
        return doc
    return {
        "schema_version": SCHEMA_VERSION,
        "cases": expected_cases,
        "results": {backend: {} for backend in BACKENDS},
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-backend MLUPS benchmark harness.")
    parser.add_argument(
        "--backend", required=True, choices=BACKENDS,
        help="Which backend's numbers to collect this invocation.")
    parser.add_argument(
        "--samples", type=int, default=3,
        help="Samples per case (default 3; median is reported).")
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"JSON artifact path (default {DEFAULT_OUT.relative_to(REPO_ROOT)}).")
    args = parser.parse_args()

    doc = _load_or_init(args.out)

    metadata = collect_run_metadata(REPO_ROOT)

    print(f"# Backend: {args.backend}")
    print(f"# Machine: {metadata.machine}")
    print(f"# Commit:  {metadata.commit_sha}")
    print(f"# Time:    {metadata.timestamp}")
    print(f"# Samples per case: {args.samples}")
    print()

    backend_results: dict[str, dict] = {}
    for case in CASES:
        samples = [_run_once(case, args.backend) for _ in range(args.samples)]
        valid = [s for s in samples if s == s]  # drop NaN
        if not valid:
            print(f"  {case.label:<20s}  FAIL  (no valid samples)")
            backend_results[case.label] = mlups_result(
                samples, None, metadata)
            continue
        median = statistics.median(valid)
        rounded = [round(s, 1) for s in valid]
        print(f"  {case.label:<20s}  median={median:8.1f}  samples={rounded}")
        backend_results[case.label] = mlups_result(samples, median, metadata)

    doc["results"][args.backend] = backend_results

    write_json_artifact(args.out, doc)
    rel = display_path(args.out, REPO_ROOT)
    print(f"\nWrote: {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
