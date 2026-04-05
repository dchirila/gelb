#!/usr/bin/env python3

"""
GeLB Midware Stage 2 - AST Transformations and Optimizations

This module provides individual midware stage functions that can be called
explicitly from the main compiler driver. Each function represents a specific
optimization or transformation pass.

Functions are organized in the order they should be applied:
1. validate_midware_input() - Input validation
2. fold_constants() - Constant folding optimization
3. validate_division_by_zero() - Division by zero detection
4. extract_stencils() - Stencil extraction
5. validate_initializer_coverage() - Initializer DF coverage check
6. validate_boundary_access() - Out-of-bounds access detection
7. validate_cross_nc_df_coverage() - Cross-NC neighbour-read coverage
   (needs ResolvedGeometry; invoked from the geometry-resolution path)
8. warn_writeonly_dynamics() - Write-only dynamic block warnings
9. warn_unused_lattices() - Unused lattice warnings
10. resolve_geometry() - Geometry resolution (node-class map)

Backend-independent analysis modules:
- gelb.midware.ast_eval -- compile-time expression evaluator
- gelb.midware.geometry -- geometry resolution (paint -> NC map)
"""


from gelb.frontend.implicit_symbols import COORDINATE_SYMBOL_NAMES
from gelb.gelb_ast.ASTNodes import Program_N
from gelb.midware.ConstantFoldingVisitor import ConstantFoldingVisitor
from gelb.midware.DivisionByZeroValidator import DivisionByZeroValidator
from gelb.midware.LocalConstantLowering import (
    lower_local_constants as _lower_local_constants,
)
from gelb.midware.StencilArgValidator import (
    validate_streaming_intrinsic_args,
)
from gelb.midware.StencilExtractionVisitor import StencilExtractionVisitor
from gelb.midware.stencil import ProgramStencils
from gelb.utils.exceptions import GeLBExStencilError


def validate_midware_input(ast):
    """
    Validate that the AST is ready for midware processing.
    
    Args:
        ast (Program_N): The AST to validate
        
    Raises:
        TypeError: If ast is not the expected type
        AttributeError: If required AST attributes are missing
    """
    if not isinstance(ast, Program_N):
        raise TypeError(f"Expected Program_N, got {type(ast).__name__}")
    
    # Check that essential attributes exist
    required_attrs = [
        'global_constants', 'lattices', 'initializers', 
        'dynamics', 'gauges', 'node_classes', 'geometry'
    ]
    
    for attr in required_attrs:
        if not hasattr(ast, attr):
            raise AttributeError(f"AST missing required attribute: {attr}")


def fold_constants(ast):
    """
    Apply constant folding optimization to the AST.
    
    Evaluates constant expressions at compile time and replaces them
    with their computed literal values.
    
    Args:
        ast (Program_N): The AST to optimize
        
    Returns:
        Program_N: The AST with constant expressions folded
    """
    folder = ConstantFoldingVisitor()
    return folder.visit(ast, ast)


def lower_local_constants(ast):
    """
    Rewrite every block-local ``const`` as a typed declaration with its
    value, so that the backends see one kind of local declaration.

    Must run after:
    - Constant folding (the value is as folded; uses are substituted)
    - The constant-assignment validation of the frontend (immutability)
    """
    return _lower_local_constants(ast)


def validate_division_by_zero(ast):
    """
    Check for division by zero operations in the AST.
    
    Must run AFTER constant folding and propagation to catch all
    compile-time detectable division by zero errors, including:
    - Direct literals: 1 / 0
    - Constants: const int ZERO = 0; ... 1 / ZERO
    - Expressions: const int ZERO = 1 - 1; ... 1 / ZERO
    
    Args:
        ast (Program_N): The AST to validate
        
    Returns:
        Program_N: The validated AST
        
    Raises:
        GeLBExTypeError: If division by zero is detected
    """
    validator = DivisionByZeroValidator()
    return validator.visit(ast, ast)


