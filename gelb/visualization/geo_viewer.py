"""Geometry viewer -- visualise node-class layout from a .gelb file.

Resolves geometry paint statements and renders the per-cell
node-class map as a colour-coded figure.  Supports 1D (bar),
2D (heatmap), and 3D (orthogonal slices) geometries.

Usage::

    from gelb.visualization.geo_viewer import compile_to_geometry, plot_geometry
    geo = compile_to_geometry("examples/sukop/karman_vortex_street_2d_bgk.gelb")
    plot_geometry(geo, output="geometry.png")
"""

from __future__ import annotations

import pathlib
from typing import Sequence

import numpy as np

from gelb.midware.geometry import ResolvedGeometry


# Compact, colourblind-friendly palette (qualitative Set2 + extras).
_NC_COLORS = [
    '#66c2a5',  # teal
    '#fc8d62',  # orange
    '#8da0cb',  # blue
    '#e78ac3',  # pink
    '#a6d854',  # green
    '#ffd92f',  # yellow
    '#e5c494',  # tan
    '#b3b3b3',  # gray (used for masked)
    '#1b9e77',  # dark teal
    '#d95f02',  # dark orange
]

_MASKED_COLOR = '#cccccc'
_MASKED_HATCH = '///'


def compile_to_geometry(gelb_file: str | pathlib.Path) -> ResolvedGeometry:
    """Run the GeLB frontend + midware pipeline and resolve geometry.

    Parameters
    ----------
    gelb_file : str or Path
        Path to a ``.gelb`` source file.

    Returns
    -------
    ResolvedGeometry
        Resolved node-class map with metadata.
    """
    from gelb.midware.program_analysis import run_analysis_pipeline
    from gelb.midware.geometry import resolve_geometry

    ast = run_analysis_pipeline(gelb_file)
    return resolve_geometry(ast)


def _per_nc_counts(geo: ResolvedGeometry) -> dict[str, int]:
    """Return cell count per node class."""
    return {name: int((geo.nc_map == info.nc_id).sum())
            for name, info in geo.nc_info.items()}


def _build_legend_label(name: str, info, count: int, total: int) -> str:
    """Build a legend label like 'WALL (masked) -- 312 cells (1.2%)'."""
    label = name
    extras = []
    if info.masked:
        extras.append("masked")
    if not info.dynamic:
        extras.append("static")
    if extras:
        label += f" ({', '.join(extras)})"
    pct = 100.0 * count / total if total > 0 else 0.0
    label += f" — {count:,} cells ({pct:.2f}%)"
    return label


def _sparse_nc_bbox(geo: ResolvedGeometry,
                    threshold: float = 0.005) -> tuple | None:
    """Find the union bbox of NCs with <threshold of total cells.

    Returns ``((x_lo, x_hi), (y_lo, y_hi), ...)`` or ``None`` if no sparse
    NCs exist (or all NCs are sparse -- meaning the geometry is small
    enough that auto-zoom isn't needed).
    """
    counts = _per_nc_counts(geo)
    total = geo.nc_map.size
    sparse_nc_names = [n for n, c in counts.items()
                       if c / total < threshold and c > 0]
    if not sparse_nc_names:
        return None
    if len(sparse_nc_names) == len(geo.nc_order):
        return None  # everything is sparse -> no useful zoom
    bboxes = [geo.nc_info[n].bbox for n in sparse_nc_names
              if geo.nc_info[n].bbox is not None]
    if not bboxes:
        return None
    union = []
    for d in range(geo.ndim):
        lo = min(bb[d][0] for bb in bboxes)
        hi = max(bb[d][1] for bb in bboxes)
        union.append((lo, hi))
    return tuple(union)


