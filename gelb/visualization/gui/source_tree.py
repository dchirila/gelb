"""
Source/variable/plot tree widget for gelb-view GUI.

Hierarchy:
  [Source: file.nc]
    |-- variable_name (dtype, shape, min..max)
    |     |-- [Plot: Heatmap t=5]
"""

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QTreeWidget, QTreeWidgetItem, QMenu,
)


# Item-type roles stored in column-0 data
_ROLE_TYPE = Qt.ItemDataRole.UserRole
_ROLE_FILEPATH = Qt.ItemDataRole.UserRole + 1
_ROLE_VARNAME = Qt.ItemDataRole.UserRole + 2
_ROLE_PLOT_ID = Qt.ItemDataRole.UserRole + 3
_ROLE_NDIM = Qt.ItemDataRole.UserRole + 4


class SourceTreeWidget(QTreeWidget):
    """Hierarchical tree showing open sources, their variables, and plots."""

    # Signals emitted to main window
    plot_requested = Signal(str, str, str)   # filepath, var_name, plot_type
    composite_plot_requested = Signal(str, list, str)  # filepath, var_names, plot_type
    file_close_requested = Signal(str)       # filepath
    plot_focus_requested = Signal(int)       # plot_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(['Name', 'Info'])
        self.setColumnWidth(0, 200)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.itemClicked.connect(self._on_click)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_source(self, filepath, dataset):
        """Add a source (open .nc file) to the tree."""
        source_item = QTreeWidgetItem()
        source_item.setText(0, _short_name(filepath))
        source_item.setToolTip(0, filepath)

        desc = getattr(dataset.ds, 'description', '')
        info_parts = [f'{dataset.ndim}D']
        if dataset.ntimesteps > 0:
            info_parts.append(f'{dataset.ntimesteps} ts')
        if desc:
            info_parts.append(desc)
        source_item.setText(1, ', '.join(info_parts))

        source_item.setData(0, _ROLE_TYPE, 'source')
        source_item.setData(0, _ROLE_FILEPATH, filepath)

        # Add variable children
        for var_name, var in dataset.variables.items():
            var_item = QTreeWidgetItem(source_item)
            var_item.setText(0, var_name)

            # Build info string: dtype, shape, min/max
            dtype_str = _netcdf_dtype_label(var)
            shape_str = 'x'.join(str(s) for s in var.shape)
            try:
                vmin, vmax = dataset.get_variable_range(var_name)
                info = f'{dtype_str}  {shape_str}  [{vmin:.4g} .. {vmax:.4g}]'
            except Exception:
                info = f'{dtype_str}  {shape_str}'

            var_item.setText(1, info)
            var_item.setData(0, _ROLE_TYPE, 'variable')
            var_item.setData(0, _ROLE_FILEPATH, filepath)
            var_item.setData(0, _ROLE_VARNAME, var_name)
            var_item.setData(0, _ROLE_NDIM, dataset.ndim)

        self.addTopLevelItem(source_item)
        source_item.setExpanded(True)

    def remove_source(self, filepath):
        """Remove a source and all its children from the tree."""
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item and item.data(0, _ROLE_FILEPATH) == filepath:
                self.takeTopLevelItem(i)
                return

    def add_plot_item(self, filepath, var_name, plot_type, plot_id):
        """Add a plot child item under the matching variable."""
        var_item = self._find_variable_item(filepath, var_name)
        if var_item is None:
            return

        plot_item = QTreeWidgetItem(var_item)
        plot_item.setText(0, f'[{plot_type}]')
        plot_item.setData(0, _ROLE_TYPE, 'plot')
        plot_item.setData(0, _ROLE_FILEPATH, filepath)
        plot_item.setData(0, _ROLE_VARNAME, var_name)
        plot_item.setData(0, _ROLE_PLOT_ID, plot_id)

        var_item.setExpanded(True)

    def remove_plot_item(self, plot_id):
        """Remove a plot item by its ID."""
        item = self._find_plot_item(plot_id)
        if item is not None:
            parent = item.parent()
            if parent:
                parent.removeChild(item)

    def selected_source_filepath(self):
        """Return filepath of the currently selected source (or None)."""
        item = self.currentItem()
        while item is not None:
            if item.data(0, _ROLE_TYPE) == 'source':
                return item.data(0, _ROLE_FILEPATH)
            item = item.parent()
        return None

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_double_click(self, item, column):
        """Double-click on a variable -> create default plot."""
        if item.data(0, _ROLE_TYPE) != 'variable':
            return
        filepath = item.data(0, _ROLE_FILEPATH)
        var_name = item.data(0, _ROLE_VARNAME)
        self.plot_requested.emit(filepath, var_name, 'Heatmap')

    def _on_click(self, item, column):
        """Click on a plot item -> request focus."""
        if item.data(0, _ROLE_TYPE) == 'plot':
            plot_id = item.data(0, _ROLE_PLOT_ID)
            if plot_id is not None:
                self.plot_focus_requested.emit(plot_id)

    def _on_context_menu(self, pos):
        """Show context menu on right-click."""
        item = self.itemAt(pos)
        if item is None:
            return

        # Check for multi-variable selection (composite plots)
        selected_vars = self._selected_variables()
        if len(selected_vars) >= 2:
            filepath, _, ndim = selected_vars[0]
            # Verify all from the same file
            if all(fp == filepath for fp, _, _ in selected_vars):
                all_names = [vn for _, vn, _ in selected_vars]
                n_vars = len(all_names)
                menu = QMenu(self)
                menu.addAction(
                    f'Side-by-Side ({n_vars} vars)',
                    lambda: self.composite_plot_requested.emit(
                        filepath, all_names, 'Side-by-Side'))
                if n_vars == 2 and ndim >= 2:
                    menu.addAction(
                        'Vector Field',
                        lambda: self.composite_plot_requested.emit(
                            filepath, all_names, 'Vector Field'))
                    menu.addAction(
                        'Streamlines',
                        lambda: self.composite_plot_requested.emit(
                            filepath, all_names, 'Streamlines'))
                if n_vars in (2, 3):
                    menu.addAction(
                        'Magnitude',
                        lambda: self.composite_plot_requested.emit(
                            filepath, all_names, 'Magnitude'))
                if n_vars == 2 and ndim == 2:
                    menu.addAction(
                        'Vorticity',
                        lambda: self.composite_plot_requested.emit(
                            filepath, all_names, 'Vorticity'))
                if n_vars == 2 and ndim >= 2:
                    menu.addAction(
                        'Particle Animation',
                        lambda: self.composite_plot_requested.emit(
                            filepath, all_names, 'Particle Animation'))
                menu.exec(self.viewport().mapToGlobal(pos))
                return

        item_type = item.data(0, _ROLE_TYPE)
        menu = QMenu(self)

        if item_type == 'source':
            filepath = item.data(0, _ROLE_FILEPATH)
            menu.addAction('Close File',
                           lambda: self.file_close_requested.emit(filepath))

        elif item_type == 'variable':
            filepath = item.data(0, _ROLE_FILEPATH)
            var_name = item.data(0, _ROLE_VARNAME)
            ndim = item.data(0, _ROLE_NDIM)
            menu.addAction(
                'New Heatmap',
                lambda: self.plot_requested.emit(filepath, var_name, 'Heatmap'))
            if ndim == 1:
                menu.addAction(
                    'New Line Plot',
                    lambda: self.plot_requested.emit(
                        filepath, var_name, 'Line Plot'))
            if ndim >= 2:
                menu.addAction(
                    'New Cross-Section',
                    lambda: self.plot_requested.emit(
                        filepath, var_name, 'Cross-Section'))
            menu.addAction(
                'New Animation',
                lambda: self.plot_requested.emit(
                    filepath, var_name, 'Animation'))

        elif item_type == 'plot':
            plot_id = item.data(0, _ROLE_PLOT_ID)
            menu.addAction('Close Plot',
                           lambda: self._close_plot(plot_id))

        if not menu.isEmpty():
            menu.exec(self.viewport().mapToGlobal(pos))

    def _close_plot(self, plot_id):
        """Request closing a plot from the context menu."""
        # The main window handles the actual closing; we just remove
        # our tree item. The dock's closed signal handles the rest.
        from gelb.visualization.gui.main_window import GeLBViewMainWindow
        window = self.window()
        if isinstance(window, GeLBViewMainWindow):
            window._on_plot_closed(plot_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _selected_variables(self):
        """Return list of (filepath, var_name, ndim) for selected variable items."""
        result = []
        for item in self.selectedItems():
            if item.data(0, _ROLE_TYPE) == 'variable':
                result.append((
                    item.data(0, _ROLE_FILEPATH),
                    item.data(0, _ROLE_VARNAME),
                    item.data(0, _ROLE_NDIM),
                ))
        return result

    def _find_variable_item(self, filepath, var_name):
        for i in range(self.topLevelItemCount()):
            source = self.topLevelItem(i)
            if source.data(0, _ROLE_FILEPATH) != filepath:
                continue
            for j in range(source.childCount()):
                child = source.child(j)
                if child.data(0, _ROLE_VARNAME) == var_name:
                    return child
        return None

    def _find_plot_item(self, plot_id):
        for i in range(self.topLevelItemCount()):
            source = self.topLevelItem(i)
            for j in range(source.childCount()):
                var_item = source.child(j)
                for k in range(var_item.childCount()):
                    plot_item = var_item.child(k)
                    if plot_item.data(0, _ROLE_PLOT_ID) == plot_id:
                        return plot_item
        return None


def _short_name(filepath):
    """Return just the filename for display."""
    import os
    return os.path.basename(filepath)


def _netcdf_dtype_label(var):
    """Return a short human-readable dtype label for a NetCDF variable."""
    dtype = var.dtype
    if dtype == np.float64:
        return 'real'
    elif dtype == np.float32:
        return 'real32'
    elif dtype in (np.int32, np.int64):
        return 'int'
    return str(dtype)