def extract_stencils(ast):
    """
    Extract input/output stencils from all blocks in the AST.

    Should run AFTER constant folding so that literal offsets (e.g., x-1)
    are fully resolved.

    Args:
        ast (Program_N): The AST to analyze

    Returns:
        ProgramStencils: Complete stencil analysis result
    """
    visitor = StencilExtractionVisitor()
    return visitor.extract(ast)


def validate_initializer_coverage(stencils: ProgramStencils) -> None:
    """
    Validate that each node class's initializer writes all DFs of every
    lattice it writes.

    This is the lattice-level rule ("an initializer that sets a lattice
    sets all of it"); whether every DF a block *reads* is defined, at
    every cell and in both phases, is proved by
    ``validate_cross_nc_df_coverage`` on the resolved geometry.  Two
    node classes are outside this rule: a ``masked`` one, whose storage
    is zeroed in both buffers before the initializers run and stays
    zero wherever none replaces it, and one whose lattice some
    initializer pushes into.

    Should run AFTER stencil extraction.

    Args:
        stencils: Extracted program stencils.

    Raises:
        GeLBExStencilError: If an initializer does not cover all DFs.
    """
    # Lattices some initializer writes at an offset ("pushes" into
    # other cells): their per-cell coverage is proved by
    # validate_cross_nc_df_coverage on the resolved geometry, where
    # the pushes land.  Here only the local rule applies.
    pushed = {
        w.lattice_name
        for block in stencils.blocks.values()
        if block.block_type == "initializer"
        for w in block.writes if any(w.spatial_offsets)}

    for nc in stencils.node_classes.values():
        init_block = stencils.blocks.get(nc.initializer)
        if init_block is None or nc.masked:
            continue

        # Group initializer writes by lattice
        written_by_lattice: dict[str, set[int | None]] = {}
        for access in init_block.writes:
            written_by_lattice.setdefault(access.lattice_name, set()).add(
                access.df_index
            )

        # Check coverage for each written lattice
        for lat_name, written_dfs in written_by_lattice.items():
            if None in written_dfs:
                continue  # full-range write covers all DFs
            if lat_name in pushed:
                continue  # proved per cell, pushes included
            lat_meta = stencils.lattices.get(lat_name)
            if lat_meta is None:
                continue
            expected = set(range(lat_meta.q))
            missing = sorted(expected - written_dfs)
            if missing:
                raise GeLBExStencilError(
                    f"Initializer '{nc.initializer}' (for node class "
                    f"'{nc.name}') does not write all DFs of lattice "
                    f"'{lat_name}': missing DFs {missing}",
                    "Add write statements for the missing distribution "
                    "functions, or use the full-range syntax "
                    "f.out[...|:] to write all DFs at once.",
                    source_line=init_block.source_line,
                    source_end_line=init_block.source_end_line,
                )


def validate_boundary_access(stencils: ProgramStencils, geometry) -> None:
    """
    Validate that non-zero stencil offsets don't cause out-of-bounds access.

    For non-periodic dimensions, checks that no node class is painted at
    boundary positions where its blocks' stencil offsets would read or
    write outside the grid.  Every block kind is checked, initializers
    included (user manual chapter 3, writes at an offset).

    The check uses the resolved class map, the one the backends use: it
    is the only way to see the classes a ``where`` predicate paints, and
    a class a later paint overrides at the wall is not there any more.
    Every compilation runs it on that map.

    Should run AFTER stencil extraction and geometry resolution.

    Args:
        stencils: Extracted program stencils.
        geometry: ``ResolvedGeometry``.

    Raises:
        GeLBExStencilError: If out-of-bounds access is detected.
    """
    for nc in stencils.node_classes.values():
        for block_name in (nc.initializer, nc.dynamic, nc.gauge):
            block = stencils.blocks.get(block_name)
            if block is None:
                continue

            for access in block.reads + block.writes:
                if access.guarded:
                    continue
                lat_meta = stencils.lattices.get(access.lattice_name)
                if lat_meta is None:
                    continue
                if lat_meta.grid_size is None or lat_meta.periodic is None:
                    continue

                for d_idx, offset in enumerate(access.spatial_offsets):
                    if offset == 0:
                        continue
                    if d_idx >= len(lat_meta.periodic):
                        continue
                    if lat_meta.periodic[d_idx]:
                        continue

                    # Non-periodic dimension with non-zero offset
                    gs = lat_meta.grid_size[d_idx]
                    if offset < 0:
                        unsafe = range(0, abs(offset))
                    else:
                        unsafe = range(gs - offset, gs)

                    if _nc_at_boundary(geometry, nc.name, d_idx, unsafe):
                        dim_name = COORDINATE_SYMBOL_NAMES[d_idx] \
                            if d_idx < 3 else f"dim{d_idx}"
                        raise GeLBExStencilError(
                            f"Out-of-bounds lattice access: block "
                            f"'{block_name}' (for node class '{nc.name}') "
                            f"reads/writes lattice '{access.lattice_name}' "
                            f"at offset {offset:+d} in {dim_name}, but "
                            f"'{nc.name}' is painted at boundary position(s) "
                            f"where this would access outside the grid",
                            f"Either make the {dim_name}-dimension periodic, "
                            f"or avoid painting '{nc.name}' at the affected "
                            f"boundary, or use a different block for boundary "
                            f"nodes.",
                            source_line=block.source_line,
                            source_end_line=block.source_end_line,
                        )


