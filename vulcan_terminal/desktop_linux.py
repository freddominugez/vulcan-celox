"""Casca do Vulcan Terminal no Linux: sobe o servidor no próprio processo e abre a interface.

Ordem: janela GTK 3 com WebKit2GTK (PyGObject), janela de app do Chromium/Chrome/Brave/Edge ou o navegador
padrão (xdg-open). Uso: vulcan-terminal [--check] [--mode gtk|app|browser]
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sys
import threading
import time
import urllib.request
from urllib.parse import urlsplit
from typing import Callable, Optional, Tuple

from vulcan_terminal import APP_NAME, __version__
from vulcan_terminal.core.runner import Runner

BROWSERS = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "brave-browser",
            "microsoft-edge", "microsoft-edge-stable")
IDLE_EXIT_SECONDS = 150.0


def gtk_webkit_version() -> Optional[str]:
    """Versão do WebKit2GTK utilizável com GTK 3, ou None."""
    try:
        import gi
        gi.require_version("Gtk", "3.0")
    except (ImportError, ValueError):
        return None
    for version in ("4.1", "4.0"):
        try:
            gi.require_version("WebKit2", version)
            from gi.repository import WebKit2  # noqa: F401
            return version
        except (ImportError, ValueError):
            continue
    return None


def choose_mode(env, which: Callable[[str], Optional[str]] = shutil.which,
                gtk: Callable[[], Optional[str]] = gtk_webkit_version) -> Tuple[str, Optional[str]]:
    """(modo, detalhe): ("gtk", versão) | ("app", navegador) | ("browser", None)."""
    forced = env.get("VULCAN_LINUX_MODE")
    if forced not in (None, "", "gtk", "app", "browser"):
        forced = None
    if forced in (None, "", "gtk") and env.get("DISPLAY", env.get("WAYLAND_DISPLAY")) is not None:
        version = gtk()
        if version:
            return "gtk", version
    if forced in (None, "", "app", "gtk"):
        browser = next((which(b) for b in BROWSERS if which(b)), None)
        if browser:
            return "app", browser
    return "browser", None


def is_app_uri(uri: Optional[str], port: int) -> bool:
    """A janela só mostra o próprio app: http://127.0.0.1:<porta> ou about:blank."""
    if uri == "about:blank":
        return True
    try:
        parts = urlsplit(uri or "")
        return parts.scheme == "http" and parts.hostname == "127.0.0.1" and parts.port == port
    except ValueError:
        return False


def bootstrap_script(token: str, port: int) -> str:
    """Define window.VULCAN só quando a página carregada é a do app: outra origem não vê o token."""
    origin = json.dumps(f"http://127.0.0.1:{port}")
    return (f"if (location.origin === {origin}) {{ window.VULCAN = {{ token: {json.dumps(token)}, native: false, "
            "bridge: true, kind: 'main' }; }")


LAUNCHER_NAME = "abrir-janela.html"


