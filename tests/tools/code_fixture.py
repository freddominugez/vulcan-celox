"""Builds a synthetic session for the Code tab sensors and, with `crescer`, writes new edits to the JSONL over time.

Usage: code_fixture.py <folder>            creates <folder>/claude and <folder>/projeto
     code_fixture.py <folder> crescer N  writes edit N (edits <folder>/projeto/passo-N.py)
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SID = "cccccccc-dddd-4eee-8fff-000000000001"
HOSTIL = "<img src=x onerror=window.__xss=1>.php"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def edit(tool_id, path, old, new):
    return {"type": "assistant", "timestamp": now(), "cwd": CWD, "gitBranch": "main",
            "message": {"role": "assistant", "content": [{"type": "tool_use", "id": tool_id, "name": "Edit",
                        "input": {"file_path": str(path), "old_string": old, "new_string": new}}]}}


def result(tool_id):
    return {"type": "user", "timestamp": now(), "cwd": CWD,
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": "ok"}]},
            "toolUseResult": {"structuredPatch": []}}


base = Path(sys.argv[1]).resolve()
project = base / "projeto"
CWD = str(project)
jsonl = base / "claude" / "projects" / "-sintetico" / f"{SID}.jsonl"


def write(*lines):
    with open(jsonl, "a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(json.dumps(line) + "\n")


if len(sys.argv) > 2 and sys.argv[2] == "crescer":
    step = sys.argv[3]
    target = project / f"passo-{step}.py"
    target.write_text("\n".join(f"# linha {i}" for i in range(400)) + f"\nvalor = {step}\ngravado = {int(time.time() * 1000)}\n", encoding="utf-8")
    write(edit(f"s{step}", target, "valor = 0", f"valor = {step}"))
else:
    project.mkdir(parents=True)
    jsonl.parent.mkdir(parents=True)
    (project / "src" / "core").mkdir(parents=True)
    hostil = project / HOSTIL
    hostil.write_text("<?php\n// <script>window.__xss=1</script>\necho '<img src=x onerror=window.__xss=1>';\n", encoding="utf-8")
    comum = project / "src" / "core" / "app.py"
    comum.write_text("def soma(a, b):\n    return a + b\n", encoding="utf-8")
    (project / ".env").write_text("SEGREDO=nao-mostrar\n", encoding="utf-8")
    write({"type": "user", "timestamp": now(), "cwd": CWD, "gitBranch": "main", "message": {"role": "user", "content": "improve the code"}},
          edit("t1", comum, "return a", "return a + b"), result("t1"),
          edit("t2", project / ".env", "SEGREDO=velho", "SEGREDO=nao-mostrar"), result("t2"),
          edit("t3", hostil, "// antes", "// <script>window.__xss=1</script>"), result("t3"))