def plot_geometry(
        geo: ResolvedGeometry,
        output: str | None = None,
        *,
        dpi: int = 150,
        title: str | None = None,
        max_height: float = 2.5,
        auto_zoom: bool = True,
) -> None:
    """Render the geometry as a colour-coded figure.

    Parameters
    ----------
    geo : ResolvedGeometry
        The resolved geometry data.
    output : str, optional
        If given, save to this file path.  Otherwise ``plt.show()``.
    dpi : int
        Figure DPI.
    title : str, optional
        Override the figure title.
    max_height : float
        Maximum figure height in inches (keeps figures compact).
    auto_zoom : bool
        If True (default), 2D geometries with sparse NCs (<0.5% of cells)
        get an inset showing the obstacle region zoomed in.
    """
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    from gelb.visualization.common import finish_figure

    n_nc = len(geo.nc_order)
    colors = [_NC_COLORS[i % len(_NC_COLORS)] for i in range(n_nc)]
    cmap = ListedColormap(colors)
    bounds = list(range(1, n_nc + 2))
    norm = BoundaryNorm(bounds, cmap.N)

    counts = _per_nc_counts(geo)
    total_cells = geo.nc_map.size
    zoom_bbox = (_sparse_nc_bbox(geo)
                 if auto_zoom and geo.ndim == 2 else None)

    if geo.ndim == 1:
        fig, ax = _plot_1d(geo, cmap, norm, dpi, max_height)
    elif geo.ndim == 2:
        fig, ax = _plot_2d(geo, cmap, norm, dpi, max_height,
                           zoom_bbox=zoom_bbox)
    else:
        fig, ax = _plot_3d(geo, cmap, norm, dpi, max_height)

    legend_patches = []
    for i, nc_name in enumerate(geo.nc_order):
        info = geo.nc_info[nc_name]
        label = _build_legend_label(nc_name, info, counts[nc_name],
                                    total_cells)
        patch = Patch(facecolor=colors[i], label=label,
                      edgecolor='#555555', linewidth=0.5)
        if info.masked:
            patch.set_hatch(_MASKED_HATCH)
        legend_patches.append(patch)

    if geo.ndim == 2:
        ax.legend(handles=legend_patches, loc='upper right',
                  fontsize=7, framealpha=0.85,
                  handlelength=1.0, handleheight=0.8)
    else:
        fig.legend(handles=legend_patches, loc='lower center',
                   ncols=min(n_nc, 5), fontsize=7, framealpha=0.85,
                   handlelength=1.0, handleheight=0.8)

    if title:
        fig.suptitle(title, fontsize=9)

    finish_figure(
        fig,
        output=output,
        dpi=dpi,
        bbox_inches='tight',
        close_after_show=True,
    )


def format_geometry_stats(geo: ResolvedGeometry) -> str:
    """Return a human-readable plain-text summary of the geometry."""
    lines = []
    lines.append(f"Dimensionality:  {geo.ndim}D")
    lines.append(f"Grid sizes:      {' × '.join(str(s) for s in geo.grid_sizes)}")
    lines.append(f"Periodicity:     {tuple(geo.periodic)}")
    lines.append(f"Total cells:     {geo.nc_map.size:,}")
    lines.append(f"Node classes:    {len(geo.nc_order)}")
    lines.append("")

    counts = _per_nc_counts(geo)
    total = geo.nc_map.size

    rows = [("ID", "Name", "Cells", "%", "Masked", "Dynamic", "Gauge", "Bbox")]
    for name in geo.nc_order:
        info = geo.nc_info[name]
        c = counts[name]
        pct = 100.0 * c / total if total > 0 else 0.0
        rows.append((
            str(info.nc_id),
            name,
            f"{c:,}",
            f"{pct:.2f}",
            "yes" if info.masked else "no",
            info.dynamic or "—",
            info.gauge or "—",
            str(info.bbox) if info.bbox else "—",
        ))

    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r_i, row in enumerate(rows):
        line = "  ".join(s.ljust(w) for s, w in zip(row, widths))
        lines.append(line)
        if r_i == 0:
            lines.append("  ".join("-" * w for w in widths))

    return "\n".join(lines)


