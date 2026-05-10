"""File-scope `__global__` kernel emission for gpu_cuda_cpp.

Per-block dynamic kernels (thread-idx derivation, bbox + nc_map
guards), halo-update kernels, the ping-pong swap kernels, the
masked-cell zero-init kernel, and the gauge NaN-init kernel.
"""

from __future__ import annotations

from gelb.backends.highway.common import _lname

from gelb.gelb_ast.ASTNodes import (
    VariableDeclarationStmt_N,
)

from gelb.midware.ast_eval import (
    is_periodic,
)


class CudaKernelEmitMixin:
    """Mixin: see module docstring.  Assembled into
    ``CudaCppCodeGenerator`` (stage3_backend_gpu_cuda_cpp);
    must precede ``HighwayCodeGenerator`` in the MRO so the
    overrides here shadow the parent's CPU emission.
    """

    def _emit_nc_map_decl(self) -> None:
        """Emit ``__device__ const int gelb_nc_map[...] = {...};``
        at file scope when at least one NC is non-dense.

        Storage layout matches midware's ``ResolvedGeometry.nc_map``:
        ``np.array`` of shape ``grid_sizes`` with x-major
        (slowest-varying) ordering, flattened via
        ``idx = x * NY * NZ + y * NZ + z`` (3D) /
        ``idx = x * NY + y`` (2D) / ``idx = x`` (1D).
        Values are 1-based NC IDs (per midware convention).
        """
        if not self._uses_nc_map:
            return

        saved_target = self._emit_target
        saved_indent = self._indent
        self._emit_target = 'device'
        self._indent = 0

        nc_map = self._geom.nc_map  # numpy array, shape = grid_sizes
        flat = nc_map.ravel(order='C').astype(int).tolist()
        # Single-line literal (long but fine for nvcc).  Source
        # size: ~6 chars per int * total.  channel_flow_circle
        # at NX=1024, NY=128 = 131072 ints ~= 800 KB source.
        # nvcc compile time impact: tolerable (~10-30 s extra
        # on the first compile).
        sizes_decl = ''.join(f'[{n}]' for n in self._grid_sizes())
        self._emit('// Per-cell node-class ID map.  Indexed in source-')
        self._emit('// AST coord order (x outer, z inner for 3D).')
        self._emit('// Used by per-NC kernels with non-dense bboxes')
        self._emit('// (multi-NC programs with masked obstacles, etc.)')
        self._emit('// to early-exit threads landing in cells of other NCs.')
        # Pretty-print the literal as `{ a, b, c, ... }` on one line.
        body = ', '.join(str(v) for v in flat)
        self._emit(f'__device__ const int gelb_nc_map{sizes_decl} = '
                   f'{{ {body} }};')
        self._emit('')

        self._emit_target = saved_target
        self._indent = saved_indent

    def _emit_nc_id_guard(self, rect_info,
                           coarsened: bool = False) -> None:
        """Emit the per-cell NC-ID guard inside the kernel body.

        For non-dense NCs only; dense NCs get covered fully by
        the bbox guard alone.  Must be emitted AFTER
        ``_emit_thread_idx_derivation`` so ``g_x`` / ``g_y`` /
        ``g_z`` are in scope.

        Coarsened mode: per-cell-iteration check; failed check
        ``continue``s to skip just this cell and try the next.
        Standard mode: ``return`` exits the whole thread.
        """
        if rect_info.bbox is None or rect_info.bbox_dense:
            return
        nc_id = rect_info.nc_id
        # Build subscript matching _emit_nc_map_decl's shape:
        # `[g_x][g_y]` (2D), `[g_x][g_y][g_z]` (3D), `[g_x]` (1D).
        subs = ''.join(f'[g_{self._axis(i)}]' for i in range(self._d))
        stmt = 'continue' if coarsened else 'return'
        self._emit(f'if (gelb_nc_map{subs} != {nc_id}) {stmt};')

    def _emit_masked_zero_init_kernel(self) -> None:
        """Emit a ``__global__`` kernel zeroing the DFs of every
        masked-NC cell (both ping-pong buffers, all lattices).

        Language guarantee: masked cells hold zero DFs (see
        LANGUAGE_DESIGN.md and the cpu_highway host-side
        counterpart ``_emit_masked_lattice_zero_init``).  The
        explicit write makes the guarantee independent of the
        ``cudaMemset`` fill, so ``--poison-uninit`` only flags
        reads that are genuinely undefined.

        Masked-cell test, per masked NC: non-dense NCs check
        ``gelb_nc_map`` (always emitted when a non-dense NC
        exists); dense NCs check their literal bbox.
        """
        if not self._any_masked_nc():
            return

        saved_target = self._emit_target
        saved_indent = self._indent
        self._emit_target = 'device'
        self._indent = 0

        self._emit('// Masked-cell DF zero-init: language guarantee'
                   ' that masked cells hold')
        self._emit('// zero DFs in both buffers.  Launched once from'
                   ' main() before the')
        self._emit('// initializer kernels.')
        self._emit('__global__ void gelb_masked_zero_init() {')
        self._indent = 1
        sizes = self._grid_sizes()
        self._emit('int g_x = blockIdx.x * blockDim.x + threadIdx.x;')
        guard_terms = [f'g_x >= {sizes[0]}']
        if self._d >= 2:
            self._emit('int g_y = blockIdx.y * blockDim.y'
                       ' + threadIdx.y;')
            guard_terms.append(f'g_y >= {sizes[1]}')
        if self._d >= 3:
            self._emit('int g_z = blockIdx.z * blockDim.z'
                       ' + threadIdx.z;')
            guard_terms.append(f'g_z >= {sizes[2]}')
        self._emit(f'if ({" || ".join(guard_terms)}) return;')

        nc_subs = ''.join(f'[g_{self._axis(i)}]' for i in range(self._d))
        masked_terms = []
        for nc_name, info in self._geom.nc_info.items():
            if not info.masked:
                continue
            if info.bbox is not None and not info.bbox_dense:
                masked_terms.append(f'(gelb_nc_map{nc_subs} == '
                                    f'{info.nc_id})')
            elif info.bbox is not None:
                bounds = []
                for i, (lo, hi) in enumerate(info.bbox):
                    ax = self._axis(i)
                    bounds.append(f'g_{ax} >= {lo} && g_{ax} <= {hi}')
                masked_terms.append(f'({" && ".join(bounds)})')
            else:
                masked_terms.append('true')
        self._emit(f'if (!({" || ".join(masked_terms)})) return;')

        coord_strs = [f'g_{self._axis(i)}' for i in range(self._d)]
        for lname, linfo in self._lattice_info.items():
            q = linfo['q']
            subs = self._storage_subscript(coord_strs, 'gelb_df', lname)
            self._emit(f'for (int gelb_buf = 0; gelb_buf < 2;'
                       f' ++gelb_buf) {{')
            self._indent += 1
            self._emit(f'for (int gelb_df = 0; gelb_df < {q};'
                       f' ++gelb_df) {{')
            self._indent += 1
            self._emit(f'{_lname(lname)}_storage[gelb_buf]{subs} = 0.0;')
            self._indent -= 1
            self._emit('}')
            self._indent -= 1
            self._emit('}')

        self._indent = 0
        self._emit('}')
        self._emit('')

        self._emit_target = saved_target
        self._indent = saved_indent

    def _emit_gauge_nan_init_kernel(self, gauge) -> None:
        """Initialize device outputs not produced by every node class.

        Real fields use NaN; integer fields use zero. Each class's gauge
        then overwrites its own fields and cells.
        """
        if gauge is None or not gauge.partial:
            return

        saved_target = self._emit_target
        saved_indent = self._indent
        self._emit_target = 'device'
        self._indent = 0

        self._emit('// Gauge NaN-init: covers masked-cell positions'
                   ' (cells whose NC has no gauge fill); per-NC'
                   ' gauge kernels overwrite their own cells.')
        self._emit('__global__ void gelb_gauge_nan_init() {')
        self._indent = 1
        sizes = self._grid_sizes()
        if self._d == 1:
            self._emit('int g_x = blockIdx.x * blockDim.x + threadIdx.x;')
            self._emit(f'if (g_x >= {sizes[0]}) return;')
        elif self._d == 2:
            self._emit('int g_x = blockIdx.x * blockDim.x + threadIdx.x;')
            self._emit('int g_y = blockIdx.y * blockDim.y + threadIdx.y;')
            self._emit(f'if (g_x >= {sizes[0]} || g_y >= {sizes[1]})'
                       f' return;')
        else:
            self._emit('int g_x = blockIdx.x * blockDim.x + threadIdx.x;')
            self._emit('int g_y = blockIdx.y * blockDim.y + threadIdx.y;')
            self._emit('int g_z = blockIdx.z * blockDim.z + threadIdx.z;')
            self._emit(f'if (g_x >= {sizes[0]} || g_y >= {sizes[1]}'
                       f' || g_z >= {sizes[2]}) return;')

        # Coord subscript: matches _emit_device_gauge_buffers shape
        # (slowest-to-fastest, i.e. [g_z][g_y][g_x] in 3D).
        rev_axes = list(reversed(range(self._d)))
        coord_subs = ''.join(f'[g_{self._axis(i)}]' for i in rev_axes)

        for decl in gauge.outputs:
            if isinstance(decl, VariableDeclarationStmt_N):
                vname = decl.name.name
                cpp_type = self._gauge_buffer_cpp_type(decl)
                value = (f'std::numeric_limits<{cpp_type}>::quiet_NaN()'
                         if cpp_type in ('float', 'double') else '0')
                self._emit(f'gelb_buf_{vname}_d{coord_subs} = {value};')

        self._indent = 0
        self._emit('}')
        self._emit('')

        self._emit_target = saved_target
        self._indent = saved_indent

    def _emit_swap_kernels(self) -> None:
        """Emit one ``__global__ void gelb_swap_<lname>()`` per
        lattice at file scope.  Each runs as ``<<<1, 1>>>`` and
        swaps the device-resident ping-pong indices in-place,
        replacing the previous host-side ``std::swap`` so the
        per-iteration body holds no host state.

        Also emits ``gelb_inc_t()`` (1-thread) when the program
        reads the implicit ``t`` symbol, so the captured graph can
        bump ``gelb_timestep_d`` per iteration without re-baking
        kernel arguments.
        """
        for lname in self._lattice_info:
            self._emit(f'__global__ void gelb_swap_{lname}() {{')
            self._indent = 1
            self._emit(f'int t = {_lname(lname)}_old;')
            self._emit(f'{_lname(lname)}_old = {_lname(lname)}_new;')
            self._emit(f'{_lname(lname)}_new = t;')
            self._indent = 0
            self._emit('}')
            self._emit('')
        if self._uses_t:
            self._emit('__global__ void gelb_inc_t() {'
                       ' gelb_timestep_d += 1; }')
            self._emit('')

    def _emit_halo_update_kernels(self) -> None:
        """Emit one ``__global__ void`` halo kernel per (lattice,
        periodic axis) at file scope.  Each kernel handles BOTH ghost slabs
        (low + high) for its axis in a single thread-decomposition.
        """
        for lname, info in self._lattice_info.items():
            d = info['d']
            q = info['q']
            per = [is_periodic(self._lattice_info, i) for i in range(d)]
            for axis_idx in range(d):
                if per[axis_idx]:
                    self._emit_halo_update_kernel(lname, q, d, axis_idx)

    def _emit_halo_update_kernel(self, lname: str, q: int, d: int,
                                  axis_idx: int) -> None:
        """One halo kernel for one periodic axis.  Sweep order is x,
        then y, then z.  Later-axis kernels include already-populated
        ghost cells from earlier-axis sweeps so corner and edge ghosts
        propagate correctly.
        """
        kname = f'gelb_halo_{lname}_axis_{axis_idx}'
        sizes = self._grid_sizes()
        # No ``int buf`` parameter -- the kernel reads the
        # device-resident OLD-buffer index directly via the
        # local-name binding below.  Keeping the body's ``buf``
        # spelling lets the per-axis emit blocks stay verbatim.
        self._emit(f'__global__ void {kname}() {{')
        self._indent = 1
        self._emit(f'const int buf = {_lname(lname)}_old;')

        # Sweep order x -> y -> z.  For axis i, the OTHER axes
        # iterate over [0, N+1] when their index j < i (already
        # swept for periodic, so corner ghosts flow in) and over
        # [1, N] otherwise.  Mirrors parent's _emit_halo_axis_copy
        # logic at cpu_highway:1335-1357.

        if d == 1:
            # Only one axis (axis_idx must be 0).  No "other axes"
            # to iterate.  One thread per DF.
            assert axis_idx == 0
            nx = sizes[0]
            self._emit('int gelb_df = blockIdx.x * blockDim.x'
                       ' + threadIdx.x;')
            self._emit(f'if (gelb_df >= {q}) return;')
            self._emit(f'{_lname(lname)}_storage[buf][gelb_df][0] = '
                       f'{_lname(lname)}_storage[buf][gelb_df][{nx}];')
            self._emit(f'{_lname(lname)}_storage[buf][gelb_df][{nx + 1}] = '
                       f'{_lname(lname)}_storage[buf][gelb_df][1];')

        elif d == 2 and axis_idx == 0:
            # x-axis: thread iterates over y in [1, NY].  For each y,
            # copy DF column at x=NX -> x=0, x=1 -> x=NX+1.
            nx, ny = sizes[0], sizes[1]
            self._emit('int g_y = blockIdx.x * blockDim.x'
                       ' + threadIdx.x + 1;')
            self._emit(f'if (g_y > {ny}) return;')
            self._emit(f'for (int gelb_df = 0; gelb_df < {q};'
                       f' ++gelb_df) {{')
            self._indent = 2
            self._emit(f'{_lname(lname)}_storage[buf][gelb_df][g_y][0] = '
                       f'{_lname(lname)}_storage[buf][gelb_df][g_y][{nx}];')
            self._emit(f'{_lname(lname)}_storage[buf][gelb_df][g_y][{nx + 1}] = '
                       f'{_lname(lname)}_storage[buf][gelb_df][g_y][1];')
            self._indent = 1
            self._emit('}')

        elif d == 2 and axis_idx == 1:
            # y-axis: thread iterates over x in [0, NX+1] (axis 0
            # already swept for periodic).
            nx, ny = sizes[0], sizes[1]
            self._emit('int g_x = blockIdx.x * blockDim.x'
                       ' + threadIdx.x;')
            self._emit(f'if (g_x > {nx + 1}) return;')
            self._emit(f'for (int gelb_df = 0; gelb_df < {q};'
                       f' ++gelb_df) {{')
            self._indent = 2
            self._emit(f'{_lname(lname)}_storage[buf][gelb_df][0][g_x] = '
                       f'{_lname(lname)}_storage[buf][gelb_df][{ny}][g_x];')
            self._emit(f'{_lname(lname)}_storage[buf][gelb_df][{ny + 1}][g_x] = '
                       f'{_lname(lname)}_storage[buf][gelb_df][1][g_x];')
            self._indent = 1
            self._emit('}')

        elif d == 3 and axis_idx == 0:
            # x-axis: iterate y in [1, NY], z in [1, NZ].  Linearize
            # 1D launch via tid = (y-1) + (z-1)*NY; total NY*NZ.
            nx, ny, nz = sizes[0], sizes[1], sizes[2]
            self._emit('int gelb_tid = blockIdx.x * blockDim.x'
                       ' + threadIdx.x;')
            self._emit(f'int g_y = gelb_tid % {ny} + 1;')
            self._emit(f'int g_z = gelb_tid / {ny} + 1;')
            self._emit(f'if (g_z > {nz}) return;')
            self._emit(f'for (int gelb_df = 0; gelb_df < {q};'
                       f' ++gelb_df) {{')
            self._indent = 2
            self._emit(f'{_lname(lname)}_storage[buf][gelb_df][g_z][g_y][0] = '
                       f'{_lname(lname)}_storage[buf][gelb_df][g_z][g_y][{nx}];')
            self._emit(f'{_lname(lname)}_storage[buf][gelb_df][g_z][g_y][{nx + 1}] = '
                       f'{_lname(lname)}_storage[buf][gelb_df][g_z][g_y][1];')
            self._indent = 1
            self._emit('}')

        elif d == 3 and axis_idx == 1:
            # y-axis: iterate x in [0, NX+1] (axis 0 already swept),
            # z in [1, NZ].  Linearize tid = x + (z-1)*(NX+2);
            # total (NX+2)*NZ.
            nx, ny, nz = sizes[0], sizes[1], sizes[2]
            self._emit('int gelb_tid = blockIdx.x * blockDim.x'
                       ' + threadIdx.x;')
            self._emit(f'int g_x = gelb_tid % {nx + 2};')
            self._emit(f'int g_z = gelb_tid / {nx + 2} + 1;')
            self._emit(f'if (g_z > {nz}) return;')
            self._emit(f'for (int gelb_df = 0; gelb_df < {q};'
                       f' ++gelb_df) {{')
            self._indent = 2
            self._emit(f'{_lname(lname)}_storage[buf][gelb_df][g_z][0][g_x] = '
                       f'{_lname(lname)}_storage[buf][gelb_df][g_z][{ny}][g_x];')
            self._emit(f'{_lname(lname)}_storage[buf][gelb_df][g_z][{ny + 1}][g_x] = '
                       f'{_lname(lname)}_storage[buf][gelb_df][g_z][1][g_x];')
            self._indent = 1
            self._emit('}')

        elif d == 3 and axis_idx == 2:
            # z-axis: iterate x in [0, NX+1] (axis 0 swept), y in
            # [0, NY+1] (axis 1 swept).  Linearize tid = x + y*(NX+2);
            # total (NX+2)*(NY+2).
            nx, ny, nz = sizes[0], sizes[1], sizes[2]
            self._emit('int gelb_tid = blockIdx.x * blockDim.x'
                       ' + threadIdx.x;')
            self._emit(f'int g_x = gelb_tid % {nx + 2};')
            self._emit(f'int g_y = gelb_tid / {nx + 2};')
            self._emit(f'if (g_y > {ny + 1}) return;')
            self._emit(f'for (int gelb_df = 0; gelb_df < {q};'
                       f' ++gelb_df) {{')
            self._indent = 2
            self._emit(f'{_lname(lname)}_storage[buf][gelb_df][0][g_y][g_x] = '
                       f'{_lname(lname)}_storage[buf][gelb_df][{nz}][g_y][g_x];')
            self._emit(f'{_lname(lname)}_storage[buf][gelb_df][{nz + 1}][g_y][g_x] = '
                       f'{_lname(lname)}_storage[buf][gelb_df][1][g_y][g_x];')
            self._indent = 1
            self._emit('}')

        else:
            raise NotImplementedError(
                f"_emit_halo_update_kernel: unhandled "
                f"(d={d}, axis_idx={axis_idx}).  Supported dimensions "
                f"are d in {{1, 2, 3}}; scope guard bug?"
            )

        self._indent = 0
        self._emit('}')
        self._emit('')

    def _emit_thread_idx_derivation(self, rect_info,
                                     coarsened: bool = False) -> None:
        """Emit per-thread coord derivation + bbox guards.

        Each kernel thread maps to a single cell (coarsening=1)
        or N consecutive cells along the outer axis
        (coarsening=N, ``coarsened=True``).  Derivation:
          * 1D -- ``g_x = blockIdx.x * blockDim.x + threadIdx.x``
          * 2D -- adds ``g_y`` from the y axis of the launch grid
          * 3D -- adds ``g_z`` from the z axis

        When ``coarsened=True``, the OUTER axis (last spatial
        axis: x for 1D, y for 2D, z for 3D) gets a base coord
        + opens a ``for (int gelb_k = 0; gelb_k < N; ++gelb_k)``
        loop; the bbox guard moves inside the loop.  The caller
        (``_emit_kernel_for_block``) is responsible for closing
        the loop with ``_emit_coarsening_loop_close`` after the
        body emit.

        Early-exit if outside the user grid (handles the
        ``ceil_div`` overshoot from the launch config) AND outside
        the region's bbox.
        """
        sizes = self._grid_sizes()
        k = self._cuda_coarsening if coarsened else 1
        outer_axis = self._d - 1  # x for 1D, y for 2D, z for 3D
        outer_ax_name = self._axis(outer_axis)

        # Emit non-outer axis coords + their early-exit guards.
        # Outer axis coord is deferred to inside the coarsening loop.
        if self._d == 1:
            # Only outer axis exists; no other coords.
            pass
        # A coordinate is a GeLB `int`, int64, in the user expressions
        # this kernel evaluates: `x + 2147483647` must not overflow.
        elif self._d == 2:
            self._emit('int64_t g_x = blockIdx.x * blockDim.x + threadIdx.x;')
            self._emit(f'if (g_x >= {sizes[0]}) return;')
        else:  # d == 3
            self._emit('int64_t g_x = blockIdx.x * blockDim.x + threadIdx.x;')
            self._emit('int64_t g_y = blockIdx.y * blockDim.y + threadIdx.y;')
            self._emit(f'if (g_x >= {sizes[0]} || g_y >= {sizes[1]})'
                       f' return;')

        if k > 1:
            # Coarsened: emit base coord + open loop.
            self._emit(f'int64_t gelb_{outer_ax_name}_base = '
                       f'(blockIdx.{outer_ax_name} * blockDim.{outer_ax_name}'
                       f' + threadIdx.{outer_ax_name}) * {k};')
            self._emit(f'for (int gelb_k = 0; gelb_k < {k}; ++gelb_k) {{')
            self._indent += 1
            self._emit(f'int64_t g_{outer_ax_name} = gelb_{outer_ax_name}_base'
                       f' + gelb_k;')
            self._emit(f'if (g_{outer_ax_name} >= {sizes[outer_axis]}) break;')
        else:
            # Standard: outer-axis coord direct from threadIdx.
            self._emit(f'int64_t g_{outer_ax_name} = blockIdx.{outer_ax_name}'
                       f' * blockDim.{outer_ax_name}'
                       f' + threadIdx.{outer_ax_name};')
            self._emit(f'if (g_{outer_ax_name} >= {sizes[outer_axis]}) return;')

        # Dimension-aware bbox guard.  For each axis, emit a
        # ``g_<ax> < lo || g_<ax> > hi`` clause when the bbox is
        # narrower than the full grid on that axis.  Combined with
        # ``||`` so a thread outside the bbox on ANY axis exits.
        # In coarsened mode, this fires per-cell-iteration via
        # ``continue`` (skip this cell, try the next); in standard
        # mode, ``return`` exits the whole thread.
        bbox_clauses = []
        for i in range(self._d):
            lo, hi = rect_info.bbox[i]
            if lo > 0 or hi < sizes[i] - 1:
                ax = self._axis(i)
                bbox_clauses.append(f'g_{ax} < {lo} || g_{ax} > {hi}')
        if bbox_clauses:
            # Coarsened: skip this cell-iteration via ``continue``;
            # standard: exit the thread via ``return``.
            stmt = 'continue' if k > 1 else 'return'
            self._emit(f'if ({" || ".join(bbox_clauses)}) {stmt};')

    def _emit_kernel_for_block(self, block, phase: str, nc_name: str,
                                rect_info, context: str,
                                gauge_outputs=None) -> None:
        """Emit one ``__global__ void`` kernel to file scope and a
        kernel launch + ``CUDA_CHECK`` in main().

        The kernel body comes from parent's ``_emit_block_body`` --
        same expression / statement / lattice-access emit as
        cpu_highway, just with our redirected ``_emit`` target so
        the lines land in ``self._device_decls`` instead of
        ``self._lines``.

        Args:
            block: AST block (initializer / dynamic / gauge node).
            phase: short name for the kernel ('init', 'dyn', 'gauge',
                   'gauge_t0').
            nc_name: NC name for kernel-name uniqueness.
            rect_info: dispatch-rect info (carries the bbox for the
                       thread-idx guard).
            context: parent's ``_emit_block_body`` context string
                     ('initializer' / 'dynamic' / 'gauge' / etc.).
            gauge_outputs: list of gauge variable names -- when set,
                           the captured body lines get a post-hoc
                           substitution ``gelb_buf_X[ -> gelb_buf_X_d[``
                           so writes target the device buffer.
        """
        self._kernel_counter += 1
        kname = f'gelb_k_{phase}_{nc_name}_{self._kernel_counter}'

        # Build kernel signature + launch arg expressions per context.
        # Body code references the ping-pong indices by name
        # (``g_<ln>_old`` / ``g_<ln>_new``); we pass them as kernel
        # ``int`` parameters with the same name so the body code
        # works unchanged inside the kernel.
        sig_args, call_exprs = self._kernel_args_for_context(context)
        sig_str = ', '.join(sig_args) if sig_args else ''
        call_str = ', '.join(call_exprs) if call_exprs else ''

        # Thread coarsening only applies to the dynamic kernel (init /
        # gauge are typically too small to benefit; coarsening their
        # bodies could even hurt by adding loop overhead to one-shot
        # kernels).
        coarsened = (context == 'dynamic'
                     and self._cuda_coarsening > 1)

        # Shared-memory tiling for the dyn kernel.  Active only when
        # ``--cuda-tiled`` is on AND the program is
        # in scope (all-periodic, single-lattice, single dense NC).
        # Coarsening + tiling is disabled for now: the
        # coarsening loop computes ``g_<outer> = base + k`` which
        # would map multiple cells per thread, defeating the
        # ``g_<axis> -> threadIdx.<axis>`` substitution.
        tiling_active = (context == 'dynamic' and self._cuda_tiled)
        if tiling_active and coarsened:
            raise NotImplementedError(
                "--cuda-tiled is incompatible with"
                " --cuda-coarsening > 1."
                "  The cooperative tile-load uses (threadIdx.<ax>"
                ", blockIdx.<ax>) directly; the coarsening loop's"
                " per-iter g_<ax> = base + k breaks the body's"
                " coord substitution.  A future implementation can emit the"
                " tile load once outside the coarsening loop and"
                " walk the loop's k cells from shared.")
        if tiling_active:
            ok, why = self._cuda_tiling_applicable()
            if not ok:
                raise NotImplementedError(
                    f"--cuda-tiled scope guard: {why}.  Run again"
                    f" without --cuda-tiled.")

        # Capture body to _device_decls.
        saved_target = self._emit_target
        saved_indent = self._indent
        self._emit_target = 'device'
        self._indent = 0
        self._emit(f'__global__ void {kname}({sig_str}) {{')
        body_start = len(self._device_decls)
        self._indent = 1
        # Decide static vs dynamic shared once: anything > 48 KB
        # forces dynamic (ptxas rejects static at compile time on
        # sm_89, even with a runtime carveout opt-in).  The
        # decision drives both the tile-load emit AND the launch
        # site (extra cudaFuncSetAttribute + size launch arg).
        tile_use_dynamic = (tiling_active
                            and self._shared_tile_bytes() > 48 * 1024)
        if tiling_active:
            # Cooperative load + barrier MUST happen before any
            # early-return (bbox guard, nc-id guard, or g_<ax> >= N
            # overshoot guard).  A thread that returns before the
            # __syncthreads() would deadlock the rest of the block.
            self._emit_tile_load(use_dynamic=tile_use_dynamic)
        # Track where the body proper begins -- substitution and
        # cache-hint passes only operate on the body, NOT on the
        # tile-load lines (those reference ``g_<ln>_storage[g_<ln>
        # _old]`` for their RHS, which the substitution would
        # otherwise rewrite into a self-copy).
        body_after_tile = len(self._device_decls)
        self._emit_thread_idx_derivation(rect_info, coarsened=coarsened)
        # nc_map dispatch for non-dense NCs.  No-op for dense NCs (bbox
        # guard alone is sufficient).
        self._emit_nc_id_guard(rect_info, coarsened=coarsened)
        self._emit_block_body(block, context=context)
        if coarsened:
            # Close the for-loop opened by _emit_thread_idx_derivation.
            self._indent -= 1
            self._emit('}')
        body_end = len(self._device_decls)
        self._indent = 0
        self._emit('}')
        self._emit('')

        # Restore target before emitting the launch.
        self._emit_target = saved_target
        self._indent = saved_indent

        # Gauge: substitute host-buffer writes to device-buffer writes.
        # Done post-hoc on the captured lines (cleaner than
        # overriding parent's gauge-buffer-fill emit site).
        if gauge_outputs:
            for j in range(body_start, body_end):
                line = self._device_decls[j]
                for vname in gauge_outputs:
                    line = line.replace(f'gelb_buf_{vname}[',
                                        f'gelb_buf_{vname}_d[')
                self._device_decls[j] = line

        # Tile-substitute OLD-buffer reads to shared memory.  Operates
        # only on the body PROPER (skips the tile-load lines whose RHS
        # legitimately reads from global).  Must run BEFORE cache hints
        # so the anchor regex can still see unwrapped storage references.
        if tiling_active:
            self._apply_tile_substitution(body_after_tile, body_end)

        # --cuda-ldg / --cuda-stwt cache hints.
        # Applied to the dynamic kernel only (init / gauge writes
        # are too rare for the hint to matter; init reads from
        # nothing meaningful).  Skipped when tiling is on: the
        # OLD-buffer reads have already been redirected to shared
        # memory, and __ldg on shared makes no sense.
        if context == 'dynamic' and not tiling_active:
            self._apply_cache_hints(body_start, body_end)

        # When the shared-memory tile exceeds 48 KB the kernel uses
        # dynamic shared memory (extern __shared__) and opts in to the
        # extended carveout once at first launch via a function-local
        # static bool guard.  Set the attribute to EXACTLY the bytes the
        # tile needs, not the device cap: passing a value above the
        # per-block opt-in queried via cudaDevAttrMaxSharedMemoryPerBlockOptin
        # makes cudaFuncSetAttribute return ``invalid argument``.
        if tile_use_dynamic:
            tile_bytes = self._shared_tile_bytes()
            self._emit(f'// Dynamic shared-mem opt-in for {kname}'
                       f' ({tile_bytes} B/block; default static cap'
                       f' is 48 KB on sm_89).')
            self._emit('{')
            self._indent += 1
            self._emit(f'static bool gelb_attr_{kname} = false;')
            self._emit(f'if (!gelb_attr_{kname}) {{')
            self._indent += 1
            self._emit(f'CUDA_CHECK(cudaFuncSetAttribute({kname},'
                       f' cudaFuncAttributeMaxDynamicSharedMemorySize,'
                       f' {tile_bytes}));')
            self._emit(f'gelb_attr_{kname} = true;')
            self._indent -= 1
            self._emit('}')
            self._indent -= 1
            self._emit('}')

        # Emit launch + per-launch error check in main().  Coarsened
        # dyn kernels use the smaller ``gelb_grid_dyn`` (outer-axis
        # grid count divided by N); init / gauge / non-coarsened
        # contexts use the per-cell ``gelb_grid``.  Dynamic-shared
        # tiled kernels need the per-block byte size as the third
        # launch argument; static-shared kernels omit it.
        grid_var = 'gelb_grid_dyn' if coarsened else 'gelb_grid'
        # When ``self._kernel_stream`` is set, launches use the 4-arg
        # ``<<<grid, block, sharedBytes, stream>>>`` form.  The third
        # arg is required (CUDA syntax forbids skipping ``sharedBytes``
        # when supplying ``stream``); 0 is the default value.
        sh = self._shared_tile_bytes() if tile_use_dynamic else 0
        if self._kernel_stream is not None:
            self._emit(f'{kname}<<<{grid_var}, gelb_block, {sh},'
                       f' {self._kernel_stream}>>>({call_str});')
        elif tile_use_dynamic:
            self._emit(f'{kname}<<<{grid_var}, gelb_block,'
                       f' {sh}>>>({call_str});')
        else:
            self._emit(f'{kname}<<<{grid_var}, gelb_block>>>'
                       f'({call_str});')
        self._emit('CUDA_CHECK(cudaGetLastError());')

    def _kernel_args_for_context(self, context: str):
        """Compute kernel signature args + call-site expressions
        per ``_emit_block_body`` context.  Returns (sig_args, call_exprs).

        Buffer indices ``g_<ln>_old`` / ``g_<ln>_new`` are
        ``__device__`` globals (see ``_emit_lattice_declarations``)
        -- kernels reference them by name without any signature
        parameter, so the body code emitted by the parent works
        unchanged inside ``__global__`` scope.
        """
        sig_args, call_exprs = [], []
        if context in ('initializer', 'initializer_2nd_buffer'):
            # No params: body code references the device-side ping-
            # pong indices directly.
            pass
        elif context in ('dynamic', 'gauge'):
            sig_args.append('int gelb_timestep')
            call_exprs.append('gelb_timestep')
        else:
            raise NotImplementedError(
                f"Unknown _emit_block_body context: {context!r}"
            )
        return sig_args, call_exprs
