#!/bin/bash
# CUDA tuning matrix.
# 6 anchors * 12 knob combos * 3 samples = 216 runs.
# Each line: anchor|k|ldg|stwt|sample1|sample2|sample3
set -uo pipefail

ANCHORS=(
    "tgv2d_bgk|examples/lbm/2d/taylor_green_vortex_2d_bgk.gelb|-n 500 -D N=512 -w 500"
    "ldc2d_bgk|examples/lbm/2d/lid_driven_cavity_2d_bgk.gelb|-n 500 -D N=512 -w 500"
    "tgv2d_mrt|examples/lbm/2d/taylor_green_vortex_2d_mrt.gelb|-n 500 -D N=512 -w 500"
    "channel|examples/lbm/2d/channel_flow_circle_obstacle_2d_bgk.gelb|-n 200 -w 200"
    "rb2d_bgk|examples/softwarex-2026-paper/rayleigh_benard_2d_bgk.gelb|-n 500 -D NY=128 -w 500"
    "tgv3d_bgk|examples/lbm/3d/taylor_green_vortex_3d_bgk.gelb|-n 100 -D N=128 -w 100"
)

KS=(1 2 4)
LDGS=(0 1)
STWTS=(0 1)

SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

for anchor_spec in "${ANCHORS[@]}"; do
    name=$(echo "$anchor_spec" | cut -d'|' -f1)
    file=$(echo "$anchor_spec" | cut -d'|' -f2)
    args=$(echo "$anchor_spec" | cut -d'|' -f3)
    for k in "${KS[@]}"; do
        for ldg in "${LDGS[@]}"; do
            for stwt in "${STWTS[@]}"; do
                flags=""
                [ "$k" -gt 1 ] && flags="--cuda-coarsening $k"
                [ "$ldg" = "1" ] && flags="$flags --cuda-ldg"
                [ "$stwt" = "1" ] && flags="$flags --cuda-stwt"
                samples=()
                for i in 1 2 3; do
                    mlups=$(./scripts/gelb-run -b gpu_cuda_cpp $args $flags "$file" 2>&1 \
                        | grep "Compute MLUPS" | awk '{print $3}')
                    samples+=("${mlups:-0}")
                done
                echo "$name|$k|$ldg|$stwt|${samples[0]}|${samples[1]}|${samples[2]}"
            done
        done
    done
done
