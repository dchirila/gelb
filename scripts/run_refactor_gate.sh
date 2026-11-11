#!/usr/bin/env bash
# Run the local compiler-refactoring gate against caller-supplied baselines.
set -euo pipefail
tree=$(pwd) base= snapshots= snapshot_tool= baseline_values= out=
jobs=12 omp_threads=4 allow_gpu=0 allow_avx=0 fuzz_dir= fuzz_baseline=
usage() {
    cat <<'EOF'
Usage: run_refactor_gate.sh --tree TREE --base REV --snapshots DIR
  --snapshot-tool FILE --baseline-values DIR --out DIR [--jobs 12]
  [--omp-threads 4] [--allow-no-gpu] [--allow-no-avx512]
  [--fuzz-dir DIR --fuzz-baseline DIR]
Snapshots: DIR/{default,soa,aos,plain}; value baselines: DIR/{default,strict}.
The output directory must be new. Documentation builds use offline intersphinx.
EOF
}
while (($#)); do
    case "$1" in
        --tree) tree=$2; shift 2;; --base) base=$2; shift 2;;
        --snapshots) snapshots=$2; shift 2;; --snapshot-tool) snapshot_tool=$2; shift 2;;
        --baseline-values) baseline_values=$2; shift 2;; --out) out=$2; shift 2;;
        --jobs) jobs=$2; shift 2;; --omp-threads) omp_threads=$2; shift 2;;
        --allow-no-gpu) allow_gpu=1; shift;; --allow-no-avx512) allow_avx=1; shift;;
        --fuzz-dir) fuzz_dir=$2; shift 2;; --fuzz-baseline) fuzz_baseline=$2; shift 2;;
        -h|--help) usage; exit 0;; *) usage >&2; exit 2;;
    esac
done
[[ -n $base && -d $snapshots && -f $snapshot_tool && -d $baseline_values && -n $out ]] || { usage >&2; exit 2; }
[[ $jobs =~ ^[1-9][0-9]*$ && $omp_threads =~ ^[1-9][0-9]*$ ]] || exit 2
[[ -z $fuzz_dir || ( -d $fuzz_dir && -d $fuzz_baseline ) ]] || { echo 'fuzz runs need both corpus and baseline' >&2; exit 2; }
tree=$(realpath "$tree") snapshots=$(realpath "$snapshots") snapshot_tool=$(realpath "$snapshot_tool")
baseline_values=$(realpath "$baseline_values") out=$(realpath -m "$out")
if [[ -n $fuzz_dir ]]; then fuzz_dir=$(realpath "$fuzz_dir"); fuzz_baseline=$(realpath "$fuzz_baseline"); fi
mkdir "$out"
mkdir "$out/logs"
cd "$tree"
export OMP_NUM_THREADS=$omp_threads OMP_DYNAMIC=FALSE QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg
unset GELB_FFLAGS GELB_CXXFLAGS GELB_NVCC_FLAGS GELBC_EXTRA
run() {
    local label=$1; shift
    printf 'Running %s\n' "$label"
    printf '%q ' "$@" > "$out/logs/$label.command"
    if "$@" > "$out/logs/$label.log" 2>&1; then
        printf '%s: PASS\n' "$label" | tee -a "$out/results.txt"
    else
        printf '%s: FAIL\n' "$label" | tee -a "$out/results.txt"
        tail -n 40 "$out/logs/$label.log" >&2
        return 1
    fi
}
uv run python - "$tree" "$allow_gpu" "$allow_avx" "$out/configs.txt" <<'PY' | tee "$out/logs/preflight.log"
from pathlib import Path
import sys
import gelb
from gelb.backends.highway.common import _detect_avx512_available
from gelb.tests.integration._toolchain import HAS_NVCC, HAS_NVIDIA_GPU
tree, allow_gpu, allow_avx, output = sys.argv[1:]
path = Path(gelb.__file__).resolve()
assert path.is_relative_to(Path(tree)), f"wrong gelb: {path}"
print(f"gelb from {path}")
gpu, avx = HAS_NVCC and HAS_NVIDIA_GPU, _detect_avx512_available()
assert gpu or allow_gpu == '1', 'CUDA compiler/GPU missing; use --allow-no-gpu explicitly'
assert avx or allow_avx == '1', 'AVX-512 missing; use --allow-no-avx512 explicitly'
configs = ['fortran', 'soa', 'aos'] + (['cbt'] if avx else []) + (['cuda'] if gpu else [])
Path(output).write_text(','.join(configs))
print('configurations:', ','.join(configs))
PY
configs=$(cat "$out/configs.txt")
run headers uv run python - "$base" <<'PY'
import hashlib
from pathlib import Path
import subprocess
import sys
from scripts.differential_value_gate import HEADERS
for name in HEADERS:
    expected = subprocess.check_output(['git', 'show', f'{sys.argv[1]}:{name}'])
    actual = Path(name).read_bytes()
    assert actual == expected, f'changed runtime header: {name}'
    print(hashlib.sha256(actual).hexdigest(), name)
