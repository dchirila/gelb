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
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import pathlib
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / 'examples'
VARIANTS = ('default', 'soa', 'aos', 'cbt', 'plain', 'strict')
EXTRA = []

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
            '--seed', '42', *EXTRA,
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


def compare_directories(baseline, candidate, allowed='', mode='byte'):
    before = json.loads((baseline / 'MANIFEST.json').read_text())
    after = json.loads((candidate / 'MANIFEST.json').read_text())
    allowed = set(filter(None, allowed.split(',')))
    names = {emission_name(e, b): str(e.relative_to(EXAMPLES_DIR))
             for e in discover_examples() for b in BACKENDS}
    if allowed - set(names.values()):
        raise ValueError('allow-changed must name exact corpus-relative example filenames')
    def sources(directory):
        return {p.name: p for p in directory.iterdir() if p.suffix in ('.cpp', '.cu', '.f90')}
    a, b = sources(baseline), sources(candidate)
    if (not a or a.keys() != b.keys() or before['failures'] != after['failures']
            or before['examples'] != after['examples'] or before['emissions'] != len(a)
            or after['emissions'] != len(b)):
        raise ValueError('incomplete or different emission sets/manifests')
    bad = 0
    for name in sorted(a):
        left, right = a[name].read_bytes(), b[name].read_bytes()
        same = left == right
        if not same and mode == 'structural':
            # Use the same alpha-renaming contract as the standalone comparator.
            from scripts.emission_structural_diff import equivalent
            same = equivalent(left.decode(), right.decode(), a[name].suffix)
        if not same:
            approved = names.get(name) in allowed
            print(f"{'ALLOWED' if approved else 'DIFF'}: {name}")
            bad += not approved
    print(f'{mode} comparison: {len(a)} files, {bad} unapproved differences')
    return int(bool(bad))


def cmd_compare(outdir, processes, candidate=None, allowed='', mode='byte'):
    if candidate is not None:
        return compare_directories(outdir, candidate, allowed, mode)
    with tempfile.TemporaryDirectory() as tmp:
        current = pathlib.Path(tmp)
        cmd_snapshot(current, processes)
        return compare_directories(outdir, current, allowed, mode)


def syntax(outdir, processes):
    files = sorted(p for p in outdir.iterdir() if p.suffix in ('.cpp', '.f90'))
    if not files:
        raise ValueError('no candidate sources to syntax-check')
    nc = subprocess.check_output(['nc-config', '--includedir'], text=True).strip()
    nf = subprocess.check_output(['nf-config', '--includedir'], text=True).strip()
    def one(path):
        if path.suffix == '.cpp':
            cmd = [os.environ.get('GELB_CXX', 'g++'), '-std=c++17', '-fopenmp', '-march=native',
                   '-fsyntax-only', '-I', str(REPO_ROOT / 'third_party/highway'),
                   '-I', str(REPO_ROOT / 'gelb/backends'), '-I', nc, str(path.resolve())]
        else:
            cmd = ['gfortran', '-fsyntax-only', '-ffree-line-length-none', '-I', nf, str(path.resolve())]
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True)
        if result.returncode:
            print(f'SYNTAX FAIL {path.name}: {result.stderr[:500]}')
        return result.returncode != 0
    with ThreadPoolExecutor(processes) as pool:
        bad = sum(pool.map(one, files))
    print(f'syntax: {len(files) - bad} ok, {bad} failed of {len(files)}')
    return int(bool(bad))


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
    parser.add_argument('mode', choices=['snapshot', 'compare', 'diff-backends', 'syntax'])
    parser.add_argument('-o', '--outdir', type=pathlib.Path,
                        help='snapshot directory (snapshot / compare)')
    parser.add_argument('-j', '--processes', type=int, default=8)
    parser.add_argument('--json', type=pathlib.Path, default=None,
                        help='diff-backends: also write a JSON report here')
    parser.add_argument('--variant', choices=VARIANTS, default='default')
    parser.add_argument('--candidate', type=pathlib.Path)
    parser.add_argument('--allow-changed', default='')
    parser.add_argument('--emission-mode', choices=('byte', 'structural'), default='byte')
    args = parser.parse_args()
    if args.variant in ('soa', 'aos', 'cbt'):
        EXTRA[:] = ['--storage-layout', args.variant]
        for backend in list(BACKENDS):
            if backend != 'cpu_highway':
                del BACKENDS[backend]
    elif args.variant == 'plain':
        EXTRA[:] = ['--no-slice-simplify', '--no-scalar-cse']
    elif args.variant == 'strict':
        EXTRA[:] = ['--strict-fp']
    if args.mode == 'diff-backends':
        return cmd_diff_backends(args.processes, args.json)
    if args.outdir is None:
        parser.error(f'{args.mode} needs -o/--outdir')
    if args.mode == 'syntax':
        return syntax(args.outdir, args.processes)
    if args.mode == 'snapshot':
        return cmd_snapshot(args.outdir, args.processes)
    return cmd_compare(args.outdir, args.processes, args.candidate, args.allow_changed, args.emission_mode)


if __name__ == '__main__':
    sys.path.insert(0, str(REPO_ROOT))
    sys.exit(main())
