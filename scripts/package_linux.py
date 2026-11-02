#!/usr/bin/env python3
"""Build Linux installers with Python 3.9+, without Swift or macOS tools."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parent.parent


def package(root, output):
    root, output = Path(root), Path(output)
    version_text = (root / "vulcan_terminal/__init__.py").read_text()
    match = re.search(r'__version__\s*=\s*[\"\x27]([^\"\x27]+)', version_text)
    if not match or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", match.group(1)):
        raise ValueError("Invalid application version")
    version = match.group(1)
    output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("make_deb", root / "scripts/make_deb.py")
    make_deb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(make_deb)
    with tempfile.TemporaryDirectory(prefix="vulcan-linux-") as temp:
        work = Path(temp)
        stage = work / ("vulcan-terminal-" + version)
        (stage / "bin").mkdir(parents=True)
        (stage / "lib").mkdir()
        (stage / "share/applications").mkdir(parents=True)
        for name in ("vulcan-terminal", "vulcan-terminal-deps"):
            shutil.copy2(root / "packaging/linux" / name, stage / "bin" / name)
            (stage / "bin" / name).chmod(0o755)
        shutil.copytree(root / "vulcan_terminal", stage / "lib/vulcan_terminal",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "ui"))
        shutil.copy2(root / "packaging/linux/vulcan-terminal.desktop",
                     stage / "share/applications/vulcan-terminal.desktop")
        icons = root / "packaging/linux/icons/hicolor"
        if not icons.is_dir() or not list(icons.rglob("vulcan-terminal.png")):
            raise ValueError("Linux product icons are missing")
        shutil.copytree(icons, stage / "share/icons/hicolor")
        for name in ("install.sh", "uninstall.sh"):
            shutil.copy2(root / "packaging/linux" / name, stage / name)
            (stage / name).chmod(0o755)
        shutil.copy2(root / "packaging/LEIA-ME.md", stage / "LEIA-ME.md")
        source_files = {}
        for path in sorted((stage / "lib/vulcan_terminal").rglob("*")):
            if path.is_file():
                source_files[str(path.relative_to(stage / "lib"))] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = {"application": "Vulcan Terminal", "version": version, "files": source_files}
        (stage / "SOURCE-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
        portable = output / (stage.name + "-linux.tar.gz")
        with tarfile.open(portable, "w:gz", format=tarfile.GNU_FORMAT) as archive:
            archive.add(stage, arcname=stage.name)
        debroot = work / "deb"
        (debroot / "opt/vulcan-terminal").mkdir(parents=True)
        for name in ("bin", "lib"):
            shutil.copytree(stage / name, debroot / "opt/vulcan-terminal" / name)
        shutil.copy2(stage / "SOURCE-MANIFEST.json", debroot / "opt/vulcan-terminal/SOURCE-MANIFEST.json")
        (debroot / "usr/bin").mkdir(parents=True)
        (debroot / "usr/bin/vulcan-terminal").symlink_to("/opt/vulcan-terminal/bin/vulcan-terminal")
        (debroot / "usr/share/applications").mkdir(parents=True)
        desktop = (root / "packaging/linux/vulcan-terminal.desktop").read_text().replace("@EXEC@", "/usr/bin/vulcan-terminal")
        (debroot / "usr/share/applications/vulcan-terminal.desktop").write_text(desktop)
        shutil.copytree(stage / "share/icons", debroot / "usr/share/icons")
        control = work / "control"
        control.write_text((root / "packaging/linux/deb/control").read_text().replace("@VERSION@", version))
        deb = output / ("vulcan-terminal_" + version + "_all.deb")
        make_deb.main(str(debroot), str(control), str(root / "packaging/linux/deb/postinst"), str(deb))
        shutil.copy2(root / "packaging/LEIA-ME.md", output / "LEIA-ME.md")
        paths = [deb, portable, output / "LEIA-ME.md"]
        (output / "SHA256SUMS").write_text("".join(
            hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n" for path in paths))
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "executaveis/linux")
    args = parser.parse_args()
    for artifact in package(ROOT, args.output):
        print(artifact)
