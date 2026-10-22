// GeLB cpu_highway backend -- runtime support header
// ================================================================
// Helpers used by every program emitted by stage3_backend_cpu_highway.py.
// Kept here (not inlined per-program) so the emitter only deals with
// program-specific code.
//
// What this header provides:
//   - Highway include + ISA-namespace boilerplate
//   - SIMD descriptor + Vec<D> type alias (CappedTag<double, 8> --
//     resolves to up-to-8 lanes per the host ISA's MaxLanes<double>,
//     matching the cell-block-tiled storage's TILE = 8 on AVX-512
//     while remaining portable to narrower ISAs)
//   - Common C++ runtime helpers (NetCDF-C wrappers, MLUPS report
//     formatting, scalar reductions)
//   - CPU timing, aligned alloc, and NT-store fence helpers
//   - Multi-accumulator reduction helpers (gelb_sum / gelb_signed_sum
//     / gelb_dot_prod_const) -- descriptor-aware overloads for
//     Highway Vec types alongside the scalar (double) overloads.
//
// Header-only: include from the GeLB-emitted .cpp.

#ifndef GELB_CPU_HIGHWAY_RUNTIME_HPP
#define GELB_CPU_HIGHWAY_RUNTIME_HPP

#include <algorithm>
#include <atomic>     // std::atomic_thread_fence (gelb_sfence fallback)
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>

#if defined(__x86_64__) || defined(_M_X64)
#  include <xmmintrin.h>  // _mm_sfence (gelb_sfence x86 path)
#endif

// Highway -- vendored at third_party/highway/, brought in via the
// emitter's -I flag.  Static dispatch path: the emitted program is
// compiled with -march=native, and Highway's headers select the
// host's native ISA at compile time.
#include "hwy/highway.h"
#include "hwy/contrib/math/math-inl.h"  // Sin, Cos, Exp, Log, etc.
#include "hwy/contrib/random/random-inl.h"  // VectorXoshiro

#ifdef _OPENMP
#  include <omp.h>
#endif

// ----------------------------------------------------------------
// SIMD descriptor + Vec<D> type alias, in ``gelb_simd::HWY_NAMESPACE``
// so the emitter can refer to them as ``::gelb_simd::D`` and
// ``::gelb_simd::V``.
//
// No HWY_BEFORE_NAMESPACE() / HWY_AFTER_NAMESPACE() around them:
// those macros attach the target ISA to the *functions* defined in
// between (``#pragma GCC target`` on GCC, ``#pragma clang attribute
// push(..., apply_to = function)`` on clang), and the emitter already
// brackets ``int main()``, where the SIMD code is.  Around types and
// a constexpr object they do nothing, and clang warns on every
// compile that the pushed attribute went unused
// (-Wpragma-clang-attribute).
// ----------------------------------------------------------------

namespace gelb_simd {
namespace HWY_NAMESPACE {

namespace hn = hwy::HWY_NAMESPACE;

// CappedTag<double, 8>: up-to-8-lane descriptor that resolves at
// compile time per the host ISA's ``MaxLanes<double>``:
//   AVX-512  -> 8 lanes  (one ZMM register; identical to the old
//              FixedTag<double, 8> binding -- zero behaviour change
//              on x86 AVX-512 builds)
//   AVX-2    -> 4 lanes  (one YMM register)
//   SSE      -> 2 lanes  (one XMM register)
//   NEON     -> 2 lanes  (one Q-register; FixedTag<double, 8> would
//              fail to compile here because Highway hard-asserts
//              kNumLanes <= MaxLanes<T>, and MaxLanes<double> = 2
//              on NEON, as found when the backend was brought up on
//              an Apple M4)
// Does NOT support scalable-vector ISAs (ARM SVE, RISC-V V); that
// remains future work.
//
// Codegen-side rule: anywhere the SIMD lane count appears in
// emitted code (loop strides, iota counts, ...), use
// ``d.MaxLanes()`` instead of a literal `8`.  ``d.MaxLanes()`` is
// a constexpr method on the descriptor (see ``hwy/ops/shared-inl.h``);
// ``hn::Lanes(d)`` exists too but is runtime-only on some Highway
// builds (it's the right call when querying scalable-vector
// lengths, which we don't use under FixedTag/CappedTag).
using D = hn::CappedTag<double, 8>;
constexpr D d;

// Convenience alias for the vector type (implementation-defined).
using V = hn::Vec<D>;

}  // namespace HWY_NAMESPACE
}  // namespace gelb_simd

