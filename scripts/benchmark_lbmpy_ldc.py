#!/usr/bin/env python3
"""lbmpy lid-driven cavity benchmark (D2Q9 BGK).

Runs lbmpy's ``create_lid_driven_cavity`` scenario with the same N,
number of steps, lid velocity and relaxation time as the
``lid_cavity_2d`` case of ``benchmark_backends.py`` (N = 512,
5000 steps, U_LID = 0.1, tau = 0.689) and reports the median
compute-only MLUPS over ``--samples`` runs (default 3).  The timed
region covers the ``--num-steps`` lattice updates that follow a
warm-up run of ``--warmup-steps`` steps, so kernel generation,
compilation and initialisation are excluded.  The result is merged
into the JSON file given by ``--out`` (default
``docs/benchmarks/lbmpy_results.json``), which
``benchmark_lbmpy_tgv.py`` also writes to.

lbmpy and pystencils are not dependencies of GeLB, and pystencils
compiles its CPU kernels at run time against the interpreter's
headers, so they live in a separate venv built from a uv-managed
Python.  Create it with ``scripts/install_lbmpy.sh`` and run this
script with that venv's interpreter, not with ``uv run``:

    ~/Soft/lbmpy/venv/bin/python scripts/benchmark_lbmpy_ldc.py
    OMP_NUM_THREADS=16 OMP_PROC_BIND=close OMP_PLACES=cores \\
        ~/Soft/lbmpy/venv/bin/python scripts/benchmark_lbmpy_ldc.py

``--target gpu`` selects pystencils' GPU target (needs cupy and a
CUDA toolkit the venv can see); the paper's table uses the CPU
target.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from pathlib import Path

from bench_common import (
    collect_run_metadata,
    display_path,
    load_json_or_empty,
    machine_tag,
    mlups_result,
    write_json_artifact,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "docs" / "benchmarks" / "lbmpy_results.json"

# Match scripts/benchmark_backends.py's lid_cavity_2d fixed case.
DEFAULT_DOMAIN_SIZE = 512
DEFAULT_NUM_STEPS = 5000
DEFAULT_TAU = 0.689        # tau = 3*nu + 0.5 with nu = (U_LID*N)/Re
DEFAULT_U_LID = 0.1
DEFAULT_RE_FOR_TAU = 75    # Re = U_LID*N/nu -> nu = U_LID*N/Re; with N=512
                           # this gives tau ~= 0.689 i.e. omega ~= 1.451.

SCHEMA_VERSION = 1


def _omega_from_tau(tau: float) -> float:
    return 1.0 / tau


def run_one(domain_size: int, num_steps: int, u_lid: float, tau: float,
            target_str: str, cpu_openmp: bool = True,
            warmup_steps: int = 100) -> float:
    """Run one lbmpy lid-driven cavity and return compute-only MLUPS.

    Cell updates per second over the timed ``num_steps`` run, the
    counterpart of GeLB's ``Compute MLUPS`` line: kernel generation,
    compilation and set-up happen during the warm-up run and are not
    counted.

    ``CreateKernelConfig`` defaults to ``cpu_openmp=False``, which
    gives a single-threaded kernel.  This script defaults to
    ``cpu_openmp=True`` so that the kernel runs under OpenMP, as
    GeLB's cpu_highway backend does; ``--no-cpu-openmp`` gives the
    single-threaded variant.
    """
    from lbmpy.scenarios import create_lid_driven_cavity
    from pystencils import Target, CreateKernelConfig

    target_map = {"cpu": Target.CPU, "gpu": Target.GPU}
    if target_str not in target_map:
        raise ValueError(f"Unknown target {target_str!r}; "
                         f"valid: {sorted(target_map)}")
    target = target_map[target_str]

    relaxation_rate = _omega_from_tau(tau)
    # pystencils vectorises only when asked (cpu_vectorize_info=None
    # gives scalar code).  Request AVX-512 explicitly on the CPU
    # target, the lane width GeLB's cpu_highway backend uses on the
    # same hardware; the machine must support AVX-512.
    cpu_vectorize_info = (
        {'instruction_set': 'avx512'} if target == Target.CPU else None)
    config = CreateKernelConfig(target=target, cpu_openmp=cpu_openmp,
                                 cpu_vectorize_info=cpu_vectorize_info)
    step = create_lid_driven_cavity(
        domain_size=(domain_size, domain_size),
        lid_velocity=u_lid,
        relaxation_rate=relaxation_rate,
        config=config,
    )

    # Warm-up: generates and compiles the kernel; not timed.
    step.run(warmup_steps)

    t0 = time.perf_counter()
    step.run(num_steps)
    elapsed = time.perf_counter() - t0

    cells = domain_size * domain_size * num_steps
    return cells / elapsed / 1e6


def main() -> int:
    parser = argparse.ArgumentParser(
        description="lbmpy lid-driven cavity benchmark (CPU or GPU).")
    parser.add_argument(
        "--target", choices=("cpu", "gpu"), default="cpu",
        help="lbmpy/pystencils target backend (default: cpu).")
    parser.add_argument(
        "--domain-size", type=int, default=DEFAULT_DOMAIN_SIZE,
        help=f"NxN grid (default: {DEFAULT_DOMAIN_SIZE}).")
    parser.add_argument(
        "--num-steps", type=int, default=DEFAULT_NUM_STEPS,
        help=f"Timesteps to time (default: {DEFAULT_NUM_STEPS}).")
    parser.add_argument(
        "--u-lid", type=float, default=DEFAULT_U_LID,
        help=f"Lid velocity (default: {DEFAULT_U_LID}).")
    parser.add_argument(
        "--tau", type=float, default=DEFAULT_TAU,
        help=f"BGK τ (default: {DEFAULT_TAU} → ω={1/DEFAULT_TAU:.4f}).")
    parser.add_argument(
        "--samples", type=int, default=3,
        help="Samples (default: 3; median reported).")
    parser.add_argument(
        "--no-cpu-openmp", action="store_true",
        help="Disable cpu_openmp on the generated kernel "
             "(single-threaded reference baseline; default: enabled).")
    parser.add_argument(
        "--warmup-steps", type=int, default=100,
        help="JIT-warmup steps before the timed run (default: 100).")
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"JSON path (default: {DEFAULT_OUT.relative_to(REPO_ROOT)}).")
    args = parser.parse_args()

    machine = machine_tag()
    print(f"# lbmpy LDC benchmark — target: {args.target}")
    print(f"# Domain: {args.domain_size}x{args.domain_size}")
    print(f"# Steps:  {args.num_steps} (warmup {args.warmup_steps})")
    print(f"# τ:      {args.tau} (ω = {_omega_from_tau(args.tau):.4f})")
    print(f"# U_LID:  {args.u_lid}")
    print(f"# Samples: {args.samples}")
    print(f"# Machine: {machine}")
    print()

    cpu_openmp = (args.target == "cpu") and not args.no_cpu_openmp
    print(f"# cpu_openmp: {cpu_openmp}")
    print()

    samples = []
    for i in range(args.samples):
        try:
            mlups = run_one(args.domain_size, args.num_steps, args.u_lid,
                            args.tau, args.target,
                            cpu_openmp=cpu_openmp,
                            warmup_steps=args.warmup_steps)
            samples.append(mlups)
            print(f"  sample {i+1}: {mlups:.1f} MLUPS")
        except Exception as e:
            print(f"  sample {i+1}: FAIL ({type(e).__name__}: {e})")
            samples.append(None)

    valid = [s for s in samples if s is not None]
    if not valid:
        print("\nAll samples failed; nothing to write.")
        return 1
    median = statistics.median(valid)
    print(f"\n  median: {median:.1f} MLUPS")

    # Merge into the results JSON without disturbing other entries.
    doc = load_json_or_empty(args.out)
    if doc and doc.get("schema_version") != SCHEMA_VERSION:
        print(f"  (warning) schema mismatch in {args.out}; overwriting")
        doc = {}

    if not doc:
        doc = {
            "schema_version": SCHEMA_VERSION,
            "case": {
                "label": "lid_cavity_2d",
                "domain_size": args.domain_size,
                "num_steps": args.num_steps,
                "tau": args.tau,
                "u_lid": args.u_lid,
                "warmup_steps": args.warmup_steps,
            },
            "results": {},
        }

    omp_threads = os.environ.get("OMP_NUM_THREADS", "default-all-cores")
    key_suffix = "_openmp" if cpu_openmp else "_serial"
    if args.target == "gpu":
        key_suffix = ""  # GPU: no threading concept
    key = f"lbmpy_{args.target}{key_suffix}"
    metadata = collect_run_metadata(REPO_ROOT, machine=machine)
    doc["results"][key] = mlups_result(
        samples, median, metadata,
        suffix={
            "lbmpy_version": __import__("lbmpy").__version__,
            "pystencils_version": __import__("pystencils").__version__,
            "cpu_openmp": cpu_openmp,
            "omp_num_threads": omp_threads,
        },
    )

    write_json_artifact(args.out, doc)
    rel = display_path(args.out.resolve(), REPO_ROOT)
    print(f"\nWrote: {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
