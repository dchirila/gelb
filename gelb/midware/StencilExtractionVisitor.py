#!/usr/bin/env python3

"""
Stencil extraction visitor for GeLB.

Walks the AST of each block and collects all lattice read/write accesses
to build BlockStencil objects.  Also extracts lattice metadata, node-class
mappings, and geometry paint statements into a ProgramStencils result.
"""

from __future__ import annotations

from gelb.gelb_ast.ASTNodes import (
    Add_N,
    Array1DLiteral_N,
    BoolLiteral_N,
    ConstantDefinitionStmt_N,
    DynamicBlock_N,
    GaugeBlock_N,
    Identifier_N,
    InitializerBlock_N,
    IntrinsicFunctionCall_N,
    IntLiteral_N,
    LatticeInstaStmt_N,
    List_N,
    Mul_N,
    Node_N,
    NodeClassInstaStmt_N,
    PaintNodesStmt_N,
    Program_N,
    Range_N,
    RealLiteral_N,
    RectSelOfLatticeInDFs_N,
    RectSelOfLatticeOutDFs_N,
    Sub_N,
    TypePromotionNode_N,
    UnaryMinusExpr_N,
)

from gelb.midware.stencil import (
    BlockStencil,
    GeometryPaint,
    LatticeMetadata,
    NodeClassInfo,
    ProgramStencils,
    StencilAccess,
    source_line_of,
)
import gelb.utils.config
from gelb.utils.exceptions import GeLBExStencilError

# Implicit loop variable names for each dimension
_DIM_NAMES = ("x", "y", "z")


def affine_index(expr) -> tuple[dict[str, int], int] | None:
    """Split an integer expression over the coordinates into (coefficient
    per coordinate name, constant): ``x + 1``, ``(x + 1) + 1``, ``2 + x``
    and ``x - (-1)`` all come out as ``({'x': 1}, k)``.  None when the
    expression is not affine in the coordinates with integer constants."""
    if isinstance(expr, TypePromotionNode_N):
        return affine_index(expr.expr)
    if isinstance(expr, Identifier_N):
        return ({expr.name: 1}, 0) if expr.name in _DIM_NAMES else None
    if isinstance(expr, IntLiteral_N):
        return ({}, int(expr.value))
    if isinstance(expr, RealLiteral_N):
        value = float(expr.value)
        return ({}, int(value)) if value.is_integer() else None
    if isinstance(expr, UnaryMinusExpr_N):
        inner = affine_index(expr.value)
        if inner is None:
            return None
        return ({k: -c for k, c in inner[0].items()}, -inner[1])
    if isinstance(expr, (Add_N, Sub_N, Mul_N)):
        left, right = affine_index(expr.left), affine_index(expr.right)
        if left is None or right is None:
            return None
        if isinstance(expr, Mul_N):
            if left[0] and right[0]:
                return None                     # x * y is not affine
            factor, term = (left[1], right) if not left[0] else (right[1], left)
            return ({k: factor * c for k, c in term[0].items() if factor * c},
                    factor * term[1])
        sign = 1 if isinstance(expr, Add_N) else -1
        coeffs = dict(left[0])
        for k, c in right[0].items():
            coeffs[k] = coeffs.get(k, 0) + sign * c
        return ({k: c for k, c in coeffs.items() if c}, left[1] + sign * right[1])
    return None


def _source_text(node) -> str | None:
    """The source text of a single-line AST node, if it is available."""
    cr = getattr(node, "code_range", None)
    src = getattr(gelb.utils.config, "GELB_SRC_RAW", None)
    if cr is None or not src or cr.start_line != cr.stop_line:
        return None
    lines = src.splitlines()
    if not 0 < cr.start_line <= len(lines):
        return None
    return lines[cr.start_line - 1][cr.start_col:cr.stop_col + 1] or None


