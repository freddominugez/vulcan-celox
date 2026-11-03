#!/usr/bin/env python3
"""Sensor do pacote no Windows, rodado de dentro da pasta extraída: terminal real, API e a interface num Edge sem tela.

Uso: python -X utf8 smoke_windows.py <saida para a captura>. Sai com erro no primeiro problema.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def main() -> int:
    out = Path(sys.argv[1])
    home = tempfile.mkdtemp(prefix="celox-smoke-")
    os.environ.update(VULCAN_CELOX_HOME=home, VULCAN_KEYSTORE="memory", VULCAN_AUTOSTART="0", VULCAN_AGENTS="0")
    from vulcan_celox import __version__
    from vulcan_celox.desktop_linux import windows_browser, write_launcher
    from vulcan_celox.server.app import VulcanApp
    print("versão", __version__)
    app = VulcanApp(token="token-do-sensor").start()
    base = f"http://127.0.0.1:{app.server.port}"

    def api(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(base + path, data=data, method=method,
                                         headers={"X-Vulcan-Token": "token-do-sensor", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        tab = api("POST", "/api/terminals", {"cwd": home, "rows": 30, "cols": 100})
        print("shell", tab["argv"])
        session = app.terminals.get(tab["id"])
        session.write("echo marca-do-sensor-çã\r".encode("utf-8"))
        deadline = time.time() + 30
        while time.time() < deadline and "marca-do-sensor-çã" not in session.history().decode("utf-8", "replace").replace("echo marca-do-sensor-çã", ""):
            time.sleep(0.3)
        text = session.history().decode("utf-8", "replace")
        if "marca-do-sensor-çã" not in text.replace("echo marca-do-sensor-çã", ""):
            print(text[-1500:])
            raise SystemExit("o terminal não respondeu ao comando")
        print("terminal ok")
        print("portas", api("GET", "/api/terminals/ports"))

        browser = windows_browser(os.environ)
        if not browser:
            raise SystemExit("sem Edge ou Chrome")
        launcher = write_launcher(app.data_dir, app.server.port, "token-do-sensor")
        common = [browser, "--headless=new", "--disable-gpu", f"--user-data-dir={home}\\perfil", "--virtual-time-budget=9000",
                  "--window-size=1440,900"]
        dom = subprocess.run(common + ["--dump-dom", launcher.as_uri()], capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
        subprocess.run(common + [f"--screenshot={out}", launcher.as_uri()], capture_output=True, timeout=120)
        for needed in ("Overview", "Terminals", "nav-item"):
            if needed not in dom:
                print(dom[:1500])
                raise SystemExit(f"a interface não mostrou: {needed}")
        if re.search(r">\s*Visão geral\s*<|class=\"[^\"]*toast-error", dom):
            raise SystemExit("texto em português ou erro na interface")
        print("interface ok; captura:", out.exists())
        app.terminals.close(tab["id"])
        print("encerrou", session.exit_code)
    finally:
        app.shutdown()
    print("SENSOR OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
