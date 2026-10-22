"""Device-side state emission for gpu_cuda_cpp.

Device-heap lattice storage (cudaMalloc + __device__ base pointer),
device gauge buffers, and the cuRAND per-thread state machinery.
"""

from __future__ import annotations

from gelb.backends.highway.common import (
    _lname,
    _TYPE_MAP,
)

from gelb.gelb_ast.ASTNodes import (
    VariableDeclarationStmt_N,
)


class CudaDeviceStateMixin:
    """Mixin: see module docstring.  Assembled into
    ``CudaCppCodeGenerator`` (stage3_backend_gpu_cuda_cpp);
    must precede ``HighwayCodeGenerator`` in the MRO so the
    overrides here shadow the parent's CPU emission.
    """

    def _emit_lattice_declarations(self) -> None:
        """Emit `__device__` storage and `__device__` ping-pong
        indices at file scope.

        Replaces parent's host-side ``static`` array declaration
        and skips the halo-update lambda (replaced by file-scope
        ``__global__`` kernels emitted by
        ``_emit_halo_update_kernels``).

        Buffer indices are device-resident so the kernels read
        the current OLD/NEW selection from device memory at
        launch time.  This makes the iteration body capturable
        into a single ``cudaGraph_t`` (kernel-arg lists no
        longer encode the per-iteration swap state).  Body code
        emitted by the parent references these by name --
        ``g_<lname>_storage[g_<lname>_old]<subs>`` etc. -- and
        works unchanged because the symbol now resolves to the
        device global.
        """
        # File-scope: __device__ storage globals.  Caller has already
        # set _emit_target to 'device' via generate().
        sizes = self._storage_sizes()
        rev_dim_str = ''.join(f'[{n}]' for n in reversed(sizes))
        self._emit('// Lattice arrays (ping-pong) -- SoA on the GPU;'
                   ' buffer indices are device-resident')
        self._emit('// so capture into cudaGraph_t works.  Storage is'
                   ' cudaMalloc-ed at startup')
        self._emit('// (static `__device__` arrays past ~2 GB break the'
                   ' link step); the pointer-')
        self._emit('// to-buffer type keeps kernel subscripts identical'
                   ' to the static-array form.')
        for lname, info in self._lattice_info.items():
            q = info['q']
            cpp_dtype = _TYPE_MAP[info['dtype']]
            self._emit(f'// {lname}: SoA [buf][{q}][...y][x],'
                       f' halo +1 cell each axis-end')
            self._emit(f'using {_lname(lname)}_buf_t = {cpp_dtype}'
                       f'[{q}]{rev_dim_str};')
            self._emit(f'__device__ {_lname(lname)}_buf_t* {_lname(lname)}_storage;')
            self._emit(f'__device__ int {_lname(lname)}_old = 0;')
            self._emit(f'__device__ int {_lname(lname)}_new = 1;')
        if self._uses_t:
            # Device-resident timestep counter.  Same motivation as
            # the ping-pong indices above: cudaGraph capture freezes
            # kernel-arg lists at capture time, so passing the host's
            # ``gelb_timestep`` would replay every iteration with
            # ``t = 0``.  ``gelb_inc_t`` (emitted next to the swap
            # kernels) bumps this from inside the captured graph.
            self._emit('__device__ int gelb_timestep_d = 0;')
        self._emit('')

    def _emit_halo_update_lambdas(self) -> None:
        # No-op: parent calls this from ``_emit_lattice_declarations``;
        # we already skip that call (our override doesn't invoke
        # ``self._emit_halo_update_lambdas()``).  Definition kept here
        # in case anything else in parent's machinery calls it.
        return

    def _emit_lattice_storage_alloc(self) -> None:
        """Allocate the ping-pong lattice storage on the device heap
        and publish the base pointer to the ``__device__``
        ``g_<lname>_storage`` symbol.

        Runs once at the top of ``main()``, before any kernel launch
        and before cudaGraph capture, so the pointer is constant for
        the whole run (capture-safe).  ``cudaMemset`` fills the storage
        (zero, or the poison byte under ``--poison-uninit``), so a
        never-written cell holds a defined value.
        """
        fill_byte = '0xFF' if self._poison_uninit else '0'
        if self._poison_uninit:
            self._emit('// Device-heap lattice storage (ping-pong'
                       ' pairs); POISON-filled (0xFF: every')
            self._emit('// uninitialized double reads as NaN) per'
                       ' gelbc --poison-uninit.')
        else:
            self._emit('// Device-heap lattice storage (ping-pong'
                       ' pairs); zero-filled to match')
            self._emit('// static-array initialization.')
        for lname in self._lattice_info:
            self._emit(f'void* gelb_{lname}_storage_p = nullptr;')
            self._emit(f'CUDA_CHECK(cudaMalloc(&gelb_{lname}_storage_p,'
                       f' 2 * sizeof({_lname(lname)}_buf_t)));')
            self._emit(f'CUDA_CHECK(cudaMemset(gelb_{lname}_storage_p,'
                       f' {fill_byte}, 2 * sizeof({_lname(lname)}_buf_t)));')
            self._emit(f'CUDA_CHECK(cudaMemcpyToSymbol('
                       f'{_lname(lname)}_storage, &gelb_{lname}_storage_p,'
                       f' sizeof(void*)));')
        self._emit('')

    def _emit_device_gauge_buffers(self) -> None:
        """Emit ``__device__`` mirror of each host gauge buffer at
        file scope.  Same shape (`[NY][NX]` for 2D); the gauge
        kernels write here, then ``cudaMemcpyFromSymbol`` copies to
        the host counterpart before NetCDF write.
        """
        gauge = self._gauge_output_layout()
        if gauge is None:
            return
        rev_axes = list(reversed([self._axis(i) for i in range(self._d)]))
        buf_dims = ''.join(f'[g__n{a}]' for a in rev_axes)
        self._emit('// Gauge buffers -- device-side (paired with host)')
        for decl in gauge.outputs:
            if isinstance(decl, VariableDeclarationStmt_N):
                vname = decl.name.name
                cpp_type = self._gauge_buffer_cpp_type(decl)
                self._emit(f'__device__ {cpp_type} '
                           f'gelb_buf_{vname}_d{buf_dims};')
        self._emit('')

    def _emit_curand_decls(self) -> None:
        """Emit ``__device__`` cuRAND state array + init kernel +
        ``gelb_random()`` device function at file scope.  No-op when
        the program doesn't use ``random()``.

        per-thread state, init via ``curand_init(seed, tid,
        0, &state[tid])``, draw via ``curand_uniform_double``.
        Tid is derived from ``blockIdx`` + ``threadIdx`` so the
        same function works regardless of 1D / 2D / 3D launch
        shape (parent's ``random()`` intrinsic emits
        ``gelb_random()`` with no args at the call site, so the
        function self-derives its tid).
        """
        if not self._uses_random:
            return

        saved_target = self._emit_target
        saved_indent = self._indent
        self._emit_target = 'device'
        self._indent = 0

        total = self._launch_total_threads()
        # cuRAND include lives here (not in the runtime header) so
        # random-free programs avoid the cost.  Empirically, pulling in
        # cuRAND unconditionally slowed random-free programs even when
        # the generated CUDA body was otherwise unchanged.
        self._emit('#include <curand_kernel.h>')
        self._emit('')
        self._emit('// cuRAND per-thread RNG state + init kernel +'
                   ' gelb_random() device fn.')
        self._emit('// Wrapped in `namespace gelb { ... }` so'
                   ' parent-emitted ``gelb::gelb_random()`` calls'
                   ' resolve correctly (mirrors the cpu_highway'
                   ' runtime header pattern).')
        self._emit('namespace gelb {')
        self._emit('')
        self._emit(f'// One independent xorwow stream per launch-grid'
                   f' thread (sized to the post-ceil-div grid total'
                   f' {total}).')
        self._emit(
            f'__device__ curandStateXORWOW gelb_rng_states[{total}];')
        self._emit('')

        # Tid derivation: 1D linearisation of (blockIdx, threadIdx)
        # within the current launch.  Works for 1D / 2D / 3D
        # launches because the unused dims have gridDim=1, blockDim=1.
        tid_decl = (
            'int gelb_tid = '
            '(blockIdx.z * gridDim.y * gridDim.x'
            ' + blockIdx.y * gridDim.x + blockIdx.x)'
            ' * (blockDim.x * blockDim.y * blockDim.z)'
            ' + (threadIdx.z * blockDim.y * blockDim.x'
            ' + threadIdx.y * blockDim.x + threadIdx.x);')

        self._emit('// Init kernel -- one curand_init per thread;'
                   ' called once from main() with the user --seed'
                   ' (or a clock-derived default).')
        self._emit('__global__ void gelb_rng_init('
                   'unsigned long long seed) {')
        self._indent = 1
        self._emit(tid_decl)
        self._emit(f'if (gelb_tid >= {total}) return;')
        self._emit('curand_init(seed, gelb_tid, 0,'
                   ' &gelb_rng_states[gelb_tid]);')
        self._indent = 0
        self._emit('}')
        self._emit('')

        self._emit('// Uniform double in [0, 1) (user manual, Numerical'
                   ' semantics: Random numbers): curand_uniform_double'
                   ' draws in (0, 1], so the draw is reflected.  Called'
                   ' from kernel bodies wherever the user program writes'
                   ' ``random()``.')
        self._emit('__device__ inline double gelb_random() {')
        self._indent = 1
        self._emit(tid_decl)
        self._emit('return 1.0 - curand_uniform_double('
                   '&gelb_rng_states[gelb_tid]);')
        self._indent = 0
        self._emit('}')
        self._emit('')
        self._emit('}  // namespace gelb')
        self._emit('')

        self._emit_target = saved_target
        self._indent = saved_indent
