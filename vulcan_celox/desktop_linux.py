"""Vulcan Celox shell on Linux: starts the server in the same process and opens the interface.

Order: a GTK 3 window with WebKit2GTK (PyGObject), an app window of Chromium/Chrome/Brave/Edge, or the
default browser (xdg-open). Usage: vulcan-celox [--check] [--mode gtk|app|browser]
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

from vulcan_celox import APP_NAME, __version__
from vulcan_celox.core.runner import Runner

BROWSERS = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "brave-browser",
            "microsoft-edge", "microsoft-edge-stable")
IDLE_EXIT_SECONDS = 150.0


def gtk_webkit_version() -> Optional[str]:
    """WebKit2GTK version usable with GTK 3, or None."""
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


def windows_browser(env, exists=os.path.exists) -> Optional[str]:
    """On Windows, Edge comes preinstalled but is not on PATH."""
    if sys.platform != "win32":
        return None
    for base in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = env.get(base)
        for tail in (("Microsoft", "Edge", "Application", "msedge.exe"), ("Google", "Chrome", "Application", "chrome.exe")):
            path = os.path.join(root, *tail) if root else ""
            if path and exists(path):
                return path
    return None


def choose_mode(env, which: Callable[[str], Optional[str]] = shutil.which,
                gtk: Callable[[], Optional[str]] = gtk_webkit_version) -> Tuple[str, Optional[str]]:
    """(mode, detail): ("gtk", version) | ("app", browser) | ("browser", None)."""
    forced = env.get("VULCAN_LINUX_MODE")
    if forced not in (None, "", "gtk", "app", "browser"):
        forced = None
    if forced in (None, "", "gtk") and env.get("DISPLAY", env.get("WAYLAND_DISPLAY")) is not None:
        version = gtk()
        if version:
            return "gtk", version
    if forced in (None, "", "app", "gtk"):
        browser = next((which(b) for b in BROWSERS if which(b)), None) or windows_browser(env)
        if browser:
            return "app", browser
    return "browser", None


def is_app_uri(uri: Optional[str], port: int) -> bool:
    """The window only shows the app itself: http://127.0.0.1:<port> or about:blank."""
    if uri == "about:blank":
        return True
    try:
        parts = urlsplit(uri or "")
        return parts.scheme == "http" and parts.hostname == "127.0.0.1" and parts.port == port
    except ValueError:
        return False


def bootstrap_script(token: str, port: int) -> str:
    """Defines window.VULCAN only when the loaded page is the app's: another origin never sees the token."""
    origin = json.dumps(f"http://127.0.0.1:{port}")
    return (f"if (location.origin === {origin}) {{ window.VULCAN = {{ token: {json.dumps(token)}, native: false, "
            "bridge: true, kind: 'main' }; }")


LAUNCHER_NAME = "abrir-janela.html"


def write_launcher(data_dir, port: int, token: str, route: str = "#/overview"):
    """A 0600 page in the data folder that takes the browser to the app with the token in the fragment.
    The token does not appear in the browser or xdg-open command line, which other users on the machine can read."""
    from pathlib import Path
    folder = Path(data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / LAUNCHER_NAME
    target = f"http://127.0.0.1:{port}/#token={token}&route={route.lstrip('#')}"
    html = ("<!doctype html><meta charset=\"utf-8\"><title>Vulcan Celox</title>"
            f"<script>location.replace({json.dumps(target)});</script>")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(html)
    os.chmod(str(path), 0o600)  # old file with a different mode
    return path


def app_window_argv(browser: str, launcher, profile) -> list:
    """Chromium in app mode opened through the launcher: no argument carries the token."""
    return [browser, f"--app={launcher.as_uri()}", f"--user-data-dir={profile}",
            "--no-first-run", "--no-default-browser-check", "--class=VulcanCelox"]


def should_exit_idle(last_request: float, started: float, now: float, timeout: float = IDLE_EXIT_SECONDS) -> bool:
    """In browser mode there is no window to watch: exits when the interface stops polling the server."""
    reference = last_request or started
    grace = timeout * 2 if not last_request else timeout  # leaves time for the browser to open
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
        print(f"check failed: {exc}", file=sys.stderr)
        return 1
    ok = "Vulcan Celox" in page and "backend" in state
    print(json.dumps({"ok": ok, "version": __version__, "backend": state["backend"]["label"],
                      "data_dir": state["app"]["data_dir"], "sites": len(state["sites"])}, ensure_ascii=False))
    return 0 if ok else 1


def run_app_window(app, token: str, browser: str) -> int:
    profile = os.path.join(str(app.data_dir), "janela")
    os.makedirs(profile, exist_ok=True)
    closed = threading.Event()
    codes = []
    # own profile: the browser process lives only while the app window is open
    launcher = write_launcher(app.data_dir, app.server.port, token)
    Runner().stream(app_window_argv(browser, launcher, profile),
                    on_exit=lambda code: (codes.append(code), closed.set()))
    closed.wait()
    return codes[0] if codes else 0


def run_browser(app, token: str) -> int:
    url = write_launcher(app.data_dir, app.server.port, token).as_uri()  # without the token on the command line
    opener = shutil.which("xdg-open")
    if sys.platform == "win32":
        Runner().stream(["explorer.exe", url])
    elif opener:
        Runner().stream([opener, url])  # in the background: some xdg-open only return when the browser closes
    print(f"{APP_NAME} running at http://127.0.0.1:{app.server.port} (open this file if the browser did not open):\n{url}",
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
        window.set_icon_name("vulcan-celox")
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
        """Navigation away from the app is cancelled; a clicked external link opens in the default browser."""
        if decision_type not in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION,
                                 WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
            return False
        action = decision.get_navigation_action() if hasattr(decision, "get_navigation_action") else None
        request = action.get_request() if action is not None else decision.get_request()
        uri = request.get_uri() if request is not None else None
        if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION and is_app_uri(uri, port):
            return False  # follows the default (use)
        decision.ignore()
        clicked = action is not None and action.get_navigation_type() == WebKit2.NavigationType.LINK_CLICKED
        opener = shutil.which("xdg-open")
        if clicked and opener and (uri or "").startswith(("http://", "https://")):
            Runner().stream([opener, uri])
        return True

    def on_message(view, window, body) -> None:
        if not is_app_uri(view.get_uri(), port):
            return  # message from a page that is not the app's
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
    parser = argparse.ArgumentParser(prog="vulcan-celox", description=f"{APP_NAME} for Linux")
    parser.add_argument("--check", action="store_true", help="start the server without a window, verify and exit (0 = ok)")
    parser.add_argument("--mode", choices=("gtk", "app", "browser"), help="force the window mode")
    parser.add_argument("--doctor", action="store_true", help="environment diagnostics as JSON")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args = parser.parse_args(argv)

    if args.doctor:
        from vulcan_celox.core.doctor import render
        print(render())
        return 0

    from vulcan_celox.core import paths, server_log
    from vulcan_celox.server.app import VulcanApp
    token = secrets.token_urlsafe(32)
    if not args.check:
        server_log.redirect_stderr(paths.data_dir(), [token])  # a crash leaves its traceback in the error log
    log = server_log.setup(paths.data_dir(), [token])
    app = VulcanApp(token=token).start()
    log.info("servidor %s no ar na porta %s", __version__, app.server.port)
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
        log.info("servidor encerrando")
        app.shutdown()
        server_log.close()


if __name__ == "__main__":
    sys.exit(main())