def format_geometry_ascii(geo: ResolvedGeometry,
                          max_width: int = 80,
                          max_height: int = 24) -> str:
    """Return an ASCII rendering of the geometry.

    1D: one row of single-letter NC IDs.
    2D: downsampled grid (cols=max_width, rows=max_height).
    3D: midplane xy slice, downsampled.
    """
    import numpy as np

    # Pick a single-letter glyph per NC: first letter of name, or '#' if collision.
    used = set()
    glyphs = {}
    for i, name in enumerate(geo.nc_order):
        for ch in name + "#$%&*+-=?":
            if ch.isalnum() and ch not in used:
                glyphs[i + 1] = ch
                used.add(ch)
                break
        else:
            glyphs[i + 1] = '?'

    def _slice_to_ascii(arr2d):
        ny, nx = arr2d.shape
        if nx > max_width:
            stride_x = (nx + max_width - 1) // max_width
            arr2d = arr2d[:, ::stride_x]
        if ny > max_height:
            stride_y = (ny + max_height - 1) // max_height
            arr2d = arr2d[::stride_y, :]
        rows = []
        for row in arr2d[::-1]:  # flip y so top of image = top of terminal
            rows.append("".join(glyphs.get(int(v), '?') for v in row))
        return "\n".join(rows)

    legend = "\n".join(
        f"  {glyphs[geo.nc_info[name].nc_id]} = {name}"
        for name in geo.nc_order)

    if geo.ndim == 1:
        N = geo.grid_sizes[0]
        if N > max_width:
            stride = (N + max_width - 1) // max_width
            arr = geo.nc_map[::stride]
        else:
            arr = geo.nc_map
        body = "".join(glyphs.get(int(v), '?') for v in arr)
        return f"{body}\n\nLegend:\n{legend}"

    if geo.ndim == 2:
        # nc_map shape is (NX, NY); transpose so rows=y, cols=x
        body = _slice_to_ascii(geo.nc_map.T)
        return f"{body}\n\nLegend:\n{legend}"

    # 3D -- midplane xy slice
    z_mid = geo.grid_sizes[2] // 2
    body = _slice_to_ascii(geo.nc_map[:, :, z_mid].T)
    header = f"xy slice at z = {z_mid}"
    return f"{header}\n{body}\n\nLegend:\n{legend}"


def export_geometry_npy(geo: ResolvedGeometry,
                        out_path: str | pathlib.Path) -> None:
    """Save the nc_map as .npy and a sidecar .json with metadata.

    Saves two files: ``out_path`` (the .npy) and ``out_path.with_suffix('.json')``
    (the metadata).
    """
    import json
    import numpy as np

    out_path = pathlib.Path(out_path)
    np.save(out_path, geo.nc_map)
    sidecar = out_path.with_suffix('.json')

    def _coerce(v):
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, (np.bool_,)):
            return bool(v)
        return v

    metadata = {
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
    }
    sidecar.write_text(json.dumps(metadata, indent=2))


def _plot_1d(geo, cmap, norm, dpi, max_height):
    import matplotlib.pyplot as plt
    N = geo.grid_sizes[0]
    fig_w = min(8, max(3, N / 10))
    fig, ax = plt.subplots(figsize=(fig_w, max_height * 0.5), dpi=dpi)
    data = geo.nc_map.reshape(1, -1)
    ax.imshow(data, cmap=cmap, norm=norm, aspect='auto',
              interpolation='nearest',
              extent=[0, N, 0, 1])
    ax.set_xlabel('cell index $x$', fontsize=8)
    ax.set_yticks([])
    ax.set_xlim(0, N)
    return fig, ax