// Re-export D / V into the unqualified gelb_simd namespace so the
// emitted code outside the HWY_NAMESPACE wrapper can use them too.
// (``HWY_NAMESPACE`` names the one target compiled for, e.g.
// ``N_AVX3`` or ``N_NEON_BF16``: static dispatch, no per-target
// copies.)
namespace gelb_simd {
using D = HWY_NAMESPACE::D;
using V = HWY_NAMESPACE::V;
inline constexpr D d{};
}  // namespace gelb_simd

// ``hn`` is the conventional short alias used throughout Highway
// docs / examples for the active-target inline namespace.  Defined
// here at global scope so emitted code can write ``hn::Set(d, x)``
// directly (the inline namespace dispatches to e.g. ``hwy::N_AVX3``
// under -march=native AVX-512).
namespace hn = hwy::HWY_NAMESPACE;

#define GELB_SCALAR_INLINE HWY_INLINE
// The scalar helpers fuse exactly where the vector ones do: where the
// compiled Highway target has a native FMA, so that every path of a
// reduction rounds alike (user manual, Numerical semantics: Build
// modes, Reproducibility).
#define GELB_FMA_NATIVE HWY_NATIVE_FMA
#include "cpp_runtime_common.hpp"
#undef GELB_FMA_NATIVE
#undef GELB_SCALAR_INLINE

namespace gelb {

// Re-export the SIMD descriptor / vector type / instance into the
// ``gelb`` namespace so that emitted code -- which always starts with
// ``using namespace gelb;`` -- can refer to them as bare ``V`` / ``d``
// without the ``::gelb_simd::`` qualifier.  Keeps the per-emit-site
// source compact while remaining explicit (no ``auto``).
using ::gelb_simd::D;
using ::gelb_simd::V;
using ::gelb_simd::d;

// ----------------------------------------------------------------
// MLUPS timing
// ----------------------------------------------------------------

struct MlupsTimer {
    using clock = std::chrono::steady_clock;
    clock::time_point t_wall_start, t_wall_end;
    clock::duration   dyn_elapsed{0};
    clock::time_point t_dyn_start;
    double total_nodes = 0.0;
    int    num_timesteps = 0;

    void wall_start() { t_wall_start = clock::now(); }
    void wall_stop()  { t_wall_end   = clock::now(); }
    void dyn_start()  { t_dyn_start  = clock::now(); }
    void dyn_stop() {
        dyn_elapsed += clock::now() - t_dyn_start;
    }

