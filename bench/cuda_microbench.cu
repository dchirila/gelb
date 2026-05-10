// GeLB Phase-4 CUDA microbenchmark harness
// =========================================
//
// Wilt-style per-op probes for the GPU executing the
// gpu_cuda_cpp backend.  Establishes the hardware ceiling
// against which Phase-4 perf-tuning targets are measured.
//
// Wilt's *CUDA Handbook* technique transfers verbatim; the
// numbers in the book pre-date Ada (sm_89), so we re-measure
// here.  Probes (Phase-4 narrow scope):
//
//   1. Empty-kernel launch latency
//   2. GMEM streaming bandwidth — copy (read + write)
//   3. GMEM streaming bandwidth — read-only
//   4. GMEM streaming bandwidth — write-only
//   5. L2 cache cliff — sweep working-set size
//   6. Shared-memory bandwidth — bank-conflict-free
//
// Build:
//   nvcc -O3 -arch=sm_89 -std=c++17 -o cuda_microbench \
//        bench/cuda_microbench.cu
//   ./cuda_microbench
//
// Output goes to stdout in a copy-paste-friendly markdown
// table format suitable for ``docs/perf_gpu_ada_microbench.md``.

#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <chrono>
#include <vector>
#include <cuda_runtime.h>

#define CUDA_CHECK(call) do {                                       \
    cudaError_t _rc = (call);                                       \
    if (_rc != cudaSuccess) {                                       \
        std::fprintf(stderr, "CUDA error at %s:%d: %s -- %s\n",     \
                     __FILE__, __LINE__, #call,                     \
                     cudaGetErrorString(_rc));                      \
        std::exit(1);                                               \
    }                                                               \
} while (0)

// ----------------------------------------------------------------
// Probe 1 — empty-kernel launch latency
// ----------------------------------------------------------------

__global__ void empty_kernel() {}

double probe_launch_latency_us(int n_launches) {
    // Warmup
    for (int i = 0; i < 100; ++i) empty_kernel<<<1, 1>>>();
    CUDA_CHECK(cudaDeviceSynchronize());

    cudaEvent_t start, stop;
    CUDA_CHECK(cudaEventCreate(&start));
    CUDA_CHECK(cudaEventCreate(&stop));

    CUDA_CHECK(cudaEventRecord(start));
    for (int i = 0; i < n_launches; ++i) empty_kernel<<<1, 1>>>();
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));

    float ms = 0;
    CUDA_CHECK(cudaEventElapsedTime(&ms, start, stop));
    CUDA_CHECK(cudaEventDestroy(start));
    CUDA_CHECK(cudaEventDestroy(stop));

    return 1000.0 * ms / n_launches;  // us per launch
}

// ----------------------------------------------------------------
// Probes 2-4 — GMEM streaming bandwidth
// ----------------------------------------------------------------

__global__ void k_copy_rw(double* __restrict__ dst,
                          const double* __restrict__ src,
                          std::size_t n) {
    std::size_t i = blockIdx.x * (std::size_t)blockDim.x + threadIdx.x;
    std::size_t stride = (std::size_t)gridDim.x * blockDim.x;
    for (; i < n; i += stride) dst[i] = src[i];
}

__global__ void k_read_only(const double* __restrict__ src,
                            double* __restrict__ sink,
                            std::size_t n) {
    std::size_t i = blockIdx.x * (std::size_t)blockDim.x + threadIdx.x;
    std::size_t stride = (std::size_t)gridDim.x * blockDim.x;
    double s = 0.0;
    for (; i < n; i += stride) s += src[i];
    // Sink to prevent dead-code elimination — write only one
    // value per block to keep it cheap.
    if (threadIdx.x == 0) sink[blockIdx.x] = s;
}

__global__ void k_write_only(double* __restrict__ dst,
                             double value,
                             std::size_t n) {
    std::size_t i = blockIdx.x * (std::size_t)blockDim.x + threadIdx.x;
    std::size_t stride = (std::size_t)gridDim.x * blockDim.x;
    for (; i < n; i += stride) dst[i] = value;
}

double bandwidth_gbs(double bytes, float ms) {
    return bytes / (ms / 1000.0) / 1e9;
}

