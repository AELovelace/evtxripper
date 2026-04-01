#!/usr/bin/env python3
"""PySide6 GUI frontend for EVTX Ripper / Chainsaw workflows."""

import os
import shutil
import sys
from typing import List, Tuple

from PySide6.QtCore import QEvent, Qt, QThread, QObject, Signal as pyqtSignal, QTimer, QElapsedTimer
from PySide6.QtGui import QBrush, QFont, QFontMetrics, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QProgressBar,
)

from evtx_core import (
    ChainsawConfig,
    ChainsawRunner,
    _resolve_manifest_path,
    build_results_folder_name,
    extract_error_summary,
    generate_sigma_reports,
    load_app_env,
    resolve_runtime_path,
)
from results_viewer import ResultsViewerWindow


load_app_env()


class HuntWorker(QObject):
    """Worker thread for running hunt operations asynchronously."""
    started = pyqtSignal()
    progress = pyqtSignal(str)  # Log message
    finished = pyqtSignal(bool, str, int, str)  # (success, output, report_count, report_err)
    
    def __init__(self, runner, cmd, run_dir, selected_files, ollama_config):
        super().__init__()
        self.runner = runner
        self.cmd = cmd
        self.run_dir = run_dir
        self.selected_files = selected_files
        self.ollama_config = ollama_config
    
    def run(self):
        """Execute the hunt process."""
        self.started.emit()
        self.progress.emit(f"Running hunt in: {self.run_dir}")
        
        ok, output = self.runner.run_command(self.cmd, output_callback=self.progress.emit)
        if not ok:
            summary = extract_error_summary(output)
            self.progress.emit(f"Hunt failed: {summary}")
            self.finished.emit(False, summary, 0, "")
            return
        
        self.progress.emit("Hunt complete, generating reports...")
        
        report_count, report_err = generate_sigma_reports(
            self.run_dir,
            self.selected_files,
            ollama_enabled=self.ollama_config['enabled'],
            endpoint=self.ollama_config['endpoint'],
            model=self.ollama_config['model'],
            timeout=self.ollama_config['timeout'],
        )
        
        if report_count > 0:
            msg = f"Hunt complete. Reports generated: {report_count}"
            self.progress.emit(msg)
            self.finished.emit(True, msg, report_count, report_err or "")
        elif report_err:
            msg = f"Hunt complete. Report warning: {report_err}"
            self.progress.emit(msg)
            self.finished.emit(True, msg, 0, report_err)
        else:
            msg = "Hunt complete."
            self.progress.emit(msg)
            self.finished.emit(True, msg, 0, "")


class SearchWorker(QObject):
    """Worker thread for running search operations asynchronously."""
    started = pyqtSignal()
    progress = pyqtSignal(str)  # Log message
    finished = pyqtSignal(bool, str)  # (success, message)
    
    def __init__(self, runner, cmd, run_dir):
        super().__init__()
        self.runner = runner
        self.cmd = cmd
        self.run_dir = run_dir
    
    def run(self):
        """Execute the search process."""
        self.started.emit()
        self.progress.emit(f"Running search in: {self.run_dir}")
        
        ok, output = self.runner.run_command(self.cmd, output_callback=self.progress.emit)
        if not ok:
            summary = extract_error_summary(output)
            self.progress.emit(f"Search failed: {summary}")
            self.finished.emit(False, summary)
            return
        
        msg = "Search complete."
        self.progress.emit(msg)
        self.finished.emit(True, msg)


class ProgressDialog(QDialog):
    """Non-closable modal dialog showing operation progress."""

    def __init__(self, title: str, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint,
        )
        console_font = ChainsawGui._console_font()
        minimum_log_width = ChainsawGui._console_minimum_width(console_font)

        self.setWindowTitle(title)
        self.setMinimumWidth(minimum_log_width + 32)
        self.setMinimumHeight(300)

        layout = QVBoxLayout(self)

        self.status_label = QLabel("Starting...")
        self.status_label.setFont(console_font)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(0)  # indeterminate
        layout.addWidget(self.progress_bar)

        self.elapsed_label = QLabel("Elapsed: 0s")
        self.elapsed_label.setFont(console_font)
        layout.addWidget(self.elapsed_label)

        self.log = QTextEdit()
        self.log.setObjectName("progressLog")
        self.log.setReadOnly(True)
        self.log.setFont(console_font)
        self.log.document().setDefaultFont(console_font)
        self.log.setMinimumWidth(minimum_log_width)
        self.log.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.log)

    def append_log(self, text: str):
        self.log.append(text)
        self.log.ensureCursorVisible()

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_elapsed(self, text: str):
        self.elapsed_label.setText(text)


