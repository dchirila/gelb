#!/usr/bin/env bash
#
# capture_hardware_info.sh -- emit a Markdown fingerprint of the host
# to keep next to per-host performance or portability measurements.
#
# Captures:
#   * Kernel + distro
#   * CPU (vendor, model, cores, threads, frequency)
#   * CPU feature flags relevant to GeLB's SIMD backends
#     (AVX2/AVX-512/AVX-512BW/.../FMA/BMI/SSE)
#   * Cache topology (L1/L2/L3 sizes via getconf + sysfs)
#   * Compiler toolchain (gcc, g++, gfortran versions)
#   * Compiler feature macros for `-march=native`
#     (which __AVX*/__SSE*/__BMI*/__FMA*/__POPCNT__ get defined)
#   * GPU (nvidia-smi summary, if present)
#   * Toolchain env vars (OMP_*, GELB_*)
#
# Output is Markdown to stdout -- pipe it to a file, or paste it into
# a report.
#
# Usage:
#   ./scripts/capture_hardware_info.sh > "$(hostname -s)_hwinfo.md"
#
# Designed for Linux but degrades gracefully on macOS (lscpu absent
# -> falls back to sysctl).  Missing tools are reported as "(not
# available)" rather than aborting.

set -uo pipefail

# -- helpers ---------------------------------------------------------
_have() { command -v "$1" >/dev/null 2>&1; }

# Capture a command's output, falling back to a placeholder if the
# command is missing or fails.  Stderr is silenced -- we want clean
# Markdown.
_try() {
    if "$@" 2>/dev/null; then
        return 0
    fi
    echo "(not available)"
}

_section() { printf '\n## %s\n\n' "$*"; }
_subsection() { printf '\n### %s\n\n' "$*"; }
_fence_open() { printf '```%s\n' "${1:-}"; }
_fence_close() { printf '```\n'; }

# -- header ----------------------------------------------------------
printf '# Hardware fingerprint — %s\n' "$(hostname -s 2>/dev/null || echo unknown)"
printf '\n'
printf '*Captured %s by `scripts/capture_hardware_info.sh`.*\n' \
    "$(date -u +'%Y-%m-%d %H:%M:%S UTC')"

