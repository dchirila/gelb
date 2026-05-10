"""Module-level constants and host-detection helpers for the
cpu_highway backend.

Shared by the concern modules that together form
:class:`~gelb.backends.stage3_backend_cpu_highway.HighwayCodeGenerator`:
the GeLB->C++ type maps, the CBT tile width, the NT-store threshold
machinery (L3 detection + env overrides), the AVX-512 probe behind the
``auto`` storage-layout heuristic, and the C++ identifier encoding.
"""

from __future__ import annotations

import os


# ----------------------------------------------------------------------
# Type mapping: GeLB scalar dtype -> C++ type spelling
# ----------------------------------------------------------------------

_TYPE_MAP = {
    'int':    'int64_t',
    'int8':   'int8_t',
    'int16':  'int16_t',
    'int32':  'int32_t',
    'int64':  'int64_t',
    'real':   'double',
    'real16': 'float',  # no widely-portable half-float in C++; widen
    'real32': 'float',
    'real64': 'double',
    'bool':   'bool',
}

# Tile width for the cell-block-tiled (CBT) storage layout.  Equals the
# AVX-512 SIMD width (Vec8d = 8 doubles).  Storage shape under CBT:
# ``[buf][...y][x_tile][df][TILE]`` so that lane 0 of (x_tile, df) is
# 64-byte-aligned and a single ``Vec8d.load_a`` covers 8 consecutive
# cells of one DF.
_CBT_TILE = 8

# Streaming (nontemporal) store gate.  When the per-buffer byte count
# exceeds this threshold, lattice writes use ``Vec8d.store_nt`` (skip
# L1, write through the write-combining buffer) instead of
# ``Vec8d.store_a``.  Empirically on a Zen4 host with 32 MB L3:
#
#   buffer=19 MB  (LDC-2D N=512 D2Q9):  NT regresses 12x
#   buffer=44 MB  (TGV-3D N=64 D3Q19):  NT regresses 31%
#   buffer=333 MB (TGV-3D N=128 D3Q19): NT wins +47%
#
# The crossover is at ~4x L3.  When the buffer is only "marginally
# past L3" (1-2x L3), the just-written cache lines partially survive
# in L3 and warm the next-timestep reads; NT bypasses cache so this
# benefit is lost, and the gain from skipping write-allocate is
# smaller than the loss from cold next-timestep reads.  Only when
# the buffer is so large that the freshly-written lines are evicted
# anyway does NT become net-positive.
#
# The 4x multiplier is **empirically tuned on Zen4** and may not
# generalise.  Cross-machine validation (laptop CPU + ideally
# Intel Xeon / AMD EPYC) is required before publishing the
# heuristic; until then the same shape (some N*L3) is used on every
# host with L3 detected at codegen time.  Override via
# ``GELB_NT_STORE_THRESHOLD_BYTES`` env var if you have a different
# tuning point.

_NT_STORE_THRESHOLD_L3_MULTIPLIER = 4


def _positive_int_env(name: str) -> int | None:
    """Return a positive integer env-var value, or None if unset/invalid."""
    raw = os.environ.get(name)
    if raw is None:
        return None

    try:
        value = int(raw)
    except ValueError:
        return None

    return value if value > 0 else None


def _detect_l3_size_bytes() -> int:
    """Detect the host's L3 cache size in bytes.  Used to scale the
    NT-store activation threshold to the machine.  Falls back to
    32 MB (representative Zen4 L3 size) if all detection methods fail.

    Detection order:
      1. ``GELB_L3_SIZE_BYTES`` env var (test / override).
      2. ``getconf LEVEL3_CACHE_SIZE`` (POSIX standard, fast,
         returns bytes directly).
      3. ``/sys/devices/system/cpu/cpu0/cache/index3/size`` (Linux
         sysfs, format like ``32768K`` or ``32M``).
      4. ``sysctl -n hw.l3cachesize`` (macOS, returns bytes).
    """
    import subprocess

    # 1. Env var override.
    value = _positive_int_env('GELB_L3_SIZE_BYTES')
    if value is not None:
        return value

    # 2. getconf
    try:
        out = subprocess.check_output(
            ['getconf', 'LEVEL3_CACHE_SIZE'],
            stderr=subprocess.DEVNULL, timeout=2).decode().strip()
        v = int(out)
        if v > 0:
            return v
    except (OSError, subprocess.SubprocessError, ValueError):
        pass

    # 3. Linux sysfs
    sysfs = '/sys/devices/system/cpu/cpu0/cache/index3/size'
    try:
        with open(sysfs) as f:
            val = f.read().strip()
        if val.endswith('K'):
            return int(val[:-1]) * 1024
        if val.endswith('M'):
            return int(val[:-1]) * 1024 * 1024
        return int(val)
    except (OSError, ValueError):
        pass

    # 4. macOS sysctl
    try:
        out = subprocess.check_output(
            ['sysctl', '-n', 'hw.l3cachesize'],
            stderr=subprocess.DEVNULL, timeout=2).decode().strip()
        v = int(out)
        if v > 0:
            return v
    except (OSError, subprocess.SubprocessError, ValueError):
        pass

    # Conservative fallback for a representative Zen4 L3.
    return 32 * 1024 * 1024


