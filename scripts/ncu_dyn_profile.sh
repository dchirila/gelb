#!/usr/bin/env bash
# ncu_dyn_profile.sh -- profile a GeLB program's dyn kernel with
# Nsight Compute and emit a single-row CSV with the metrics that
# distinguish "structural memory bottleneck" from "register-pressure-
# driven" from "stall-driven" bucketing.
#
# Usage:
#   ncu_dyn_profile.sh [--tag TAG] -b gpu_cuda_cpp \
#       [-D NAME=VALUE]... <example.gelb>
#
# Output: CSV row on stdout (header on first call when --header given).
# Side effect: leaves the .ncu-rep at /tmp/ncu_<tag>.ncu-rep for
# follow-up inspection via `ncu --import` or `ncu-ui`.
#
# Requirements:
#   * sudo passwordless to ncu when NVIDIA perfcounter access is admin-only
#     on the target machine.
#   * gelbc on PATH (i.e., .venv/bin in the caller's PATH).

set -euo pipefail

TAG=""
BACKEND=""
DEFINES=()
GELB_FILE=""
HEADER=false
ITERS=200

usage() {
    sed -n 's/^# //p' "$0" | head -25
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -b|--backend)   BACKEND="$2"; shift 2 ;;
        -D|--define)    DEFINES+=(-D "$2"); shift 2 ;;
        --tag)          TAG="$2"; shift 2 ;;
        --header)       HEADER=true; shift ;;
        -n|--iters)     ITERS="$2"; shift 2 ;;
        -h|--help)      usage ;;
        *)
            [[ -z "$GELB_FILE" ]] || { echo "ERROR: multiple input files" >&2; exit 1; }
            GELB_FILE="$1"; shift ;;
    esac
done

if $HEADER; then
    echo "tag,backend,N,kernel_duration_us,reg_per_thread,achieved_occupancy_pct,sm_compute_pct,dram_pct,l1_hit_pct,l2_hit_pct,fp64_pipe_pct,stall_long_sb_pct,stall_short_sb_pct,uncoalesced_pct,kernel_name"
    [[ -z "$GELB_FILE" ]] && exit 0
fi

[[ -z "$BACKEND" ]] && { echo "ERROR: -b BACKEND required" >&2; exit 1; }
[[ -z "$GELB_FILE" ]] && { echo "ERROR: input .gelb file required" >&2; exit 1; }
[[ -z "$TAG" ]] && TAG="$(basename "$GELB_FILE" .gelb)_${BACKEND}"

# Build: re-use gelb-run's pipeline up through compile, but we need
# the binary path -- easiest is to run gelb-run with -k (keep) and find
# the exe.
WORK=$(mktemp -d -t ncu_dyn_XXXXX)
trap "rm -rf '$WORK'" EXIT

ROOT_REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WORK"

# gelb-run writes the .nc + builds + runs.  We just need the binary,
# but gelb-run cleans up by default; -k keeps source+exe.  Use a
# small but non-tiny -n: the pre-profile run is throwaway, but we
# need enough dyn launches that the ncu --launch-skip below has
# room to advance past warmup-noise iterations and still profile
# one steady-state dyn invocation.  n=30 is plenty.
"$ROOT_REPO/scripts/gelb-run" -b "$BACKEND" -n 30 -w 9999 -k "${DEFINES[@]}" "$GELB_FILE" \
    >/tmp/ncu_${TAG}_build.log 2>&1 || {
    echo "BUILD-FAIL: $TAG (see /tmp/ncu_${TAG}_build.log)" >&2
    exit 2
}
EXE=$(basename "$GELB_FILE" .gelb)
EXE_PATH="$WORK/$EXE"
[[ -x "$EXE_PATH" ]] || { echo "ERROR: built exe not found at $EXE_PATH" >&2; exit 3; }

# Now run ncu under sudo with the right chdir + env.  Output as CSV.
# Curated metric list that maps to the bucket-decision signatures.
# `gpu__time_duration.sum` is in nanoseconds; we convert to us below.
METRICS="\
gpu__time_duration.sum,\
launch__registers_per_thread,\
sm__warps_active.avg.pct_of_peak_sustained_active,\
sm__throughput.avg.pct_of_peak_sustained_elapsed,\
gpu__compute_memory_throughput.avg.pct_of_peak_sustained_elapsed,\
l1tex__t_sector_hit_rate.pct,\
lts__t_sector_hit_rate.pct,\
sm__pipe_fp64_cycles_active.avg.pct_of_peak_sustained_elapsed,\
smsp__warp_issue_stalled_long_scoreboard_per_warp_active.pct,\
smsp__warp_issue_stalled_short_scoreboard_per_warp_active.pct,\
smsp__sass_average_data_bytes_per_sector_mem_global_op_ld.pct"

