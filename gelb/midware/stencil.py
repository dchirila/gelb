#!/usr/bin/env python3

"""
Stencil data structures for GeLB.

A stencil describes which lattice distribution functions (DFs) a block reads
from (input stencil) and writes to (output stencil), along with the spatial
offsets of each access relative to the current node.

These structures are rendering-agnostic and used by:
  - gelbc --stencils (text report)
  - gelb-view algo   (interactive visualization)
  - Future: validation passes, optimization passes
"""

from __future__ import annotations

from dataclasses import dataclass, field


def source_line_of(node) -> int | None:
    """1-based first line of an AST node, or None if it has no code range."""
    code_range = getattr(node, "code_range", None)
    return code_range.start_line if code_range is not None else None


@dataclass(frozen=True)
class StencilAccess:
    """A single lattice DF access (read or write).

    Attributes:
        lattice_name: Name of the lattice (e.g., "f").
        spatial_offsets: Offset tuple relative to the current node.
            Length equals the lattice dimensionality.
            E.g., (-1, 0) means "one cell to the left in x, same y".
        df_index: DF index accessed (0-based), or None for all DFs (`:` syntax).
        guarded: An out-of-grid neighbour read falls back to the same DF
            at the current cell. Periodic axes still wrap.
    """
    lattice_name: str
    spatial_offsets: tuple[int, ...]
    df_index: int | None
    # Outside a non-periodic grid, read the same DF at the current cell.
    guarded: bool = False


@dataclass
class BlockStencil:
    """Stencil information for a single block (initializer, dynamic, or gauge).

    Attributes:
        block_name: Name of the block (e.g., "FluidDynamic").
        block_type: One of "initializer", "dynamic", "gauge".
        reads: List of input (f.in) accesses.
        writes: List of output (f.out) accesses.
    """
    block_name: str
    block_type: str
    reads: list[StencilAccess] = field(default_factory=list)
    writes: list[StencilAccess] = field(default_factory=list)
    source_line: int | None = None
    source_end_line: int | None = None

    @property
    def read_offsets(self) -> set[tuple[int, ...]]:
        """Unique spatial offsets read from."""
        return {a.spatial_offsets for a in self.reads}

    @property
    def write_offsets(self) -> set[tuple[int, ...]]:
        """Unique spatial offsets written to."""
        return {a.spatial_offsets for a in self.writes}

    @property
    def is_local(self) -> bool:
        """True if all accesses are at offset (0, ..., 0)."""
        zero = None  # lazy -- computed on first access
        for a in self.reads + self.writes:
            if zero is None:
                zero = tuple(0 for _ in a.spatial_offsets)
            if a.spatial_offsets != zero:
                return False
        return True

    def format_report(self) -> str:
        """Human-readable text report for this block's stencil."""
        lines = [f"Block: {self.block_name} ({self.block_type})"]

        for direction, accesses in [("Input", self.reads),
                                    ("Output", self.writes)]:
            if not accesses:
                continue
            # Group by lattice
            by_lattice: dict[str, list[StencilAccess]] = {}
            for a in accesses:
                by_lattice.setdefault(a.lattice_name, []).append(a)

            for lat_name, lat_accesses in by_lattice.items():
                lines.append(f"  {direction} stencil ({lat_name}):")
                for a in lat_accesses:
                    df_str = "*" if a.df_index is None else str(a.df_index)
                    off_str = "(" + ", ".join(
                        f"{o:+d}" if o != 0 else "0"
                        for o in a.spatial_offsets
                    ) + ")"
                    lines.append(f"    DF {df_str}: {off_str}")

        # Neighborhood summary
        all_offsets = self.read_offsets | self.write_offsets
        if all_offsets:
            if self.is_local:
                lines.append("  Neighborhood: local")
            else:
                lines.append(
                    f"  Neighborhood: {len(all_offsets)} offset(s)")

        return "\n".join(lines)


