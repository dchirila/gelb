#!/usr/bin/env python3
"""
Stage 3: Fortran Backend (CPU, Serial)

Generates a standalone Fortran 90 program from a GeLB AST that has
passed through the frontend and midware stages.
"""

import hashlib
import math

from gelb.gelb_ast.ASTNodes import *
from gelb.backends.gauge_outputs import collect_gauge_outputs
from gelb.backends.string_literals import description_text, fortran_string
from gelb.frontend.intrinsic_functions import CAST_INTRINSIC_NAMES
from gelb.backends.fortran.common import (
    total_nodes_rhs,
    emit_mlups_wall_time_calc,
    emit_mlups_report_header,
    emit_mlups_throughput_lines,
)
from gelb.midware.StencilExtractionVisitor import affine_index
from gelb.midware.ast_eval import (
    collect_lattice_info,
    eval_const_expr,
    get_max_dim,
)


# GeLB type -> Fortran type
_TYPE_MAP = {
    'int': 'integer(8)',
    'int8': 'integer(1)',
    'int16': 'integer(2)',
    'int32': 'integer(4)',
    'int64': 'integer(8)',
    'real': 'double precision',
    'real16': 'real(2)',
    'real32': 'real(4)',
    'real64': 'real(8)',
    'bool': 'logical(1)',
}

# Fortran format specifiers for gauge output
_FORMAT_MAP = {
    'int': "'(I0)'",
    'int8': "'(I0)'",
    'int16': "'(I0)'",
    'int32': "'(I0)'",
    'int64': "'(I0)'",
    'real': "'(ES23.16)'",
    'real16': "'(ES15.8)'",
    'real32': "'(ES15.8)'",
    'real64': "'(ES23.16)'",
    'bool': "'(L1)'",
}

_DIM_NAMES = ['x', 'y', 'z']
_DIM_SIZE_NAMES = ['Nx', 'Ny', 'Nz']

# GeLB type -> NetCDF type constant
_NETCDF_TYPE_MAP = {
    'int': 'NF90_INT',
    'int8': 'NF90_BYTE',
    'int16': 'NF90_SHORT',
    'int32': 'NF90_INT',
    'int64': 'NF90_INT',
    'real': 'NF90_DOUBLE',
    'real16': 'NF90_FLOAT',
    'real32': 'NF90_FLOAT',
    'real64': 'NF90_DOUBLE',
    'bool': 'NF90_BYTE',
}


def generate_fortran(ast, num_timesteps=1, output_mode='netcdf',
                     output_filename=None, write_every=1,
                     random_seed=None, source_file=None,
                     resolved_geometry=None, backend_context=None,
                     poison_uninit=False, strict_fp=False):
    """Generate Fortran 90 source code from a GeLB AST.

    The cpu_fortran_serial backend is single-threaded by design: its
    role is to be a readable algorithmic reference and the
    bit-equivalence subject for cross-backend tests.  Multi-threaded
    perf is the cpu_highway backend's job.

    Args:
        ast: Program_N node (post frontend + midware).
        num_timesteps: Number of simulation time steps.
        output_mode: 'netcdf' (write .nc file) or 'stdout' (print to terminal).
        output_filename: NetCDF output filename (used when output_mode='netcdf').
        write_every: Write gauge output every N timesteps (default: 1).
        random_seed: If not None, use this fixed integer to seed the runtime
            PRNG instead of the system clock.  Enables reproducible runs of
            programs that call ``random()``.
        source_file: Original .gelb source filename (for header comment).
        resolved_geometry: Optional ``ResolvedGeometry`` computed by the
            compiler driver.  When omitted, the backend resolves geometry
            itself to preserve direct generator-call behavior.
        backend_context: Optional shared backend analysis context.  When
            supplied, it provides lattice metadata and resolved geometry;
            ``resolved_geometry`` is retained for direct-call compatibility.

    Returns:
        Complete Fortran program as a string.
    """
    gen = FortranCodeGenerator(ast, num_timesteps, output_mode,
                               output_filename, write_every,
                               random_seed, source_file,
                               resolved_geometry=resolved_geometry,
                               backend_context=backend_context,
                               poison_uninit=poison_uninit,
                               strict_fp=strict_fp)
    return gen.generate()


