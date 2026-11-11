#!/usr/bin/env python3
"""Record exact NetCDF values, compare revisions, or check strict backend contracts."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading

import netCDF4
import numpy as np

CONFIGS = {"fortran": ("cpu_fortran_serial", None), "soa": ("cpu_highway", "soa"),
           "aos": ("cpu_highway", "aos"), "cbt": ("cpu_highway", "cbt"), "cuda": ("gpu_cuda_cpp", None)}
HEADERS = ("gelb/backends/cpp_runtime_common.hpp", "gelb/backends/cpu_highway_runtime.hpp",
           "gelb/backends/gpu_cuda_cpp_runtime.cuh")
HOST_KEYS = ("GELB_HAS_AVX512", "GELB_L3_SIZE_BYTES", "GELB_NT_STORE_THRESHOLD_BYTES",
             "GELB_NT_STORE_THRESHOLD_L3_MULTIPLIER")
NC_LOCK = threading.Lock()  # HDF5/NetCDF reads cannot run concurrently in threads.


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(path):
    result = {}
    with NC_LOCK, netCDF4.Dataset(path) as nc:
        nc.set_auto_mask(False)
        for name, var in nc.variables.items():
            a = np.array(var[:], copy=True)
            nan = np.isnan(a) if np.issubdtype(a.dtype, np.floating) else np.zeros(a.shape, dtype=bool)
            sign = np.signbit(a) & ~nan if np.issubdtype(a.dtype, np.floating) else np.zeros(a.shape, dtype=bool)
            # The contract ignores NaN payload/sign, but retains signed zero and all int64 bits.
            if nan.any():
                a[nan] = np.nan
            result[name] = {"dims": list(var.dimensions), "shape": list(a.shape), "dtype": str(var.dtype),
                            "values": digest(a.tobytes()), "signbit": digest(sign.tobytes()), "nan": digest(nan.tobytes())}
    return result


def command_output(args, cwd):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"{args}: {result.stderr}")
    return result.stdout.strip()


def exact_program(kind):
    # For at most three steps, every intermediate is a multiple of 1/64
    # with magnitude < 2048: all intermediates fit exactly even in binary32.
    return f'''simulation_description("exact reduction intermediates");
global_constants {{ const array[{kind}, 4] W = {{0.5, 0.25, 0.125, 0.0625}}; }}
lattices {{ lattice f(1, 4, {kind}, 67, false); }}
initializer I {{ f.out[x | :] = real(x) + 1.0; }}
dynamic D {{
    array[{kind}, 4] a = f.in[x | :];
    f.out[x | 0] = dot_prod(W, a) + sum(a);
    f.out[x | 1:3] = f.in[x | 1:3];
}}
gauge G -> ({kind} value) {{ value = f.in[x | 0]; }}
node_classes {{ node_class BULK(I, D, G); }}
geometry {{ nodes[:] = BULK; }}
'''


def record(args):
    import gelb
    from gelb.backends.highway import common
    tree, out = args.tree.resolve(), args.out.resolve()
    imported = Path(gelb.__file__).resolve()
    if not imported.is_relative_to(tree):
        raise ValueError(f"wrong gelb import: {imported}, expected inside {tree}")
    print(f"gelb from {imported}", flush=True)
    configs = args.configs.split(",")
    if not configs or len(set(configs)) != len(configs) or set(configs) - CONFIGS.keys():
        raise ValueError("configs must be distinct names from " + ",".join(CONFIGS))
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"refusing to overwrite nonempty output: {out}")
    out.mkdir(parents=True, exist_ok=True)
    corpus = args.corpus.resolve() if args.corpus else tree / "examples"
    if args.exact_probes:
        corpus = out / "inputs"
        corpus.mkdir()
        for kind in ("real", "real32"):
            (corpus / f"exact_{kind}.gelb").write_text(exact_program(kind))
    examples = sorted(corpus.rglob("*.gelb"))
    if not examples:
        raise ValueError(f"no programs in {corpus}")
    inputs = {}
    for path in examples:
        code = re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"', "", path.read_text())
        inputs[str(path.relative_to(corpus))] = {"sha256": digest(path.read_bytes()),
                                               "random": bool(re.search(r"\brandom\s*\(", code))}
    versions = {}
    for compiler in ("g++", "gfortran", "nvcc", "nc-config", "nf-config"):
        try:
            versions[compiler] = command_output([compiler, "--version"], tree)
        except (OSError, RuntimeError):
            versions[compiler] = "unavailable"
    env = dict(os.environ, GELB_PYTHON=sys.executable, OMP_NUM_THREADS=str(args.omp_threads), OMP_DYNAMIC="FALSE")
    for key in ("GELB_FFLAGS", "GELB_CXXFLAGS", "GELB_NVCC_FLAGS", "GELBC_EXTRA"):
        env.pop(key, None)
    manifest = {
        "format": 1, "revision": command_output(["git", "rev-parse", "HEAD"], tree),
        "gelb_file": str(imported), "python": sys.version, "compiler_versions": versions,
        "highway_revision": command_output(["git", "-C", "third_party/highway", "rev-parse", "HEAD"], tree),
        "headers": {name: digest((tree / name).read_bytes()) for name in HEADERS},
        "settings": {"configs": sorted(configs), "strict_fp": args.strict_fp, "steps": args.steps,
                     "write_every": 1, "seed": 42, "OMP_NUM_THREADS": args.omp_threads, "OMP_DYNAMIC": "FALSE",
                     "exact_intermediates": args.exact_probes,
                     "host_overrides": {key: env.get(key) for key in HOST_KEYS},
                     "avx512": common._detect_avx512_available(), "l3_bytes": common._detect_l3_size_bytes(),
                     "nt_store_bytes": common._nt_store_threshold_bytes()},
        "inputs": inputs, "runs": {},
    }

    def one(job):
        index, path, config = job
        directory = out / "runs" / config / str(index)
        directory.mkdir(parents=True)
        backend, layout = CONFIGS[config]
        child_env = dict(env, GELBC_EXTRA=f"--storage-layout {layout}" if layout else "")
        cmd = [str(tree / "scripts/gelb-run"), "-b", backend, "-n", str(args.steps), "-w", "1", "-s", "42"]
        cmd += (["--strict-fp"] if args.strict_fp else []) + [str(path)]
        try:
            with subprocess.Popen(cmd, cwd=directory, env=child_env, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, start_new_session=True) as run:
                try:
                    stdout, stderr = run.communicate(timeout=args.timeout)
                    status, log = run.returncode, stdout + stderr
                except subprocess.TimeoutExpired:
                    # The runner spawns compilers and executables: kill its whole group.
                    try:
                        os.killpg(run.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    stdout, stderr = run.communicate()
                    status, log = 124, stdout + stderr + f"\ntimeout after {args.timeout}s"
        except OSError as error:
            status, log = 127, str(error)
        (directory / "run.log").write_text(log)
        (directory / "command.json").write_text(json.dumps(cmd) + "\n")
        outputs = sorted(directory.glob("*.nc"))
        entry = {"status": status, "variables": {}, "log": str((directory / "run.log").relative_to(out))}
        if status == 0:
            if len(outputs) != 1:
                entry.update(status=125, error=f"expected one NetCDF file, found {len(outputs)}")
            else:
                try:
                    entry["variables"] = fingerprint(outputs[0])
                except Exception as error:
                    entry.update(status=125, error=str(error))
        name = str(path.relative_to(corpus))
        print(f"{config}: {name}: status {entry['status']}", flush=True)
        return name, config, entry

    jobs = [(i, path, config) for i, path in enumerate(examples) for config in configs]
    with ThreadPoolExecutor(args.jobs) as pool:
        for name, config, entry in pool.map(one, jobs):
            manifest["runs"].setdefault(name, {})[config] = entry
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    bad = sum(entry["status"] != 0 for runs in manifest["runs"].values() for entry in runs.values())
    print(f"record: {len(jobs) - bad} passed, {bad} failed")
    return int(bad != 0)


def load(directory):
    data = json.loads((directory / "manifest.json").read_text())
    if data["format"] != 1 or not data["inputs"] or data["inputs"].keys() != data["runs"].keys():
        raise ValueError("invalid manifest or incomplete corpus")
    expected = set(data["settings"]["configs"])
    if not expected or expected - CONFIGS.keys():
        raise ValueError("invalid configurations")
    for name, runs in data["runs"].items():
        if runs.keys() != expected or any(r["status"] != 0 or not r["variables"] for r in runs.values()):
            raise ValueError(f"missing or unsuccessful run: {name}")
    return data


def compare_baseline(args):
    before, after = load(args.baseline), load(args.candidate)
    allowed = set(filter(None, args.allow_changed.split(",")))
    if allowed - before["inputs"].keys():
        raise ValueError("allow-changed must name exact corpus-relative filenames")
    for key in ("format", "settings", "headers", "compiler_versions", "highway_revision"):
        if before[key] != after[key]:
            raise ValueError(f"incompatible manifests: {key}")
    if before["inputs"].keys() != after["inputs"].keys():
        raise ValueError("different corpus file sets")
    failures = []
    for name, runs in before["runs"].items():
        changed = before["inputs"][name] != after["inputs"][name]
        changed |= any(entry["variables"] != after["runs"][name][config]["variables"] for config, entry in runs.items())
        if changed:
            print(f"{'ALLOWED' if name in allowed else 'VALUE DIFF'}: {name}")
            if name not in allowed:
                failures.append(name)
    print(f"baseline comparison: {len(failures)} unapproved differences")
    return int(bool(failures))


def compare_backends(args):
    data = load(args.run_dir)
    if not data["settings"]["strict_fp"]:
        raise ValueError("backend comparison requires --strict-fp recordings")
    configs = set(data["settings"]["configs"])
    selected = configs if data["settings"]["exact_intermediates"] else configs & {"soa", "aos", "cbt"}
    if len(selected) < 2:
        raise ValueError("backend comparison requires at least two applicable configurations")
    bad, checked = 0, 0
    for name, runs in data["runs"].items():
        if data["inputs"][name]["random"]:
            continue
        reference = runs[sorted(selected)[0]]["variables"]
        checked += 1
        if any(runs[c]["variables"] != reference for c in selected):
            print(f"BACKEND DIFF: {name}")
            bad += 1
    if not checked:
        raise ValueError("no non-random programs were compared")
    print(f"backend comparison ({','.join(sorted(selected))}): {checked} programs, {bad} differences")
    return int(bad != 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("record")
    p.add_argument("--tree", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--configs", default=",".join(CONFIGS))
    p.add_argument("--strict-fp", action="store_true")
    p.add_argument("--omp-threads", type=int, default=4)
    p.add_argument("-n", "--steps", type=int, default=3)
    p.add_argument("-j", "--jobs", type=int, default=4)
    p.add_argument("--timeout", type=int, default=900)
    corpus = p.add_mutually_exclusive_group()
    corpus.add_argument("--corpus", type=Path, help="run this .gelb corpus instead of examples/")
    corpus.add_argument("--exact-probes", action="store_true", help="run built-in exact-intermediate fixtures")
    p = sub.add_parser("compare-baseline")
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--allow-changed", default="", help="comma-separated exact corpus-relative filenames")
    p = sub.add_parser("compare-backends")
    p.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "record" and min(args.steps, args.jobs, args.omp_threads, args.timeout) < 1:
            raise ValueError("steps, jobs, threads and timeout must be positive")
        if args.command == "record" and args.exact_probes and args.steps > 3:
            raise ValueError("exact-intermediate fixtures are proved only for 1..3 steps")
        return {"record": record, "compare-baseline": compare_baseline,
                "compare-backends": compare_backends}[args.command](args)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
