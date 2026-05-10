"""main()-side launch emission for gpu_cuda_cpp.

Launch configuration (dimension-aware block shapes), the per-phase
kernel launches (initialiser / halo / dynamic / swap / gauge), the
cudaGraph capture-and-replay time loop, and the gauge D2H transfer.
"""

from __future__ import annotations

from gelb.gelb_ast.ASTNodes import (
    VariableDeclarationStmt_N,
)

from gelb.midware.ast_eval import (
    is_periodic,
)


class CudaLaunchEmitMixin:
    """Mixin: see module docstring.  Assembled into
    ``CudaCppCodeGenerator`` (stage3_backend_gpu_cuda_cpp);
    must precede ``HighwayCodeGenerator`` in the MRO so the
    overrides here shadow the parent's CPU emission.
    """

    def _launch_total_threads(self) -> int:
        """Total threads spawned by one launch of the main per-cell
        grid (>= NX*NY*NZ).  Sized to match
        ``_emit_launch_config``'s grid * block product so the
        ``gelb_rng_states`` array is large enough that every
        possible tid (including ceil-div overshoot) has a valid
        slot.

        Delegates to ``_block_dims_tuple`` for the per-axis block
        sizes -- the two functions MUST agree on shape, otherwise
        the cuRAND state array undersizes at the ceil-div boundary
        and the random()-using examples crash with an OOB read.
        """
        sizes = self._grid_sizes()
        bdims = self._block_dims_tuple()
        # ceil-div product over (axis size, block size) pairs;
        # bdims has length d, axes beyond d are absent.
        total = 1
        for axis_size, b in zip(sizes, bdims):
            total *= ((axis_size + b - 1) // b) * b
        return total

    def _emit_curand_init_launch(self) -> None:
        """Emit ``gelb_rng_init<<<...>>>(seed)`` in main() once at
        startup.  No-op when the program doesn't use ``random()``.
        """
        if not self._uses_random:
            return
        if self.random_seed is not None:
            seed_expr = f'{int(self.random_seed)}ULL'
        else:
            # Clock-derived default seed.  Doesn't try to be
            # cryptographically secure -- just reproducible across
            # the same wall-clock instant and varied across runs.
            seed_expr = ('static_cast<unsigned long long>('
                         'std::chrono::steady_clock::now()'
                         '.time_since_epoch().count())')
        self._emit('// Seed the per-thread cuRAND state once at'
                   ' startup.')
        self._emit('gelb_rng_init<<<gelb_grid, gelb_block>>>('
                   f'{seed_expr});')
        self._emit('CUDA_CHECK(cudaGetLastError());')
        self._emit('CUDA_CHECK(cudaDeviceSynchronize());')
        self._emit('')

    def _block_dims_tuple(self) -> tuple[int, ...]:
        """Per-axis block dimensions used by all kernel launches.

        Single source of truth shared by ``_emit_launch_config``
        and ``_block_dims_for_dim`` (the tile-sizing helper).

        Current auto-default: pick the 1D-along-x layout (32, 1[, 1])
        at production grid sizes where benchmark data shows it beating
        the square-block default, and fall back to the dim-aware
        square-block default in regimes where 1D-along-x is mixed or
        regressive.  Threshold rationale:

        * 2D -- 1D-along-x ONLY when every axis is periodic.  TGV-2D
          BGK / MRT (all-periodic, single-NC) win clearly with the
          flip (+2-6 % on production N, up to +30 % at small N).
          Programs with non-periodic axes (walls -> multi-NC +
          boundary kernels) -- LDC-2D, RB-2D, channel
          obstacle, etc. -- show mixed-to-mildly-regressive results
          on the controlled 2026-05-08 sweep (LDC-2D N=512: -4.8 %).
          The all-periodic gate is a clean per-program signature.

        * 3D -- 1D-along-x at NX >= 64; 8x8x4 stays below.  At NX=48
          the 1D-along-x layout regresses ~14 % (794 -> 680 MLUPS)
          because there aren't enough x-cells per block to cover
          the per-warp coalescing window.
        * 1D -- kept at (256,); no production data motivates a flip.

        When ``--cuda-block-size N`` IS passed explicitly, honor
        the user override unconditionally (1D-along-x layout, same
        emit shape as the auto path).  This is the escape hatch
        for hardware where the auto thresholds aren't right, and
        for power users who want to opt-in on a non-periodic 2D
        program.
        """
        N = self._user_block_size
        if N is not None:
            if self._d == 1:
                return (N,)
            if self._d == 2:
                return (N, 1)
            return (N, 1, 1)
        if self._d == 1:
            return (256,)
        if self._d == 2:
            # 2D: flip only when every axis is periodic.
            all_periodic = all(
                is_periodic(self._lattice_info, i)
                for i in range(self._d))
            return (32, 1) if all_periodic else (16, 16)
        # 3D: production-scale auto-flip at NX >= 64.
        sizes = self._grid_sizes()
        return (32, 1, 1) if sizes[0] >= 64 else (8, 8, 4)

    def _emit_launch_config(self) -> None:
        """Emit ``dim3 gelb_block`` + ``dim3 gelb_grid`` in main(),
        sized for the program's dimensionality.

        See ``_block_dims_tuple`` for the dimension-aware launch policy.

        When ``--cuda-coarsening N`` is on, the outer-most spatial
        axis's grid count is divided by N (each thread handles N
        consecutive cells along that axis).  Outer axis = last spatial
        axis (x for 1D, y for 2D, z for 3D) -- matches PMPP Sec. 8.4's
        typical recommendation.  Two grid configs are emitted in
        main(): ``gelb_grid`` (default per-cell launches for init /
        gauge) and ``gelb_grid_dyn`` (coarsened launch for the dynamic
        kernel).  Halo + non-dyn kernels always use ``gelb_grid``
        (coarsening doesn't apply).
        """
        sizes = self._grid_sizes()
        bdims = self._block_dims_tuple()
        k = self._cuda_coarsening
        block_args = ', '.join(str(b) for b in bdims)
        block_summary = 'x'.join(str(b) for b in bdims)
        threads = 1
        for b in bdims:
            threads *= b
        if self._d == 1:
            self._emit(f'// CUDA launch config -- 1D ({block_summary} block,'
                       f' {threads} threads)')
            self._emit(f'dim3 gelb_block({block_args});')
            self._emit(f'dim3 gelb_grid(({sizes[0]} + {bdims[0] - 1}) / {bdims[0]});')
        elif self._d == 2:
            self._emit(f'// CUDA launch config -- 2D ({block_summary} block,'
                       f' {threads} threads)')
            self._emit(f'dim3 gelb_block({block_args});')
            self._emit(f'dim3 gelb_grid(({sizes[0]} + {bdims[0] - 1}) / {bdims[0]},'
                       f' ({sizes[1]} + {bdims[1] - 1}) / {bdims[1]});')
        else:  # d == 3
            self._emit(f'// CUDA launch config -- 3D ({block_summary} block,'
                       f' {threads} threads)')
            self._emit(f'dim3 gelb_block({block_args});')
            self._emit(f'dim3 gelb_grid(({sizes[0]} + {bdims[0] - 1}) / {bdims[0]},'
                       f' ({sizes[1]} + {bdims[1] - 1}) / {bdims[1]},'
                       f' ({sizes[2]} + {bdims[2] - 1}) / {bdims[2]});')
        if k > 1:
            self._emit(f'// Coarsened dyn-kernel launch grid'
                       f' (--cuda-coarsening={k}; outer axis divided)')
            if self._d == 1:
                # Outer axis = x; only axis.
                bx = bdims[0]
                self._emit(f'dim3 gelb_grid_dyn('
                           f'({sizes[0]} + {bx} * {k} - 1) / ({bx} * {k}));')
            elif self._d == 2:
                # Outer axis = y; coarsen y.
                bx, by = bdims
                self._emit(f'dim3 gelb_grid_dyn(({sizes[0]} + {bx - 1}) / {bx},'
                           f' ({sizes[1]} + {by} * {k} - 1) / ({by} * {k}));')
            else:  # 3D, outer axis = z
                bx, by, bz = bdims
                self._emit(f'dim3 gelb_grid_dyn(({sizes[0]} + {bx - 1}) / {bx},'
                           f' ({sizes[1]} + {by - 1}) / {by},'
                           f' ({sizes[2]} + {bz} * {k} - 1) / ({bz} * {k}));')
        self._emit('// Halo-update launch config -- 1D')
        self._emit('dim3 gelb_halo_block(256);')

    def _cuda_graphs_skip_reason(self) -> str:
        """Skip when ``random()`` is used (the cuRAND seed plumbing is
        fine -- it runs once before the loop -- but graph replay needs
        kernel-argument updates for a fully general random/timestep path),
        or when the program has no dynamic NC at all (degenerate; nothing
        per-iteration to capture).

        With the device-side ping-pong swap (per-lattice 1-thread
        ``gelb_swap_<ln>`` kernel) the captured region is the
        same shape every iteration even with multi-lattice, multi-NC,
        masked NCs, or non-periodic axes.

        Returns the empty string when the program is in scope.
        """
        if self._uses_random:
            return (
                'program uses random(); --cuda-graphs currently gates'
                ' this conservatively because the captured kernel arg'
                ' list bakes in gelb_timestep; for random()-using'
                ' programs we keep the no-graphs path until codegen wires'
                ' cudaGraphExecKernelNodeSetParams)')
        any_dyn = any(info.dynamic is not None
                      for info in self._geom.nc_info.values())
        if not any_dyn:
            return ('program has no dynamic NC -- nothing per-'
                    'iteration to capture')
        return ''

    def _cuda_graphs_in_scope(self) -> bool:
        return self._cuda_graphs_skip_reason() == ''

    def _emit_initialiser_loops(self) -> None:
        """Replace parent's nested ``for`` loops with kernel launches."""
        self._emit('// ========== Initialiser ==========')
        for nc_name, info in self._geom.nc_info.items():
            if info.initializer is None:
                continue
            iblock = self._find_block(self.ast.initializers,
                                       info.initializer)
            if iblock is None:
                continue
            for rect_info, _ in self._iter_dispatch_rects(info):
                self._emit_kernel_for_block(
                    iblock, 'init', nc_name, rect_info,
                    context='initializer')

        # 2nd-buffer init for static-only NCs.  Programs with both init
        # and dyn skip this loop via the `info.dynamic is not None`
        # filter.  Kept symmetric with parent for static-only support.
        for nc_name, info in self._geom.nc_info.items():
            if info.initializer is None or info.dynamic is not None:
                continue
            iblock = self._find_block(self.ast.initializers,
                                       info.initializer)
            if iblock is None:
                continue
            for rect_info, _ in self._iter_dispatch_rects(info):
                self._emit_kernel_for_block(
                    iblock, 'init2nd', nc_name, rect_info,
                    context='initializer_2nd_buffer')
        self._emit('')

    def _emit_masked_lattice_zero_init(self) -> None:
        """Override of the parent's host-side masked zero-init: on
        the GPU the storage lives behind a ``__device__`` pointer,
        so the zeroing runs as a one-time kernel launch (definition
        emitted at file scope by ``_emit_masked_zero_init_kernel``).
        """
        if not self._any_masked_nc():
            return
        self._emit('// Masked-cell DF zero-init (language guarantee:'
                   ' masked cells hold zero DFs)')
        self._emit('gelb_masked_zero_init<<<gelb_grid,'
                   ' gelb_block>>>();')
        self._emit('')

    def _emit_gauge_at_t0(self) -> None:
        gauge = self._gauge_output_layout()
        if not self._emit_gauge_at_t0_preamble(gauge):
            return

        self._emit_gauge_halo_launches()
        # Initialize outputs absent from some classes, including masked
        # cells, before filling the fields each class produces.
        # The per-NC gauge kernels overwrite their own cells via the
        # bbox guard.
        if gauge.partial:
            self._emit('gelb_gauge_nan_init<<<gelb_grid, gelb_block>>>();')
            self._emit('CUDA_CHECK(cudaGetLastError());')
        for nc_name, info, rect_info, _ in self._iter_gauge_dispatch_rects():
            gblock = self._find_block(self.ast.gauges, info.gauge)
            gauge_outputs = [decl.name.name for decl in gblock.outputs]
            self._emit_kernel_for_block(
                gblock, 'gauge_t0', nc_name, rect_info,
                context='gauge', gauge_outputs=gauge_outputs)

        self._emit_gauge_d2h_transfer(gauge)
        self._emit_gauge_netcdf_write(gauge)

    def _emit_inc_t_launch(self) -> None:
        """Emit ``gelb_inc_t<<<1, 1, 0, stream>>>();`` if the program
        reads ``t``.  Goes between halo updates and dyn launches in
        both the captured-graph and no-graph paths so the dyn
        kernels see ``gelb_timestep_d == k`` at iteration k.
        """
        if not self._uses_t:
            return
        stream_arg = (f', 0, {self._kernel_stream}'
                      if self._kernel_stream is not None else '')
        self._emit(f'gelb_inc_t<<<1, 1{stream_arg}>>>();')
        self._emit('CUDA_CHECK(cudaGetLastError());')

    def _emit_halo_launches(self, only=None, default_stream=False) -> None:
        """Emit halo-kernel launches for every (lattice, periodic
        axis) pair, or for the lattices in ``only``.  Stream comes from
        ``self._kernel_stream`` unless ``default_stream`` is set.
        """
        sizes = self._grid_sizes()
        stream_arg = (f', 0, {self._kernel_stream}'
                      if self._kernel_stream is not None
                      and not default_stream else '')
        for lname, info in self._lattice_info.items():
            if only is not None and lname not in only:
                continue
            d = info['d']
            q = info['q']
            per = [is_periodic(self._lattice_info, i) for i in range(d)]
            for axis_idx in range(d):
                if not per[axis_idx]:
                    continue
                if d == 1:
                    n_threads = q
                elif d == 2 and axis_idx == 0:
                    n_threads = sizes[1]
                elif d == 2 and axis_idx == 1:
                    n_threads = sizes[0] + 2
                elif d == 3 and axis_idx == 0:
                    n_threads = sizes[1] * sizes[2]
                elif d == 3 and axis_idx == 1:
                    n_threads = (sizes[0] + 2) * sizes[2]
                elif d == 3 and axis_idx == 2:
                    n_threads = (sizes[0] + 2) * (sizes[1] + 2)
                else:
                    raise NotImplementedError(
                        f"halo launch: unhandled "
                        f"(d={d}, axis_idx={axis_idx})"
                    )
                self._emit(
                    f'gelb_halo_{lname}_axis_{axis_idx}<<<'
                    f'(({n_threads} + 255) / 256),'
                    f' gelb_halo_block{stream_arg}>>>();')
                self._emit('CUDA_CHECK(cudaGetLastError());')

    def _emit_gauge_halo_launches(self) -> None:
        """Refresh the ghost cells a gauge reads, on the default stream
        like the gauges.  The time loop updates the halo before the
        dynamics only; gauges run after the swap and at t=0, so a gauge
        reading a neighbour across a periodic axis needs its own
        refresh.  Without stencil information every periodic lattice is
        refreshed."""
        wanted = (self._stencils.gauge_halo_lattices()
                  if self._stencils is not None else set(self._lattice_info))
        if wanted:
            self._emit_halo_launches(only=wanted, default_stream=True)

    def _emit_dyn_launches(self) -> None:
        """Emit one dyn-kernel launch per (NC, dispatch-rect)
        with optional MlupsTimer brackets.

        Brackets are emitted ONLY when ``--cuda-graphs`` is
        inactive; under graph capture, recording cuda events
        inside the captured region would create graph-event
        nodes (which then synchronise on every replay,
        defeating the point), and the timing is anyway
        dominated by ``cudaGraphLaunch`` overhead.  The
        per-iteration ``cudaGraphLaunch`` site adds its own
        stream-aware ``dyn_start``/``dyn_stop`` overload
        instead -- see ``_emit_time_loop``.
        """
        emit_brackets = self._kernel_stream is None
        for nc_name, info in self._geom.nc_info.items():
            if info.dynamic is None:
                continue
            dblock = self._find_block(self.ast.dynamics, info.dynamic)
            if dblock is None:
                continue
            for rect_info, _ in self._iter_dispatch_rects(info):
                if emit_brackets:
                    self._emit('gelb_timer.dyn_start();')
                self._emit_kernel_for_block(
                    dblock, 'dyn', nc_name, rect_info,
                    context='dynamic')
                if emit_brackets:
                    self._emit('gelb_timer.dyn_stop();')

    def _emit_swap_launches(self) -> None:
        """Emit one 1-thread ``gelb_swap_<lname>`` launch per
        lattice -- the device-side ping-pong rotation.
        """
        stream_arg = (f', 0, {self._kernel_stream}'
                      if self._kernel_stream is not None else '')
        for ln in self._lattice_info:
            self._emit(f'gelb_swap_{ln}<<<1, 1{stream_arg}>>>();')
            self._emit('CUDA_CHECK(cudaGetLastError());')

    def _emit_gauge_dispatch(self) -> None:
        """Emit the per-iteration gauge dispatch (always on the
        default stream -- host-side ``write_every`` guard plus
        ``cudaMemcpyFromSymbol`` and ``nc_put_*`` are not
        capture-friendly, so this stays outside any cudaGraph_t).
        """
        gauge = self._gauge_output_layout()
        if gauge is None:
            return
        need_guard = self.write_every > 1
        if need_guard:
            self._emit(f'if (gelb_timestep % {self.write_every} == 0 '
                       f'|| gelb_timestep == {self.num_timesteps}) {{')
            self._indent += 1
        self._emit('gelb_write_count += 1;')
        self._emit_gauge_halo_launches()
        # Initialize fields absent from some classes before the per-class
        # gauge kernels overwrite their own fields and cells.
        if gauge.partial:
            self._emit('gelb_gauge_nan_init<<<gelb_grid, gelb_block>>>();')
            self._emit('CUDA_CHECK(cudaGetLastError());')
        for nc_name, info in self._geom.nc_info.items():
            if info.gauge is None:
                continue
            gblock = self._find_block(self.ast.gauges, info.gauge)
            gauge_outputs = [decl.name.name for decl in gblock.outputs]
            for rect_info, _ in self._iter_dispatch_rects(info):
                self._emit_kernel_for_block(
                    gblock, 'gauge', nc_name, rect_info,
                    context='gauge', gauge_outputs=gauge_outputs)
        self._emit_gauge_d2h_transfer(gauge)
        self._emit_gauge_netcdf_write(gauge)
        if need_guard:
            self._indent -= 1
            self._emit('}')

    def _emit_time_loop(self) -> None:
        # Halo / dyn / swap launch ranges per (d, axis_idx) -- see
        # _emit_halo_update_kernel for the body shape:
        #   d=1, axis 0: q DFs (no other axis)
        #   d=2, axis 0: y in [1, NY]                    -> NY
        #   d=2, axis 1: x in [0, NX+1]                  -> NX+2
        #   d=3, axis 0: y in [1, NY], z in [1, NZ]      -> NY*NZ
        #   d=3, axis 1: x in [0, NX+1], z in [1, NZ]    -> (NX+2)*NZ
        #   d=3, axis 2: x in [0, NX+1], y in [0, NY+1]  -> (NX+2)*(NY+2)
        #
        # Dyn-kernel timer brackets normally go INSIDE the loop, around
        # each dyn-kernel call Without this match, ``Compute
        # MLUPS`` would report entire-loop throughput (halo + dyn +
        # gauge + nc_put_var) on the cpp side but dyn-only throughput
        # on the fortran side, making column-by-column comparisons
        # apples-to-oranges (the original 2026-05-07 source of the
        # phantom "12 % 3D gap").  ``Real MLUPS`` is wall-clock-based
        # and stays scope-independent.
        #
        # Under ``--cuda-graphs``, the halo + dyn + swap sequence is
        # captured once before the time loop into a ``cudaGraph_t`` on a
        # dedicated stream, and each iteration issues a single
        # ``cudaGraphLaunch`` instead of N kernel launches.  Dyn-event
        # records bracket the graph launch (with the stream-aware
        # ``dyn_start(stream)`` / ``dyn_stop(stream)`` overloads in
        # ``gpu_cuda_cpp_runtime.cuh``).  Gauge dispatch stays outside
        # the captured region -- host-side ``write_every`` guard +
        # ``nc_put_*`` aren't capture-friendly.
        self._emit('// ========== Time loop ==========')

        if self._cuda_graphs_active:
            self._emit('// --cuda-graphs: capture halo + dyn + swap'
                       ' once, replay per iteration.')
            self._emit('cudaStream_t gelb_stream;')
            self._emit('CUDA_CHECK(cudaStreamCreate(&gelb_stream));')
            self._emit('cudaGraph_t     gelb_graph = nullptr;')
            self._emit('cudaGraphExec_t gelb_exec  = nullptr;')
            self._emit('CUDA_CHECK(cudaStreamBeginCapture(gelb_stream,'
                       ' cudaStreamCaptureModeGlobal));')
            self._kernel_stream = 'gelb_stream'
            self._emit_halo_launches()
            self._emit_inc_t_launch()
            self._emit_dyn_launches()
            self._emit_swap_launches()
            self._kernel_stream = None
            self._emit('CUDA_CHECK(cudaStreamEndCapture(gelb_stream,'
                       ' &gelb_graph));')
            self._emit('CUDA_CHECK(cudaGraphInstantiate(&gelb_exec,'
                       ' gelb_graph, nullptr, nullptr, 0));')

        self._emit('gelb_timer.wall_start();')
        self._emit(f'for (gelb_timestep = 1; gelb_timestep <= '
                   f'{self.num_timesteps}; ++gelb_timestep) {{')
        self._indent += 1

        if self._cuda_graphs_active:
            self._emit('gelb_timer.dyn_start(gelb_stream);')
            self._emit('CUDA_CHECK(cudaGraphLaunch(gelb_exec,'
                       ' gelb_stream));')
            # dyn_stop syncs on gelb_stream -- afterwards, default-
            # stream gauge work is guaranteed to see the latest
            # storage state without an extra cudaStreamSynchronize.
            self._emit('gelb_timer.dyn_stop(gelb_stream);')
        else:
            self._emit_halo_launches()
            self._emit_inc_t_launch()
            self._emit_dyn_launches()
            self._emit_swap_launches()

        self._emit_gauge_dispatch()

        self._indent -= 1
        self._emit('}')
        self._emit('gelb_timer.wall_stop();')

        if self._cuda_graphs_active:
            self._emit('CUDA_CHECK(cudaGraphExecDestroy(gelb_exec));')
            self._emit('CUDA_CHECK(cudaGraphDestroy(gelb_graph));')
            self._emit('CUDA_CHECK(cudaStreamDestroy(gelb_stream));')

    def _emit_gauge_d2h_transfer(self, gauge) -> None:
        """Copy device gauge buffers back to host before NetCDF write.

        Uses ``cudaMemcpyFromSymbol`` (synchronous wrt the issuing
        stream) to fetch the contents of each ``__device__``
        ``gelb_buf_<vname>_d`` into the host ``gelb_buf_<vname>``.
        Synchronous => no extra ``cudaDeviceSynchronize`` needed
        before the subsequent ``nc_put_vara_*`` calls.
        """
        for decl in gauge.outputs:
            if isinstance(decl, VariableDeclarationStmt_N):
                vname = decl.name.name
                self._emit(f'CUDA_CHECK(cudaMemcpyFromSymbol('
                           f'gelb_buf_{vname}, gelb_buf_{vname}_d, '
                           f'sizeof(gelb_buf_{vname})));')