    double wall_secs() const {
        return std::chrono::duration<double>(
                   t_wall_end - t_wall_start).count();
    }
    double dyn_secs() const {
        return std::chrono::duration<double>(dyn_elapsed).count();
    }
    double real_mlups() const {
        return gelb_mlups_rate(total_nodes, num_timesteps, wall_secs());
    }
    double compute_mlups() const {
        return gelb_mlups_rate(total_nodes, num_timesteps, dyn_secs());
    }
    void print_report() const {
        gelb_print_mlups_report(
            wall_secs(), dyn_secs(), total_nodes, num_timesteps);
    }
};

// ----------------------------------------------------------------
// Aligned-allocation helpers -- 64-byte alignment for Vec<D>
// AVX-512 / aligned loads.
// ----------------------------------------------------------------

inline void* gelb_alloc_fill(std::size_t bytes, int fill_byte) {
    void* p = nullptr;
    if (posix_memalign(&p, 64, bytes) != 0) {
        std::fprintf(stderr,
                     "gelb_alloc: posix_memalign failed for %.1f MB\n",
                     bytes / (1024.0 * 1024.0));
        std::exit(2);
    }
    // fill_byte 0 zero-fills (matches static-storage initialization);
    // 0xFF poison-fills so every uninitialized double reads as NaN
    // (gelbc --poison-uninit: detects reads of unwritten lattice cells).
    std::memset(p, fill_byte, bytes);
    return p;
}

inline void* gelb_alloc(std::size_t bytes) {
    return gelb_alloc_fill(bytes, 0);
}

inline void* gelb_alloc_lattice(std::size_t bytes, int fill_byte) {
    // Lattice storage gets guard padding on BOTH sides: the SIMD
    // x-edge emission intentionally over-reads up to one CBT tile
    // below the first row (``g_x_tile - 1`` at tile 0) and above the
    // last row (``g_x_tile + 1`` at the last tile); the loaded lanes
    // are discarded by the cross-tile lane selection.  When storage
    // was a static array those reads silently landed in neighbouring
    // .bss; a bare heap allocation segfaults intermittently instead.
    // 4 KiB covers one tile entry (q * 8 lanes * 8 B = 576 B for
    // D2Q9 FP64; 1728 B for D3Q27) with ample margin, and keeps the
    // returned pointer 64-byte aligned (4096 % 64 == 0).
    constexpr std::size_t kGuard = 4096;
    unsigned char* p = static_cast<unsigned char*>(
        gelb_alloc_fill(bytes + 2 * kGuard, fill_byte));
    return p + kGuard;
}

inline void gelb_free(void* p) {
    std::free(p);
}

// The lane count is ``hn::Lanes(d)`` (constexpr) at the call site,
// not a header-level constant, so that the value tracks the active
// ``D`` automatically across ISAs.

// ----------------------------------------------------------------
// NT-store visibility fence for cpu_highway.
//
// Highway's ``hn::Stream(v, d, ptr)`` writes through the
// write-combining buffer (skipping L1/L2 cache fill) and is NOT
// inherently ordered with respect to subsequent loads.  An
// explicit fence after the streaming-step is required so that
// the NT writes are globally visible before the next timestep's
// halo-update / dynamic / gauge sweep reads them back.
//
// We dispatch per target so the macOS / NEON path and any future
// RISC-V / SVE port don't re-litigate this on first recompile.  The
// chosen approach is an explicit per-target ``gelb_sfence`` helper that
// expands to:
//
//   * ``_mm_sfence()``                              on x86
//   * ``__asm__ __volatile__("dmb ishst" ::: "memory")``
//                                                    on ARM
//   * ``std::atomic_thread_fence(std::memory_order_release)``
//                                                    everywhere else
//
// The atomic fallback is correct on any C++ target; it's slightly heavier
// than the native instruction but compiles cleanly without ISA-specific
// intrinsics.  The AVX-512 path inlines to a single ``sfence`` instruction
// at -O3.

inline void gelb_sfence() {
#if HWY_ARCH_X86
    _mm_sfence();
#elif HWY_ARCH_ARM
    __asm__ __volatile__("dmb ishst" ::: "memory");
#else
    std::atomic_thread_fence(std::memory_order_release);
#endif
}

// ----------------------------------------------------------------
// PRNG -- Highway's vendored ``VectorXoshiro`` (parallel-stream
// xoshiro256+ from Blackman & Vigna, see hwy/contrib/random/).
// Uses an independent stream per SIMD lane (jumped 2^128 apart);
// thread_local instance per OpenMP thread (long-jumped 2^192 by
// thread id) so worker threads get fully decorrelated streams
// without locking.
//
// Seed storage is a plain ``static`` global so the main-thread
// ``gelb_seed_prng(N)`` call is visible to every worker thread's
// first-touch initialisation of its thread_local rng.  Default
// seed is 0; caller is expected to set one (gelb-run / --seed
// passes the user value, otherwise the codegen seeds from
// ``steady_clock``).
//
// We picked the upstream Highway port over rolling our own
// because:
//   * it's the canonical Blackman & Vigna implementation --
//     well-tested, distribution properties verified by Highway's
//     own ``random_test.cc``;
//   * ``Uniform()`` returns ``Vec<F64>`` directly, no manual
//     bit-fiddling for the [0, 1) conversion;
//   * the parallel-stream init via SplitMix64 + Jump() handles
//     the per-lane decorrelation correctly.
// ----------------------------------------------------------------

inline std::uint64_t& gelb_prng_seed_storage() {
    static std::uint64_t seed = 0;
    return seed;
}

inline void gelb_seed_prng(std::uint64_t seed) {
    gelb_prng_seed_storage() = seed;
}

// Lazy thread_local singleton.  First touch on each OpenMP thread
// reads the (already-set) shared seed and creates a stream offset
// by ``thread_id`` long-jumps from the master sequence.
inline ::hn::VectorXoshiro& gelb_prng() {
#ifdef _OPENMP
    const std::uint64_t tid =
        static_cast<std::uint64_t>(omp_get_thread_num());
#else
    const std::uint64_t tid = 0;
#endif
    static thread_local ::hn::VectorXoshiro rng{
        gelb_prng_seed_storage(), tid};
    return rng;
}

// SIMD-mode call: returns a V (8 lanes on AVX-512 / 4 on AVX-2 /
// 2 on NEON or SSE) of independent uniform-[0,1) doubles.
inline V gelb_random_vec() {
    return gelb_prng().Uniform();
}

// Scalar-mode call: takes one lane of the V draw.  Wastes the
// other 7 lanes per call, but the scalar PRNG path is uncommon
// (init only) and the alternative -- running a separate scalar
// xoshiro alongside the vector one -- would diverge the two
// streams and complicate the seed contract.
inline double gelb_random() {
    return ::hn::ExtractLane(gelb_prng().Uniform(), 0);
}

// ----------------------------------------------------------------
// Reduction helpers (multi-accumulator, 4-way independent streams).
//
// ``gelb_sum<T, N>`` / ``gelb_signed_sum<T, Mp, Mn>`` /
// ``gelb_dot_prod_const<T, M>`` break the 9-/19-deep ``vaddpd``
// dependency chain of LBM moment / equilibrium reductions into 4
// parallel accumulators.  The SIMD overloads take a descriptor
// ``D d`` as first arg and use ``hn::Zero(d)`` /
// ``hn::Set(d, scalar)`` to materialise zero / scalar broadcasts
// (Highway's opaque ``Vec<D>`` has no value-constructor).
//
// Highway's contrib has a similar pattern in ``hwy/contrib/dot/``
// (``hn::Dot::Compute(d, pa, pb, n)``) -- multi-acc 4-way unroll
// returning a scalar -- but the shape doesn't match ours: GeLB
// needs sum-across-an-array-of-V (one V per DF index, sum
// per-lane), not sum-across-scalars-with-final-ReduceSum.
// Highway's source acknowledges the gap with the comment
// "Compiler doesn't make independent sum* accumulators, so
// unroll manually" -- so even upstream hand-writes the multi-acc
// pattern at this shape.  We do the same.
//
// Scalar overloads live in cpp_runtime_common.hpp.  The overloads
// below are Highway-specific and take ``D d`` as first arg,
// ``Vec<D>``-typed ``arr`` / ``a`` arguments, and return ``Vec<D>``.
// ----------------------------------------------------------------

// Shape note: ``gelb_sum`` takes ``const V (&a)[N]`` (where N is
// encoded in the type) but ``signed_sum`` / ``dot_prod_const``
// take ``const V* a`` (so the same helper handles arrays of any
// size, with the relevant index arrays carrying the bounds via
// templates).  An earlier attempt used array-ref everywhere with
// 4-way per side on signed_sum, which under-inlined and regressed
// MRT by 12 % in paired bench -- the pointer-arg + 2-acc-per-side
// shape below closes that gap.

// ---- gelb_sum: sum_{i=0}^{N-1} arr[i] -------------------------

// SIMD overload: per-lane sum of an array of V's.  4-way
// independent accumulators break the N-deep ``vaddpd`` chain.
template <std::size_t N>
HWY_INLINE V gelb_sum(::gelb_simd::D d, const V (&arr)[N]) {
    if constexpr (N == 0) {
        return ::hn::Zero(d);
    } else if constexpr (N == 1) {
        return arr[0];
    } else if constexpr (N == 2) {
        return ::hn::Add(arr[0], arr[1]);
    } else if constexpr (N == 3) {
        return ::hn::Add(::hn::Add(arr[0], arr[1]), arr[2]);
    } else {
        V s0 = arr[0], s1 = arr[1], s2 = arr[2], s3 = arr[3];
        std::size_t i = 4;
        for (; i + 4 <= N; i += 4) {
            s0 = ::hn::Add(s0, arr[i + 0]);
            s1 = ::hn::Add(s1, arr[i + 1]);
            s2 = ::hn::Add(s2, arr[i + 2]);
            s3 = ::hn::Add(s3, arr[i + 3]);
        }
        for (; i < N; ++i) s0 = ::hn::Add(s0, arr[i]);
        return ::hn::Add(::hn::Add(s0, s1), ::hn::Add(s2, s3));
    }
}

// ---- gelb_signed_sum: (sum at pos_idx) - (sum at neg_idx) -----
//
// **2 accumulators total** (one per sign), pointer-arg ``a``.
// D2Q9/D3Q19 momentum reductions have Mp <= 5 each, so 4-way per
// side is overkill; it over-pressures the register file and
// regressed TGV-2D MRT by 12 % in an earlier attempt.

template <std::size_t Mp, std::size_t Mn>
HWY_INLINE V gelb_signed_sum(::gelb_simd::D d,
                              const V* a,
                              const int (&pos)[Mp],
                              const int (&neg)[Mn]) {
    V sp = (Mp > 0) ? a[pos[0]] : ::hn::Zero(d);
    V sn = (Mn > 0) ? a[neg[0]] : ::hn::Zero(d);
    for (std::size_t i = 1; i < Mp; ++i)
        sp = ::hn::Add(sp, a[pos[i]]);
    for (std::size_t j = 1; j < Mn; ++j)
        sn = ::hn::Add(sn, a[neg[j]]);
    if constexpr (Mn == 0) return sp;
    if constexpr (Mp == 0) return ::hn::Sub(::hn::Zero(d), sn);
    return ::hn::Sub(sp, sn);
}

// ---- gelb_mul_add: the one place GeLB decides a fusion
//
// Build modes (user manual, Numerical semantics): a multiply-add in a
// GeLB runtime helper may be fused only where GeLB says so, and in a
// strict build nothing is fused.  The generated source defines
// ``GELB_STRICT_FP`` *before* including this header, so the choice is
// made here, once, for every code path that calls the helper.  In a
// default build this is ``hn::MulAdd`` -- a true FMA where the target
// has one, two roundings elsewhere.
// The vector overload of cpp_runtime_common.hpp's scalar helper.
#if defined(GELB_STRICT_FP) && GELB_STRICT_FP
HWY_INLINE V gelb_mul_add(V a, V b, V c) {
    return ::hn::Add(::hn::Mul(a, b), c);
}
#else
HWY_INLINE V gelb_mul_add(V a, V b, V c) {
    return ::hn::MulAdd(a, b, c);
}
#endif

// ---- gelb_min / gelb_max on vectors: IEEE 754-2019 minimum / maximum
//
// The same definition as the scalar helpers in cpp_runtime_common.hpp
// (user manual, Numerical semantics: Types and promotion), so the SIMD
// body, the peeled edges and the scalar tail agree: a NaN lane gives
// NaN, and -0 is less than +0.  hn::Min/Max alone would follow the
// target's own NaN rule.
HWY_INLINE V gelb_min(V a, V b) {
    const auto nan = ::hn::Or(::hn::IsNaN(a), ::hn::IsNaN(b));
    const V on_equal = ::hn::IfThenElse(::hn::IsNegative(a), a, b);
    const V picked = ::hn::IfThenElse(
        ::hn::Lt(a, b), a, ::hn::IfThenElse(::hn::Lt(b, a), b, on_equal));
    return ::hn::IfThenElse(nan, ::hn::Set(::gelb_simd::d, std::numeric_limits<double>::quiet_NaN()), picked);
}

HWY_INLINE V gelb_max(V a, V b) {
    const auto nan = ::hn::Or(::hn::IsNaN(a), ::hn::IsNaN(b));
    const V on_equal = ::hn::IfThenElse(::hn::IsNegative(a), b, a);
    const V picked = ::hn::IfThenElse(
        ::hn::Lt(a, b), b, ::hn::IfThenElse(::hn::Lt(b, a), a, on_equal));
    return ::hn::IfThenElse(nan, ::hn::Set(::gelb_simd::d, std::numeric_limits<double>::quiet_NaN()), picked);
}

// ---- gelb_sin / gelb_cos / gelb_tan / gelb_tanh / gelb_exp / gelb_log
//
// One implementation of each library function on this backend, used
// in every code path (user manual, Numerical semantics: Library
// functions): Highway's contrib math in the SIMD body and, through a
// one-lane vector, in the scalar tail and the peeled edge cells, so
// two cells with the same argument give the same bits whatever their
// position.  Highway's functions are valid on a range (math-inl.h,
// Highway 1.4.0: sin and cos for |x| <= 39000, exp for x <= +706, log
// on positive finite x, tanh everywhere finite); outside it, and for a
// NaN or infinite argument, the platform's function is used, chosen
// lane by lane from the argument's value, never from the cell's
// position.  Highway has no tan: the platform's tan serves every lane.
// Highway's documented bounds: exp 1 ULP, sin and cos 3, log 4, tanh 4.

using D1 = ::hn::CappedTag<double, 1>;

template <class F>
HWY_INLINE V gelb_lanewise(V x, F f) {
    // f on every lane of x, through memory: the platform's function
    // where Highway has none, or outside its valid range.
    alignas(64) double lanes[::hn::MaxLanes(::gelb_simd::d)];
    ::hn::Store(x, ::gelb_simd::d, lanes);
    for (std::size_t i = 0; i < ::hn::Lanes(::gelb_simd::d); ++i) lanes[i] = f(lanes[i]);
    return ::hn::Load(::gelb_simd::d, lanes);
}

template <class F>
HWY_INLINE V gelb_outside(V highway_result, ::hn::Mask<::gelb_simd::D> inside, V x, F f) {
    // Highway's result where the argument is inside its valid range,
    // the platform's function elsewhere.
    if (HWY_LIKELY(::hn::AllTrue(::gelb_simd::d, inside))) return highway_result;
    return ::hn::IfThenElse(inside, highway_result, gelb_lanewise(x, f));
}

#define GELB_LIBRARY_FUNCTION(NAME, HWY_FN, INSIDE_V, INSIDE_S, STD_FN)         \
    HWY_INLINE V gelb_##NAME(V x) {                                            \
        return gelb_outside(::hn::HWY_FN(::gelb_simd::d, x), (INSIDE_V), x,    \
                            [](double v) { return STD_FN(v); });               \
    }                                                                          \
    HWY_INLINE double gelb_##NAME(double x) {                                  \
        if (HWY_LIKELY(INSIDE_S)) {                                            \
            const D1 d1;                                                       \
            return ::hn::GetLane(::hn::HWY_FN(d1, ::hn::Set(d1, x)));          \
        }                                                                      \
        return STD_FN(x);                                                      \
    }