def write_launcher(data_dir, port: int, token: str, route: str = "#/overview"):
    """Página 0600 na pasta de dados que leva o navegador ao app com o token no fragmento.
    O token não aparece na linha de comando do navegador nem do xdg-open, que outros usuários da máquina leem."""
    from pathlib import Path
    folder = Path(data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / LAUNCHER_NAME
    target = f"http://127.0.0.1:{port}/#token={token}&route={route.lstrip('#')}"
    html = ("<!doctype html><meta charset=\"utf-8\"><title>Vulcan Terminal</title>"
            f"<script>location.replace({json.dumps(target)});</script>")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(html)
    os.chmod(str(path), 0o600)  # arquivo antigo com outro modo
    return path


def app_window_argv(browser: str, launcher, profile) -> list:
    """Chromium em modo app aberto pelo lançador: nenhum argumento leva o token."""
    return [browser, f"--app={launcher.as_uri()}", f"--user-data-dir={profile}",
            "--no-first-run", "--no-default-browser-check", "--class=VulcanTerminal"]


def should_exit_idle(last_request: float, started: float, now: float, timeout: float = IDLE_EXIT_SECONDS) -> bool:
    """No modo navegador não há janela para observar: encerra quando a interface para de consultar o servidor."""
    reference = last_request or started
    grace = timeout * 2 if not last_request else timeout  # dá tempo de o navegador abrir
    return now - reference > grace


def check(app, token: str) -> int:
    """Sobe o servidor sem janela, consulta a API e a interface, e encerra."""
    base = f"http://127.0.0.1:{app.server.port}"
    try:
        request = urllib.request.Request(f"{base}/api/state", headers={"X-Vulcan-Token": token})
        with urllib.request.urlopen(request, timeout=10) as response:
            state = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base}/", timeout=10) as response:
            page = response.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"check falhou: {exc}", file=sys.stderr)
        return 1
    ok = "Vulcan Terminal" in page and "backend" in state
    print(json.dumps({"ok": ok, "version": __version__, "backend": state["backend"]["label"],
                      "data_dir": state["app"]["data_dir"], "sites": len(state["sites"])}, ensure_ascii=False))
    return 0 if ok else 1


def run_app_window(app, token: str, browser: str) -> int:
    profile = os.path.join(str(app.data_dir), "janela")
    os.makedirs(profile, exist_ok=True)
    closed = threading.Event()
    codes = []
    # perfil próprio: o processo do navegador vive só enquanto a janela do app estiver aberta
    launcher = write_launcher(app.data_dir, app.server.port, token)
    Runner().stream(app_window_argv(browser, launcher, profile),
                    on_exit=lambda code: (codes.append(code), closed.set()))
    closed.wait()
    return codes[0] if codes else 0


def run_browser(app, token: str) -> int:
    url = write_launcher(app.data_dir, app.server.port, token).as_uri()  # sem o token na linha de comando
    opener = shutil.which("xdg-open")
    if opener:
        Runner().stream([opener, url])  # em segundo plano: alguns xdg-open só retornam quando o navegador fecha
    print(f"{APP_NAME} rodando em http://127.0.0.1:{app.server.port} (abra este arquivo se o navegador não abriu):\n{url}",
          flush=True)
    started = time.monotonic()
    while not should_exit_idle(app.server.last_api_request, started, time.monotonic()):
        time.sleep(5)
    return 0


