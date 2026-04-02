#!/usr/bin/env python3
"""
Results Browser for EVTX Ripper / Chainsaw GUI.

Opens a modeless window that lets users browse chainsaw_results subfolders
and view sigma reports (markdown) alongside hunt/search output (CSV or JSON).
"""

from __future__ import annotations

import csv
import json
import os
from collections import namedtuple
from typing import Any, List, Optional

try:
    import markdown as _md_lib
    _MARKDOWN_AVAILABLE = True
except ImportError:
    _MARKDOWN_AVAILABLE = False

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
)
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableView,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QSizePolicy,
    QWidget,
)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

ResultEntry = namedtuple(
    "ResultEntry",
    ["folder_name", "folder_path", "md_path", "csv_path", "json_path"],
)


def scan_results_folder(root_dir: str) -> List[ResultEntry]:
    """Return ResultEntry list for every direct subfolder in *root_dir*."""
    entries: List[ResultEntry] = []

    if not os.path.isdir(root_dir):
        return entries

    for name in os.listdir(root_dir):
        folder_path = os.path.join(root_dir, name)
        if not os.path.isdir(folder_path):
            continue

        md_path: Optional[str] = None
        csv_path: Optional[str] = None
        json_path: Optional[str] = None

        # Find sigma report markdown (direct children of run folder)
        for fname in os.listdir(folder_path):
            fpath = os.path.join(folder_path, fname)
            if fname.lower().endswith(".md") and os.path.isfile(fpath):
                md_path = fpath
                break  # take first .md found

        # Hunt output CSV lives in hunt-output/
        hunt_dir = os.path.join(folder_path, "hunt-output")
        if os.path.isdir(hunt_dir):
            candidate = os.path.join(hunt_dir, "sigma.csv")
            if os.path.isfile(candidate):
                csv_path = candidate
            else:
                # Fall back to any .csv in hunt-output
                for fname in os.listdir(hunt_dir):
                    if fname.lower().endswith(".csv"):
                        csv_path = os.path.join(hunt_dir, fname)
                        break

        # Search output JSON (or txt) directly in run folder
        for ext in ("json", "txt"):
            candidate = os.path.join(folder_path, f"search-output.{ext}")
            if os.path.isfile(candidate):
                json_path = candidate
                break

        entries.append(ResultEntry(name, folder_path, md_path, csv_path, json_path))

    # Sort newest-first: the folder name suffix is YYMMDD-HHMM so lexicographic
    # descending works correctly.
    entries.sort(key=lambda e: e.folder_name, reverse=True)
    return entries


# ---------------------------------------------------------------------------
# Markdown pane
# ---------------------------------------------------------------------------

_REPORT_HTML_STYLE = """
<style>
body { font-family: Segoe UI, sans-serif; font-size: 13px; color: #2f1e1e;
    background: #F8E7EB; margin: 12px; }
h1 { font-size: 1.3em; color: #6c3d3d; border-bottom: 1px solid #cfa8a8; padding-bottom: 4px; }
h2 { font-size: 1.1em; color: #6c3d3d; }
h3 { font-size: 1.0em; color: #6c3d3d; }
code, pre { background: rgba(255, 255, 255, 0.78); border-radius: 4px; padding: 2px 6px;
          font-family: Consolas, monospace; font-size: 12px; color: #7a3d3d; }
pre { padding: 8px; display: block; white-space: pre-wrap; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; }
th { background: rgba(230, 198, 198, 0.88); color: #3a2424; padding: 6px 10px;
    border: 1px solid #cfa8a8; text-align: left; }
td { padding: 5px 10px; border: 1px solid #d7b3b3; vertical-align: top; }
tr:nth-child(even) { background: rgba(255, 255, 255, 0.54); }
a { color: #9e5050; }
li { margin-bottom: 3px; }
</style>
"""

_PLACEHOLDER_HTML = (
    _REPORT_HTML_STYLE
    + "<body><p style='color:#666;margin-top:30px;text-align:center;'>"
    "Select a result folder to view the sigma report.</p></body>"
)

_NO_REPORT_HTML = (
    _REPORT_HTML_STYLE
    + "<body><p style='color:#888;margin-top:30px;text-align:center;'>"
    "No sigma report (.md) found in this folder.</p></body>"
)