def _nc_at_boundary(geometry, nc_name, fixed_dim, unsafe_positions):
    """Whether ``nc_name`` occupies any cell whose coordinate along
    ``fixed_dim`` is in ``unsafe_positions``, on the resolved map."""
    import numpy as np
    info = geometry.nc_info.get(nc_name)
    if info is None or fixed_dim >= geometry.ndim:
        return False
    positions = [p for p in unsafe_positions
                 if 0 <= p < geometry.grid_sizes[fixed_dim]]
    if not positions:
        return False
    band = np.take(geometry.nc_map == info.nc_id, positions,
                   axis=fixed_dim)
    return bool(band.any())


def _grid_masks(geometry):
    """Per-node-class boolean masks over the grid, plus the union masks of
    static (no dynamic) and masked node classes."""
    import numpy as np
    masks = {name: (geometry.nc_map == info.nc_id)
             for name, info in geometry.nc_info.items()}
    static = np.zeros(geometry.nc_map.shape, dtype=bool)
    masked = np.zeros(geometry.nc_map.shape, dtype=bool)
    for name, info in geometry.nc_info.items():
        if info.dynamic is None:
            static |= masks[name]
        if info.masked:
            masked |= masks[name]
    return masks, static, masked


def _normalized_offset(offset, geometry):
    """Offsets that reach the same cells are one writer: on a periodic
    axis an offset counts modulo the axis size."""
    return tuple(
        (off % geometry.grid_sizes[ax]) if geometry.periodic[ax] else off
        for ax, off in enumerate(offset))


def _shift_mask(mask, offset, geometry):
    """Cells reached from the cells of ``mask`` by ``offset``: the
    destinations of a write, or the cells a read lands on.  On a wall
    axis, cells whose target leaves the grid drop out."""
    import numpy as np
    result = mask
    for ax, off in enumerate(offset):
        if off == 0:
            continue
        n = geometry.grid_sizes[ax]
        result = np.roll(result, off, axis=ax)
        if not geometry.periodic[ax]:
            keep = np.ones(n, dtype=bool)
            if off > 0:
                keep[:off] = False       # came from the wrap-around
            else:
                keep[n + off:] = False
            shape = [1] * geometry.ndim
            shape[ax] = n
            result = result & keep.reshape(shape)
    return result


def _fmt_offset(offset) -> str:
    return '(' + ', '.join(f'{o:+d}' if o else '0' for o in offset) + ')'


def _fmt_cell(index) -> str:
    return '(' + ', '.join(str(int(c)) for c in index) + ')'


def _needed_dfs(read_dfs: set, q: int) -> set:
    if None in read_dfs:
        return set(range(q))
    return {df for df in read_dfs if df is not None}


