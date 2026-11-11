#!/usr/bin/env bash
# Run the local compiler-refactoring gate against caller-supplied baselines.
set -euo pipefail
tree=$(pwd) base= snapshots= snapshot_tool= baseline_values= out=
jobs=12 omp_threads=4 allow_gpu=0 allow_avx=0 fuzz_dir= fuzz_baseline=
extra_snapshots= build_hashes= skip_values=0 skip_smoke=0 skip_plain=0
allow_emission= allow_value= allow_headers= emission_mode=byte smoke_iters=10 smoke_backends=
usage() {
    cat <<'EOF'
Usage: run_refactor_gate.sh --tree TREE --base REV --snapshots DIR
  --baseline-values DIR --out DIR [--snapshot-tool FILE] [--extra-snapshots DIR]
  [--jobs 12] [--omp-threads 4] [--allow-no-gpu] [--allow-no-avx512]
  [--skip-values] [--skip-smoke] [--skip-plain-build] [--build-hashes DIR]
  [--smoke-iters 10] [--smoke-backends serial,cpu_highway,gpu_cuda_cpp]
  [--emission-mode byte|structural] [--allow-emission-changed EXAMPLES]
  [--allow-value-changed EXAMPLES] [--allow-changed-headers PATHS]
  [--fuzz-dir DIR --fuzz-baseline DIR]
Snapshots: default, soa, aos, cbt, plain, strict directories (or emis_* names).
Build hashes default to snapshots/build_hashes. Output must be new.
Skip guards fail immediately (exit 1); matching evidence logs SKIP, never PASS.
Header exceptions name exact runtime-header paths and forbid all skip flags.
EOF
}
while (($#)); do
    case "$1" in
        --tree) tree=$2; shift 2;; --base) base=$2; shift 2;;
        --snapshots) snapshots=$2; shift 2;; --snapshot-tool) snapshot_tool=$2; shift 2;;
        --baseline-values) baseline_values=$2; shift 2;; --out) out=$2; shift 2;;
        --extra-snapshots) extra_snapshots=$2; shift 2;; --build-hashes) build_hashes=$2; shift 2;;
        --jobs) jobs=$2; shift 2;; --omp-threads) omp_threads=$2; shift 2;;
        --skip-values) skip_values=1; shift;; --skip-smoke) skip_smoke=1; shift;;
        --skip-plain-build) skip_plain=1; shift;;
        --allow-emission-changed) allow_emission=$2; shift 2;;
        --allow-value-changed) allow_value=$2; shift 2;;
        --allow-changed-headers) allow_headers=$2; shift 2;;
        --emission-mode) emission_mode=$2; shift 2;;
        --smoke-iters) smoke_iters=$2; shift 2;; --smoke-backends) smoke_backends=$2; shift 2;;
        --allow-no-gpu) allow_gpu=1; shift;; --allow-no-avx512) allow_avx=1; shift;;
        --fuzz-dir) fuzz_dir=$2; shift 2;; --fuzz-baseline) fuzz_baseline=$2; shift 2;;
        -h|--help) usage; exit 0;; *) usage >&2; exit 2;;
    esac
