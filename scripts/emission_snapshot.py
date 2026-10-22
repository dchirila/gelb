#!/usr/bin/env python3
"""Golden-emission snapshot/compare harness for backend work.

Generates the backend source emitted for every public example across
all three backends and either stores it as a snapshot directory or
byte-compares a fresh generation against an existing snapshot.  The
contract for backend work is *byte-identical emission*: any diff is
either a bug or a deliberate, explained change.

Usage:
    uv run python scripts/emission_snapshot.py snapshot -o /tmp/emissions_baseline
    uv run python scripts/emission_snapshot.py compare  -o /tmp/emissions_baseline
    uv run python scripts/emission_snapshot.py diff-backends [--json report.json]

Exit code 0 when a compare finds no differences; 1 otherwise.  Examples
that fail to compile are recorded in the snapshot manifest -- a change
must not alter *which* examples fail either.

``diff-backends`` needs no baseline: it compiles every example with every
backend and reports the examples whose outcome differs between backends
(compiles on one, fails on another, or fails with different errors).  A
frontend error is the same on every backend, so a divergence is by
construction a backend-specific gap.  Exit code 1 when any example
diverges -- the cross-backend compile gate.
"""

from __future__ import annotations

import argparse
import difflib
import json
import multiprocessing as mp
import pathlib
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / 'examples'

BACKENDS = {
    'cpu_fortran_serial': '.f90',
    'cpu_highway': '.cpp',
    'gpu_cuda_cpp': '.cu',
}

def discover_examples() -> list[pathlib.Path]:
    return sorted(EXAMPLES_DIR.rglob('*.gelb'))


def emission_name(example: pathlib.Path, backend: str) -> str:
    rel = example.relative_to(REPO_ROOT)
    flat = str(rel.with_suffix('')).replace('/', '__')
    return f'{flat}__{backend}{BACKENDS[backend]}'


def generate_one(job: tuple[str, str]) -> tuple[str, str, str | None, str]:
    """Worker: (example, backend) -> (example, backend, source|None, error)."""
    example, backend = job
    from gelb.gelbc import cli as gelbc_cli

    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / ('out' + BACKENDS[backend])
        args = [
            example,
            '--backend', backend,
            '-o', str(out),
            '--num-timesteps', '10',
            '--write-every', '10',
            '--nc-output', 'out.nc',
            '--seed', '42',
        ]
        try:
            gelbc_cli.main(args=args, standalone_mode=False)
        except Exception as exc:  # noqa: BLE001 - record any failure
            return example, backend, None, f'{type(exc).__name__}: {exc}'
        return example, backend, out.read_text(), ''


def generate_all(jobs: list[tuple[str, str]], processes: int) -> list:
    with mp.Pool(processes) as pool:
        return pool.map(generate_one, jobs)


def cmd_snapshot(outdir: pathlib.Path, processes: int) -> int:
    outdir.mkdir(parents=True, exist_ok=True)
    examples = discover_examples()
    jobs = [(str(e), b) for e in examples for b in BACKENDS]
    print(f'Generating {len(jobs)} emissions '
          f'({len(examples)} examples x {len(BACKENDS)} backends) ...')
    failures = {}
    n_ok = 0
    for example, backend, source, error in generate_all(jobs, processes):
        name = emission_name(pathlib.Path(example), backend)
        if source is None:
            failures[name] = error
            continue
        (outdir / name).write_text(source)
        n_ok += 1
    manifest = {
        'examples': len(examples),
        'emissions': n_ok,
        'failures': failures,
    }
    (outdir / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2))
    print(f'Snapshot: {n_ok} emissions, {len(failures)} expected-fail '
          f'-> {outdir}')
    for name, err in sorted(failures.items()):
        print(f'  FAIL (recorded): {name}: {err[:100]}')
    return 0


