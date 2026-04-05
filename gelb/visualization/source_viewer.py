"""Unified source viewer -- geometry + stencils side-by-side or overlaid.

Powers the ``gelb-view source`` subcommand.  Five render modes:

- ``geo``      -- geometry only (delegates to ``geo_viewer.plot_geometry``)
- ``algo``     -- stencils only (delegates to ``algo_viewer.plot_stencils``)
- ``both``     -- side-by-side
- ``combined`` -- geometry heatmap with arrows from a chosen cell to its
  block's read neighbours (the killer feature)

Plus a JSON export mode for VSCode/external tools.
"""

from __future__ import annotations

import base64
import json
import pathlib

import numpy as np

from gelb.midware.program_analysis import (
    ProgramAnalysis, compile_to_program_analysis,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plot_program_analysis(
        analysis: ProgramAnalysis,
        output: str | None = None,
        *,
        mode: str = "both",
        dpi: int = 150,
        cell: tuple[int, int] | None = None,
        block: str | None = None,
) -> None:
    """Render a program-analysis figure.

    Parameters
    ----------
    analysis : ProgramAnalysis
        Bundled geometry + stencils.
    output : str, optional
        Save to this path; otherwise show with ``plt.show()``.
    mode : {'geo', 'algo', 'both', 'combined'}
        Which view to render.
    dpi : int
        Figure DPI.
    cell : (int, int), optional
        For combined mode: cell to overlay arrows from.  Defaults to the
        centroid of the first non-FLUID, non-masked, non-static NC.
    block : str, optional
        For combined mode: dynamic block name to use for the read
        footprint.  Defaults to the chosen cell's NC's dynamic block.
    """
    if mode == "geo":
        from gelb.visualization.geo_viewer import plot_geometry
        plot_geometry(analysis.geometry, output=output, dpi=dpi)
        return
    if mode == "algo":
        from gelb.visualization.algo_viewer import plot_stencils
        plot_stencils(analysis.stencils, block_names=None,
                      output=output)
        return
    if mode == "both":
        _plot_both(analysis, output, dpi)
        return
    if mode == "combined":
        _plot_combined(analysis, output, dpi, cell=cell, block=block)
        return
    raise ValueError(f"Unknown mode: {mode!r}")


def export_program_analysis_json(
        analysis: ProgramAnalysis,
        out_path: str | pathlib.Path) -> None:
    """Export geometry + stencils as a single JSON document.

    Schema::

        {
          "geometry": {ndim, grid_sizes, periodic, nc_order, nc_info,
                       boundary_contacts, nc_map_b64, nc_map_dtype,
                       nc_map_shape},
          "stencils": {blocks: {name: {block_type, reads: [...],
                                       writes: [...]}, ...},
                       lattices: {name: {d, q, grid_size, periodic}}}
        }
    """
    geo = analysis.geometry
    sten = analysis.stencils

    nc_map_arr = np.ascontiguousarray(geo.nc_map.astype(np.int32))
    nc_map_b64 = base64.b64encode(nc_map_arr.tobytes()).decode("ascii")

    geometry_json = {
        "ndim": int(geo.ndim),
        "grid_sizes": [int(s) for s in geo.grid_sizes],
        "periodic": [bool(p) for p in geo.periodic],
        "nc_order": list(geo.nc_order),
        "nc_info": {
            name: {
                "nc_id": int(info.nc_id),
                "initializer": info.initializer,
                "dynamic": info.dynamic,
                "gauge": info.gauge,
                "masked": bool(info.masked),
                "bbox": ([[int(lo), int(hi)] for lo, hi in info.bbox]
                         if info.bbox else None),
                "bbox_dense": bool(info.bbox_dense),
            }
            for name, info in geo.nc_info.items()
        },
        "boundary_contacts": {
            name: {str(d): sorted(sides) for d, sides in dims.items()}
            for name, dims in geo.boundary_contacts.items()
        },
        "nc_map_b64": nc_map_b64,
        "nc_map_dtype": "int32",
        "nc_map_shape": list(nc_map_arr.shape),
    }

    def _access_to_json(a):
        return {
            "lattice_name": a.lattice_name,
            "spatial_offsets": [int(o) for o in a.spatial_offsets],
            "df_index": (int(a.df_index)
                         if a.df_index is not None else None),
        }

    blocks_json = {}
    for name, block in sten.blocks.items():
        blocks_json[name] = {
            "block_type": block.block_type,
            "reads": [_access_to_json(a) for a in block.reads],
            "writes": [_access_to_json(a) for a in block.writes],
        }

    lattices_json = {
        name: {
            "d": int(meta.d),
            "q": int(meta.q),
            "grid_size": ([int(s) for s in meta.grid_size]
                          if meta.grid_size is not None else None),
            "periodic": ([bool(p) for p in meta.periodic]
                         if meta.periodic is not None else None),
        }
        for name, meta in sten.lattices.items()
    }

    doc = {
        "geometry": geometry_json,
        "stencils": {"blocks": blocks_json, "lattices": lattices_json},
    }
    pathlib.Path(out_path).write_text(json.dumps(doc, indent=2))


# ---------------------------------------------------------------------------
# Internal renderers
# ---------------------------------------------------------------------------

def _plot_both(analysis: ProgramAnalysis,
               output: str | None, dpi: int) -> None:
    """Side-by-side: geometry on the left, stencils on the right."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    from gelb.visualization.common import configure_xy_axes, finish_figure
    from gelb.visualization.geo_viewer import (
        _NC_COLORS, _MASKED_HATCH, _per_nc_counts, _build_legend_label,
    )

    geo = analysis.geometry
    n_nc = len(geo.nc_order)
    colors = [_NC_COLORS[i % len(_NC_COLORS)] for i in range(n_nc)]
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(list(range(1, n_nc + 2)), cmap.N)

    fig = plt.figure(figsize=(12, 4.5), dpi=dpi)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.5, 1.0])
    ax_geo = fig.add_subplot(gs[0])
    ax_alg = fig.add_subplot(gs[1])

    # --- Geometry on the left ---
    if geo.ndim == 1:
        ax_geo.imshow(geo.nc_map.reshape(1, -1), cmap=cmap, norm=norm,
                      aspect='auto', interpolation='nearest',
                      extent=[0, geo.grid_sizes[0], 0, 1])
        ax_geo.set_yticks([])
        configure_xy_axes(ax_geo, show_ylabel=False)
    elif geo.ndim == 2:
        ax_geo.imshow(geo.nc_map.T, origin='lower', cmap=cmap, norm=norm,
                      aspect='equal', interpolation='nearest')
        configure_xy_axes(ax_geo)
    else:
        z_mid = geo.grid_sizes[2] // 2
        ax_geo.imshow(geo.nc_map[:, :, z_mid].T, origin='lower',
                      cmap=cmap, norm=norm, aspect='equal',
                      interpolation='nearest')
        configure_xy_axes(ax_geo, title=f'xy slice at z={z_mid}')

    counts = _per_nc_counts(geo)
    total = geo.nc_map.size
    legend_patches = []
    for i, name in enumerate(geo.nc_order):
        info = geo.nc_info[name]
        label = _build_legend_label(name, info, counts[name], total)
        patch = Patch(facecolor=colors[i], label=label,
                      edgecolor='#555', linewidth=0.5)
        if info.masked:
            patch.set_hatch(_MASKED_HATCH)
        legend_patches.append(patch)
    ax_geo.legend(handles=legend_patches, loc='upper right',
                  fontsize=6, framealpha=0.85)

    # --- Stencils summary on the right ---
    sten = analysis.stencils
    lines = ["Block stencils:"]
    for name, block in sten.blocks.items():
        if block.block_type != "dynamic":
            continue
        n_r = len(block.reads)
        n_w = len(block.writes)
        rd_offs = sorted(set(tuple(a.spatial_offsets)
                              for a in block.reads))
        max_reach = max(
            (max(abs(o) for o in offs) for offs in rd_offs),
            default=0,
        )
        lines.append(
            f"  {name} ({block.block_type}): "
            f"{n_r} reads, {n_w} writes, max reach = {max_reach}"
        )
        for offs in rd_offs[:8]:
            lines.append(f"      read offset {offs}")
        if len(rd_offs) > 8:
            lines.append(f"      ... and {len(rd_offs) - 8} more")

    ax_alg.text(0.02, 0.98, "\n".join(lines),
                family='monospace', fontsize=7,
                verticalalignment='top',
                transform=ax_alg.transAxes)
    ax_alg.set_xticks([])
    ax_alg.set_yticks([])
    ax_alg.set_title("Stencils summary", fontsize=8)

    fig.suptitle("Program analysis — geometry + stencils",
                 fontsize=10)
    finish_figure(
        fig,
        output=output,
        dpi=dpi,
        bbox_inches='tight',
        close_after_show=True,
    )


def _plot_combined(analysis: ProgramAnalysis,
                   output: str | None, dpi: int,
                   cell: tuple[int, int] | None,
                   block: str | None) -> None:
    """Geometry heatmap with arrows from one cell to its read neighbours."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    from gelb.visualization.common import configure_xy_axes, finish_figure
    from gelb.visualization.geo_viewer import (
        _NC_COLORS, _MASKED_HATCH, _per_nc_counts, _build_legend_label,
    )

    geo = analysis.geometry
    sten = analysis.stencils

    if geo.ndim != 2:
        raise NotImplementedError(
            "combined mode currently supports 2D geometries only "
            f"(got {geo.ndim}D)")

    # Pick a default cell if none given
    if cell is None:
        cell, block = _pick_default_cell_and_block(geo, sten)
    else:
        if block is None:
            x, y = cell
            nc_id = int(geo.nc_map[x, y])
            nc_name = geo.nc_order[nc_id - 1]
            block = geo.nc_info[nc_name].dynamic

    cx, cy = cell
    block_data = sten.blocks.get(block) if block else None

    n_nc = len(geo.nc_order)
    colors = [_NC_COLORS[i % len(_NC_COLORS)] for i in range(n_nc)]
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(list(range(1, n_nc + 2)), cmap.N)

    Nx, Ny = geo.grid_sizes
    nc_id = int(geo.nc_map[cx, cy])
    nc_name = (geo.nc_order[nc_id - 1] if 0 < nc_id <= n_nc else "?")

    # Compute read targets so we know how big the zoom needs to be
    targets: list[tuple[int, int, int]] = []  # (tx, ty, df_index)
    if block_data is not None:
        seen = set()
        for access in block_data.reads:
            if len(access.spatial_offsets) != 2:
                continue
            dx, dy = (int(o) for o in access.spatial_offsets[:2])
            if (dx, dy) == (0, 0):
                continue
            tx, ty = cx - dx, cy - dy
            if (tx, ty) in seen:
                continue
            seen.add((tx, ty))
            targets.append((tx, ty, access.df_index))

    # Two-panel layout: full domain (overview) + zoomed (the arrows)
    fig = plt.figure(figsize=(11, 4.5), dpi=dpi)
    gs = fig.add_gridspec(1, 2, width_ratios=[2, 1])
    ax_full = fig.add_subplot(gs[0])
    ax_zoom = fig.add_subplot(gs[1])

    ax_full.imshow(geo.nc_map.T, origin='lower', cmap=cmap, norm=norm,
                   aspect='equal', interpolation='nearest')
    configure_xy_axes(ax_full, title='Full domain')

    # Zoom region around (cx, cy) -- pad to include all read targets
    if targets:
        xs = [cx] + [t[0] for t in targets]
        ys = [cy] + [t[1] for t in targets]
        pad = 4
        xlo = max(0, min(xs) - pad)
        xhi = min(Nx - 1, max(xs) + pad)
        ylo = max(0, min(ys) - pad)
        yhi = min(Ny - 1, max(ys) + pad)
    else:
        pad = 6
        xlo, xhi = max(0, cx - pad), min(Nx - 1, cx + pad)
        ylo, yhi = max(0, cy - pad), min(Ny - 1, cy + pad)

    from matplotlib.patches import Rectangle
    ax_full.add_patch(Rectangle(
        (xlo - 0.5, ylo - 0.5), xhi - xlo + 1, yhi - ylo + 1,
        linewidth=0.8, edgecolor='black', facecolor='none', linestyle='--'))

    # Zoomed view
    region = geo.nc_map[xlo:xhi + 1, ylo:yhi + 1]
    ax_zoom.imshow(region.T, origin='lower', cmap=cmap, norm=norm,
                   aspect='equal', interpolation='nearest',
                   extent=[xlo - 0.5, xhi + 0.5, ylo - 0.5, yhi + 0.5])
    ax_zoom.add_patch(Rectangle(
        (cx - 0.5, cy - 0.5), 1, 1,
        linewidth=1.5, edgecolor='black', facecolor='none'))

    if targets:
        for tx, ty, df_idx in targets:
            ax_zoom.annotate(
                "", xy=(tx, ty), xytext=(cx, cy),
                arrowprops=dict(arrowstyle='->', color='black',
                                lw=0.8, shrinkA=4, shrinkB=4))
            if df_idx is not None:
                ax_zoom.text(tx, ty - 0.35, f"{df_idx}",
                             fontsize=6, ha='center', va='top',
                             color='black')

    ax_zoom.set_xlim(xlo - 0.5, xhi + 0.5)
    ax_zoom.set_ylim(ylo - 0.5, yhi + 0.5)
    configure_xy_axes(ax_zoom, title='Zoomed: read footprint',
                      show_ylabel=False)

    title = (
        f"cell ({cx}, {cy}) ∈ '{nc_name}' using block "
        f"'{block}'  ({len(targets)} read sites)"
        if block_data is not None
        else f"cell ({cx}, {cy}) ∈ '{nc_name}' — no dynamic block"
    )

    counts = _per_nc_counts(geo)
    total = geo.nc_map.size
    legend_patches = []
    for i, name in enumerate(geo.nc_order):
        info = geo.nc_info[name]
        label = _build_legend_label(name, info, counts[name], total)
        patch = Patch(facecolor=colors[i], label=label,
                      edgecolor='#555', linewidth=0.5)
        if info.masked:
            patch.set_hatch(_MASKED_HATCH)
        legend_patches.append(patch)
    ax_full.legend(handles=legend_patches, loc='upper right',
                   fontsize=6, framealpha=0.85)

    fig.suptitle(title, fontsize=9)
    finish_figure(
        fig,
        output=output,
        dpi=dpi,
        bbox_inches='tight',
        close_after_show=True,
    )


def _pick_default_cell_and_block(geo, stencils=None
                                  ) -> tuple[tuple[int, int], str | None]:
    """Pick a sensible default cell to overlay arrows from.

    Prefers:
    1. A non-masked NC whose dynamic block has non-local reads
       (most informative -- shows actual stencil arrows).
    2. Any non-masked NC with a dynamic block (may show only local reads).

    The chosen cell is guaranteed to actually belong to the picked NC.
    """
    def _first_cell_of(nc_id: int) -> tuple[int, int]:
        coords = np.argwhere(geo.nc_map == nc_id)
        if len(coords) == 0:
            return (0, 0)
        centre = coords.mean(axis=0)
        dists = ((coords - centre) ** 2).sum(axis=1)
        nearest = coords[int(dists.argmin())]
        return tuple(int(c) for c in nearest)

    def _has_nonlocal_reads(block_name: str) -> bool:
        if stencils is None:
            return False
        block = stencils.blocks.get(block_name)
        if block is None:
            return False
        for access in block.reads:
            if any(o != 0 for o in access.spatial_offsets):
                return True
        return False

    # Pass 1: prefer NCs whose block has non-local reads
    for name in geo.nc_order:
        info = geo.nc_info[name]
        if not info.dynamic or info.masked:
            continue
        if _has_nonlocal_reads(info.dynamic):
            return _first_cell_of(info.nc_id), info.dynamic

    # Pass 2: any non-masked NC with a dynamic
    for name in geo.nc_order:
        info = geo.nc_info[name]
        if info.dynamic and not info.masked:
            return _first_cell_of(info.nc_id), info.dynamic

    return (0, 0), None