GELB_LIBRARY_FUNCTION(sin, Sin,
    ::hn::Le(::hn::Abs(x), ::hn::Set(::gelb_simd::d, 39000.0)),
    std::fabs(x) <= 39000.0, std::sin)
GELB_LIBRARY_FUNCTION(cos, Cos,
    ::hn::Le(::hn::Abs(x), ::hn::Set(::gelb_simd::d, 39000.0)),
    std::fabs(x) <= 39000.0, std::cos)
GELB_LIBRARY_FUNCTION(exp, Exp,
    ::hn::Le(x, ::hn::Set(::gelb_simd::d, 706.0)),
    x <= 706.0, std::exp)
GELB_LIBRARY_FUNCTION(log, Log,
    ::hn::And(::hn::Gt(x, ::hn::Zero(::gelb_simd::d)), ::hn::IsFinite(x)),
    x > 0.0 && std::isfinite(x), std::log)
GELB_LIBRARY_FUNCTION(tanh, Tanh,
    ::hn::IsFinite(x),
    std::isfinite(x), std::tanh)

#undef GELB_LIBRARY_FUNCTION

// The platform's tan in every lane and every path.
HWY_INLINE V gelb_tan(V x) {
    return gelb_lanewise(x, [](double v) { return std::tan(v); });
}
HWY_INLINE double gelb_tan(double x) { return std::tan(x); }

