"""Builds a sample project for the Code screen sensors, with every state the screen has to explain.

Usage: explorer_fixture.py <folder> [git]

With `git`, the folder becomes a repository with one commit and then a changed, a new and a deleted file, plus a change
inside src/: the Git marks of the tree."""

import os
import subprocess
import sys
from pathlib import Path

base = Path(sys.argv[1]).resolve()
(base / "src" / "core").mkdir(parents=True, exist_ok=True)
(base / "node_modules" / "pkg").mkdir(parents=True, exist_ok=True)
(base / "vazia").mkdir(exist_ok=True)
(base / "src" / "core" / "Checkout.php").write_text("<?php\n\nclass Checkout\n{\n    public function store()\n    {\n        return 1;\n    }\n}\n", encoding="utf-8")
for i in range(1, 6):
    (base / "src" / f"mod{i}.js").write_text(f"export const v{i} = {i};\n", encoding="utf-8")
(base / "README.md").write_text("# Projeto\n\nTexto do projeto.\n", encoding="utf-8")
(base / ".env").write_text("SEGREDO=1\n", encoding="utf-8")
(base / "node_modules" / "pkg" / "index.js").write_text("x\n", encoding="utf-8")
(base / "grande.txt").write_bytes(b"a" * (1024 * 1024 + 10))
(base / "binario.bin").write_bytes(b"a\x00b")
(base / "<img src=x onerror=window.__xss=1>.php").write_text("<script>window.__xss=2</script>\n", encoding="utf-8")
(base / "longo.txt").write_text("\n".join(f"linha {i}" for i in range(1, 401)) + "\n", encoding="utf-8")
outside = base.parent / "fora-do-projeto.txt"
outside.write_text("fora\n", encoding="utf-8")
if not (base / "link-fora").is_symlink():
    os.symlink(outside, base / "link-fora")
if sys.argv[2:] == ["git"]:
    def git(*args):
        subprocess.run(["git", "-C", str(base), "-c", "user.email=t@example.com", "-c", "user.name=t", *args], check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    (base / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-qm", "inicio")
    (base / "README.md").write_text("# Projeto\n\nTexto do projeto, mudado depois do commit.\n", encoding="utf-8")
    (base / "src" / "mod1.js").write_text("export const v1 = 100;\n", encoding="utf-8")
    (base / "novo.txt").write_text("novo\n", encoding="utf-8")
    (base / "longo.txt").unlink()
print(base)
