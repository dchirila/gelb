"""Storage layout, lattice declarations, and halo emission for cpu_highway.

SoA/AoS/CBT layout decisions (ISA- and dimension-aware), the storage
subscript builder shared by every lattice access, NT-store gating,
lattice allocation emission, and the periodic halo-update lambdas.
"""

from __future__ import annotations

from gelb.backends.highway.common import (
    _lname,
    _CBT_TILE,
    _NT_STORE_THRESHOLD_BYTES,
    _TYPE_MAP,
    _cbt_addr_to_tile_start,
    _detect_avx512_available,
)

from gelb.gelb_ast.ASTNodes import (
    IntLiteral_N,
)

from gelb.midware.ast_eval import (
    get_max_dim,
    is_periodic,
)


class StorageLayoutMixin:
    """Mixin: see module docstring.  Assembled into
    ``HighwayCodeGenerator`` (stage3_backend_cpu_highway).
    """

    def _storage_sizes(self) -> tuple[int, ...]:
        # Hidden halo: storage allocates one ghost cell per axis-end, so
        # the per-axis storage size is the user grid size + 2.  Storage
        # index k corresponds to user-coord (k - 1); user-coord [0, N-1]
        # lives in storage [1, N], with [0] and [N+1] as ghost cells
        # populated each timestep by the halo-update kernel.
        return tuple(n + 2 for n in self._grid_sizes())

    def _storage_subscript(self, coord_strs, df_idx_str=None,
                           lattice_name=None) -> str:
        """Build the storage subscript chain from a list of user-coord
        strings.  Applies the +1 halo shift per axis so the subscript
        addresses the interior [1, N] of the halo'd storage.  Spatial
        axes are reversed so the contiguous (x) axis is innermost
        within the spatial portion.

        ``df_idx_str``: index expression for the DF dimension (e.g.
        ``'3'``, ``'gelb_df'``).  If omitted, the returned subscript
        omits the DF dimension entirely (callers that prepend the DF
        index themselves -- historic behaviour preserved).
        ``lattice_name``: looked up in ``self._use_aos`` /
        ``self._use_cbt`` to decide AoS vs SoA vs CBT dimension order.
        Only consulted when ``df_idx_str`` is provided.

        SoA: ``[df][c_d-1]...[c_0]``           (DF outermost spatial-wise)
        AoS: ``[c_d-1]...[c_0][df]``           (DF innermost -- co-located cell DFs)
        CBT: ``[c_d-1]...[c_1][x_tile][df][x_within]``
            where x_tile = (c_0 + 1) / TILE, x_within = (c_0 + 1) % TILE.
            Note CBT splits the x (innermost) coord into two subscripts
            and inserts the DF dimension between them.
        """
        if df_idx_str is not None and self._use_cbt.get(lattice_name, False):
            # CBT: split x into x_tile + x_within, insert df between them
            # and the rest of the spatial dims.  ``coord_strs[0]`` is x.
            x_str = f'({coord_strs[0]}) + 1'
            non_x_spatial = ''.join(
                f'[({c}) + 1]' for c in reversed(coord_strs[1:]))
            return (f'{non_x_spatial}'
                    f'[({x_str}) / {_CBT_TILE}]'
                    f'[{df_idx_str}]'
                    f'[({x_str}) % {_CBT_TILE}]')
        spatial = ''.join(f'[({c}) + 1]' for c in reversed(coord_strs))
        if df_idx_str is None:
            # Legacy entry point: caller will prepend the DF index.
            # Equivalent to SoA spatial portion only.
            return spatial
        if self._use_aos.get(lattice_name, False):
            return f'{spatial}[{df_idx_str}]'
        return f'[{df_idx_str}]{spatial}'

    def _any_aos_lattice(self) -> bool:
        """True iff at least one lattice in the program uses AoS
        storage.  Gates SIMD emission: ``Vec8d.load(&...)`` assumes 8
        contiguous cells along x for one DF (true in SoA), but in AoS
        the 8 contiguous doubles are 8 DFs of one cell -- different
        semantics -- so SIMD is disabled when any lattice is AoS."""
        return any(self._use_aos.values())

    def _auto_layout_choice(self) -> str:
        """Resolve ``--storage-layout auto`` to a concrete layout
        (``'soa'`` or ``'cbt'``) based on dimensionality and
        compile-host ISA.  Heuristic:

          * **1D** -> SoA.  CBT not designed for 1D (the tile axis
            is the only spatial axis; tiling makes no sense).
          * **3D + AVX-512** -> CBT.  Decisively wins (3D buffers
            easily exceed 4x L3, NT-store activates and the
            locality + write-combining wins compound).
          * **3D without AVX-512** -> SoA.  The current
            CBT cross-tile shuffle hardcodes 8-element index arrays
            that target ``Lanes(d) == _CBT_TILE``; on NEON
            (Lanes=2) this silently miscompiles streaming.  A
            TILE=2 native-NEON layout is the planned
            replacement.
          * **2D + AVX-512** -> CBT.  Single-instruction valignq-
            equivalent for cross-tile lane shifts.
          * **2D without AVX-512** -> SoA.

        Explicit ``--storage-layout {soa,cbt,aos}`` overrides this.
        AoS remains opt-in only (empirically slower than SIMD SoA;
        kept for experimentation).
        """
        dim = get_max_dim(self._lattice_info)
        if dim == 1:
            return 'soa'
        # 2D and 3D both gate CBT on AVX-512.  Without it,
        # ``Lanes(d) < _CBT_TILE`` on every Highway target we ship
        # to (NEON Lanes=2, AVX-2 Lanes=4), and the cross-tile
        # shuffle via ``hn::TwoTablesLookupLanes`` with 8-element
        # indices produces wrong results.  AVX-2 was previously
        # auto-CBT for 3D -- the gate is intentionally tightened here
        # pending a TILE=2 native-NEON layout.  Manual override
        # via ``--storage-layout cbt`` still works on AVX-512.
        return 'cbt' if _detect_avx512_available() else 'soa'

    def _resolve_storage_layout(self) -> str:
        """Resolve the user-facing ``_storage_layout_override`` to a
        concrete layout (``'soa'`` / ``'cbt'`` / ``'aos'``).  Pure
        function of state; called by the two
        ``_decide_storage_layout*`` maps so they can't disagree."""
        override = getattr(self, '_storage_layout_override', 'auto')
        if override == 'auto':
            return self._auto_layout_choice()
        return override

    def _decide_storage_layout(self) -> dict:
        """Pick AoS-vs-SoA-vs-CBT per-lattice based on the
        ``--storage-layout`` override.

        Returns ``{lattice_name: bool}`` where True = use AoS.  CBT
        (cell-block-tiled) is exposed via the parallel ``_use_cbt`` map
        populated alongside this method's return value -- see
        ``_decide_storage_layout_cbt``.

        ``'auto'`` resolves through ``_auto_layout_choice`` (since
        May 2026 -- previously hard-wired to SoA): an ISA- and
        dimension-aware rule that fits both AVX-512 and AVX2
        measurements.  See ``_auto_layout_choice`` for the rule.

        AoS opt-in: empirically scalar AoS is 1.4-2.5x SLOWER than SIMD
        SoA on LDC-2D N in {128, 256, 512} -- kept as ``--storage-layout
        aos`` for experimentation only.

        CBT opt-in (``--storage-layout cbt``): cell-block-tiled layout
        ``[buf][y_pad][x_tile][df][x_within_tile]`` with x_within_tile =
        SIMD width (8 for AVX-512 / Vec8d).  Recovers SIMD while keeping
        per-cell DF locality (9 cache lines per 8-cell tile, all
        contiguous).  Validated by a hand-coded prototype at LDC-2D
        N=512 OMP=16: +26.4 % over SoA.
        """
        resolved = self._resolve_storage_layout()
        out: dict[str, bool] = {}
        for name in self._lattice_info:
            # CBT is a third option; it sets _use_aos=False (CBT preserves
            # SIMD across cells, just like SoA does -- the cell-block-tiled
            # arrangement is orthogonal to AoS-vs-SoA).
            out[name] = (resolved == 'aos')
        return out

    def _decide_storage_layout_cbt(self) -> dict:
        """Parallel map for CBT (cell-block-tiled) storage.  Returns
        ``{lattice_name: bool}`` where True = use CBT.  Mutually
        exclusive with AoS (cannot opt into both).

        Uses the same ``_resolve_storage_layout`` as ``_use_aos`` so
        the two maps can't disagree about ``auto`` resolution."""
        resolved = self._resolve_storage_layout()
        # CBT's cross-tile loads handle x +- 1 only; a program reading
        # further across a periodic edge keeps the SoA layout.  Its
        # tile-aligned (and streaming) stores land only at the cell
        # being computed, so a program that writes at an offset keeps
        # SoA too.
        if resolved == 'cbt' and (self._periodic_reach() > 1
                                  or self._write_reach() > 0):
            resolved = 'soa'
        return {name: (resolved == 'cbt') for name in self._lattice_info}

    def _any_cbt_lattice(self) -> bool:
        """True iff at least one lattice in the program uses CBT."""
        return any(getattr(self, '_use_cbt', {}).values())

    def _cbt_store_suffix(self) -> str:
        """``'_a'`` when in SIMD-CBT mode (so ``Vec8d.store_a`` emits an
        aligned 64-byte store at the tile-start), ``'_nt'`` when also
        large enough to benefit from skipping write-allocate (sees
        ``_should_use_nt_stores``), else empty (``store``)."""
        if self._simd_mode == 'vec8d' and self._any_cbt_lattice():
            if self._should_use_nt_stores():
                return '_nt'
            return '_a'
        return ''

    def _should_use_nt_stores(self) -> bool:
        """Return True iff at least one CBT lattice's per-buffer storage
        exceeds ``_NT_STORE_THRESHOLD_BYTES``.  When True, lattice-out
        stores in CBT-SIMD mode emit ``Vec8d.store_nt`` (write-combining,
        skips L1 fill) instead of ``Vec8d.store_a``.

        Single threshold for the whole program: a multi-lattice program
        either uses NT for all CBT lattices or none, so the
        end-of-timestep ``_mm_sfence()`` covers every NT write
        regardless of which lattice issued it.  Per-lattice gating
        would buy little (in practice all lattices in a program are
        either all-large or all-small) and complicate the fence
        bookkeeping.
        """
        return self._max_cbt_buffer_bytes() > _NT_STORE_THRESHOLD_BYTES

    def _max_cbt_buffer_bytes(self) -> int:
        """Max single-buffer byte count over all CBT lattices.  Returns
        0 if no CBT lattice is in use.

        Buffer size is ``q * prod(N_i + 2) * sizeof(dtype)``, with the
        inner-x dim rounded up to a TILE multiple (CBT pads the inner
        axis).  Used by ``_should_use_nt_stores``."""
        if not self._any_cbt_lattice():
            return 0
        # All lattices in a multi-lattice program share the same grid
        # size in current GeLB programs; use the program-level
        # ``_grid_sizes`` helper which resolves IntLiteral_N etc.
        grid = self._grid_sizes()
        max_bytes = 0
        for lname, info in self._lattice_info.items():
            if not self._use_cbt.get(lname, False):
                continue
            q = info['q']
            dtype = info['dtype']
            elem_bytes = 4 if dtype in ('real32', 'real16') else 8
            # CBT inner-x dim is ceil((N_x + 2) / TILE) * TILE.
            x_tiles = (grid[0] + 2 + _CBT_TILE - 1) // _CBT_TILE
            spatial_cells = x_tiles * _CBT_TILE
            for n in grid[1:]:
                spatial_cells *= (n + 2)
            buf_bytes = q * spatial_cells * elem_bytes
            if buf_bytes > max_bytes:
                max_bytes = buf_bytes
        return max_bytes

    def _cbt_aligned_addr(self, addr: str) -> str:
        """In SIMD-CBT mode, rewrite a CBT lattice address whose lane
        subscript is ``[(...) % TILE]`` to ``[0]`` (lane-0 aligned).
        The tile-aligned iteration guarantees the lane subscript folds
        to 0 at runtime; the rewrite gives gcc a static alignment hint
        and matches the ``Store`` / ``Load`` (aligned) semantics."""
        if self._simd_mode == 'vec8d' and self._any_cbt_lattice():
            return _cbt_addr_to_tile_start(addr)
        return addr

    def _emit_lattice_declarations(self) -> None:
        # Per-lattice storage allocation.  Layout chosen by
        # ``self._use_aos[lname]`` / ``self._use_cbt[lname]`` at
        # construction time:
        #   SoA: g_<lname>_storage[buf][df][...y][x]
        #   AoS: g_<lname>_storage[buf][...y][x][df]
        #   CBT: g_<lname>_storage[buf][...y][x_tile][df][TILE]
        # Spatial dims are sized N+2 (one ghost cell per axis-end);
        # the user-facing interior lives in storage indices [1, N].
        # For CBT: x_tile = ceil((N_x + 2) / TILE) where TILE = 8 (Vec8d).
        rev_dim_str = ''.join(f'[g__n{self._axis(i)} + 2]'
                              for i in reversed(range(self._d)))
        # CBT-specific: same as rev_dim_str but for spatial dims y, z, ... (excluding x),
        # with x replaced by x_tile dimension.
        # Spatial dims in storage order are [...y][x] (x innermost).
        # For CBT we replace [x] with [x_tile][df][TILE] effectively.
        if self._d >= 1:
            non_x_dim_str = ''.join(
                f'[g__n{self._axis(i)} + 2]'
                for i in reversed(range(1, self._d)))
        else:
            non_x_dim_str = ''
        self._emit('// Lattice arrays (ping-pong) -- layout per-lattice;'
                   ' halo: +1 cell per axis-end.')
        self._emit('// Heap-allocated via gelb_alloc_lattice (64-byte'
                   ' aligned, guard padding on')
        self._emit('// both sides for the SIMD x-edge over-reads):'
                   ' static arrays land in .bss,')
        self._emit('// and past ~2 GB the small code model breaks the'
                   ' link step.  The named-')
        self._emit('// type reference keeps subscript syntax identical'
                   ' to the static-array form.')
        for lname, info in self._lattice_info.items():
            q = info['q']
            cpp_dtype = _TYPE_MAP[info['dtype']]
            use_aos = self._use_aos.get(lname, False)
            use_cbt = self._use_cbt.get(lname, False)
            if use_cbt:
                layout_tag = (f'CBT [buf]{non_x_dim_str}'
                              f'[x_tile][{q}][{_CBT_TILE}]')
                self._emit(f'// {lname}: {layout_tag}')
                # x_tile count: ceil((nx + 2) / TILE).  Using a constexpr
                # lets the C++ compiler fold the dim into an immediate.
                self._emit(
                    f'static constexpr int g__{lname}_x_tiles = '
                    f'(g__n{self._axis(0)} + 2 + {_CBT_TILE} - 1) / {_CBT_TILE};')
                self._emit(
                    f'using {_lname(lname)}_storage_t = {cpp_dtype}[2]'
                    f'{non_x_dim_str}[g__{lname}_x_tiles][{q}][{_CBT_TILE}];')
            elif use_aos:
                layout_tag = f'AoS [buf][...y][x][{q}]'
                self._emit(f'// {lname}: {layout_tag}')
                self._emit(f'using {_lname(lname)}_storage_t = {cpp_dtype}[2]'
                           f'{rev_dim_str}[{q}];')
            else:
                layout_tag = f'SoA [buf][{q}][...y][x]'
                self._emit(f'// {lname}: {layout_tag}')
                self._emit(f'using {_lname(lname)}_storage_t = {cpp_dtype}[2]'
                           f'[{q}]{rev_dim_str};')
            fill_byte = '0xFF' if self._poison_uninit else '0'
            alloc_call = (f'gelb_alloc_lattice('
                          f'sizeof({_lname(lname)}_storage_t), {fill_byte})')
            self._emit(f'static {_lname(lname)}_storage_t& {_lname(lname)}_storage = '
                       f'*static_cast<{_lname(lname)}_storage_t*>('
                       f'{alloc_call});')
            self._emit(f'int {_lname(lname)}_old = 0;')
            self._emit(f'int {_lname(lname)}_new = 1;')
        self._emit('')
        self._emit_halo_update_lambdas()

    def _emit_halo_update_lambdas(self) -> None:
        """For each lattice with at least one periodic axis, emit a
        ``halo_update_<lname>`` lambda that copies periodic-wrap data
        into the ghost cells of the halo'd storage.  The lambda is
        called from the time-loop body before the dynamic dispatch.

        Sweep order: x-faces first, then y-faces, then z-faces.  Each
        face copy iterates over the OTHER axes; for an other-axis A
        that is periodic AND has already been swept (lower index than
        the current axis), iterate A over the storage range
        ``[0, N+1]`` so that edge / corner ghosts populated by the
        earlier sweep flow into the later one.  For non-periodic A or
        not-yet-swept A, iterate A over the interior ``[1, N]`` only.

        For D3Q19 fully periodic this populates all 6 face slabs and
        all 12 edges; corners are populated for free (D3Q19 doesn't
        need them but the iteration covers them).  For mixed
        periodicity (e.g. RB: periodic-x, wall-y) only the periodic
        axis's faces are emitted; the wall-axis ghosts stay zero, and
        the dynamic kernel's clamp ternary keeps the read in user
        range so wall ghosts are never accessed."""
        for lname, info in self._lattice_info.items():
            d = info['d']
            q = info['q']
            per = [is_periodic(self._lattice_info, i) for i in range(d)]
            if not any(per):
                continue
            self._emit(f'// Halo-update lambda for `{lname}`: copy '
                       f'periodic-wrap into ghost cells.')
            self._emit(f'auto halo_update_{lname} = [&](int buf) {{')
            self._indent += 1
            for axis_idx in range(d):
                if per[axis_idx]:
                    self._emit_halo_axis_copy(lname, q, d, axis_idx, per)
            self._indent -= 1
            self._emit('};')
            self._emit('')

    def _emit_halo_axis_copy(self, lname: str, q: int, d: int,
                              axis_idx: int,
                              periodic_flags: list) -> None:
        """Emit the face-copy loops for one periodic axis ``axis_idx``."""
        ax = self._axis(axis_idx)
        n_axis = f'g__n{ax}'
        # Outer-axis loops: the OTHER axes, in storage-reversed order
        # (z outermost, x innermost) -- except we drop axis_idx from the
        # list because that's the face we're copying along.
        other_axes = [i for i in range(d) if i != axis_idx]
        # In storage layout the leftmost subscript is the highest axis
        # index (z for 3-D), so loop nesting goes from highest index
        # outwards.  Among the OTHER axes we follow the same order.
        loop_axes = sorted(other_axes, reverse=True)
        self._emit(f'// {ax}-faces')
        # Open loops for each other axis.
        opened = 0
        for j in loop_axes:
            ax_j = self._axis(j)
            n_j = f'g__n{ax_j}'
            # Earlier-swept axis => already-populated ghosts => iterate
            # over the storage range so edges/corners flow through.
            if periodic_flags[j] and j < axis_idx:
                lo, hi = '0', f'{n_j} + 1'
            else:
                lo, hi = '1', n_j
            if opened == 0 and self.use_openmp and len(loop_axes) >= 1:
                fp = self._omp_firstprivate_clause()
                if len(loop_axes) >= 2:
                    self._emit(f'#pragma omp parallel for '
                               f'collapse({len(loop_axes)}) '
                               f'schedule(static){" " + fp if fp else ""}')
                else:
                    self._emit(f'#pragma omp parallel for '
                               f'schedule(static){" " + fp if fp else ""}')
            self._emit(f'for (int g_{ax_j} = {lo}; '
                       f'g_{ax_j} <= {hi}; ++g_{ax_j}) {{')
            self._indent += 1
            opened += 1
        # Innermost: per-DF copy of the two ghost slabs (low and high).
        self._emit(f'for (int gelb_df = 0; gelb_df < {q}; ++gelb_df) {{')
        self._indent += 1
        # Build subscripts for low ghost (axis = 0, src = N) and
        # high ghost (axis = N+1, src = 1).  Storage indexing depends
        # on layout:
        #   SoA: [buf][df][z][y][x]
        #   AoS: [buf][z][y][x][df]
        # The values list holds absolute storage indices per axis (no
        # +1 user-coord shift here -- the halo iterators ALREADY emit
        # storage indices like '0', 'g__nx', etc.), so we can't reuse
        # ``_storage_subscript`` (which applies +1).
        use_aos = self._use_aos.get(lname, False)
        use_cbt = self._use_cbt.get(lname, False)

        def addr(values):
            if use_cbt:
                # CBT: [buf][...y_pad][x_tile][df][x_within].
                # ``values`` holds storage indices already (no +1 shift);
                # split values[0] (x) into x_tile and x_within.
                non_x_spatial = ''.join(
                    f'[{values[i]}]' for i in reversed(range(1, d)))
                x_str = values[0]
                return (f'{_lname(lname)}_storage[buf]'
                        f'{non_x_spatial}'
                        f'[({x_str}) / {_CBT_TILE}]'
                        f'[gelb_df]'
                        f'[({x_str}) % {_CBT_TILE}]')
            spatial = ''.join(f'[{values[i]}]'
                              for i in reversed(range(d)))
            if use_aos:
                return (f'{_lname(lname)}_storage[buf]'
                        f'{spatial}[gelb_df]')
            return (f'{_lname(lname)}_storage[buf][gelb_df]'
                    f'{spatial}')
        lo_dst = [None] * d
        lo_src = [None] * d
        hi_dst = [None] * d
        hi_src = [None] * d
        for i in range(d):
            ax_i = self._axis(i)
            if i == axis_idx:
                lo_dst[i] = '0'
                lo_src[i] = f'g__n{ax_i}'
                hi_dst[i] = f'g__n{ax_i} + 1'
                hi_src[i] = '1'
            else:
                lo_dst[i] = f'g_{ax_i}'
                lo_src[i] = f'g_{ax_i}'
                hi_dst[i] = f'g_{ax_i}'
                hi_src[i] = f'g_{ax_i}'
        self._emit(f'{addr(lo_dst)} = {addr(lo_src)};')
        self._emit(f'{addr(hi_dst)} = {addr(hi_src)};')
        self._indent -= 1
        self._emit('}')
        # Close the outer-axis loops.
        for _ in range(opened):
            self._indent -= 1
            self._emit('}')