def _plot_2d(geo, cmap, norm, dpi, max_height, *, zoom_bbox=None):
    import matplotlib.pyplot as plt
    from gelb.visualization.common import configure_xy_axes
    Nx, Ny = geo.grid_sizes
    aspect_ratio = Nx / max(Ny, 1)
    fig_w = min(10, max(3, aspect_ratio * max_height))
    fig_h = min(max_height, fig_w / max(aspect_ratio, 0.1))

    if zoom_bbox is None:
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
        ax.imshow(geo.nc_map.T, origin='lower', cmap=cmap, norm=norm,
                  aspect='equal', interpolation='nearest')
        configure_xy_axes(ax)
        return fig, ax

    # Side-by-side: full domain + zoomed obstacle inset
    (xlo, xhi), (ylo, yhi) = zoom_bbox
    pad_x = max(2, (xhi - xlo) // 4)
    pad_y = max(2, (yhi - ylo) // 4)
    xlo, xhi = max(0, xlo - pad_x), min(Nx - 1, xhi + pad_x)
    ylo, yhi = max(0, ylo - pad_y), min(Ny - 1, yhi + pad_y)

    fig, (ax_full, ax_zoom) = plt.subplots(
        1, 2, figsize=(fig_w + 3, fig_h), dpi=dpi,
        gridspec_kw={'width_ratios': [2, 1]})

    ax_full.imshow(geo.nc_map.T, origin='lower', cmap=cmap, norm=norm,
                   aspect='equal', interpolation='nearest')
    configure_xy_axes(ax_full, title='Full domain')
    # Draw a rectangle on the full view showing the zoom region
    from matplotlib.patches import Rectangle
    ax_full.add_patch(Rectangle(
        (xlo - 0.5, ylo - 0.5), xhi - xlo + 1, yhi - ylo + 1,
        linewidth=0.8, edgecolor='black', facecolor='none', linestyle='--'))

    region = geo.nc_map[xlo:xhi + 1, ylo:yhi + 1]
    ax_zoom.imshow(region.T, origin='lower', cmap=cmap, norm=norm,
                   aspect='equal', interpolation='nearest',
                   extent=[xlo, xhi + 1, ylo, yhi + 1])
    configure_xy_axes(ax_zoom, title='Zoomed', show_ylabel=False)

    # Legend goes on the zoom panel since it has the most empty space
    return fig, ax_zoom


def _plot_3d(geo, cmap, norm, dpi, max_height):
    import matplotlib.pyplot as plt
    Nx, Ny, Nz = geo.grid_sizes
    mid = [s // 2 for s in geo.grid_sizes]
    fig, axes = plt.subplots(1, 3, figsize=(9, max_height), dpi=dpi)

    # xy slice at z=mid[2]
    axes[0].imshow(geo.nc_map[:, :, mid[2]].T, origin='lower',
                   cmap=cmap, norm=norm, aspect='equal',
                   interpolation='nearest')
    axes[0].set_title(f'$xy$ at $z={mid[2]}$', fontsize=8)
    axes[0].set_xlabel('$x$', fontsize=7)
    axes[0].set_ylabel('$y$', fontsize=7)

    # xz slice at y=mid[1]
    axes[1].imshow(geo.nc_map[:, mid[1], :].T, origin='lower',
                   cmap=cmap, norm=norm, aspect='equal',
                   interpolation='nearest')
    axes[1].set_title(f'$xz$ at $y={mid[1]}$', fontsize=8)
    axes[1].set_xlabel('$x$', fontsize=7)
    axes[1].set_ylabel('$z$', fontsize=7)

    # yz slice at x=mid[0]
    axes[2].imshow(geo.nc_map[mid[0], :, :].T, origin='lower',
                   cmap=cmap, norm=norm, aspect='equal',
                   interpolation='nearest')
    axes[2].set_title(f'$yz$ at $x={mid[0]}$', fontsize=8)
    axes[2].set_xlabel('$y$', fontsize=7)
    axes[2].set_ylabel('$z$', fontsize=7)

    for ax in axes:
        ax.tick_params(labelsize=6)
    return fig, axes[0]