def validate_write_destinations(stencils: ProgramStencils, geometry) -> None:
    """
    Validate the destinations of lattice writes (user manual chapter 3,
    writes at an offset).  A write ``u.out[x + k | d]`` executed for cell
    ``c`` sets DF ``d`` of cell ``c + k``, wrapped on periodic axes; a
    write off a wall is caught by ``validate_boundary_access``.  Here:

    * a write may not land in a cell of a **static** node class or of
      an **empty masked** node class, in any phase; the destination
      is taken after wrapping, so an offset that is a multiple of a
      periodic axis's size is the cell's own write;
    * per phase (the initialization, or one time step) and per
      (destination cell, lattice, DF), at most one **source cell** may
      write.  Statements from the same source cell are ordered and
      fine; offsets congruent modulo a periodic axis are the same source
      cell.  Two source cells writing one cell would race under OpenMP
      and CUDA, so it is an error naming both writers and a cell.

    Should run AFTER geometry resolution and the wall check.
    """
    import numpy as np

    masks, _static, _masked = _grid_masks(geometry)
    id_to_name = {info.nc_id: name for name, info in geometry.nc_info.items()}

    def _block(bname):
        return stencils.blocks.get(bname) if bname else None

    # --- forbidden destination classes: static, empty masked -----------
    for name, info in geometry.nc_info.items():
        for bname in (info.initializer, info.dynamic):
            block = _block(bname)
            if block is None:
                continue
            seen = set()
            for w in block.writes:
                # An offset that is a multiple of a periodic axis's size
                # reaches the source cell itself: the offset is
                # normalized modulo the periodic axes before it counts.
                off = _normalized_offset(w.spatial_offsets, geometry)
                if not any(off) or (w.lattice_name, off) in seen:
                    continue
                seen.add((w.lattice_name, off))
                dest = _shift_mask(masks[name], off, geometry)
                for d_id in np.unique(geometry.nc_map[dest]):
                    d_name = id_to_name[int(d_id)]
                    d_info = geometry.nc_info[d_name]
                    if d_info.dynamic is None and not (
                            d_info.initializer is None and d_info.masked):
                        raise GeLBExStencilError(
                            f"Block '{bname}' (for node class '{name}') writes"
                            f" lattice '{w.lattice_name}' at offset"
                            f" {_fmt_offset(w.spatial_offsets)} into cells"
                            f" painted '{d_name}', a static node class",
                            f"While a cell belongs to a static node class its"
                            f" values are those its initializer set: write"
                            f" them in '{d_name}''s own initializer, or give"
                            f" '{d_name}' a dynamic.",
                            source_line=block.source_line,
                            source_end_line=block.source_end_line)
                    if d_info.initializer is None and d_info.dynamic is None:
                        raise GeLBExStencilError(
                            f"Block '{bname}' (for node class '{name}') writes"
                            f" lattice '{w.lattice_name}' at offset"
                            f" {_fmt_offset(w.spatial_offsets)} into cells"
                            f" painted '{d_name}', an empty masked node class",
                            f"An empty masked node class holds zero DFs by"
                            f" language guarantee and accepts no writes; give"
                            f" '{d_name}' an initializer and a dynamic, or keep"
                            f" '{name}' from writing into it.",
                            source_line=block.source_line,
                            source_end_line=block.source_end_line)

    # --- one source cell per (destination cell, lattice, DF, phase) ---
    for phase, attr in (('initialization', 'initializer'), ('time step', 'dynamic')):
        writers: dict[tuple, list] = {}     # (lattice, df) -> [(nc, offset, block)]
        for name, info in geometry.nc_info.items():
            block = _block(getattr(info, attr))
            if block is None:
                continue
            seen = set()
            for w in block.writes:
                lat_meta = stencils.lattices.get(w.lattice_name)
                if lat_meta is None:
                    continue
                dfs = (range(lat_meta.q) if w.df_index is None else (w.df_index,))
                off = _normalized_offset(w.spatial_offsets, geometry)
                for df in dfs:
                    key = (name, off, w.lattice_name, df)
                    if key in seen:
                        continue
                    seen.add(key)
                    writers.setdefault((w.lattice_name, df), []).append(
                        (name, w.spatial_offsets, off, block))
        for (lat, df), entries in writers.items():
            if len(entries) < 2:
                continue
            count = np.zeros(geometry.nc_map.shape, dtype=np.int32)
            covers = []
            for name, offset, off, block in entries:
                dest = _shift_mask(masks[name], offset, geometry)
                covers.append(dest)
                count += dest
            if count.max() <= 1:
                continue
            cell = tuple(int(c) for c in np.argwhere(count > 1)[0])
            hits = [e for e, dest in zip(entries, covers) if dest[cell]]
            (n1, o1, _, b1), (n2, o2, _, b2) = hits[0], hits[1]
            raise GeLBExStencilError(
                f"Two source cells write DF {df} of lattice '{lat}' at cell"
                f" {_fmt_cell(cell)} in the same {phase}: block"
                f" '{b1.block_name}' (for node class '{n1}') at offset"
                f" {_fmt_offset(o1)} and block '{b2.block_name}' (for node"
                f" class '{n2}') at offset {_fmt_offset(o2)}",
                "A cell's DF may be written by at most one source cell per"
                " phase: two writers would race across threads. Several"
                " statements of one block at the same offset are fine (the"
                " later wins); make the writes of different source cells"
                " land on different cells or different DFs.",
                source_line=b1.source_line,
                source_end_line=b1.source_end_line)