class MarkdownPane(QTextBrowser):
    """Left-side pane that renders a sigma report markdown file as HTML."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(False)
        self.setHtml(_PLACEHOLDER_HTML)

    def load_file(self, path: Optional[str]) -> None:
        if path is None or not os.path.isfile(path):
            self.setHtml(_NO_REPORT_HTML)
            return

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            self.setHtml(_NO_REPORT_HTML)
            return

        if _MARKDOWN_AVAILABLE:
            html_body = _md_lib.markdown(
                text,
                extensions=["tables", "fenced_code", "nl2br"],
            )
            html = _REPORT_HTML_STYLE + f"<body>{html_body}</body>"
        else:
            # Plain-text fallback
            escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html = (
                _REPORT_HTML_STYLE
                + f"<body><pre style='white-space:pre-wrap'>{escaped}</pre></body>"
            )

        self.setHtml(html)
        # Scroll to top
        bar = self.verticalScrollBar()
        if bar:
            bar.setValue(0)

    def preferred_content_width(self) -> int:
        """Return an estimated width needed to display markdown content comfortably."""
        doc_width = int(self.document().idealWidth())
        # Add margins/padding and keep within a practical readable band.
        return max(360, min(760, doc_width + 48))


# ---------------------------------------------------------------------------
# CSV table model
# ---------------------------------------------------------------------------

class CsvTableModel(QAbstractTableModel):
    """Read-only table model backed by a parsed CSV file."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._headers: List[str] = []
        self._rows: List[List[str]] = []

    def load_file(self, path: str) -> None:
        self.beginResetModel()
        self._headers = []
        self._rows = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames:
                    self._headers = list(reader.fieldnames)
                for row in reader:
                    self._rows.append([row.get(h, "") for h in self._headers])
        except OSError:
            pass
        self.endResetModel()

    # --- QAbstractTableModel interface ---

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            return self._rows[index.row()][index.column()]
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignTop | Qt.AlignLeft)
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ) -> Any:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self._headers[section] if section < len(self._headers) else ""
        return str(section + 1)


# ---------------------------------------------------------------------------
# JSON viewer widget
# ---------------------------------------------------------------------------

def _populate_tree_item(parent: QTreeWidgetItem, key: str, value: Any) -> None:
    """Recursively build a QTreeWidgetItem tree from a JSON value."""
    if isinstance(value, dict):
        node = QTreeWidgetItem(parent, [key, "{…}"])
        for k, v in value.items():
            _populate_tree_item(node, str(k), v)
    elif isinstance(value, list):
        node = QTreeWidgetItem(parent, [key, f"[{len(value)} items]"])
        for i, v in enumerate(value):
            _populate_tree_item(node, f"[{i}]", v)
    else:
        QTreeWidgetItem(parent, [key, str(value)])


