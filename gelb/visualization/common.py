"""
Shared plotting utilities for gelb-view.

Used by both data_viewer (NetCDF output) and future algo_viewer
(AST-driven algorithm visualization).
"""

import matplotlib.pyplot as plt
import numpy as np


def create_figure(n_panels, title=None, figsize_per_panel=(6, 5)):
    """Create a figure with n_panels side-by-side subplots.

    Returns (fig, axes) where axes is always a list.
    """
    width = figsize_per_panel[0] * n_panels
    height = figsize_per_panel[1]
    fig, axes = plt.subplots(1, n_panels, figsize=(width, height))
    if n_panels == 1:
        axes = [axes]
    if title:
        fig.suptitle(title)
    return fig, axes


def image_data(data):
    """``data`` in the form an image should get it: an integer array as
    float64, any other array unchanged.

    matplotlib resamples an integer image whose range is at most 1e8 in
    float32, which rounds every value above 2**24: an ``int64`` field
    near 3e9 showed one or two colours per row.  float64 holds every
    integer up to 2**53 exactly, and a masked array keeps its mask.
    """
    if np.asanyarray(data).dtype.kind in 'iub':
        return np.ma.asarray(data, dtype=np.float64)
    return data


def add_colorbar(fig, ax, im, label=None):
    """Add a colorbar beside ``ax``, as tall as the plot itself.

    ``fig.colorbar(im, ax=ax)`` spans the axes box, which an equal-aspect
    image does not fill; a divider axes follows the drawn image instead.
    ``Colorbar.remove()`` removes that axes too.
    """
    from mpl_toolkits.axes_grid1 import make_axes_locatable
    cax = make_axes_locatable(ax).append_axes('right', size='4%', pad=0.1)
    cbar = fig.colorbar(im, cax=cax)
    if label:
        cbar.set_label(label)
    return cbar


def configure_xy_axes(
        ax,
        *,
        title=None,
        show_ylabel=True,
        label_fontsize=8,
        tick_labelsize=7):
    """Apply the standard compact x/y domain-axis styling."""
    ax.set_xlabel('$x$', fontsize=label_fontsize)
    if show_ylabel:
        ax.set_ylabel('$y$', fontsize=label_fontsize)
    if title is not None:
        ax.set_title(title, fontsize=label_fontsize)
    ax.tick_params(labelsize=tick_labelsize)


def finish_figure(
        fig,
        output=None,
        dpi=150,
        *,
        bbox_inches=None,
        layout_rect=None,
        close_after_show=False):
    """Save to file or display interactively."""
    if layout_rect is None:
        fig.tight_layout()
    else:
        fig.tight_layout(rect=layout_rect)
    if output:
        fig.savefig(output, dpi=dpi, bbox_inches=bbox_inches)
        plt.close(fig)
    else:
        plt.show()
        if close_after_show:
            plt.close(fig)
