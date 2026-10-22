#!/usr/bin/env python3
"""lbmpy Taylor-Green vortex benchmark (D2Q9 BGK, fully periodic).

Runs lbmpy's ``create_fully_periodic_flow`` scenario on an N x N
periodic domain initialised with a Taylor-Green velocity field, with
the same N, number of steps and relaxation time as the ``tgv_2d``
case of ``benchmark_backends.py`` (N = 512, 5000 steps, tau = 0.689),
and reports the median compute-only MLUPS over ``--samples`` runs
(default 3).  The timed region covers the ``--num-steps`` lattice
updates that follow a warm-up run of ``--warmup-steps`` steps, so
kernel generation, compilation and initialisation are excluded.  The
result is merged into the JSON file given by ``--out`` (default
``docs/benchmarks/lbmpy_results.json``), which
``benchmark_lbmpy_ldc.py`` also writes to.

lbmpy and pystencils are not dependencies of GeLB.  Install them into
a separate venv with ``scripts/install_lbmpy.sh`` and run this script
with that venv's interpreter, not with ``uv run``:

    ~/Soft/lbmpy/venv/bin/python scripts/benchmark_lbmpy_tgv.py
    OMP_NUM_THREADS=16 OMP_PROC_BIND=close OMP_PLACES=cores \\
        ~/Soft/lbmpy/venv/bin/python scripts/benchmark_lbmpy_tgv.py
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

DEFAULT_DOMAIN_SIZE = 512
DEFAULT_NUM_STEPS = 5000
DEFAULT_TAU = 0.689
DEFAULT_AMP = 0.05    # initial Taylor-Green amplitude

SCHEMA_VERSION = 1


def _omega_from_tau(tau: float) -> float:
    return 1.0 / tau


def run_one(domain_size: int, num_steps: int, amp: float, tau: float,
            target_str: str, cpu_openmp: bool = True,
            warmup_steps: int = 100) -> float:
    """Run one lbmpy Taylor-Green-init periodic flow and return MLUPS."""
    import numpy as np
    from lbmpy.scenarios import create_fully_periodic_flow
    from pystencils import Target, CreateKernelConfig

    target_map = {"cpu": Target.CPU, "gpu": Target.GPU}
    target = target_map[target_str]
    relaxation_rate = _omega_from_tau(tau)

    xs = np.arange(domain_size, dtype=np.float64)
    ys = np.arange(domain_size, dtype=np.float64)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    ux0 =  amp * np.sin(2 * np.pi * X / domain_size) \
              * np.cos(2 * np.pi * Y / domain_size)
    uy0 = -amp * np.cos(2 * np.pi * X / domain_size) \
              * np.sin(2 * np.pi * Y / domain_size)
    initial_velocity = np.stack([ux0, uy0], axis=-1)

    # pystencils vectorises only when asked (cpu_vectorize_info=None
    # gives scalar code).  Request AVX-512 explicitly on the CPU
    # target, the lane width GeLB's cpu_highway backend uses on the
    # same hardware; the machine must support AVX-512.
    cpu_vectorize_info = (
        {'instruction_set': 'avx512'} if target == Target.CPU else None)
    config = CreateKernelConfig(target=target, cpu_openmp=cpu_openmp,
                                 cpu_vectorize_info=cpu_vectorize_info)
    step = create_fully_periodic_flow(
        initial_velocity=initial_velocity,
        relaxation_rate=relaxation_rate,
        periodicity_in_kernel=True,
        config=config,
    )

    step.run(warmup_steps)
    t0 = time.perf_counter()
    step.run(num_steps)
    elapsed = time.perf_counter() - t0
    return domain_size * domain_size * num_steps / elapsed / 1e6


def main() -> int:
    parser = argparse.ArgumentParser(
        description="lbmpy Taylor-Green periodic benchmark (CPU or GPU).")
    parser.add_argument(
        "--target", choices=("cpu", "gpu"), default="cpu",
        help="target backend (default: cpu).")
    parser.add_argument(
        "--domain-size", type=int, default=DEFAULT_DOMAIN_SIZE)
    parser.add_argument(
        "--num-steps", type=int, default=DEFAULT_NUM_STEPS)
    parser.add_argument(
        "--amp", type=float, default=DEFAULT_AMP,
        help="Initial Taylor-Green velocity amplitude (default: 0.05).")
    parser.add_argument(
        "--tau", type=float, default=DEFAULT_TAU)
    parser.add_argument(
        "--samples", type=int, default=3)
    parser.add_argument(
        "--warmup-steps", type=int, default=100)
    parser.add_argument(
        "--no-cpu-openmp", action="store_true",
        help="Disable cpu_openmp in pystencils (single-threaded baseline).")
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"JSON path (default: {DEFAULT_OUT.relative_to(REPO_ROOT)}).")
    args = parser.parse_args()

    cpu_openmp = (args.target == "cpu") and not args.no_cpu_openmp
    machine = machine_tag()
    print(f"# lbmpy TGV-periodic benchmark — target: {args.target}")
    print(f"# Domain: {args.domain_size}x{args.domain_size}")
    print(f"# Steps:  {args.num_steps} (warmup {args.warmup_steps})")
    print(f"# τ:      {args.tau} (ω = {_omega_from_tau(args.tau):.4f})")
    print(f"# amp:    {args.amp}")
    print(f"# Samples: {args.samples}")
    print(f"# Machine: {machine}")
    print(f"# cpu_openmp: {cpu_openmp}")
    print()

    samples = []
    for i in range(args.samples):
        try:
            mlups = run_one(args.domain_size, args.num_steps, args.amp,
                            args.tau, args.target, cpu_openmp=cpu_openmp,
                            warmup_steps=args.warmup_steps)
            samples.append(mlups)
            print(f"  sample {i+1}: {mlups:.1f} MLUPS")
        except Exception as e:
            print(f"  sample {i+1}: FAIL ({type(e).__name__}: {e})")
            samples.append(None)

    valid = [s for s in samples if s is not None]
    if not valid:
        print("\nAll samples failed.")
        return 1
    median = statistics.median(valid)
    print(f"\n  median: {median:.1f} MLUPS")

    # Merge into the results JSON without disturbing other entries.
    doc = load_json_or_empty(args.out)
    if not doc:
        doc = {"schema_version": SCHEMA_VERSION, "results": {}}
    doc.setdefault("results", {})

    omp_threads = os.environ.get("OMP_NUM_THREADS", "default-all-cores")
    key = f"lbmpy_tgv_{args.target}_{'openmp' if cpu_openmp else 'serial'}"
    metadata = collect_run_metadata(REPO_ROOT, machine=machine)
    doc["results"][key] = mlups_result(
        samples, median, metadata,
        prefix={
            "case": "tgv_periodic",
            "domain_size": args.domain_size,
            "num_steps": args.num_steps,
            "tau": args.tau,
            "amp": args.amp,
        },
        suffix={
            "lbmpy_version": __import__("lbmpy").__version__,
            "pystencils_version": __import__("pystencils").__version__,
            "cpu_openmp": cpu_openmp,
            "omp_num_threads": omp_threads,
        },
    )

    write_json_artifact(args.out, doc)
    print(f"\nWrote: {display_path(args.out.resolve(), REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
