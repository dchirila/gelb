// GeLB gpu_cuda_cpp backend -- runtime support header
// ================================================================
// Helpers used by every program emitted by stage3_backend_gpu_cuda_cpp.py.
// Kept out-of-line so the emitter only deals with program-specific code.
//
// What this header provides:
//   - <cuda_runtime.h> plus common C++ runtime helpers
//   - CUDA_CHECK(call)  -- macro: file:line + cudaGetErrorString(rc),
//                         std::exit(2) on non-success
//   - GELB_NC(call)     -- shared NetCDF-C error wrapper
//   - MlupsTimer        -- wall via std::chrono::steady_clock,
//                         compute via paired cudaEvent_t recorded
//                         around the dynamic batch
//   - Scalar reduction helpers (gelb_sum / gelb_signed_sum /
//     gelb_dot_prod_const) -- __host__ __device__ overloads so they
//     can be called from kernel bodies.  The SIMD overloads from
//     cpu_highway are intentionally absent (CUDA's parallelism axis
//     is the thread axis, not a vector axis).
//
// Header-only: include from the GeLB-emitted .cu.

#ifndef GELB_GPU_CUDA_CPP_RUNTIME_CUH
#define GELB_GPU_CUDA_CPP_RUNTIME_CUH

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>

#include <cuda_runtime.h>
// cuRAND (``<curand_kernel.h>``) is NOT pulled in here --
// programs that use ``random()`` get the include emitted into
// their generated .cu by the backend's ``_emit_curand_decls``.
// Including it unconditionally measurably slowed down
// random-free programs (TGV-2D BGK regressed ~30 % in a controlled
// bisection -- possibly a constructor / global-init side effect,
// possibly cuRAND's own headers polluting the include graph for unused
// symbols).

// CUDA error-check macro.  Emitted code wraps every CUDA runtime
// API call with this so an early failure (OOM, invalid launch
// config, kernel assertion) prints file:line and exits with a
// distinct code (2) -- same exit-code convention as nc_check.
#define CUDA_CHECK(call) do {                                       \
    cudaError_t _gelb_cuda_rc = (call);                             \
    if (_gelb_cuda_rc != cudaSuccess) {                             \
        std::fprintf(stderr, "CUDA error at %s:%d: %s -- %s\n",     \
                     __FILE__, __LINE__, #call,                     \
                     cudaGetErrorString(_gelb_cuda_rc));            \
        std::exit(2);                                               \
    }                                                               \
} while (0)

#define GELB_SCALAR_HOST_DEVICE __host__ __device__
// Every CUDA device has a fused multiply-add: the reduction helpers
// fuse explicitly in a default build, where nvcc fuses anyway,
// and not at all in a strict one (GELB_STRICT_FP, -fmad=false).
#define GELB_FMA_NATIVE 1
// NetCDF-C and shared scalar/runtime helpers come from the common header.
#include "cpp_runtime_common.hpp"
#undef GELB_FMA_NATIVE
#undef GELB_SCALAR_HOST_DEVICE

namespace gelb {

// ----------------------------------------------------------------
// MLUPS timing
//
// API mirrors cpu_highway_runtime.hpp's MlupsTimer (wall_start /
// wall_stop / dyn_start / dyn_stop / wall_secs / dyn_secs /
// real_mlups / compute_mlups / print_report) so the emitted main()
// reads the same way as the cpu_highway version.
//
// Wall time uses std::chrono::steady_clock (host-side, same as
// cpu_highway).
//
// Compute time uses a paired cudaEvent_t recorded around the
// dynamic batch.  The codegen calls dyn_start() once before the
// first dynamic-kernel launch in the time-step and dyn_stop() once
// after the last one; multiple calls accumulate (dyn_ms_total +=
// elapsed) so a per-rect kernel-launch pattern still aggregates
// correctly.  cudaEventSynchronize inside dyn_stop blocks until
// the stop event completes -- one host-device sync per timestep
// boundary, which is the natural rhythm anyway (the CPU needs to
// know when one dyn batch finishes so it can launch the next one
// or a halo update).
// ----------------------------------------------------------------

struct MlupsTimer {
    using clock = std::chrono::steady_clock;
    clock::time_point t_wall_start, t_wall_end;
    cudaEvent_t ev_dyn_start = nullptr, ev_dyn_stop = nullptr;
    float dyn_ms_total = 0.0f;
    double total_nodes = 0.0;
    int    num_timesteps = 0;

    MlupsTimer() {
        CUDA_CHECK(cudaEventCreate(&ev_dyn_start));
        CUDA_CHECK(cudaEventCreate(&ev_dyn_stop));
    }
    ~MlupsTimer() {
        if (ev_dyn_start) cudaEventDestroy(ev_dyn_start);
        if (ev_dyn_stop)  cudaEventDestroy(ev_dyn_stop);
    }
    MlupsTimer(const MlupsTimer&) = delete;
    MlupsTimer& operator=(const MlupsTimer&) = delete;

    void wall_start() { t_wall_start = clock::now(); }
    void wall_stop()  { t_wall_end   = clock::now(); }
    void dyn_start()  { CUDA_CHECK(cudaEventRecord(ev_dyn_start, 0)); }
    void dyn_stop() {
        CUDA_CHECK(cudaEventRecord(ev_dyn_stop, 0));
        CUDA_CHECK(cudaEventSynchronize(ev_dyn_stop));
        float ms = 0.0f;
        CUDA_CHECK(cudaEventElapsedTime(&ms, ev_dyn_start, ev_dyn_stop));
        dyn_ms_total += ms;
    }
    // Stream-aware overloads -- used by the --cuda-graphs path so
    // dyn-kernel timing is recorded on the same stream the work
    // runs on.  Recording on stream 0 while the kernels execute
    // on a non-default stream would race (events would fire as
    // soon as stream 0 idles, not when the work finishes), so the
    // overloads route ``cudaEventRecord`` through the caller's
    // stream.
    void dyn_start(cudaStream_t s) {
        CUDA_CHECK(cudaEventRecord(ev_dyn_start, s));
    }
    void dyn_stop(cudaStream_t s) {
        CUDA_CHECK(cudaEventRecord(ev_dyn_stop, s));
        CUDA_CHECK(cudaEventSynchronize(ev_dyn_stop));
        float ms = 0.0f;
        CUDA_CHECK(cudaEventElapsedTime(&ms, ev_dyn_start, ev_dyn_stop));
        dyn_ms_total += ms;
    }

    double wall_secs() const {
        return std::chrono::duration<double>(
                   t_wall_end - t_wall_start).count();
    }
    double dyn_secs() const {
        return static_cast<double>(dyn_ms_total) / 1000.0;
    }
    double real_mlups() const {
        return gelb_mlups_rate(total_nodes, num_timesteps, wall_secs());
    }
    double compute_mlups() const {
        return gelb_mlups_rate(total_nodes, num_timesteps, dyn_secs());
    }
    void print_report() const {
        // Label the columns with their measurement scope so the report's
        // columns aren't conflated.  ``Compute MLUPS`` measures the dyn
        // kernel only; ``Real MLUPS`` measures end-to-end wall-clock.
        gelb_print_mlups_report(
            wall_secs(), dyn_secs(), total_nodes, num_timesteps,
            "end-to-end, includes halo + dyn + gauge + nc_put",
            "sum of dyn-kernel cudaEvent durations",
            "wall-clock, end-to-end including halo / dyn / gauge / I-O",
            "dyn-kernel cudaEvent durations only");
    }
};

}  // namespace gelb

#endif  // GELB_GPU_CUDA_CPP_RUNTIME_CUH