def _detect_avx512_available() -> bool:
    """Return True iff the host's compiler defines ``__AVX512F__``
    under ``-march=native``.

    Used by the ``auto`` storage-layout heuristic
    (``_decide_storage_layout``) to decide whether to default to CBT
    (AVX-512 only -- single-instruction ``valignq`` for cross-tile lane
    shifts wins over SoA's plain load) or to SoA (AVX2 and NEON only --
    multi-instruction emulation of the cross-lane shuffle cancels CBT's
    locality benefit in the measured portability sweep).

    Detection order (mirrors ``_detect_l3_size_bytes``):

      1. ``GELB_HAS_AVX512`` env var (``1`` / ``true`` / ``yes``
         force True; ``0`` / ``false`` / ``no`` force False).
         For testing and for cross-compilation scenarios where the
         build host's compiler doesn't reflect the deploy host's
         capabilities.
      2. Probe via ``${GELB_CXX:-g++} -march=native -E -dM``: scan
         the predefined-macro dump for ``__AVX512F__``.  Cached.
      3. Conservative fallback: assume **no** AVX-512 (returns
         False) if the probe fails.  CBT-on-AVX-2 still works after
         the ``blend8`` codegen fix, so a wrong
         False is at most a missed-optimisation in 2D, never a
         correctness issue.

    Cached on the first call (the result is fixed per-process,
    re-detection adds nothing).
    """
    import subprocess

    cached = getattr(_detect_avx512_available, '_cached', None)
    if cached is not None:
        return cached

    # 1. Env var override.
    raw = os.environ.get('GELB_HAS_AVX512')
    if raw is not None:
        v = raw.strip().lower()
        if v in ('1', 'true', 'yes'):
            _detect_avx512_available._cached = True
            return True
        if v in ('0', 'false', 'no'):
            _detect_avx512_available._cached = False
            return False
        # Other / garbage values fall through.

    # 2. Compiler probe.
    cxx = os.environ.get('GELB_CXX', 'g++')
    try:
        out = subprocess.check_output(
            [cxx, '-march=native', '-E', '-dM', '-x', 'c++', '-'],
            input=b'',
            stderr=subprocess.DEVNULL, timeout=10).decode()
        result = '__AVX512F__' in out
        _detect_avx512_available._cached = result
        return result
    except (OSError, subprocess.SubprocessError):
        pass

    # 3. Conservative fallback.
    _detect_avx512_available._cached = False
    return False


def _nt_store_threshold_l3_multiplier() -> int:
    """Return the NT-store activation L3-size multiplier.

    Default ``_NT_STORE_THRESHOLD_L3_MULTIPLIER`` (=4 -- tuned on Zen4
    and checked on an AVX2 laptop CPU in May 2026 cross-machine
    measurements).  Override via
    ``GELB_NT_STORE_THRESHOLD_L3_MULTIPLIER`` env var when porting to
    a host whose buffer-vs-cache crossover doesn't sit at 4x L3 -- for
    example on a CPU with very small L3 (older Xeon, mobile parts) or
    very large L3 (Sapphire Rapids, Genoa-X with VCache) the multiplier
    may need to be re-fit.  This knob is the convenient form;
    ``GELB_NT_STORE_THRESHOLD_BYTES`` is the absolute-bytes form (which
    bypasses both the multiplier and the L3-detection logic).
    """
    value = _positive_int_env('GELB_NT_STORE_THRESHOLD_L3_MULTIPLIER')
    if value is not None:
        return value
    return _NT_STORE_THRESHOLD_L3_MULTIPLIER


def _nt_store_threshold_bytes() -> int:
    """Return the NT-store activation threshold (bytes).  Computed
    once per process from the detected L3 size and the empirical
    multiplier; can be overridden via
    ``GELB_NT_STORE_THRESHOLD_BYTES`` (absolute) or
    ``GELB_NT_STORE_THRESHOLD_L3_MULTIPLIER`` (multiple of L3) env
    vars.  When both are set, the absolute-bytes form wins."""
    value = _positive_int_env('GELB_NT_STORE_THRESHOLD_BYTES')
    if value is not None:
        return value
    return _nt_store_threshold_l3_multiplier() * _detect_l3_size_bytes()


_NT_STORE_THRESHOLD_BYTES = _nt_store_threshold_bytes()


def _cbt_addr_to_tile_start(addr: str) -> str:
    """Given a CBT storage address ending with ``[(expr) % TILE]`` (the
    x_within lane subscript), strip the lane subscript and replace it
    with ``[0]`` so the address points at lane 0 of the tile (the
    aligned tile-start).  Used by the SIMD-CBT load/store emit when
    the iteration's tile-aligned ``g_x`` guarantees the lane subscript
    folds to ``0``; we rewrite it in source to give gcc the clearest
    possible alignment hint.
    """
    # The CBT subscript ends with `[(<x_expr>) % <TILE>]`; replace the
    # last bracketed group with `[0]`.
    closing = addr.rfind(']')
    opening = addr.rfind('[', 0, closing)
    if opening < 0:
        return addr
    return addr[:opening] + '[0]'

_NETCDF_TYPE_MAP = {
    'bool':   'NC_BYTE',
    'int':    'NC_INT64',
    'int8':   'NC_BYTE',
    'int16':  'NC_SHORT',
    'int32':  'NC_INT',
    'int64':  'NC_INT64',
    'real':   'NC_DOUBLE',
    'real32': 'NC_FLOAT',
    'real64': 'NC_DOUBLE',
}


def _uname(name: str) -> str:
    """Encode a GeLB identifier for C++ emission.

    C++ is case-sensitive, so unlike the Fortran backend we don't
    need underscore escaping.  We just prefix ``g_`` to avoid
    clashing with C++ keywords / runtime symbols.
    """
    return f'g_{name}'


def _lname(name: str) -> str:
    """Internal lattice symbols cannot collide with ``g_`` user symbols.

    The source-name length also separates different lattice names when
    buffer/type suffixes are appended to this base.
    """
    return f'g0_{len(name)}_{name}'
