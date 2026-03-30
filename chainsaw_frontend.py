#!/usr/bin/env python3
"""
Chainsaw Frontend - Interactive ncurses UI for EVTX analysis
Provides a menu-driven interface for browsing and analyzing Windows Event Logs using Chainsaw
"""

import os
import sys
import subprocess
import json
import csv
import ntpath
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import smb.SMBConnection
import logging
from dotenv import load_dotenv
from enum import Enum

try:
    import curses
except ModuleNotFoundError:
    curses = None

# Load environment variables from .env
load_dotenv('.env')

# Configure logging
logging.basicConfig(
    level=logging.getLevelName(os.getenv('LOG_LEVEL', 'INFO')),
    filename=os.getenv('LOG_FILE', './evtxripper.log'),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OperationMode(Enum):
    """Operation modes for Chainsaw"""
    HUNT = "hunt"
    SEARCH = "search"


@dataclass
class ChainsawConfig:
    """Chainsaw configuration"""
    executable: str
    sigma_path: str
    rules_path: str
    mapping_file: str
    output_format: str
    timezone: str
    column_width: int
    skip_errors: bool
    load_unknown: bool


@dataclass
class SMBConfig:
    """SMB Connection configuration"""
    host: str
    port: int
    share_name: str
    username: str
    password: str
    domain: str


class SMBBrowser:
    """Handles SMB share browsing and file operations"""

    def __init__(self, config: SMBConfig):
        self.config = config
        self.connection = None
        self.share_name, self.base_path = self._split_share_and_base_path(config.share_name)

    @staticmethod
    def _split_share_and_base_path(share_value: str) -> Tuple[str, str]:
        """Split SMB value into share name and optional base path.

        Accepts either:
        - Share
        - Share\\Subfolder\\Nested
        """
        normalized = (share_value or "").strip().strip("\\/")
        if not normalized:
            return "", "/"

        parts = [p for p in normalized.replace("/", "\\").split("\\") if p]
        share_name = parts[0]
        if len(parts) == 1:
            return share_name, "/"

        return share_name, "/" + "/".join(parts[1:])

    def _join_remote_path(self, path: str) -> str:
        """Join requested path to configured base path for SMB operations."""
        cleaned = (path or "/").replace("\\", "/")
        if not cleaned.startswith("/"):
            cleaned = "/" + cleaned

        if self.base_path == "/":
            return cleaned

        if cleaned == "/":
            return self.base_path

        return self.base_path.rstrip("/") + cleaned

    def connect(self) -> bool:
        """Establish SMB connection"""
        try:
            self.connection = smb.SMBConnection.SMBConnection(
                self.config.username,
                self.config.password,
                'client',
                self.config.host,
                domain=self.config.domain,
                use_ntlm_v2=True
            )
            self.connection.connect(self.config.host, self.config.port, timeout=10)
            logger.info(f"Connected to SMB share: {self.config.host}")
            return True
        except Exception as e:
            logger.error(f"SMB Connection failed: {str(e)}")
            return False

    def disconnect(self):
        """Close SMB connection"""
        if self.connection:
            try:
                self.connection.close()
                logger.info("SMB connection closed")
            except Exception as e:
                logger.error(f"Error closing SMB connection: {str(e)}")

    def list_files(self, path: str = '/') -> List[Dict]:
        """List EVTX files in SMB share"""
        try:
            files = []
            remote_path = self._join_remote_path(path)
            items = self.connection.listPath(self.share_name, remote_path)
            for item in items:
                if item.filename not in ['.', '..']:
                    file_info = {
                        'name': item.filename,
                        'path': f"{path}{item.filename}",
                        'is_dir': item.file_attributes & smb.base.SMB_FILE_ATTRIBUTE_DIRECTORY != 0,
                        'size': item.file_size,
                        'modified': item.last_write_time
                    }
                    if file_info['is_dir'] or item.filename.lower().endswith('.evtx'):
                        files.append(file_info)
            return sorted(files, key=lambda x: (not x['is_dir'], x['name']))
        except Exception as e:
            logger.error(f"Error listing SMB files: {str(e)}")
            return []

    def download_file(self, remote_path: str, local_path: str) -> bool:
        """Download file from SMB share"""
        try:
            os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
            full_remote_path = self._join_remote_path(remote_path)
            with open(local_path, 'wb') as f:
                self.connection.retrieveFile(self.share_name, full_remote_path, f)
            logger.info(f"Downloaded: {full_remote_path} to {local_path}")
            return True
        except Exception as e:
            logger.error(f"Error downloading file: {str(e)}")
            return False


class ChainsawRunner:
    """Handles Chainsaw execution"""

    def __init__(self, config: ChainsawConfig):
        self.config = config

    def build_hunt_command(
        self,
        evtx_paths: List[str],
        output_file: Optional[str] = None,
        use_sigma: bool = True,
        use_rules: bool = True,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        full_output: bool = False,
        metadata: bool = False,
        log_format: bool = False
    ) -> List[str]:
        """Build chainsaw hunt command"""
        cmd = [self.config.executable, "hunt"]

        if use_sigma:
            cmd.extend(["-s", self.config.sigma_path])
            cmd.extend(["-m", self.config.mapping_file])

        if use_rules and os.path.isdir(self.config.rules_path):
            cmd.extend(["-r", self.config.rules_path])

        if self.config.output_format == "csv":
            cmd.append("--csv")
        elif self.config.output_format == "json":
            cmd.append("--json")

        if output_file:
            cmd.extend(["-o", output_file])

        if from_date:
            cmd.extend(["--from", from_date])

        if to_date:
            cmd.extend(["--to", to_date])

        if full_output:
            cmd.append("--full")

        if metadata:
            cmd.append("--metadata")

        if log_format:
            cmd.append("--log")

        if self.config.skip_errors:
            cmd.append("--skip-errors")

        if self.config.load_unknown:
            cmd.append("--load-unknown")

        cmd.extend([f"--timezone", self.config.timezone])
        cmd.extend([f"--column-width", str(self.config.column_width)])

        cmd.extend(evtx_paths)

        return cmd

    def build_search_command(
        self,
        evtx_paths: List[str],
        pattern: str = "",
        output_file: Optional[str] = None,
        regex_patterns: Optional[List[str]] = None,
        tau_expressions: Optional[List[str]] = None,
        ignore_case: bool = False,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        json_output: bool = False
    ) -> List[str]:
        """Build chainsaw search command"""
        cmd = [self.config.executable, "search"]

        if json_output:
            cmd.append("--json")

        if output_file:
            cmd.extend(["-o", output_file])

        if ignore_case:
            cmd.append("-i")

        if from_date:
            cmd.extend(["--from", from_date])

        if to_date:
            cmd.extend(["--to", to_date])

        if regex_patterns:
            for pattern in regex_patterns:
                cmd.extend(["-e", pattern])

        if tau_expressions:
            for expr in tau_expressions:
                cmd.extend(["-t", expr])

        cmd.extend(["-timezone", self.config.timezone])

        if pattern and not regex_patterns and not tau_expressions:
            cmd.append(pattern)

        cmd.extend(evtx_paths)

        return cmd

    def run_command(self, cmd: List[str]) -> Tuple[bool, str]:
        """Execute chainsaw command"""
        try:
            sanitized_cmd = [str(part) for part in cmd if part is not None]
            logger.info(f"Running command: {' '.join(sanitized_cmd)}")
            result = subprocess.run(
                sanitized_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            output = (result.stdout or "") + (result.stderr or "")
            if result.returncode == 0:
                logger.info("Chainsaw execution successful")
                return True, output
            else:
                logger.error(f"Chainsaw execution failed: {output}")
                return False, output
        except subprocess.TimeoutExpired:
            error_msg = "Chainsaw execution timeout"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Error running chainsaw: {str(e)}"
            logger.error(error_msg)
            return False, error_msg


class ChainsawUI:
    """Ncurses UI for Chainsaw frontend"""

    def __init__(self):
        self.smb_config = self._load_smb_config()
        self.chainsaw_config = self._load_chainsaw_config()
        self.smb_browser = SMBBrowser(self.smb_config)
        self.chainsaw_runner = ChainsawRunner(self.chainsaw_config)
        self.selected_files: List[str] = []
        self.remote_selected_files = set()
        self.browser_files: List[Dict] = []
        self.browser_index = 0
        self.browser_path = '/'
        self.smb_connected = False
        self.current_menu = "main"
        self.main_menu_index = 0
        self.hunt_menu_index = 0
        self.search_menu_index = 0
        self.config_menu_index = 0
        self.message = ""
        self.message_type = "info"  # info, error, success

    def _refresh_browser_files(self):
        """Refresh browser file listing from SMB share."""
        self.browser_files = self.smb_browser.list_files(self.browser_path)
        if self.browser_files and self.browser_index >= len(self.browser_files):
            self.browser_index = len(self.browser_files) - 1
        if not self.browser_files:
            self.browser_index = 0

    def _enter_file_browser(self):
        """Connect to SMB and prepare browser state."""
        self.current_menu = "file_browser"

        if self.smb_connected:
            self._refresh_browser_files()
            return

        if not self.smb_browser.connect():
            self.message = "Failed to connect to SMB share"
            self.message_type = "error"
            return

        self.smb_connected = True
        self.browser_path = '/'
        self.browser_index = 0
        self._refresh_browser_files()

        if not self.browser_files:
            self.message = "Connected, but no files or directories found"
            self.message_type = "warning"
            return

        self.message = "Connected to SMB share"
        self.message_type = "success"

    def _leave_file_browser(self):
        """Disconnect SMB session when leaving file browser."""
        if self.smb_connected:
            self.smb_browser.disconnect()
            self.smb_connected = False

    def _download_selected_remote_files(self):
        """Download selected remote EVTX files to local folder and mark them ready for Chainsaw."""
        if not self.remote_selected_files:
            self.message = "No files selected in browser"
            self.message_type = "warning"
            return

        target_dir = os.path.join(os.getcwd(), "downloaded_evtx")
        os.makedirs(target_dir, exist_ok=True)

        downloaded_count = 0
        for remote_path in sorted(self.remote_selected_files):
            filename = ntpath.basename(remote_path.replace('/', '\\'))
            local_path = os.path.join(target_dir, filename)
            if self.smb_browser.download_file(remote_path, local_path):
                downloaded_count += 1
                if local_path not in self.selected_files:
                    self.selected_files.append(local_path)

        if downloaded_count:
            self.message = f"Downloaded {downloaded_count} file(s). Ready for hunt/search: {len(self.selected_files)}"
            self.message_type = "success"
        else:
            self.message = "Download failed for selected files"
            self.message_type = "error"

    def _download_remote_file(self, remote_path: str):
        """Download one remote file to local folder and add to Chainsaw input list."""
        target_dir = os.path.join(os.getcwd(), "downloaded_evtx")
        os.makedirs(target_dir, exist_ok=True)

        filename = ntpath.basename(remote_path.replace('/', '\\'))
        local_path = os.path.join(target_dir, filename)

        if self.smb_browser.download_file(remote_path, local_path):
            if local_path not in self.selected_files:
                self.selected_files.append(local_path)
            self.message = f"Downloaded: {filename}. Ready for hunt/search: {len(self.selected_files)}"
            self.message_type = "success"
        else:
            self.message = f"Download failed: {filename}"
            self.message_type = "error"

    def _activate_main_menu_item(self):
        """Activate highlighted item in the main menu."""
        if self.main_menu_index == 0:
            self._enter_file_browser()
        elif self.main_menu_index == 1:
            self.current_menu = "hunt_options"
        elif self.main_menu_index == 2:
            self.current_menu = "search_options"
        elif self.main_menu_index == 3:
            self.current_menu = "config"
        elif self.main_menu_index == 4:
            self._show_selected_files()
        elif self.main_menu_index == 5:
            raise SystemExit

    def _activate_hunt_menu_item(self):
        """Activate highlighted item in hunt menu."""
        if self.hunt_menu_index == 5:
            self._run_hunt()
        elif self.hunt_menu_index == 6:
            self.current_menu = "main"
        else:
            self.message = "This option is not implemented yet"
            self.message_type = "warning"

    def _activate_search_menu_item(self):
        """Activate highlighted item in search menu."""
        if self.search_menu_index == 5:
            self._run_search()
        elif self.search_menu_index == 6:
            self.current_menu = "main"
        else:
            self.message = "This option is not implemented yet"
            self.message_type = "warning"

    def _load_smb_config(self) -> SMBConfig:
        """Load SMB configuration from environment"""
        return SMBConfig(
            host=os.getenv('SMB_HOST', ''),
            port=int(os.getenv('SMB_PORT', '445')),
            share_name=os.getenv('SMB_SHARE_NAME', ''),
            username=os.getenv('SMB_USERNAME', ''),
            password=os.getenv('SMB_PASSWORD', ''),
            domain=os.getenv('SMB_DOMAIN', '')
        )

    def _load_chainsaw_config(self) -> ChainsawConfig:
        """Load Chainsaw configuration from environment"""
        return ChainsawConfig(
            executable=os.getenv('CHAINSAW_EXECUTABLE', 'chainsaw'),
            sigma_path=os.getenv('CHAINSAW_SIGMA_PATH', './chainsaw'),
            rules_path=os.getenv('CHAINSAW_RULES_PATH', './chainsaw/rules'),
            mapping_file=os.getenv('CHAINSAW_MAPPING_FILE', './chainsaw/mappings/sigma-event-logs-all.yml'),
            output_format=os.getenv('CHAINSAW_OUTPUT_FORMAT', 'csv'),
            timezone=os.getenv('CHAINSAW_TIMEZONE', 'UTC'),
            column_width=int(os.getenv('CHAINSAW_COLUMN_WIDTH', '50')),
            skip_errors=os.getenv('CHAINSAW_SKIP_ERRORS', 'false').lower() == 'true',
            load_unknown=os.getenv('CHAINSAW_LOAD_UNKNOWN', 'false').lower() == 'true'
        )

    def run(self, stdscr):
        """Main UI loop"""
        curses.curs_set(0)
        stdscr.nodelay(False)
        stdscr.keypad(True)

        # Color pairs
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)  # Header
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Success
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)    # Error
        curses.init_pair(4, curses.COLOR_YELLOW, curses.COLOR_BLACK) # Warning
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Normal
        curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Selected

        running = True
        while running:
            stdscr.clear()
            height, width = stdscr.getmaxyx()

            # Draw interface
            self._draw_header(stdscr, width)
            
            if self.current_menu == "main":
                self._draw_main_menu(stdscr, height, width)
            elif self.current_menu == "file_browser":
                self._draw_file_browser(stdscr, height, width)
            elif self.current_menu == "hunt_options":
                self._draw_hunt_options(stdscr, height, width)
            elif self.current_menu == "search_options":
                self._draw_search_options(stdscr, height, width)
            elif self.current_menu == "config":
                self._draw_config_menu(stdscr, height, width)

            self._draw_message(stdscr, height, width)

            stdscr.refresh()

            # Handle input
            key = stdscr.getch()
            if key == ord('q'):
                if self.current_menu == "main":
                    running = False
                else:
                    if self.current_menu == "file_browser":
                        self._leave_file_browser()
                    self.current_menu = "main"
                    self.message = ""
            elif key in (27, getattr(curses, "KEY_EXIT", -1)):
                if self.current_menu != "main":
                    if self.current_menu == "file_browser":
                        self._leave_file_browser()
                    self.current_menu = "main"
                    self.message = ""
            else:
                try:
                    self._handle_menu_input(key)
                except SystemExit:
                    running = False

    def _draw_header(self, stdscr, width):
        """Draw header"""
        header = " Chainsaw Forensic Event Log Analysis Frontend "
        padding = (width - len(header)) // 2
        stdscr.attron(curses.color_pair(1))
        stdscr.addstr(0, 0, " " * width)
        stdscr.addstr(0, padding, header)
        stdscr.attroff(curses.color_pair(1))

    def _draw_main_menu(self, stdscr, height, width):
        """Draw main menu"""
        menu_items = [
            "1. Browse SMB Share & Select EVTX Files",
            "2. Run Chainsaw Hunt",
            "3. Run Chainsaw Search",
            "4. Configure Settings",
            "5. View Selected Files",
            "0. Exit"
        ]

        start_row = 3
        for idx, item in enumerate(menu_items):
            if idx == self.main_menu_index:
                stdscr.attron(curses.color_pair(6))
                stdscr.addstr(start_row + idx, 2, item[:width - 4])
                stdscr.attroff(curses.color_pair(6))
            else:
                stdscr.addstr(start_row + idx, 2, item[:width - 4])

        info_text = "Selected files: " + str(len(self.selected_files))
        stdscr.addstr(height - 3, 2, info_text)
        stdscr.addstr(height - 1, 2, "Up/Down + Enter, or 1-5. q quits from main")

    def _draw_file_browser(self, stdscr, height, width):
        """Draw file browser"""
        stdscr.addstr(2, 2, "SMB File Browser")
        stdscr.addstr(3, 2, f"Share: {self.smb_config.host}\\{self.smb_config.share_name}")
        stdscr.addstr(4, 2, f"Path: {self.browser_path}")

        if not self.smb_connected:
            stdscr.addstr(6, 2, "Not connected. Press ESC to return.")
            return

        if not self.browser_files:
            stdscr.addstr(6, 2, "No files or directories in this path.")
            return

        start_row = 6
        visible_rows = max(1, height - 11)
        top_index = max(0, self.browser_index - visible_rows + 1)

        for idx, file_info in enumerate(self.browser_files[top_index:top_index + visible_rows]):
            real_index = top_index + idx
            prefix = "[DIR]" if file_info['is_dir'] else "[FILE]"
            marker = "[x]" if file_info['path'] in self.remote_selected_files else "[ ]"
            display = f"{marker} {prefix} {file_info['name']}"

            if real_index == self.browser_index:
                stdscr.attron(curses.color_pair(6))
                stdscr.addstr(start_row + idx, 4, display[:width - 8])
                stdscr.attroff(curses.color_pair(6))
            else:
                stdscr.addstr(start_row + idx, 4, display[:width - 8])

        stdscr.addstr(height - 3, 2, "Up/Down: move  Enter: open dir/select file  Backspace: up")
        stdscr.addstr(height - 2, 2, "Space: mark file  d: download highlighted  D: download marked  r: refresh")

    def _draw_hunt_options(self, stdscr, height, width):
        """Draw hunt options"""
        stdscr.addstr(2, 2, "Chainsaw Hunt Options")
        stdscr.addstr(3, 2, "=" * (width - 4))

        options = [
            "1. Use Sigma Rules (current: ON)",
            "2. Use Custom Rules (current: ON)",
            "3. Output Format (current: " + self.chainsaw_config.output_format.upper() + ")",
            "4. Full Output (current: OFF)",
            "5. Include Metadata (current: OFF)",
            "6. Run Hunt",
            "0. Back"
        ]

        start_row = 5
        for idx, option in enumerate(options):
            if idx == self.hunt_menu_index:
                stdscr.attron(curses.color_pair(6))
                stdscr.addstr(start_row + idx, 4, option[:width - 8])
                stdscr.attroff(curses.color_pair(6))
            else:
                stdscr.addstr(start_row + idx, 4, option[:width - 8])

        stdscr.addstr(height - 3, 2, "Up/Down + Enter supported. 6 runs hunt, 0 goes back")

    def _draw_search_options(self, stdscr, height, width):
        """Draw search options"""
        stdscr.addstr(2, 2, "Chainsaw Search Options")
        stdscr.addstr(3, 2, "=" * (width - 4))

        options = [
            "1. Enter Search Pattern",
            "2. Enter Regex Pattern",
            "3. Enter TAU Expression",
            "4. Ignore Case (current: OFF)",
            "5. Output Format (current: " + self.chainsaw_config.output_format.upper() + ")",
            "6. Run Search",
            "0. Back"
        ]

        start_row = 5
        for idx, option in enumerate(options):
            if idx == self.search_menu_index:
                stdscr.attron(curses.color_pair(6))
                stdscr.addstr(start_row + idx, 4, option[:width - 8])
                stdscr.attroff(curses.color_pair(6))
            else:
                stdscr.addstr(start_row + idx, 4, option[:width - 8])

        stdscr.addstr(height - 3, 2, "Up/Down + Enter supported. 6 runs search, 0 goes back")

    def _draw_config_menu(self, stdscr, height, width):
        """Draw configuration menu"""
        stdscr.addstr(2, 2, "Configuration Settings")
        stdscr.addstr(3, 2, "=" * (width - 4))

        config_info = [
            f"SMB Host: {self.smb_config.host}",
            f"SMB Share: {self.smb_config.share_name}",
            f"SMB Username: {self.smb_config.username}",
            f"Chainsaw Executable: {self.chainsaw_config.executable}",
            f"Output Format: {self.chainsaw_config.output_format}",
            f"Timezone: {self.chainsaw_config.timezone}",
        ]

        start_row = 5
        for idx, info in enumerate(config_info):
            stdscr.addstr(start_row + idx, 4, info)

        back_row = start_row + len(config_info) + 2
        back_text = "Back"
        if self.config_menu_index == 0:
            stdscr.attron(curses.color_pair(6))
            stdscr.addstr(back_row, 2, back_text)
            stdscr.attroff(curses.color_pair(6))
        else:
            stdscr.addstr(back_row, 2, back_text)

        stdscr.addstr(back_row + 1, 2, "Edit .env file to change settings")
        stdscr.addstr(back_row + 2, 2, "Enter or ESC returns")

    def _draw_message(self, stdscr, height, width):
        """Draw status message"""
        if self.message:
            color_pair = 2 if self.message_type == "success" else (3 if self.message_type == "error" else 4)
            stdscr.attron(curses.color_pair(color_pair))
            msg_display = self.message[:width - 4]
            stdscr.addstr(height - 2, 2, msg_display)
            stdscr.attroff(curses.color_pair(color_pair))

    def _handle_menu_input(self, key):
        """Handle menu input"""
        if self.current_menu == "main":
            key_up = {getattr(curses, "KEY_UP", 259), 259, ord('k')}
            key_down = {getattr(curses, "KEY_DOWN", 258), 258, ord('j')}
            key_enter = {10, 13, getattr(curses, "KEY_ENTER", 343)}

            if key in key_up and self.main_menu_index > 0:
                self.main_menu_index -= 1
            elif key in key_down and self.main_menu_index < 5:
                self.main_menu_index += 1
            elif key in key_enter:
                self._activate_main_menu_item()
            if key == ord('1'):
                self.main_menu_index = 0
                self._enter_file_browser()
            elif key == ord('2'):
                self.main_menu_index = 1
                self.current_menu = "hunt_options"
            elif key == ord('3'):
                self.main_menu_index = 2
                self.current_menu = "search_options"
            elif key == ord('4'):
                self.main_menu_index = 3
                self.current_menu = "config"
            elif key == ord('5'):
                self.main_menu_index = 4
                self._show_selected_files()
            elif key == ord('0'):
                self.main_menu_index = 5
                raise SystemExit
        elif self.current_menu == "file_browser":
            key_up = {getattr(curses, "KEY_UP", 259), 259, ord('k')}
            key_down = {getattr(curses, "KEY_DOWN", 258), 258, ord('j')}
            key_enter = {10, 13, getattr(curses, "KEY_ENTER", 343)}
            key_back = {8, 127, getattr(curses, "KEY_BACKSPACE", 263)}

            if key in key_up and self.browser_index > 0:
                self.browser_index -= 1
            elif key in key_down and self.browser_index < max(0, len(self.browser_files) - 1):
                self.browser_index += 1
            elif key in key_enter and self.browser_files:
                current = self.browser_files[self.browser_index]
                if current['is_dir']:
                    current_path = self.browser_path.rstrip('/')
                    self.browser_path = f"{current_path}/{current['name']}" if current_path else f"/{current['name']}"
                    self.browser_index = 0
                    self._refresh_browser_files()
                else:
                    self._download_remote_file(current['path'])
            elif key in key_back:
                if self.browser_path != '/':
                    parent = self.browser_path.rstrip('/').rsplit('/', 1)[0]
                    self.browser_path = parent if parent else '/'
                    self.browser_index = 0
                    self._refresh_browser_files()
            elif key == ord('r'):
                self._refresh_browser_files()
                self.message = "Refreshed SMB listing"
                self.message_type = "info"
            elif key == ord(' '):
                if self.browser_files:
                    current = self.browser_files[self.browser_index]
                    if current['is_dir']:
                        self.message = "Cannot select a directory; open it with Enter"
                        self.message_type = "warning"
                    else:
                        if current['path'] in self.remote_selected_files:
                            self.remote_selected_files.remove(current['path'])
                        else:
                            self.remote_selected_files.add(current['path'])
                        self.message = f"Selected in browser: {len(self.remote_selected_files)}"
                        self.message_type = "info"
            elif key == ord('d'):
                if self.browser_files:
                    current = self.browser_files[self.browser_index]
                    if current['is_dir']:
                        self.message = "Highlighted item is a directory"
                        self.message_type = "warning"
                    else:
                        self._download_remote_file(current['path'])
            elif key == ord('D'):
                self._download_selected_remote_files()
        elif self.current_menu == "hunt_options":
            key_up = {getattr(curses, "KEY_UP", 259), 259, ord('k')}
            key_down = {getattr(curses, "KEY_DOWN", 258), 258, ord('j')}
            key_enter = {10, 13, getattr(curses, "KEY_ENTER", 343)}

            if key in key_up and self.hunt_menu_index > 0:
                self.hunt_menu_index -= 1
            elif key in key_down and self.hunt_menu_index < 6:
                self.hunt_menu_index += 1
            elif key in key_enter:
                self._activate_hunt_menu_item()

            if key == ord('6'):
                self._run_hunt()
            elif key == ord('0'):
                self.current_menu = "main"
        elif self.current_menu == "search_options":
            key_up = {getattr(curses, "KEY_UP", 259), 259, ord('k')}
            key_down = {getattr(curses, "KEY_DOWN", 258), 258, ord('j')}
            key_enter = {10, 13, getattr(curses, "KEY_ENTER", 343)}

            if key in key_up and self.search_menu_index > 0:
                self.search_menu_index -= 1
            elif key in key_down and self.search_menu_index < 6:
                self.search_menu_index += 1
            elif key in key_enter:
                self._activate_search_menu_item()

            if key == ord('6'):
                self._run_search()
            elif key == ord('0'):
                self.current_menu = "main"
        elif self.current_menu == "config":
            key_enter = {10, 13, getattr(curses, "KEY_ENTER", 343)}
            if key in key_enter:
                self.current_menu = "main"

    def _run_hunt(self):
        """Run Chainsaw hunt"""
        if not self.selected_files:
            self.message = "Please select EVTX files first"
            self.message_type = "error"
            return

        self.message = "Running Chainsaw hunt..."
        self.message_type = "info"

        output_file = os.path.join(
            os.getenv('OUTPUT_PATH', './chainsaw_results'),
            f"hunt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

        cmd = self.chainsaw_runner.build_hunt_command(
            self.selected_files,
            output_file=output_file
        )

        success, output = self.chainsaw_runner.run_command(cmd)
        if success:
            self.message = f"Hunt completed. Results saved to: {output_file}"
            self.message_type = "success"
        else:
            self.message = f"Hunt failed: {output[:100]}"
            self.message_type = "error"

    def _run_search(self):
        """Run Chainsaw search"""
        if not self.selected_files:
            self.message = "Please select EVTX files first"
            self.message_type = "error"
            return

        self.message = "Running Chainsaw search..."
        self.message_type = "info"

        output_file = os.path.join(
            os.getenv('OUTPUT_PATH', './chainsaw_results'),
            f"search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        cmd = self.chainsaw_runner.build_search_command(
            self.selected_files,
            pattern="malicious|suspicious",
            output_file=output_file,
            json_output=True
        )

        success, output = self.chainsaw_runner.run_command(cmd)
        if success:
            self.message = f"Search completed. Results saved to: {output_file}"
            self.message_type = "success"
        else:
            self.message = f"Search failed: {output[:100]}"
            self.message_type = "error"

    def _show_selected_files(self):
        """Show selected files"""
        if self.selected_files:
            self.message = "Selected: " + ", ".join(self.selected_files)
        else:
            self.message = "No files selected"
        self.message_type = "info"


def main():
    """Main entry point"""
    try:
        if curses is None:
            print("Error: curses support is not available in this Python environment.")
            print("On Windows, install support with:")
            print("  python -m pip install windows-curses")
            sys.exit(1)

        ui = ChainsawUI()
        curses.wrapper(ui.run)
    except KeyboardInterrupt:
        print("\nApplication terminated by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {str(e)}")
        logger.error(f"Application error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
