#!/usr/bin/env python3
"""Builds the portable Windows .zip: the app, the embedded Python and a launcher. Runs on any system.

Usage: package_windows.py <output>. No installer or signature: whoever downloads it extracts the folder and opens Vulcan Celox.cmd.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from vulcan_celox import __version__  # noqa: E402

PYTHON = "3.12.10"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON}/python-{PYTHON}-embed-amd64.zip"
PYTHON_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
FORA = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "ui", "desktop_linux_gtk*")
LAUNCHER = 'start "" "%~dp0python\\pythonw.exe" -X utf8 -m vulcan_celox.desktop_windows\r\n'
README = """Vulcan Celox for Windows (test build)

1. Extract this folder wherever you like.
2. Open "Vulcan Celox.cmd".

Windows may warn about an unknown publisher, because the app is not signed: choose More info, then Run anyway.
It opens in its own Microsoft Edge or Chrome window. Python is included, so there is nothing to install.
Your data stays in %APPDATA%\\VulcanCelox. Windows 10 version 1809 or newer is required.

Not available on Windows: Lerd and Valet, so PHP sites run in local mode.
"""


def fetch_python(target: Path) -> None:
    with urllib.request.urlopen(PYTHON_URL, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != PYTHON_SHA256:
        raise SystemExit("o Python baixado não confere com a soma fixa")
    target.write_bytes(data)


def build(output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    name = f"Vulcan-Celox-{__version__}-windows"
    final = output / f"{name}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / name
        (stage / "python").mkdir(parents=True)
        embed = Path(tmp) / "embed.zip"
        fetch_python(embed)
        with zipfile.ZipFile(embed) as archive:
            archive.extractall(stage / "python")
        # the embedded Python ignores the environment: this file is what says where the app is
        pth = next((stage / "python").glob("python*._pth"))
        pth.write_text(pth.read_text(encoding="utf-8") + "\n..\\app\n", encoding="utf-8")
        shutil.copytree(ROOT / "vulcan_celox", stage / "app" / "vulcan_celox", ignore=FORA)
        (stage / "Vulcan Celox.cmd").write_bytes(("@echo off\r\n" + LAUNCHER).encode("ascii"))
        (stage / "README.txt").write_bytes(README.replace("\n", "\r\n").encode("utf-8"))
        with zipfile.ZipFile(final, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(stage.parent))
    return final


if __name__ == "__main__":
    print(build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "executaveis" / "windows"))
