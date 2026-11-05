"""Writes in the sample project while the Code screen sensor watches, as any program would.

Usage: explorer_escreve.py <folder> <seconds to wait before starting>"""

import os
import sys
import time
from pathlib import Path

base = Path(sys.argv[1])
time.sleep(float(sys.argv[2]))
lines = [f"linha {i}" for i in range(1, 401)]
lines[4] = f"gravado = {int(time.time() * 1000)}"
(base / "longo.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
time.sleep(3)
(base / "src" / "novo-arquivo.js").write_text("export const novo = 1;\n", encoding="utf-8")
time.sleep(3)
(base / "longo.txt").unlink()
time.sleep(3)
os.rename(base / "binario.bin", base / "renomeado.bin")
