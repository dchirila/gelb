"""
Main window for gelb-view GUI.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QDockWidget, QWidget, QStatusBar,
)

from gelb.visualization.data_viewer import GeLBDataset
from gelb.visualization.gui.actions import (
    create_open_action, create_close_action, create_quit_action,
)
from gelb.visualization.gui.source_tree import SourceTreeWidget


class GeLBViewMainWindow(QMainWindow):
    """Main application window for gelb-view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('gelb-view')
        self.resize(1200, 800)

        # Open datasets: filepath -> GeLBDataset
        self._datasets = {}
        # Active plot docks: id -> PlotDockWidget
        self._plot_docks = {}
        self._next_plot_id = 0

        self._setup_menus()
        self._setup_source_tree()
        self._setup_status_bar()

        # Hide central widget (all content lives in dock widgets)
        central = QWidget()
        central.setMaximumSize(0, 0)
        self.setCentralWidget(central)

        # Allow nested docking (split in any direction, like VSCode panes)
        self.setDockNestingEnabled(True)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_menus(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu('&File')
        file_menu.addAction(create_open_action(self, self._on_open))
        file_menu.addAction(create_close_action(self, self._on_close))
        file_menu.addSeparator()
        file_menu.addAction(create_quit_action(self, self.close))

    def _setup_source_tree(self):
        self._source_tree = SourceTreeWidget()
        tree_dock = QDockWidget('Sources', self)
        tree_dock.setWidget(self._source_tree)
        tree_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, tree_dock)

        # Connect signals
        self._source_tree.plot_requested.connect(self._create_plot)
        self._source_tree.composite_plot_requested.connect(
            self._create_composite_plot)
        self._source_tree.file_close_requested.connect(self.close_file)

    def _setup_status_bar(self):
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage('Ready')

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------

    def open_file(self, filepath):
        """Open a NetCDF file and add it to the source tree."""
        if filepath in self._datasets:
            self._status_bar.showMessage(
                f'Already open: {filepath}', 3000)
            return

        try:
            dataset = GeLBDataset(filepath)
        except Exception as e:
            self._status_bar.showMessage(f'Error opening {filepath}: {e}',
                                         5000)
            return

        self._datasets[filepath] = dataset
        self._source_tree.add_source(filepath, dataset)
        self._status_bar.showMessage(f'Opened: {filepath}', 3000)

        # Give a newly opened 1D/2D dataset an immediate, useful view.
        # Additional variables remain available from the source tree.
        if dataset.ndim in (1, 2) and dataset.ntimesteps > 0 and dataset.variables:
            var_name = next(iter(dataset.variables))
            plot_type = ('Line Plot' if dataset.ndim == 1
                         and dataset.ntimesteps == 1 else 'Heatmap')
            self._create_plot(filepath, var_name, plot_type)

    def close_file(self, filepath):
        """Close a dataset and remove all associated plots."""
        dataset = self._datasets.pop(filepath, None)
        if dataset is None:
            return

        # Close all plot docks associated with this file
        to_remove = [
            pid for pid, dock in self._plot_docks.items()
            if dock.filepath == filepath
        ]
        for pid in to_remove:
            dock = self._plot_docks.pop(pid)
            self.removeDockWidget(dock)
            dock.deleteLater()

        self._source_tree.remove_source(filepath)
        dataset.close()
        self._status_bar.showMessage(f'Closed: {filepath}', 3000)

    # ------------------------------------------------------------------
    # Plot management
    # ------------------------------------------------------------------

    def _create_plot(self, filepath, var_name, plot_type):
        """Create a new plot dock widget."""
        from gelb.visualization.gui.plot_panel import PlotDockWidget

        dataset = self._datasets.get(filepath)
        if dataset is None:
            return

        plot_id = self._next_plot_id
        self._next_plot_id += 1

        dock = PlotDockWidget(
            filepath, dataset, var_name, plot_type, plot_id, self)
        dock.closed.connect(self._on_plot_closed)
        self._plot_docks[plot_id] = dock

        # Find existing plot docks to split space with
        existing = [d for pid, d in self._plot_docks.items()
                    if pid != plot_id and d.isVisible()]
        if existing:
            # Split vertically with the last existing dock
            self.splitDockWidget(existing[-1], dock, Qt.Orientation.Horizontal)
        else:
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self._source_tree.add_plot_item(filepath, var_name, plot_type, plot_id)
        self._status_bar.showMessage(
            f'{plot_type}: {var_name}', 3000)

    def _create_composite_plot(self, filepath, var_names, plot_type):
        """Create a new composite plot dock widget (multiple variables)."""
        from gelb.visualization.gui.composite_plot_panel import (
            CompositePlotDockWidget,
        )

        dataset = self._datasets.get(filepath)
        if dataset is None:
            return

        plot_id = self._next_plot_id
        self._next_plot_id += 1

        dock = CompositePlotDockWidget(
            filepath, dataset, var_names, plot_type, plot_id, self)
        dock.closed.connect(self._on_plot_closed)
        self._plot_docks[plot_id] = dock

        existing = [d for pid, d in self._plot_docks.items()
                    if pid != plot_id and d.isVisible()]
        if existing:
            self.splitDockWidget(existing[-1], dock, Qt.Orientation.Horizontal)
        else:
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        label = ', '.join(var_names)
        self._source_tree.add_plot_item(
            filepath, var_names[0], f'{plot_type} ({label})', plot_id)
        self._status_bar.showMessage(f'{plot_type}: {label}', 3000)

    def _on_plot_closed(self, plot_id):
        """Handle a plot dock being closed."""
        dock = self._plot_docks.pop(plot_id, None)
        if dock is not None:
            self._source_tree.remove_plot_item(plot_id)
            self.removeDockWidget(dock)
            dock.deleteLater()

    def raise_plot(self, plot_id):
        """Bring a plot dock to the front."""
        dock = self._plot_docks.get(plot_id)
        if dock is not None:
            dock.raise_()
            dock.setFocus()

    # ------------------------------------------------------------------
    # Menu callbacks
    # ------------------------------------------------------------------

    def _on_open(self):
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, 'Open NetCDF File', '',
            'NetCDF Files (*.nc);;All Files (*)')
        for fp in filepaths:
            self.open_file(fp)

    def _on_close(self):
        filepath = self._source_tree.selected_source_filepath()
        if filepath:
            self.close_file(filepath)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        """Stop all animations and close all datasets on window close."""
        for dock in self._plot_docks.values():
            if dock._anim_controls:
                dock._anim_controls.stop()
        for dataset in self._datasets.values():
            dataset.close()
        self._datasets.clear()
        super().closeEvent(event)