class ChainsawGui(QMainWindow):
    @staticmethod
    def _console_font() -> QFont:
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        font.setFixedPitch(True)
        return font

    @staticmethod
    def _console_minimum_width(font: QFont, columns: int = 100) -> int:
        metrics = QFontMetrics(font)
        return metrics.horizontalAdvance("M" * columns) + 24

    def __init__(self):
        super().__init__()
        self.setWindowTitle("EVTX Ripper - Chainsaw GUI")
        self.resize(1200, 760)

        self.selected_files: List[str] = []
        self.provenance_manifest_map: dict[str, str] = {}

        self.runner = ChainsawRunner(self._load_chainsaw_config())
        self.output_root = resolve_runtime_path(os.getenv('OUTPUT_PATH', './chainsaw_results'))
        self.bg_image_path = resolve_runtime_path('./bg.jpg', must_exist=True)
        self._bg_pixmap = QPixmap(self.bg_image_path)
        self._bg_targets: list[QWidget] = []
        self._results_viewer: ResultsViewerWindow | None = None
        self._progress_dialog: ProgressDialog | None = None
        self._console_font_instance = self._console_font()
        self._console_log_minimum_width = self._console_minimum_width(self._console_font_instance)

        # Worker threads and timers for async operations
        self.hunt_worker = None
        self.hunt_thread = None
        self.search_worker = None
        self.search_thread = None
        self.elapsed_timer = QElapsedTimer()
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_elapsed_time)
        self.hunt_running = False
        self.search_running = False

        self._build_ui()
        self._apply_theme()
        self._configure_text_backgrounds()
        self._load_env_defaults()

    def _build_theme_stylesheet(self) -> str:
        return f"""
QMainWindow, QWidget {{
    background-color: #F0E0E0;
    color: #3A2424;
    font-family: Segoe UI;
}}
QGroupBox {{
    border: 1px solid #C08080;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    background: rgba(255, 255, 255, 0.66);
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: #6C3D3D;
    font-weight: 600;
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
QCheckBox, QLabel {{
    color: #3A2424;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid #C08080;
    border-radius: 3px;
    background-color: rgba(255, 255, 255, 0.85);
}}
QCheckBox::indicator:hover {{
    border-color: #B07070;
    background-color: rgba(255, 255, 255, 0.95);
}}
QCheckBox::indicator:checked {{
    border-color: #9E6060;
    background-color: #C08080;
}}
QCheckBox::indicator:checked:hover {{
    border-color: #8E5050;
    background-color: #B07070;
}}
QLineEdit, QTextEdit, QTextBrowser, QListWidget, QTableView, QTreeWidget {{
    background-color: rgba(255, 255, 255, 0.80);
    border: 1px solid #CFA8A8;
    border-radius: 6px;
    selection-background-color: #C08080;
    selection-color: #FFFFFF;
    color: #2F1E1E;
}}
#executionLog, #progressLog {{
    font-family: Consolas, "Courier New", monospace;
    font-size: 10pt;
}}
QHeaderView::section {{
    background-color: #E6C6C6;
    color: #3A2424;
    border: 1px solid #CFA8A8;
    padding: 4px;
    font-weight: 600;
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: rgba(255, 255, 255, 0.4);
    border: 1px solid #D7B3B3;
}}
"""

    def _apply_theme(self):
        self.setStyleSheet(self._build_theme_stylesheet())

    def _background_target(self, widget: QWidget) -> QWidget:
        return widget.viewport() if hasattr(widget, 'viewport') else widget

    def _configure_text_backgrounds(self):
        widgets: List[QWidget] = [
            self.log,
            self.search_pattern,
            self.search_regex,
            self.search_tau,
            self.ollama_endpoint,
            self.ollama_model,
            self.ollama_timeout,
        ]
        self._bg_targets = [self._background_target(w) for w in widgets]
        for target in self._bg_targets:
            target.installEventFilter(self)
            self._apply_cover_background(target)

        # Keep EVTX input list on a solid palette color for readability.
        self.files_list.setStyleSheet(
            "QListWidget {"
            " background-image: none;"
            " background-color: #F8E7EB;"
            " border: 1px solid #CFA8A8;"
            " border-radius: 6px;"
            " }"
        )

    def _apply_cover_background(self, target: QWidget):
        if self._bg_pixmap.isNull():
            return
        size = target.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        cover = self._bg_pixmap.scaled(
            size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        palette = target.palette()
        brush = QBrush(cover)
        palette.setBrush(QPalette.Window, brush)
        palette.setBrush(QPalette.Base, brush)
        target.setAutoFillBackground(True)
        target.setPalette(palette)

    def eventFilter(self, watched, event):
        if watched in self._bg_targets and event.type() in (QEvent.Resize, QEvent.Show):
            self._apply_cover_background(watched)
        return super().eventFilter(watched, event)

    def _load_chainsaw_config(self) -> ChainsawConfig:
        return ChainsawConfig(
            executable=resolve_runtime_path(os.getenv('CHAINSAW_EXECUTABLE', './chainsaw/chainsaw.exe'), must_exist=True),
            sigma_path=resolve_runtime_path(os.getenv('CHAINSAW_SIGMA_PATH', './sigma/rules'), must_exist=True),
            rules_path=resolve_runtime_path(os.getenv('CHAINSAW_RULES_PATH', './chainsaw/rules')),
            mapping_file=resolve_runtime_path(os.getenv('CHAINSAW_MAPPING_FILE', './chainsaw/mappings/sigma-event-logs-all.yml'), must_exist=True),
            output_format=os.getenv('CHAINSAW_OUTPUT_FORMAT', 'csv'),
            timezone=os.getenv('CHAINSAW_TIMEZONE', 'UTC'),
            column_width=int(os.getenv('CHAINSAW_COLUMN_WIDTH', '50')),
            skip_errors=os.getenv('CHAINSAW_SKIP_ERRORS', 'false').lower() == 'true',
            load_unknown=os.getenv('CHAINSAW_LOAD_UNKNOWN', 'false').lower() == 'true',
        )

    def _build_ui(self):
        container = QWidget()
        root_layout = QVBoxLayout(container)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)

        files_box = QGroupBox("EVTX Input Files")
        files_layout = QVBoxLayout(files_box)
        self.files_list = QListWidget()
        files_layout.addWidget(self.files_list)

        files_btns = QHBoxLayout()
        self.add_files_btn = QPushButton("Add EVTX Files")
        self.remove_file_btn = QPushButton("Remove Selected")
        self.clear_files_btn = QPushButton("Clear")
        files_btns.addWidget(self.add_files_btn)
        files_btns.addWidget(self.remove_file_btn)
        files_btns.addWidget(self.clear_files_btn)
        files_layout.addLayout(files_btns)
        left_layout.addWidget(files_box)

        hunt_box = QGroupBox("Hunt Options")
        hunt_form = QFormLayout(hunt_box)
        self.hunt_use_sigma = QCheckBox()
        self.hunt_use_rules = QCheckBox()
        self.hunt_full_output = QCheckBox()
        self.hunt_metadata = QCheckBox()
        self.hunt_format = QComboBox()
        self.hunt_format.addItems(["csv", "json", "log"])
        hunt_form.addRow("Use Sigma Rules", self.hunt_use_sigma)
        hunt_form.addRow("Use Custom Rules", self.hunt_use_rules)
        hunt_form.addRow("Output Format", self.hunt_format)
        hunt_form.addRow("Full Output", self.hunt_full_output)
        hunt_form.addRow("Include Metadata", self.hunt_metadata)
        left_layout.addWidget(hunt_box)

        search_box = QGroupBox("Search Options")
        search_form = QFormLayout(search_box)
        self.search_pattern = QLineEdit()
        self.search_regex = QLineEdit()
        self.search_tau = QLineEdit()
        self.search_ignore_case = QCheckBox()
        self.search_format = QComboBox()
        self.search_format.addItems(["json", "text"])
        search_form.addRow("Pattern", self.search_pattern)
        search_form.addRow("Regex (comma-separated)", self.search_regex)
        search_form.addRow("TAU (comma-separated)", self.search_tau)
        search_form.addRow("Ignore Case", self.search_ignore_case)
        search_form.addRow("Output Format", self.search_format)
        left_layout.addWidget(search_box)

        ollama_box = QGroupBox("Ollama Report Options")
        ollama_form = QFormLayout(ollama_box)
        self.ollama_enabled = QCheckBox()
        self.ollama_endpoint = QLineEdit()
        self.ollama_model = QLineEdit()
        self.ollama_timeout = QLineEdit()
        ollama_form.addRow("Enabled", self.ollama_enabled)
        ollama_form.addRow("Endpoint", self.ollama_endpoint)
        ollama_form.addRow("Model", self.ollama_model)
        ollama_form.addRow("Timeout (seconds)", self.ollama_timeout)
        left_layout.addWidget(ollama_box)

        action_row = QHBoxLayout()
        self.run_hunt_btn = QPushButton("Run Hunt")
        self.run_search_btn = QPushButton("Run Search")
        self.browse_results_btn = QPushButton("Browse Results")
        action_row.addWidget(self.run_hunt_btn)
        action_row.addWidget(self.run_search_btn)
        action_row.addWidget(self.browse_results_btn)
        left_layout.addLayout(action_row)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Execution Log"))
        self.log = QTextEdit()
        self.log.setObjectName("executionLog")
        self.log.setReadOnly(True)
        self.log.setFont(self._console_font_instance)
        self.log.document().setDefaultFont(self._console_font_instance)
        self.log.setMinimumWidth(self._console_log_minimum_width)
        self.log.setLineWrapMode(QTextEdit.NoWrap)
        right_layout.addWidget(self.log)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([650, 550])

        root_layout.addWidget(splitter)
        self.setCentralWidget(container)

        self.add_files_btn.clicked.connect(self._add_files)
        self.remove_file_btn.clicked.connect(self._remove_selected_file)
        self.clear_files_btn.clicked.connect(self._clear_files)
        self.run_hunt_btn.clicked.connect(self._run_hunt)
        self.run_search_btn.clicked.connect(self._run_search)
        self.browse_results_btn.clicked.connect(self._open_results_browser)

    def _load_env_defaults(self):
        self.hunt_use_sigma.setChecked(True)
        self.hunt_use_rules.setChecked(True)
        self.hunt_full_output.setChecked(False)
        self.hunt_metadata.setChecked(False)

        self.hunt_format.setCurrentText(os.getenv('CHAINSAW_OUTPUT_FORMAT', 'csv').lower())
        self.search_format.setCurrentText('json')

        self.ollama_enabled.setChecked(os.getenv('OLLAMA_ENABLED', 'true').lower() == 'true')
        self.ollama_endpoint.setText(os.getenv('OLLAMA_ENDPOINT', 'http://100.66.64.45:11434'))
        self.ollama_model.setText(os.getenv('OLLAMA_MODEL', 'qwen3.5:4b-q8_0'))
        self.ollama_timeout.setText(os.getenv('OLLAMA_TIMEOUT', '300'))

    def _open_results_browser(self):
        if self._results_viewer is None or not self._results_viewer.isVisible():
            self._results_viewer = ResultsViewerWindow(self.output_root, parent=self)
            self._results_viewer.show()
        else:
            self._results_viewer.raise_()
            self._results_viewer.activateWindow()

    def _show_result_in_browser(self, run_dir: str) -> None:
        self._open_results_browser()
        if self._results_viewer is None:
            return

        if not self._results_viewer.focus_result(folder_path=run_dir):
            self._append_log(f"Result folder not found in browser: {run_dir}")

    def _refresh_results_viewer(self):
        if self._results_viewer is not None and self._results_viewer.isVisible():
            self._results_viewer.refresh()

    def _append_log(self, text: str):
        self.log.append(text)
        self.log.ensureCursorVisible()

    def _update_elapsed_time(self):
        """Update the elapsed time display."""
        if self.elapsed_timer.isValid() and self._progress_dialog is not None:
            elapsed_ms = self.elapsed_timer.elapsed()
            seconds = elapsed_ms // 1000
            minutes = seconds // 60
            hours = minutes // 60

            if hours > 0:
                time_str = f"Elapsed: {hours}h {minutes % 60}m {seconds % 60}s"
            elif minutes > 0:
                time_str = f"Elapsed: {minutes}m {seconds % 60}s"
            else:
                time_str = f"Elapsed: {seconds}s"

            self._progress_dialog.set_elapsed(time_str)

    def _cleanup_hunt_worker(self):
        """Clean up hunt worker thread."""
        if self.hunt_thread is not None:
            self.hunt_thread.quit()
            self.hunt_thread.wait()
            self.hunt_thread = None
        self.hunt_worker = None

    def _cleanup_search_worker(self):
        """Clean up search worker thread."""
        if self.search_thread is not None:
            self.search_thread.quit()
            self.search_thread.wait()
            self.search_thread = None
        self.search_worker = None

    def _on_hunt_started(self):
        """Called when hunt process starts."""
        self.hunt_running = True
        self.run_hunt_btn.setEnabled(False)
        self.run_search_btn.setEnabled(False)
        self._progress_dialog = ProgressDialog("Hunt in Progress", parent=self)
        self._progress_dialog.show()
        self.elapsed_timer.start()
        self.update_timer.start(500)  # Update every 500ms

    def _on_hunt_progress(self, message: str):
        """Called when hunt emits a progress message."""
        self._append_log(message)
        if self._progress_dialog is not None:
            self._progress_dialog.append_log(message)
            self._progress_dialog.set_status(message)

    def _on_hunt_finished(self, success: bool, message: str, report_count: int, report_err: str):
        """Called when hunt process completes."""
        self.hunt_running = False
        self.update_timer.stop()
        run_dir = self.hunt_worker.run_dir if self.hunt_worker else "results"
        self._cleanup_hunt_worker()
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None
        self.run_hunt_btn.setEnabled(True)
        self.run_search_btn.setEnabled(True)

        if success:
            self._refresh_results_viewer()
            self._show_result_in_browser(run_dir)
            if report_err:
                self._append_log(f"Report warning: {report_err}")
                QMessageBox.warning(self, "Report warning", report_err)
        else:
            QMessageBox.critical(self, "Hunt failed", message)

    def _on_search_started(self):
        """Called when search process starts."""
        self.search_running = True
        self.run_hunt_btn.setEnabled(False)
        self.run_search_btn.setEnabled(False)
        self._progress_dialog = ProgressDialog("Search in Progress", parent=self)
        self._progress_dialog.show()
        self.elapsed_timer.start()
        self.update_timer.start(500)  # Update every 500ms

    def _on_search_progress(self, message: str):
        """Called when search emits a progress message."""
        self._append_log(message)
        if self._progress_dialog is not None:
            self._progress_dialog.append_log(message)
            self._progress_dialog.set_status(message)

    def _on_search_finished(self, success: bool, message: str):
        """Called when search process completes."""
        self.search_running = False
        self.update_timer.stop()
        run_dir = self.search_worker.run_dir if self.search_worker else "results"
        self._cleanup_search_worker()
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None
        self.run_hunt_btn.setEnabled(True)
        self.run_search_btn.setEnabled(True)

        if success:
            self._refresh_results_viewer()
            self._show_result_in_browser(run_dir)
        else:
            QMessageBox.critical(self, "Search failed", message)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select EVTX files", "", "EVTX Files (*.evtx);;All Files (*.*)")
        loaded_now = 0
        manifests_attached_now = 0
        for file_path in files:
            if file_path not in self.selected_files:
                self.selected_files.append(file_path)
                self.files_list.addItem(QListWidgetItem(file_path))
                loaded_now += 1

            if self._load_provenance_for_file(file_path):
                manifests_attached_now += 1

        if loaded_now > 0:
            self._append_log(
                f"Loaded {loaded_now} file(s). Manifests attached: {manifests_attached_now}. "
                f"Total selected files: {len(self.selected_files)}"
            )

    def _load_provenance_for_file(self, evtx_path: str) -> bool:
        """Resolve and cache manifest for an EVTX file at add-time."""
        manifest_path = _resolve_manifest_path(evtx_path)
        if not manifest_path:
            self._append_log(f"Provenance: missing for {os.path.basename(evtx_path)}")
            return False

        canonical_manifest_path = f"{evtx_path}.manifest.json"
        if os.path.normcase(os.path.abspath(manifest_path)) != os.path.normcase(os.path.abspath(canonical_manifest_path)):
            try:
                shutil.copy2(manifest_path, canonical_manifest_path)
                manifest_path = canonical_manifest_path
            except Exception as exc:
                self._append_log(
                    f"Provenance: found but failed to cache for {os.path.basename(evtx_path)} ({exc})"
                )
                return False

        self.provenance_manifest_map[evtx_path] = manifest_path
        self._append_log(f"Provenance: attached for {os.path.basename(evtx_path)}")
        return True

    def _remove_selected_file(self):
        row = self.files_list.currentRow()
        if row < 0:
            return
        removed = self.selected_files.pop(row)
        self.files_list.takeItem(row)
        self._append_log(f"Removed: {removed}")

    def _clear_files(self):
        self.selected_files.clear()
        self.files_list.clear()
        self._append_log("Cleared selected files")

    def _create_run_dir(self) -> str:
        run_dir = os.path.join(self.output_root, build_results_folder_name(self.selected_files))
        os.makedirs(run_dir, exist_ok=True)
        return run_dir

    def _split_csv_list(self, value: str) -> List[str]:
        return [v.strip() for v in value.split(',') if v.strip()]

    def _generate_reports(self, run_dir: str) -> Tuple[int, str]:
        model = self.ollama_model.text().strip() or 'qwen3.5:4b-q8_0'
        endpoint = self.ollama_endpoint.text().strip().rstrip('/')
        timeout = int((self.ollama_timeout.text().strip() or '120'))

        return generate_sigma_reports(
            run_dir,
            self.selected_files,
            ollama_enabled=self.ollama_enabled.isChecked(),
            endpoint=endpoint,
            model=model,
            timeout=timeout,
        )

    def _run_hunt(self):
        if not self.selected_files:
            QMessageBox.warning(self, "No files", "Add EVTX files first.")
            return

        if self.hunt_running or self.search_running:
            QMessageBox.warning(self, "Operation in progress", "Another operation is already running.")
            return

        run_dir = self._create_run_dir()
        output_target = os.path.join(run_dir, 'hunt-output')

        cmd = self.runner.build_hunt_command(
            self.selected_files,
            output_file=output_target,
            output_format=self.hunt_format.currentText(),
            use_sigma=self.hunt_use_sigma.isChecked(),
            use_rules=self.hunt_use_rules.isChecked(),
            full_output=self.hunt_full_output.isChecked(),
            metadata=self.hunt_metadata.isChecked(),
            log_format=self.hunt_format.currentText().lower() == 'log',
        )

        # Prepare ollama config
        ollama_config = {
            'enabled': self.ollama_enabled.isChecked(),
            'endpoint': self.ollama_endpoint.text().strip().rstrip('/'),
            'model': self.ollama_model.text().strip() or 'qwen3.5:4b-q8_0',
            'timeout': int((self.ollama_timeout.text().strip() or '120')),
        }

        # Create worker and thread
        self._cleanup_hunt_worker()
        self.hunt_worker = HuntWorker(self.runner, cmd, run_dir, self.selected_files, ollama_config)
        self.hunt_thread = QThread()
        self.hunt_worker.moveToThread(self.hunt_thread)

        # Connect signals
        self.hunt_thread.started.connect(self.hunt_worker.run)
        self.hunt_worker.started.connect(self._on_hunt_started)
        self.hunt_worker.progress.connect(self._on_hunt_progress)
        self.hunt_worker.finished.connect(self._on_hunt_finished)

        # Start the thread
        self.hunt_thread.start()

    def _run_search(self):
        if not self.selected_files:
            QMessageBox.warning(self, "No files", "Add EVTX files first.")
            return

        if self.hunt_running or self.search_running:
            QMessageBox.warning(self, "Operation in progress", "Another operation is already running.")
            return

        pattern = self.search_pattern.text().strip()
        regex = self._split_csv_list(self.search_regex.text())
        tau = self._split_csv_list(self.search_tau.text())

        if not pattern and not regex and not tau:
            QMessageBox.warning(self, "Missing query", "Provide a pattern, regex, or TAU expression.")
            return

        run_dir = self._create_run_dir()
        ext = 'json' if self.search_format.currentText().lower() == 'json' else 'txt'
        output_file = os.path.join(run_dir, f"search-output.{ext}")

        cmd = self.runner.build_search_command(
            self.selected_files,
            pattern=pattern,
            output_file=output_file,
            output_format=self.search_format.currentText().lower(),
            regex_patterns=regex,
            tau_expressions=tau,
            ignore_case=self.search_ignore_case.isChecked(),
            json_output=self.search_format.currentText().lower() == 'json',
        )

        # Create worker and thread
        self._cleanup_search_worker()
        self.search_worker = SearchWorker(self.runner, cmd, run_dir)
        self.search_thread = QThread()
        self.search_worker.moveToThread(self.search_thread)

        # Connect signals
        self.search_thread.started.connect(self.search_worker.run)
        self.search_worker.started.connect(self._on_search_started)
        self.search_worker.progress.connect(self._on_search_progress)
        self.search_worker.finished.connect(self._on_search_finished)

        # Start the thread
        self.search_thread.start()


def main():
    app = QApplication(sys.argv)
    win = ChainsawGui()
    win.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
