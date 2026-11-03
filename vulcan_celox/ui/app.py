"""Janela principal do Vulcan Celox."""

from __future__ import annotations

import os
import queue
import sys
import tempfile
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable, List, Mapping, Optional

from vulcan_celox import APP_NAME, __version__
from vulcan_celox.core import paths
from vulcan_celox.core.backends import detect_backend
from vulcan_celox.core.debounce import Debouncer
from vulcan_celox.core.markdown_index import (INDEX_FILENAME, ProjectIndexSettings, ProjectPathMissing,
                                                 global_index_path, render_global, render_project_block,
                                                 sync_project_indexes, write_if_changed, write_project_index)
from vulcan_celox.core.notebook import Notebook
from vulcan_celox.core.progress import Progress, progress, progress_by_site
from vulcan_celox.core.store import Store, migrate_legacy
from vulcan_celox.ui import theme
from vulcan_celox.ui.notes import NotesBoard
from vulcan_celox.ui.search import SearchWindow
from vulcan_celox.ui.sidebar import Sidebar
from vulcan_celox.ui.tags import TagManager
from vulcan_celox.ui.tasks import TasksPanel

STATUS_INTERVAL_MS = 15000
INDEX_DEBOUNCE_SECONDS = 0.5
DRAIN_INTERVAL_MS = 100