def validate_cross_nc_df_coverage(stencils: ProgramStencils,
                                  geometry) -> None:
    """
    Validate that every DF a block reads has a defined value, at t = 0 and
    after every buffer swap, at every cell it is read from.

    The two buffers of a lattice alternate, so a DF has a defined value at
    a cell only if something writes it there in the right phase:

    * **initial** -- the t = 0 gauge and the first dynamic step read the
      buffer the initializers filled: the DF must be written at that cell
      by an *initializer* (the cell's own, or one pushing into it);
    * **recurring** -- every later read sees the buffer the previous
      dynamic pass filled: the DF must be written at that cell by a
      *dynamic* every step (its own, or one pushing into it).  Cells of a
      *static* node class keep their initializer values in both buffers.

    Reads are checked at the cells they land on: the reader's own cells
    for offset 0, and the cells an offset reaches, wrapped on periodic
    axes; on a wall axis, reads that leave the grid clamp at the read site
    (``validate_boundary_access`` covers genuinely unsafe cases) and are
    not checked here. Guarded intrinsic reads instead fall back to the
    reader's own cell, whose DF is checked as well. The proof is per cell,
    so a push that lands on
    only some cells of a node class counts only there.

    Masked storage starts at zero: at a cell of a ``masked`` node class a
    DF no initializer writes is zero at t = 0 (whether or not a dynamic
    writes it later), and one nothing ever writes stays zero, so both
    phases are covered (the empty ``SOLID() masked`` marker is the
    limiting case).  A DF a masked class's initializer does write follows
    the ordinary recurring rule.

    Should run AFTER geometry resolution (needs the painted ``nc_map``).

    Raises:
        GeLBExStencilError: If a read is not covered.
    """
    import numpy as np

    masks, static_mask, masked_mask = _grid_masks(geometry)
    id_to_name = {info.nc_id: name for name, info in geometry.nc_info.items()}
    shape = geometry.nc_map.shape

    # --- per (phase, lattice, df): the cells some block writes -----------
    writes: dict[tuple, list] = {}   # (phase, lattice, df) -> [(nc, offset)]
    for name, info in geometry.nc_info.items():
        for phase, bname in (('init', info.initializer), ('dyn', info.dynamic)):
            block = stencils.blocks.get(bname) if bname else None
            if block is None:
                continue
            for w in block.writes:
                lat_meta = stencils.lattices.get(w.lattice_name)
                if lat_meta is None:
                    continue
                dfs = range(lat_meta.q) if w.df_index is None else (w.df_index,)
                for df in dfs:
                    writes.setdefault((phase, w.lattice_name, df), []).append(
                        (name, w.spatial_offsets))

    cache: dict[tuple, object] = {}

    def _written(phase, lat, df):
        key = (phase, lat, df)
        if key not in cache:
            acc = np.zeros(shape, dtype=bool)
            for name, offset in writes.get(key, ()):
                acc |= _shift_mask(masks[name], offset, geometry)
            cache[key] = acc
        return cache[key]

    def _ok(lat, df):
        init = _written('init', lat, df)
        dyn = _written('dyn', lat, df)
        never = ~init & ~dyn
        # Masked storage is zeroed in both buffers before the initializers
        # run, so it starts at zero wherever none replaces it, whatever a
        # dynamic writes later, and stays zero where nothing ever writes it.
        ok_initial = init | masked_mask
        ok_recurring = dyn | (init & static_mask) | (masked_mask & never)
        return ok_initial, ok_recurring, init, dyn, never

    def _report(block, bname, name, lat, offset, df_cells):
        """``df_cells``: {df: (bad_initial_cells, bad_recurring_cells)}."""
        never_dfs, init_only, dyn_only = [], [], []
        example = {}
        for df, (bad_i, bad_r) in sorted(df_cells.items()):
            _, _, init, dyn, never = _ok(lat, df)
            bad = bad_i | bad_r
            cell = tuple(int(c) for c in np.argwhere(bad)[0])
            if never[cell]:
                never_dfs.append(df); example.setdefault('never', cell)
            elif init[cell] and not dyn[cell]:
                init_only.append(df); example.setdefault('init', cell)
            else:
                dyn_only.append(df); example.setdefault('dyn', cell)
        own = not any(offset)
        common = dict(source_line=block.source_line,
                      source_end_line=block.source_end_line)

        def _where(cell):
            d_name = id_to_name[int(geometry.nc_map[cell])]
            if own:
                return d_name, f"at its own cells (e.g. {_fmt_cell(cell)})"
            return d_name, (f"at offset {_fmt_offset(offset)} from cells"
                            f" painted '{d_name}' (e.g. {_fmt_cell(cell)})")

        if never_dfs:
            d_name, where = _where(example['never'])
            if own:
                raise GeLBExStencilError(
                    f"Block '{bname}' (for node class '{name}') reads lattice"
                    f" '{lat}', but no block of '{name}' ever writes DF(s)"
                    f" {never_dfs} of it",
                    f"Add initialization for lattice '{lat}' in node class"
                    f" '{name}', or read a lattice the node class computes.",
                    **common)
            raise GeLBExStencilError(
                f"Block '{bname}' (for node class '{name}')"
                f" reads lattice '{lat}' {where}, but"
                f" '{d_name}' never writes DF(s)"
                f" {never_dfs} of '{lat}'",
                f"Write the missing DFs in '{d_name}''s"
                f" initializer or dynamic, mark '{d_name}'"
                f" masked (its cells then hold zero DFs"
                f" by language guarantee), or keep"
                f" '{name}' from bordering '{d_name}'.",
                **common)
        if init_only:
            d_name, where = _where(example['init'])
            raise GeLBExStencilError(
                f"Block '{bname}' (for node class '{name}') reads lattice"
                f" '{lat}' {where}, but '{d_name}' writes DF(s) {init_only}"
                f" of '{lat}' only in its initializer: after the first"
                f" buffer swap they are undefined at its cells",
                f"Write DF(s) {init_only} of '{lat}' in '{d_name}''s dynamic"
                f" every step, or make '{d_name}' a static node class"
                f" (no dynamic) if its values must not change.",
                **common)
        d_name, where = _where(example['dyn'])
        raise GeLBExStencilError(
            f"Block '{bname}' (for node class '{name}') reads lattice"
            f" '{lat}' {where}, but '{d_name}' writes DF(s) {dyn_only}"
            f" of '{lat}' only in its dynamic: at t = 0 (and for the"
            f" first step's reads) they are uninitialized",
            f"Write DF(s) {dyn_only} of '{lat}' in '{d_name}''s"
            f" initializer as well.",
            **common)

    # --- per-NC read checks ------------------------------------------
    for name, info in geometry.nc_info.items():
        for bname in (info.dynamic, info.gauge):
            block = stencils.blocks.get(bname) if bname else None
            if block is None:
                continue
            grouped: dict[tuple, set] = {}
            for r in block.reads:
                grouped.setdefault(
                    (r.lattice_name, r.spatial_offsets, r.guarded), set()
                ).add(r.df_index)
            for (lat, offset, guarded), read_dfs in grouped.items():
                lat_meta = stencils.lattices.get(lat)
                if lat_meta is None:
                    continue
                cells = _shift_mask(masks[name], offset, geometry)
                if guarded:
                    # Only failed links read locally. A diagonal with one
                    # invalid axis falls back along ALL axes.
                    valid = np.ones(shape, dtype=bool)
                    for axis, off in enumerate(offset):
                        if geometry.periodic[axis] or off == 0:
                            continue
                        target = np.arange(shape[axis]) + off
                        axis_shape = [1] * geometry.ndim
                        axis_shape[axis] = shape[axis]
                        valid &= ((target >= 0) & (target < shape[axis])).reshape(axis_shape)
                    cells = (_shift_mask(masks[name] & valid, offset, geometry)
                             | (masks[name] & ~valid))
                if not cells.any():
                    continue
                bad: dict[int, tuple] = {}
                for df in sorted(_needed_dfs(read_dfs, lat_meta.q)):
                    ok_initial, ok_recurring, *_ = _ok(lat, df)
                    bad_i = cells & ~ok_initial
                    bad_r = cells & ~ok_recurring
                    if bad_i.any() or bad_r.any():
                        bad[df] = (bad_i, bad_r)
                if bad:
                    _report(block, bname, name, lat, offset, bad)


