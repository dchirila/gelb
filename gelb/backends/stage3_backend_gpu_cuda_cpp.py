"""GeLB ``gpu_cuda_cpp`` backend - CUDA C++ codegen.

Generates standalone CUDA C++ from a frontend + midware-normalized
GeLB AST.  The backend subclasses :class:`HighwayCodeGenerator` to
reuse expression emission, statement emission, lattice metadata,
NetCDF wiring, and cross-backend helper logic, while overriding the
CPU spatial loops with one-thread-per-cell CUDA kernel launches.

User-triggerable unsupported cases should be rejected with clear
diagnostics before generated CUDA reaches ``nvcc``.
"""

from gelb.backends.cuda.device import CudaDeviceStateMixin
from gelb.backends.cuda.kernels import CudaKernelEmitMixin
from gelb.backends.cuda.launch import CudaLaunchEmitMixin
from gelb.backends.cuda.tiling import CudaTilingEmitMixin
from gelb.backends.stage3_backend_cpu_highway import (
    HighwayCodeGenerator,
    _TYPE_MAP,
)
from gelb.gelb_ast.ASTNodes import VariableDeclarationStmt_N
from gelb.midware.ast_eval import get_max_dim, is_periodic


# Default threads per CUDA block.  256 = 8 warps; modern NVIDIA
# (sm_75+, including Ada sm_89) typically peaks between 128-256
# threads/block for memory-bound kernels.  CUDA Fortran defaults
# to 32 (one warp); we prefer 256 since it gives better occupancy
# for streaming workloads on Ada.  Override via
# ``--cuda-block-size``.
_CUDA_BLOCK_SIZE = 256


def generate_cuda_cpp(ast, num_timesteps=1, output_filename='output.nc',
                      write_every=1, random_seed=None,
                      source_file='', cuda_block_size=None,
                      cuda_coarsening=1, cuda_ldg=False,
                      cuda_stwt=False, cuda_tiled=False,
                      cuda_graphs=False, resolved_geometry=None,
                      backend_context=None, poison_uninit=False,
                      strict_fp=False):
    """Generate CUDA C++ source code from a GeLB AST.

    Args:
        ast: ``Program_N`` node (post frontend + midware).
        num_timesteps: Number of simulation time steps.
        output_filename: NetCDF output filename.
        write_every: Write gauge output every N timesteps.
        random_seed: Optional seed for deterministic PRNG initialization
            when the program uses ``random()``.
        source_file: Original ``.gelb`` source filename (header comment).
        cuda_block_size: CUDA threads per block (default:
            ``_CUDA_BLOCK_SIZE``).
        backend_context: Optional shared backend analysis context produced by
            the compiler pipeline.
        resolved_geometry: Optional ``ResolvedGeometry`` computed by the
            compiler driver.  When omitted, the inherited Highway layer
            resolves geometry itself. Retained for direct-call compatibility.

    Returns:
        Complete CUDA C++ program as a string (``.cu`` source).

    Raises:
        :class:`NotImplementedError` for backend-specific feature
        combinations that are not yet supported.
    """
    gen = CudaCppCodeGenerator(
        ast,
        num_timesteps=num_timesteps,
        output_filename=output_filename,
        write_every=write_every,
        random_seed=random_seed,
        source_file=source_file,
        cuda_block_size=cuda_block_size,
        cuda_coarsening=cuda_coarsening,
        cuda_ldg=cuda_ldg,
        cuda_stwt=cuda_stwt,
        cuda_tiled=cuda_tiled,
        cuda_graphs=cuda_graphs,
        resolved_geometry=resolved_geometry,
        backend_context=backend_context,
        poison_uninit=poison_uninit,
        strict_fp=strict_fp,
    )
    return gen.generate()


