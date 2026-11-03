"""Geração do índice Markdown de tarefas (TAREFAS.md)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from vulcan_terminal.core.models import PRIORITY_LABELS, Tag, Task
from vulcan_terminal.core.progress import progress, text_bar
from vulcan_terminal.core.store import write_text_atomic

INDEX_FILENAME = "TAREFAS.md"
GLOBAL_LABEL = "Global"
HEADER_NOTE = ("> Índice gerado automaticamente pelo Vulcan Celox. "
               "Alterações feitas à mão neste arquivo serão sobrescritas.")
SECTIONS = (("todo", "A fazer"), ("doing", "Em andamento"), ("done", "Concluídas"))
TABLE_HEAD = ("| Prioridade | Título | Tags | Prazo | Concluída em |\n"
              "|---|---|---|---|---|")


def anchor(text: str) -> str:
    """Âncora no padrão do GitHub: minúsculas, sem pontuação, espaços viram hífens."""
    slug = text.strip().lower()
    slug = re.sub(r"[^\w\- ]", "", slug)
    return slug.replace(" ", "-")


def site_label(site: Optional[str]) -> str:
    return GLOBAL_LABEL if site is None else site


def _cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _sort_key(task: Task):
    return (task.priority, task.due or "9999-12-31", task.order, task.title.casefold())


def _ordered_sites(tasks: List[Task]) -> List[Optional[str]]:
    keys = {t.site for t in tasks}
    return sorted(keys, key=lambda k: (k is not None, (k or "").casefold()))


def _progress_line(prefix: str, tasks: List[Task]) -> str:
    p = progress(tasks)
    if p.total == 0:
        return f"**{prefix}:** sem tarefas"
    return f"**{prefix}:** {p.label} `[{text_bar(p.pct)}]`"


def render_site_sections(tasks: List[Task], tags: Dict[str, Tag], heading_level: int = 3) -> List[str]:
    """Blocos A fazer / Em andamento / Concluídas de um conjunto de tarefas."""
    hashes = "#" * heading_level
    lines: List[str] = []
    for status, title in SECTIONS:
        group = sorted((t for t in tasks if t.status == status), key=_sort_key)
        lines += [f"{hashes} {title} ({len(group)})", ""]
        if not group:
            lines += ["_Nenhuma._", ""]
            continue
        lines.append(TABLE_HEAD)
        for task in group:
            tag_text = " ".join(f"`{_cell(tags[t].name)}`" for t in task.tags if t in tags)
            done = (task.done_at or "")[:10] if status == "done" else ""
            lines.append(f"| {PRIORITY_LABELS.get(task.priority, '')} | {_cell(task.title)} | "
                         f"{tag_text} | {task.due or ''} | {done} |")
        lines.append("")
    return lines


def render_global(tasks: Iterable[Task], tags: Dict[str, Tag]) -> str:
    tasks = list(tasks)
    lines = ["# Tarefas", "", HEADER_NOTE, "", _progress_line("Progresso geral", tasks), "",
             "## Índice", ""]
    sites = _ordered_sites(tasks)
    if not sites:
        lines += ["_Sem tarefas._", ""]
        return "\n".join(lines).rstrip("\n") + "\n"
    for site in sites:
        label = site_label(site)
        lines.append(f"- [{label}](#{anchor(label)}): {progress(t for t in tasks if t.site == site).label}")
    lines.append("")
    for site in sites:
        group = [t for t in tasks if t.site == site]
        lines += [f"## {site_label(site)}", "", _progress_line("Progresso", group), ""]
        lines += render_site_sections(group, tags)
    return "\n".join(lines).rstrip("\n") + "\n"


def write_if_changed(path: Path, content: str) -> bool:
    """Grava de forma atômica só quando o conteúdo mudou. Retorna True se gravou."""
    path = Path(path)
    try:
        if path.read_text(encoding="utf-8") == content:
            return False
    except (OSError, UnicodeDecodeError):
        pass
    write_text_atomic(path, content)
    return True


def global_index_path(data_dir: Path) -> Path:
    return Path(data_dir) / INDEX_FILENAME


# ── índice dentro da pasta do projeto (opt-in) ───────────────────────────────
BLOCK_START = "<!-- vulcan:tarefas:inicio -->"
BLOCK_END = "<!-- vulcan:tarefas:fim -->"
SETTINGS_FILE = "settings"


class ProjectPathMissing(Exception):
    """A pasta do projeto não existe mais."""


def render_project_block(site: Optional[str], tasks: Iterable[Task], tags: Dict[str, Tag]) -> str:
    group = [t for t in tasks if t.site == site]
    lines = [BLOCK_START, f"## Tarefas ({site_label(site)})", "",
             "> Bloco mantido pelo Vulcan Celox. O texto fora dos marcadores é preservado.", "",
             _progress_line("Progresso", group), ""]
    lines += render_site_sections(group, tags)
    return "\n".join(lines).rstrip("\n") + "\n" + BLOCK_END


def apply_block(existing: str, block: str) -> str:
    """Troca o bloco marcado; sem marcadores válidos, acrescenta o bloco ao final."""
    start = existing.find(BLOCK_START)
    end = existing.find(BLOCK_END, start + len(BLOCK_START)) if start != -1 else -1
    if start != -1 and end != -1:
        return existing[:start] + block + existing[end + len(BLOCK_END):]
    if not existing.strip():
        return block + "\n"
    return existing.rstrip("\n") + "\n\n" + block + "\n"


def write_project_index(project_path: str, site: Optional[str], tasks: Iterable[Task],
                        tags: Dict[str, Tag]) -> bool:
    folder = Path(project_path).expanduser()
    if not folder.is_dir():
        raise ProjectPathMissing(str(folder))
    target = folder / INDEX_FILENAME
    try:
        existing = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = ""
    return write_if_changed(target, apply_block(existing, render_project_block(site, tasks, tags)))


class ProjectIndexSettings:
    """Quais sites mantêm TAREFAS.md na própria pasta (persistido em settings.json)."""

    def __init__(self, store):
        self.store = store

    def _load(self) -> Dict:
        data = self.store.load(SETTINGS_FILE, {})
        return data if isinstance(data, dict) else {}

    def enabled(self, site: str) -> bool:
        return bool(self._load().get("project_index", {}).get(site))

    def set(self, site: str, value: bool) -> None:
        data = self._load()
        data.setdefault("project_index", {})[site] = bool(value)
        self.store.save(SETTINGS_FILE, data)

    def enabled_sites(self) -> List[str]:
        return sorted(s for s, on in self._load().get("project_index", {}).items() if on)


def sync_project_indexes(settings: ProjectIndexSettings, site_paths: Dict[str, str],
                         tasks: Iterable[Task], tags: Dict[str, Tag]) -> List[str]:
    """Atualiza os TAREFAS.md de projeto habilitados. Retorna avisos.

    Site habilitado cuja pasta sumiu é desligado; site fora da lista atual é ignorado.
    """
    tasks = list(tasks)
    warnings: List[str] = []
    for site in settings.enabled_sites():
        path = site_paths.get(site)
        if path is None:
            continue
        try:
            write_project_index(path, site, tasks, tags)
        except ProjectPathMissing:
            settings.set(site, False)
            warnings.append(f"pasta de '{site}' não existe mais: TAREFAS.md do projeto desligado")
    return warnings