double probe_gmem_copy_bw(std::size_t n_doubles, int iters) {
    double *src, *dst;
    CUDA_CHECK(cudaMalloc(&src, n_doubles * sizeof(double)));
    CUDA_CHECK(cudaMalloc(&dst, n_doubles * sizeof(double)));
    CUDA_CHECK(cudaMemset(src, 0, n_doubles * sizeof(double)));

    int block = 256;
    int grid = (int)((n_doubles + block - 1) / block);
    if (grid > 65535) grid = 65535;

    // Warmup
    k_copy_rw<<<grid, block>>>(dst, src, n_doubles);
    CUDA_CHECK(cudaDeviceSynchronize());

    cudaEvent_t a, b;
    CUDA_CHECK(cudaEventCreate(&a));
    CUDA_CHECK(cudaEventCreate(&b));
    CUDA_CHECK(cudaEventRecord(a));
    for (int i = 0; i < iters; ++i)
        k_copy_rw<<<grid, block>>>(dst, src, n_doubles);
    CUDA_CHECK(cudaEventRecord(b));
    CUDA_CHECK(cudaEventSynchronize(b));
    float ms = 0;
    CUDA_CHECK(cudaEventElapsedTime(&ms, a, b));

    // Bytes per iter: 1 read + 1 write per double = 16 B
    double bytes = (double)iters * n_doubles * 16.0;
    double gbs = bandwidth_gbs(bytes, ms);

    CUDA_CHECK(cudaFree(src));
    CUDA_CHECK(cudaFree(dst));
    CUDA_CHECK(cudaEventDestroy(a));
    CUDA_CHECK(cudaEventDestroy(b));
    return gbs;
}

double probe_gmem_read_bw(std::size_t n_doubles, int iters) {
    double *src, *sink;
    CUDA_CHECK(cudaMalloc(&src, n_doubles * sizeof(double)));
    int block = 256;
    int grid = (int)((n_doubles + block - 1) / block);
    if (grid > 65535) grid = 65535;
    CUDA_CHECK(cudaMalloc(&sink, grid * sizeof(double)));
    CUDA_CHECK(cudaMemset(src, 0, n_doubles * sizeof(double)));

    k_read_only<<<grid, block>>>(src, sink, n_doubles);
    CUDA_CHECK(cudaDeviceSynchronize());

    cudaEvent_t a, b;
    CUDA_CHECK(cudaEventCreate(&a));
    CUDA_CHECK(cudaEventCreate(&b));
    CUDA_CHECK(cudaEventRecord(a));
    for (int i = 0; i < iters; ++i)
        k_read_only<<<grid, block>>>(src, sink, n_doubles);
    CUDA_CHECK(cudaEventRecord(b));
    CUDA_CHECK(cudaEventSynchronize(b));
    float ms = 0;
    CUDA_CHECK(cudaEventElapsedTime(&ms, a, b));

    // Bytes per iter: 1 read per double = 8 B (sink is negligible)
    double bytes = (double)iters * n_doubles * 8.0;
    double gbs = bandwidth_gbs(bytes, ms);

    CUDA_CHECK(cudaFree(src));
    CUDA_CHECK(cudaFree(sink));
    CUDA_CHECK(cudaEventDestroy(a));
    CUDA_CHECK(cudaEventDestroy(b));
    return gbs;
}

double probe_gmem_write_bw(std::size_t n_doubles, int iters) {
    double *dst;
    CUDA_CHECK(cudaMalloc(&dst, n_doubles * sizeof(double)));
    int block = 256;
    int grid = (int)((n_doubles + block - 1) / block);
    if (grid > 65535) grid = 65535;

    k_write_only<<<grid, block>>>(dst, 1.0, n_doubles);
    CUDA_CHECK(cudaDeviceSynchronize());

    cudaEvent_t a, b;
    CUDA_CHECK(cudaEventCreate(&a));
    CUDA_CHECK(cudaEventCreate(&b));
    CUDA_CHECK(cudaEventRecord(a));
    for (int i = 0; i < iters; ++i)
        k_write_only<<<grid, block>>>(dst, 1.0 + i, n_doubles);
    CUDA_CHECK(cudaEventRecord(b));
    CUDA_CHECK(cudaEventSynchronize(b));
    float ms = 0;
    CUDA_CHECK(cudaEventElapsedTime(&ms, a, b));

    double bytes = (double)iters * n_doubles * 8.0;
    double gbs = bandwidth_gbs(bytes, ms);

    CUDA_CHECK(cudaFree(dst));
    CUDA_CHECK(cudaEventDestroy(a));
    CUDA_CHECK(cudaEventDestroy(b));
    return gbs;
}

// ----------------------------------------------------------------
// Probe 5 — L2 cache cliff (sweep working-set size)
// ----------------------------------------------------------------

void probe_l2_cliff() {
    // Working-set sizes from 64 KB to 256 MB (log2 sweep).
    // RTX 4080 Laptop has ~32 MB L2; expected cliff somewhere
    // around 16-32 MB.
    std::printf("\n## Probe 5 — L2 cache cliff (read-only bandwidth vs WSS)\n\n");
    std::printf("| Working set | GB/s |\n|---:|---:|\n");
    for (int log2_kb = 6; log2_kb <= 18; ++log2_kb) {
        std::size_t n_doubles = (1ULL << log2_kb) * 1024 / 8;  // log2_kb -> KB -> doubles
        if (n_doubles < 1024) continue;
        // Use enough iters to amortise launch overhead
        int iters = (int)(64ULL << 20) / (int)(n_doubles);
        if (iters < 4) iters = 4;
        if (iters > 256) iters = 256;
        double gbs = probe_gmem_read_bw(n_doubles, iters);
        double mb = (double)(n_doubles * 8) / (1024.0 * 1024.0);
        std::printf("| %.1f MB | %.1f |\n", mb, gbs);
    }
}