def run_gtk(app, token: str, version: str) -> int:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", version)
    from gi.repository import Gdk, Gtk, WebKit2

    port = app.server.port
    bootstrap = bootstrap_script(token, port)
    windows = {}

    def run_js(view, script: str) -> None:
        if hasattr(view, "evaluate_javascript"):
            view.evaluate_javascript(script, -1, None, None, None, None, None)
        else:
            view.run_javascript(script, None, None, None)

    def message_body(result):
        value = result.get_js_value() if hasattr(result, "get_js_value") else result
        return json.loads(value.to_json(0))

    def make_window(route: str, title: str, key: str):
        manager = WebKit2.UserContentManager()
        manager.add_script(WebKit2.UserScript(bootstrap, WebKit2.UserContentInjectedFrames.TOP_FRAME,
                                              WebKit2.UserScriptInjectionTime.START, None, None))
        view = WebKit2.WebView.new_with_user_content_manager(manager)
        window = Gtk.Window(title=title)
        window.set_default_size(1280 if key == "main" else 900, 820 if key == "main" else 560)
        window.set_icon_name("vulcan-terminal")
        window.add(view)
        manager.register_script_message_handler("vulcan")
        manager.connect("script-message-received::vulcan", lambda _m, result: on_message(view, window, message_body(result)))
        view.connect("decide-policy", on_policy)
        windows[key] = (window, view)

        def on_destroy(_w):
            windows.pop(key, None)
            if key == "main":
                Gtk.main_quit()
            elif "main" in windows:
                run_js(windows["main"][1], f"window.dispatchEvent(new CustomEvent('vulcan-popout-closed', {{detail: {json.dumps(key)}}}))")

        window.connect("destroy", on_destroy)
        view.load_uri(f"http://127.0.0.1:{port}/{route}")
        window.show_all()
        return window

    def on_policy(_view, decision, decision_type) -> bool:
        """Navegação fora do app é cancelada; link externo clicado abre no navegador padrão."""
        if decision_type not in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION,
                                 WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
            return False
        action = decision.get_navigation_action() if hasattr(decision, "get_navigation_action") else None
        request = action.get_request() if action is not None else decision.get_request()
        uri = request.get_uri() if request is not None else None
        if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION and is_app_uri(uri, port):
            return False  # segue o padrão (usar)
        decision.ignore()
        clicked = action is not None and action.get_navigation_type() == WebKit2.NavigationType.LINK_CLICKED
        opener = shutil.which("xdg-open")
        if clicked and opener and (uri or "").startswith(("http://", "https://")):
            Runner().stream([opener, uri])
        return True

    def on_message(view, window, body) -> None:
        if not is_app_uri(view.get_uri(), port):
            return  # mensagem de página que não é do app
        kind = body.get("type")
        if kind == "setTitle":
            window.set_title(str(body.get("title") or APP_NAME))
        elif kind == "close":
            window.close()
        elif kind == "popout" and body.get("id"):
            key = str(body["id"])
            if key in windows:
                windows[key][0].present()
            else:
                make_window(f"#/popout/{key}", str(body.get("title") or "Terminal"), key)
        elif kind == "copy" and isinstance(body.get("text"), str):
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(body["text"], -1)
            clipboard.store()
        elif kind == "focusPopout" and str(body.get("id")) in windows:
            windows[str(body["id"])][0].present()
        elif kind == "pickFolder":
            dialog = Gtk.FileChooserNative.new("Escolha a pasta onde o terminal vai abrir", window,
                                               Gtk.FileChooserAction.SELECT_FOLDER, "Abrir terminal aqui", "Cancelar")
            start = body.get("start")
            if start:
                dialog.set_current_folder(os.path.expanduser(str(start)))
            path = dialog.get_filename() if dialog.run() == Gtk.ResponseType.ACCEPT else None
            dialog.destroy()
            run_js(view, "window.dispatchEvent(new CustomEvent('vulcan-folder-picked', "
                         f"{{detail: {{id: {json.dumps(str(body.get('id', '')))}, path: {json.dumps(path)}}}}}))")

    make_window("#/overview", APP_NAME, "main")
    Gtk.main()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="vulcan-terminal", description=f"{APP_NAME} para Linux")
    parser.add_argument("--check", action="store_true", help="sobe o servidor sem janela, verifica e sai (0 = ok)")
    parser.add_argument("--mode", choices=("gtk", "app", "browser"), help="força o modo de janela")
    parser.add_argument("--doctor", action="store_true", help="diagnóstico em JSON do ambiente")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args = parser.parse_args(argv)

    if args.doctor:
        from vulcan_terminal.core.doctor import render
        print(render())
        return 0

    from vulcan_terminal.server.app import VulcanApp
    token = secrets.token_urlsafe(32)
    app = VulcanApp(token=token).start()
    try:
        if args.check:
            return check(app, token)
        app.autostart.begin()
        env = dict(os.environ)
        if args.mode:
            env["VULCAN_LINUX_MODE"] = args.mode
        mode, detail = choose_mode(env)
        if mode == "gtk":
            return run_gtk(app, token, detail)
        if mode == "app":
            return run_app_window(app, token, detail)
        return run_browser(app, token)
    except KeyboardInterrupt:
        return 0
    finally:
        app.shutdown()


if __name__ == "__main__":
    sys.exit(main())
