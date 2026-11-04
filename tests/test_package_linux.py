import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


def ar_files(data):
    assert data[:8] == b"!<arch>\n"
    position, files = 8, {}
    while position < len(data):
        header = data[position:position + 60]
        size = int(header[48:58])
        name = header[:16].decode().strip().rstrip("/")
        files[name] = data[position + 60:position + 60 + size]
        position += 60 + size + size % 2
    return files


class LinuxPackageTest(unittest.TestCase):
    def test_installers_include_current_source_and_preserve_launchers(self):
        spec = importlib.util.spec_from_file_location("package_linux", ROOT / "scripts/package_linux.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            deb, portable, readme = module.package(ROOT, output)
            members = ar_files(deb.read_bytes())
            self.assertEqual(members["debian-binary"], b"2.0\n")
            with tarfile.open(fileobj=io.BytesIO(members["control.tar.gz"])) as control:
                text = control.extractfile("./control").read().decode()
                self.assertIn("Architecture: all", text)
                self.assertIn("Depends: python3 (>= 3.9)", text)
                self.assertNotIn("@VERSION@", text)
                self.assertNotIn("@SIZE@", text)
            with tarfile.open(fileobj=io.BytesIO(members["data.tar.gz"])) as data, tarfile.open(portable) as archive:
                names = archive.getnames()
                prefix = names[0] + "/"
                checked = 0
                for source in (ROOT / "vulcan_celox").rglob("*"):
                    relative = source.relative_to(ROOT / "vulcan_celox")
                    if not source.is_file() or "ui" in relative.parts or "__pycache__" in relative.parts or source.suffix == ".pyc":
                        continue
                    current = source.read_bytes()
                    self.assertEqual(data.extractfile("./opt/vulcan-celox/lib/vulcan_celox/" + relative.as_posix()).read(), current)
                    self.assertEqual(archive.extractfile(prefix + "lib/vulcan_celox/" + relative.as_posix()).read(), current)
                    checked += 1
                self.assertGreater(checked, 60)
                launcher = data.getmember("./usr/bin/vulcan-celox")
                self.assertTrue(launcher.issym())
                self.assertEqual(launcher.linkname, "/opt/vulcan-celox/bin/vulcan-celox")
                for name in ("vulcan-celox", "vulcan-celox-deps"):
                    self.assertEqual(data.getmember("./opt/vulcan-celox/bin/" + name).mode, 0o755)
                desktop = data.extractfile("./usr/share/applications/vulcan-celox.desktop").read()
                self.assertIn(b"/usr/bin/vulcan-celox", desktop)
                self.assertNotIn(b"@EXEC@", desktop)
                self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))
            for line in (output / "SHA256SUMS").read_text().splitlines():
                expected, name = line.split("  ", 1)
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected)