class JsonViewWidget(QWidget):
    """
    Displays JSON content.

    - List of dicts → flat QTableView
    - Anything else → collapsible QTreeWidget
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        self._layout.addWidget(self._stack)

        # --- Table view (for array-of-dicts) ---
        self._table_container = QWidget()
        tbl_layout = QVBoxLayout(self._table_container)
        tbl_layout.setContentsMargins(0, 0, 0, 0)

        tbl_btn_row = QHBoxLayout()
        self._tbl_fit_btn = QPushButton("Fit Rows")
        self._tbl_fit_btn.setFixedWidth(80)
        tbl_btn_row.addWidget(self._tbl_fit_btn)
        tbl_btn_row.addStretch()
        tbl_layout.addLayout(tbl_btn_row)

        self._json_table = QTableView()
        self._json_table.setWordWrap(True)
        self._json_table.setAlternatingRowColors(True)
        self._json_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._json_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._json_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._json_table.horizontalHeader().setStretchLastSection(False)
        self._json_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._json_table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._json_table.verticalHeader().setDefaultSectionSize(60)

        self._tbl_fit_btn.clicked.connect(self._json_table.resizeRowsToContents)
        tbl_layout.addWidget(self._json_table)
        self._stack.addWidget(self._table_container)  # index 0

        # --- Tree view (for nested JSON) ---
        self._json_tree = QTreeWidget()
        self._json_tree.setHeaderLabels(["Key", "Value"])
        self._json_tree.header().setSectionResizeMode(QHeaderView.Interactive)
        self._json_tree.header().setStretchLastSection(True)
        self._stack.addWidget(self._json_tree)  # index 1

    def load_data(self, data: Any) -> None:
        """Display the already-parsed JSON *data*."""
        if isinstance(data, list) and data and isinstance(data[0], dict):
            self._load_as_table(data)
        else:
            self._load_as_tree(data)

    def _load_as_table(self, rows: List[dict]) -> None:
        all_keys: List[str] = []
        seen: set = set()
        for row in rows:
            for k in row.keys():
                if k not in seen:
                    seen.add(k)
                    all_keys.append(k)

        model = QStandardItemModel(len(rows), len(all_keys))
        model.setHorizontalHeaderLabels(all_keys)
        for r, row in enumerate(rows):
            for c, key in enumerate(all_keys):
                cell_val = row.get(key, "")
                item = QStandardItem(
                    json.dumps(cell_val, ensure_ascii=False)
                    if isinstance(cell_val, (dict, list))
                    else str(cell_val)
                )
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setTextAlignment(Qt.AlignTop | Qt.AlignLeft)
                model.setItem(r, c, item)

        self._json_table.setModel(model)
        self._stack.setCurrentIndex(0)

    def _load_as_tree(self, data: Any) -> None:
        self._json_tree.clear()
        if isinstance(data, list):
            for i, item in enumerate(data):
                _populate_tree_item(self._json_tree.invisibleRootItem(), f"[{i}]", item)
        elif isinstance(data, dict):
            for k, v in data.items():
                _populate_tree_item(self._json_tree.invisibleRootItem(), str(k), v)
        else:
            QTreeWidgetItem(self._json_tree.invisibleRootItem(), ["value", str(data)])
        self._json_tree.expandAll()
        self._stack.setCurrentIndex(1)


# ---------------------------------------------------------------------------
# Data pane (tabs for CSV + JSON)
# ---------------------------------------------------------------------------

_NO_DATA_HTML = """
<html><body style='background:#1e1e1e;color:#666;font-family:Segoe UI,sans-serif;'>
<p style='margin-top:40px;text-align:center;font-size:13px;'>
No data files found in this folder.<br>
<span style='font-size:11px;'>(Expected hunt-output/sigma.csv or search-output.json)</span>
</p></body></html>
"""


class DataPane(QWidget):
    """Right-side pane: CSV tab and/or JSON tab, or 'no data' message."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Page 0: no data label
        self._no_data_label = QTextBrowser()
        self._no_data_label.setHtml(_NO_DATA_HTML)
        self._no_data_label.setReadOnly(True)
        self._stack.addWidget(self._no_data_label)  # index 0

        # Page 1: tab widget that holds CSV and/or JSON tabs
        self._tabs = QTabWidget()
        self._stack.addWidget(self._tabs)  # index 1

        # Keep Fit Rows on the same line as tab labels (e.g., Hunt CSV).
        self._csv_fit_btn = QPushButton("Fit Rows")
        self._csv_fit_btn.setFixedWidth(80)
        self._csv_corner = QWidget()
        csv_corner_layout = QHBoxLayout(self._csv_corner)
        csv_corner_layout.setContentsMargins(0, 0, 20, 0)
        csv_corner_layout.addWidget(self._csv_fit_btn)
        self._tabs.setCornerWidget(self._csv_corner, Qt.TopRightCorner)

        # CSV tab
        self._csv_tab = QWidget()
        csv_layout = QVBoxLayout(self._csv_tab)
        csv_layout.setContentsMargins(0, 0, 0, 0)

        self._csv_view = QTableView()
        self._csv_model = CsvTableModel()
        self._csv_view.setModel(self._csv_model)
        self._csv_view.setWordWrap(True)
        self._csv_view.setAlternatingRowColors(True)
        self._csv_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._csv_view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self._csv_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._csv_view.horizontalHeader().setStretchLastSection(False)
        self._csv_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._csv_view.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._csv_view.verticalHeader().setDefaultSectionSize(60)
        self._csv_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._csv_view.customContextMenuRequested.connect(self._show_csv_context_menu)

        self._csv_fit_btn.clicked.connect(self._csv_view.resizeRowsToContents)
        csv_layout.addWidget(self._csv_view)

        # JSON tab
        self._json_widget = JsonViewWidget()

        # Show placeholder on startup
        self._stack.setCurrentIndex(0)

    def load_entry(self, entry: ResultEntry) -> None:
        self._tabs.clear()

        has_csv = entry.csv_path is not None
        has_json = entry.json_path is not None

        if not has_csv and not has_json:
            self._stack.setCurrentIndex(0)
            return

        if has_csv:
            self._csv_model.load_file(entry.csv_path)
            # Resize columns to a reasonable default
            self._csv_view.resizeColumnsToContents()
            # Match the exact behavior of clicking the "Fit Rows" button.
            self._csv_view.resizeRowsToContents()
            self._tabs.addTab(self._csv_tab, "Hunt CSV")

        if has_json:
            self._load_json(entry.json_path)
            self._tabs.addTab(self._json_widget, "Search JSON")

        self._stack.setCurrentIndex(1)

    def _load_json(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                raw = fh.read().strip()
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            # Treat non-JSON as plain text shown in tree
            data = {"parse_error": "File could not be decoded as JSON.", "raw": raw[:2000]}
        self._json_widget.load_data(data)

    def _show_csv_context_menu(self, pos) -> None:
        menu = QMenu(self)
        copy_action = menu.addAction("Copy Selected")
        chosen = menu.exec(self._csv_view.viewport().mapToGlobal(pos))
        if chosen == copy_action:
            self._copy_selected_csv_cells()

    def _copy_selected_csv_cells(self) -> None:
        indexes = self._csv_view.selectionModel().selectedIndexes()
        if not indexes:
            return

        row_map: dict[int, dict[int, str]] = {}
        min_col: int | None = None
        max_col: int | None = None

        for index in indexes:
            row = index.row()
            col = index.column()
            value = self._csv_model.data(index, Qt.DisplayRole)
            row_map.setdefault(row, {})[col] = "" if value is None else str(value)
            if min_col is None or col < min_col:
                min_col = col
            if max_col is None or col > max_col:
                max_col = col

        if min_col is None or max_col is None:
            return

        lines: List[str] = []
        for row in sorted(row_map.keys()):
            cols = row_map[row]
            line = "\t".join(cols.get(col, "") for col in range(min_col, max_col + 1))
            lines.append(line)

        QApplication.clipboard().setText("\n".join(lines))


# ---------------------------------------------------------------------------
# Results viewer window
# ---------------------------------------------------------------------------

class ResultsViewerWindow(QMainWindow):
    """
    Modeless window that lists chainsaw_results subfolders and displays
    the sigma report + raw data for the selected folder.
    """

    def __init__(
        self,
        output_root: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._output_root = output_root
        self._entries: List[ResultEntry] = []
        self._left_panel_width = 250

        self.setWindowTitle("Results Browser")
        self.resize(1700, 900)

        self._build_ui()
        self._apply_theme()
        self.refresh()

    def _build_theme_stylesheet(self) -> str:
        return f"""
QMainWindow, QWidget {{
    background-color: #F0E0E0;
    color: #3A2424;
    font-family: Segoe UI;
}}
QPushButton {{
    background-color: #C08080;
    color: #FFFFFF;
    border: 1px solid #B07070;
    border-radius: 6px;
    padding: 5px 10px;
}}
QPushButton:hover {{
    background-color: #B07070;
}}
QPushButton:pressed {{
    background-color: #9E6060;
}}
QLabel {{
    color: #3A2424;
}}
QTextBrowser, QListWidget, QTableView, QTreeWidget {{
    background-color: #F8E7EB;
    border: 1px solid #CFA8A8;
    border-radius: 6px;
    selection-background-color: #C08080;
    selection-color: #FFFFFF;
    color: #2F1E1E;
}}
QHeaderView::section {{
    background-color: #E6C6C6;
    color: #3A2424;
    border: 1px solid #CFA8A8;
    padding: 4px;
    font-weight: 600;
}}
QTabBar::tab {{
    background: #EED6D6;
    color: #5A2F2F;
    border: 1px solid #CFA8A8;
    padding: 6px 10px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: #C08080;
    color: #FFFFFF;
}}
"""

    def _apply_theme(self) -> None:
        self.setStyleSheet(self._build_theme_stylesheet())

    def _build_ui(self) -> None:
        container = QWidget()
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(6, 6, 6, 6)

        self._outer_splitter = QSplitter(Qt.Horizontal)

        # ---- Left panel: folder list ----
        left = QWidget()
        self._left_panel = left
        left.setMinimumWidth(self._left_panel_width)
        left.setMaximumWidth(self._left_panel_width)
        left.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("<b>Results Folders</b>"))
        header_row.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedWidth(70)
        header_row.addWidget(self._refresh_btn)
        left_layout.addLayout(header_row)

        self._folder_list = QListWidget()
        self._folder_list.setMinimumWidth(self._left_panel_width - 10)
        self._folder_list.setMaximumWidth(self._left_panel_width - 10)
        left_layout.addWidget(self._folder_list)

        self._outer_splitter.addWidget(left)

        # ---- Right panel: markdown + data splitter ----
        self._right_splitter = QSplitter(Qt.Horizontal)

        self._md_pane = MarkdownPane()
        self._data_pane = DataPane()
        self._md_pane.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self._data_pane.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._right_splitter.addWidget(self._md_pane)
        self._right_splitter.addWidget(self._data_pane)
        self._right_splitter.setCollapsible(0, False)
        self._right_splitter.setCollapsible(1, False)
        self._right_splitter.setStretchFactor(0, 1)
        self._right_splitter.setStretchFactor(1, 2)
        self._right_splitter.setSizes([500, 660])

        self._outer_splitter.addWidget(self._right_splitter)
        self._outer_splitter.setCollapsible(0, False)
        self._outer_splitter.setCollapsible(1, False)
        self._outer_splitter.setStretchFactor(0, 0)
        self._outer_splitter.setStretchFactor(1, 1)
        self._outer_splitter.setSizes([self._left_panel_width, 1150])

        root_layout.addWidget(self._outer_splitter)
        self.setCentralWidget(container)

        # Signals
        self._refresh_btn.clicked.connect(self.refresh)
        self._folder_list.currentItemChanged.connect(self._on_folder_changed)

    def refresh(self) -> None:
        """Re-scan output_root and repopulate the folder list."""
        current_name = None
        if self._folder_list.currentItem():
            current_name = self._folder_list.currentItem().text()

        self._entries = scan_results_folder(self._output_root)
        self._folder_list.blockSignals(True)
        self._folder_list.clear()
        for entry in self._entries:
            item = QListWidgetItem(entry.folder_name)
            item.setData(Qt.UserRole, entry)
            self._folder_list.addItem(item)
        self._folder_list.blockSignals(False)

        self._apply_dynamic_left_panel_width()

        # Try to re-select the previously selected folder
        if current_name:
            for i in range(self._folder_list.count()):
                if self._folder_list.item(i).text() == current_name:
                    self._folder_list.setCurrentRow(i)
                    return
        # Otherwise select first item if any
        if self._folder_list.count() > 0:
            self._folder_list.setCurrentRow(0)

    def focus_result(self, folder_path: Optional[str] = None, folder_name: Optional[str] = None) -> bool:
        """Refresh and select a specific result folder by full path or folder name."""
        target_name = folder_name
        if target_name is None and folder_path:
            target_name = os.path.basename(os.path.normpath(folder_path))

        self.refresh()
        if not target_name:
            return False

        for index in range(self._folder_list.count()):
            item = self._folder_list.item(index)
            if item.text() == target_name:
                self._folder_list.setCurrentRow(index)
                self.raise_()
                self.activateWindow()
                return True

        return False

    def _apply_dynamic_left_panel_width(self) -> None:
        """Size the folder panel to the longest folder name once per refresh."""
        font_metrics = self._folder_list.fontMetrics()
        longest = 0
        for entry in self._entries:
            longest = max(longest, font_metrics.horizontalAdvance(entry.folder_name))

        # Include list frame, scrollbar allowance, and breathing room.
        list_width = max(220, min(520, longest + 40))
        panel_width = list_width + 10

        self._left_panel_width = panel_width
        self._folder_list.setMinimumWidth(list_width)
        self._folder_list.setMaximumWidth(list_width)
        self._left_panel.setMinimumWidth(panel_width)
        self._left_panel.setMaximumWidth(panel_width)
        self._outer_splitter.setSizes([panel_width, max(400, self.width() - panel_width)])

    def _on_folder_changed(
        self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]
    ) -> None:
        if current is None:
            return
        entry: ResultEntry = current.data(Qt.UserRole)
        if entry is None:
            return
        self._md_pane.load_file(entry.md_path)
        self._md_pane.setMinimumWidth(0)
        self._md_pane.setMaximumWidth(16777215)
        preferred = self._md_pane.preferred_content_width()
        self._md_pane.setMinimumWidth(preferred)
        available = max(500, self._right_splitter.size().width())
        md_width = min(max(preferred, int(available * 0.35)), int(available * 0.55))
        self._right_splitter.setSizes([md_width, max(320, available - md_width)])
        self._data_pane.load_entry(entry)