class CudaCppCodeGenerator(
        CudaKernelEmitMixin,
        CudaLaunchEmitMixin,
        CudaTilingEmitMixin,
        CudaDeviceStateMixin,
        HighwayCodeGenerator,
):
    """Generates CUDA C++ from a GeLB AST."""

    backend_name = 'gpu_cuda_cpp'
    runtime_header = 'gpu_cuda_cpp_runtime.cuh'
    wrap_main_with_highway = False

    def __init__(self, ast, num_timesteps=1, output_filename='output.nc',
                 write_every=1, random_seed=None,
                 source_file='', cuda_block_size=None,
                 cuda_coarsening=1, cuda_ldg=False, cuda_stwt=False,
                 cuda_tiled=False, cuda_graphs=False,
                 resolved_geometry=None, backend_context=None,
                 poison_uninit=False, strict_fp=False):
        # Parent constructor: ``use_openmp=False`` (no OpenMP on
        # the GPU) and ``storage_layout='soa'`` (no AoS, no CBT --
        # CBT would emit Highway tile-shuffle ops that don't
        # exist under scalar emit).
        super().__init__(
            ast,
            num_timesteps=num_timesteps,
            output_filename=output_filename,
            write_every=write_every,
            use_openmp=False,
            random_seed=random_seed,
            source_file=source_file,
            storage_layout='soa',
            resolved_geometry=resolved_geometry,
            backend_context=backend_context,
            poison_uninit=poison_uninit,
            # Inherited ``_emit_includes`` then defines GELB_STRICT_FP
            # in the .cu as well; the CUDA helpers fuse nothing of their
            # own, so on CUDA strictness is nvcc's -fmad=false.
            strict_fp=strict_fp,
        )

        # Sanity-check the parent's default mode.  The CUDA backend
        # relies on scalar expression emission everywhere; if a future
        # parent change flips the default this assert catches it before
        # Highway intrinsics are emitted into CUDA C++.
        assert self._simd_mode == 'scalar', (
            f"gpu_cuda_cpp expects parent's _simd_mode='scalar', "
            f"got {self._simd_mode!r}"
        )

        # Belt-and-braces: explicitly hard-disable the parent's
        # auto-CBT chooser per-lattice.  ``storage_layout='soa'``
        # already forces ``_use_aos[ln]=False`` for every lattice;
        # the parallel CBT map needs the same treatment so the
        # ``_storage_subscript`` builder emits the plain
        # ``g_<lname>_storage[buf][df][...y][x]`` SoA shape.
        self._use_cbt = {ln: False for ln in self._lattice_info}

        # ---- Inherited-contract invariants -------------------------
        # The CUDA backend reuses the parent's emission machinery in
        # exactly one configuration: scalar expressions (asserted
        # above) over SoA storage.  Parent code branches on
        # ``self._use_aos`` / ``self._use_cbt`` in ~50 transitive
        # callers of ``_storage_subscript``; pin both maps here so a
        # future parent-side layout change cannot silently route CUDA
        # emission through an AoS/CBT (Highway-intrinsic) path.
        assert not any(self._use_aos.values()), (
            "gpu_cuda_cpp inherited contract violated: parent enabled "
            "AoS storage for "
            f"{[ln for ln, v in self._use_aos.items() if v]} despite "
            "storage_layout='soa'")
        assert not any(self._use_cbt.values()), (
            "gpu_cuda_cpp inherited contract violated: a CBT lattice "
            "survived the hard-disable above")
        # ``_simd_int_locals`` must stay empty in scalar mode -- a
        # non-empty map means a parent SIMD-retyping path ran, which
        # would emit Highway ``V`` types into CUDA C++.  Checked here
        # (constructor) and cheap enough to re-assert in generate().
        assert not self._simd_int_locals, (
            "gpu_cuda_cpp inherited contract violated: parent recorded "
            "SIMD-retyped locals in scalar mode")

        # CUDA-specific: threads-per-block for kernel launches.
        # ``self._user_block_size`` is None when the caller did not
        # pass ``--cuda-block-size`` (then the dimension-aware
        # defaults apply: 1D=256, 2D=16x16, 3D=8x8x4 -- total 256
        # threads/block).  When set explicitly, the launch config
        # switches to a 1D-along-x layout: (N,) / (N, 1) / (N, 1, 1)
        # -- single-warp blocks aligned to consecutive sx values give
        # 1 cache line per stencil read instead of 4 per warp on
        # 8x8x4.
        self._user_block_size: int | None = (
            int(cuda_block_size) if cuda_block_size is not None else None
        )
        # Effective threads/block (used by halo-launch and other
        # 1D-launch paths that don't depend on per-axis dims).
        self._block_size = (
            self._user_block_size if self._user_block_size is not None
            else _CUDA_BLOCK_SIZE
        )

        # CUDA perf-tuning knobs (CLI-exposed; conservative defaults
        # until broader hardware heuristics are validated).
        self._cuda_coarsening: int = max(1, int(cuda_coarsening))
        self._cuda_ldg: bool = bool(cuda_ldg)
        self._cuda_stwt: bool = bool(cuda_stwt)
        # PMPP Sec. 8.3 shared-memory tiling for the dyn kernel.  The
        # constructor only records the flag; codegen kicks in inside
        # ``_emit_kernel_for_block`` (tile load + body substitution)
        # and ``_emit_main_header`` (cudaFuncSetAttribute opt-in for
        # 3D when shared per-block exceeds 48 KB).  Scope checks keep
        # unsupported program shapes on the normal non-tiled path.
        self._cuda_tiled: bool = bool(cuda_tiled)

        # Capture the per-iteration kernel sequence into a
        # ``cudaGraph_t`` once and replay it via ``cudaGraphLaunch``.
        # Constructor records the user request; the actual decision
        # (whether the program is in scope) is computed by
        # ``_cuda_graphs_active`` after the AST and geometry scans.
        self._cuda_graphs_requested: bool = bool(cuda_graphs)

        # Stream variable used by every in-loop kernel launch.
        # ``None`` means launches use the default stream (current
        # behaviour); set to ``'gelb_stream'`` during the capture
        # region of ``_emit_time_loop`` so kernels record into the
        # cudaGraph_t.  ``_emit_kernel_for_block`` and the halo /
        # swap launch sites consult this attribute.
        self._kernel_stream: str | None = None

        # File-scope content (`__device__` globals, `__global__`
        # kernels, deferred constexpr arrays) accumulated by the
        # codegen and spliced between ``#include`` and ``int main()``
        # by the ``generate()`` override.  Lines stored here have
        # NO indent prefix applied by ``_emit`` (since they're
        # always at file scope).
        self._device_decls: list[str] = []

        # Counter giving unique kernel names per emit site.  Bumped
        # by ``_emit_kernel_for_block`` and ``_emit_halo_update_kernel``.
        self._kernel_counter: int = 0

        # Emit-target flag.  ``'main'`` => ``self._emit`` appends to
        # ``self._lines`` (parent's behaviour).  ``'device'`` =>
        # appends to ``self._device_decls`` with indent zero (file
        # scope).  Switched by ``generate()`` and ``_emit_kernel_for_block``
        # to redirect the appropriate emit slices to the right
        # buffer without overhauling the parent's hundreds of
        # ``self._emit(...)`` call sites.
        self._emit_target: str = 'main'

        # Scan AST once for ``random()`` usage.  Drives the cuRAND
        # emit (state array + init kernel + gelb_random device fn)
        # and the seed-init launch in main().
        self._uses_random = self._ast_uses_intrinsic('random')

        # Programs that read the implicit ``t`` symbol need it as
        # a ``__device__`` int instead of a kernel argument: under
        # ``--cuda-graphs`` (the default since 2026-05-08) the
        # captured kernel-arg list freezes the value of
        # ``gelb_timestep`` at capture time, so every replay would
        # see ``t = 0``.  Mirroring the device-side ping-pong-index
        # pattern (``g_<lname>_old`` / ``g_<lname>_new`` updated by
        # a ``gelb_swap_<lname>`` kernel inside the graph), we
        # emit ``__device__ int gelb_timestep_d = 0`` plus a
        # ``gelb_inc_t`` 1-thread kernel that increments it; the
        # kernel-body emit for ``t`` then resolves to the device
        # global rather than the kernel parameter.
        self._uses_t = self._ast_uses_implicit_t()

        # Emit a per-cell ``nc_map`` array iff any node-class in the
        # resolved geometry is non-dense (e.g. a masked obstacle inside
        # BULK).  Without nc_map, the per-NC kernel's bbox guard alone
        # would let BULK threads write into obstacle cells, corrupting
        # neighbour reads at obstacle-adjacent BULK cells.  A single
        # kernel per NC plus nc_map dispatch avoids exploding one NC
        # into many tiny GPU launches.
        self._uses_nc_map = any(
            not info.bbox_dense
            for info in self._geom.nc_info.values()
            if info.bbox is not None)

        # Parent backend scope checks have already run from
        # ``super().__init__()``; this layer adds CUDA-specific limits.
        self._validate_cuda_cpp_scope()

        # CUDA Graphs in-scope check.  Resolved after the AST scans and
        # geometry inspection above so the scope decision can consult
        # them.  When the user passed
        # ``--cuda-graphs`` but the program is out of scope, fall
        # back to the no-graphs emit path with a one-line stderr
        # note (consistent with how ``--cuda-tiled`` handles its
        # own scope guard) -- the rest of the program still
        # compiles and runs normally.
        self._cuda_graphs_active: bool = (
            self._cuda_graphs_requested
            and self._cuda_graphs_in_scope())
        if self._cuda_graphs_requested and not self._cuda_graphs_active:
            import sys
            sys.stderr.write(
                f'gpu_cuda_cpp: --cuda-graphs falling back to'
                f' no-graphs emit ({self._cuda_graphs_skip_reason()}).\n')

    # ------------------------------------------------------------------
    # Scope enforcement
    # ------------------------------------------------------------------

    def _validate_cuda_cpp_scope(self) -> None:
        """Reject any feature outside the current scope with a precise
        ``NotImplementedError``.

        Current scope: 1D / 2D / 3D, multi-lattice, multi-NC
        (including masked node classes), mixed periodicity, ``random()``,
        and ``real32``.
        """
        d = get_max_dim(self._lattice_info)
        if d not in (1, 2, 3):
            raise NotImplementedError(
                f"gpu_cuda_cpp supports 1-D, 2-D, and 3-D lattices "
                f"(this program is {d}-D)."
            )

        # CUDA support for multi-lattice, multi-NC, masked NCs, and
        # non-periodic boundaries lives in:
        #   - non-periodic halo: _emit_halo_update_kernels gates on
        #     is_periodic per axis
        #   - multi-NC: _emit_nc_map_decl + _emit_nc_id_guard
        #   - masked NCs: _emit_gauge_nan_init_kernel + launch
        #   - multi-lattice: _emit_lattice_declarations already
        #     iterates _lattice_info

        # Programs using ``random()`` pull in the cuRAND device API,
        # plus codegen emits a per-thread state array, init kernel, and
        # ``gelb_random()`` device function.

        # Parent precision-aware emit (HighwayCodeGenerator)
        # already produces ``float`` storage and ``f``-suffixed
        # literals; the runtime header's __host__ __device__
        # reduction helpers are templates and accept either type.

    # ------------------------------------------------------------------
    # AST scanning helpers used by the scope guard
    # ------------------------------------------------------------------

    def _ast_uses_intrinsic(self, name: str) -> bool:
        """Recursively scan the AST for any
        ``IntrinsicFunctionCall_N`` whose ``function_name`` matches
        ``name`` (case-insensitive).

        Uses the AST's ``get_children()`` API plus a visited-set
        (AST nodes carry parent links -> naive __dict__ walk
        infinite-recurses).
        """
        from gelb.gelb_ast.ASTNodes import IntrinsicFunctionCall_N

        target = name.lower()
        seen: set[int] = set()

        def visit(node) -> bool:
            if node is None:
                return False
            nid = id(node)
            if nid in seen:
                return False
            seen.add(nid)
            if isinstance(node, IntrinsicFunctionCall_N):
                fn = getattr(node, 'function_name', None)
                if fn is not None and str(fn).lower() == target:
                    return True
            getter = getattr(node, 'get_children', None)
            if callable(getter):
                try:
                    children = getter() or ()
                except Exception:
                    children = ()
                for child in children:
                    if visit(child):
                        return True
            return False

        return visit(self.ast)

    def _ast_uses_implicit_t(self) -> bool:
        """Recursively scan the AST for any ``Identifier_N`` whose
        ``symbol_tag == "implicit timestep variable"`` -- i.e., a
        block-body reference to the per-step timestep ``t``.

        Same shape as ``_ast_uses_intrinsic`` but for the implicit
        symbol.  Used to gate the ``__device__ int gelb_timestep_d``
        + ``gelb_inc_t`` emit so programs that don't read ``t``
        don't pay for an unused device global / extra kernel.
        """
        from gelb.gelb_ast.ASTNodes import Identifier_N

        seen: set[int] = set()

        def visit(node) -> bool:
            if node is None:
                return False
            nid = id(node)
            if nid in seen:
                return False
            seen.add(nid)
            if isinstance(node, Identifier_N):
                if (getattr(node, 'symbol_tag', None)
                        == "implicit timestep variable"):
                    return True
            getter = getattr(node, 'get_children', None)
            if callable(getter):
                try:
                    children = getter() or ()
                except Exception:
                    children = ()
                for child in children:
                    if visit(child):
                        return True
            return False

        return visit(self.ast)

    def _emit_expression(self, expr, df_var=None) -> str:
        """Override only the implicit-``t`` resolution.

        Parent (HighwayCodeGenerator) emits ``t`` as ``gelb_timestep``
        -- the host loop variable.  Under ``--cuda-graphs``, kernel
        arguments are baked into the captured graph at capture
        time, so ``gelb_timestep`` would be frozen at 0 and every
        replay would compute ``sin(0)`` etc.  Resolve ``t`` to the
        device-resident counter instead (incremented by
        ``gelb_inc_t`` at the head of the captured sequence).
        """
        from gelb.gelb_ast.ASTNodes import Identifier_N
        if (self._uses_t
                and isinstance(expr, Identifier_N)
                and getattr(expr, 'symbol_tag', None)
                    == "implicit timestep variable"):
            return 'static_cast<int64_t>(gelb_timestep_d)'
        return super()._emit_expression(expr, df_var)

    def _ast_uses_real32(self) -> bool:
        """Check if any lattice declares ``df_type=real32``.

        The lattice info dict carries each lattice's df_type as a
        string-or-equivalent; a stringified comparison is robust to
        the precise type of the entry (string token vs AST node).
        """
        for info in self._lattice_info.values():
            df_type = info.get('dtype') if isinstance(info, dict) \
                else getattr(info, 'df_type', None)
            if df_type is not None and 'real32' in str(df_type):
                return True
        return False

    def _block_simd_eligible(self, block, info) -> bool:
        # Hard-disable parent's SIMD emit path everywhere.  Even with
        # ``storage_layout='soa'`` and ``use_openmp=False``, the
        # parent's dispatcher (in ``_emit_initialiser_loops`` /
        # ``_emit_gauge_at_t0`` / ``_emit_time_loop``) consults
        # ``_block_simd_eligible`` and, if True, calls
        # ``_emit_block_simd`` which flips ``_simd_mode`` to
        # ``'vec8d'`` for the body.  That emits Highway intrinsics
        # (``hn::Set``, ``hn::Iota``, ``V`` / ``d``) which nvcc
        # cannot lower.  Returning False forces the parent to take
        # the per-cell scalar-loop path everywhere -- which is
        # exactly what the CUDA grid wants (one thread per cell,
        # scalar arithmetic in the kernel body).  CUDA codegen then
        # converts those scalar loops into kernel launches via
        # the ``_emit_spatial_loop_open`` override.
        return False

    def _emit_aux_variables(self) -> None:
        # Mirror parent's MLUPS-timer + counter-init shape, but skip
        # the ``gelb_seed_prng`` / xoshiro-clock-fallback block; CUDA
        # programs that use ``random()`` are seeded through the cuRAND
        # initialization emitted below.
        self._emit_mlups_timer_setup()
        self._emit_timestep_counters()
        self._emit('')

    # ------------------------------------------------------------------
    # Override -- emit dispatch
    # ------------------------------------------------------------------

    def _emit(self, line: str = '') -> None:
        """Override parent's ``_emit`` to dispatch by ``self._emit_target``.

        Parent appends to ``self._lines`` with ``'  ' * self._indent``
        prefix.  We do the same when target is ``'main'`` (default --
        parent's behaviour, untouched).  When target is ``'device'``,
        we append to ``self._device_decls`` with NO indent prefix
        (file-scope content) -- so the per-method ``self._indent``
        tracking inside captured kernels is honoured by the indent
        applied within the kernel body, not the file-scope
        positioning of the kernel itself.
        """
        # Apply axis substitutions exactly like parent (preserves the
        # singleton-axis literal-folding pass for boundary/elided regions).
        if line and self._axis_substitutions:
            line = self._apply_axis_substitutions(line)
        if self._emit_target == 'device':
            # File-scope target: indent is honoured (so kernel bodies
            # at indent>=1 read as proper nested code).
            if line:
                self._device_decls.append('  ' * self._indent + line)
            else:
                self._device_decls.append('')
            return
        # Default 'main' target: parent's behaviour.
        if line:
            self._lines.append('  ' * self._indent + line)
        else:
            self._lines.append('')

    # ------------------------------------------------------------------
    # Override -- generate() composition
    # ------------------------------------------------------------------

    def generate(self) -> str:
        """Compose the final ``.cu`` source.

        Layout:
            // header comment
            #include "gpu_cuda_cpp_runtime.cuh"
            using namespace gelb;
            --- file-scope (self._device_decls) ---
              constexpr int g__nx = ...;
              static constexpr ... g_PI = ...;
              static constexpr int gelb_dp_pos_*[] = ...;     // deferred constexpr arrays
              __device__ double g_<lname>_storage[2][q][...];
              __device__ <type> gelb_buf_<vname>_d[...];
              __global__ void gelb_halo_<lname>_axis_<i>(int buf) { ... }
              __global__ void gelb_k_<phase>_<nc>_<i>(...) { ... }
            --- main() (self._lines) ---
              int main() { ... }

        The two buffers are joined at the end; nothing in main()
        references device storage by host pointer (everything is
        accessed by name from the file-scope ``__device__`` globals).
        """
        self._emit_header_comment()
        self._emit_includes()
        # Capture header + includes as a separate prefix; clear
        # ``_lines`` so main() emit starts fresh.  Final composition:
        # header_prefix + _device_decls + _lines.
        header_prefix = list(self._lines)
        self._lines = []

        # File-scope emission: grid + global constants, lattice
        # storage, gauge device buffers, halo kernels.  Switching
        # ``_emit_target`` to ``'device'`` redirects parent's emits
        # to ``_device_decls`` for the duration.
        self._emit_target = 'device'
        self._emit_grid_constants()
        self._emit_lattice_declarations()
        self._emit_device_gauge_buffers()
        # Per-cell nc_map for non-dense NC dispatch (no-op when every NC
        # is dense).  Must come before halo / gauge-NaN / dyn kernels
        # since they may reference it.
        self._emit_nc_map_decl()
        self._emit_halo_update_kernels()
        # Per-lattice 1-thread swap kernel -- replaces the host-side
        # ``std::swap`` so the iteration body is fully GPU-side and
        # capture-friendly.  See _emit_swap_kernels.
        self._emit_swap_kernels()
        # Initialize gauge fields absent from some classes (including
        # masked cells).
        self._emit_gauge_nan_init_kernel(self._gauge_output_layout())
        # Zero-init kernel for masked-NC lattice DFs (no-op when no NC
        # is masked).  Definition here; launched once from main() via
        # the _emit_masked_lattice_zero_init override.
        self._emit_masked_zero_init_kernel()
        # cuRAND state + init kernel + gelb_random (no-op when the
        # program doesn't use random()).
        self._emit_curand_decls()
        self._emit_target = 'main'

        self._emit_main_header()
        self._emit_lattice_storage_alloc()
        self._emit_aux_variables()
        self._emit_netcdf_setup()
        self._emit_launch_config()
        self._emit('')
        # Seed cuRAND state once at startup (no-op when the program
        # doesn't use random()).
        self._emit_curand_init_launch()
        self._emit_simulation_body()

        # Splice the deferred ``static constexpr`` arrays (registered
        # by ``_register_constexpr_array`` during dot_prod / matmul
        # body emit) at file scope so kernels can reference them.
        # PREPEND, not append: the kernels (already in
        # ``_device_decls``) reference these arrays by name, so the
        # arrays must come before the first kernel definition.  Parent
        # splices these into main() at ``_main_body_start_idx``; we
        # override that and put them at file scope ahead of all
        # kernels instead.
        if self._deferred_constexpr_decls:
            constexpr_block = (['// Deferred dot_prod / matmul index'
                                ' + coefficient arrays']
                               + list(self._deferred_constexpr_decls)
                               + [''])
            self._device_decls = constexpr_block + self._device_decls

        # ``static constexpr`` ARRAYS at file scope are HOST-only --
        # nvcc rejects array reads from ``__global__`` kernels even
        # with ``--expt-relaxed-constexpr`` because the host symbol
        # has no device-side storage backing.  Patch only those to
        # ``__device__ constexpr`` so the data lives in device
        # memory and kernels can index it.  SCALAR ``static constexpr``
        # decls are left alone because (a) ``--expt-relaxed-constexpr``
        # accepts them at device-side use sites, and (b) some user
        # constants have non-constexpr initializers (e.g.
        # ``static constexpr double g_DRAG_NL = 0.184 /
        # std::sqrt(g_K_PERM);`` -- ``std::sqrt`` isn't constexpr in
        # C++17, so ``__device__ constexpr`` rejects it but
        # ``static constexpr`` accepts it as a best-effort
        # initialization).  The array detector splits on ``=`` and
        # looks for ``[`` in the LHS -- covers both
        # ``g_W[9] = {...}`` and the deferred ``gelb_dp_pos_1[] =
        # {...}`` shapes.
        def _swap_array_constexpr(line: str) -> str:
            stripped = line.lstrip()
            if not stripped.startswith('static constexpr'):
                return line
            lhs = stripped.split('=', 1)[0]
            if '[' not in lhs:
                return line  # scalar -- leave as static constexpr
            return line.replace('static constexpr',
                                '__device__ constexpr', 1)
        self._device_decls = [_swap_array_constexpr(line)
                              for line in self._device_decls]

        # Compose: header prefix (header comment + #include + using),
        # then file-scope decls/kernels, then main().
        return ('\n'.join(header_prefix) + '\n'
                + '\n'.join(self._device_decls) + '\n\n'
                + '\n'.join(self._lines) + '\n')

    # ------------------------------------------------------------------
    # Kernel coalescing for non-dense NCs
    # ------------------------------------------------------------------

    def _iter_dispatch_rects(self, info):
        """Override parent: yield ONE rect per NC (no decomposition).

        Parent decomposes non-dense NCs into many dense
        rectangles, which on the CPU each map to a tight inner
        loop -- fine.  On the GPU each maps to a separate kernel
        launch -- at ~1.4 us launch latency on sm_89, a 168-rect
        program (channel_flow_circle) eats 168*500 ~= 84k
        launches per 500-timestep run = ~115 ms of overhead vs
        ~50 ms of actual compute.

        We yield the full NC's ``info`` (with its real
        ``bbox_dense`` flag).  When ``bbox_dense=False``, the
        kernel emit adds an ``nc_map`` lookup at the top of the
        body so threads landing in cells of OTHER NCs early-exit
        -- same correctness, dramatically fewer launches.
        """
        if info.bbox is not None:
            yield info, False