// ---- gelb_dot_prod_const: sum_{k=0}^{M-1} coeff[k] * arr[idx[k]]
//
// 4-way multi-acc, pointer-arg ``a``.  SIMD overload accumulates with
// ``gelb_mul_add`` above (fused in a default build, not in a strict
// one).  Coefficients are always ``double`` (constexpr arrays
// registered by the codegen); ``hn::Set(d, coeff[i])`` broadcasts
// per-iteration.

template <std::size_t M>
HWY_INLINE V gelb_dot_prod_const(::gelb_simd::D d,
                                  const double (&coeff)[M],
                                  const V* a,
                                  const int (&idx)[M]) {
    if constexpr (M == 0) return ::hn::Zero(d);
    if constexpr (M == 1)
        return ::hn::Mul(::hn::Set(d, coeff[0]), a[idx[0]]);
    if constexpr (M == 2)
        return ::hn::Add(
            ::hn::Mul(::hn::Set(d, coeff[0]), a[idx[0]]),
            ::hn::Mul(::hn::Set(d, coeff[1]), a[idx[1]]));
    if constexpr (M == 3)
        return ::hn::Add(
            ::hn::Add(::hn::Mul(::hn::Set(d, coeff[0]), a[idx[0]]),
                       ::hn::Mul(::hn::Set(d, coeff[1]), a[idx[1]])),
            ::hn::Mul(::hn::Set(d, coeff[2]), a[idx[2]]));
    if constexpr (M >= 4) {
        V s0 = ::hn::Mul(::hn::Set(d, coeff[0]), a[idx[0]]);
        V s1 = ::hn::Mul(::hn::Set(d, coeff[1]), a[idx[1]]);
        V s2 = ::hn::Mul(::hn::Set(d, coeff[2]), a[idx[2]]);
        V s3 = ::hn::Mul(::hn::Set(d, coeff[3]), a[idx[3]]);
        std::size_t k = 4;
        for (; k + 4 <= M; k += 4) {
            s0 = gelb_mul_add(::hn::Set(d, coeff[k + 0]),
                              a[idx[k + 0]], s0);
            s1 = gelb_mul_add(::hn::Set(d, coeff[k + 1]),
                              a[idx[k + 1]], s1);
            s2 = gelb_mul_add(::hn::Set(d, coeff[k + 2]),
                              a[idx[k + 2]], s2);
            s3 = gelb_mul_add(::hn::Set(d, coeff[k + 3]),
                              a[idx[k + 3]], s3);
        }
        for (; k < M; ++k) {
            s0 = gelb_mul_add(::hn::Set(d, coeff[k]),
                              a[idx[k]], s0);
        }
        return ::hn::Add(::hn::Add(s0, s1), ::hn::Add(s2, s3));
    }
    return ::hn::Zero(d);  // unreachable
}

}  // namespace gelb

#endif  // GELB_CPU_HIGHWAY_RUNTIME_HPP