class FortranCodeGenerator:
    """Generates a standalone Fortran 90 program from a GeLB AST."""

    def __init__(self, ast, num_timesteps=1, output_mode='netcdf',
                 output_filename=None, write_every=1,
                 random_seed=None, source_file=None,
                 resolved_geometry=None, backend_context=None,
                 poison_uninit=False, strict_fp=False):
        if backend_context is not None and backend_context.ast is not ast:
            raise ValueError(
                "BackendContext AST does not match the AST passed to "
                "FortranCodeGenerator.")

        self.ast = ast
        self.num_timesteps = num_timesteps
        self.output_mode = output_mode
        self.output_filename = output_filename or 'gelb_output.nc'
        self.write_every = write_every
        self._random_seed = random_seed
        self._source_file = source_file
        # ``--poison-uninit``: NaN-fill lattice arrays before the
        # initializers run, so reads of never-written cells surface as
        # NaN in the output instead of hiding behind the compiler's
        # implicit zero-initialization of program-level arrays.
        self._poison_uninit = bool(poison_uninit)
        # Strict build (user manual, Numerical semantics: Build modes).
        # Fortran emits no fused operation of its own, so strictness is
        # gfortran's -ffp-contract=off; the header comment records the
        # mode.
        self._strict_fp = bool(strict_fp)
        self._border_corrections = []  # [(coords_tuple, nc_name), ...]
        self._lines = []
        self._indent = 0
        if backend_context is not None:
            self._lattice_info = backend_context.lattice_info
            self._resolved_geometry = backend_context.geometry
            self._stencils = backend_context.stencils
        else:
            self._lattice_info = collect_lattice_info(ast)
            self._resolved_geometry = resolved_geometry
            self._stencils = None
        self._uses_random = False  # set True when random() intrinsic is emitted
        self._uses_real_minmax = False  # real min/max: the IEEE 754-2019 helpers
        self._use_nc_mask = False
        self._nc_ids = None
        self._grid_sizes = None
        # Per-node-class boundary-contact info.
        #   dict: nc_name -> {dim_idx: set of sides ('low', 'high')}
        # Populated by _resolve_geometry_{1d,nd,single} and read by
        # _emit_streaming_dfs to clamp non-periodic upstream reads so
        # that boundary cells don't generate out-of-bounds Fortran
        # array reads (silences gfortran's static bounds check and
        # makes the dead read well-defined at runtime).
        self._nc_boundary_dims = {}
        # Name of the node class currently being emitted (set by
        # _emit_spatial_loop_start, cleared by _emit_spatial_loop_end).
        # Lookup key into self._nc_boundary_dims.
        self._current_nc = None
        # Per-region coordinate-literal substitution map.
        # dict: dim_idx -> literal coord string (e.g. {1: '0'} for an
        # elided y-dim with g_y = 0).  Populated by
        # _emit_spatial_loop_start when a region's bbox collapses to a
        # single point along a dim, and consumed by _emit_expr (for
        # Identifier_N coord refs) and _emit_streaming_dfs (for upstream
        # read coord computation).  Cleared by _emit_spatial_loop_end.
        self._coord_subst = {}
        self._local_names = {}
        self._active_local_names = {}
        self._bounded_names = {}
        self._bounded_name_owners = {}
        self._deferred_constant_initializers = []

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def generate(self):
        regions = self._resolve_geometry_via_midware()
        all_vars = self._collect_variables(regions)
        self._scan_for_random_usage(regions)
        self._scan_for_real_minmax(regions)
        use_netcdf = self.output_mode == 'netcdf'
        self._any_masked = any(r.get('masked') for r in regions)

        output_layout = collect_gauge_outputs(r['gauge'] for r in regions)
        self._partial_gauge_outputs = bool(output_layout and output_layout.partial)

        # --- header comment ---
        self._emit_header_comment()
        self._emit('')

        # --- program header ---
        self._emit('program gelb_simulation')
        self._indent += 1
        if use_netcdf:
            self._emit('use netcdf')
        if (self._partial_gauge_outputs or self._poison_uninit
                or self._uses_real_minmax or self._contains_nonfinite(self.ast)):
            self._emit('use ieee_arithmetic')
        self._emit('implicit none')
        self._emit('')

        # --- declarations ---
        self._emit_global_constants()
        self._emit_grid_parameters()
        self._emit_lattice_declarations()
        self._emit_variable_declarations(all_vars)
        self._emit_loop_variables()
        if self._use_nc_mask:
            self._emit('')
            self._emit_nc_map_declaration()
        if use_netcdf:
            self._emit('')
            self._emit_netcdf_declarations(output_layout)
        if self._uses_random:
            self._emit('')
            self._emit_random_declarations()
        self._emit('')

        # --- ping-pong init ---
        # IEEE_VALUE is not a Fortran initialization expression. These
        # GeLB constants are assigned once, before any simulation code.
        for assignment in self._deferred_constant_initializers:
            self._emit(assignment)
        self._emit_pingpong_init()
        if self._uses_random:
            self._emit('')
            self._emit_random_seed_init()
        self._emit('')

        # --- node class map init (multi-region) ---
        if self._use_nc_mask:
            self._emit_nc_map_init()
            self._emit('')

        # --- NetCDF setup ---
        if use_netcdf:
            self._emit_netcdf_setup(output_layout)
            self._emit('')

        # --- masked-cell DF zero-init (language guarantee) ---
        # Masked NCs have no initializer, yet neighbouring cells may
        # read their DFs (e.g. a bounce-back WALL ring around a masked
        # SOLID obstacle gathers them via bounce_back_dfs).  Zero them
        # explicitly, in both ping-pong buffers, so the guarantee does
        # not depend on the compiler's implicit zeroing of program-
        # level arrays (and --poison-uninit only flags genuinely
        # undefined reads).  See LANGUAGE_DESIGN.md.
        masked_regions = [r for r in regions if r.get('masked')]
        if masked_regions:
            self._emit('! ========== Masked-cell DF zero-init'
                       ' ==========')
            self._emit('! Language guarantee: masked cells hold zero'
                       ' DFs in both buffers')
            d = self._max_dim()
            for region in masked_regions:
                self._emit_spatial_loop_start(region)
                coords = ', '.join(
                    self._coord_subst.get(i, self._symbol_name(_DIM_NAMES[i]))
                    for i in range(d))
                for lname, info in self._lattice_info.items():
                    flname = self._symbol_name(lname)
                    zero = self._fortran_real(0.0, info['dtype'])
                    self._emit(f'{flname}(:, {coords}, :) = {zero}')
                self._emit_spatial_loop_end()
            self._emit('')

        # --- initializer (one loop per region) ---
        for region in regions:
            iblock = region['initializer']
            if iblock is None:
                continue  # masked node class with no initializer
            self._emit(
                f'! ========== Initializer: {iblock.name.name} '
                f'({self._region_label(region)}) ==========')
            self._emit_spatial_loop_start(region, iblock)
            self._emit_block_statements(iblock, 'initializer')
            self._emit_spatial_loop_end()
            self._emit('')

        # Static nodes (no dynamic): copy initializer values to both buffers.
        # The first pass above wrote to f_old; this second pass writes the
        # same values to f_new so that both ping-pong buffers are consistent.
        static_regions = [r for r in regions
                          if r['dynamic'] is None and r['initializer'] is not None]
        if static_regions:
            for region in static_regions:
                iblock = region['initializer']
                self._emit(
                    f'! ========== Init (2nd buffer): {iblock.name.name} '
                    f'({self._region_label(region)}) ==========')
                self._emit_spatial_loop_start(region, iblock)
                self._emit_block_statements(iblock, 'initializer_copy')
                self._emit_spatial_loop_end()
                self._emit('')

        # --- pre-loop gauge (t=0 snapshot of initial conditions) ---
        self._emit('! ========== Gauge at t=0 (initial conditions) ==========')
        self._emit('gelb_timestep = 0')
        self._emit('gelb_write_count = 1')
        self._emit_gauge_halo_updates()
        if self._partial_gauge_outputs and use_netcdf:
            self._emit_gauge_nan_init(output_layout)
        for region in regions:
            gblock = region['gauge']
            if gblock is None:
                continue  # masked node class -- no gauge
            self._emit(
                f'! --- Gauge: {gblock.name.name} '
                f'({self._region_label(region)}) ---')
            self._emit_spatial_loop_start(region, gblock)
            self._emit_block_statements(gblock, 'gauge')
            if use_netcdf:
                self._emit_gauge_fill_buffers(gblock)
            else:
                self._emit_gauge_output(gblock)
            self._emit_spatial_loop_end()
        if use_netcdf:
            self._emit_gauge_netcdf_write(output_layout)
        self._emit('')

        # --- time loop ---
        self._emit_mlups_timer_init()
        self._emit('')
        self._emit('! ========== Time loop ==========')
        self._emit(f'do gelb_timestep = 1, {self.num_timesteps}')
        self._indent += 1

        # Halo update: refresh ghost cells on the input buffer for
        # every periodic-axis lattice before the dynamic kernel reads
        # them.  Mirrors cpu_highway's halo-update placement.
        for lname, info in self._lattice_info.items():
            if any(self._is_periodic(info, i) for i in range(info['d'])):
                flname = self._symbol_name(lname)
                self._emit(
                    f'call gelb_halo_update_{flname}({flname}_old)')
        self._emit('')

        # dynamic (one loop per region, skip static nodes)
        self._emit_mlups_dyn_start()
        for region in regions:
            dblock = region['dynamic']
            if dblock is None:
                continue  # static node class -- no dynamic
            self._emit(
                f'! --- Dynamic: {dblock.name.name} '
                f'({self._region_label(region)}) ---')
            self._emit_spatial_loop_start(region, dblock)
            self._emit_block_statements(dblock, 'dynamic')
            self._emit_spatial_loop_end()
            self._emit('')
        self._emit_mlups_dyn_stop()

        # swap buffers
        for lname in self._lattice_info:
            flname = self._symbol_name(lname)
            self._emit(f'call gelb_swap({flname}_old, {flname}_new)')
        self._emit('')

        # gauge (one loop per region, filling shared buffers)
        use_write_guard = self.write_every > 1
        if use_write_guard:
            self._emit(f'if (mod(gelb_timestep, {self.write_every}) == 0 '
                       f'.or. gelb_timestep == {self.num_timesteps}) then')
            self._indent += 1

        self._emit('gelb_write_count = gelb_write_count + 1')
        self._emit_gauge_halo_updates()

        if self._partial_gauge_outputs and use_netcdf:
            self._emit_gauge_nan_init(output_layout)

        for region in regions:
            gblock = region['gauge']
            if gblock is None:
                continue  # masked node class -- no gauge
            self._emit(
                f'! --- Gauge: {gblock.name.name} '
                f'({self._region_label(region)}) ---')
            self._emit_spatial_loop_start(region, gblock)
            self._emit_block_statements(gblock, 'gauge')
            if use_netcdf:
                self._emit_gauge_fill_buffers(gblock)
            else:
                self._emit_gauge_output(gblock)
            self._emit_spatial_loop_end()

        if use_netcdf:
            self._emit_gauge_netcdf_write(output_layout)

        if use_write_guard:
            self._indent -= 1
            self._emit('end if')

        # end time loop
        self._indent -= 1
        self._emit('end do')
        self._emit_mlups_report()

        # --- NetCDF cleanup ---
        if use_netcdf:
            self._emit('')
            self._emit('! Close NetCDF file')
            self._emit('call gelb_nc_check(nf90_close(gelb_ncid))')

        # --- contains ---
        self._indent -= 1
        self._emit('')
        self._emit('contains')
        self._emit('')
        self._indent += 1
        self._emit_user_function_definitions()
        self._emit_swap_subroutine()
        self._emit('')
        self._emit_halo_update_subroutines()
        if self._uses_random:
            self._emit('')
            self._emit_random_function()
        if self._uses_real_minmax:
            self._emit('')
            self._emit_real_minmax_functions()
        if use_netcdf:
            self._emit('')
            self._emit_nccheck_subroutine()
        self._indent -= 1

        # --- end program ---
        self._emit('')
        self._emit('end program gelb_simulation')

        from gelb.backends.fortran.line_formatter import format_fortran_lines
        return format_fortran_lines('\n'.join(self._lines) + '\n')

    # ------------------------------------------------------------------
    # AST metadata collection
    # ------------------------------------------------------------------

    _REAL_TYPES = frozenset({'real', 'real16', 'real32', 'real64'})
    # A real literal is spelled in the width the type pass gave it: a
    # plain literal is `real`, double precision (the manual's contract:
    # `real` is an alias for `real64`, in a real32 program too), a folded
    # real32 constant is real(4).  Every numeric kind reaches the
    # emitted code as the type pass gave it; a per-program dominant
    # real kind would make `real` single precision in a real32 program.
    _REAL_KINDS = ('real', 'real16', 'real32', 'real64')

    @classmethod
    def _contains_nonfinite(cls, node):
        if isinstance(node, RealLiteral_N):
            return not math.isfinite(float(node.value))
        if isinstance(node, Node_N):
            return any(cls._contains_nonfinite(value)
                       for value in vars(node).values())
        if isinstance(node, (list, tuple)):
            return any(cls._contains_nonfinite(value) for value in node)
        return False

    # An integer literal is spelled bare, a default-kind integer, unless
    # its magnitude does not fit the default kind: then it carries the
    # kind suffix of the width that holds it, ``9007199254740993_8``
    # (a native literal must express its GeLB value and type; gfortran
    # rejects the bare spelling).  The minimum int64 value has no
    # integer(8) magnitude and is spelled as the negative maximum minus
    # one.  A bare literal is enough otherwise: Fortran evaluates
    # mixed-kind integer arithmetic in the wider kind, every GeLB
    # integer the literal can meet is integer(8) (a variable, a
    # constant, a coordinate, ``t`` and ``Nx`` converted at their use),
    # and literal-only arithmetic was folded upstream.
    _DEFAULT_INT_MAX = 2 ** 31 - 1
    _INT64_MIN = -2 ** 63

    @classmethod
    def _fortran_int(cls, value):
        v = int(value)
        if -cls._DEFAULT_INT_MAX <= v <= cls._DEFAULT_INT_MAX:
            return str(v)
        return cls._fortran_int8(v)

    @classmethod
    def _fortran_int8(cls, value):
        """``value`` spelled as an ``integer(8)`` literal."""
        v = int(value)
        if v == cls._INT64_MIN:
            return f'(-{-(v + 1)}_8 - 1_8)'
        return f'{v}_8' if v >= 0 else f'(-{-v}_8)'

    @staticmethod
    def _int_literal_value(node):
        """The value of an integer literal, negated or wrapped in a
        promotion; None for anything else."""
        negate = False
        while True:
            if isinstance(node, TypePromotionNode_N):
                node = node.expr
            elif isinstance(node, UnaryMinusExpr_N):
                negate = not negate
                node = node.value
            else:
                break
        if isinstance(node, IntLiteral_N):
            return -node.value if negate else node.value
        return None

    @classmethod
    def _literal_kind(cls, node):
        """The real kind of ``node``: a literal's inferred width, or a
        data type's element width; ``real`` when neither is a real."""
        kind = getattr(node, 'element_dtype', None)
        if kind is None:
            kind = getattr(getattr(node, 'inferred_type', None), 'element_dtype', None)
        return kind if kind in cls._REAL_KINDS else 'real'

    def _resolve_geometry_via_midware(self):
        """Resolve geometry using the midware analysis pass.

        Delegates to ``gelb.midware.geometry.resolve_geometry()`` and
        populates the backend's internal fields from the result.
        Returns a list of region dicts in the format the emission
        layer expects.
        """
        if self._resolved_geometry is None:
            from gelb.midware.geometry import resolve_geometry
            geo = resolve_geometry(self.ast)
        else:
            geo = self._resolved_geometry

        self._grid_sizes = geo.grid_sizes
        self._nc_boundary_dims = geo.boundary_contacts
        self._border_corrections = geo.border_corrections
        self._paint_ops = geo.paint_ops

        # 1D with contiguous regions: use the tight-loop form
        # (no nc_map, each region gets its own do-loop bounds).
        if geo.ndim == 1 and all(
                info.bbox_dense for info in geo.nc_info.values()):
            regions = []
            for nc_name in geo.nc_order:
                info = geo.nc_info[nc_name]
                lo, hi = info.bbox[0]
                region = self._make_region(nc_name, lo, hi)
                region['bbox'] = info.bbox
                region['bbox_dense'] = True
                regions.append(region)
            return regions

        # 2D/3D or non-contiguous 1D: use nc_map with IF guards.
        if len(geo.nc_order) > 1:
            self._nc_ids = {name: info.nc_id
                            for name, info in geo.nc_info.items()}
            self._use_nc_mask = True
        else:
            self._nc_ids = None
            self._use_nc_mask = False

        regions = []
        for nc_name in geo.nc_order:
            info = geo.nc_info[nc_name]
            region = self._make_region(nc_name, None, None)
            region['bbox'] = info.bbox
            region['bbox_dense'] = info.bbox_dense
            if self._use_nc_mask:
                region['nc_id'] = info.nc_id
            regions.append(region)
        return regions

    def _make_region(self, nc_name, low, high):
        """Build a region dict for a contiguous node-class run."""
        # Find the node class definition
        nc = None
        for stmt in self.ast.node_classes.stmts:
            if isinstance(stmt, NodeClassInstaStmt_N) and stmt.name.name == nc_name:
                nc = stmt
                break
        if nc is None:
            raise ValueError(f"Node class '{nc_name}' not found")

        return {
            'nc_name': nc_name,
            'low': low,
            'high': high,
            # Per-dim bounding box of the cells assigned to this NC.
            # Populated by _resolve_geometry_via_midware after the
            # region is built, from the midware geometry resolver's
            # NCInfo.bbox.  A None bbox means "fall back to full-grid
            # loops" -- exercised only on the error path.
            'bbox': None,
            'bbox_dense': False,
            'initializer': (self._find_block(self.ast.initializers,
                                             nc.initializer.name)
                            if nc.initializer is not None else None),
            'dynamic': (self._find_block(self.ast.dynamics, nc.dynamic.name)
                        if nc.dynamic is not None else None),
            'gauge': (self._find_block(self.ast.gauges, nc.gauge.name)
                      if nc.gauge is not None else None),
            'masked': nc.masked,
        }

    def _eval_range_expr(self, expr):
        """Evaluate an AST expression to an integer (for paint ranges)."""
        result = eval_const_expr(
            expr, ast=self.ast, lattice_info=self._lattice_info)
        return int(result)

    def _find_block(self, block_list, name):
        for block in block_list:
            if block.name.name == name:
                return block
        raise ValueError(f"Block '{name}' not found")

    def _collect_variables(self, regions):
        """Collect declarations by computational block, preserving identity."""
        result = []
        for region in regions:
            for key in ('initializer', 'dynamic', 'gauge'):
                block = region[key]
                if block is None or id(block) in self._local_names:
                    continue
                block_index = len(self._local_names)
                names = self._local_names[id(block)] = {}
                declarations = list(getattr(block, 'outputs', ())) + list(block.stmts)
                for decl in declarations:
                    if isinstance(decl, VariableDeclarationStmt_N):
                        name = decl.name.name
                        if name not in names:
                            encoded = self._bounded_name(
                                f'gelb_b{block_index}_{self._symbol_name(name)}')
                            names[name] = encoded
                            result.append((encoded, decl.data_type))
        return result

    def _vname(self, name):
        """Resolve a block-local name without affecting lattice/global names."""
        return self._active_local_names.get(name) or self._symbol_name(name)

    def _scan_for_real_minmax(self, regions):
        """Pre-scan all blocks for a real-typed ``min``/``max`` call, which
        is emitted as the IEEE 754-2019 helper (user manual, Numerical
        semantics: Types and promotion) and needs ``ieee_arithmetic``."""
        def _walk(node):
            if isinstance(node, IntrinsicFunctionCall_N) \
                    and node.function_name in ('min', 'max') \
                    and self._is_real_kind(node):
                self._uses_real_minmax = True
                return
            for child in getattr(node, '__dict__', {}).values():
                if isinstance(child, Node_N):
                    _walk(child)
                elif isinstance(child, list):
                    for item in child:
                        if isinstance(item, Node_N):
                            _walk(item)

        for region in regions:
            for key in ('initializer', 'dynamic', 'gauge'):
                block = region[key]
                if block is not None:
                    _walk(block)
                if self._uses_real_minmax:
                    return

    @staticmethod
    def _is_real_kind(node):
        dtype = getattr(getattr(node, 'inferred_type', None), 'element_dtype', None)
        return dtype in ('real', 'real32', 'real64')

    def _emit_real_minmax_functions(self):
        """IEEE 754-2019 minimum / maximum for reals (user manual,
        Numerical semantics: Types and promotion), the same definition as
        the C++ backends' helpers: a NaN operand gives NaN, and -0 is
        less than +0.  Fortran's own MIN/MAX differ on both."""
        for kind, suffix in (('real(8)', 'r8'), ('real(4)', 'r4')):
            one = '1.0_8' if suffix == 'r8' else '1.0_4'
            zero = '0.0_8' if suffix == 'r8' else '0.0_4'
            for name, pick_first_on_tie in (('min', True), ('max', False)):
                self._emit(f'elemental function gelb_{name}_{suffix}(a, b) result(r)')
                self._indent += 1
                self._emit(f'{kind}, intent(in) :: a, b')
                self._emit(f'{kind} :: r')
                self._emit('if (ieee_is_nan(a)) then')
                self._emit('  r = a')
                self._emit('else if (ieee_is_nan(b)) then')
                self._emit('  r = b')
                self._emit(f'else if (a {"<" if name == "min" else ">"} b) then')
                self._emit('  r = a')
                self._emit(f'else if (b {"<" if name == "min" else ">"} a) then')
                self._emit('  r = b')
                # equal values, possibly zeros of different sign: -0 is the smaller
                self._emit(f'else if (sign({one}, a) < {zero}) then')
                self._emit('  r = a' if name == 'min' else '  r = b')
                self._emit('else')
                self._emit('  r = b' if name == 'min' else '  r = a')
                self._emit('end if')
                self._indent -= 1
                self._emit(f'end function gelb_{name}_{suffix}')
                self._emit('')

    def _scan_for_random_usage(self, regions):
        """Pre-scan all blocks for random() intrinsic calls."""
        def _walk(node):
            if isinstance(node, IntrinsicFunctionCall_N):
                if node.function_name == 'random':
                    self._uses_random = True
                    return
            for child in getattr(node, '__dict__', {}).values():
                if isinstance(child, Node_N):
                    _walk(child)
                elif isinstance(child, list):
                    for item in child:
                        if isinstance(item, Node_N):
                            _walk(item)

        for region in regions:
            for key in ('initializer', 'dynamic', 'gauge'):
                block = region[key]
                if block is not None:
                    _walk(block)
                if self._uses_random:
                    return

    # ------------------------------------------------------------------
    # Emission helpers
    # ------------------------------------------------------------------

    def _emit(self, line):
        if line == '':
            self._lines.append('')
        else:
            self._lines.append('  ' * self._indent + line)

    def _bounded_name(self, name):
        """Leave room for the longest derived name, ``gelb_halo_update_``.

        Hash names use a namespace disjoint from ordinary ``g_`` names.
        Record ownership and disambiguate even a truncated-hash collision.
        """
        if len(name) <= 46:
            return name
        if name not in self._bounded_names:
            digest = hashlib.sha256(name.encode('utf-8')).hexdigest()[:20]
            candidate = self._hashed_name(name)
            index = 0
            while candidate in self._bounded_name_owners:
                index += 1
                candidate = f'g0_{digest}_{index}'
            self._bounded_names[name] = candidate
            self._bounded_name_owners[candidate] = name
        return self._bounded_names[name]

    @staticmethod
    def _hashed_name(name):
        digest = hashlib.sha256(name.encode('utf-8')).hexdigest()[:20]
        return f'g0_{name[:20]}_{digest}'

    @classmethod
    def _uname(cls, name):
        """Stateless spelling for external identifier-mapping consumers."""
        encoded = cls._encode_name(name)
        return encoded if len(encoded) <= 46 else cls._hashed_name(encoded)

    def _symbol_name(self, name):
        return self._bounded_name(self._encode_name(name))

    @staticmethod
    def _encode_name(name):
        """Encode a GeLB identifier for case-insensitive Fortran emission.

        Fortran is case-insensitive, so GeLB names that differ only in
        case (e.g. ``m`` vs ``M``, ``fIn`` vs ``fin``) must map to
        distinct Fortran identifiers.  The encoding uses underscore
        escaping:

        - lowercase letter ``x``   ->  ``x``
        - uppercase letter ``X``   ->  ``_`` + lowercase(``X``)
        - literal underscore ``_`` ->  ``__``
        - digit ``d``              ->  ``d``

        The result is prefixed with ``g_`` to avoid clashes with Fortran
        reserved words and intrinsics.

        Examples::

            m       ->  g_m
            M       ->  g__m
            TAU     ->  g__t_a_u
            fIn     ->  g_f_in
            M_INV   ->  g__m___i_n_v
            rho     ->  g_rho
            NX      ->  g__n_x
            ux      ->  g_ux

        The encoding is injective: distinct GeLB names always produce
        distinct Fortran names under case-folding.  Backend-internal
        names (``gelb_*``) are never passed through here.
        """
        encoded = []
        for ch in name:
            if ch == '_':
                encoded.append('__')
            elif ch.isupper():
                encoded.append('_')
                encoded.append(ch.lower())
            else:
                encoded.append(ch)
        return 'g_' + ''.join(encoded)

    def _max_dim(self):
        return get_max_dim(self._lattice_info)

    # ------------------------------------------------------------------
    # Declaration emission
    # ------------------------------------------------------------------

    def _dim_size_fname(self, dim_index):
        """Return the Fortran identifier for the i-th grid dimension size.

        When a global constant (e.g. ``NX``) matches the canonical
        dimension name (``Nx``) case-insensitively, the constant's own
        encoded name is used (``g__n_x``) instead of the canonical
        encoding (``g__nx``).  This avoids duplicate or mismatched
        declarations after case-aware name encoding.
        """
        return self._symbol_name(self._dim_size_gelb_names[dim_index])

    def _emit_header_comment(self):
        """Emit a header comment explaining the generated code and naming conventions."""
        import os
        self._emit('! Generated by GeLB (Generic Lattice Boltzmann DSL)')
        if self._source_file:
            basename = os.path.basename(self._source_file)
            self._emit(f'! Source: {basename}')
        if self._strict_fp:
            self._emit('! Strict floating point: no fused multiply-add'
                       ' (compile with -ffp-contract=off)')
        self._emit('!')
        self._emit('! Naming conventions:')
        self._emit('!   g_<name>  -- user-defined identifier (variable, constant, lattice)')
        self._emit('!   g__<name> -- compiler-derived identifier (grid dimensions)')
        self._emit('!   gelb_*    -- compiler-internal (NetCDF, ping-pong buffers, timing)')

    def _emit_grid_parameters(self):
        """Emit backend-internal grid-size parameters.

        Grid sizes are always emitted as plain ``integer`` (default kind,
        32-bit on x86) -- not ``integer(8)`` -- because NetCDF's Fortran
        API takes default-kind integers for dimension lengths and
        start/count arrays.

        The backend-internal parameter is always emitted with the
        canonical encoded name (``g__nx``, ``g__ny``, ``g__nz``), even
        when a matching user constant exists.  The user constant is left
        untouched (still ``integer(8)``) so user code obeys
        ``int == int64``; the backend just uses its own default-kind alias
        for indexing and loop bounds.
        """
        self._emit('! Grid parameters')
        # All lattices share the same grid (validated by frontend)
        first_lattice = next(iter(self._lattice_info.values()))
        d = first_lattice['d']
        grid_size = first_lattice['grid_size']

        # Backend-internal dimension parameters always use the canonical
        # encoded name -- never a user constant -- so they are always
        # default-kind integer regardless of the user's type choices.
        self._dim_size_gelb_names = list(_DIM_SIZE_NAMES)

        for i in range(d):
            is_literal = False
            if d == 1:
                # 1D: grid_size is already resolved to a Python int
                if isinstance(grid_size, int):
                    size_val = str(grid_size)
                    is_literal = True
                else:
                    size_val = self._emit_expr(grid_size, 'global')
                    is_literal = isinstance(grid_size, IntLiteral_N)
            else:
                # 2D/3D: grid_size is a List_N; extract i-th element
                size_val_node = grid_size.elements[i]
                size_val = self._emit_expr(size_val_node, 'global')
                is_literal = isinstance(size_val_node, IntLiteral_N)
            # If size_val is an expression that could involve an
            # integer(8) user constant, wrap in int() to narrow it to
            # the default kind without compiler warnings.  For literal
            # sizes, no cast is needed.
            rhs = size_val if is_literal else f'int({size_val})'
            self._emit(
                f'integer, parameter :: {self._dim_size_fname(i)} = {rhs}')
        self._emit('')

    def _emit_global_constants(self):
        if self.ast.global_constants is None:
            return
        self._emit('! Global constants')
        for stmt in self.ast.global_constants.stmts:
            if isinstance(stmt, ConstantDefinitionStmt_N):
                cst_kind = stmt.data_type.element_dtype
                ftype = _TYPE_MAP[cst_kind]
                fname = self._symbol_name(stmt.name.name)
                value = self._emit_constant_array(stmt, cst_kind)
                if value is None:
                    value = self._emit_expr(stmt.value, 'global')
                if 'ieee_value(' in value:
                    qualifier = ''
                    initialization = ''
                    self._deferred_constant_initializers.append(f'{fname} = {value}')
                else:
                    qualifier = ', parameter'
                    initialization = f' = {value}'
                shape = stmt.data_type.shape
                if isinstance(shape, IntLiteral_N):
                    # 1D array constant
                    self._emit(f'{ftype}{qualifier} :: {fname}(0:{shape.value - 1}){initialization}')
                elif isinstance(shape, Array1DLiteral_N):
                    # Multi-dimensional array constant
                    dims = ', '.join(
                        f'0:{e.value - 1}'
                        for e in shape.value.elements)
                    self._emit(f'{ftype}{qualifier} :: {fname}({dims}){initialization}')
                else:
                    # Scalar constant
                    self._emit(f'{ftype}{qualifier} :: {fname}{initialization}')
        self._emit('')

    _NARROW_ELEMENT_KINDS = ('real32', 'real16', 'int8', 'int16', 'int32')

    def _emit_constant_array(self, stmt, kind):
        """A constant array of a narrow element kind as a constructor of
        literals in that kind: each element is the value the kind stores
        (user manual, Numerical semantics: Types and promotion; through
        the one evaluator), so that the declaration, the element reads
        and the folds agree; an element the kind cannot hold (a real
        past its range) is spelled as the conversion, which gives an
        infinity at run time (Special values).  A constant array is
        emitted in its declared kind: ``int((/300, 1/), 1)`` did not
        deliver the wrapped value.  None for a wide kind or a non-array,
        which keep the general emission."""
        if kind not in self._NARROW_ELEMENT_KINDS:
            return None
        value = stmt.value
        while isinstance(value, TypePromotionNode_N):
            value = value.expr
        if isinstance(value, Array1DLiteral_N):
            elements = [self._fortran_constant_element(e, kind)
                        for e in value.value.elements]
            return f'(/{", ".join(elements)}/)'
        if isinstance(value, Array2DLiteral_N):
            rows = value.value.elements
            nrows = len(rows)
            ncols = len(rows[0].value.elements)
            elements = []
            for col in range(ncols):          # column-major, as reshape wants
                for row in range(nrows):
                    elements.append(self._fortran_constant_element(
                        rows[row].value.elements[col], kind))
            return f'reshape((/{", ".join(elements)}/), (/{nrows}, {ncols}/))'
        return None

    _INT_KIND_SUFFIX = {'int8': '_1', 'int16': '_2', 'int32': '_4'}

    def _fortran_constant_element(self, node, kind):
        from gelb.midware.ast_eval import convert_plain, eval_const_expr
        try:
            value = eval_const_expr(node, ast=self.ast)
        except Exception:
            # not a constant, or an expression that overflows
            # (``real32(1.0e300)``, ``1.0e300 * 1.0e300``): the expression
            # itself, converted; gfortran folds it to an infinity under
            # ``-fno-range-check``, the IEEE value the operation gives at
            # run time (user manual, Numerical semantics: Special values)
            return self._emit_cast(self._emit_expr(node, 'global'), None, kind)
        try:
            converted = convert_plain(value, kind)
        except OverflowError:
            # past the kind's range: the conversion, an infinity at run time
            wide = self._fortran_real(float(value), 'real')
            return f'real({wide}, 2)' if kind == 'real16' else f'real({wide})'
        except Exception:
            return self._emit_cast(self._emit_expr(node, 'global'), None, kind)
        if isinstance(converted, bool):
            return self._emit_expr(node, 'global')
        if isinstance(converted, int):
            suffix = self._INT_KIND_SUFFIX[kind]
            return f'{converted}{suffix}' if converted >= 0 else f'(-{-converted}{suffix})'
        return self._fortran_real(float(converted), kind)

    def _emit_lattice_declarations(self):
        self._emit('! Lattice arrays')
        self._emit('! Hidden-halo storage: each spatial dim is sized')
        self._emit('! -1:N (one ghost cell per axis-end).  Periodic axes')
        self._emit('! get the wrap pre-staged into the halo by')
        self._emit('! gelb_halo_update_<lname>() each timestep, so the')
        self._emit('! inner streaming loop can read x+/-1 directly without')
        self._emit('! modulo().  Wall axes also get the +2 storage but')
        self._emit('! their halo cells stay zero; wall reads still clamp')
        self._emit('! via max(0,...) / min(N-1,...) at the read site.')
        self._emit('! Layout matches cpu_highway''s halo convention so')
        self._emit('! that compare_backends.py can diff with no')
        self._emit('! storage-shape special-casing.')
        for lname, info in self._lattice_info.items():
            ftype = _TYPE_MAP[info['dtype']]
            q = info['q']
            d = info['d']
            flname = self._symbol_name(lname)

            # Dimensions: (0:q-1, -1:Nx, [-1:Ny, ...], 0:1)
            dims = [f'0:{q - 1}']
            for i in range(d):
                dims.append(f'-1:{self._dim_size_fname(i)}')
            dims.append('0:1')  # ping-pong

            self._emit(f'{ftype} :: {flname}({", ".join(dims)})')
            self._emit(f'integer :: {flname}_old, {flname}_new')
        self._emit('')

    def _emit_variable_declarations(self, variables):
        if not variables:
            return
        self._emit('! Variables')
        for vname, data_type in variables:
            ftype = _TYPE_MAP[data_type.element_dtype]
            fvname = vname
            shape = data_type.shape
            if isinstance(shape, List_N) and len(shape.elements) == 0:
                # Scalar (0-dimensional)
                self._emit(f'{ftype} :: {fvname}')
            elif isinstance(shape, IntLiteral_N):
                # 1D array
                self._emit(f'{ftype} :: {fvname}(0:{shape.value - 1})')
            elif isinstance(shape, Array1DLiteral_N):
                # Multi-dimensional array
                dims = ', '.join(
                    f'0:{e.value - 1}' for e in shape.value.elements)
                self._emit(f'{ftype} :: {fvname}({dims})')
            elif isinstance(shape, List_N) and len(shape.elements) > 0:
                dims = ', '.join(
                    f'0:{e.value - 1}' for e in shape.elements)
                self._emit(f'{ftype} :: {fvname}({dims})')
            else:
                # Fallback
                self._emit(f'{ftype} :: {fvname}')
        self._emit('')

    def _emit_loop_variables(self):
        self._emit('! Loop variables')
        d = self._max_dim()
        dim_vars = ', '.join(self._symbol_name(n) for n in _DIM_NAMES[:d])
        # A coordinate is a GeLB `int`, int64: `x + 2147483647` must
        # not overflow.
        self._emit(f'integer(8) :: {dim_vars}')
        self._emit('integer :: gelb_timestep')
        self._emit('integer :: gelb_write_count')
        if self._uses_random:
            self._emit('integer :: gelb_df   ! per-element random() draws')
        self._emit('')
        self._emit_mlups_declarations()

    # ------------------------------------------------------------------
    # MLUPS timing
    # ------------------------------------------------------------------

    def _emit_mlups_declarations(self):
        """Declare variables for MLUPS measurement."""
        self._emit('! MLUPS timing')
        self._emit('integer(8) :: gelb_clock_start, gelb_clock_end, gelb_clock_rate')
        self._emit('integer(8) :: gelb_dyn_clock_start, gelb_dyn_clock_end')
        self._emit('integer(8) :: gelb_dyn_ticks')
        self._emit('real(8) :: gelb_wall_secs, gelb_dyn_secs')
        self._emit('real(8) :: gelb_total_nodes')

    def _emit_mlups_timer_init(self):
        """Emit timer initialization before the time loop."""
        d = self._max_dim()
        node_expr = total_nodes_rhs(
            self._dim_size_fname(i) for i in range(d))
        self._emit('')
        self._emit('! MLUPS timer init')
        self._emit(f'gelb_total_nodes = {node_expr}')
        self._emit('gelb_dyn_ticks = 0')
        self._emit('call system_clock(gelb_clock_start, gelb_clock_rate)')

    def _emit_mlups_dyn_start(self):
        """Emit timer start around dynamic kernels."""
        self._emit('call system_clock(gelb_dyn_clock_start)')

    def _emit_mlups_dyn_stop(self):
        """Emit timer stop around dynamic kernels and accumulate."""
        self._emit('call system_clock(gelb_dyn_clock_end)')
        self._emit('gelb_dyn_ticks = gelb_dyn_ticks + '
                    '(gelb_dyn_clock_end - gelb_dyn_clock_start)')

    def _emit_mlups_report(self):
        """Emit MLUPS computation and print after the time loop."""
        self._emit('')
        self._emit('! MLUPS report')
        emit_mlups_wall_time_calc(self._emit)
        self._emit('gelb_dyn_secs = dble(gelb_dyn_ticks) '
                    '/ dble(gelb_clock_rate)')
        emit_mlups_report_header(self._emit)
        self._emit(f"write(*, '(A,F10.3,A)') "
                    f"'  Compute time: ', gelb_dyn_secs, ' s'")
        emit_mlups_throughput_lines(
            self._emit, self.num_timesteps, 'gelb_dyn_secs')

    def _emit_pingpong_init(self):
        self._emit('! Initialize ping-pong buffers')
        for lname in self._lattice_info:
            flname = self._symbol_name(lname)
            self._emit(f'{flname}_old = 0')
            self._emit(f'{flname}_new = 1')
        if self._poison_uninit:
            self._emit('')
            self._emit('! --poison-uninit: NaN-fill lattice arrays so'
                       ' reads of never-written')
            self._emit('! cells surface as NaN instead of hiding behind'
                       ' implicit zeros')
            for lname, info in self._lattice_info.items():
                flname = self._symbol_name(lname)
                zero_lit = self._fortran_real(0.0, info['dtype'])
                self._emit(f'{flname} = '
                           f'ieee_value({zero_lit}, ieee_quiet_nan)')

    # ------------------------------------------------------------------
    # 2D multi-region: node-class map
    # ------------------------------------------------------------------

    def _region_label(self, region):
        """Return a human-readable label for a region (used in comments)."""
        if region.get('nc_id') is not None:
            return f'{region["nc_name"]}, nc_id={region["nc_id"]}'
        elif region['low'] is not None:
            return f'nodes {region["low"]}..{region["high"]}'
        else:
            return f'nodes None..None'

    def _emit_nc_map_declaration(self):
        """Emit declaration for the integer node-class map array."""
        d = self._max_dim()
        dims = ', '.join(f'0:{self._dim_size_fname(i)}-1' for i in range(d))
        self._emit('! Node class map')
        self._emit(f'integer :: gelb_nc_map({dims})')

    def _emit_nc_map_init(self):
        """Emit Fortran assignments that initialize the node-class map.

        Replays the resolved geometry's paint operations in source order
        (``ResolvedGeometry.paint_ops``): a range or point paint becomes
        one array-slice assignment, a ``where`` paint one assignment per
        cell it painted.  Later statements overwrite earlier ones
        whatever their kind, exactly as the resolver applied them; the
        ``border()`` corrections follow.  The map therefore matches
        ``nc_map``, which the validators and the other backends use.
        Works for any number of dimensions (2D, 3D, ...).
        """
        self._emit('! Initialize node class map')
        for op in self._paint_ops:
            kind, payload, nc_name = op
            nc_id = self._nc_ids[nc_name]
            if kind == 'rect':
                slices = []
                for i, (lo, hi) in enumerate(payload):
                    dim_size = self._grid_sizes[i]
                    if lo == 0 and hi == dim_size - 1:
                        slices.append(':')
                    elif lo == hi:
                        slices.append(str(lo))
                    else:
                        slices.append(f'{lo}:{hi}')
                slice_str = ', '.join(slices)
                self._emit(
                    f'gelb_nc_map({slice_str}) = '
                    f'{nc_id}  ! {nc_name}')
            else:  # 'cells': one assignment per painted cell
                if payload:
                    self._emit(f'! where-paint: {nc_name}')
                for coords in payload:
                    slice_str = ', '.join(str(c) for c in coords)
                    self._emit(
                        f'gelb_nc_map({slice_str}) = '
                        f'{nc_id}  ! {nc_name}')

        # Apply border() corrections: emit per-cell overrides for cells
        # that were repainted by border() during geometry resolution.
        if self._border_corrections:
            self._emit('! border() corrections')
            for coords, nc_name in self._border_corrections:
                nc_id = self._nc_ids[nc_name]
                slice_str = ', '.join(str(c) for c in coords)
                self._emit(
                    f'gelb_nc_map({slice_str}) = '
                    f'{nc_id}  ! {nc_name} (border)')

    # ------------------------------------------------------------------
    # Spatial loops
    # ------------------------------------------------------------------

    def _emit_spatial_loop_start(self, region=None, block=None):
        """Emit nested DO loops for spatial dimensions.

        ``block`` is the block the loops will run; when it calls a
        library function, the innermost loop carries ``!GCC$ novector``
        so that gfortran does not vectorize it through glibc's vector
        math library (libmvec, four-ULP functions in the vector body,
        the scalar library in the remainder: results by cell position;
        user manual, Numerical semantics: Library functions).  One
        implementation, the scalar library, then serves every cell.

        Uses ``region['bbox']`` to tightly bound each loop.  A dim
        whose bbox collapses to a single point (lo == hi) is ELIDED:
        every reference to that coordinate (emitted by ``_emit_expr``
        or ``_emit_streaming_dfs``) is rewritten as a literal, and no
        ``do``/``end do`` pair is emitted for that dim.  When all dims
        collapse to literals (e.g. ``nodes[0, 0] = CORNER`` in 2D),
        the block body runs once with zero surrounding control flow.

        The surrounding ``!$omp parallel do`` directive is only
        emitted if at least one dim remains active, and its
        ``collapse(...)`` count tracks the number of active dims.

        The runtime ``if (gelb_nc_map == nc_id)`` guard is dropped
        when ``region['bbox_dense']`` is True -- the bbox loops are
        then exact, so no runtime filtering is needed.
        """
        # Track the current node class so that _emit_streaming_dfs
        # (and any other per-NC-aware emission hook) can look up
        # boundary-contact info via self._nc_boundary_dims.
        self._active_local_names = self._local_names.get(id(block), {})
        self._current_nc = region['nc_name'] if region is not None else None
        d = self._max_dim()
        bbox = region.get('bbox') if region is not None else None
        # Partition dims into elided (lo == hi -> coord literal) and
        # active (still looped).  An absent bbox falls back to the
        # full grid -- defensive; all resolved regions populate bbox.
        self._coord_subst = {}
        active_dims = []
        dim_bounds = {}   # dim_idx -> (lo_literal, hi_literal) for active dims
        for i in range(d):
            if bbox is not None:
                lo, hi = bbox[i]
            else:
                lo, hi = None, None
            if lo is not None and lo == hi:
                self._coord_subst[i] = str(lo)
            else:
                active_dims.append(i)
                dim_bounds[i] = (lo, hi)
        n_active = len(active_dims)
        # Emit do-loops for active dims only, innermost last.  Active
        # dims use the bbox bounds when available, otherwise fall
        # back to the full grid.
        novector = block is not None and self._block_calls_library(block)
        for i in reversed(active_dims):
            fdim = self._symbol_name(_DIM_NAMES[i])
            lo, hi = dim_bounds[i]
            if novector and i == active_dims[0]:
                self._emit('!GCC$ novector')
            if lo is not None:
                self._emit(f'do {fdim} = {lo}, {hi}')
            else:
                fdim_size = self._dim_size_fname(i)
                self._emit(f'do {fdim} = 0, {fdim_size} - 1')
            self._indent += 1
        # Multi-region: emit IF guard after DO loops, but only if the
        # bbox isn't dense (otherwise the bbox loops already cover
        # exactly the cells belonging to this node class).  Elided
        # dims in the guard use their coord literal.
        if (self._use_nc_mask and region is not None and
                region.get('nc_id') is not None and
                not region.get('bbox_dense', False)):
            fdim_parts = []
            for i in range(d):
                if i in self._coord_subst:
                    fdim_parts.append(self._coord_subst[i])
                else:
                    fdim_parts.append(self._symbol_name(_DIM_NAMES[i]))
            fdims = ', '.join(fdim_parts)
            self._emit(
                f'if (gelb_nc_map({fdims}) == {region["nc_id"]}) then')
            self._indent += 1
            self._if_guard_active = True
        else:
            self._if_guard_active = False
        self._active_dims_count = n_active

    _LIBRARY_FUNCTIONS = frozenset({'sin', 'cos', 'tan', 'tanh', 'exp', 'log', 'atan2'})

    def _block_calls_library(self, block) -> bool:
        """Whether ``block`` calls a library function, or raises a real
        to a power (``pow`` is a library function too)."""
        def _walk(node):
            if isinstance(node, IntrinsicFunctionCall_N) \
                    and node.function_name in self._LIBRARY_FUNCTIONS:
                return True
            if isinstance(node, Pow_N) and self._is_real_kind(node):
                return True
            for child in getattr(node, '__dict__', {}).values():
                if isinstance(child, Node_N):
                    if _walk(child):
                        return True
                elif isinstance(child, list):
                    for item in child:
                        if isinstance(item, Node_N) and _walk(item):
                            return True
            return False
        return _walk(block)

    def _emit_spatial_loop_end(self):
        if getattr(self, '_if_guard_active', False):
            self._indent -= 1
            self._emit('end if')
            self._if_guard_active = False
        for _ in range(self._active_dims_count):
            self._indent -= 1
            self._emit('end do')
        self._current_nc = None
        self._coord_subst = {}
        self._active_dims_count = 0
        self._active_local_names = {}

    # ------------------------------------------------------------------
    # Block statement emission
    # ------------------------------------------------------------------

    def _emit_block_statements(self, block, context):
        for stmt in block.stmts:
            self._emit_statement(stmt, context)

    @staticmethod
    def _draw_broadcast_count(stmt):
        """The element count when ``stmt`` declares a one-dimensional
        array initialised by a broadcast ``random()``, else None."""
        init = stmt.initial_value
        while isinstance(init, TypePromotionNode_N):
            init = init.expr
        if not isinstance(init, BroadcastNode_N):
            return None
        call = init.scalar_expr
        while isinstance(call, TypePromotionNode_N):
            call = call.expr
        if not (isinstance(call, IntrinsicFunctionCall_N)
                and call.function_name == 'random'):
            return None
        shape = stmt.data_type.shape
        if isinstance(shape, IntLiteral_N):
            return shape.value
        if isinstance(shape, List_N) and len(shape.elements) == 1 \
                and isinstance(shape.elements[0], IntLiteral_N):
            return shape.elements[0].value
        return None

    def _emit_statement(self, stmt, context):
        if isinstance(stmt, LatticeOutSelectionAssignmentStmt_N):
            lhs = self._emit_lattice_access(stmt.lhs, 'out', context)
            rhs = self._emit_expr(stmt.rhs, context)
            self._emit(f'{lhs} = {rhs}')

        elif isinstance(stmt, VariableAssignmentStmt_N):
            lhs = self._emit_expr(stmt.lhs, context)
            rhs = self._emit_expr(stmt.rhs, context)
            self._emit(f'{lhs} = {rhs}')

        elif isinstance(stmt, VariableDeclarationStmt_N):
            # Declaration is at program level; emit initial value if present
            if stmt.initial_value is not None:
                fvname = self._vname(stmt.name.name)
                count = self._draw_broadcast_count(stmt)
                if count is not None:
                    # ``array[real, q] t = random();`` (the draw-sequencing
                    # pass): once per element, in index order (user
                    # manual, Numerical semantics: Random numbers); an
                    # array-section assignment would draw once and
                    # broadcast it.
                    self._emit(f'do gelb_df = 0, {count - 1}')
                    self._emit(f'  {fvname}(gelb_df) = gelb_random()')
                    self._emit('end do')
                    self._uses_random = True
                else:
                    value = self._emit_expr(stmt.initial_value, context)
                    self._emit(f'{fvname} = {value}')

        elif isinstance(stmt, ArraySelectionAssignmentStmt_N):
            lhs = self._emit_expr(stmt.lhs, context)
            rhs = self._emit_expr(stmt.rhs, context)
            self._emit(f'{lhs} = {rhs}')

        elif isinstance(stmt, ConstantDefinitionStmt_N):
            # Block-local constant: treat as assignment
            fvname = self._vname(stmt.name.name)
            value = self._emit_expr(stmt.value, context)
            self._emit(f'{fvname} = {value}')

        elif isinstance(stmt, DestructuringAssignmentStmt_N):
            self._emit_destructuring_call(stmt, context)

        else:
            raise NotImplementedError(
                f"Unsupported statement type: {type(stmt).__name__}"
            )

    def _emit_gauge_output(self, gauge_block):
        """Emit write statements for gauge output variables."""
        for decl in gauge_block.outputs:
            if isinstance(decl, VariableDeclarationStmt_N):
                fvname = self._vname(decl.name.name)
                vtype = decl.data_type.element_dtype
                fmt = _FORMAT_MAP.get(vtype, "'(A)'")
                self._emit(f'write(*, {fmt}) {fvname}')

    # ------------------------------------------------------------------
    # NetCDF output
    # ------------------------------------------------------------------

    def _gauge_output_vars(self, gauge_block):
        """Return list of (name, gelb_type) for gauge output variables."""
        result = []
        for decl in gauge_block.outputs:
            if isinstance(decl, VariableDeclarationStmt_N):
                result.append((decl.name.name, decl.data_type.element_dtype))
        return result

    def _emit_netcdf_declarations(self, gauge_block):
        """Emit declarations for NetCDF IDs and buffer arrays."""
        d = self._max_dim()
        output_vars = self._gauge_output_vars(gauge_block)

        self._emit('! NetCDF variables')
        self._emit(f"character(len=*), parameter :: gelb_nc_file = "
                   f"{fortran_string(self.output_filename)}")
        self._emit('integer :: gelb_ncid')

        # Dimension IDs
        dim_id_names = [f'gelb_dim_{_DIM_NAMES[i]}_id' for i in range(d)]
        dim_id_names.append('gelb_dim_time_id')
        self._emit(f'integer :: {", ".join(dim_id_names)}')

        # Coordinate variable IDs
        coord_var_names = [f'gelb_coord_{_DIM_NAMES[i]}_id' for i in range(d)]
        coord_var_names.append('gelb_coord_time_id')
        self._emit(f'integer :: {", ".join(coord_var_names)}')

        # Gauge output variable IDs
        for vname, _ in output_vars:
            self._emit(f'integer :: gelb_varid_{self._symbol_name(vname)}')

        # Buffer arrays for gauge output
        for vname, vtype in output_vars:
            ftype = 'integer(1)' if vtype == 'bool' else _TYPE_MAP[vtype]
            dims = ', '.join(f'0:{self._dim_size_fname(i)}-1' for i in range(d))
            self._emit(f'{ftype} :: gelb_buf_{self._symbol_name(vname)}({dims})')

    def _emit_netcdf_setup(self, gauge_block):
        """Emit NetCDF file creation, dimension/variable definitions."""
        d = self._max_dim()
        output_vars = self._gauge_output_vars(gauge_block)

        self._emit('! ========== NetCDF setup ==========')
        # Create file
        self._emit('call gelb_nc_check(nf90_create(gelb_nc_file, '
                   'ior(ior(NF90_CLOBBER, NF90_NETCDF4), NF90_SHARE), '
                   'gelb_ncid))')
        self._emit('')

        # Global attributes
        sim_desc = ''
        if hasattr(self.ast, 'simulation_description') and \
                self.ast.simulation_description is not None:
            sim_desc = description_text(self.ast.simulation_description)
        self._emit(f"call gelb_nc_check(nf90_put_att(gelb_ncid, NF90_GLOBAL, "
                   f"'description', {fortran_string(sim_desc)}))")
        self._emit('')

        # Define spatial dimensions
        for i in range(d):
            dim_name = _DIM_NAMES[i]           # unprefixed: for NetCDF strings & gelb_* names
            fdim_size = self._dim_size_fname(i)  # prefixed: Fortran identifier
            self._emit(f"call gelb_nc_check(nf90_def_dim(gelb_ncid, "
                       f"'{dim_name}', {fdim_size}, "
                       f"gelb_dim_{dim_name}_id))")

        # Unlimited time dimension
        self._emit("call gelb_nc_check(nf90_def_dim(gelb_ncid, 'time', "
                   "NF90_UNLIMITED, gelb_dim_time_id))")
        self._emit('')

        # Define coordinate variables
        for i in range(d):
            dim_name = _DIM_NAMES[i]
            self._emit(f"call gelb_nc_check(nf90_def_var(gelb_ncid, "
                       f"'{dim_name}', NF90_INT, "
                       f"gelb_dim_{dim_name}_id, "
                       f"gelb_coord_{dim_name}_id))")
        self._emit("call gelb_nc_check(nf90_def_var(gelb_ncid, 'time', "
                   "NF90_INT, gelb_dim_time_id, gelb_coord_time_id))")
        self._emit('')

        # Define gauge output variables (NetCDF names stay unprefixed)
        dim_ids = ', '.join(f'gelb_dim_{_DIM_NAMES[i]}_id' for i in range(d))
        dim_ids_with_time = dim_ids + ', gelb_dim_time_id'
        for vname, vtype in output_vars:
            nc_type = _NETCDF_TYPE_MAP.get(vtype, 'NF90_DOUBLE')
            self._emit(f"call gelb_nc_check(nf90_def_var(gelb_ncid, "
                       f"'{vname}', {nc_type}, "
                       f"(/{dim_ids_with_time}/), "
                       f"gelb_varid_{self._symbol_name(vname)}))")
        self._emit('')

        # End define mode
        self._emit('call gelb_nc_check(nf90_enddef(gelb_ncid))')
        self._emit('')

        # Write spatial coordinate values
        for i in range(d):
            dim_name = _DIM_NAMES[i]           # unprefixed: for gelb_* names
            fdim = self._symbol_name(dim_name)       # prefixed: Fortran loop variable
            fdim_size = self._dim_size_fname(i)
            self._emit(f'do {fdim} = 0, {fdim_size} - 1')
            self._indent += 1
            # The loop variable is integer(8), a GeLB `int`; the NetCDF
            # interfaces take default integers.
            self._emit(f'call gelb_nc_check(nf90_put_var(gelb_ncid, '
                       f'gelb_coord_{dim_name}_id, int({fdim}), '
                       f'start=(/int({fdim}) + 1/)))')
            self._indent -= 1
            self._emit('end do')

    def _emit_gauge_nan_init(self, gauge_block):
        """Initialize fields where a node class does not produce an output."""
        self._emit('! NaN-fill gauge buffers (masked cells stay NaN)')
        for decl in gauge_block.outputs:
            if isinstance(decl, VariableDeclarationStmt_N):
                vname = decl.name.name
                dtype = decl.data_type.element_dtype
                if dtype in ('real', 'real16', 'real32', 'real64'):
                    zero_lit = self._fortran_real(
                        0.0, self._literal_kind(decl.data_type))
                    value = f'ieee_value({zero_lit}, ieee_quiet_nan)'
                else:
                    value = '0'
                self._emit(f'gelb_buf_{self._symbol_name(vname)} = {value}')
        self._emit('')

    def _emit_gauge_fill_buffers(self, gauge_block):
        """Fill buffer arrays inside spatial loop (replaces write(*) for NetCDF)."""
        d = self._max_dim()
        parts = []
        for i in range(d):
            if i in self._coord_subst:
                parts.append(self._coord_subst[i])
            else:
                parts.append(self._symbol_name(_DIM_NAMES[i]))
        findices = ', '.join(parts)
        for decl in gauge_block.outputs:
            if isinstance(decl, VariableDeclarationStmt_N):
                vname = decl.name.name
                value = self._vname(vname)
                if decl.data_type.element_dtype == 'bool':
                    value = f'merge(1_1, 0_1, {value})'
                self._emit(f'gelb_buf_{self._symbol_name(vname)}({findices}) = {value}')

    def _emit_gauge_netcdf_write(self, gauge_block):
        """Write buffer arrays to NetCDF file (called after spatial loop)."""
        d = self._max_dim()
        output_vars = self._gauge_output_vars(gauge_block)
        self._emit('')

        # Record index: sequential write count (1-based, includes t=0 pre-loop)
        rec = 'gelb_write_count'

        # Write time coordinate (value is always the actual timestep)
        self._emit(f'call gelb_nc_check(nf90_put_var(gelb_ncid, '
                   f'gelb_coord_time_id, gelb_timestep, '
                   f'start=(/{rec}/)))')

        # Write each gauge variable
        start = ', '.join(['1'] * d) + f', {rec}'
        count = ', '.join(self._dim_size_fname(i) for i in range(d)) + ', 1'
        for vname, _ in output_vars:
            self._emit(f'call gelb_nc_check(nf90_put_var(gelb_ncid, '
                       f'gelb_varid_{self._symbol_name(vname)}, gelb_buf_{self._symbol_name(vname)}, '
                       f'start=(/{start}/), count=(/{count}/)))')

        # Sync for live monitoring
        self._emit('call gelb_nc_check(nf90_sync(gelb_ncid))')

    def _emit_nccheck_subroutine(self):
        """Emit a helper subroutine for NetCDF error checking."""
        self._emit('subroutine gelb_nc_check(status)')
        self._indent += 1
        self._emit('integer, intent(in) :: status')
        self._emit('if (status /= nf90_noerr) then')
        self._indent += 1
        self._emit("write(*, '(a,a)') 'NetCDF error: ', "
                   "trim(nf90_strerror(status))")
        self._emit('stop 1')
        self._indent -= 1
        self._emit('end if')
        self._indent -= 1
        self._emit('end subroutine gelb_nc_check')

    # ------------------------------------------------------------------
    # Swap subroutine
    # ------------------------------------------------------------------

    def _emit_swap_subroutine(self):
        self._emit('subroutine gelb_swap(a, b)')
        self._indent += 1
        self._emit('integer, intent(inout) :: a, b')
        self._emit('integer :: tmp')
        self._emit('tmp = a')
        self._emit('a = b')
        self._emit('b = tmp')
        self._indent -= 1
        self._emit('end subroutine gelb_swap')

    def _emit_gauge_halo_updates(self):
        """Refresh the ghost cells a gauge reads.  The time loop updates
        the halo before the dynamics only; gauges run after the swap and
        at t=0, so a gauge reading a neighbour across a periodic axis
        needs its own refresh.  Without stencil information every
        periodic lattice is refreshed."""
        if self._stencils is not None:
            wanted = self._stencils.gauge_halo_lattices()
        else:
            wanted = set(self._lattice_info)
        for lname, info in self._lattice_info.items():
            if lname in wanted and any(
                    self._is_periodic(info, i) for i in range(info['d'])):
                flname = self._symbol_name(lname)
                self._emit(f'call gelb_halo_update_{flname}({flname}_old)')

    def _emit_halo_update_subroutines(self):
        """Emit one ``gelb_halo_update_<lname>(buf)`` per lattice that
        has at least one periodic spatial axis.  Refreshes the periodic-
        wrap ghost cells of the given buffer.  Sweep order is x -> y -> z
        so that ghost cells filled by an earlier face copy propagate
        into the corner / edge cells that the next face copy reads.
        Wall axes are skipped -- their halo cells stay zero, and the
        inner-loop streaming clamp (max(0,...) / min(N-1,...)) keeps
        wall-cell reads in-bounds.

        Emitted as Fortran array-slice assignments -- gfortran lowers
        these to contiguous-block copies (effectively ``memcpy``) when
        the DF axis is the leading dimension, much faster than per-DF
        explicit loops.  Bodies access lattice arrays via host
        association from the enclosing program.
        """
        for lname, info in self._lattice_info.items():
            d = info['d']
            flname = self._symbol_name(lname)
            # Skip lattices with no periodic axes -- no halo update
            # needed (and the subroutine would be empty).
            if not any(self._is_periodic(info, i) for i in range(d)):
                continue
            self._emit(
                f'subroutine gelb_halo_update_{flname}(buf)')
            self._indent += 1
            self._emit('integer, intent(in) :: buf')
            # Per-axis face copies, swept x -> y -> z so corners/edges
            # propagate.
            for axis_idx in range(d):
                if not self._is_periodic(info, axis_idx):
                    continue
                self._emit_halo_face_copy(flname, info, axis_idx)
            self._indent -= 1
            self._emit(f'end subroutine gelb_halo_update_{flname}')

    def _emit_halo_face_copy(self, flname, info, axis_idx):
        """Emit two array-slice assignments for ``axis_idx``: low ghost
        <- high interior, and high ghost <- low interior.  Outer non-
        target axes use ``-1:N`` when they are periodic AND already
        swept (so corners propagate via this axis), else ``0:N-1``."""
        d = info['d']
        target_size = self._dim_size_fname(axis_idx)
        ax_label = ['x', 'y', 'z'][axis_idx]
        self._emit(f'! {ax_label}-faces (periodic axis {axis_idx})')

        # Build the per-spatial-axis slice expression for outer axes.
        # The DF axis is always ':' (full extent, leading dim -> unit
        # stride for gfortran's block-copy lowering).
        def _outer_slice(outer_ax):
            outer_size = self._dim_size_fname(outer_ax)
            if outer_ax < axis_idx and self._is_periodic(info, outer_ax):
                # Already swept and periodic -- include corners.
                return f'-1:{outer_size}'
            else:
                # Not yet swept (or not periodic) -- interior only.
                return f'0:{outer_size} - 1'

        def _subscript(pos_for_target):
            parts = [':']  # df axis: full extent
            for i in range(d):
                if i == axis_idx:
                    parts.append(pos_for_target)
                else:
                    parts.append(_outer_slice(i))
            parts.append('buf')
            return f'{flname}({", ".join(parts)})'

        # Low ghost <- high interior.  user_x = -1 <- user_x = N - 1.
        self._emit(
            f'{_subscript("-1")} = {_subscript(f"{target_size} - 1")}')
        # High ghost <- low interior.  user_x = N <- user_x = 0.
        self._emit(
            f'{_subscript(target_size)} = {_subscript("0")}')

    def _emit_random_declarations(self):
        """Emit declarations for PRNG seed variables."""
        self._emit('! PRNG seed variables')
        self._emit('integer :: gelb_seed_n, gelb_seed_i, gelb_clock_count')
        self._emit('integer, allocatable :: gelb_seed(:)')

    def _emit_random_seed_init(self):
        """Emit PRNG seed initialization.

        When ``self._random_seed`` is set, the seed array is filled with a
        fixed offset from the user-supplied integer so that two runs of
        the same program produce identical PRNG streams.  Otherwise, the
        seed is taken from the system clock as before.
        """
        if self._random_seed is not None:
            self._emit(
                f'! Seed the PRNG with the user-supplied fixed seed '
                f'({self._random_seed})')
            self._emit('call random_seed(size=gelb_seed_n)')
            self._emit('allocate(gelb_seed(gelb_seed_n))')
            self._emit(
                f'gelb_seed = {int(self._random_seed)} + '
                '[(gelb_seed_i, gelb_seed_i = 1, gelb_seed_n)]')
            self._emit('call random_seed(put=gelb_seed)')
        else:
            self._emit('! Seed the PRNG from the system clock')
            self._emit('call random_seed(size=gelb_seed_n)')
            self._emit('allocate(gelb_seed(gelb_seed_n))')
            self._emit('call system_clock(count=gelb_clock_count)')
            self._emit('gelb_seed = gelb_clock_count + [(gelb_seed_i, '
                       'gelb_seed_i = 1, gelb_seed_n)]')
            self._emit('call random_seed(put=gelb_seed)')

    def _emit_random_function(self):
        """Emit gelb_random() wrapper around Fortran's random_number subroutine."""
        self._emit('function gelb_random() result(r)')
        self._indent += 1
        self._emit(f"{_TYPE_MAP['real']} :: r")
        self._emit('call random_number(r)')
        self._indent -= 1
        self._emit('end function gelb_random')

    # ------------------------------------------------------------------
    # Expression emission
    # ------------------------------------------------------------------

    def _emit_expr(self, node, context='dynamic'):
        """Recursively translate an AST expression node to a Fortran string."""

        if isinstance(node, IntLiteral_N):
            return self._fortran_int(node.value)

        elif isinstance(node, RealLiteral_N):
            return self._fortran_real(node.value, self._literal_kind(node))

        elif isinstance(node, BoolLiteral_N):
            v = node.value
            if isinstance(v, bool):
                return '.true.' if v else '.false.'
            # GeLB stores booleans as lowercase strings
            return '.true.' if str(v).lower() == 'true' else '.false.'

        elif isinstance(node, StringLiteral_N):
            return fortran_string(description_text(node))

        elif isinstance(node, Identifier_N):
            # The implicit timestep symbol `t` resolves to the outer time-loop
            # iterator, not to a `_uname`-encoded user identifier. The tag is
            # stamped on the node by TypeInferenceVisitor.
            # `t` and `Nx`/`Ny`/`Nz` are GeLB `int`, int64, but their
            # Fortran carriers are default integers (the NetCDF
            # interfaces need them so): converted where a user
            # expression reads them.
            tag = getattr(node, 'symbol_tag', None)
            if tag == "implicit timestep variable":
                return 'int(gelb_timestep, 8)'
            if tag == "implicit dimension constant":
                return f'int({self._symbol_name(node.name)}, 8)'
            # Coordinate-literal substitution for elided dims.  When
            # _emit_spatial_loop_start has collapsed a single-point
            # dim into a literal, every reference to that coordinate
            # becomes the literal directly -- the do-loop for that dim
            # no longer exists, so the loop variable has no value.
            if node.name in ('x', 'y', 'z'):
                dim_idx = ('x', 'y', 'z').index(node.name)
                if dim_idx in self._coord_subst:
                    # The literal of a collapsed axis is the coordinate's
                    # value, an int64 wherever arithmetic reads it: a bare
                    # literal would be a default integer and
                    # `(x + 2147483647) + 1` would overflow, in a value
                    # or a subscript.  An index that is the coordinate
                    # alone stays bare (`_emit_index`).
                    return f'int({self._coord_subst[dim_idx]}, 8)'
            return self._vname(node.name)

        # --- binary arithmetic ---
        elif isinstance(node, Add_N):
            return self._binop(node, '+', context)
        elif isinstance(node, Sub_N):
            return self._binop(node, '-', context)
        elif isinstance(node, Mul_N):
            return self._binop(node, '*', context)
        elif isinstance(node, Div_N):
            return self._binop(node, '/', context)
        elif isinstance(node, Pow_N):
            return self._binop(node, '**', context)

        # --- unary ---
        elif isinstance(node, UnaryMinusExpr_N):
            return f'(-{self._emit_expr(node.value, context)})'
        elif isinstance(node, NotExpr_N):
            return f'(.not. {self._emit_expr(node.value, context)})'

        # --- comparison ---
        elif isinstance(node, Less_N):
            return self._binop(node, '<', context)
        elif isinstance(node, Greater_N):
            return self._binop(node, '>', context)
        elif isinstance(node, LessEqual_N):
            return self._binop(node, '<=', context)
        elif isinstance(node, GreaterEqual_N):
            return self._binop(node, '>=', context)
        elif isinstance(node, Equal_N):
            dtype = getattr(getattr(node.left, 'inferred_type', None), 'element_dtype', None)
            return self._binop(node, '.eqv.' if dtype == 'bool' else '==', context)
        elif isinstance(node, NotEqual_N):
            dtype = getattr(getattr(node.left, 'inferred_type', None), 'element_dtype', None)
            return self._binop(node, '.neqv.' if dtype == 'bool' else '/=', context)

        # --- logical ---
        elif isinstance(node, And_N):
            return self._binop(node, '.and.', context)
        elif isinstance(node, Or_N):
            return self._binop(node, '.or.', context)

        # --- lattice selections ---
        elif isinstance(node, RectSelOfLatticeInDFs_N):
            return self._emit_lattice_access(node, 'in', context)
        elif isinstance(node, RectSelOfLatticeOutDFs_N):
            return self._emit_lattice_access(node, 'out', context)

        # --- array selections ---
        elif isinstance(node, RectSelOfArrayElems_N):
            return self._emit_array_access(node, context)

        # --- type system nodes ---
        elif isinstance(node, TypePromotionNode_N):
            return self._emit_type_promotion(node, context)
        elif isinstance(node, BroadcastNode_N):
            return self._emit_expr(node.scalar_expr, context)

        # --- intrinsic functions ---
        elif isinstance(node, IntrinsicFunctionCall_N):
            return self._emit_intrinsic_call(node, context)

        # --- user-defined function calls ---
        elif isinstance(node, UserFunctionCall_N):
            return self._emit_user_function_call(node, context)

        # --- array literals ---
        elif isinstance(node, Array1DLiteral_N):
            elements = [self._emit_array_element(elem, node, context)
                        for elem in node.value.elements]
            return f'(/{", ".join(elements)}/)'

        elif isinstance(node, Array2DLiteral_N):
            return self._emit_2d_array_literal(node, context)

        else:
            raise NotImplementedError(
                f"Unsupported expression type: {type(node).__name__}"
            )

    def _emit_array_element(self, element, array, context):
        """Fortran constructors require every element to have the same kind."""
        target = getattr(getattr(array, 'inferred_type', None), 'element_dtype', None)
        expr = self._emit_expr(element, context)
        if target == 'bool':
            return f'logical({expr}, 1)'
        source = getattr(getattr(element, 'inferred_type', None), 'element_dtype', None)
        return self._emit_cast(expr, source, target)

    def _emit_2d_array_literal(self, node, context):
        """Emit a 2D array literal as reshape((/col-major/), (/r, c/))."""
        rows = node.value.elements  # List_N of Array1DLiteral_N
        nrows = len(rows)
        ncols = len(rows[0].value.elements)
        # Column-major order for Fortran reshape
        all_elements = []
        for col in range(ncols):
            for row in range(nrows):
                all_elements.append(
                    self._emit_array_element(rows[row].value.elements[col], node, context))
        joined = ', '.join(all_elements)
        return f'reshape((/{joined}/), (/{nrows}, {ncols}/))'

    def _binop(self, node, op, context):
        left = self._emit_expr(node.left, context)
        right = self._emit_expr(node.right, context)
        return f'({left} {op} {right})'

    # ------------------------------------------------------------------
    # Lattice / array access
    # ------------------------------------------------------------------

    def _emit_index(self, node, context):
        """A subscript expression.  A collapsed coordinate standing
        alone is its bare literal (``g_f(0, 0, g_f_new)``); inside
        arithmetic it keeps its int64 kind, as a loop coordinate
        does."""
        if (isinstance(node, Identifier_N) and node.name in _DIM_NAMES
                and _DIM_NAMES.index(node.name) in self._coord_subst):
            return self._coord_subst[_DIM_NAMES.index(node.name)]
        return self._emit_expr(node, context)

    def _emit_lattice_access(self, node, direction, context):
        """Translate a lattice selection to Fortran array indexing.

        Array layout: f(df_index, spatial..., buffer)
        Periodic-axis offset reads of +-1 land in the one-cell hidden
        halo (filled by gelb_halo_update_<lname> at the start of each
        timestep), so no modulo wrap is needed for them; a larger
        offset is wrapped with modulo().  A *write* at any non-zero
        offset along a periodic axis wraps too: a ghost cell is never
        copied back, so a push must land in the interior.  Wall axes use
        the existing clamp
        in ``_emit_streaming_dfs`` for upstream reads; non-streaming
        direct reads at non-periodic axes are passed through as-is
        (callers stay within bounds via the bbox decomposition).
        """
        lattice_name = node.lattice_name.name
        flname = self._symbol_name(lattice_name)
        info = self._lattice_info[lattice_name]
        n_ranges = len(node.element_ranges)

        # Last range is the DF index; preceding ranges are spatial
        df_range = node.element_ranges[n_ranges - 1]
        spatial_ranges = [node.element_ranges[i] for i in range(n_ranges - 1)]

        parts = []
        # DF index (first dimension)
        parts.append(self._emit_range(df_range, context))
        # Spatial dimensions: the hidden halo holds the periodic wrap one
        # cell deep, so the user-coord expression passes through
        # directly unless it reaches further along a periodic axis.
        halo_reach = 1 if direction == 'in' else 0
        for i, sr in enumerate(spatial_ranges):
            idx = self._emit_range(sr, context)
            form = affine_index(sr.low) if sr.low is not None else None
            if (form is not None and abs(form[1]) > halo_reach
                    and self._is_periodic(info, i)):
                idx = f'modulo({idx}, {self._dim_size_fname(i)})'
            parts.append(idx)
        # Ping-pong buffer (last dimension)
        if direction == 'in':
            parts.append(f'{flname}_old')
        else:  # 'out'
            if context == 'initializer':
                parts.append(f'{flname}_old')
            elif context == 'initializer_copy':
                parts.append(f'{flname}_new')
            else:
                parts.append(f'{flname}_new')

        return f'{flname}({", ".join(parts)})'

    def _is_periodic(self, lattice_info, dim_index):
        """Check if a lattice dimension is periodic."""
        periodic = lattice_info['periodic']
        # 1D: BoolLiteral_N.value is a string ("true"/"false")
        if isinstance(periodic, str):
            return periodic.lower() == 'true'
        if isinstance(periodic, bool):
            return periodic
        # 2D+: List_N with BoolLiteral_N elements
        if hasattr(periodic, 'elements'):
            el = periodic.elements[dim_index]
            if hasattr(el, 'value'):
                v = el.value
                return v is True or str(v).lower() == 'true'
        return False

    def _has_offset(self, range_node):
        """Check if a range is a simple coordinate (x) or has an offset (x+1)."""
        # If range is just an Identifier, no offset needed
        from gelb.gelb_ast.ASTNodes import Identifier_N
        return not isinstance(range_node.low, Identifier_N)

    def _emit_array_access(self, node, context):
        farray_name = self._vname(node.array_name.name)
        indices = [self._emit_range(r, context) for r in node.element_ranges]
        return f'{farray_name}({", ".join(indices)})'

    def _emit_range(self, range_node, context):
        low = self._emit_index(range_node.low, context)
        high = self._emit_index(range_node.high, context)
        if low == high:
            return low  # single element
        return f'{low}:{high}'  # slice

    # ------------------------------------------------------------------
    # Type promotion
    # ------------------------------------------------------------------

    def _emit_type_promotion(self, node, context):
        expr = self._emit_expr(node.expr, context)
        target = node.target_type.element_dtype
        # Determine source type for special-case handling
        source = None
        if hasattr(node.expr, 'inferred_type') and hasattr(node.expr.inferred_type, 'element_dtype'):
            source = node.expr.inferred_type.element_dtype
        return self._emit_cast(expr, source, target)

    def _emit_cast(self, expr, source, target):
        """Emit a Fortran type-conversion expression.

        Used by both implicit type promotions (TypePromotionNode_N) and
        the explicit cast intrinsics (int(x), real(x), int8(x), ...).
        ``source`` is the source GeLB type-name (str) or None if unknown;
        ``target`` is the target GeLB type-name (str).
        """
        if target in ('real', 'real64'):
            if source == 'bool':
                return f'dble(merge(1, 0, {expr}))'
            return f'dble({expr})'
        elif target == 'real32':
            if source == 'bool':
                return f'real(merge(1, 0, {expr}))'
            return f'real({expr})'
        elif target == 'real16':
            if source == 'bool':
                return f'real(merge(1, 0, {expr}), 2)'
            return f'real({expr}, 2)'
        elif target in ('int', 'int64'):
            # Fortran int() cannot convert logical->integer; use merge()
            if source == 'bool':
                return f'merge(1_8, 0_8, {expr})'
            return f'int({expr}, 8)'
        elif target == 'int32':
            if source == 'bool':
                return f'merge(1_4, 0_4, {expr})'
            return f'int({expr}, 4)'
        elif target == 'int16':
            if source == 'bool':
                return f'merge(1_2, 0_2, {expr})'
            return f'int({expr}, 2)'
        elif target == 'int8':
            if source == 'bool':
                return f'merge(1_1, 0_1, {expr})'
            return f'int({expr}, 1)'
        return expr

    # ------------------------------------------------------------------
    # Intrinsic functions
    # ------------------------------------------------------------------

    def _emit_intrinsic_call(self, node, context):
        args = [self._emit_expr(arg, context) for arg in node.arguments]
        name = node.function_name
        if name == 'sum':
            return f'sum({", ".join(args)})'
        elif name == 'dot_prod':
            return f'dot_product({", ".join(args)})'
        elif name in ('min', 'max') and self._is_real_kind(node):
            # IEEE 754-2019 minimum / maximum (user manual, Numerical
            # semantics: Types and promotion); the arguments have the
            # call's width after the frontend's conversions.
            dtype = node.inferred_type.element_dtype
            suffix = 'r4' if dtype == 'real32' else 'r8'
            return f'gelb_{name}_{suffix}({", ".join(args)})'
        elif name in ('sin', 'cos', 'sqrt', 'exp', 'abs', 'log', 'tan', 'tanh',
                      'min', 'max', 'mod', 'atan2'):
            return f'{name}({", ".join(args)})'
        elif name == 'random':
            self._uses_random = True
            return 'gelb_random()'
        elif name in ('matmul', 'transpose'):
            return f'{name}({", ".join(args)})'
        elif name in ('upstream_dfs', 'bounce_back_dfs'):
            return self._emit_streaming_dfs(node, context)
        elif name in CAST_INTRINSIC_NAMES:
            # Type-cast intrinsic: int(x), real(x), int8(x), ...
            # Reuses _emit_cast which also serves implicit promotions.
            arg_node = node.arguments.elements[0]
            source = None
            if (hasattr(arg_node, 'inferred_type')
                    and hasattr(arg_node.inferred_type, 'element_dtype')):
                source = arg_node.inferred_type.element_dtype
            return self._emit_cast(args[0], source, name)
        elif name in ('inverse', 'determinant'):
            raise NotImplementedError(
                f"{name}() is a compile-time-only intrinsic and should have "
                f"been evaluated during constant folding. "
                f"Ensure its argument is a compile-time constant."
            )
        else:
            raise NotImplementedError(f"Unsupported intrinsic: {name}")

    def _emit_streaming_dfs(self, node, context):
        """Emit upstream_dfs or bounce_back_dfs as a Fortran array constructor.

        upstream_dfs(f, x, y, {EX, EY}):
          (/ g_f(0, g_x, g_y, g_f_old), g_f(1, mod(g_x-1+g_Nx,g_Nx), ...) /)

        bounce_back_dfs(f, x, y, {EX, EY}):
          (/ g_f(opp[0], g_x + EX[0], g_y + EY[0], g_f_old), ... /)
        """
        args = node.arguments.elements

        # Parse arguments: lattice_name, coord_1..coord_d, {vel_1..vel_d}
        lattice_name = args[0].name  # Identifier_N (unprefixed for lookup)
        flname = self._symbol_name(lattice_name)
        vel_set = args[-1]           # Array1DLiteral_N: {EX, EY, ...}
        coord_args = args[1:-1]      # spatial coordinates (x, y, ...)

        info = self._lattice_info[lattice_name]
        d = info['d']
        q = info['q']

        # Extract coordinate expressions (auto-prefixed via _emit_expr);
        # they become subscripts, so a collapsed coordinate standing
        # alone stays bare.
        coords = [self._emit_index(c, context) for c in coord_args]

        # Extract velocity vectors (constant-folded to literal arrays)
        vel_arrays = []
        if isinstance(vel_set, Array1DLiteral_N):
            # 2D/3D: {EX, EY} or {EX, EY, EZ}
            for vel_node in vel_set.value.elements:
                vel_arrays.append(self._extract_constant_array(vel_node))
        else:
            # 1D: single velocity array passed directly (no braces)
            vel_arrays.append(self._extract_constant_array(vel_set))

        # Determine buffer variable
        buffer_var = self._current_buffer_var(lattice_name, 'in', context)

        if node.function_name == 'bounce_back_dfs':
            opp_map = self._compute_opposite_mapping(vel_arrays, q)
            elements = []
            for i in range(q):
                shifted, guards = [], []
                for axis, coord in enumerate(coords):
                    off = int(vel_arrays[axis][i])
                    target = f'({coord} + ({off}))' if off else coord
                    size = self._dim_size_fname(axis)
                    if self._is_periodic(info, axis):
                        target = f'modulo({target}, {size})' if off else coord
                    elif off:
                        guards.append(f'({target} >= 0 .and. {target} < {size})')
                    shifted.append(target)
                # Select safe subscripts, not loads: Fortran MERGE may
                # evaluate both value arguments, including an invalid load.
                if guards:
                    valid = ' .and. '.join(guards)
                    shifted = [f'merge({target}, {coord}, {valid})'
                               for target, coord in zip(shifted, coords)]
                parts = [str(opp_map[i]), *shifted, buffer_var]
                elements.append(f'{flname}({", ".join(parts)})')
        else:
            # upstream_dfs: read from upstream neighbours.
            #
            # Boundary-aware clamping: for a non-periodic dimension,
            # if the current node class is painted at the side that
            # this DF's streaming direction would read from, wrap the
            # index in max(0, ...) or min(N-1, ...) so that:
            #   - gfortran's compile-time bounds check is satisfied
            #     (single-point 1D loops would otherwise trip a
            #     "out of bounds (-1 < 0)" warning),
            #   - the runtime read is well-defined (the read at a
            #     boundary cell clamps to a valid neighbour and is
            #     then typically overwritten by the user's BC formula).
            # For interior node classes the clamp is omitted, so the
            # fast path emission for bulk reads is unchanged.
            nc_sides = self._nc_boundary_dims.get(self._current_nc, {})
            elements = []
            for i in range(q):
                parts = [str(i)]
                for dim_idx in range(d):
                    offset = int(vel_arrays[dim_idx][i])
                    coord = coords[dim_idx]
                    if offset == 0:
                        parts.append(coord)
                    else:
                        # Build offset expression: "g_x - 1" or "g_x + 1"
                        # Streaming direction +offset reads from `coord - offset`
                        # (upstream of a particle moving toward +offset), so a
                        # positive velocity offset reads DOWN in index, i.e.
                        # toward the LOW boundary.
                        if offset > 0:
                            offset_expr = f'{coord} - {offset}'
                        else:
                            offset_expr = f'{coord} + {-offset}'
                        if self._is_periodic(info, dim_idx):
                            # Hidden halo: periodic wrap is pre-staged
                            # by gelb_halo_update_<lname>, one cell
                            # deep, so a +-1 offset reads directly; a
                            # larger one wraps with modulo().
                            if abs(offset) > 1:
                                fsize = self._dim_size_fname(dim_idx)
                                parts.append(
                                    f'modulo({offset_expr}, {fsize})')
                            else:
                                parts.append(f'({offset_expr})')
                        else:
                            sides = nc_sides.get(dim_idx, set())
                            if offset > 0 and 'low' in sides:
                                # Reading below -- clamp at 0
                                parts.append(f'max(0, {offset_expr})')
                            elif offset < 0 and 'high' in sides:
                                # Reading above -- clamp at N-1
                                fsize = self._dim_size_fname(dim_idx)
                                parts.append(
                                    f'min({fsize} - 1, {offset_expr})')
                            else:
                                parts.append(f'({offset_expr})')
                parts.append(buffer_var)
                elements.append(f'{flname}({", ".join(parts)})')

        # Emit as Fortran array constructor -- the post-processing
        # formatter will handle line splitting if needed.
        return f'(/{", ".join(elements)}/)'

    def _extract_constant_array(self, node):
        """Extract numeric values from a constant-folded array node."""
        if isinstance(node, TypePromotionNode_N):
            return self._extract_constant_array(node.expr)
        if isinstance(node, Identifier_N):
            # Look up the constant definition in global constants
            for stmt in self.ast.global_constants.stmts:
                if isinstance(stmt, ConstantDefinitionStmt_N):
                    if stmt.name.name == node.name:
                        return self._extract_constant_array(stmt.value)
            raise ValueError(f"Cannot resolve constant array '{node.name}'")
        if isinstance(node, Array1DLiteral_N):
            return [self._extract_scalar_value(e)
                    for e in node.value.elements]
        raise ValueError(
            f"Cannot extract constant array from {type(node).__name__}")

    def _extract_scalar_value(self, node):
        """Extract a numeric value from a constant-folded scalar node."""
        if isinstance(node, TypePromotionNode_N):
            return self._extract_scalar_value(node.expr)
        if isinstance(node, IntLiteral_N):
            return node.value
        if isinstance(node, RealLiteral_N):
            return node.value
        if isinstance(node, UnaryMinusExpr_N):
            return -self._extract_scalar_value(node.value)
        raise ValueError(
            f"Cannot extract scalar from {type(node).__name__}")

    def _compute_opposite_mapping(self, vel_arrays, q):
        """Compute opposite DF index mapping from velocity vectors.

        For each i, find j such that vel_d[j] = -vel_d[i] for all d.
        """
        nd = len(vel_arrays)
        opp = [None] * q
        for i in range(q):
            vi = tuple(vel_arrays[dim][i] for dim in range(nd))
            neg_vi = tuple(-v for v in vi)
            for j in range(q):
                vj = tuple(vel_arrays[dim][j] for dim in range(nd))
                if vj == neg_vi:
                    opp[i] = j
                    break
            if opp[i] is None:
                raise ValueError(
                    f"No opposite DF found for DF {i} with velocity {vi}")
        return opp

    def _current_buffer_var(self, lattice_name, direction, context):
        """Get the Fortran buffer variable for lattice read/write."""
        flname = self._symbol_name(lattice_name)
        return f'{flname}_old' if direction == 'in' else f'{flname}_new'

    # ------------------------------------------------------------------
    # User-defined functions
    # ------------------------------------------------------------------

    def _emit_user_function_call(self, node, context):
        """Emit a user-defined function call expression (single-output only).

        Multi-output calls must go through _emit_destructuring_call as
        statements, not expressions.
        """
        ffunc_name = self._symbol_name(node.function_name.name)

        # Check if any argument is a multi-output UserFunctionCall_N
        # that needs to be expanded into a subroutine call + temp vars
        expanded_args = []
        for i, arg in enumerate(node.arguments):
            if isinstance(arg, UserFunctionCall_N) and hasattr(arg, 'function_block'):
                # Multi-output inner call -- expand into temp vars
                inner_func = arg.function_block
                finner_name = self._symbol_name(arg.function_name.name)
                inner_args = [self._emit_expr(a, context) for a in arg.arguments]
                temps = []
                for out in inner_func.outputs.elements:
                    tname = f'gelb_tmp_{out.name.name}'
                    temps.append(tname)
                self._emit(f'call {finner_name}({", ".join(inner_args + temps)})')
                expanded_args.extend(temps)
            else:
                expanded_args.append(self._emit_expr(arg, context))

        return f'{ffunc_name}({", ".join(expanded_args)})'

    def _emit_destructuring_call(self, stmt, context):
        """Emit a destructuring assignment.

        Two RHS shapes are supported:

        1. ``UserFunctionCall_N`` -- multi-output function call.
           Emitted as: ``call g_Func(args..., g_a, g_b, g_c)``.

        2. Any 1D array expression (literal, variable, slice).
           Emitted as a series of element-wise assignments
           (with a temp for non-literal expressions to avoid
           recomputation).
        """
        rhs = stmt.rhs
        if isinstance(rhs, UserFunctionCall_N):
            self._emit_destructuring_function_call(stmt, context)
        else:
            self._emit_destructuring_array(stmt, context)

    def _emit_destructuring_function_call(self, stmt, context):
        """Emit a multi-output function-call destructuring.

        Emitted as: ``call g_Func(args..., g_a, g_b, g_c)``
        """
        rhs = stmt.rhs
        ffunc_name = self._symbol_name(rhs.function_name.name)

        # Handle chained multi-output calls in arguments
        in_args = []
        for arg in rhs.arguments:
            if isinstance(arg, UserFunctionCall_N) and hasattr(arg, 'function_block'):
                # Multi-output inner call -- expand
                inner_func = arg.function_block
                finner_name = self._symbol_name(arg.function_name.name)
                inner_args = [self._emit_expr(a, context) for a in arg.arguments]
                temps = []
                for out in inner_func.outputs.elements:
                    tname = f'gelb_tmp_{out.name.name}'
                    temps.append(tname)
                self._emit(f'call {finner_name}({", ".join(inner_args + temps)})')
                in_args.extend(temps)
            else:
                in_args.append(self._emit_expr(arg, context))

        out_args = [self._vname(t.name) for t in stmt.targets]
        self._emit(f'call {ffunc_name}({", ".join(in_args + out_args)})')

    def _emit_destructuring_array(self, stmt, context):
        """Emit a 1D-array destructuring.

        For an array literal RHS, each element is assigned directly to
        the corresponding target -- no temp needed.

        For a non-literal RHS (variable, slice, expression), we first
        copy the result to a temporary array to avoid recomputing the
        expression for each target, then read element-wise from the temp.
        """
        rhs = stmt.rhs
        targets = stmt.targets

        if isinstance(rhs, Array1DLiteral_N):
            # Direct element-wise assignment -- no temp.
            for target, elem in zip(targets, rhs.value.elements):
                ftarget = self._vname(target.name)
                value_str = self._emit_expr(elem, context)
                self._emit(f'{ftarget} = {value_str}')
            return

        # Non-literal RHS: emit a temp + per-target reads.
        # The temp is declared inline (Fortran 2008 supports block-local
        # auto arrays -- but for portability we use a unique name and
        # rely on the existing variable-declaration machinery).  Since
        # the temp is short-lived and only used within this snippet, we
        # use Fortran's "associate" construct to scope it locally.
        rhs_str = self._emit_expr(rhs, context)
        n = len(targets)
        # Use an associate block: associate (gelb_destr_tmp => <expr>) ... end associate
        self._emit(f'associate (gelb_destr_tmp => {rhs_str})')
        self._indent += 1
        for i, target in enumerate(targets):
            ftarget = self._vname(target.name)
            # Fortran array indices are 1-based by default; the
            # associated expression preserves its original lower bound,
            # which for our generated arrays is typically 1.  We use the
            # explicit ``lbound`` to be safe across slice expressions.
            self._emit(
                f'{ftarget} = gelb_destr_tmp(lbound(gelb_destr_tmp, 1) + {i})')
        self._indent -= 1
        self._emit('end associate')

    def _emit_user_function_definitions(self):
        """Emit Fortran function/subroutine definitions for all user-defined
        function blocks in the AST.
        """
        if self.ast.functions is None:
            return

        for func in self.ast.functions:
            self._emit('')
            inputs = func.inputs.elements
            outputs = func.outputs.elements

            if len(outputs) == 1:
                self._emit_fortran_function(func, inputs, outputs[0])
            else:
                self._emit_fortran_subroutine(func, inputs, outputs)

    def _user_function_attr_prefix(self):
        """Fortran attribute prefix for user-defined functions / subroutines.

        Empty on host-only CPU backends.  CUDA-style backends override this
        to emit ``attributes(device)`` so the same function is callable
        from device kernels.
        """
        return ''

    def _emit_fortran_function(self, func, inputs, output):
        """Emit a single-output user function as a Fortran function."""
        fname = self._symbol_name(func.name.name)
        fparam_names = [self._symbol_name(p.name.name) for p in inputs]
        fresult_name = self._symbol_name(output.name.name)

        prefix = self._user_function_attr_prefix()
        self._emit(f'{prefix}function {fname}'
                   f'({", ".join(fparam_names)}) result({fresult_name})')
        self._indent += 1
        self._emit('implicit none')

        # Declare input parameters
        for param in inputs:
            ftype = self._fortran_type_from_decl(param)
            self._emit(f'{ftype}, intent(in) :: {self._symbol_name(param.name.name)}')

        # Declare result variable
        ftype = self._fortran_type_from_decl(output)
        self._emit(f'{ftype} :: {fresult_name}')

        # Declare local variables
        self._emit_function_local_vars(func, inputs, [output])

        self._emit('')

        # Emit body statements
        for stmt in func.stmts:
            self._emit_statement(stmt, 'function')

        self._indent -= 1
        self._emit(f'end function {fname}')

    def _emit_fortran_subroutine(self, func, inputs, outputs):
        """Emit a multi-output user function as a Fortran subroutine."""
        fname = self._symbol_name(func.name.name)
        fparam_names = [self._symbol_name(p.name.name) for p in inputs]
        fout_names = [self._symbol_name(o.name.name) for o in outputs]
        all_params = fparam_names + fout_names

        prefix = self._user_function_attr_prefix()
        self._emit(f'{prefix}subroutine {fname}({", ".join(all_params)})')
        self._indent += 1
        self._emit('implicit none')

        # Declare input parameters
        for param in inputs:
            ftype = self._fortran_type_from_decl(param)
            self._emit(f'{ftype}, intent(in) :: {self._symbol_name(param.name.name)}')

        # Declare output parameters
        for param in outputs:
            ftype = self._fortran_type_from_decl(param)
            self._emit(f'{ftype}, intent(out) :: {self._symbol_name(param.name.name)}')

        # Declare local variables
        self._emit_function_local_vars(func, inputs, outputs)

        self._emit('')

        # Emit body statements
        for stmt in func.stmts:
            self._emit_statement(stmt, 'function')

        self._indent -= 1
        self._emit(f'end subroutine {fname}')

    def _emit_function_local_vars(self, func, inputs, outputs):
        """Emit declarations for local variables in a function body."""
        param_names = set(p.name.name for p in inputs)
        param_names.update(o.name.name for o in outputs)

        for stmt in func.stmts:
            if isinstance(stmt, VariableDeclarationStmt_N):
                if stmt.name.name not in param_names:
                    ftype = self._fortran_type_from_decl(stmt)
                    self._emit(f'{ftype} :: {self._symbol_name(stmt.name.name)}')
            elif isinstance(stmt, ConstantDefinitionStmt_N):
                if stmt.name.name not in param_names:
                    dtype = stmt.data_type
                    ftype = self._gelb_type_to_fortran(dtype)
                    self._emit(f'{ftype} :: {self._symbol_name(stmt.name.name)}')

    def _fortran_type_from_decl(self, decl):
        """Get the Fortran type string from a VariableDeclarationStmt_N."""
        dtype = decl.data_type
        return self._gelb_type_to_fortran(dtype)

    def _gelb_type_to_fortran(self, dtype):
        """Convert a GeLB data type to a Fortran type string."""
        if isinstance(dtype, ArrayDataType_N):
            base = _TYPE_MAP.get(dtype.element_dtype, 'double precision')
            # Get array shape
            if isinstance(dtype.shape, List_N) and len(dtype.shape.elements) == 0:
                return base  # scalar
            elif isinstance(dtype.shape, IntLiteral_N):
                return f'{base}, dimension({dtype.shape.value})'
            elif isinstance(dtype.shape, Array1DLiteral_N):
                dims = ', '.join(
                    str(e.value) for e in dtype.shape.value.elements)
                return f'{base}, dimension({dims})'
            elif isinstance(dtype.shape, List_N):
                dims = ', '.join(str(e.value) for e in dtype.shape.elements)
                return f'{base}, dimension({dims})'
            return base
        elif isinstance(dtype, ScalarDataType_N):
            return _TYPE_MAP.get(dtype.name, 'double precision')
        else:
            # Plain string data type name
            return _TYPE_MAP.get(str(dtype), 'double precision')

    # ------------------------------------------------------------------
    # Fortran literal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fortran_real(value, kind='real'):
        """Convert a Python float to a Fortran real literal with appropriate kind.

        kind='real' or 'real64' -> double precision (d-exponent),
        kind='real32'           -> single precision (e-exponent),
        kind='real16'           -> half precision (_2 kind parameter).
        """
        if not math.isfinite(float(value)):
            zero = {'real16': '0.0_2', 'real32': '0.0_4'}.get(kind, '0.0_8')
            ieee_class = ('ieee_quiet_nan' if math.isnan(float(value)) else
                          'ieee_positive_inf' if float(value) > 0 else 'ieee_negative_inf')
            return f'ieee_value({zero}, {ieee_class})'
        s = repr(value)
        if kind in ('real', 'real64'):
            if 'e' in s or 'E' in s:
                return s.replace('e', 'd').replace('E', 'd')
            if '.' in s:
                return s + 'd0'
            return s + '.0d0'
        elif kind == 'real32':
            if 'e' in s or 'E' in s:
                return s
            if '.' in s:
                return s + 'e0'
            return s + '.0e0'
        elif kind == 'real16':
            if '.' not in s:
                s = s + '.0'
            return s + '_2'
        else:
            if '.' in s:
                return s + 'd0'
            return s + '.0d0'