REPORT="/tmp/ncu_${TAG}.ncu-rep"
# Pre-clean any prior report (stale files from earlier runs cause
# ncu to error "Unable to write to file" even though --force-overwrite
# is set -- the lock-file check fires first).
rm -f "$REPORT"

# Step 1: profile and write the .ncu-rep (no CSV here -- ncu's --csv
# and --export to stdout don't compose; --export wins and CSV is
# silently suppressed).
sudo -n env "PATH=$PATH" "HOME=$HOME" bash -c "cd '$WORK' && \
    ncu --metrics $METRICS \
        --launch-skip 2 --launch-count 1 \
        --kernel-name regex:'^gelb_k_dyn_.*\$|^.*dynamic.*\$' \
        --export '$REPORT' --force-overwrite \
        '$EXE_PATH'" 2>/tmp/ncu_${TAG}_ncu.err >/tmp/ncu_${TAG}_run.log \
    || {
        echo "NCU-FAIL ($TAG): see /tmp/ncu_${TAG}_ncu.err" >&2
        cat /tmp/ncu_${TAG}_ncu.err >&2
        exit 4
    }
# sudo wrote the report as root -- fix ownership for follow-up reads.
sudo -n chown "$USER:$USER" "$REPORT" 2>/dev/null || true

# Step 2: extract CSV from the report (no sudo needed for --import).
ncu --import "$REPORT" --csv --page raw > /tmp/ncu_${TAG}_ncu.csv 2>/tmp/ncu_${TAG}_import.err \
    || {
        echo "NCU-IMPORT-FAIL ($TAG): see /tmp/ncu_${TAG}_import.err" >&2
        exit 5
    }

# Parse metric values out of the wide CSV.  `ncu --import --csv --page raw`
# emits row 1: header (metric names), row 2: units, row 3: values for
# the first kernel.  Use python's csv module -- embedded commas in
# values like "1,665,000" break naive awk splitting.
get_metric() {
    local key="$1"
    python3 -c "
import csv, sys
key = sys.argv[1]
with open(sys.argv[2]) as f:
    rows = list(csv.reader(f))
if len(rows) < 3: sys.exit(0)
hdr = rows[0]
try:
    col = hdr.index(key)
except ValueError:
    sys.exit(0)
v = rows[2][col]
v = v.replace(',', '')
print(v)
" "$key" /tmp/ncu_${TAG}_ncu.csv
}

# Kernel name (column "Kernel Name").
KERNEL_NAME=$(get_metric "Kernel Name")
N_VALUE=""
for d in "${DEFINES[@]}"; do
    if [[ "$d" =~ ^N= ]] || [[ "$d" =~ ^NY= ]] || [[ "$d" =~ ^NX= ]]; then
        N_VALUE="${d#*=}"
        break
    fi
done

# gpu__time_duration.sum is reported in microseconds in the units row
# of the wide CSV (`us`), so no ns->us conversion needed.
dur_us=$(get_metric "gpu__time_duration.sum")
reg=$(get_metric "launch__registers_per_thread")
occ=$(get_metric "sm__warps_active.avg.pct_of_peak_sustained_active")
smc=$(get_metric "sm__throughput.avg.pct_of_peak_sustained_elapsed")
dram=$(get_metric "gpu__compute_memory_throughput.avg.pct_of_peak_sustained_elapsed")
l1=$(get_metric "l1tex__t_sector_hit_rate.pct")
l2=$(get_metric "lts__t_sector_hit_rate.pct")
fp64=$(get_metric "sm__pipe_fp64_cycles_active.avg.pct_of_peak_sustained_elapsed")
sl_lsb=$(get_metric "smsp__warp_issue_stalled_long_scoreboard_per_warp_active.pct")
sl_ssb=$(get_metric "smsp__warp_issue_stalled_short_scoreboard_per_warp_active.pct")
unc=$(get_metric "smsp__sass_average_data_bytes_per_sector_mem_global_op_ld.pct")

# Trim to 1-decimal where it makes sense (occupancy/throughput/hit-pct).
fmt() { awk -v v="$1" 'BEGIN{ if (v == "" || v == "?") print "?"; else printf "%.1f", v+0 }'; }
echo "$TAG,$BACKEND,$N_VALUE,$(fmt "$dur_us"),$reg,$(fmt "$occ"),$(fmt "$smc"),$(fmt "$dram"),$(fmt "$l1"),$(fmt "$l2"),$(fmt "$fp64"),$(fmt "$sl_lsb"),$(fmt "$sl_ssb"),$(fmt "$unc"),$KERNEL_NAME"