class StencilExtractionVisitor:
    """Extract stencil information from a typed, constant-folded AST."""

    def __init__(self):
        self._result = ProgramStencils()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, ast: Program_N) -> ProgramStencils:
        """Run extraction on the full program AST.  Returns ProgramStencils."""
        self._ast = ast
        self._extract_lattices(ast)
        self._extract_blocks(ast)
        self._extract_node_classes(ast)
        self._extract_geometry(ast)
        return self._result

    # ------------------------------------------------------------------
    # Lattice metadata
    # ------------------------------------------------------------------

    def _extract_lattices(self, ast: Program_N) -> None:
        if ast.lattices is None:
            return
        for stmt in ast.lattices.stmts:
            if not isinstance(stmt, LatticeInstaStmt_N):
                continue
            d = self._eval_int(stmt.d)
            q = self._eval_int(stmt.q)
            grid_size = self._eval_grid_size(stmt.grid_size, d)
            periodic = self._eval_periodicity(stmt.periodicity, d)
            self._result.lattices[stmt.name.name] = LatticeMetadata(
                name=stmt.name.name,
                d=d,
                q=q,
                grid_size=grid_size,
                periodic=periodic,
                source_line=source_line_of(stmt),
            )

    # ------------------------------------------------------------------
    # Block stencils
    # ------------------------------------------------------------------

    def _extract_blocks(self, ast: Program_N) -> None:
        if ast.initializers is not None:
            for init in ast.initializers.elements:
                if isinstance(init, InitializerBlock_N):
                    self._extract_block(init, "initializer")

        if ast.dynamics is not None:
            for dyn in ast.dynamics.elements:
                if isinstance(dyn, DynamicBlock_N):
                    self._extract_block(dyn, "dynamic")

        if ast.gauges is not None:
            for gauge in ast.gauges.elements:
                if isinstance(gauge, GaugeBlock_N):
                    self._extract_block(gauge, "gauge")

    def _extract_block(self, block, block_type: str) -> None:
        name = block.name.name
        self._block_name = name
        bs = BlockStencil(block_name=name, block_type=block_type)
        if hasattr(block, "code_range") and block.code_range is not None:
            bs.source_line = block.code_range.start_line
            bs.source_end_line = block.code_range.stop_line
        self._walk_for_accesses(block, bs)
        # Deduplicate (StencilAccess is frozen/hashable)
        bs.reads = list(dict.fromkeys(bs.reads))
        bs.writes = list(dict.fromkeys(bs.writes))
        self._result.blocks[name] = bs

    def _walk_for_accesses(self, node, bs: BlockStencil) -> None:
        """Recursively walk *node* and collect lattice accesses into *bs*."""
        if node is None:
            return

        if isinstance(node, RectSelOfLatticeInDFs_N):
            accesses = self._parse_lattice_access(node, is_write=False)
            bs.reads.extend(accesses)

        if isinstance(node, RectSelOfLatticeOutDFs_N):
            accesses = self._parse_lattice_access(node, is_write=True)
            bs.writes.extend(accesses)

        if isinstance(node, IntrinsicFunctionCall_N):
            if node.function_name in ('upstream_dfs', 'bounce_back_dfs'):
                accesses = self._parse_streaming_intrinsic(node)
                bs.reads.extend(accesses)

        # Recurse into children (same pattern as LatticeAccessContextValidator)
        for attr_name in vars(node):
            if attr_name.startswith("_"):
                continue
            child = getattr(node, attr_name, None)
            if child is None:
                continue
            if isinstance(child, Node_N):
                self._walk_for_accesses(child, bs)
            elif isinstance(child, list):
                for item in child:
                    if isinstance(item, Node_N):
                        self._walk_for_accesses(item, bs)
            elif hasattr(child, "elements") and isinstance(
                getattr(child, "elements", None), list
            ):
                for item in child.elements:
                    if isinstance(item, Node_N):
                        self._walk_for_accesses(item, bs)

    # ------------------------------------------------------------------
    # Parsing a single lattice access node
    # ------------------------------------------------------------------

    def _parse_lattice_access(self, node, is_write=False) -> list[StencilAccess]:
        """Parse a RectSelOfLattice{In,Out}DFs_N into StencilAccess(es).

        element_ranges layout: [spatial_0, spatial_1, ..., df_range]
        The last element is the DF range; preceding elements are spatial.
        """
        lattice_name = node.lattice_name.name
        ranges = node.element_ranges
        if isinstance(ranges, List_N):
            ranges = ranges.elements
        elif not isinstance(ranges, list):
            ranges = list(ranges)

        if len(ranges) < 1:
            return []

        # Split into spatial ranges and DF range
        df_range = ranges[-1]
        spatial_ranges = ranges[:-1]

        # Extract spatial offsets
        offsets = tuple(self._extract_offset(sr, axis, lattice_name)
                        for axis, sr in enumerate(spatial_ranges))

        # Extract DF index/indices.  A write must name its DFs at compile
        # time: the coverage and conflict checks reason
        # about each DF, and "some DF" would prove nothing.  A read may
        # select a DF at run time; it then counts as a read of every DF.
        df_indices = self._extract_df_indices(df_range)
        if is_write and None in df_indices:
            text = _source_text(df_range) or "this index"
            raise GeLBExStencilError(
                f"Block '{self._block_name}' writes lattice "
                f"'{lattice_name}' with DF index '{text}', which is not a "
                f"compile-time integer",
                "A write must name its DFs: use a literal or constant "
                "index, a constant slice such as 0:2, or ':' for every DF.",
                source_line=source_line_of(df_range),
                source_end_line=source_line_of(df_range),
            )

        return [
            StencilAccess(
                lattice_name=lattice_name,
                spatial_offsets=offsets,
                df_index=df_idx,
            )
            for df_idx in df_indices
        ]

    def _extract_offset(self, range_node: Range_N, axis: int,
                        lattice_name: str) -> int:
        """The offset of a lattice index along ``axis``.  The index must be
        that axis's coordinate plus a compile-time integer (``x``,
        ``x + 1``, ``(x + 1) + 1``, ``2 + x``, ...).  Anything else is an
        error, not a guess: the boundary checks and the backends' halo
        handling rely on these offsets."""
        low, high = range_node.low, range_node.high
        form = affine_index(low) if low is not None else None
        if (form is not None and high is not low
                and (high is None or affine_index(high) != form)):
            form = None                          # a spatial range, low:high
        dim = _DIM_NAMES[axis] if axis < len(_DIM_NAMES) else None
        if form is None or form[0] != {dim: 1}:
            text = _source_text(range_node) or "this index"
            raise GeLBExStencilError(
                f"Block '{self._block_name}' indexes lattice "
                f"'{lattice_name}' along {dim} with '{text}', which is not "
                f"{dim} plus or minus a compile-time integer",
                f"Inside a block, lattices are addressed relative to the "
                f"current cell: write {dim}, {dim} + k or {dim} - k here "
                f"(k an integer constant), with the coordinates in the "
                f"order x, y, z.",
                source_line=source_line_of(range_node),
                source_end_line=source_line_of(range_node),
            )
        return form[1]

    def _extract_df_indices(self, range_node: Range_N) -> list[int | None]:
        """Extract DF index or indices from the DF range.

        Returns a list so that full-range (`:`) can expand to [None],
        indicating "all DFs".
        """
        # Full range: low is None, or both are None
        if range_node.low is None or range_node.high is None:
            return [None]

        low = self._try_eval_int(range_node.low)
        high = self._try_eval_int(range_node.high)

        if low is not None and high is not None:
            if low == high:
                return [low]
            # Explicit range like 0:8
            return list(range(low, high + 1))

        # Could not evaluate -- treat as all DFs
        return [None]

    # ------------------------------------------------------------------
    # Streaming intrinsics
    # ------------------------------------------------------------------

    def _parse_streaming_intrinsic(self, node) -> list[StencilAccess]:
        """Extract read stencils from the streaming intrinsics.

        upstream_dfs(f, x, y, {EX, EY}):
          For each DF i, read at offset (-EX[i], -EY[i]) with df_index=i.

        bounce_back_dfs(f, x, y, {EX, EY}):
          Read at (+EX[i], +EY[i]), DF opp(i), where opp(i) is the
          index j such that c_j = -c_i. Guarded reads outside a
          non-periodic grid fall back to that DF at the current cell.
        """
        args = node.arguments.elements
        lattice_name = args[0].name  # Identifier_N
        vel_set = args[-1]
        for axis, coord in enumerate(args[1:-1]):
            dim = _DIM_NAMES[axis] if axis < len(_DIM_NAMES) else None
            if affine_index(coord) != ({dim: 1}, 0):
                text = _source_text(coord) or "this argument"
                raise GeLBExStencilError(
                    f"Block '{self._block_name}' passes '{text}' as the "
                    f"{dim} coordinate of {node.function_name}(); it must "
                    f"be {dim} itself",
                    f"Streaming intrinsics act on the current cell: call "
                    f"{node.function_name}({lattice_name}, "
                    f"{', '.join(_DIM_NAMES[:len(args) - 2])}, ...).",
                    source_line=source_line_of(coord),
                    source_end_line=source_line_of(coord),
                )

        # Extract velocity arrays from the last argument
        vel_arrays = []
        if isinstance(vel_set, Array1DLiteral_N):
            # 2D/3D: {EX, EY} or {EX, EY, EZ}
            for vel_node in vel_set.value.elements:
                vel_arrays.append(self._resolve_constant_array(vel_node))
        else:
            # 1D: single velocity array (no braces)
            vel_arrays.append(self._resolve_constant_array(vel_set))

        q = len(vel_arrays[0])
        nd = len(vel_arrays)

        if node.function_name == 'bounce_back_dfs':
            opp_map = self._compute_opposite_mapping(vel_arrays, q)
            return [
                StencilAccess(
                    lattice_name=lattice_name,
                    spatial_offsets=tuple(int(v[i]) for v in vel_arrays),
                    guarded=True,
                    df_index=opp_map[i],
                )
                for i in range(q)
            ]
        else:
            # upstream_dfs: pull streaming offsets
            return [
                StencilAccess(
                    lattice_name=lattice_name,
                    spatial_offsets=tuple(
                        -int(vel_arrays[dim][i]) for dim in range(nd)
                    ),
                    df_index=i,
                )
                for i in range(q)
            ]

    def _resolve_constant_array(self, node) -> list[float]:
        """Resolve an AST node to a list of numeric values.

        Handles Identifier_N (looks up global constant), Array1DLiteral_N
        (extracts element values), TypePromotionNode_N (unwraps), and
        nested combinations.
        """
        if isinstance(node, TypePromotionNode_N):
            return self._resolve_constant_array(node.expr)
        if isinstance(node, Identifier_N):
            if self._ast.global_constants is not None:
                for stmt in self._ast.global_constants.stmts:
                    if (isinstance(stmt, ConstantDefinitionStmt_N)
                            and stmt.name.name == node.name):
                        return self._resolve_constant_array(stmt.value)
            raise ValueError(
                f"Cannot resolve constant array '{node.name}'")
        if isinstance(node, Array1DLiteral_N):
            return [self._eval_scalar(e) for e in node.value.elements]
        raise ValueError(
            f"Cannot resolve constant array from {type(node).__name__}")

    @staticmethod
    def _eval_scalar(node) -> float:
        """Extract a numeric value from a constant-folded scalar node."""
        if isinstance(node, TypePromotionNode_N):
            return StencilExtractionVisitor._eval_scalar(node.expr)
        if isinstance(node, IntLiteral_N):
            return float(node.value)
        if isinstance(node, RealLiteral_N):
            return float(node.value)
        if isinstance(node, UnaryMinusExpr_N):
            return -StencilExtractionVisitor._eval_scalar(node.value)
        raise ValueError(
            f"Cannot extract scalar from {type(node).__name__}")

    @staticmethod
    def _compute_opposite_mapping(vel_arrays, q) -> list[int]:
        """Compute opposite DF index mapping from velocity vectors."""
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

    # ------------------------------------------------------------------
    # Node classes
    # ------------------------------------------------------------------

    def _extract_node_classes(self, ast: Program_N) -> None:
        if ast.node_classes is None:
            return
        for stmt in ast.node_classes.stmts:
            if not isinstance(stmt, NodeClassInstaStmt_N):
                continue
            self._result.node_classes[stmt.name.name] = NodeClassInfo(
                name=stmt.name.name,
                initializer=stmt.initializer.name if stmt.initializer is not None else None,
                dynamic=stmt.dynamic.name if stmt.dynamic is not None else None,
                gauge=stmt.gauge.name if stmt.gauge is not None else None,
                masked=bool(getattr(stmt, 'masked', False)),
            )

    # ------------------------------------------------------------------
    # Geometry paints
    # ------------------------------------------------------------------

    def _extract_geometry(self, ast: Program_N) -> None:
        if ast.geometry is None:
            return
        for stmt in ast.geometry.stmts:
            if not isinstance(stmt, PaintNodesStmt_N):
                continue
            nc_name = stmt.rhs.name
            spatial_ranges = stmt.lhs
            if isinstance(spatial_ranges, List_N):
                spatial_ranges = spatial_ranges.elements
            elif not isinstance(spatial_ranges, list):
                spatial_ranges = list(spatial_ranges)

            ranges = []
            for sr in spatial_ranges:
                if not isinstance(sr, Range_N):
                    ranges.append(None)
                    continue
                # Full range: low and high are both None
                if sr.low is None and sr.high is None:
                    ranges.append(None)
                    continue
                low = self._try_eval_int(sr.low)
                high = self._try_eval_int(sr.high)
                if low is not None and high is not None:
                    ranges.append((low, high))
                else:
                    ranges.append(None)

            self._result.geometry_paints.append(
                GeometryPaint(ranges=ranges, node_class=nc_name)
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _eval_int(node) -> int:
        """Evaluate an AST node to an integer.  Raises if not possible."""
        if isinstance(node, int):
            return node
        if isinstance(node, IntLiteral_N):
            return node.value
        if isinstance(node, RealLiteral_N):
            return int(node.value)
        raise ValueError(
            f"Cannot evaluate {type(node).__name__} as integer"
        )

    @staticmethod
    def _try_eval_int(node) -> int | None:
        """Try to evaluate an AST node to an integer.  Returns None on failure."""
        if isinstance(node, int):
            return node
        if isinstance(node, IntLiteral_N):
            return node.value
        if isinstance(node, RealLiteral_N):
            return int(node.value)
        return None

    def _eval_grid_size(self, gs_node, d: int) -> tuple[int, ...] | None:
        """Evaluate grid_size to a tuple of ints."""
        if gs_node is None:
            return None
        if isinstance(gs_node, int):
            return (gs_node,)
        if isinstance(gs_node, (IntLiteral_N, RealLiteral_N)):
            return (self._eval_int(gs_node),)
        # Array1DLiteral_N wraps a List_N in .value
        if isinstance(gs_node, Array1DLiteral_N):
            gs_node = gs_node.value
        if isinstance(gs_node, List_N):
            try:
                return tuple(self._eval_int(e) for e in gs_node.elements)
            except (ValueError, AttributeError):
                return None
        return None

    def _eval_periodicity(self, p_node, d: int) -> tuple[bool, ...] | None:
        """Evaluate periodicity to a tuple of bools."""
        if p_node is None:
            return None
        # A 1-D lattice takes a scalar: lattice u(1, 1, real, 8, true)
        if isinstance(p_node, bool):
            return (p_node,) * d
        if isinstance(p_node, BoolLiteral_N):
            return (p_node.value == "true" or p_node.value is True,) * d
        # Array1DLiteral_N wraps a List_N in .value
        if isinstance(p_node, Array1DLiteral_N):
            p_node = p_node.value
        if isinstance(p_node, List_N):
            result = []
            for e in p_node.elements:
                if isinstance(e, BoolLiteral_N):
                    result.append(e.value == "true" or e.value is True)
                elif isinstance(e, bool):
                    result.append(e)
                else:
                    return None
            return tuple(result)
        return None
