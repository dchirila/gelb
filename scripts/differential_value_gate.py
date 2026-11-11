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
import tempfile

import netCDF4
import numpy as np

CONFIGS = {"fortran": ("cpu_fortran_serial", None), "soa": ("cpu_highway", "soa"),
           "aos": ("cpu_highway", "aos"), "cbt": ("cpu_highway", "cbt"), "cuda": ("gpu_cuda_cpp", None)}
HEADERS = ("gelb/backends/cpp_runtime_common.hpp", "gelb/backends/cpu_highway_runtime.hpp",
           "gelb/backends/gpu_cuda_cpp_runtime.cuh")
HOST_KEYS = ("GELB_HAS_AVX512", "GELB_L3_SIZE_BYTES", "GELB_NT_STORE_THRESHOLD_BYTES",
             "GELB_NT_STORE_THRESHOLD_L3_MULTIPLIER")
RUNNERS = ("gelb/scripts/gelb-run", "scripts/gelb-run")
EXTENSIONS = {"cpu_fortran_serial": ".f90", "cpu_highway": ".cpp", "gpu_cuda_cpp": ".cu"}
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


def prepare_record(args):
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
        "runners": {name: digest((tree / name).read_bytes()) for name in RUNNERS},
        "inputs": inputs, "runs": {},
    }

    return tree, out, corpus, examples, configs, env, manifest


def record(args):
    tree, out, corpus, examples, configs, env, manifest = prepare_record(args)

    def one(job):
        index, path, config = job
        directory = out / "runs" / config / str(index)
        directory.mkdir(parents=True)
        backend, layout = CONFIGS[config]
        child_env = dict(env, GELBC_EXTRA=f"--storage-layout {layout}" if layout else "")
        cmd = [str(tree / "scripts/gelb-run"), "-b", backend, "-n", str(args.steps), "-w", "1", "-s", "42", "-k"]
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
        source = directory / (path.stem + EXTENSIONS[backend])
        try:
            entry["source_sha256"] = digest(source.read_bytes())
        except OSError as error:
            entry.update(status=125, error=f"compiled source unavailable: {error}")
        finally:
            source.unlink(missing_ok=True)
            (directory / path.stem).unlink(missing_ok=True)
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
    compatible(before, after, allowed_headers(getattr(args, "allow_changed_headers", "")))
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



def allowed_headers(value):
    paths = set(filter(None, value.split(",")))
    if paths - set(HEADERS):
        raise ValueError("allow-changed-headers must name exact runtime header paths")
    return paths


def compatible(before, after, headers=(), *, sources=False):
    keys = ("format", "settings", "compiler_versions", "highway_revision")
    if sources:
        keys += ("inputs", "runners")
    for key in keys:
        if key not in before or before[key] != after[key]:
            raise ValueError(f"incompatible manifests: {key}")
    if before["headers"].keys() != set(HEADERS) or after["headers"].keys() != set(HEADERS):
        raise ValueError("incomplete runtime header manifest")
    for name in HEADERS:
        if name not in headers and before["headers"][name] != after["headers"][name]:
            raise ValueError(f"changed runtime header: {name}")


def require_hashes(data, configs):
    if not data.get("inputs") or data["inputs"].keys() != data.get("runs", {}).keys():
        raise ValueError("incomplete source corpus")
    for name, runs in data["runs"].items():
        if runs.keys() != set(configs):
            raise ValueError(f"incomplete source configurations: {name}")
        for config, entry in runs.items():
            if not re.fullmatch(r"[0-9a-fA-F]{64}", str(entry.get("source_sha256", ""))):
                raise ValueError(f"missing or invalid source_sha256: {name} ({config})")


def generated_hash(tree, path, backend, flags, env, timeout):
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / (path.stem + EXTENSIONS[backend])
        cmd = [sys.executable, "-P", "-m", "gelb.gelbc", str(path), "--backend", backend,
               "-o", str(source), *flags]
        run = subprocess.run(cmd, cwd=tree, env=env, capture_output=True, text=True, timeout=timeout)
        if run.returncode:
            raise ValueError(f"code generation failed for {path.name} ({backend}): {run.stdout}{run.stderr}")
        return digest(source.read_bytes())


def verify_sources(args):
    before = load(args.baseline)
    require_hashes(before, args.configs.split(","))
    with tempfile.TemporaryDirectory() as tmp:
        args.out = Path(tmp)
        tree, _, corpus, examples, configs, env, after = prepare_record(args)
        compatible(before, after, sources=True)
        def one(job):
            path, config = job
            backend, layout = CONFIGS[config]
            flags = ["--num-timesteps", str(args.steps), "--write-every", "1", "--output-mode",
                     "netcdf", "--seed", "42", "--cuda-graphs"]
            flags += ["--strict-fp"] if args.strict_fp else []
            flags += ["--storage-layout", layout] if layout else []
            name = str(path.relative_to(corpus))
            actual = generated_hash(tree, path, backend, flags, env, args.timeout)
            if actual != before["runs"][name][config]["source_sha256"]:
                raise ValueError(f"source_sha256 mismatch: {name} ({config})")
        with ThreadPoolExecutor(args.jobs) as pool:
            list(pool.map(one, [(path, config) for path in examples for config in configs]))
    print(f"verified sources: {len(examples) * len(configs)}")
    return 0