def cmd_compare(outdir: pathlib.Path, processes: int) -> int:
    manifest = json.loads((outdir / 'MANIFEST.json').read_text())
    examples = discover_examples()
    jobs = [(str(e), b) for e in examples for b in BACKENDS]
    print(f'Regenerating {len(jobs)} emissions for comparison ...')
    diffs = []
    for example, backend, source, error in generate_all(jobs, processes):
        name = emission_name(pathlib.Path(example), backend)
        baseline_file = outdir / name
        was_failure = name in manifest['failures']
        if source is None:
            if not was_failure:
                diffs.append(f'NEW FAILURE: {name}: {error[:200]}')
            continue
        if was_failure:
            diffs.append(f'UNEXPECTED PASS (baseline failed): {name}')
            continue
        if not baseline_file.exists():
            diffs.append(f'NEW EMISSION (not in baseline): {name}')
            continue
        baseline = baseline_file.read_text()
        if source != baseline:
            delta = list(difflib.unified_diff(
                baseline.splitlines(), source.splitlines(),
                'baseline', 'current', lineterm='', n=1))
            head = '\n    '.join(delta[:12])
            diffs.append(f'DIFF: {name}\n    {head}')
    if diffs:
        print(f'\n{len(diffs)} emission difference(s):')
        for d in diffs:
            print(f'  {d}')
        return 1
    print(f'OK: all emissions byte-identical to {outdir} '
          f'({manifest["emissions"]} files, '
          f'{len(manifest["failures"])} expected-fail unchanged).')
    return 0


def cmd_diff_backends(processes: int, json_out: pathlib.Path | None) -> int:
    examples = discover_examples()
    jobs = [(str(e), b) for e in examples for b in BACKENDS]
    print(f'Compiling {len(jobs)} (example, backend) pairs '
          f'({len(examples)} examples x {len(BACKENDS)} backends) ...')
    outcome: dict[str, dict[str, str]] = {}
    for example, backend, source, error in generate_all(jobs, processes):
        rel = str(pathlib.Path(example).relative_to(REPO_ROOT))
        outcome.setdefault(rel, {})[backend] = error   # '' means compiled
    divergent, uniform_failures = [], []
    for rel in sorted(outcome):
        errors = outcome[rel]
        if not any(errors.values()):
            continue
        if len(set(errors.values())) == 1:
            uniform_failures.append((rel, next(iter(errors.values()))))
        else:
            divergent.append((rel, errors))
    print(f'{len(examples) - len(divergent) - len(uniform_failures)} examples '
          f'compile on every backend; {len(uniform_failures)} fail identically '
          f'everywhere; {len(divergent)} diverge.')
    for rel, error in uniform_failures:
        print(f'  SAME-FAIL  {rel}: {error[:120]}')
    for rel, errors in divergent:
        print(f'  DIVERGENT  {rel}')
        for backend in BACKENDS:
            error = errors.get(backend, '')
            print(f'      {backend:<20} {"ok" if not error else error[:140]}')
    if json_out is not None:
        json_out.write_text(json.dumps(
            {'examples': len(examples), 'backends': list(BACKENDS),
             'divergent': dict(divergent),
             'uniform_failures': dict(uniform_failures)}, indent=2))
        print(f'JSON report -> {json_out}')
    return 1 if divergent else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['snapshot', 'compare', 'diff-backends'])
    parser.add_argument('-o', '--outdir', type=pathlib.Path,
                        help='snapshot directory (snapshot / compare)')
    parser.add_argument('-j', '--processes', type=int, default=8)
    parser.add_argument('--json', type=pathlib.Path, default=None,
                        help='diff-backends: also write a JSON report here')
    args = parser.parse_args()
    if args.mode == 'diff-backends':
        return cmd_diff_backends(args.processes, args.json)
    if args.outdir is None:
        parser.error(f'{args.mode} needs -o/--outdir')
    if args.mode == 'snapshot':
        return cmd_snapshot(args.outdir, args.processes)
    return cmd_compare(args.outdir, args.processes)


if __name__ == '__main__':
    sys.exit(main())