done
[[ -n $base && -d $snapshots && -d $baseline_values && -n $out ]] || { usage >&2; exit 2; }
[[ $jobs =~ ^[1-9][0-9]*$ && $omp_threads =~ ^[1-9][0-9]*$ && $smoke_iters =~ ^[0-9]+$ ]] || exit 2
[[ $emission_mode == byte || $emission_mode == structural ]] || exit 2
[[ -z $fuzz_dir || ( -d $fuzz_dir && -d $fuzz_baseline ) ]] || { echo 'fuzz runs need both corpus and baseline' >&2; exit 2; }
tree=$(realpath "$tree") snapshots=$(realpath "$snapshots")
snapshot_tool=$(realpath "${snapshot_tool:-$tree/scripts/emission_snapshot.py}")
build_hashes=$(realpath -m "${build_hashes:-$snapshots/build_hashes}")
baseline_values=$(realpath "$baseline_values") out=$(realpath -m "$out")
[[ -z $extra_snapshots ]] || extra_snapshots=$(realpath "$extra_snapshots")
if [[ -n $fuzz_dir ]]; then fuzz_dir=$(realpath "$fuzz_dir"); fuzz_baseline=$(realpath "$fuzz_baseline"); fi
mkdir "$out"
mkdir "$out/logs" "$out/emissions"
# Short paths avoid generated Fortran string wrapping; the Git ceiling keeps
# temporary test directories independent of any enclosing repository.
scratch=$(mktemp -d /tmp/gelb-gate.XXXXXXXX)
trap 'rm -rf -- "$scratch"' EXIT
cd "$tree"
export TMPDIR=$scratch GIT_CEILING_DIRECTORIES="$scratch${GIT_CEILING_DIRECTORIES:+:$GIT_CEILING_DIRECTORIES}"
export OMP_NUM_THREADS=$omp_threads OMP_DYNAMIC=FALSE QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg
unset GELB_FFLAGS GELB_CXXFLAGS GELB_NVCC_FLAGS GELBC_EXTRA
stage() {
    local label=$1 verdict=$2 started=$SECONDS; shift 2
    printf 'Running %s\n' "$label"
    printf '%q ' "$@" > "$out/logs/$label.command"
    if "$@" > "$out/logs/$label.log" 2>&1; then
        printf '%s: %s\n' "$label" "$verdict" | tee -a "$out/results.txt"
        printf '%s: %ss\n' "$label" "$((SECONDS-started))" | tee -a "$out/timings.txt"
    else
        printf '%s: FAIL\n' "$label" | tee -a "$out/results.txt"
        tail -n 40 "$out/logs/$label.log" >&2
        return 1
    fi
}
run() { local label=$1; shift; stage "$label" PASS "$@"; }
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
backends=cpu_fortran_serial,cpu_highway
if [[ ,$configs, == *,cuda,* ]]; then backends+=,gpu_cuda_cpp; fi
smoke_backends=${smoke_backends:-$backends}
value_gate=$tree/scripts/differential_value_gate.py
base_guard() {
    uv run python "$value_gate" check-runners --tree "$tree" --base "$base" --allow-changed-headers "$allow_headers"
}
value_guard() {
    base_guard && uv run python "$value_gate" verify-sources --tree "$tree" --baseline "$baseline_values/$1" \
        --configs "$configs" --omp-threads "$omp_threads" -j "$jobs" "${@:2}"
}
reference() {
    local variant=$1 root path matches
    for root in "$snapshots" "$extra_snapshots"; do
        [[ -n $root ]] || continue
        if [[ -d $root/$variant ]]; then printf '%s\n' "$root/$variant"; return; fi
        shopt -s nullglob
        matches=()
        for path in "$root"/emis_"$variant" "$root"/emis_*_"$variant"; do
            [[ ! -d $path ]] || matches+=("$path")
        done
        shopt -u nullglob
        if ((${#matches[@]} == 1)) && [[ -d ${matches[0]} ]]; then printf '%s\n' "${matches[0]}"; return; fi
    done
    echo "missing or ambiguous snapshot: $variant" >&2; return 1
}
emit() {
    uv run python "$snapshot_tool" snapshot -j 16 -o "$out/emissions/$1" --variant "$1"
}
build_guard() {
    local kind=$1 selected=$2
    base_guard && uv run python "$value_gate" verify-build-hashes --tree "$tree" --kind "$kind" \
        --build-hashes "$build_hashes" --backends "$selected" --smoke-iters "$smoke_iters" -j "$jobs" || return 1
    if [[ $kind == plain-build ]]; then
        emit plain && uv run python "$snapshot_tool" compare -o "$(reference plain)" --variant plain \
            --candidate "$out/emissions/plain" || return 1
    fi
}
# Check requested skips before expensive stages. No guard falls back to execution.
if ((skip_values)); then
    stage values-default SKIP value_guard default
    stage values-strict SKIP value_guard strict --strict-fp
fi
if ((skip_smoke)); then stage smoke SKIP build_guard smoke "$smoke_backends"; fi
if ((skip_plain)); then stage plain-build SKIP build_guard plain-build "$backends"; fi
run headers uv run python "$value_gate" check-headers --tree "$tree" --base "$base" --allow-changed-headers "$allow_headers"
for variant in default soa aos cbt plain strict; do
    if [[ $variant == cbt && ,$configs, != *,cbt,* ]]; then
        printf 'emission-cbt: SKIP (AVX-512 explicitly waived)\n' | tee -a "$out/results.txt"
        continue
    fi
    if [[ ! -d $out/emissions/$variant ]]; then run "generate-$variant" emit "$variant"; fi
    baseline=$(reference "$variant")
    run "emission-$variant" uv run python "$snapshot_tool" compare -o "$baseline" --variant "$variant" \
        --candidate "$out/emissions/$variant" --emission-mode "$emission_mode" --allow-changed "$allow_emission"
    run "syntax-$variant" uv run python "$snapshot_tool" syntax -j 8 -o "$out/emissions/$variant"
done
run diff-backends uv run python "$tree/scripts/emission_snapshot.py" diff-backends -j 16
run unit uv run pytest -q --durations=25 --basetemp "$scratch/pytest-unit" "$tree/gelb/tests/unit"
uv run python - <<'PY' > "$out/ci-files.txt"
from pathlib import Path
from gelb.tests.unit.test_ci_integration_coverage import ci_files
files = ci_files(Path('.github/workflows/release-health.yml').read_text())
assert len(files) == len(set(files)) == 49
print('\n'.join('gelb/tests/integration/' + name for name in files))
PY
mapfile -t ci < "$out/ci-files.txt"
run integration-ci49 uv run pytest -q -n "$jobs" --durations=25 --basetemp "$scratch/pytest-ci" "${ci[@]}"
repro=$(uv run python "$value_gate" reproducibility-needed --tree "$tree" --base "$base")
if [[ $repro == RUN ]]; then
    run reproducibility uv run pytest -q --basetemp "$scratch/pytest-repro" gelb/tests/integration/test_reproducibility.py
else
    printf 'reproducibility: SKIP\n' | tee -a "$out/results.txt"
fi
if ((!skip_plain)); then
    run plain-build uv run pytest -q --basetemp "$scratch/pytest-plain" gelb/tests/integration/test_plain_build_compiles.py
fi
if ((!skip_smoke)); then
    run smoke uv run pytest -q -n "$jobs" --basetemp "$scratch/pytest-smoke" gelb/tests/integration/test_examples_smoke.py \
        --run-smoke --smoke-backends="${smoke_backends//cpu_fortran_serial/serial}" --smoke-iters="$smoke_iters"
fi
for kind in plain-build smoke; do
    selected=$backends; if [[ $kind == smoke ]]; then selected=$smoke_backends; fi
    run "hashes-$kind" uv run python "$value_gate" record-build-hashes --tree "$tree" --kind "$kind" \
        --build-hashes "$out/build_hashes" --backends "$selected" --smoke-iters "$smoke_iters" -j "$jobs"
done
run numeric uv run pytest -q --durations=25 --basetemp "$scratch/pytest-numeric" "$tree/gelb/tests/numeric"
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
for mode in default strict; do
    flags=(); if [[ $mode == strict ]]; then flags+=(--strict-fp); fi
    if ((!skip_values)); then
        run "values-$mode" uv run python "$value_gate" record --tree "$tree" --out "$out/values/$mode" --configs "$configs" --omp-threads "$omp_threads" -j "$jobs" "${flags[@]}"
        run "baseline-$mode" uv run python "$value_gate" compare-baseline --baseline "$baseline_values/$mode" --candidate "$out/values/$mode" \
            --allow-changed "$allow_value" --allow-changed-headers "$allow_headers"
    fi
    if [[ -n $fuzz_dir ]]; then
        run "fuzz-$mode" uv run python "$value_gate" record --tree "$tree" --out "$out/fuzz/$mode" --corpus "$fuzz_dir" --configs "$configs" --omp-threads "$omp_threads" -j "$jobs" "${flags[@]}"
        run "fuzz-baseline-$mode" uv run python "$value_gate" compare-baseline --baseline "$fuzz_baseline/$mode" --candidate "$out/fuzz/$mode" \
            --allow-changed-headers "$allow_headers"
    fi
done
if ((!skip_values)); then run layouts uv run python "$value_gate" compare-backends --run-dir "$out/values/strict"; fi
run exact-record uv run python "$value_gate" record --tree "$tree" --out "$out/exact" --exact-probes --strict-fp --configs "$configs" --omp-threads "$omp_threads" -j "$jobs"
run exact-backends uv run python "$value_gate" compare-backends --run-dir "$out/exact"
printf 'Gate passed; logs: %s\n' "$out/logs"
