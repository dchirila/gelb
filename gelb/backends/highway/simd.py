"""SIMD (Google Highway Vec8d) emission for cpu_highway.

The structural SIMD eligibility gate, vectorized block emission, the x-split
machinery for boundary-adjacent SIMD bodies, CBT cross-tile loads, and
aligned/NT store selection.
"""

from __future__ import annotations

from gelb.backends.highway.addressing import LatticeAddress, spatial_subscript

from gelb.backends.highway.simd_types import ScalarFallbackRequired

from gelb.backends.highway.common import (
    _lname,
    _CBT_TILE,
    _TYPE_MAP,
)

from gelb.midware.ast_eval import (
    is_periodic,
)


class SimdEmitMixin:
    """Mixin: see module docstring.  Assembled into
    ``HighwayCodeGenerator`` (stage3_backend_cpu_highway).
    """

    def _emit_simd_store(self, vname: str, lhs_addr: LatticeAddress) -> str:
        """Return the C++ source for a SIMD-mode lattice-store call,
        dispatching on the active layout's alignment / NT-store
        decision:

          * SoA (``_cbt_store_suffix() == ''``)         -> ``hn::StoreU(v, d, &addr)``.
            Cells aren't 64-byte aligned in general (head/tail of
            the SoA range can land anywhere); ``LoadU`` /
            ``StoreU`` lower to a zero-cost aligned op when the
            address turns out aligned at runtime.
          * CBT-no-NT (``_cbt_store_suffix() == '_a'``) -> ``hn::Store(v, d, &cbt_addr)``.
            Tile-aligned iteration guarantees the lane subscript
            folds to 0 at runtime; ``hn::Store`` is the aligned
            variant. The structured address renders a lane-zero
            subscript, giving gcc a static alignment hint.
          * CBT+NT (``_cbt_store_suffix() == '_nt'``)    -> ``hn::Stream(v, d, &cbt_addr)``.
            NT-store path.  The gate (``_should_use_nt_stores()``)
            decides when the backend can safely use streaming stores;
            otherwise CBT stays on the aligned ``Store`` path.

        ``store`` / ``store_a`` / ``store_nt`` map 1:1 to the three
        Highway calls.
        """
        suffix = self._cbt_store_suffix()
        if suffix == '_nt':
            return (f'hn::Stream({vname}, d, '
                    f'&{lhs_addr.aligned()})')
        if suffix == '_a':
            return (f'hn::Store({vname}, d, '
                    f'&{lhs_addr.aligned()})')
        return f'hn::StoreU({vname}, d, &{lhs_addr})'

    def _block_simd_eligible(self, block, info) -> bool:
        """Context-agnostic predicate: is this block (initializer /
        dynamic / gauge) eligible for SIMD emission?

        A block is SIMD-eligible when:
          - its NC fills its bbox densely,
          - the bbox's innermost (x) axis spans at least
            Vec8d::size cells (after deducting head/tail), AND
          - any upstream_dfs offsets are foldable to small integers
            (which the offset analysis takes care of).

        These are the conditions of the block's shape.  Whether its
        statements have a vector form is found while they are emitted
        (``ScalarFallbackRequired``; ``_emit_block_dispatch``).
        """
        if info.bbox is None or not info.bbox_dense:
            return False
        # The vector gauge store writes a double vector into the
        # output buffer, so a gauge whose output is not binary64 (an
        # integer, a bool, a real32) takes the scalar path, where every
        # cell converts its value to the output's type.  Gauges of
        # different classes that share an output name fill one buffer,
        # declared from the first-painted class's gauge
        # (collect_gauge_outputs), so that buffer must be binary64 too.
        # The frontend rejects outputs of one name with different types
        # (GaugeValidationVisitor), so this only guards a program that
        # bypasses it.
        outputs = list(getattr(block, 'outputs', ()))
        if any(_TYPE_MAP.get(getattr(decl.data_type, 'element_dtype', None))
               != 'double' for decl in outputs):
            return False
        if outputs:
            layout = self._gauge_output_layout()
            buffers = {buf.name.name: buf
                       for buf in (layout.outputs if layout else ())}
            if any(self._gauge_buffer_cpp_type(buffers[decl.name.name])
                   != 'double'
                   for decl in outputs if decl.name.name in buffers):
                return False
        # Vec8d is double-precision only.  If any lattice (this block
        # may read from or write to multiple) isn't double, fall back
        # to scalar emission.
        if any(_TYPE_MAP.get(info['dtype']) != 'double'
               for info in self._lattice_info.values()):
            return False
        x_lo, x_hi = info.bbox[0]
        # After deducting head/tail along x, the SIMD interior must
        # still span >= VW cells for the vector body to fire even once.
        offsets = self._stencils.offset_bounds(block.name.name, self._d)
        if (self._has_guarded_reads(block) and self._any_cbt_lattice()
                and max(offsets[0]) >= _CBT_TILE):
            # The cross-tile loader covers adjacent tiles. Wider links
            # still work through scalar addressing (including modulo).
            return False
        woffs = self._stencils.offset_bounds(block.name.name, self._d, writes=True)
        neg_x = max(offsets[0][0], woffs[0][0])
        pos_x = max(offsets[0][1], woffs[0][1])
        periodic_x = is_periodic(self._lattice_info, 0)
        sizes = self._grid_sizes()
        head_x = neg_x if (periodic_x and x_lo == 0) else 0
        tail_x = pos_x if (periodic_x and x_hi == sizes[0] - 1) else 0
        interior = (x_hi - tail_x) - (x_lo + head_x) + 1
        if interior < self._simd_vw:
            return False
        return True

    def _emit_block_dispatch(self, label: str, block, nc_name: str, info,
                             rect_suffix: str, context: str) -> None:
        """Emit ``block`` over one rectangle of a node class: as a vector
        body when it has one, else as one scalar loop nest.

        The vector form is emitted speculatively.  A statement without a
        vector form raises ``ScalarFallbackRequired``; everything the
        attempt wrote or registered is then undone, and the block is
        emitted as scalar code under a banner without ``-- SIMD``.  A
        rectangle whose interior runs scalar anyway (AoS storage, a CBT
        range without a full tile, a range that is all peel) emits no
        vector body, so the body is emitted once more as a vector one
        and discarded: the path of a block must not depend on the
        storage layout or on the rectangle."""
        name = block.name.name
        if self._block_simd_eligible(block, info):
            saved = self._emission_state()
            try:
                self._emit(f'// {label}: {name} ({nc_name}) -- SIMD{rect_suffix}')
                self._vector_bodies = 0
                self._emit_block_simd(block, info, context=context)
                if not self._vector_bodies:
                    emitted = self._emission_state()
                    self._simd_mode = 'vec8d'
                    self._emit_block_body(block, context=context)
                    self._restore_emission_state(emitted)
                return
            except ScalarFallbackRequired:
                self._restore_emission_state(saved)
        self._emit(f'// {label}: {name} ({nc_name}){rect_suffix}')
        self._emit_spatial_loop_open(info)
        self._emit_block_body(block, context=context)
        self._emit_spatial_loop_close()

    def _emission_state(self) -> tuple:
        """Everything a block's emission changes, to be put back by
        ``_restore_emission_state``."""
        return (len(self._lines), self._indent, self._simd_mode, self._simd_env,
                set(self._wrap_safe_axes), dict(self._axis_bindings),
                list(self._axis_binding_stack), self._current_block,
                self._in_coord_scalar, len(self._deferred_constexpr_decls),
                dict(self._deferred_constexpr_dedup),
                self._deferred_constexpr_counter)

    def _restore_emission_state(self, state: tuple) -> None:
        (n_lines, self._indent, self._simd_mode, self._simd_env,
         self._wrap_safe_axes, self._axis_bindings, self._axis_binding_stack,
         self._current_block, self._in_coord_scalar, n_decls,
         self._deferred_constexpr_dedup, self._deferred_constexpr_counter) = state
        del self._lines[n_lines:]
        del self._deferred_constexpr_decls[n_decls:]

    def _has_guarded_reads(self, block) -> bool:
        """Whether ``block`` reads a neighbour through ``bounce_back_dfs``
        (a guarded read of the stencil analysis)."""
        return any(access.guarded
                   for access in self._stencils.blocks[block.name.name].reads)

    def _emit_block_simd(self, block, info, *,
                        context: str = 'dynamic') -> None:
        """Context-agnostic SIMD emit: head/body/tail x-axis split with
        outer-axis recursion.  ``context`` controls how
        ``_emit_block_body`` resolves lattice slot / output destination
        (``'dynamic'`` writes f_new, ``'initializer'`` writes f_old,
        ``'gauge'`` reads only and fills gauge buffers).

        Outer (non-x) axes get a 3-way split: head / body / tail.
        The innermost (x) axis ALWAYS gets head / SIMD-body / tail --
        independently of whether the outer axes are at their safe
        body sub-range or in a head/tail boundary row.  The outer
        axes' safety only affects which axes we mark as
        ``_wrap_safe_axes`` (so cross-axis reads can drop the
        modulo) -- it does NOT gate SIMD vectorisation along x.

        Outer (non-x) axes get a 3-way split: head / body / tail.
        The innermost (x) axis ALWAYS gets head / SIMD-body / tail --
        independently of whether the outer axes are at their safe
        body sub-range or in a head/tail boundary row.  The outer
        axes' safety only affects which axes we mark as
        ``_wrap_safe_axes`` (so cross-axis reads can drop the
        modulo) -- it does NOT gate SIMD vectorisation along x.

        Gating on the outer axes would emit the entire inner-x range
        of a y- or z-boundary row as a single scalar loop, leaving
        ~6 % of cells (TGV-3D N=64) running scalar despite a
        62-cell-wide SIMD-eligible interior."""
        dblock = block  # alias kept for readability in the body
        d = self._d
        sizes = self._grid_sizes()
        offsets = self._stencils.offset_bounds(dblock.name.name, self._d)
        woffs = self._stencils.offset_bounds(dblock.name.name, self._d, writes=True)
        bbox = info.bbox
        # Per-axis head/tail peel counts.  The halo-update kernel
        # pre-stages the periodic wrap into one ghost cell per axis
        # end, so reads at +-1 cross the boundary unconditionally and a
        # block that reaches no further peels nothing: the SIMD body
        # extends over the whole bbox.  A block reaching k > 1 cells
        # along a periodic axis peels the k - 1 cells per side whose
        # reads would leave the halo; they run scalar, where
        # _coordinate wraps those reads with a modulo.  A write at
        # offset k (a push) peels the full k cells per side: a ghost
        # cell is never copied back, so the destination must be in the
        # interior; the peeled cells wrap their stores with a modulo.
        # Non-periodic axes never peel (their bboxes are restricted to
        # interior regions -- walls live in a separate NC), and the
        # clamp ternary in _coordinate handles boundary reads
        # (writes off a wall are rejected by the validators).
        head = [0] * d
        tail = [0] * d
        bounce = self._has_guarded_reads(block)
        for axis in range(d):
            if not is_periodic(self._lattice_info, axis):
                if bounce and axis == 0:
                    # Guarded reads may occur at grid-edge cells. Keep
                    # those lanes scalar; the vector body has valid x
                    # neighbours, while y/z use uniform load guards.
                    span = bbox[axis][1] - bbox[axis][0] + 1
                    head[axis] = min(span, max(0, offsets[axis][0] - bbox[axis][0]))
                    tail[axis] = min(span - head[axis], max(
                        0, bbox[axis][1] + offsets[axis][1] - sizes[axis] + 1))
                continue
            head[axis] = max(0, offsets[axis][0] - 1, woffs[axis][0])
            tail[axis] = max(0, offsets[axis][1] - 1, woffs[axis][1])
            span = bbox[axis][1] - bbox[axis][0] + 1
            if head[axis] + tail[axis] > span:
                head[axis], tail[axis] = span, 0    # all of it scalar
        # 1-D: only the x-axis split.  No outer axes => no outer-safe
        # set to thread through.
        if d == 1:
            self._emit_x_split(dblock, info, head[0], tail[0],
                               outer_safe_axes=frozenset(),
                               context=context)
            return

        def _emit_axis_split(axis_idx: int,
                             outer_safe_axes: frozenset):
            """Recursively emit the per-axis head/body/tail split.
            ``outer_safe_axes`` is the set of axis indices among
            (axis_idx+1, ..., d-1) currently in their safe body
            sub-range.  At axis_idx == 0 we delegate to
            ``_emit_x_split`` and pass the set through; the SIMD body
            always fires."""
            if axis_idx == 0:
                self._emit_x_split(dblock, info, head[0], tail[0],
                                   outer_safe_axes=outer_safe_axes,
                                   context=context)
                return
            bbox_lo, bbox_hi = bbox[axis_idx]
            safe_lo = bbox_lo + head[axis_idx]
            safe_hi = bbox_hi - tail[axis_idx]
            ax = self._axis(axis_idx)
            is_outermost = (axis_idx == d - 1)
            omp_request = is_outermost and self.use_openmp
            # Head (axis unsafe -- cross-row reads need modulo wrap).
            if safe_lo > bbox_lo:
                self._emit_axis_loop_open(
                    ax, bbox_lo, safe_lo - 1,
                    label=f"{ax} = head ({ax}-axis unsafe; "
                          f"cross-{ax} reads use modulo wrap)",
                    omp=omp_request and (safe_lo - bbox_lo) >= 2)
                _emit_axis_split(axis_idx - 1, outer_safe_axes)
                self._emit_axis_loop_close()
            # Body (axis safe -- drop modulo wrap on this axis).
            if safe_hi >= safe_lo:
                self._emit_axis_loop_open(
                    ax, safe_lo, safe_hi,
                    label=f"{ax} = interior ({ax}-axis safe; "
                          f"cross-{ax} reads skip modulo)",
                    omp=omp_request and (safe_hi - safe_lo + 1) >= 2)
                _emit_axis_split(axis_idx - 1,
                                 outer_safe_axes | {axis_idx})
                self._emit_axis_loop_close()
            # Tail (axis unsafe).
            if safe_hi < bbox_hi:
                self._emit_axis_loop_open(
                    ax, safe_hi + 1, bbox_hi,
                    label=f"{ax} = tail ({ax}-axis unsafe; "
                          f"cross-{ax} reads use modulo wrap)",
                    omp=omp_request and (bbox_hi - safe_hi) >= 2)
                _emit_axis_split(axis_idx - 1, outer_safe_axes)
                self._emit_axis_loop_close()

        _emit_axis_split(d - 1, frozenset())

    def _emit_x_split(self, dblock, info, x_head, x_tail, *,
                      outer_safe_axes: frozenset,
                      context: str = 'dynamic'):
        """Emit the x-axis split: scalar-with-wrap head, SIMD-eligible
        interior (Vec8d body + scalar tail), scalar-with-wrap tail.

        ``outer_safe_axes`` is the set of outer-axis indices in their
        safe body sub-range (so cross-row reads on those axes can drop
        the modulo).  The x-axis's SIMD body fires unconditionally
        regardless of outer-axis safety -- the y/z wrap modulos are
        applied at the per-direction read level via
        ``_wrap_safe_axes``."""
        bbox_x_lo, bbox_x_hi = info.bbox[0]
        x_safe_lo = bbox_x_lo + x_head
        x_safe_hi = bbox_x_hi - x_tail
        vw = self._simd_vw
        outer_safe_set = set(outer_safe_axes)
        # scalar head (with wrap on x; outer-axis safety unchanged).
        if x_safe_lo > bbox_x_lo:
            self._emit_axis_loop_open(
                'x', bbox_x_lo, x_safe_lo - 1,
                label="x = scalar head (x-axis unsafe; "
                      "x reads use modulo wrap)")
            old = self._wrap_safe_axes
            self._wrap_safe_axes = outer_safe_set
            self._emit_block_body(dblock, context=context)
            self._wrap_safe_axes = old
            self._emit_axis_loop_close()
        # interior (x in its safe range): SIMD body + scalar remainder.
        interior_safe_set = outer_safe_set | {0}
        if x_safe_hi >= x_safe_lo:
            if self._any_aos_lattice():
                # AoS: Vec8d.load(&storage[buf][y][x][df]) would load 8
                # DFs of one cell, not 8 cells of one DF -- wrong
                # semantics.  Fall back to a single scalar x-loop for
                # correctness.
                self._emit('// x = scalar interior (AoS storage; '
                           'across-cell SIMD disabled, x-axis safe)')
                self._emit(f'for (int64_t g_x = {x_safe_lo}; '
                           f'g_x <= {x_safe_hi}; ++g_x) {{')
                self._indent += 1
                old_axes = self._wrap_safe_axes
                self._wrap_safe_axes = interior_safe_set
                self._emit_block_body(dblock, context=context)
                self._wrap_safe_axes = old_axes
                self._indent -= 1
                self._emit('}')
            elif self._any_cbt_lattice():
                # CBT: tile-aligned SIMD body.  Iterate tile_id over
                # all tiles overlapping the x_safe range, with
                # ``g_x = tile_id * TILE - 1`` so storage_x = g_x + 1
                # is a multiple of TILE and lattice loads/stores use
                # ``Vec8d.load_a`` / ``store_a``.  Cross-tile stencil
                # reads (DF with EX[i] = +/-1) emit a valignq pattern
                # via _emit_upstream_dfs.
                #
                # Cells outside the x_safe range that fall within the
                # iterated tiles get processed by the SIMD body too.
                # We split this into two cases by *what's outside the
                # range*:
                #   (a) **halo / padding cells** -- i.e. the straddle
                #       lands at user_x < 0 (left halo) or
                #       user_x >= N (right halo + post-grid padding).
                #       The wide SIMD store is fine: halo is
                #       overwritten by the halo-update kernel each
                #       step, and padding is allocated-but-never-read.
                #   (b) **real interior cells of OTHER node classes**
                #       -- i.e. the straddle lands at
                #       0 <= user_x < N but outside this rect's bbox.
                #       Two sub-cases:
                #         (b1) the cell belongs to *another NC* whose
                #              dispatch will overwrite it later in
                #              the same timestep -- fine.
                #         (b2) the cell belongs to a *masked NC*
                #              (SOLID, etc.) -- there is no
                #              overwriting dispatch.  The wide SIMD
                #              store leaves spurious values in
                #              masked-cell storage, which then feeds
                #              the next timestep's neighbour reads
                #              and propagates wrong-answer errors.
                # We can't tell (b1) from (b2) from per-rect bbox
                # alone (would need full NC-map knowledge here), but
                # both sub-cases are handled correctly by peeling the
                # straddler tiles to per-lane scalar stores covering
                # only the in-bbox lanes -- that respects every NC's
                # exclusive ownership of its own cells.
                #
                # Gauge context is special: the gauge buffer has no
                # halo or padding, so *any* straddle (including what
                # would be "halo" for the lattice) would corrupt
                # adjacent rows.  Gauge therefore always peels both
                # ends, regardless of bbox endpoint.
                #
                # Bit-equivalence regression tests cover 2D and 3D
                # obstacle cases.
                n_x = self._grid_sizes()[0]
                first_tile = (x_safe_lo + 1) // _CBT_TILE
                last_tile = (x_safe_hi + 1) // _CBT_TILE
                # A tile T is "fully in safe range" iff
                #   T*TILE - 1 >= x_safe_lo  AND
                #   T*TILE + (TILE - 2) <= x_safe_hi
                first_full_tile = (x_safe_lo + _CBT_TILE) // _CBT_TILE
                last_full_tile = ((x_safe_hi - (_CBT_TILE - 2))
                                  // _CBT_TILE)
                # Per-side peel decisions.  Gauge always peels (no
                # halo/padding to soak the overshoot).  Init/dyn
                # peel only when the straddle lands in real interior
                # cells (i.e. bbox doesn't reach the corresponding
                # grid edge).
                guarded_reads = self._has_guarded_reads(dblock)
                # Guarded neighbour loads describe real grid cells only.
                # Do not execute them for halo/padding lanes: a shifted
                # whole-tile load could otherwise reach past storage.
                head_peel = (first_tile < first_full_tile and
                             (context == 'gauge' or guarded_reads or x_safe_lo > 0))
                tail_peel = (last_tile > last_full_tile and
                             (context == 'gauge' or guarded_reads
                              or x_safe_hi < n_x - 1))
                body_first_tile = (first_full_tile if head_peel
                                   else first_tile)
                body_last_tile = (last_full_tile if tail_peel
                                  else last_tile)
                peel_partial = head_peel or tail_peel

                if peel_partial and body_last_tile < body_first_tile:
                    # No full tiles fit between the peels -- emit a
                    # single scalar loop covering the whole safe
                    # range.  Triggers when the NC bbox is narrower
                    # than 2*TILE - 1 cells AND both sides need to
                    # peel (e.g. a wall column one tile wide
                    # straddling a tile boundary).
                    label_suffix = ('gauge-buffer overrun guard'
                                    if context == 'gauge'
                                    else 'masked-cell spillover guard')
                    self._emit_axis_loop_open(
                        'x', x_safe_lo, x_safe_hi,
                        label=f'x = scalar (CBT, no full tiles in '
                              f'safe range; {label_suffix})')
                    old = self._wrap_safe_axes
                    self._wrap_safe_axes = interior_safe_set
                    self._emit_block_body(dblock, context=context)
                    self._wrap_safe_axes = old
                    self._emit_axis_loop_close()
                else:
                    body_lo = body_first_tile * _CBT_TILE - 1
                    body_hi = (((body_last_tile + 1) * _CBT_TILE - 2)
                               if tail_peel else x_safe_hi)
                    label_suffix = ('gauge-buffer overrun guard'
                                    if context == 'gauge'
                                    else 'masked-cell spillover guard')
                    # Scalar peel: partial first tile.
                    if head_peel and x_safe_lo <= body_lo - 1:
                        self._emit_axis_loop_open(
                            'x', x_safe_lo, body_lo - 1,
                            label=f'x = scalar peel (CBT partial '
                                  f'first tile; {label_suffix})')
                        old = self._wrap_safe_axes
                        self._wrap_safe_axes = interior_safe_set
                        self._emit_block_body(dblock, context=context)
                        self._wrap_safe_axes = old
                        self._emit_axis_loop_close()
                    # SIMD body.  When peeling either side, iterate
                    # only fully-in-bbox tiles; otherwise iterate
                    # every tile overlapping x_safe (the dyn / init
                    # contexts rely on this to write halo/padding
                    # cells, which are then overwritten by halo
                    # update or are unread allocated padding).
                    self._emit('// x = SIMD body: tile-aligned CBT iteration')
                    self._emit('{')
                    self._indent += 1
                    if peel_partial:
                        body_comment = ('; partial-tile peels '
                                        'emitted separately to '
                                        f'avoid {label_suffix}')
                    else:
                        body_comment = (
                            '; cells outside the safe range get '
                            'overwritten by halo update or land in '
                            'allocated padding storage.')
                    self._emit(f'// tiles {body_first_tile}..'
                               f'{body_last_tile} cover x_safe = '
                               f'[{x_safe_lo}, {x_safe_hi}]'
                               + body_comment)
                    self._emit(f'for (int g_x_tile = {body_first_tile}; '
                               f'g_x_tile <= {body_last_tile}; '
                               f'++g_x_tile) {{')
                    self._indent += 1
                    self._emit(f'int64_t g_x = g_x_tile * {_CBT_TILE} - 1;')
                    # This CBT branch is kept separate from the plain
                    # SoA path because it needs Highway cross-tile
                    # ``hn::CombineShiftRightLanes`` shuffles.
                    #
                    # NOTE (NEON): this block hardcodes the tile-wide
                    # ``Vec`` ops to ``Lanes(d) == _CBT_TILE``
                    # -- both ``hn::Iota(d, g_x)`` covering the whole
                    # tile and the cross-tile ``TwoTablesLookupLanes``
                    # below uses 8-element indices.  On NEON
                    # (Lanes=2) the indices are oversized and the
                    # blend silently produces wrong results -- a TILE=2
                    # native-NEON layout is the planned replacement.
                    # Until then the auto-layout
                    # selector gates CBT on AVX-512 (see
                    # ``_auto_layout_choice``), gelbc rejects
                    # ``--storage-layout cbt`` without AVX-512, and
                    # every CBT program static_asserts eight lanes.
                    self._emit(f'V gelb_xv = hn::Iota(d, '
                               f'static_cast<double>(g_x));')
                    old_mode, old_axes = (self._simd_mode,
                                          self._wrap_safe_axes)
                    self._simd_mode = 'vec8d'
                    self._wrap_safe_axes = interior_safe_set
                    self._emit_block_body(dblock, context=context)
                    self._simd_mode = old_mode
                    self._wrap_safe_axes = old_axes
                    self._indent -= 1
                    self._emit('}')
                    self._indent -= 1
                    self._emit('}')
                    # Scalar peel: partial last tile.
                    if tail_peel and body_hi + 1 <= x_safe_hi:
                        self._emit_axis_loop_open(
                            'x', body_hi + 1, x_safe_hi,
                            label=f'x = scalar peel (CBT partial '
                                  f'last tile; {label_suffix})')
                        old = self._wrap_safe_axes
                        self._wrap_safe_axes = interior_safe_set
                        self._emit_block_body(dblock, context=context)
                        self._wrap_safe_axes = old
                        self._emit_axis_loop_close()
            else:
                # SoA: full SIMD body + scalar remainder.
                # Wrap in an extra scope so the bare ``int g_x`` decl
                # doesn't collide with subsequent dynamic-block emits at
                # the same nesting level (1-D programs with multiple
                # per-NC dyn loops produce two SIMD x-splits one after
                # the other in the same enclosing block).
                interior_cells = x_safe_hi - x_safe_lo + 1
                # Codegen-time eligibility / remainder decisions use
                # the x86 AVX-512 lane count (``self._simd_vw == 8``)
                # because that is the AVX-512 build target used to tune
                # this code path.
                # The emitted source uses ``hn::Lanes(d)`` (constexpr
                # in Highway) for the actual per-iteration stride --
                # so the SAME .cpp recompiled with -march for AVX-2
                # (4 lanes) or NEON (2 lanes) produces a correct
                # loop with a different stride.  A non-zero codegen-
                # time remainder is conservatively over-emitted: on
                # narrower ISAs the SIMD loop covers more iterations
                # so the remainder runs over fewer cells (or zero),
                # which is still correct.
                needs_remainder = interior_cells % vw != 0
                self._emit('// x = SIMD body' +
                           (' + scalar remainder' if needs_remainder
                            else '') +
                           ' (x-axis safe; modulo elided)')
                self._emit('{')
                self._indent += 1
                self._emit(f'int64_t g_x = {x_safe_lo};')
                # ``d.MaxLanes()`` is the constexpr lane count;
                # ``hn::Lanes(d)`` is runtime-only on some Highway
                # builds and would force the loop bound off the
                # constexpr path.
                self._emit('constexpr int VW = '
                           'static_cast<int>(d.MaxLanes());')
                self._emit('// SIMD body: V x VW cells/iter '
                           f'(VW = {vw} on AVX-512)')
                self._emit(f'for (; g_x + VW <= {x_safe_hi + 1}; '
                           f'g_x += VW) {{')
                self._indent += 1
                # Per-lane x coordinate.  Each V lane needs to see
                # x = g_x + lane_idx so any arithmetic involving the
                # spatial-x identifier (e.g. r = R_INNER + 1.0 * x)
                # gets the correct per-cell value.  ``hn::Iota(d,
                # start)`` produces lanes [start, start+1, ...,
                # start+VW-1] of the descriptor's element type
                # (double).  Lattice indexing still uses the scalar
                # g_x (it computes the address of the first lane,
                # then ``hn::LoadU`` slurps VW contiguous cells).
                self._emit(f'V gelb_xv = hn::Iota(d, '
                           f'static_cast<double>(g_x));')
                old_mode, old_axes = (self._simd_mode,
                                      self._wrap_safe_axes)
                self._simd_mode = 'vec8d'
                self._wrap_safe_axes = interior_safe_set
                self._emit_block_body(dblock, context=context)
                self._simd_mode = old_mode
                self._wrap_safe_axes = old_axes
                self._indent -= 1
                self._emit('}')
                # Scalar remainder of the SIMD body -- only emit when
                # the SIMD-eligible range isn't an exact multiple of
                # the vector width.  When ``(x_safe_hi - x_safe_lo + 1)
                # % vw == 0`` the SIMD body covers every cell exactly
                # and the remainder loop would run zero iterations;
                # eliding the emit keeps the generated source compact.
                if needs_remainder:
                    self._emit('// scalar remainder of SIMD body '
                               '(x-axis still safe)')
                    self._emit(f'for (; g_x <= {x_safe_hi}; ++g_x) {{')
                    self._indent += 1
                    old_axes = self._wrap_safe_axes
                    self._wrap_safe_axes = interior_safe_set
                    self._emit_block_body(dblock, context=context)
                    self._wrap_safe_axes = old_axes
                    self._indent -= 1
                    self._emit('}')
                # Close the extra scope wrapper opened above.
                self._indent -= 1
                self._emit('}')
        # scalar tail (x wraps).
        if x_safe_hi < bbox_x_hi:
            self._emit_axis_loop_open(
                'x', x_safe_hi + 1, bbox_x_hi,
                label="x = scalar tail (x-axis unsafe; "
                      "x reads use modulo wrap)")
            old = self._wrap_safe_axes
            self._wrap_safe_axes = outer_safe_set
            self._emit_block_body(dblock, context=context)
            self._wrap_safe_axes = old
            self._emit_axis_loop_close()

    def _emit_simd_lattice_load(self, lname: str, coord_strs: list,
                                df_idx_str: str,
                                x_offset: int | None) -> str:
        """Emit a SIMD lattice-input read for one DF at ``coord_strs``.

        Branches on storage layout:
        - **CBT cross-tile** path (``x_offset != 0`` AND lattice is CBT
          AND axis 0 is periodic / wrap-safe): emit
          ``hn::TwoTablesLookupLanes`` over two consecutive tile loads
          for the same df.  This is the same pattern
          ``_emit_upstream_dfs`` uses; mirroring it here closes the
          long-standing bug where explicit ``f.in[x +/- k, ...]`` reads
          in boundary kernels (Zou-He, MRT walls, reduced-gravity,
          etc.) silently spilled across df boundaries under CBT.
        - **Fallthrough** (SoA, scalar mode, or x-aligned reads): emit
          the previous ``hn::LoadU`` form (or the bare lvalue in scalar
          mode).  In SoA, ``LoadU`` with stride-1 contiguity along x is
          the natural CBT-free pattern.

        ``x_offset`` is the parsed integer offset of the x-coord
        relative to ``g_x``.  Pass ``None`` (or 0) when the offset
        cannot be determined as a literal -- the LoadU fallthrough
        is the correct emit in that case.
        """
        cbt_xshift = (
            self._simd_mode == 'vec8d'
            and self._use_cbt.get(lname, False)
            and x_offset is not None
            and x_offset != 0
            and (0 in self._wrap_safe_axes
                 or is_periodic(self._lattice_info, 0)))
        if not cbt_xshift:
            coord_idx = self._storage_subscript(
                coord_strs, df_idx_str=df_idx_str, lattice_name=lname)
            addr = f'{_lname(lname)}_storage[{_lname(lname)}_old]{coord_idx}'
            if self._simd_mode == 'vec8d':
                return f'hn::LoadU(d, &{addr})'
            return addr

        # CBT cross-tile sliding-window read.  ``g_x_tile`` is in scope
        # in every CBT iteration body (boundary and bulk).  Two
        # aligned ``hn::Load``s of (tile_lo, tile_hi) for the same df,
        # then a single ``hn::TwoTablesLookupLanes`` permute by
        # ``imm = x_offset mod 8`` (Python modulo gives a non-negative
        # result; for ``x_offset`` in {-1, +1} this is {7, 1}).
        #
        # Sign convention (CRITICAL): ``x_offset`` is the *source's*
        # x position relative to ``g_x``.  For ``f.in[x - 1, y, df]``
        # source = ``x - 1``, so ``x_offset == -1``; for
        # ``f.in[x + 1, y, df]`` source = ``x + 1``, so
        # ``x_offset == +1``.  ``_emit_upstream_dfs`` uses an
        # *inverse* convention -- its ``off_x`` is the velocity
        # component ``EX[i]``, so source = ``c_expr - off_x``.  The
        # formulas below are therefore mirrored relative to that
        # path:
        #   off_x > 0 (bulk: source at c_expr - off_x) <-> x_offset < 0
        #
        # Earlier versions of this helper accidentally used the bulk
        # path's velocity-component formulas verbatim, which silently
        # works on x-translation-invariant problems (couette,
        # poiseuille -- uniform in x) but produces wrong results on
        # x-varying ones (Shan-Chen, Sukop's taylor_dispersion solute
        # strip, Sukop's pressure-Zou-He inlet/outlet).
        imm_const = x_offset % _CBT_TILE
        if x_offset < 0:
            tile_lo_expr = '(g_x_tile - 1)'
            tile_hi_expr = 'g_x_tile'
        else:  # x_offset > 0
            tile_lo_expr = 'g_x_tile'
            tile_hi_expr = '(g_x_tile + 1)'
        non_x_spatial = spatial_subscript(coord_strs[1:])
        addr_lo = (f'{_lname(lname)}_storage[{_lname(lname)}_old]'
                   f'{non_x_spatial}[{tile_lo_expr}][{df_idx_str}][0]')
        addr_hi = (f'{_lname(lname)}_storage[{_lname(lname)}_old]'
                   f'{non_x_spatial}[{tile_hi_expr}][{df_idx_str}][0]')
        blend_indices = tuple(imm_const + k for k in range(_CBT_TILE))
        idx_arr_name = self._register_constexpr_array(
            'gelb_cbt_idx', 'int64_t', blend_indices)
        return (f'hn::TwoTablesLookupLanes(d, '
                f'hn::Load(d, &{addr_lo}), '
                f'hn::Load(d, &{addr_hi}), '
                f'hn::SetTableIndices(d, {idx_arr_name}))')