// ----------------------------------------------------------------
// Probe 6 — Shared-memory bandwidth (no bank conflicts)
// ----------------------------------------------------------------

__global__ void k_shared_bw(double* __restrict__ sink,
                            int n_iter) {
    extern __shared__ double smem[];
    int tid = threadIdx.x;
    smem[tid] = (double)tid;
    __syncthreads();
    double s = 0.0;
    // Each thread reads its own slot n_iter times — fully
    // bank-conflict-free (32 banks × 4 B = 128 B; 64-bit reads
    // pair across two banks, still conflict-free for 1 thread
    // per slot).
    for (int i = 0; i < n_iter; ++i) s += smem[tid] * i;
    if (tid == 0) sink[blockIdx.x] = s;
}

double probe_shared_bw(int block, int n_iter, int n_blocks) {
    double *sink;
    CUDA_CHECK(cudaMalloc(&sink, n_blocks * sizeof(double)));
    int smem_bytes = block * (int)sizeof(double);

    k_shared_bw<<<n_blocks, block, smem_bytes>>>(sink, n_iter);
    CUDA_CHECK(cudaDeviceSynchronize());

    cudaEvent_t a, b;
    CUDA_CHECK(cudaEventCreate(&a));
    CUDA_CHECK(cudaEventCreate(&b));
    CUDA_CHECK(cudaEventRecord(a));
    for (int i = 0; i < 20; ++i)
        k_shared_bw<<<n_blocks, block, smem_bytes>>>(sink, n_iter);
    CUDA_CHECK(cudaEventRecord(b));
    CUDA_CHECK(cudaEventSynchronize(b));
    float ms = 0;
    CUDA_CHECK(cudaEventElapsedTime(&ms, a, b));

    // Bytes per iter: each thread reads 8 B × n_iter, n_blocks
    // blocks × block threads, 20 iters.
    double bytes = 20.0 * n_blocks * block * (double)n_iter * 8.0;
    double gbs = bandwidth_gbs(bytes, ms);

    CUDA_CHECK(cudaFree(sink));
    CUDA_CHECK(cudaEventDestroy(a));
    CUDA_CHECK(cudaEventDestroy(b));
    return gbs;
}

// ----------------------------------------------------------------
// Main
// ----------------------------------------------------------------

int main() {
    int dev = 0;
    cudaDeviceProp p;
    CUDA_CHECK(cudaGetDeviceProperties(&p, dev));
    std::printf("# GeLB CUDA microbench — %s\n\n", p.name);
    std::printf("- Compute capability: sm_%d%d\n", p.major, p.minor);
    std::printf("- SMs: %d\n", p.multiProcessorCount);
    std::printf("- L2 cache: %d MB\n", p.l2CacheSize / (1024 * 1024));
    std::printf("- Memory: %.1f GB GDDR%s @ %.1f GB/s peak (theoretical)\n",
                (double)p.totalGlobalMem / (1024.0 * 1024.0 * 1024.0),
                "6X",  // sm_89 family ships GDDR6/6X
                p.memoryBusWidth * (double)p.memoryClockRate * 2.0
                    / 8.0 / 1.0e6);

    // ---- Probe 1: launch latency ----
    std::printf("\n## Probe 1 — empty-kernel launch latency\n\n");
    double us = probe_launch_latency_us(10000);
    std::printf("- %.2f us per launch (10000 launches)\n", us);

    // ---- Probes 2-4: GMEM bandwidth at large WSS (DRAM-bound) ----
    std::printf("\n## Probes 2-4 — GMEM streaming bandwidth (256 MB WSS)\n\n");
    std::size_t n = 256ULL * 1024 * 1024 / 8;  // 256 MB / 8 B
    int iters = 10;
    std::printf("| Mode | GB/s |\n|---|---:|\n");
    std::printf("| Copy (1R + 1W) | %.1f |\n", probe_gmem_copy_bw(n, iters));
    std::printf("| Read only      | %.1f |\n", probe_gmem_read_bw(n, iters));
    std::printf("| Write only     | %.1f |\n", probe_gmem_write_bw(n, iters));

    // ---- Probe 5: L2 cliff ----
    probe_l2_cliff();

    // ---- Probe 6: shared bandwidth ----
    std::printf("\n## Probe 6 — Shared-memory bandwidth (bank-conflict-free)\n\n");
    int n_blocks = p.multiProcessorCount * 4;  // saturate occupancy
    std::printf("- block=256, smem=2 KB/block, %d blocks: %.1f GB/s\n",
                n_blocks, probe_shared_bw(256, 1024, n_blocks));

    return 0;
}