# -- kernel + distro -------------------------------------------------
_section "Host"
_fence_open
printf 'hostname: %s\n' "$(hostname 2>/dev/null || echo unknown)"
printf 'kernel:   %s\n' "$(uname -srm 2>/dev/null || echo unknown)"
if [ -f /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    printf 'distro:   %s\n' "${PRETTY_NAME:-${NAME:-unknown}}"
fi
_fence_close

# -- CPU summary -----------------------------------------------------
_section "CPU"
_fence_open
if _have lscpu; then
    # Filter to the ~10 most relevant lines.  `lscpu` output ordering is
    # stable; the regex covers vendor, model, family/stepping, cores,
    # sockets, threads-per-core, frequency.
    lscpu 2>/dev/null | grep -E \
        '^(Architecture|Vendor ID|Model name|CPU family|Model|Stepping|Thread|Core|Socket|CPU\(s\)|CPU max MHz|CPU min MHz):' \
        || lscpu 2>/dev/null
elif _have sysctl; then
    # macOS fallback
    sysctl -n machdep.cpu.brand_string 2>/dev/null || true
    sysctl hw.ncpu hw.physicalcpu hw.logicalcpu 2>/dev/null || true
else
    grep -E '^(model name|cpu MHz|cpu cores|siblings|physical id)' \
        /proc/cpuinfo 2>/dev/null | sort -u || echo "(no /proc/cpuinfo)"
fi
_fence_close

# -- CPU feature flags -----------------------------------------------
#
# This is the section that matters most for cpu_highway's SIMD
# targets.  We surface the AVX/SSE/BMI/FMA family of flags explicitly,
# then a raw flags dump for completeness.
_section "CPU feature flags"

# Reasonable groups for GeLB's SIMD work.  Each entry is a regex over
# /proc/cpuinfo's `flags` field.  Tested on AMD Zen and Intel; these
# are the canonical Linux flag names.
_subsection 'Relevant for GeLB'"'"'s SIMD backends'
_fence_open
if [ -r /proc/cpuinfo ]; then
    # shellcheck disable=SC2155
    local_flags=$(grep -m1 '^flags' /proc/cpuinfo 2>/dev/null | cut -d: -f2-)
    if [ -z "$local_flags" ]; then
        # Some CPUs report "Features" instead of "flags" (ARM)
        local_flags=$(grep -m1 '^Features' /proc/cpuinfo 2>/dev/null | cut -d: -f2-)
    fi
    if [ -n "$local_flags" ]; then
        # Each row: short tag for Markdown alignment | regex over flag tokens.
        for row in 'SSE      | sse|sse2|sse3|ssse3|sse4_1|sse4_2|sse4a' \
                   'AVX      | avx|avx2' \
                   'AVX-512  | avx512f|avx512cd|avx512bw|avx512dq|avx512vl|avx512_bf16|avx512_vnni|avx512_fp16|avx512ifma|avx512vbmi|avx512vbmi2|avx512vpopcntdq|avx512bitalg' \
                   'FMA      | fma|fma3|fma4' \
                   'BMI/ABM  | bmi1|bmi2|abm|tbm' \
                   'Crypto   | aes|sha_ni|pclmulqdq|vaes|vpclmulqdq' \
                   'RNG      | rdrand|rdseed' \
                   'Misc     | movbe|popcnt|lzcnt|f16c|adx' \
                   'ARM      | aarch64|neon|asimd|sve|sve2'; do
            tag="${row%%|*}"
            grp="${row#*|}"; grp="${grp# }"
            present=$(printf '%s\n' $local_flags | tr ' ' '\n' \
                      | grep -E "^($grp)$" 2>/dev/null | sort -u | tr '\n' ' ')
            if [ -n "$present" ]; then
                printf '%-9s %s\n' "${tag%%[[:space:]]*}:" "$present"
            else
                printf '%-9s (none)\n' "${tag%%[[:space:]]*}:"
            fi
        done
    else
        echo "(no flags field in /proc/cpuinfo)"
    fi
else
    echo "(no /proc/cpuinfo — non-Linux?)"
fi
_fence_close

_subsection 'Raw `flags` line'
_fence_open
if [ -r /proc/cpuinfo ]; then
    grep -m1 '^flags' /proc/cpuinfo 2>/dev/null \
        || grep -m1 '^Features' /proc/cpuinfo 2>/dev/null \
        || echo "(no flags)"
else
    echo "(no /proc/cpuinfo)"
fi
_fence_close

# -- Cache topology --------------------------------------------------
_section "Cache"

_subsection 'via `getconf`'
_fence_open
for level in LEVEL1_DCACHE_SIZE LEVEL1_ICACHE_SIZE LEVEL2_CACHE_SIZE LEVEL3_CACHE_SIZE; do
    val=$(getconf "$level" 2>/dev/null || true)
    if [ -n "$val" ] && [ "$val" != "0" ]; then
        # Convert to human-readable: KiB if <1MiB, MiB otherwise
        if [ "$val" -lt 1048576 ]; then
            human="$((val / 1024)) KiB"
        else
            human="$((val / 1048576)) MiB"
        fi
        printf '%-26s %12d B  (%s)\n' "$level" "$val" "$human"
    else
        printf '%-26s (not reported)\n' "$level"
    fi
done
_fence_close

_subsection "via Linux sysfs"
_fence_open
if [ -d /sys/devices/system/cpu/cpu0/cache ]; then
    for idx in /sys/devices/system/cpu/cpu0/cache/index*; do
        [ -d "$idx" ] || continue
        name=$(basename "$idx")
        size=$(cat "$idx/size" 2>/dev/null || echo "?")
        type_=$(cat "$idx/type" 2>/dev/null || echo "?")
        level=$(cat "$idx/level" 2>/dev/null || echo "?")
        printf '%-9s level=%s type=%-12s size=%s\n' "$name" "$level" "$type_" "$size"
    done
else
    echo "(no sysfs cache info)"
fi
_fence_close

# -- Memory ----------------------------------------------------------
_section "Memory"
_fence_open
if [ -r /proc/meminfo ]; then
    grep -E '^(MemTotal|MemAvailable|HugePages_Total|Hugepagesize):' \
        /proc/meminfo 2>/dev/null
else
    _try sysctl hw.memsize
fi
_fence_close

# -- Compiler toolchain ----------------------------------------------
_section "Compiler toolchain"
_fence_open
for cc in gcc g++ gfortran clang clang++; do
    if _have "$cc"; then
        ver=$("$cc" --version 2>/dev/null | head -1)
        printf '%-12s %s\n' "$cc:" "$ver"
    else
        printf '%-12s (not on PATH)\n' "$cc:"
    fi
done
_fence_close

_subsection 'g++ predefined macros for `-march=native`'
printf 'Filtered to the macro families the cpu_highway backend keys off.\n\n'
_fence_open
if _have g++; then
    g++ -march=native -E -dM -x c++ - </dev/null 2>/dev/null \
        | grep -E '__(AVX[0-9A-Z_]*|SSE[0-9A-Z_]*|FMA[0-9A-Z_]*|BMI[0-9A-Z_]*|SSE4[0-9A-Z_]*|POPCNT|LZCNT|F16C|RDRND|RDSEED|VAES|VPCLMULQDQ|XOP|MMX|3DNOW)__' \
        | sort \
        || echo "(g++ -march=native -E -dM failed)"
else
    echo "(g++ not on PATH)"
fi
_fence_close

# -- GPU -------------------------------------------------------------
_section "GPU"
_fence_open
if _have nvidia-smi; then
    nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap \
        --format=csv,noheader 2>/dev/null \
        || nvidia-smi 2>/dev/null | head -15
else
    echo "(nvidia-smi not on PATH — no NVIDIA driver, or non-NVIDIA host)"
fi
_fence_close

# -- Toolchain env relevant to GeLB ----------------------------------
_section "Relevant env vars"
_fence_open
for var in OMP_NUM_THREADS OMP_PROC_BIND OMP_PLACES OMP_STACKSIZE \
           GELB_FC GELB_CXX GELB_FFLAGS GELB_CXXFLAGS \
           GELB_NETCDF_INC GELB_NETCDF_LIB \
           GELB_NETCDF_C_INC GELB_NETCDF_C_LIB \
           GELB_L3_SIZE_BYTES GELB_NT_STORE_THRESHOLD_BYTES; do
    val="${!var:-}"
    if [ -n "$val" ]; then
        printf '%-32s = %s\n' "$var" "$val"
    else
        printf '%-32s (unset)\n' "$var"
    fi
done
_fence_close

# -- done ------------------------------------------------------------
printf '\n*End of fingerprint.*\n'