PY
for variant in default soa aos plain; do
    run "emission-$variant" uv run python "$snapshot_tool" compare -j 16 -o "$snapshots/$variant" --variant "$variant"
    run "syntax-$variant" uv run python "$snapshot_tool" syntax -o "$snapshots/$variant"
done
run diff-backends uv run python "$tree/scripts/emission_snapshot.py" diff-backends -j 16
run unit uv run pytest -q --durations=25 "$tree/gelb/tests/unit"
smoke=serial,cpu_highway
if [[ ,$configs, == *,cuda,* ]]; then smoke+=,gpu_cuda_cpp; fi
run integration uv run pytest -q -n "$jobs" --durations=25 "$tree/gelb/tests/integration" --run-smoke --smoke-backends="$smoke"
run numeric uv run pytest -q --durations=25 "$tree/gelb/tests/numeric"
run docs uv run python - "$tree/docs" "$out/html" <<'PY'
from pathlib import Path
import sys
from sphinx.application import Sphinx
docs, out = map(Path, sys.argv[1:])
app = Sphinx(docs, docs, out, out / '.doctrees', 'html', freshenv=True,
             confoverrides={'intersphinx_mapping': {}}, warningiserror=True, keep_going=True)
app.build(force_all=True)
raise SystemExit(app.statuscode)
PY
value_gate=$tree/scripts/differential_value_gate.py
for mode in default strict; do
    flags=(); if [[ $mode == strict ]]; then flags+=(--strict-fp); fi
    run "values-$mode" uv run python "$value_gate" record --tree "$tree" --out "$out/values/$mode" --configs "$configs" --omp-threads "$omp_threads" -j "$jobs" "${flags[@]}"
    run "baseline-$mode" uv run python "$value_gate" compare-baseline --baseline "$baseline_values/$mode" --candidate "$out/values/$mode"
    if [[ -n $fuzz_dir ]]; then
        run "fuzz-$mode" uv run python "$value_gate" record --tree "$tree" --out "$out/fuzz/$mode" --corpus "$fuzz_dir" --configs "$configs" --omp-threads "$omp_threads" -j "$jobs" "${flags[@]}"
        run "fuzz-baseline-$mode" uv run python "$value_gate" compare-baseline --baseline "$fuzz_baseline/$mode" --candidate "$out/fuzz/$mode"
    fi
done
run layouts uv run python "$value_gate" compare-backends --run-dir "$out/values/strict"
run exact-record uv run python "$value_gate" record --tree "$tree" --out "$out/exact" --exact-probes --strict-fp --configs "$configs" --omp-threads "$omp_threads" -j "$jobs"
run exact-backends uv run python "$value_gate" compare-backends --run-dir "$out/exact"
printf 'Gate passed; logs: %s\n' "$out/logs"
