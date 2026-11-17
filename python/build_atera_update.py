"""Rebuild ps/Atera-ChainsawUpdate.ps1 after chainsaw.ps1 or sigma-update.ps1 changes.

The Atera script carries both scripts inline as base64 plus their SHA256, so Atera
can push them without any download. This re-embeds the current files from the repo.

Usage (from the repo root):  python python/build_atera_update.py
"""
import base64
import hashlib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent          # repo root (this file lives in python/)
ATERA = REPO / "ps" / "Atera-ChainsawUpdate.ps1"         # the script Atera runs

# Each embedded script: (source file in the repo, destination path variable used in Atera script)
EMBEDDED = [
    (REPO / "ps" / "chainsaw.ps1", '"$bin\\chainsaw.ps1"'),          # 5-minute hunt (active response)
    (REPO / "ps" / "sigma-update.ps1", '"$base\\sigma-update.ps1"'),  # daily Sigma rule pull
]


def main() -> None:
    text = ATERA.read_text(encoding="utf-8")                     # current Atera script
    for src, dest in EMBEDDED:
        data = src.read_bytes()                                  # exact bytes (keeps CRLF line endings)
        b64 = base64.b64encode(data).decode("ascii")             # what Put() decodes on the PC
        sha = hashlib.sha256(data).hexdigest().upper()           # what Put() checks with Get-FileHash
        # Replace the whole "Put '<b64>' <dest> '<sha>'" line for this destination
        pattern = re.compile(r"^Put '[A-Za-z0-9+/=]*' " + re.escape(dest) + r" '[0-9A-F]{64}'$", re.M)
        new_line = f"Put '{b64}' {dest} '{sha}'"
        text, n = pattern.subn(lambda _m: new_line, text)
        if n != 1:                                               # refuse to write a half-updated script
            raise SystemExit(f"expected one Put line for {dest}, found {n}")
        print(f"{src.name}: SHA256 {sha}")                      # record this in the runbook / commit message
    ATERA.write_text(text, encoding="utf-8", newline="")         # newline="" keeps the file's own line endings


if __name__ == "__main__":
    main()