@dataclass
class LatticeMetadata:
    """Metadata for a single lattice, extracted from the AST.

    Attributes:
        name: Lattice name (e.g., "f").
        d: Spatial dimensionality (1, 2, or 3).
        q: Number of discrete velocities / DFs.
        grid_size: Grid dimensions as evaluated integers, e.g., (64, 64).
            None if dimensions could not be resolved at compile time.
        periodic: Periodicity per dimension, e.g., (True, True).
            None if not resolved.
        source_line: 1-based line of the declaration (None if unknown).
    """
    name: str
    d: int
    q: int
    grid_size: tuple[int, ...] | None = None
    periodic: tuple[bool, ...] | None = None
    source_line: int | None = None


@dataclass
class NodeClassInfo:
    """Mapping from a node class to its associated block names."""
    name: str
    initializer: str | None
    dynamic: str | None
    gauge: str | None
    masked: bool = False


@dataclass
class GeometryPaint:
    """A single geometry paint statement, evaluated to concrete ranges.

    Attributes:
        ranges: Per-dimension (low, high) pairs.  A full-range dimension
            is represented as None.
        node_class: Name of the node class painted.
    """
    ranges: list[tuple[int, int] | None]
    node_class: str


@dataclass
class ProgramStencils:
    """Complete stencil analysis result for a GeLB program.

    Attributes:
        blocks: block_name -> BlockStencil
        lattices: lattice_name -> LatticeMetadata
        node_classes: nc_name -> NodeClassInfo
        geometry_paints: Ordered list of paint statements (CSS override
            semantics -- later statements overwrite earlier ones).
    """
    blocks: dict[str, BlockStencil] = field(default_factory=dict)
    lattices: dict[str, LatticeMetadata] = field(default_factory=dict)
    node_classes: dict[str, NodeClassInfo] = field(default_factory=dict)
    geometry_paints: list[GeometryPaint] = field(default_factory=list)

    def format_report(self) -> str:
        """Full human-readable stencil report."""
        parts = []
        for bs in self.blocks.values():
            parts.append(bs.format_report())
        return "\n\n".join(parts)

    def periodic_reach(self) -> int:
        """The largest |offset| of any read or write along a periodic
        axis (0 when there is none).  The backends keep one ghost cell
        per periodic axis end, so a reach above 1 needs wrapped indices
        for the accesses that go further."""
        reach = 0
        for block in self.blocks.values():
            for access in block.reads + block.writes:
                periodic = self.lattices[access.lattice_name].periodic or ()
                for axis, off in enumerate(access.spatial_offsets):
                    if axis < len(periodic) and periodic[axis]:
                        reach = max(reach, abs(off))
        return reach

    def write_reach(self) -> int:
        """The largest |offset| of any lattice write along any axis (0 when
        every write is local).  A write at an offset is a "push": the
        backends must wrap its destination on periodic axes even at +/-1
        (a ghost cell is never copied back), and the paths that store
        only at the cell they compute (the CBT layout with its aligned and
        streaming stores, the CUDA shared-memory tiles) are not used."""
        reach = 0
        for block in self.blocks.values():
            for access in block.writes:
                for off in access.spatial_offsets:
                    reach = max(reach, abs(off))
        return reach

    def gauge_halo_lattices(self) -> set[str]:
        """Lattices that a gauge reads at a non-zero offset along a
        periodic axis.  The backends refresh their periodic ghost cells
        before each dynamic pass; gauges run after the buffer swap (and
        once before the first step), so these lattices need a refresh
        before the gauges too."""
        names = set()
        for block in self.blocks.values():
            if block.block_type != "gauge":
                continue
            for access in block.reads:
                periodic = self.lattices[access.lattice_name].periodic or ()
                if any(off and axis < len(periodic) and periodic[axis]
                       for axis, off in enumerate(access.spatial_offsets)):
                    names.add(access.lattice_name)
        return names

    def get_node_class_at(self, *coords: int) -> str | None:
        """Look up the node class at a given grid position.

        Replays paint statements in order (CSS override semantics).
        Returns None if the position was never painted.
        """
        result = None
        for paint in self.geometry_paints:
            match = True
            for dim_idx, rng in enumerate(paint.ranges):
                if rng is None:
                    continue  # full range -- matches any coordinate
                low, high = rng
                if dim_idx >= len(coords):
                    match = False
                    break
                if not (low <= coords[dim_idx] <= high):
                    match = False
                    break
            if match:
                result = paint.node_class
        return result