class App(tk.Tk):
    def __init__(self, env: Optional[Mapping[str, str]] = None, selftest: bool = False):
        super().__init__()
        self.env = os.environ if env is None else env
        self.selftest_mode = selftest
        self.errors: List[str] = []
        self._ui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self.current_site: Optional[str] = None

        self.title(f"{APP_NAME} {__version__}")
        self.geometry("1180x740")
        self.minsize(960, 600)
        theme.apply(self)

        self.store = Store(paths.data_dir(self.env))
        migrate_legacy(self.store, paths.legacy_dir(self.env))
        self.notebook = Notebook(self.store)
        self.notebook.migrate_legacy_notes()
        self.backend = detect_backend(self.env)
        self.runner = self.backend.runner
        self.manual_sites = self.store.load("sites", {})
        self.sites = []

        self._progress_job = None
        self.data_dir = paths.data_dir(self.env)
        self.index_debouncer = Debouncer(INDEX_DEBOUNCE_SECONDS, self.write_indexes)
        self.project_index = ProjectIndexSettings(self.store)
        self._build()
        self.notebook.subscribe(self._on_notebook_change)
        self.reload_sites()
        self.sidebar.select(None)
        self.show_site(None)
        self._refresh_status()
        self.write_indexes()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(DRAIN_INTERVAL_MS, self._drain)

    # ── infraestrutura ───────────────────────────────────────────────────
    def report_callback_exception(self, exc, val, tb):  # noqa: N802 (API do Tk)
        text = "".join(traceback.format_exception(exc, val, tb))
        self.errors.append(text)
        sys.stderr.write(text)
        self.set_message(f"erro: {val}", error=True)

    def call_in_ui(self, fn: Callable[[], None]) -> None:
        """Agenda fn na thread da UI (seguro a partir de outras threads)."""
        self._ui_queue.put(fn)

    def run_in_background(self, work: Callable[[], object], done: Callable[[object], None]) -> None:
        def _worker():
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001
                result = exc
            self.call_in_ui(lambda: done(result))
        threading.Thread(target=_worker, daemon=True).start()

    def _drain(self) -> None:
        while True:
            try:
                fn = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:  # noqa: BLE001
                self.report_callback_exception(*sys.exc_info())
        self.index_debouncer.poll()
        self.after(DRAIN_INTERVAL_MS, self._drain)

    # ── layout ───────────────────────────────────────────────────────────
    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        caderno = tk.Menu(menubar, tearoff=0)
        caderno.add_command(label="Buscar…", command=self.open_search, accelerator="Cmd+K")
        caderno.add_command(label="Gerenciar tags…", command=self.open_tags, accelerator="Cmd+T")
        caderno.add_separator()
        caderno.add_command(label="Abrir TAREFAS.md geral", command=self.open_global_index)
        caderno.add_command(label="Abrir pasta de dados", command=lambda: self._open(["/usr/bin/open", str(self.data_dir)]))
        caderno.add_separator()
        caderno.add_command(label="Exportar caderno…", command=self.export_notebook)
        caderno.add_command(label="Importar caderno…", command=self.import_notebook)
        menubar.add_cascade(label="Caderno", menu=caderno)
        self.menu_caderno = caderno
        self.config(menu=menubar)
        self.bind_all("<Command-t>", lambda _e: self.open_tags())
        self.bind_all("<Command-k>", lambda _e: self.open_search())

    def open_tags(self) -> TagManager:
        existing = getattr(self, "_tag_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return existing
        self._tag_window = TagManager(self, self.notebook)
        return self._tag_window

    def open_search(self) -> SearchWindow:
        existing = getattr(self, "_search_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.entry.focus_set()
            return existing
        self._search_window = SearchWindow(self, lambda: self.sites, self.notebook, self.navigate)
        return self._search_window

    def navigate(self, hit) -> None:
        """Leva ao item escolhido na busca."""
        if hit.kind == "tag":
            win = self.open_tags()
            if win.tree.exists(hit.key):
                win.tree.selection_set(hit.key)
                win.tree.see(hit.key)
            return
        site = hit.site if (hit.site is None or self.sidebar.site(hit.site)) else None
        self.sidebar.select(site)
        if self.current_site != site or not hasattr(self, "tabs"):
            self.show_site(site)
        if hit.kind == "task":
            self.tabs.select(self.tasks_panel)
            self.tasks_panel.var_status.set("Todas")
            self.tasks_panel.var_tag.set("Todas as tags")
            self.tasks_panel.render()
            if self.tasks_panel.tree.exists(hit.key):
                self.tasks_panel.tree.selection_set(hit.key)
                self.tasks_panel.tree.see(hit.key)
        elif hit.kind == "note":
            self.tabs.select(self.notes_board)
            self.notes_board.var_query.set("")
            self.notes_board.render()
            card = self.notes_board.cards.get(hit.key)
            if card is not None:
                card.text.focus_set()
        if hit.site is not None and site is None:
            self.set_message(f"'{hit.site}' não está na lista de projetos agora; mostrando Global")

    def export_notebook(self) -> None:
        path = filedialog.asksaveasfilename(parent=self, title="Exportar caderno", defaultextension=".json",
                                            initialfile="vulcan-celox-caderno.json")
        if path:
            counts = self.notebook.export(path)
            self.set_message(f"exportado: {counts['tasks']} tarefas, {counts['notes']} post-its, {counts['tags']} tags")

    def import_notebook(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Importar caderno", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            counts = self.notebook.import_(path)
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        self.show_site(self.current_site)
        self.set_message(f"importado: {counts['tasks']} tarefas, {counts['notes']} post-its, {counts['tags']} tags")

    def _build(self) -> None:
        self._build_menu()
        header = ttk.Frame(self, style="Panel.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="Vulcan Celox", style="Brand.TLabel").pack(side="left", padx=14, pady=10)
        self.var_status = tk.StringVar(value="…")
        ttk.Label(header, textvariable=self.var_status, style="PanelDim.TLabel").pack(side="left", padx=12)
        self.var_global_progress = tk.StringVar(value="")
        ttk.Label(header, textvariable=self.var_global_progress, style="PanelDim.TLabel").pack(side="left", padx=(24, 6))
        self.global_bar = ttk.Progressbar(header, length=140, maximum=100, style="Accent.Horizontal.TProgressbar")
        self.global_bar.pack(side="left")

        self.service_buttons = []
        for text, action in (("Restart", "restart"), ("Stop", "stop"), ("Start", "start")):
            btn = ttk.Button(header, text=text, command=lambda a=action: self.service(a))
            btn.pack(side="right", padx=4, pady=8)
            self.service_buttons.append(btn)
        if not self.backend.available:
            for btn in self.service_buttons:
                btn.state(["disabled"])
        if hasattr(self.backend, "dashboard_url"):
            ttk.Button(header, text="Painel", style="Accent.TButton",
                       command=self.open_dashboard).pack(side="right", padx=(4, 12), pady=8)
        self.header = header

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.sidebar = Sidebar(body, on_select=self.show_site, on_add=self.add_manual_site,
                               on_remove=self.remove_manual_site, on_reload=self.reload_sites,
                               on_browser=self.open_in_browser, on_terminal=self.open_in_terminal)
        self.sidebar.pack(side="left", fill="y")

        self.panel = ttk.Frame(body)
        self.panel.pack(side="left", fill="both", expand=True, padx=14, pady=10)

        footer = ttk.Frame(self, style="Panel.TFrame")
        footer.pack(fill="x", side="bottom")
        self.var_message = tk.StringVar(value="")
        self.lbl_message = ttk.Label(footer, textvariable=self.var_message, style="PanelDim.TLabel")
        self.lbl_message.pack(side="left", padx=12, pady=4)

    def build_site_panel(self, parent: ttk.Frame, site_name: Optional[str]) -> None:
        """Abas do painel de um site."""
        self.tabs = ttk.Notebook(parent)
        self.tabs.pack(fill="both", expand=True)
        self.tasks_panel = TasksPanel(self.tabs, self.notebook, site_name, on_message=self.set_message)
        self.tabs.add(self.tasks_panel, text="  Tarefas  ")
        self.notes_board = NotesBoard(self.tabs, self.notebook, site_name)
        self.tabs.add(self.notes_board, text="  Post-its  ")

    def show_site(self, name: Optional[str]) -> None:
        self.current_site = name
        for child in self.panel.winfo_children():
            child.destroy()
        top = ttk.Frame(self.panel)
        top.pack(fill="x", pady=(0, 8))
        site = self.sidebar.site(name)
        if site is None:
            ttk.Label(top, text="Global", style="Title.TLabel").pack(side="left")
            ttk.Label(top, text="notas e tarefas fora de projeto", style="Dim.TLabel").pack(side="left", padx=12)
        else:
            ttk.Label(top, text=site.name, style="Title.TLabel").pack(side="left")
            php = f"PHP {site.php}  ·  " if site.php else ""
            ttk.Label(top, text=f"{site.url}  ·  {php}{site.path}  ·  {site.kind}",
                      style="Dim.TLabel").pack(side="left", padx=12)
        self.var_site_progress = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.var_site_progress, style="Dim.TLabel").pack(side="right", padx=(8, 0))
        self.site_bar = ttk.Progressbar(top, length=180, maximum=100, style="Accent.Horizontal.TProgressbar")
        self.site_bar.pack(side="right")
        self.panel_top = top
        self.update_progress()
        if site is not None:
            self._build_project_index_row(site)
        content = ttk.Frame(self.panel)
        content.pack(fill="both", expand=True)
        self.build_site_panel(content, name)

    def set_message(self, text: str, error: bool = False) -> None:
        self.var_message.set(text)

    # ── sites ────────────────────────────────────────────────────────────
    def reload_sites(self) -> None:
        self.manual_sites = self.store.load("sites", {})
        self.sites = self.backend.list_sites(self.manual_sites)
        self.sidebar.set_sites(self.sites, self.progress_labels())

    def progress_labels(self):
        return {site: p.short for site, p in progress_by_site(self.notebook.tasks).items()}

    def update_progress(self) -> None:
        self._progress_job = None
        overall = progress(self.notebook.tasks)
        self.var_global_progress.set(f"Geral: {overall.label}")
        self.global_bar["value"] = overall.pct
        if hasattr(self, "site_bar") and self.site_bar.winfo_exists():
            current = progress_by_site(self.notebook.tasks).get(self.current_site, Progress())
            self.var_site_progress.set(current.label)
            self.site_bar["value"] = current.pct
        self.sidebar.update_progress(self.progress_labels())

    def _on_notebook_change(self, kind: str) -> None:
        if kind in ("tasks", "all") and self._progress_job is None:
            self._progress_job = self.after(50, self.update_progress)
        if kind in ("tasks", "tags", "all"):
            self.index_debouncer.touch()

    # ── índice Markdown ──────────────────────────────────────────────────
    def write_indexes(self) -> bool:
        content = render_global(self.notebook.tasks, self.notebook.tags)
        changed = write_if_changed(global_index_path(self.data_dir), content)
        site_paths = {s.name: s.path for s in self.sites}
        for warning in sync_project_indexes(self.project_index, site_paths, self.notebook.tasks, self.notebook.tags):
            self.set_message(warning, error=True)
            if getattr(self, "var_project_index", None) is not None:
                self.var_project_index.set(self.project_index.enabled(self.current_site or ""))
        return changed

    def _build_project_index_row(self, site) -> None:
        row = ttk.Frame(self.panel)
        row.pack(fill="x", pady=(0, 8))
        self.var_project_index = tk.BooleanVar(value=self.project_index.enabled(site.name))
        ttk.Checkbutton(row, text=f"Manter {INDEX_FILENAME} na pasta do projeto", variable=self.var_project_index,
                        command=lambda: self.toggle_project_index(site.name)).pack(side="left")
        ttk.Button(row, text=f"Abrir {INDEX_FILENAME}", style="Small.TButton",
                   command=lambda: self.open_project_index(site.name)).pack(side="left", padx=(12, 4))
        ttk.Button(row, text="Copiar Markdown", style="Small.TButton",
                   command=lambda: self.copy_markdown(site.name)).pack(side="left")

    def toggle_project_index(self, site_name: str) -> None:
        enabled = bool(self.var_project_index.get())
        site = self.sidebar.site(site_name)
        if enabled:
            try:
                write_project_index(site.path, site.name, self.notebook.tasks, self.notebook.tags)
            except ProjectPathMissing:
                self.var_project_index.set(False)
                self.project_index.set(site_name, False)
                self.set_message(f"pasta de '{site_name}' não existe", error=True)
                return
            self.set_message(f"{INDEX_FILENAME} mantido em {site.path}")
        else:
            self.set_message(f"{INDEX_FILENAME} de '{site_name}' não será mais atualizado (o arquivo continua lá)")
        self.project_index.set(site_name, enabled)

    def open_project_index(self, site_name: str) -> None:
        site = self.sidebar.site(site_name)
        target = os.path.join(site.path, INDEX_FILENAME)
        if not os.path.exists(target):
            self.set_message(f"{INDEX_FILENAME} ainda não existe no projeto: ligue a opção ao lado")
            return
        self._open(["/usr/bin/open", target])

    def copy_markdown(self, site_name: Optional[str]) -> str:
        text = render_project_block(site_name, self.notebook.tasks, self.notebook.tags)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.set_message("Markdown das tarefas copiado")
        return text

    def open_global_index(self) -> None:
        self.index_debouncer.flush()
        self.write_indexes()
        self._open(["/usr/bin/open", str(global_index_path(self.data_dir))])

    def close(self) -> None:
        for widget in (getattr(self, "notes_board", None),):
            if widget is not None:
                try:
                    widget.flush()
                except tk.TclError:
                    pass
        self.index_debouncer.flush()
        self.destroy()

    def add_manual_site(self) -> None:
        folder = filedialog.askdirectory(parent=self, title="Pasta do projeto")
        if not folder:
            return
        name = simpledialog.askstring("Nome do projeto", "Nome (vira http://nome.test):",
                                      initialvalue=os.path.basename(folder), parent=self)
        if not name:
            return
        name = name.strip()
        self.manual_sites[name] = folder
        self.store.save("sites", self.manual_sites)
        self.reload_sites()
        self.sidebar.select(name)
        self.set_message(f"projeto '{name}' adicionado")

    def remove_manual_site(self) -> None:
        name = self.sidebar.selected_key()
        site = self.sidebar.site(name)
        if site is None:
            return
        if site.kind != "manual":
            messagebox.showinfo(APP_NAME, f"'{name}' vem do {self.backend.label} ({site.kind}).\n"
                                f"Use 'unlink' no {self.backend.name} ou o painel dele; "
                                "desregistrar pelo app chega na próxima versão.", parent=self)
            return
        if messagebox.askyesno(APP_NAME, f"Remover '{name}' da lista?\n(a pasta não é apagada; "
                               "notas e tarefas continuam salvas)", parent=self):
            self.manual_sites.pop(name, None)
            self.store.save("sites", self.manual_sites)
            self.reload_sites()
            self.sidebar.select(None)
            self.show_site(None)

    def open_dashboard(self) -> None:
        self._open(["/usr/bin/open", self.backend.dashboard_url()])

    def open_in_browser(self) -> None:
        site = self.sidebar.site(self.sidebar.selected_key())
        if site:
            self._open(["/usr/bin/open", site.url])

    def open_in_terminal(self) -> None:
        site = self.sidebar.site(self.sidebar.selected_key())
        self._open(["/usr/bin/open", "-a", "Terminal", site.path if site else os.path.expanduser("~")])

    def _open(self, argv) -> None:
        self.run_in_background(lambda: self.runner.run(argv, timeout=15),
                               lambda r: self.set_message(" ".join(argv[1:]) if getattr(r, "ok", False)
                                                          else f"erro ao abrir: {getattr(r, 'output', r)}"))

    # ── serviços ─────────────────────────────────────────────────────────
    def service(self, action: str) -> None:
        self.set_message(f"{self.backend.name} {action}…")
        fn = getattr(self.backend, action)
        self.run_in_background(fn, lambda r: self._service_done(action, r))

    def _service_done(self, action: str, result) -> None:
        if isinstance(result, Exception):
            self.set_message(f"{self.backend.name} {action}: {result}", error=True)
        else:
            text = (result.output or "").strip().splitlines()
            self.set_message(f"{self.backend.name} {action}: {'ok' if result.ok else 'falhou'}"
                             + (f" · {text[-1]}" if text else ""), error=not result.ok)
        self._refresh_status(reschedule=False)

    def _refresh_status(self, reschedule: bool = True) -> None:
        backend = self.backend

        def work():
            return backend.status().summary

        self.run_in_background(work, lambda text: self.var_status.set(str(text)))
        if reschedule:
            self.after(STATUS_INTERVAL_MS, self._refresh_status)

    # ── selftest ─────────────────────────────────────────────────────────
    def selftest_steps(self) -> List[Callable[[], None]]:
        def select_first():
            first = self.sites[0].name if self.sites else None
            self.sidebar.select(first)
            self.show_site(first)

        def tags_window():
            win = self.open_tags()
            win.var_name.set(f"selftest-{time.time_ns()}")
            win.create()
            win.cycle_color()
            win.destroy()

        def notes_flow():
            board = self.notes_board
            note = board.new_note()
            card = board.cards[note.id]
            card.text.insert("1.0", "nota do selftest com NGINX")
            card._on_modified()
            board.flush()
            assert self.notebook.note(note.id).text == "nota do selftest com NGINX"
            second = board.new_note()
            board.move(second.id, note.id)
            self.notebook.cycle_note_color(note.id)
            self.notebook.add_tag_to_item(self.notebook.note(note.id), f"tag-{time.time_ns()}")
            board.var_query.set("nginx")
            board.render()
            assert list(board.cards) == [note.id]
            board.var_query.set("")
            board.render()
            board.cards[second.id]._delete()  # vazio: apaga sem confirmação
            assert self.notebook.note(second.id) is None

        def tasks_flow():
            panel = self.tasks_panel
            panel.var_title.set("tarefa do selftest")
            panel.var_due.set("2026-13-40")
            assert panel.add() is None  # prazo inválido vira mensagem, não modal
            panel.var_due.set("2026-09-30")
            panel._queue_tag(f"tarefa-{time.time_ns()}")
            task = panel.add()
            assert task is not None and task.tags and panel.tree.exists(task.id)
            self.notebook.cycle_status(task.id)
            assert panel.tree.set(task.id, "status") == "◐"
            self.update_progress()
            expected = progress_by_site(self.notebook.tasks).get(self.current_site, Progress()).label
            assert self.var_site_progress.get() == expected, self.var_site_progress.get()
            self.notebook.set_status(task.id, "done")
            self.update_progress()
            assert self.site_bar["value"] == progress_by_site(self.notebook.tasks)[self.current_site].pct
            panel.tree.selection_set(task.id)
            panel.tree.update_idletasks()
            editor = panel.edit_cell(task.id, "#3", task.title, lambda v: self.notebook.update_task(task.id, title=v))
            if editor is not None:
                editor.delete(0, "end")
                editor.insert(0, "tarefa editada")
                editor.commit()
                assert self.notebook.task(task.id).title == "tarefa editada"
            panel.tree.selection_set(task.id)
            panel.delete_selected()
            assert self.notebook.task(task.id) is None
            panel.undo()
            assert self.notebook.task(task.id) is not None
            panel.var_status.set("A fazer")
            panel.render()
            assert not panel.tree.exists(task.id)  # está concluída
            panel.var_status.set("Concluídas")
            panel.render()
            assert panel.tree.exists(task.id)
            panel.var_status.set("Todas")
            panel.render()

        def index_flow():
            self.index_debouncer.flush()
            text = global_index_path(self.data_dir).read_text(encoding="utf-8")
            assert "## Índice" in text and "tarefa editada" in text, text[:200]
            assert "vulcan:tarefas:inicio" in self.copy_markdown(None)
            if self.env.get(paths.ENV_HOME):
                # só com diretório de dados isolado: cria um projeto manual descartável
                project = os.path.join(str(self.data_dir), "selftest-projeto")
                os.makedirs(project, exist_ok=True)
                self.manual_sites["selftest-projeto"] = project
                self.store.save("sites", self.manual_sites)
                self.reload_sites()
            if self.sites:
                site = self.sites[0]
                self.sidebar.select(site.name)
                self.show_site(site.name)
                self.notebook.add_task(site.name, "tarefa do projeto selftest")
                self.var_project_index.set(True)
                self.toggle_project_index(site.name)
                self.index_debouncer.flush()
                self.write_indexes()
                path = os.path.join(site.path, INDEX_FILENAME)
                assert "tarefa do projeto selftest" in open(path, encoding="utf-8").read()

        def search_flow():
            task = self.notebook.add_task(None, f"busca-selftest-{time.time_ns()}")
            win = self.open_search()
            win.var_query.set(task.title)
            win.run_query()
            assert f"task:{task.id}" in win.hits, list(win.hits)
            win.tree.selection_set(f"task:{task.id}")
            win.open_selected()
            assert self.current_site is None
            assert self.tasks_panel.selected_id() == task.id
            export = os.path.join(tempfile.mkdtemp(prefix="vulcan-selftest-"), "caderno.json")
            before = len(self.notebook.tasks)
            self.notebook.export(export)
            self.notebook.import_(export)
            assert len(self.notebook.tasks) == before

        return [select_first, lambda: self.show_site(None), tags_window, notes_flow, tasks_flow, index_flow,
                search_flow]


SELFTEST_WATCHDOG_SECONDS = 30


def _selftest_watchdog() -> None:
    # Um diálogo modal inesperado trava o mainloop: o selftest precisa falhar, não pendurar.
    sys.stderr.write(f"SELFTEST FALHOU: travou por mais de {SELFTEST_WATCHDOG_SECONDS} s "
                     "(diálogo modal ou loop bloqueado)\n")
    sys.stderr.flush()
    os._exit(2)


def run(selftest: bool = False, env: Optional[Mapping[str, str]] = None) -> int:
    if selftest:
        watchdog = threading.Timer(SELFTEST_WATCHDOG_SECONDS, _selftest_watchdog)
        watchdog.daemon = True
        watchdog.start()
    try:
        app = App(env=env, selftest=selftest)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1

    if selftest:
        steps = app.selftest_steps()
        delay = 100
        for step in steps:
            app.after(delay, step)
            delay += 120
        app.after(max(delay, 1000) + 200, app.close)

    app.mainloop()
    if selftest:
        if app.errors:
            print(f"SELFTEST FALHOU: {len(app.errors)} erro(s)", file=sys.stderr)
            return 1
        print("SELFTEST OK")
    return 0
