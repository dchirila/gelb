"""
Algorithm / stencil visualization for GeLB programs.

Reads a .gelb source file, runs frontend + midware + stencil extraction,
and produces matplotlib plots showing stencil patterns for each block.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from gelb.midware.stencil import BlockStencil, ProgramStencils

# Standard D2Q9 velocity vectors (index -> (ex, ey))
_D2Q9_VELOCITIES = {
    0: (0, 0),
    1: (1, 0),
    2: (0, 1),
    3: (-1, 0),
    4: (0, -1),
    5: (1, 1),
    6: (-1, 1),
    7: (-1, -1),
    8: (1, -1),
}

# Standard D1Q3 velocity vectors (index -> (cx,))
_D1Q3_VELOCITIES = {
    0: (0,),
    1: (1,),
    2: (-1,),
}


def _get_velocity(df_index: int | None, ndim: int) -> tuple[float, ...]:
    """Get the velocity direction for a DF index.

    Falls back to origin if the index is unknown or None.
    """
    if df_index is None:
        return tuple(0.0 for _ in range(ndim))
    if ndim == 1:
        v = _D1Q3_VELOCITIES.get(df_index)
        if v is not None:
            return v
    elif ndim == 2:
        v = _D2Q9_VELOCITIES.get(df_index)
        if v is not None:
            return v
    return tuple(0.0 for _ in range(ndim))


def _get_all_velocities(ndim: int) -> dict[int, tuple]:
    """Return the full velocity table for the given dimensionality."""
    if ndim == 1:
        return _D1Q3_VELOCITIES
    elif ndim == 2:
        return _D2Q9_VELOCITIES
    return {}


def _draw_all_dfs(ax, node_x, node_y, scale, velocities, ndim,
                  markersize=5):
    """Draw gray DF dots at a lattice node for all velocity directions."""
    for df_idx, vel in velocities.items():
        if ndim == 1:
            cx = node_x + scale * vel[0]
            ax.plot(cx, node_y, "o", color="#d0d0d0", markersize=markersize,
                    zorder=2)
        else:
            cx = node_x + scale * vel[0]
            cy = node_y + scale * vel[1]
            ax.plot(cx, cy, "o", color="#d0d0d0", markersize=markersize,
                    zorder=2)


def _plot_stencil_1d(ax: plt.Axes, bs: BlockStencil, title: str) -> None:
    """Plot a 1D stencil on the given axes."""
    all_offsets = bs.read_offsets | bs.write_offsets
    if not all_offsets:
        ax.set_title(title)
        ax.text(0.5, 0.5, "No accesses", ha="center", va="center",
                transform=ax.transAxes, fontsize=12, color="gray")
        return

    min_x = min(o[0] for o in all_offsets) - 1
    max_x = max(o[0] for o in all_offsets) + 1
    velocities = _get_all_velocities(1)
    scale = 0.25

    # Draw node positions and all DF dots (gray) at every node
    for x in range(min_x, max_x + 1):
        ax.plot(x, 0, "o", color="lightgray", markersize=12, zorder=1)
        _draw_all_dfs(ax, x, 0, scale, velocities, 1, markersize=7)

    # Highlight center node
    ax.plot(0, 0, "s", color="black", markersize=14, zorder=3,
            fillstyle="none", linewidth=2)

    # Build sets for quick lookup
    read_keys = {(a.spatial_offsets, a.df_index) for a in bs.reads}
    write_keys = {(a.spatial_offsets, a.df_index) for a in bs.writes}

    # Plot reads (filled blue)
    for a in bs.reads:
        ox = a.spatial_offsets[0]
        vel = _get_velocity(a.df_index, 1)
        cx = ox + scale * vel[0]
        ax.plot(cx, 0, "o", color="royalblue", markersize=7,
                zorder=4, alpha=0.9)
        label = "*" if a.df_index is None else str(a.df_index)
        ax.annotate(label, (cx, 0), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=7, color="royalblue")

    # Plot writes (unfilled green circles)
    for a in bs.writes:
        ox = a.spatial_offsets[0]
        vel = _get_velocity(a.df_index, 1)
        cx = ox + scale * vel[0]
        ax.plot(cx, 0, "o", color="green", markersize=9,
                zorder=5, fillstyle="none", markeredgewidth=1.8)
        label = "*" if a.df_index is None else str(a.df_index)
        # Only annotate if not already labeled by a read at same position
        if (a.spatial_offsets, a.df_index) not in read_keys:
            ax.annotate(label, (cx, 0), textcoords="offset points",
                        xytext=(0, 8), ha="center", fontsize=7, color="green")

    ax.set_xlim(min_x - 0.5, max_x + 0.5)
    ax.set_ylim(-0.8, 0.8)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10)
    ax.axhline(0, color="lightgray", linewidth=0.5, zorder=0)
    ax.set_yticks([])
    ax.set_xticks(range(min_x, max_x + 1))


def _plot_stencil_2d(ax: plt.Axes, bs: BlockStencil, title: str) -> None:
    """Plot a 2D stencil on the given axes."""
    all_offsets = bs.read_offsets | bs.write_offsets
    if not all_offsets:
        ax.set_title(title)
        ax.text(0.5, 0.5, "No accesses", ha="center", va="center",
                transform=ax.transAxes, fontsize=12, color="gray")
        return

    min_x = min(o[0] for o in all_offsets) - 1
    max_x = max(o[0] for o in all_offsets) + 1
    min_y = min(o[1] for o in all_offsets) - 1
    max_y = max(o[1] for o in all_offsets) + 1
    velocities = _get_all_velocities(2)
    scale = 0.2

    # Draw grid of node positions and all DF dots (gray) at every node
    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            ax.plot(x, y, "o", color="lightgray", markersize=10, zorder=1)
            _draw_all_dfs(ax, x, y, scale, velocities, 2, markersize=5)

    # Highlight center node
    ax.plot(0, 0, "s", color="black", markersize=14, zorder=3,
            fillstyle="none", linewidth=2)

    # Build sets for quick lookup
    read_keys = {(a.spatial_offsets, a.df_index) for a in bs.reads}
    write_keys = {(a.spatial_offsets, a.df_index) for a in bs.writes}

    # Plot reads (filled blue)
    for a in bs.reads:
        ox, oy = a.spatial_offsets
        vel = _get_velocity(a.df_index, 2)
        cx = ox + scale * vel[0]
        cy = oy + scale * vel[1]
        ax.plot(cx, cy, "o", color="royalblue", markersize=6,
                zorder=4, alpha=0.9)
        label = "*" if a.df_index is None else str(a.df_index)
        ax.annotate(label, (cx, cy), textcoords="offset points",
                    xytext=(5, 5), ha="left", fontsize=6, color="royalblue")

    # Plot writes (unfilled green circles)
    for a in bs.writes:
        ox, oy = a.spatial_offsets
        vel = _get_velocity(a.df_index, 2)
        cx = ox + scale * vel[0]
        cy = oy + scale * vel[1]
        ax.plot(cx, cy, "o", color="green", markersize=9,
                zorder=5, fillstyle="none", markeredgewidth=1.5)
        label = "*" if a.df_index is None else str(a.df_index)
        # Only annotate if not already labeled by a read at same position
        if (a.spatial_offsets, a.df_index) not in read_keys:
            ax.annotate(label, (cx, cy), textcoords="offset points",
                        xytext=(5, 5), ha="left", fontsize=6, color="green")

    ax.set_xlim(min_x - 0.5, max_x + 0.5)
    ax.set_ylim(min_y - 0.5, max_y + 0.5)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10)
    ax.set_xticks(range(min_x, max_x + 1))
    ax.set_yticks(range(min_y, max_y + 1))
    ax.grid(True, alpha=0.15)


def _plot_stencil_3d(ax, bs: BlockStencil, title: str) -> None:
    """Plot a 3D stencil on the given mpl_toolkits.mplot3d axes.

    Rather than replicate the 2-D per-node DF cluster -- which gets
    unreadable once 19 or 27 directions stack at every lattice site
    -- we plot only the positions actually touched by the block's
    reads / writes, plus a sparse gray scaffolding of the surrounding
    lattice points. Origin is highlighted with a black cube marker.
    """
    all_offsets = bs.read_offsets | bs.write_offsets
    if not all_offsets:
        ax.set_title(title)
        ax.text2D(0.5, 0.5, "No accesses", ha="center", va="center",
                  transform=ax.transAxes, fontsize=12, color="gray")
        return

    min_x = min(o[0] for o in all_offsets) - 1
    max_x = max(o[0] for o in all_offsets) + 1
    min_y = min(o[1] for o in all_offsets) - 1
    max_y = max(o[1] for o in all_offsets) + 1
    min_z = min(o[2] for o in all_offsets) - 1
    max_z = max(o[2] for o in all_offsets) + 1

    # Sparse lattice scaffold -- a small gray dot at every integer
    # position in the bounding box. Helps the viewer see the spatial
    # footprint of the stencil without cluttering the plot.
    gx, gy, gz = [], [], []
    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            for z in range(min_z, max_z + 1):
                gx.append(x); gy.append(y); gz.append(z)
    ax.scatter(gx, gy, gz, c="lightgray", s=10, alpha=0.35,
               depthshade=False, zorder=1)

    # Origin marker.
    ax.scatter([0], [0], [0], marker="s", s=90,
               facecolors="none", edgecolors="black", linewidths=1.5,
               depthshade=False, zorder=5)

    read_keys = {(a.spatial_offsets, a.df_index) for a in bs.reads}

    # Reads -- solid blue.
    for a in bs.reads:
        ox, oy, oz = a.spatial_offsets
        ax.scatter([ox], [oy], [oz], c="royalblue", s=40,
                   depthshade=False, zorder=4)
        label = "*" if a.df_index is None else str(a.df_index)
        ax.text(ox, oy, oz + 0.18, label, color="royalblue",
                fontsize=6, ha="center")

    # Writes -- hollow green.
    for a in bs.writes:
        ox, oy, oz = a.spatial_offsets
        ax.scatter([ox], [oy], [oz], s=70,
                   facecolors="none", edgecolors="green", linewidths=1.4,
                   depthshade=False, zorder=5)
        if (a.spatial_offsets, a.df_index) not in read_keys:
            label = "*" if a.df_index is None else str(a.df_index)
            ax.text(ox, oy, oz + 0.18, label, color="green",
                    fontsize=6, ha="center")

    ax.set_xlim(min_x - 0.5, max_x + 0.5)
    ax.set_ylim(min_y - 0.5, max_y + 0.5)
    ax.set_zlim(min_z - 0.5, max_z + 0.5)
    ax.set_xlabel("x", fontsize=8); ax.tick_params(axis='x', labelsize=7)
    ax.set_ylabel("y", fontsize=8); ax.tick_params(axis='y', labelsize=7)
    ax.set_zlabel("z", fontsize=8); ax.tick_params(axis='z', labelsize=7)
    ax.set_title(title, fontsize=10)
    # Aim for a roughly cubic aspect so the bounding box reads
    # correctly; matplotlib 3-D axes don't support set_aspect('equal')
    # on all backends, so we use set_box_aspect with the actual
    # extents.
    ax.set_box_aspect(
        (max_x - min_x + 1, max_y - min_y + 1, max_z - min_z + 1))


def plot_stencils(stencils: ProgramStencils,
                  block_names: list[str] | None = None,
                  output: str | None = None) -> None:
    """Plot stencil diagrams for selected blocks (headless matplotlib).

    Args:
        stencils: Extracted program stencils.
        block_names: Blocks to plot (default: all).
        output: Save to file if given, otherwise plt.show().
    """
    blocks = stencils.blocks
    if block_names:
        blocks = {n: b for n, b in blocks.items() if n in block_names}

    if not blocks:
        return

    # Determine dimensionality from first lattice.
    ndim = 2  # default
    if stencils.lattices:
        ndim = next(iter(stencils.lattices.values())).d

    n = len(blocks)
    fig_w = max(5, 4 * n)
    fig_h = 5 if ndim >= 2 else 3
    # 3-D stencils need mpl_toolkits.mplot3d axes; 1-D and 2-D use the
    # default Cartesian axes. subplot_kw is applied to *all* panels,
    # which is fine because the per-program ndim is consistent across
    # blocks.
    subplot_kw = {"projection": "3d"} if ndim >= 3 else {}
    fig, axes = plt.subplots(
        1, n, figsize=(fig_w, fig_h),
        squeeze=False, subplot_kw=subplot_kw,
    )
    axes = axes[0]

    for ax, (name, bs) in zip(axes, blocks.items()):
        title = f"{name} ({bs.block_type})"
        if ndim == 1:
            _plot_stencil_1d(ax, bs, title)
        elif ndim == 2:
            _plot_stencil_2d(ax, bs, title)
        else:
            _plot_stencil_3d(ax, bs, title)

    # Legend
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#d0d0d0",
               markersize=7, label="DF (inactive)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="royalblue",
               markersize=7, label="Input (f.in)"),
        Line2D([0], [0], marker="o", color="green", markerfacecolor="w",
               markersize=8, markeredgewidth=1.5, label="Output (f.out)"),
    ]
    fig.legend(handles=legend_elements, loc="lower center",
               ncol=3, fontsize=9, frameon=False)

    plt.tight_layout(rect=[0, 0.06, 1, 1])

    if output:
        fig.savefig(output, dpi=150)
        plt.close(fig)
    else:
        plt.show()


def compile_to_stencils(gelb_file: str) -> ProgramStencils:
    """Run the GeLB frontend + midware pipeline and extract stencils.

    Args:
        gelb_file: Path to a .gelb source file.

    Returns:
        ProgramStencils from stencil extraction.
    """
    from gelb.midware.program_analysis import run_analysis_pipeline
    from gelb.midware.stage2_midware import extract_stencils

    ast = run_analysis_pipeline(gelb_file)
    return extract_stencils(ast)