def warn_writeonly_dynamics(
        stencils: ProgramStencils) -> list[tuple[str, str, int | None]]:
    """
    Warn about dynamic blocks that write f.out but never read f.in.

    A write-only dynamic is not necessarily a bug (e.g. Dirichlet BCs use
    this pattern intentionally), so this emits a warning rather than an
    error.  Empty (no-op) dynamics are not flagged.

    Should run AFTER stencil extraction.

    Args:
        stencils: Extracted program stencils.

    Returns:
        List of ``(message, hint, source_line)`` tuples (empty if none);
        ``source_line`` is the 1-based line the warning is about, or None.
    """
    warnings = []
    for block in stencils.blocks.values():
        if block.block_type != "dynamic":
            continue
        if block.writes and not block.reads:
            msg = (
                f"Dynamic block '{block.block_name}' writes to f.out "
                f"but never reads f.in"
            )
            hint = (
                "This is valid for Dirichlet-style boundary conditions "
                "(constant re-initialization). If this is intentional, "
                "consider using f.out[...|:] = f.in[...|:] instead, "
                "to copy the previous values (cheaper than recomputing)."
            )
            warnings.append((msg, hint, block.source_line))
    return warnings


def warn_unused_lattices(
        stencils: ProgramStencils) -> list[tuple[str, str, int | None]]:
    """
    Warn about lattices declared but never referenced in any block.

    Should run AFTER stencil extraction.

    Args:
        stencils: Extracted program stencils.

    Returns:
        List of ``(message, hint, source_line)`` tuples (empty if none);
        ``source_line`` is the 1-based line the warning is about, or None.
    """
    # Collect all lattice names referenced in any block
    referenced = set()
    for block in stencils.blocks.values():
        for access in block.reads + block.writes:
            referenced.add(access.lattice_name)

    warnings = []
    for lat_name in stencils.lattices:
        if lat_name not in referenced:
            msg = (
                f"Lattice '{lat_name}' is declared but never read "
                f"or written by any block"
            )
            hint = (
                f"Remove the unused lattice declaration, or add "
                f"read/write statements for '{lat_name}' in the "
                f"appropriate blocks."
            )
            warnings.append(
                (msg, hint, stencils.lattices[lat_name].source_line))
    return warnings
