// GeLB C++ backend common runtime helpers
// ================================================================
// Host-compatible utilities shared by the cpu_highway and
// gpu_cuda_cpp runtime headers.

#ifndef GELB_CPP_RUNTIME_COMMON_HPP
#define GELB_CPP_RUNTIME_COMMON_HPP

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <type_traits>

#include <netcdf.h>

#ifndef GELB_SCALAR_HOST_DEVICE
#define GELB_SCALAR_HOST_DEVICE
#define GELB_SCALAR_HOST_DEVICE_DEFINED_BY_COMMON
#endif

#ifndef GELB_SCALAR_INLINE
#define GELB_SCALAR_INLINE inline
#define GELB_SCALAR_INLINE_DEFINED_BY_COMMON
#endif

namespace gelb {

// ----------------------------------------------------------------
// NetCDF helpers
// ----------------------------------------------------------------

inline void nc_check(int status, const char* context) {
    if (status != NC_NOERR) {
        std::fprintf(stderr, "NetCDF error at %s: %s\n",
                     context, nc_strerror(status));
        std::exit(2);
    }
}

// ----------------------------------------------------------------
// MLUPS report helpers
// ----------------------------------------------------------------

inline double gelb_mlups_rate(double total_nodes,
                              int num_timesteps,
                              double seconds) {
    if (seconds <= 0.0) return 0.0;
    return total_nodes * num_timesteps / (seconds * 1.0e6);
}

inline void gelb_print_mlups_line(const char* label,
                                  double value,
                                  const char* unit,
                                  const char* note) {
    if (note != nullptr) {
        std::printf("  %s%10.3f %s   (%s)\n", label, value, unit, note);
    } else {
        std::printf("  %s%10.3f %s\n", label, value, unit);
    }
}

inline void gelb_print_mlups_value_line(const char* label,
                                        double value,
                                        const char* note) {
    if (note != nullptr) {
        std::printf("  %s%10.1f MLUPS  (%s)\n", label, value, note);
    } else {
        std::printf("  %s%10.1f MLUPS\n", label, value);
    }
}

inline void gelb_print_mlups_report(
        double wall_secs,
        double compute_secs,
        double total_nodes,
        int num_timesteps,
        const char* wall_time_note = nullptr,
        const char* compute_time_note = nullptr,
        const char* real_mlups_note = nullptr,
        const char* compute_mlups_note = nullptr) {
    std::printf("=== MLUPS Report ===\n");
    gelb_print_mlups_line("Wall time:    ", wall_secs, "s",
                          wall_time_note);
    gelb_print_mlups_line("Compute time: ", compute_secs, "s",
                          compute_time_note);
    gelb_print_mlups_value_line(
        "Real MLUPS:   ",
        gelb_mlups_rate(total_nodes, num_timesteps, wall_secs),
        real_mlups_note);
    gelb_print_mlups_value_line(
        "Compute MLUPS:",
        gelb_mlups_rate(total_nodes, num_timesteps, compute_secs),
        compute_mlups_note);
}

// ----------------------------------------------------------------
// Scalar intrinsic helpers (user manual, Numerical semantics: Types and
// promotion)
//
// One definition of each intrinsic row, called from every code path
// of the cpu_highway and gpu_cuda_cpp backends (the SIMD body has
// vector overloads of gelb_min / gelb_max in cpu_highway_runtime.hpp
// with the same definition).  The compile-time evaluator
// (gelb/midware/ast_eval.py) gives the same values for constants.
// ----------------------------------------------------------------

// mod(a, b): the truncated remainder, with the sign of the dividend,
// for integers (C++ %) and reals (fmod).  A zero divisor is undefined
// at run time; the compiler rejects one it can see.
template <typename T>
GELB_SCALAR_HOST_DEVICE GELB_SCALAR_INLINE T gelb_mod(T a, T b) {
    if constexpr (std::is_integral<T>::value) {
        return a % b;
    } else {
        return std::fmod(a, b);
    }
}

// min / max: for integers the smaller / larger; for reals IEEE
// 754-2019 minimum / maximum: a NaN operand gives NaN, and -0 is less
// than +0, on every backend and in every path.
template <typename T>
GELB_SCALAR_HOST_DEVICE GELB_SCALAR_INLINE T gelb_min(T a, T b) {
    if constexpr (std::is_integral<T>::value) {
        return (b < a) ? b : a;
    } else {
        if (a != a) return a;
        if (b != b) return b;
        if (a < b) return a;
        if (b < a) return b;
        return std::signbit(a) ? a : b;    // equal: -0 is the smaller
    }
}

template <typename T>
GELB_SCALAR_HOST_DEVICE GELB_SCALAR_INLINE T gelb_max(T a, T b) {
    if constexpr (std::is_integral<T>::value) {
        return (a < b) ? b : a;
    } else {
        if (a != a) return a;
        if (b != b) return b;
        if (a < b) return b;
        if (b < a) return a;
        return std::signbit(a) ? b : a;    // equal: +0 is the larger
    }
}

// An integer raised to an integer: exact integer arithmetic, the same
// on every backend (user manual, Numerical semantics: Types and
// promotion).  A negative exponent follows Fortran: x^-n is 1 / x^n in
// integer division, so 0 unless x is 1 or -1; 0^-n is a division by
// zero and undefined here.  Overflow wraps, which the language leaves
// undefined at run time.  The multiplication runs in the
// unsigned width so that it is defined behaviour in C++.
template <typename T>
GELB_SCALAR_HOST_DEVICE GELB_SCALAR_INLINE T gelb_ipow(T base, T exponent) {
    static_assert(std::is_integral<T>::value, "gelb_ipow is for integers");
    if (exponent < 0) {
        if (base == 1) return T(1);
        if (base == -1) return (exponent % 2 != 0) ? T(-1) : T(1);
        return T(0);
    }
    using U = typename std::make_unsigned<T>::type;
    U result = 1;
    U b = static_cast<U>(base);
    T e = exponent;
    while (e > 0) {
        if (e % 2 != 0) result = static_cast<U>(result * b);
        b = static_cast<U>(b * b);
        e /= 2;
    }
    return static_cast<T>(result);
}

// ----------------------------------------------------------------
// gelb_mul_add: the one place GeLB decides a fusion (user manual,
// Numerical semantics: Build modes, Reproducibility)
//
// A multiply-add in a GeLB runtime helper is fused only where GeLB
// says so, and then identically in every code path of a backend: the
// SIMD body (cpu_highway_runtime.hpp's vector overload), the peeled
// edges and the scalar tail (this one), and CUDA's kernels.  Each
// runtime header defines GELB_FMA_NATIVE before including this file:
// Highway's HWY_NATIVE_FMA for the target it compiles for (so the
// scalar helper rounds once exactly where the vector one does, and
// twice where the target has no FMA), 1 on CUDA.  A strict build
// (GELB_STRICT_FP, defined by the generated source) fuses nothing; the
// native compilers run with contraction off, so ``a * b + c`` here is
// two roundings.
// ----------------------------------------------------------------

#if defined(GELB_STRICT_FP) && GELB_STRICT_FP
template <typename T>
GELB_SCALAR_HOST_DEVICE GELB_SCALAR_INLINE T gelb_mul_add(T a, T b, T c) {
    return a * b + c;
}
#elif defined(GELB_FMA_NATIVE) && GELB_FMA_NATIVE
template <typename T>
GELB_SCALAR_HOST_DEVICE GELB_SCALAR_INLINE T gelb_mul_add(T a, T b, T c) {
    return std::fma(a, b, c);
}
#else
template <typename T>
GELB_SCALAR_HOST_DEVICE GELB_SCALAR_INLINE T gelb_mul_add(T a, T b, T c) {
    return a * b + c;
}
#endif

// ----------------------------------------------------------------
// Scalar reduction helpers
//
// The same accumulator structure as the vector overloads in
// cpu_highway_runtime.hpp, term for term, so that a cell in the SIMD
// body and one in the scalar tail round alike (user manual, Numerical
// semantics: Reproducibility); the fusion shows too: a dot_prod with a
// coefficient 1 + 2^-52 against an input 1 - 2^-52 gives -2^-104 fused
// once and 0 unfused.  Every term counts: a zero coefficient is
// multiplied, so an Inf or NaN in that direction propagates.
// ----------------------------------------------------------------

template <typename T, std::size_t N>
GELB_SCALAR_HOST_DEVICE GELB_SCALAR_INLINE T gelb_sum(
        const T (&arr)[N]) {
    if constexpr (N == 0) return T(0);
    if constexpr (N == 1) return arr[0];
    if constexpr (N == 2) return arr[0] + arr[1];
    if constexpr (N == 3) return (arr[0] + arr[1]) + arr[2];
    if constexpr (N >= 4) {
        T s0 = arr[0], s1 = arr[1], s2 = arr[2], s3 = arr[3];
        std::size_t i = 4;
        for (; i + 4 <= N; i += 4) {
            s0 += arr[i + 0]; s1 += arr[i + 1];
            s2 += arr[i + 2]; s3 += arr[i + 3];
        }
        for (; i < N; ++i) s0 += arr[i];
        return (s0 + s1) + (s2 + s3);
    }
    return T(0);
}

template <typename T, std::size_t Mp, std::size_t Mn>
GELB_SCALAR_HOST_DEVICE GELB_SCALAR_INLINE T gelb_signed_sum(
        const T* a,
        const int (&pos)[Mp],
        const int (&neg)[Mn]) {
    T sp = (Mp > 0) ? a[pos[0]] : T(0);
    T sn = (Mn > 0) ? a[neg[0]] : T(0);
    for (std::size_t i = 1; i < Mp; ++i) sp = sp + a[pos[i]];
    for (std::size_t j = 1; j < Mn; ++j) sn = sn + a[neg[j]];
    if constexpr (Mn == 0) return sp;
    if constexpr (Mp == 0) return T(0) - sn;
    return sp - sn;
}

template <typename T, std::size_t M>
GELB_SCALAR_HOST_DEVICE GELB_SCALAR_INLINE T gelb_dot_prod_const(
        const double (&coeff)[M],
        const T* a,
        const int (&idx)[M]) {
    if constexpr (M == 0) return T(0);
    if constexpr (M == 1) return T(coeff[0]) * a[idx[0]];
    if constexpr (M == 2)
        return T(coeff[0]) * a[idx[0]] + T(coeff[1]) * a[idx[1]];
    if constexpr (M == 3)
        return (T(coeff[0]) * a[idx[0]]
                + T(coeff[1]) * a[idx[1]])
               + T(coeff[2]) * a[idx[2]];
    if constexpr (M >= 4) {
        T s0 = T(coeff[0]) * a[idx[0]];
        T s1 = T(coeff[1]) * a[idx[1]];
        T s2 = T(coeff[2]) * a[idx[2]];
        T s3 = T(coeff[3]) * a[idx[3]];
        std::size_t k = 4;
        for (; k + 4 <= M; k += 4) {
            s0 = gelb_mul_add(T(coeff[k + 0]), a[idx[k + 0]], s0);
            s1 = gelb_mul_add(T(coeff[k + 1]), a[idx[k + 1]], s1);
            s2 = gelb_mul_add(T(coeff[k + 2]), a[idx[k + 2]], s2);
            s3 = gelb_mul_add(T(coeff[k + 3]), a[idx[k + 3]], s3);
        }
        for (; k < M; ++k) s0 = gelb_mul_add(T(coeff[k]), a[idx[k]], s0);
        return (s0 + s1) + (s2 + s3);
    }
    return T(0);
}

}  // namespace gelb

#ifndef GELB_NC
#define GELB_NC(call) ::gelb::nc_check((call), #call)
#endif

#ifdef GELB_SCALAR_HOST_DEVICE_DEFINED_BY_COMMON
#undef GELB_SCALAR_HOST_DEVICE
#undef GELB_SCALAR_HOST_DEVICE_DEFINED_BY_COMMON
#endif

#ifdef GELB_SCALAR_INLINE_DEFINED_BY_COMMON
#undef GELB_SCALAR_INLINE
#undef GELB_SCALAR_INLINE_DEFINED_BY_COMMON
#endif

#endif  // GELB_CPP_RUNTIME_COMMON_HPP
