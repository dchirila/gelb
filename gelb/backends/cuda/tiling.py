"""Shared-memory tiling and cache hints for gpu_cuda_cpp.

PMPP-style shared-memory tile loads with body substitution
(opt-in via --cuda-tiled), applicability checks, and the
__ldg/__stwt cache-hint rewrites (--cuda-ldg / --cuda-stwt).
"""

from __future__ import annotations

from gelb.backends.highway.common import (
    _lname,
    _TYPE_MAP,
)

from gelb.midware.ast_eval import (
    is_periodic,
)


class CudaTilingEmitMixin:
    """Mixin: see module docstring.  Assembled into
    ``CudaCppCodeGenerator`` (stage3_backend_gpu_cuda_cpp);
    must precede ``HighwayCodeGenerator`` in the MRO so the
    overrides here shadow the parent's CPU emission.
    """

    def _block_dims_for_dim(self) -> tuple[int, ...]:
        """Per-axis block dimensions matching ``_emit_launch_config``.

        Delegates to ``_block_dims_tuple`` so the tiling pass and
        the launcher always agree on the constexpr block dims.
        """
        return self._block_dims_tuple()

    def _shared_tile_bytes(self) -> int:
        """Total bytes/block of the dyn-kernel shared tile, summed
        over all lattices.  Currently ``--cuda-tiled`` is scoped to a
        single lattice, but this helper is kept lattice-agnostic so the
        scope can be relaxed without changing the size calculation.
        """
        bd = self._block_dims_for_dim()
        tile_cells = 1
        for b in bd:
            tile_cells *= (b + 2)
        total = 0
        for info in self._lattice_info.values():
            cpp_dtype = _TYPE_MAP[info['dtype']]
            elt_bytes = 8 if cpp_dtype == 'double' else 4
            total += tile_cells * info['q'] * elt_bytes
        return total

    def _cuda_tiling_applicable(self) -> tuple[bool, str]:
        """Scope check for ``--cuda-tiled``.

        Returns (ok, reason).  ``ok=True`` means the program is in
        scope; ``reason`` is informational (empty when ok).  When
        ``ok=False``, the dyn-kernel emit must fall back to the
        non-tiled path AND the user-facing error message should
        include ``reason`` so they understand why.

        Current requirements:
          * 2D only -- ncu-confirmed on an sm_89 RTX 4080 Laptop GPU
            (2026-05-07).  3D D3Q19's 91 KB/block shared
            budget collapses theoretical occupancy from 66.7 %
            (default) to 16.7 % (tiled, 1 block/SM cap), and
            achieved occupancy from 64 % to 16 %.  SM Compute
            throughput drops 84 % -> 48 %, kernel duration grows
            2.41 ms -> 4.20 ms (1.74x regression at N=128).
            Candidate 3D options: slab tiling along one axis (PMPP
            Sec. 8.3 alt), register tiling (PMPP Sec. 8.5), or per-Q
            tile splitting.
            2D D2Q9 is **already compute-bound at default** (SM
            Compute 81 %, DRAM 29 %, L2 hit 58 %): tiling cannot
            help (no DRAM bottleneck to recover) and adds 27 %
            barrier-stall overhead from __syncthreads.  Net 2D
            effect: -5 % (152 -> 159 us) -- neutral within sample
            noise.
          * all axes periodic -- non-periodic axes leave storage halo
            uninitialised, so unconditional tile-load reads garbage;
          * single lattice -- multi-lattice support is a pure shared-
            memory budgeting question (D3Q19 + D3Q7 Boussinesq is
            the canonical workload);
          * single dense NC -- multi-NC + non-dense bbox loads
            obstacle/halo cells into shared with no semantics, which
            is correct but wasteful AND makes per-axis storage-
            halo handling more involved;
          * periodic reach of at most one cell -- the tile holds one
            ghost cell per side.

        Future work can loosen all five constraints.
        """
        if self._d != 2:
            return False, (
                f"--cuda-tiled is currently 2D-only"
                f" (this program is {self._d}-D).  ncu-confirmed:"
                f" 91 KB/block shared collapses theoretical occupancy"
                f" to 16.7 % (1 block/SM on sm_89), starving latency"
                f" hiding -- TGV-3D BGK regresses 1.74x (2410 us ->"
                f" 4200 us).  Candidate future work: slab / register"
                f" tiling for 3D"
            )
        per = [is_periodic(self._lattice_info, i) for i in range(self._d)]
        if not all(per):
            return False, (
                f"axes {[i for i, p in enumerate(per) if not p]} are not"
                f" periodic -- tile-load clamping for"
                f" walls"
            )
        if len(self._lattice_info) != 1:
            return False, (
                f"multi-lattice ({len(self._lattice_info)} lattices)"
                f" -- Boussinesq D3Q19+D3Q7 needs"
                f" combined-tile shared-memory budgeting"
            )
        nc_count = len(self._geom.nc_info)
        if nc_count != 1:
            return False, (
                f"{nc_count} node classes -- tiling"
                f" with masked / multi-NC dispatch"
            )
        only_info = next(iter(self._geom.nc_info.values()))
        if not only_info.bbox_dense:
            return False, (
                "non-dense NC bbox -- tile load"
                " skipping obstacle cells"
            )
        reach = self._periodic_reach()
        if reach > 1:
            return False, (
                f"the program reads {reach} cells across a periodic"
                f" edge; the shared tile holds one ghost cell per side"
            )
        if self._write_reach() > 0:
            return False, (
                "the program writes at an offset; the tiled kernel"
                " stores only the cell it computes"
            )
        return True, ""

    def _emit_tile_load(self, lname_filter=None,
                         use_dynamic: bool = False) -> None:
        """Emit a cooperative shared-memory tile load + barrier for
        the dyn kernel.

        Each block loads its (block + halo) tile of all DFs from the
        OLD buffer into shared memory using a strided thread-loop,
        then ``__syncthreads()`` before the body's per-cell compute
        runs.

        Tile size matches ``_block_dims_for_dim()`` + 2 per axis
        (halo=1 each side; sufficient for D2Q9 / D3Q19 / D3Q27 since
        all stencil offsets are in {-1, 0, +1}^d).

        Storage indexing uses the lattice's ``[buf][Q][...y][x]``
        SoA shape; halo cells at storage indices 0 and N+1 on each
        axis are pre-populated by the per-axis halo kernels that
        ran just before this dyn kernel, so ``g_<axis>_base + local
        _<axis>`` maps directly into storage indices for both
        interior + boundary blocks.

        Args:
            lname_filter: optional iterable of lattice names; when
                set, only those lattices get tile-loaded.  ``None``
                (default) loads every lattice in
                ``self._lattice_info``.
        """
        bd = self._block_dims_for_dim()
        tile_dims = tuple(b + 2 for b in bd)
        tile_cells = 1
        for td in tile_dims:
            tile_cells *= td
        nthreads = 1
        for b in bd:
            nthreads *= b
        storage_sizes = self._storage_sizes()  # fastest-axis first

        # Linear thread index inside the block (used as the strided
        # load's starting offset).  Layout: tid = ((z*BY)+y)*BX + x.
        if self._d == 1:
            self._emit('// Tile-load: cooperative load of (block+halo)'
                       ' tile into shared memory.')
            self._emit('int gelb_tid = threadIdx.x;')
        elif self._d == 2:
            self._emit('// Tile-load: cooperative load of (block+halo)'
                       ' tile into shared memory.')
            self._emit('int gelb_tid = threadIdx.y * blockDim.x'
                       ' + threadIdx.x;')
        else:
            self._emit('// Tile-load: cooperative load of (block+halo)'
                       ' tile into shared memory.')
            self._emit('int gelb_tid = (threadIdx.z * blockDim.y'
                       ' + threadIdx.y) * blockDim.x + threadIdx.x;')

        # When the per-block tile exceeds the sm_89 default static-
        # shared cap (48 KB), ptxas rejects ``__shared__ T arr[...]``
        # at compile time even with a runtime carveout opt-in.  The
        # canonical workaround is dynamic shared memory: declare
        # ``extern __shared__ char raw[]``, then reinterpret_cast a
        # typed pointer with the trailing dimensions baked in.  The
        # caller is responsible for (a) passing the size as the
        # third launch arg and (b) calling
        # ``cudaFuncSetAttribute(..., cudaFuncAttributeMaxDynamic
        # SharedMemorySize, ...)`` once on first launch.
        if use_dynamic:
            # Single buffer, partitioned by lattice via byte offsets
            # at cast time.  In the current single-lattice tiled scope,
            # there's exactly one cast.
            self._emit('extern __shared__ unsigned char'
                       ' gelb_shared_raw[];')
            shared_offset_bytes = 0
        for lname, info in self._lattice_info.items():
            if lname_filter is not None and lname not in lname_filter:
                continue
            q = info['q']
            cpp_dtype = _TYPE_MAP[info['dtype']]
            # __shared__ tile dims slowest-to-fastest:
            # 1D: [Q][BX+2]; 2D: [Q][BY+2][BX+2];
            # 3D: [Q][BZ+2][BY+2][BX+2].  Matches the global
            # storage's [...y][x] orientation so the body
            # substitution stays mechanical.
            if self._d == 1:
                sh_dims = f'[{q}][{tile_dims[0]}]'
                ptr_trail = f'[{tile_dims[0]}]'
            elif self._d == 2:
                sh_dims = f'[{q}][{tile_dims[1]}][{tile_dims[0]}]'
                ptr_trail = f'[{tile_dims[1]}][{tile_dims[0]}]'
            else:
                sh_dims = (f'[{q}][{tile_dims[2]}]'
                           f'[{tile_dims[1]}][{tile_dims[0]}]')
                ptr_trail = (f'[{tile_dims[2]}][{tile_dims[1]}]'
                             f'[{tile_dims[0]}]')
            if use_dynamic:
                # Reinterpret a per-lattice slice of the dynamic
                # shared buffer as the typed multi-D array.
                # ``s_<lname>[df][...lz...][lx]`` then works
                # exactly as for the static case, so the body
                # substitution stays mechanical.
                elt_bytes = 8 if cpp_dtype == 'double' else 4
                lattice_bytes = tile_cells * q * elt_bytes
                self._emit(
                    f'auto s_{lname} = reinterpret_cast<{cpp_dtype}'
                    f' (*){ptr_trail}>(&gelb_shared_raw'
                    f'[{shared_offset_bytes}]);')
                shared_offset_bytes += lattice_bytes
            else:
                self._emit(f'__shared__ {cpp_dtype} s_{lname}{sh_dims};')
            # Strided cooperative load.  Each thread visits
            # ceil(tile_cells / nthreads) cells; the bounds
            # check ``gelb_s* < storage_size`` skips ceil-div
            # overshoot (irrelevant for grids that are exact
            # block-multiples but mandatory for arbitrary sizes).
            self._emit(
                f'for (int gelb_i = gelb_tid; gelb_i < {tile_cells};'
                f' gelb_i += {nthreads}) {{')
            self._indent += 1
            if self._d == 1:
                self._emit('int gelb_lx = gelb_i;')
                self._emit('int gelb_sx = blockIdx.x * blockDim.x'
                           ' + gelb_lx;')
                self._emit(f'if (gelb_sx >= {storage_sizes[0]}) continue;')
            elif self._d == 2:
                self._emit(f'int gelb_lx = gelb_i % {tile_dims[0]};')
                self._emit(f'int gelb_ly = gelb_i / {tile_dims[0]};')
                self._emit('int gelb_sx = blockIdx.x * blockDim.x'
                           ' + gelb_lx;')
                self._emit('int gelb_sy = blockIdx.y * blockDim.y'
                           ' + gelb_ly;')
                self._emit(f'if (gelb_sx >= {storage_sizes[0]}'
                           f' || gelb_sy >= {storage_sizes[1]}) continue;')
            else:
                self._emit(f'int gelb_lx = gelb_i % {tile_dims[0]};')
                self._emit(f'int gelb_lyz = gelb_i / {tile_dims[0]};')
                self._emit(f'int gelb_ly = gelb_lyz % {tile_dims[1]};')
                self._emit(f'int gelb_lz = gelb_lyz / {tile_dims[1]};')
                self._emit('int gelb_sx = blockIdx.x * blockDim.x'
                           ' + gelb_lx;')
                self._emit('int gelb_sy = blockIdx.y * blockDim.y'
                           ' + gelb_ly;')
                self._emit('int gelb_sz = blockIdx.z * blockDim.z'
                           ' + gelb_lz;')
                self._emit(f'if (gelb_sx >= {storage_sizes[0]}'
                           f' || gelb_sy >= {storage_sizes[1]}'
                           f' || gelb_sz >= {storage_sizes[2]}) continue;')
            # Per-cell DF copy.
            if self._d == 1:
                shared_subs = '[gelb_df][gelb_lx]'
                global_subs = '[gelb_df][gelb_sx]'
            elif self._d == 2:
                shared_subs = '[gelb_df][gelb_ly][gelb_lx]'
                global_subs = '[gelb_df][gelb_sy][gelb_sx]'
            else:
                shared_subs = '[gelb_df][gelb_lz][gelb_ly][gelb_lx]'
                global_subs = '[gelb_df][gelb_sz][gelb_sy][gelb_sx]'
            self._emit('#pragma unroll')
            self._emit(f'for (int gelb_df = 0; gelb_df < {q};'
                       f' ++gelb_df) {{')
            self._indent += 1
            self._emit(
                f's_{lname}{shared_subs} ='
                f' {_lname(lname)}_storage[{_lname(lname)}_old]{global_subs};')
            self._indent -= 1
            self._emit('}')
            self._indent -= 1
            self._emit('}')
        self._emit('__syncthreads();')

    def _apply_tile_substitution(self, body_start: int,
                                  body_end: int) -> None:
        """Redirect OLD-buffer reads in the captured dyn-kernel body
        to the shared-memory tile.

        For each line in ``[body_start, body_end]``:
          * walk every ``g_<lname>_storage[g_<lname>_old]<chained
            subscripts>`` anchor (same bracket-depth walker as
            ``_apply_cache_hints``);
          * replace the prefix with ``s_<lname>``;
          * inside the matched subscripts, substitute
            ``g_x -> threadIdx.x`` (and ``g_y``, ``g_z`` for higher
            dims) using word-boundary regex so non-subscript usages
            of ``g_x`` (e.g. cell-center coord computations) stay
            untouched.

        OLD-buffer WRITES (rare) and NEW-buffer accesses are left
        verbatim -- only stencil reads of the old buffer benefit
        from the shared-memory cache.
        """
        if not self._cuda_tiled:
            return
        import re
        anchor_re = re.compile(r'g0_\d+_(\w+)_storage\[g0_\d+_\1_(old|new)\]')
        word_subs = [
            (re.compile(r'\bg_x\b'), 'threadIdx.x'),
            (re.compile(r'\bg_y\b'), 'threadIdx.y'),
            (re.compile(r'\bg_z\b'), 'threadIdx.z'),
        ]
        for j in range(body_start, body_end):
            line = self._device_decls[j]
            if 'g0_' not in line:
                continue
            self._device_decls[j] = self._tile_substitute_line(
                line, anchor_re, word_subs)

    def _tile_substitute_line(self, line: str, anchor_re,
                                word_subs) -> str:
        """One-line substitution for ``_apply_tile_substitution``."""
        out_parts = []
        pos = 0
        while pos < len(line):
            m = anchor_re.search(line, pos)
            if not m:
                out_parts.append(line[pos:])
                break
            lname = m.group(1)
            buf_kind = m.group(2)
            out_parts.append(line[pos:m.start()])
            # Walk subscript chain past the anchor.
            end = m.end()
            unbalanced = False
            while end < len(line) and line[end] == '[':
                depth = 1
                end += 1
                while end < len(line) and depth > 0:
                    if line[end] == '[':
                        depth += 1
                    elif line[end] == ']':
                        depth -= 1
                    end += 1
                if depth != 0:
                    unbalanced = True
                    break
            if unbalanced:
                # Bail out -- emit verbatim from the anchor to EOL
                # (this branch shouldn't fire on well-formed emit;
                # it's belt-and-braces against a future emit change).
                out_parts.append(line[m.start():])
                break
            if buf_kind == 'old':
                subs = line[m.end():end]
                for rx, repl in word_subs:
                    subs = rx.sub(repl, subs)
                out_parts.append(f's_{lname}{subs}')
            else:
                out_parts.append(line[m.start():end])
            pos = end
        return ''.join(out_parts)

    def _apply_cache_hints(self, body_start: int, body_end: int) -> None:
        """Wrap OLD-buffer reads in ``__ldg(&...)`` and convert
        NEW-buffer writes to ``__stwt(&..., value)`` for the dyn
        kernel's body lines, when the corresponding flag is on.

        Implementation: walk each line, find every
        ``g_<lname>_storage[g_<ln>_(old|new)]<subscripts>``
        anchor, then walk subscripts with bracket-depth counting
        (handles nested patterns like
        ``g_f_storage[g_f_old][gelb_opp_EX_EY[gelb_df]][...]``
        that LDC's bounce-back emit produces).  Determine
        read-vs-write by peeking at the next non-whitespace char
        (``=`` followed by non-``=`` => assignment LHS = write).
        """
        if not (self._cuda_ldg or self._cuda_stwt):
            return
        import re

        anchor_re = re.compile(
            r'g0_\d+_(\w+)_storage\[g0_\d+_\1_(old|new)\]')

        for j in range(body_start, body_end):
            line = self._device_decls[j]
            if ('__ldg' in line) or ('__stwt' in line):
                continue  # avoid double-wrap on re-applied lines
            line = self._cache_hint_line(line, anchor_re)
            self._device_decls[j] = line

    def _cache_hint_line(self, line: str, anchor_re) -> str:
        """One-line transformation for ``_apply_cache_hints``.

        Walks the line, finds each ``g_<lname>_storage[g_<ln>_old]``
        or ``[g_<ln>_new]`` anchor, then matches its subscript
        chain (handles nested brackets), then rewrites read
        accesses to ``__ldg(&...)`` and write accesses to
        ``__stwt(&..., expr)`` when the relevant flag is on.
        """
        out_parts = []
        pos = 0
        while pos < len(line):
            m = anchor_re.search(line, pos)
            if not m:
                out_parts.append(line[pos:])
                break
            buf_kind = m.group(2)  # 'old' or 'new'
            # Append everything before the anchor verbatim.
            out_parts.append(line[pos:m.start()])
            # Walk subscript chain after the anchor with balanced-
            # bracket depth counting.
            end = m.end()
            while end < len(line) and line[end] == '[':
                depth = 1
                end += 1
                while end < len(line) and depth > 0:
                    if line[end] == '[':
                        depth += 1
                    elif line[end] == ']':
                        depth -= 1
                    end += 1
                if depth != 0:
                    # Unbalanced -- give up on this line; emit verbatim.
                    out_parts.append(line[m.start():])
                    return ''.join(out_parts)
            # ``ref`` is the full ``g_X_storage[g_X_buf]<subs>``.
            ref = line[m.start():end]
            # Read vs write: peek next non-whitespace char.
            ws = end
            while ws < len(line) and line[ws].isspace():
                ws += 1
            is_write = (ws < len(line) and line[ws] == '='
                        and (ws + 1 >= len(line)
                             or line[ws + 1] != '='))
            if is_write and buf_kind == 'new' and self._cuda_stwt:
                # Capture the RHS expression up to the next ``;``.
                rhs_end = line.find(';', ws + 1)
                if rhs_end == -1:
                    out_parts.append(line[m.start():])
                    pos = len(line)
                    continue
                rhs = line[ws + 1:rhs_end].strip()
                out_parts.append(f'__stwt(&{ref}, {rhs});')
                pos = rhs_end + 1
            elif (not is_write) and buf_kind == 'old' and self._cuda_ldg:
                out_parts.append(f'__ldg(&{ref})')
                pos = end
            else:
                # Read-of-new or write-of-old (rare): leave as-is.
                out_parts.append(ref)
                pos = end
        return ''.join(out_parts)
