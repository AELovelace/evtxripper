#!/usr/bin/env python3
"""PySide6 GUI frontend for EVTX Ripper / Chainsaw workflows."""

import os
import sys
from typing import List, Tuple

from dotenv import load_dotenv
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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
)

from evtx_core import (
    ChainsawConfig,
    ChainsawRunner,
    build_results_folder_name,
    extract_error_summary,
    generate_sigma_reports,
)


load_dotenv('.env')
class ChainsawGui(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EVTX Ripper - Chainsaw GUI")
        self.resize(1200, 760)

        self.selected_files: List[str] = []

        self.runner = ChainsawRunner(self._load_chainsaw_config())
        self.output_root = os.getenv('OUTPUT_PATH', './chainsaw_results')

        self._build_ui()
        self._load_env_defaults()

    def _load_chainsaw_config(self) -> ChainsawConfig:
        return ChainsawConfig(
            executable=os.getenv('CHAINSAW_EXECUTABLE', './chainsaw/chainsaw.exe'),
            sigma_path=os.getenv('CHAINSAW_SIGMA_PATH', './sigma/rules'),
            rules_path=os.getenv('CHAINSAW_RULES_PATH', './chainsaw/rules'),
            mapping_file=os.getenv('CHAINSAW_MAPPING_FILE', './chainsaw/mappings/sigma-event-logs-all.yml'),
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
        action_row.addWidget(self.run_hunt_btn)
        action_row.addWidget(self.run_search_btn)
        left_layout.addLayout(action_row)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Execution Log"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
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
        self.ollama_timeout.setText(os.getenv('OLLAMA_TIMEOUT', '120'))

    def _append_log(self, text: str):
        self.log.append(text)
        self.log.ensureCursorVisible()

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select EVTX files", "", "EVTX Files (*.evtx);;All Files (*.*)")
        for file_path in files:
            if file_path not in self.selected_files:
                self.selected_files.append(file_path)
                self.files_list.addItem(QListWidgetItem(file_path))
        self._append_log(f"Loaded files: {len(self.selected_files)}")

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

        self._append_log(f"Running hunt in: {run_dir}")
        ok, output = self.runner.run_command(cmd)
        if not ok:
            summary = extract_error_summary(output)
            self._append_log(f"Hunt failed: {summary}")
            QMessageBox.critical(self, "Hunt failed", summary)
            return

        report_count, report_err = self._generate_reports(run_dir)
        if report_count > 0:
            self._append_log(f"Hunt complete. Reports generated: {report_count}")
        elif report_err:
            self._append_log(f"Hunt complete. Report warning: {report_err}")
        else:
            self._append_log("Hunt complete.")

        QMessageBox.information(self, "Hunt complete", f"Run folder:\n{run_dir}")

    def _run_search(self):
        if not self.selected_files:
            QMessageBox.warning(self, "No files", "Add EVTX files first.")
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

        self._append_log(f"Running search in: {run_dir}")
        ok, output = self.runner.run_command(cmd)
        if not ok:
            summary = extract_error_summary(output)
            self._append_log(f"Search failed: {summary}")
            QMessageBox.critical(self, "Search failed", summary)
            return

        self._append_log("Search complete.")
        QMessageBox.information(self, "Search complete", f"Run folder:\n{run_dir}")


def main():
    app = QApplication(sys.argv)
    win = ChainsawGui()
    win.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
