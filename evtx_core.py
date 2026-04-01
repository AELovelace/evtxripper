#!/usr/bin/env python3
"""Shared core services for EVTX Ripper frontends (TUI + GUI)."""

import os
import re
import subprocess
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import requests
from dotenv import load_dotenv


def get_launch_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_bundle_dir() -> str:
    return getattr(sys, '_MEIPASS', get_launch_dir())


def load_app_env() -> Optional[str]:
    candidates = [
        os.path.join(get_launch_dir(), '.env'),
        os.path.join(os.getcwd(), '.env'),
    ]

    seen = set()
    for candidate in candidates:
        normalized = os.path.normcase(os.path.abspath(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        if os.path.isfile(candidate):
            load_dotenv(candidate)
            return candidate

    return None


def resolve_runtime_path(path_value: str, must_exist: bool = False) -> str:
    expanded = os.path.expandvars(os.path.expanduser(path_value or ''))
    if not expanded:
        return expanded

    if os.path.isabs(expanded):
        return expanded

    candidates = [
        os.path.join(get_launch_dir(), expanded),
        os.path.join(get_bundle_dir(), expanded),
        os.path.join(os.getcwd(), expanded),
    ]

    if must_exist:
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate

    return candidates[0]


@dataclass
class ChainsawConfig:
    """Chainsaw configuration."""

    executable: str
    sigma_path: str
    rules_path: str
    mapping_file: str
    output_format: str
    timezone: str
    column_width: int
    skip_errors: bool
    load_unknown: bool


class ChainsawRunner:
    """Handles Chainsaw command construction and execution."""

    def __init__(self, config: ChainsawConfig):
        self.config = config

    def build_hunt_command(
        self,
        evtx_paths: List[str],
        output_file: Optional[str] = None,
        output_format: Optional[str] = None,
        use_sigma: bool = True,
        use_rules: bool = True,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        full_output: bool = False,
        metadata: bool = False,
        log_format: bool = False,
    ) -> List[str]:
        cmd = [self.config.executable, "hunt"]
        selected_output_format = (output_format or self.config.output_format).lower()

        if use_sigma:
            cmd.extend(["-s", self.config.sigma_path])
            cmd.extend(["-m", self.config.mapping_file])

        if use_rules and os.path.isdir(self.config.rules_path):
            cmd.extend(["-r", self.config.rules_path])

        if selected_output_format == "csv":
            cmd.append("--csv")
        elif selected_output_format == "json":
            cmd.append("--json")
        elif selected_output_format == "log":
            cmd.append("--log")

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

        cmd.extend(["--timezone", self.config.timezone])
        cmd.extend(["--column-width", str(self.config.column_width)])

        cmd.extend(evtx_paths)
        return cmd

    def build_search_command(
        self,
        evtx_paths: List[str],
        pattern: str = "",
        output_file: Optional[str] = None,
        output_format: str = "json",
        regex_patterns: Optional[List[str]] = None,
        tau_expressions: Optional[List[str]] = None,
        ignore_case: bool = False,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        json_output: bool = False,
    ) -> List[str]:
        cmd = [self.config.executable, "search"]
        use_json = json_output or output_format.lower() == "json"

        if use_json:
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
            for value in regex_patterns:
                cmd.extend(["-e", value])

        if tau_expressions:
            for value in tau_expressions:
                cmd.extend(["-t", value])

        cmd.extend(["--timezone", self.config.timezone])

        if pattern and not regex_patterns and not tau_expressions:
            cmd.append(pattern)

        cmd.extend(evtx_paths)
        return cmd

    def run_command(
        self,
        cmd: List[str],
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str]:
        try:
            sanitized_cmd = [str(part) for part in cmd if part is not None]
            process = subprocess.Popen(
                sanitized_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            output_lines: List[str] = []

            try:
                if process.stdout is not None:
                    for line in iter(process.stdout.readline, ""):
                        if line == "":
                            break

                        cleaned_line = line.rstrip("\r\n")
                        output_lines.append(line)
                        if output_callback is not None and cleaned_line:
                            output_callback(cleaned_line)

                result_code = process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                return False, "Chainsaw execution timeout"
            finally:
                if process.stdout is not None:
                    process.stdout.close()

            output = "".join(output_lines)

            if not output.strip():
                output = f"Command exited with code {result_code} and produced no decodable output."

            return result_code == 0, output
        except Exception as exc:
            return False, f"Error running chainsaw: {exc}"


def sanitize_for_filename(value: str, fallback: str = "result") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", (value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or fallback


def build_results_folder_name(source_files: List[str]) -> str:
    short_dt = datetime.now().strftime('%y%m%d-%H%M')
    if len(source_files) == 1:
        base = Path(source_files[0]).stem
        key = sanitize_for_filename(base)[:15]
    else:
        key = f"multi-{len(source_files)}files"
    return f"{key}-results-{short_dt}"


def create_run_results_dir(source_files: List[str], output_root: str) -> str:
    run_dir = os.path.join(output_root, build_results_folder_name(source_files))
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def has_sigma_rules(sigma_path: str) -> bool:
    if not sigma_path or not os.path.isdir(sigma_path):
        return False

    for _, _, files in os.walk(sigma_path):
        for filename in files:
            lower = filename.lower()
            if lower.endswith((".yml", ".yaml")) and not lower.startswith("sigma-event-logs-"):
                return True

    return False


def extract_error_summary(output: str) -> str:
    cleaned = re.sub(r"\x1b\[[0-9;]*m", "", output or "")
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return "No error details were returned."

    priority_markers = ["no valid detection rules", "error", "failed", "cannot", "invalid", "not found"]
    for line in lines:
        lower = line.lower()
        if any(marker in lower for marker in priority_markers):
            return line

    return lines[-1]


def find_sigma_csv(run_dir: str) -> Optional[str]:
    preferred = os.path.join(run_dir, 'sigma.csv')
    if os.path.isfile(preferred):
        return preferred

    for root, _, files in os.walk(run_dir):
        for name in files:
            if name.lower() == 'sigma.csv':
                return os.path.join(root, name)

    for root, _, files in os.walk(run_dir):
        for name in files:
            if name.lower().endswith('.csv'):
                return os.path.join(root, name)

    return None


def generate_sigma_reports(
    run_dir: str,
    source_evtx_files: List[str],
    ollama_enabled: Optional[bool] = None,
    endpoint: Optional[str] = None,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> Tuple[int, str]:
    enabled = ollama_enabled if ollama_enabled is not None else (os.getenv('OLLAMA_ENABLED', 'true').lower() == 'true')
    if not enabled:
        return 0, "Ollama reporting is disabled"

    sigma_csv = find_sigma_csv(run_dir)
    if not sigma_csv:
        report_count = 0
        for evtx_path in source_evtx_files:
            evtx_name = Path(evtx_path).name
            safe_name = sanitize_for_filename(Path(evtx_path).stem, 'evtx')
            report_name = f"sigma-report-{safe_name}.md"
            report_path = os.path.join(run_dir, report_name)

            with open(report_path, 'w', encoding='utf-8') as report_file:
                report_file.write(f"# Sigma Report for {evtx_name}\n\n")
                report_file.write(f"Generated: {datetime.now().isoformat()}\n\n")
                report_file.write("## Summary\n")
                report_file.write("No Sigma CSV detections were produced for this hunt run.\n\n")
                report_file.write("## Notes\n")
                report_file.write("- Chainsaw completed successfully.\n")
                report_file.write("- Output folder did not contain a CSV detection file (for example `sigma.csv`).\n")
                report_file.write("- This typically indicates no matching detections for the selected EVTX and ruleset.\n")

            report_count += 1

        return report_count, ""

    endpoint_value = (endpoint or os.getenv('OLLAMA_ENDPOINT', 'http://100.66.64.45:11434')).rstrip('/')
    model_value = model or os.getenv('OLLAMA_MODEL', 'qwen3.5:4b-q8_0')
    timeout_value = timeout if timeout is not None else int(os.getenv('OLLAMA_TIMEOUT', '300'))
    try:
        num_ctx_value = int(os.getenv('OLLAMA_NUM_CTX', '128000'))
    except ValueError:
        num_ctx_value = 128000
    max_chars_value = max_chars if max_chars is not None else int(os.getenv('OLLAMA_MAX_CSV_CHARS', '25000'))
    language_value = os.getenv('OLLAMA_REPORT_LANGUAGE', 'English').strip() or 'English'

    with open(sigma_csv, 'r', encoding='utf-8', errors='replace') as handle:
        csv_content = handle.read()
    csv_excerpt = csv_content[:max_chars_value]

    report_count = 0
    errors: List[str] = []

    for evtx_path in source_evtx_files:
        evtx_name = Path(evtx_path).name
        safe_name = sanitize_for_filename(Path(evtx_path).stem, 'evtx')
        report_name = f"sigma-report-{safe_name}.md"
        report_path = os.path.join(run_dir, report_name)
        manifest_path = _resolve_manifest_path(evtx_path)
        provenance_rows = _load_provenance_rows(manifest_path)
        provenance_markdown = _format_provenance_markdown(provenance_rows)
        provenance_prompt = _format_provenance_prompt(provenance_rows)
        benign_paths_prompt = _format_known_benign_paths_prompt()

        prompt = (
            f"Respond in {language_value} only. Do not use any other language.\n"
            "Use concise markdown with clear section headers.\n\n"
            "You are a SOC analyst. Analyze the following Chainsaw hunt CSV results and provide:\n"
            "1) Top 5 notable findings\n"
            "2) Likely attack techniques (MITRE ATT&CK IDs if inferable)\n"
            "3) False-positive candidates\n"
            "4) Immediate triage actions\n"
            "5) A short executive summary\n\n"
            f"Source EVTX: {evtx_name}\n\n"
            "Use the provenance manifest mapping as authoritative for channel/file origin.\n"
            "Do not infer source paths that are not present in the manifest.\n\n"
            f"Known benign export-path context:\n{benign_paths_prompt}\n\n"
            f"Provenance manifest data:\n{provenance_prompt}\n\n"
            f"CSV:\n{csv_excerpt}"
        )

        payload = {
            'model': model_value,
            'prompt': prompt,
            'stream': False,
            'options': {
                'num_ctx': num_ctx_value
            }
        }

        try:
            response = requests.post(f"{endpoint_value}/api/generate", json=payload, timeout=timeout_value)
            response.raise_for_status()
            model_response = response.json().get('response', '').strip() or 'Model returned an empty response.'

            with open(report_path, 'w', encoding='utf-8') as report_file:
                report_file.write(f"# Sigma Report for {evtx_name}\n\n")
                report_file.write(f"Generated: {datetime.now().isoformat()}\n\n")
                report_file.write(f"Source CSV: {sigma_csv}\n\n")
                report_file.write(model_response)
                report_file.write("\n\n## Analysis Context & Assumptions\n")
                report_file.write("The following export-chain paths are treated as expected infrastructure ")
                report_file.write("context and are **not** flagged as malicious by themselves:\n\n")
                report_file.write(benign_paths_prompt)
                report_file.write("\n\n## Deterministic Provenance Manifest\n")
                report_file.write(provenance_markdown)

            report_count += 1
        except Exception as exc:
            with open(report_path, 'w', encoding='utf-8') as report_file:
                report_file.write(f"# Sigma Report for {evtx_name}\n\n")
                report_file.write(f"Generated: {datetime.now().isoformat()}\n\n")
                report_file.write(f"Source CSV: {sigma_csv}\n\n")
                report_file.write("## Report Generation Warning\n")
                report_file.write("Automated Ollama analysis did not complete successfully for this run.\n\n")
                report_file.write(f"- Error: {exc}\n")
                report_file.write(f"- Endpoint: {endpoint_value}\n")
                report_file.write(f"- Model: {model_value}\n\n")
                report_file.write("## Deterministic Provenance Manifest\n")
                report_file.write(provenance_markdown)

            errors.append(f"{evtx_name}: {exc}")
            report_count += 1

    if errors:
        return report_count, "; ".join(errors)

    return report_count, ""


def _resolve_manifest_path(evtx_path: str) -> Optional[str]:
    candidates = [
        f"{evtx_path}.manifest.json",
        f"{os.path.splitext(evtx_path)[0]}.manifest.json",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    evtx_dir = os.path.dirname(evtx_path) or '.'
    evtx_name = os.path.basename(evtx_path)
    evtx_stem = os.path.splitext(evtx_name)[0]
    expected_name_norm = _normalize_manifest_match_key(evtx_name)
    expected_stem_norm = _normalize_manifest_match_key(evtx_stem)

    try:
        with os.scandir(evtx_dir) as entries:
            for entry in entries:
                if not entry.is_file():
                    continue
                filename = entry.name
                if not filename.lower().endswith('.manifest.json'):
                    continue

                exported_name = filename[:-len('.manifest.json')]
                exported_stem = os.path.splitext(exported_name)[0]
                exported_name_norm = _normalize_manifest_match_key(exported_name)
                exported_stem_norm = _normalize_manifest_match_key(exported_stem)

                if (
                    exported_name_norm == expected_name_norm
                    or exported_stem_norm == expected_stem_norm
                ):
                    return entry.path
    except OSError:
        return None

    return None


def _load_provenance_rows(manifest_path: Optional[str]) -> List[Tuple[str, str]]:
    if not manifest_path:
        return []

    try:
        with open(manifest_path, 'rb') as handle:
            raw_payload = handle.read()

        payload = None
        for encoding in ('utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be', 'utf-8'):
            try:
                payload = json.loads(raw_payload.decode(encoding))
                break
            except Exception:
                continue

        if payload is None:
            return []
    except Exception:
        return []

    rows: List[Tuple[str, str]] = []
    channels = _dict_get_case_insensitive(payload, ['Channels', 'channels']) if isinstance(payload, dict) else None
    if not isinstance(channels, list):
        return []

    for item in channels:
        if not isinstance(item, dict):
            continue
        channel = str(_dict_get_case_insensitive(item, ['Channel', 'channel', 'LogName', 'log_name', 'Name', 'name']) or '').strip()
        original_path = str(_dict_get_case_insensitive(item, ['OriginalPath', 'original_path', 'LogFilePath', 'log_file_path', 'FilePath', 'file_path', 'Path', 'path']) or '').strip()
        if channel:
            rows.append((channel, original_path or '(unknown)'))

    return rows


def _format_provenance_prompt(rows: List[Tuple[str, str]]) -> str:
    if not rows:
        return 'No manifest available.'

    lines = [f"- {channel} => {path}" for channel, path in rows]
    return "\n".join(lines)


def _format_known_benign_paths_prompt() -> str:
    """Provide path-context guardrails to reduce false positives in AI summaries."""
    configured_remote_dir = (os.getenv('REMOTE_DIRECTORY', 'logdump') or 'logdump').strip()
    names = {'logdump', configured_remote_dir}
    normalized = sorted({name for name in names if name})

    lines = [
        '- Treat export staging locations as expected infrastructure context unless accompanied by independent malicious behavior.',
        '- Do not classify path location alone as malicious, suspicious, or attacker-controlled.',
        '- Specifically treat references to paths containing these folder names as expected export-chain artifacts:'
    ]
    lines.extend([f'  - {name}' for name in normalized])

    return "\n".join(lines)


def _format_provenance_markdown(rows: List[Tuple[str, str]]) -> str:
    if not rows:
        return "No provenance manifest was available for this EVTX file.\n"

    output = ["| Channel | Original Path |", "|---|---|"]
    for channel, path in rows:
        safe_channel = channel.replace('|', '\\|')
        safe_path = path.replace('|', '\\|')
        output.append(f"| {safe_channel} | {safe_path} |")

    return "\n".join(output) + "\n"


def _normalize_manifest_match_key(value: str) -> str:
    """Normalize names for resilient EVTX/manifest basename matching."""
    return re.sub(r'[^a-z0-9]', '', (value or '').lower())


def _dict_get_case_insensitive(payload: dict, keys: List[str]):
    """Return the first matching key from payload, case-insensitively."""
    if not isinstance(payload, dict):
        return None

    keymap = {str(k).lower(): v for k, v in payload.items()}
    for key in keys:
        value = keymap.get(key.lower())
        if value is not None:
            return value
    return None
