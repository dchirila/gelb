"""NetCDF and gauge output emission for cpu_highway.

NetCDF file setup, the per-interval gauge write, gauge buffer fill
and NaN-init for masked cells, and the MLUPS report.
"""

from __future__ import annotations

from gelb.backends.string_literals import cpp_string, description_text

from gelb.backends.highway.common import (
    _NETCDF_TYPE_MAP,
    _uname,
)

from gelb.gelb_ast.ASTNodes import (
    GaugeBlock_N,
    VariableDeclarationStmt_N,
)


class OutputEmitMixin:
    """Mixin: see module docstring.  Assembled into
    ``HighwayCodeGenerator`` (stage3_backend_cpu_highway).
    """

    def _gauge_buffer_cpp_type(self, decl):
        """NetCDF Boolean fields are signed bytes containing zero or one."""
        cpp_type = self._decl_cpp_type(decl)
        return 'int8_t' if cpp_type == 'bool' else cpp_type

    def _emit_netcdf_setup(self) -> None:
        gauge = self._gauge_output_layout()
        if gauge is None:
            self._emit('// (no gauge -- skipping NetCDF setup)')
            return
        nc_path = self.output_filename
        d = self._d
        axes = [self._axis(i) for i in range(d)]
        # NetCDF C API expects dim ids in slowest-to-fastest order,
        # so the spatial dims come in the reverse of (x, y, z).
        # i.e. for 2-D: (time, y, x), for 1-D: (time, x).
        rev_axes = list(reversed(axes))
        slab_rank = d + 1  # +1 for time
        self._emit('// NetCDF setup')
        self._emit('int gelb_ncid;')
        dim_ids = ', '.join(f'gelb_dim_{a}_id' for a in axes) + ', gelb_dim_time_id'
        coord_ids = ', '.join(f'gelb_coord_{a}_id' for a in axes) + ', gelb_coord_time_id'
        self._emit(f'int {dim_ids};')
        self._emit(f'int {coord_ids};')
        # Buffer dim ordering matches NetCDF in-memory layout: x fastest.
        # 1-D: buf[nx]; 2-D: buf[ny][nx] (y outer, x inner).
        buf_dims = ''.join(f'[g__n{a}]' for a in rev_axes)
        for decl in gauge.outputs:
            if isinstance(decl, VariableDeclarationStmt_N):
                vname = decl.name.name
                self._emit(f'int gelb_varid_{vname};')
                # alignas(64) keeps the buffer's first byte 64-byte
                # aligned for AVX-512 ``Vec8d.store_a`` writes when
                # the SIMD gauge path stores 8 contiguous cells at a
                # time.  The current emit uses unaligned ``store()``
                # so this is a hint for the compiler / branch-future
                # tile-aligned path; harmless when not used.
                self._emit(f'alignas(64) static {self._gauge_buffer_cpp_type(decl)} '
                           f'gelb_buf_{vname}{buf_dims};')
        self._emit('')
        self._emit(f'GELB_NC(nc_create({cpp_string(nc_path)}, '
                   f'NC_CLOBBER | NC_NETCDF4, &gelb_ncid));')
        if self.ast.simulation_description is not None:
            desc = description_text(self.ast.simulation_description)
            self._emit(f'GELB_NC(nc_put_att_text(gelb_ncid, NC_GLOBAL, '
                       f'"description", {len(desc.encode("utf-8"))}, {cpp_string(desc)}));')
        for a in axes:
            self._emit(f'GELB_NC(nc_def_dim(gelb_ncid, "{a}", g__n{a}, '
                       f'&gelb_dim_{a}_id));')
        self._emit('GELB_NC(nc_def_dim(gelb_ncid, "time", NC_UNLIMITED, '
                   '&gelb_dim_time_id));')
        for a in axes:
            self._emit(f'GELB_NC(nc_def_var(gelb_ncid, "{a}", NC_INT, 1, '
                       f'&gelb_dim_{a}_id, &gelb_coord_{a}_id));')
        self._emit('GELB_NC(nc_def_var(gelb_ncid, "time", NC_INT, 1, '
                   '&gelb_dim_time_id, &gelb_coord_time_id));')
        # Var dim list: [time, y, x] for 2-D; [time, x] for 1-D.
        var_dim_list = ['gelb_dim_time_id'] + [f'gelb_dim_{a}_id'
                                               for a in rev_axes]
        for decl in gauge.outputs:
            if isinstance(decl, VariableDeclarationStmt_N):
                vname = decl.name.name
                dt = decl.data_type
                elem = (getattr(dt, 'element_dtype', None)
                        or getattr(dt, 'name', 'real'))
                nc_type = _NETCDF_TYPE_MAP.get(elem, 'NC_DOUBLE')
                self._emit(f'{{ int dims[{slab_rank}] = '
                           f'{{ {", ".join(var_dim_list)} }};')
                self._emit(f'  GELB_NC(nc_def_var(gelb_ncid, "{vname}", '
                           f'{nc_type}, {slab_rank}, dims, '
                           f'&gelb_varid_{vname})); }}')
        self._emit('GELB_NC(nc_enddef(gelb_ncid));')
        self._emit('// Coordinate variables')
        for a in axes:
            self._emit(f'for (int g_{a} = 0; g_{a} < g__n{a}; ++g_{a}) {{')
            self._indent += 1
            self._emit(f'size_t idx = static_cast<size_t>(g_{a});')
            self._emit(f'GELB_NC(nc_put_var1_int(gelb_ncid, '
                       f'gelb_coord_{a}_id, &idx, &g_{a}));')
            self._indent -= 1
            self._emit('}')

    def _emit_gauge_nan_init(self, gauge):
        """Initialize outputs absent from some node classes before a sweep.

        Real fields use NaN; integer fields use zero, as for masked cells.
        """
        if not gauge.partial:
            return
        self._emit('// NaN-fill gauge buffers (masked cells stay NaN)')
        for decl in gauge.outputs:
            if isinstance(decl, VariableDeclarationStmt_N):
                vname = decl.name.name
                # std::numeric_limits<T>::quiet_NaN() -- pulled in via
                # <limits>.  Most common gauge dtype is double; for
                # integer types use zero.
                cpp_type = self._gauge_buffer_cpp_type(decl)
                value = (f'std::numeric_limits<{cpp_type}>::quiet_NaN()'
                         if cpp_type in ('float', 'double') else '0')
                # Total element count = product of grid sizes.
                total = ' * '.join(f'g__n{self._axis(i)}'
                                   for i in range(self._d))
                self._emit(
                    f'std::fill_n(reinterpret_cast<{cpp_type}*>'
                    f'(gelb_buf_{vname}), {total}, '
                    f'{value});')

    def _emit_gauge_at_t0(self) -> None:
        gauge = self._gauge_output_layout()
        if not self._emit_gauge_at_t0_preamble(gauge):
            return
        self._emit_gauge_halo_updates()
        self._emit_gauge_nan_init(gauge)
        for nc_name, info, rect_info, is_synth in \
                self._iter_gauge_dispatch_rects():
            gblock = self._find_block(self.ast.gauges, info.gauge)
            rect_suffix = (f' [rect bbox={rect_info.bbox}]'
                           if is_synth else '')
            if self._block_simd_eligible(gblock, rect_info):
                self._emit(f'// Gauge: {info.gauge} ({nc_name}) '
                           f'-- SIMD{rect_suffix}')
                self._emit_block_simd(gblock, rect_info,
                                      context='gauge')
            else:
                self._emit(f'// Gauge: {info.gauge} '
                           f'({nc_name}){rect_suffix}')
                self._emit_spatial_loop_open(rect_info)
                self._emit_block_body(gblock, context='gauge')
                self._emit_spatial_loop_close()
        self._emit_gauge_netcdf_write(gauge)

    def _emit_gauge_at_t0_preamble(self, gauge) -> bool:
        if gauge is None:
            return False
        self._emit('// ========== Gauge at t=0 ==========')
        self._emit('gelb_timestep = 0;')
        self._emit('gelb_write_count = 1;')
        return True

    def _iter_gauge_dispatch_rects(self):
        for nc_name, info in self._geom.nc_info.items():
            if info.gauge is None:
                continue
            for rect_info, is_synth in self._iter_dispatch_rects(info):
                yield nc_name, info, rect_info, is_synth

    def _emit_gauge_buffer_fill(self, gauge: GaugeBlock_N) -> None:
        # Buffer index order: x fastest (innermost), so 1-D = [g_x],
        # 2-D = [g_y][g_x].
        idx = ''.join(f'[g_{self._axis(i)}]'
                      for i in reversed(range(self._d)))
        for decl in gauge.outputs:
            if isinstance(decl, VariableDeclarationStmt_N):
                vname = decl.name.name
                if self._simd_mode == 'vec8d':
                    # Highway unaligned store -- gauge buffer rows are
                    # ``nx * sizeof(double)`` bytes, which may not be
                    # 64-byte aligned for arbitrary nx.  ``StoreU`` is
                    # zero-cost on AVX-512 when the address turns out
                    # aligned at runtime, so this is safe without
                    # padding the buffer to a tile multiple.
                    self._emit(f'hn::StoreU({_uname(vname)}, d, '
                               f'&gelb_buf_{vname}{idx});')
                else:
                    self._emit(f'gelb_buf_{vname}{idx} = '
                               f'{_uname(vname)};')

    def _emit_gauge_netcdf_write(self, gauge) -> None:
        # Time coord write
        self._emit('{')
        self._indent += 1
        self._emit('size_t time_idx = static_cast<size_t>(gelb_write_count - 1);')
        self._emit('GELB_NC(nc_put_var1_int(gelb_ncid, gelb_coord_time_id, '
                   '&time_idx, &gelb_timestep));')
        self._indent -= 1
        self._emit('}')
        # Gauge variable writes -- one var at a time, using slab semantics.
        for decl in gauge.outputs:
            if isinstance(decl, VariableDeclarationStmt_N):
                vname = decl.name.name
                cpp_type = self._gauge_buffer_cpp_type(decl)
                put_fn, nc_buf_type = {
                    'int8_t':  ('nc_put_vara_schar',    'signed char'),
                    'int16_t': ('nc_put_vara_short',    'short'),
                    'int32_t': ('nc_put_vara_int',      'int'),
                    'int64_t': ('nc_put_vara_longlong', 'long long'),
                    'float':   ('nc_put_vara_float',    'float'),
                    'double':  ('nc_put_vara_double',   'double'),
                }.get(cpp_type, ('nc_put_vara_double', 'double'))
                # Slab order matches the var-dim list (time, then
                # spatial dims slowest-to-fastest). For 1-D this is
                # (time, x); for 2-D it is (time, y, x).
                rev_axes = list(reversed([self._axis(i)
                                          for i in range(self._d)]))
                slab_rank = self._d + 1
                start_terms = ['static_cast<size_t>(gelb_write_count - 1)']
                start_terms.extend(['0'] * self._d)
                count_terms = ['1']
                count_terms.extend(f'static_cast<size_t>(g__n{a})'
                                   for a in rev_axes)
                self._emit('{')
                self._indent += 1
                self._emit(f'size_t start[{slab_rank}] = '
                           f'{{ {", ".join(start_terms)} }};')
                self._emit(f'size_t count[{slab_rank}] = '
                           f'{{ {", ".join(count_terms)} }};')
                self._emit(f'GELB_NC({put_fn}(gelb_ncid, '
                           f'gelb_varid_{vname}, start, count, '
                           f'reinterpret_cast<const {nc_buf_type}*>'
                           f'(gelb_buf_{vname})));')
                self._indent -= 1
                self._emit('}')
        self._emit('GELB_NC(nc_sync(gelb_ncid));')

    def _emit_mlups_report(self) -> None:
        self._emit('gelb_timer.print_report();')

    def _emit_netcdf_close(self) -> None:
        gauge = self._gauge_output_layout()
        if gauge is not None:
            self._emit('GELB_NC(nc_close(gelb_ncid));')