def build_hashes(args):
    """Record or verify the sources generated by the two independent build sweeps."""
    backends = sorted({"cpu_fortran_serial" if b == "serial" else b for b in args.backends.split(",")})
    if not backends or set(backends) - EXTENSIONS.keys():
        raise ValueError("unknown build backend")
    target = args.build_hashes / args.kind / "manifest.json"
    before = None
    if args.command == "verify-build-hashes":
        before = json.loads(target.read_text())
        require_hashes(before, backends)
    with tempfile.TemporaryDirectory() as tmp:
        args.out = Path(tmp)
        tree, _, corpus, examples, _, env, data = prepare_record(args)
        if args.kind == "plain-build":
            flags = ["--no-slice-simplify", "--no-scalar-cse"]
            data["settings"] = {"flags": flags, "steps": 1, "write_every": 1, "backends": backends}
        else:
            flags = ["--num-timesteps", str(args.smoke_iters), "--write-every", str(max(args.smoke_iters, 1)),
                     "--nc-output", "smoke.nc"]
            data["settings"] = {"smoke_iters": args.smoke_iters, "backends": backends}
        if before is not None:
            compatible(before, data, sources=True)
        def one(job):
            path, backend = job
            name = str(path.relative_to(corpus))
            sha = generated_hash(tree, path, backend, flags, env, args.timeout)
            if before is not None and sha != before["runs"][name][backend]["source_sha256"]:
                raise ValueError(f"source_sha256 mismatch: {name} ({backend})")
            return name, backend, {"source_sha256": sha}
        with ThreadPoolExecutor(args.jobs) as pool:
            for name, backend, entry in pool.map(one, [(p, b) for p in examples for b in backends]):
                data["runs"].setdefault(name, {})[backend] = entry
        if before is None:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x") as f:
                json.dump(data, f, indent=2, sort_keys=True)
    print(f"{args.command} {args.kind}: {len(examples) * len(backends)} sources")
    return 0


def changed_files(tree, base):
    return command_output(["git", "diff", "--name-only", base, "--"], tree).splitlines()


def needs_reproducibility(paths):
    return any((p.startswith("gelb/") and not p.startswith("gelb/tests/"))
               or p.startswith("third_party/") or p in {
                   "gelb/tests/integration/test_reproducibility.py", "gelb/tests/integration/conftest.py",
                   "gelb/tests/integration/_toolchain.py", "scripts/gelb-run", "pyproject.toml", "uv.lock"}
               for p in paths)


def check_base_files(args):
    allowed = allowed_headers(args.allow_changed_headers)
    names = RUNNERS if args.command == "check-runners" else HEADERS
    if args.command == "check-runners":
        if allowed:
            raise ValueError("header exceptions cannot be combined with a skip")
        names = (*HEADERS, *RUNNERS)
    for name in names:
        expected = subprocess.check_output(["git", "show", f"{args.base}:{name}"], cwd=args.tree)
        if name not in allowed and (args.tree / name).read_bytes() != expected:
            raise ValueError(f"changed dependency: {name}")
    return 0

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("record", "verify-sources", "record-build-hashes", "verify-build-hashes"):
        p = sub.add_parser(command)
        p.add_argument("--tree", type=Path, required=True)
        if command == "record":
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
        if command == "verify-sources":
            p.add_argument("--baseline", type=Path, required=True)
        if command.endswith("build-hashes"):
            p.add_argument("--build-hashes", type=Path, required=True)
            p.add_argument("--kind", choices=("smoke", "plain-build"), required=True)
            p.add_argument("--backends", default=",".join(EXTENSIONS))
            p.add_argument("--smoke-iters", type=int, default=10)
    p = sub.add_parser("compare-baseline")
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--allow-changed", default="", help="comma-separated exact corpus-relative filenames")
    p.add_argument("--allow-changed-headers", default="")
    p = sub.add_parser("compare-backends")
    p.add_argument("--run-dir", type=Path, required=True)
    for command in ("check-headers", "check-runners", "reproducibility-needed"):
        p = sub.add_parser(command)
        p.add_argument("--tree", type=Path, required=True)
        p.add_argument("--base", required=True)
        p.add_argument("--allow-changed-headers", default="")
    args = parser.parse_args()
    try:
        if hasattr(args, "steps") and min(args.steps, args.jobs, args.omp_threads, args.timeout) < 1:
            raise ValueError("steps, jobs, threads and timeout must be positive")
        if args.command == "record" and args.exact_probes and args.steps > 3:
            raise ValueError("exact-intermediate fixtures are proved only for 1..3 steps")
        return {"record": record, "compare-baseline": compare_baseline,
                "compare-backends": compare_backends, "verify-sources": verify_sources,
                "record-build-hashes": build_hashes, "verify-build-hashes": build_hashes,
                "check-headers": check_base_files, "check-runners": check_base_files,
                "reproducibility-needed": lambda a: print("RUN" if needs_reproducibility(changed_files(a.tree, a.base)) else "SKIP") or 0}[args.command](args)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
