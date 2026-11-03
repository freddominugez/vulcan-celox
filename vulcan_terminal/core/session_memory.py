"""Memória de uma sessão de terminal em Markdown: o que foi executado e o que foi anotado."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from vulcan_terminal.core.models import PRIORITY_LABELS, Note, Tag, Task
from vulcan_terminal.core.textutil import normalize

MAX_TRANSCRIPT_LINES = 2000
TRANSCRIPT_START = "<!-- vulcan:registro:inicio -->"
TRANSCRIPT_END = "<!-- vulcan:registro:fim -->"
SESSIONS_DIR = "sessoes"

_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_CSI = re.compile(r"\x1b\[([0-?]*)[ -/]*([@-~])")
_ESC2 = re.compile(r"\x1b[@-Z\\-_]")


# ── registro do terminal ─────────────────────────────────────────────────────
def strip_terminal(data) -> Tuple[str, bool]:
    """Converte a saída crua do PTY em texto legível. Retorna (texto, truncado).

    Remove cores e sequências de controle, aplica retorno de carro, backspace e
    apagamento de linha do jeito que o terminal mostraria.
    """
    text = data.decode("utf-8", errors="replace") if isinstance(data, (bytes, bytearray)) else str(data)
    text = _OSC.sub("", text)
    lines: List[str] = []
    line: List[str] = []
    col = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\x1b":
            m = _CSI.match(text, i)
            if m:
                params, final = m.group(1), m.group(2)
                if final == "K":  # apaga até o fim da linha (modo 0)
                    if params in ("", "0"):
                        del line[col:]
                    elif params == "2":
                        line.clear()
                        col = 0
                elif final == "J" and params in ("", "0"):
                    del line[col:]
                elif final == "C":
                    col += int(params or 1) if params.isdigit() else 1
                elif final == "D":
                    col = max(0, col - (int(params or 1) if params.isdigit() else 1))
                elif final == "G":
                    col = max(0, (int(params) if params.isdigit() else 1) - 1)
                i = m.end()
                continue
            m2 = _ESC2.match(text, i)
            i = m2.end() if m2 else i + 1
            continue
        if ch == "\n":
            lines.append("".join(line).rstrip())
            line, col = [], 0
        elif ch == "\r":
            col = 0
        elif ch == "\b":
            col = max(0, col - 1)
        elif ch == "\t":
            target = (col // 8 + 1) * 8
            while col < target:
                _put(line, col, " ")
                col += 1
        elif ord(ch) >= 0x20:
            _put(line, col, ch)
            col += 1
        i += 1
    if line:
        lines.append("".join(line).rstrip())
    compact: List[str] = []
    for entry in lines:
        if entry == "" and compact and compact[-1] == "":
            continue
        compact.append(entry)
    while compact and compact[-1] == "":
        compact.pop()
    while compact and compact[0] == "":
        compact.pop(0)
    truncated = len(compact) > MAX_TRANSCRIPT_LINES
    if truncated:
        compact = compact[-MAX_TRANSCRIPT_LINES:]
    return "\n".join(compact), truncated


def _put(line: List[str], col: int, ch: str) -> None:
    while len(line) < col:
        line.append(" ")
    if col < len(line):
        line[col] = ch
    else:
        line.append(ch)


def extract_transcript(markdown: str) -> Tuple[str, bool]:
    """Recupera o registro de uma memória já gravada (para regenerar sessões encerradas)."""
    start = markdown.find(TRANSCRIPT_START)
    end = markdown.find(TRANSCRIPT_END, start + 1)
    if start == -1 or end == -1:
        return "", False
    block = markdown[start + len(TRANSCRIPT_START):end]
    truncated = "_Mostrando as últimas" in block
    fence = re.search(r"^(`{3,}|~{3,})text\n(.*?)\n\1$", block, re.S | re.M)
    return (fence.group(2) if fence else ""), truncated


# ── Markdown da sessão ───────────────────────────────────────────────────────
def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def format_when(value: Optional[str]) -> str:
    dt = parse_iso(value)
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "-"


def format_duration(start: Optional[str], end: Optional[str]) -> str:
    a, b = parse_iso(start), parse_iso(end)
    if not a or not b:
        return "em andamento"
    seconds = max(0, int((b - a).total_seconds()))
    if seconds < 60:
        return f"{seconds} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


def slugify(value: str, fallback: str = "sessao") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize(value)).strip("-")
    return slug[:48] or fallback


def memory_path(data_dir: Path, record) -> Path:
    dt = parse_iso(record.created_at)
    stamp = dt.strftime("%Y-%m-%d-%H%M") if dt else "sem-data"
    folder = slugify(record.site, "global") if record.site else "global"
    return Path(data_dir) / SESSIONS_DIR / folder / f"{stamp}-{slugify(record.title)}-{record.id}.md"


def doc_path(memory_file) -> Optional[Path]:
    """Documentação gerada por IA fica ao lado da memória: <memória>.doc.md."""
    if not memory_file:
        return None
    path = Path(memory_file)
    return path.with_name(path.name[:-3] + ".doc.md") if path.name.endswith(".md") else path.with_name(path.name + ".doc.md")


def _cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _fence_for(text: str) -> str:
    longest = max((len(m.group(0)) for m in re.finditer(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def _tag_list(ids: Iterable[str], tags: Dict[str, Tag]) -> str:
    names = [f"`{tags[t].name}`" for t in ids if t in tags]
    return " ".join(names)


AGENT_LABELS = {"claude": "Claude Code", "codex": "Codex"}
PUBLISH_LABELS = {"none": "sem commit", "committed": "commit feito, falta o push", "pushed": "push feito",
                  "pr_open": "PR aberto"}
MAX_AGENT_FILES = 15


def agent_lines(agents) -> List[str]:
    """Resumo de cada sessão de agente pareada com a aba, igual na memória e no texto para a IA."""
    lines: List[str] = []
    for s in agents:
        root = (s.project_root or s.cwd or "").rstrip("/") + "/"
        edited = [f.path[len(root):] if f.path.startswith(root) else f.path for f in s.files if f.kind != "read"]
        tests = sum(1 for c in s.commands if c.kind == "test")
        lines += [f"### {AGENT_LABELS.get(s.agent, s.agent)} · `{s.id}`", ""]
        if s.first_user_message:
            lines.append(f"- Pedido: {' '.join(s.first_user_message.split())[:300]}")
        lines.append(f"- Branch: {s.git_branch or 'não informado'} · modelo {s.model or 'não informado'} · "
                     f"{s.turns} {'pedido' if s.turns == 1 else 'pedidos'}")
        lines.append(f"- Publicação: {PUBLISH_LABELS.get(s.published, s.published)}")
        if edited:
            shown = ", ".join(f"`{p}`" for p in edited[:MAX_AGENT_FILES])
            lines.append(f"- Arquivos editados ({len(edited)}): {shown}{' e outros' if len(edited) > MAX_AGENT_FILES else ''}")
        else:
            lines.append("- Arquivos editados: nenhum")
        lines.append(f"- Comandos: {s.commands_total}{f' (testes: {tests})' if tests else ''}")
        if s.loop_alert:
            lines.append(f"- Possível loop: `{s.loop_alert['command']}` rodou {s.loop_alert['count']} vezes sem commit")
        lines.append("")
    return lines


def render_session_md(record, tasks: List[Task], notes: List[Note], tags: Dict[str, Tag],
                      transcript: str, truncated: bool = False, agents=None) -> str:
    status = ("aberta" if record.is_open else
              f"encerrada{f' (código {record.exit_code})' if record.exit_code is not None else ''}")
    lines = [
        f"# Sessão: {record.title or record.id}",
        "",
        "> Memória gerada pelo Vulcan Celox. Tarefas, post-its e tags continuam editáveis no app; "
        "este arquivo é regravado quando eles mudam.",
        "",
        "| Campo | Valor |",
        "|---|---|",
        f"| Site | {_cell(record.site or 'Global')} |",
        f"| Pasta | `{_cell(record.cwd)}` |",
        f"| Início | {format_when(record.created_at)} |",
        f"| Fim | {format_when(record.closed_at) if record.closed_at else '-'} |",
        f"| Duração | {format_duration(record.created_at, record.closed_at)} |",
        f"| Estado | {status} |",
        f"| Sessão | `{record.id}` |",
        "",
        "## Tags",
        "",
        _tag_list(record.tags, tags) or "_Nenhuma._",
        "",
    ]

    done = sum(1 for t in tasks if t.status == "done")
    lines += [f"## Tarefas ({done}/{len(tasks)})", ""]
    if not tasks:
        lines += ["_Nenhuma tarefa nesta sessão._", ""]
    else:
        order = {"doing": 0, "todo": 1, "done": 2}
        for task in sorted(tasks, key=lambda t: (order.get(t.status, 1), t.priority, t.due or "9999", t.title.casefold())):
            extra = [PRIORITY_LABELS.get(task.priority, "")]
            if task.status == "doing":
                extra.append("em andamento")
            if task.assignee:
                extra.append(f"responsável {task.assignee}")
            if task.due:
                extra.append(f"prazo {task.due}")
            if task.done_at:
                extra.append(f"concluída em {task.done_at[:10]}")
            tag_text = _tag_list(task.tags, tags)
            lines.append(f"- [{'x' if task.status == 'done' else ' '}] {task.title} · {' · '.join(extra)}"
                         f"{f' · {tag_text}' if tag_text else ''}")
        lines.append("")

    lines += [f"## Post-its ({len(notes)})", ""]
    if not notes:
        lines += ["_Nenhum post-it nesta sessão._", ""]
    else:
        for note in sorted(notes, key=lambda n: (not n.pinned, n.order, n.created_at)):
            title = note.title or "(sem título)"
            tag_text = _tag_list(note.tags, tags)
            lines.append(f"### {title}{' (fixado)' if note.pinned else ''}")
            lines.append("")
            body = note.text.strip().splitlines()[1:] if note.text.strip() else []
            for row in body:
                lines.append(f"> {row}" if row.strip() else ">")
            if body:
                lines.append("")
            if tag_text:
                lines += [f"Tags: {tag_text}", ""]

    commands = record.commands
    if agents:
        lines += [f"## Sessões de agente ({len(agents)})", ""] + agent_lines(agents)
    lines += [f"## Comandos executados ({len(commands)})", ""]
    if not commands:
        lines += ["_Nenhum comando digitado registrado._", ""]
    else:
        lines += ["| Hora (UTC) | Comando |", "|---|---|"]
        for item in commands:
            dt = parse_iso(item.get("ts"))
            cmd = _cell(item.get("cmd", ""))
            code = f"`` {cmd} ``" if "`" in cmd else f"`{cmd}`"
            lines.append(f"| {dt.strftime('%H:%M:%S') if dt else '-'} | {code} |")
        lines.append("")

    lines += ["## Registro do terminal", "", TRANSCRIPT_START]
    if truncated:
        lines += [f"_Mostrando as últimas {MAX_TRANSCRIPT_LINES} linhas._", ""]
    if transcript:
        fence = _fence_for(transcript)
        lines += [f"{fence}text", transcript, fence]
    else:
        lines.append("_Sem saída registrada._")
    lines += [TRANSCRIPT_END, ""]
    return "\n".join(lines)


# ── índice geral ─────────────────────────────────────────────────────────────
GENERAL_INDEX_FILENAME = "INDICE.md"
GENERAL_DOC_FILENAME = "DOCUMENTACAO.md"


def _relative_link(path: Optional[str], data_dir: Path) -> Optional[str]:
    if not path:
        return None
    try:
        rel = Path(path).resolve().relative_to(Path(data_dir).resolve())
    except ValueError:
        return None
    return "/".join(rel.parts).replace(" ", "%20")


def render_general_index(records, tasks: List[Task], notes: List[Note], tags: Dict[str, Tag],
                         data_dir: Path, agents_by_tab: Optional[Dict[str, List[str]]] = None) -> str:
    from vulcan_terminal.core.markdown_index import INDEX_FILENAME, anchor
    from vulcan_terminal.core.progress import progress

    records = list(records)
    by_session_tasks: Dict[str, List[Task]] = {}
    by_session_notes: Dict[str, int] = {}
    for task in tasks:
        if task.terminal:
            by_session_tasks.setdefault(task.terminal, []).append(task)
    for note in notes:
        if note.terminal:
            by_session_notes[note.terminal] = by_session_notes.get(note.terminal, 0) + 1

    open_count = sum(1 for r in records if r.is_open)
    linked_tasks = [t for t in tasks if t.terminal]
    lines = [
        "# Índice geral",
        "",
        "> Gerado automaticamente pelo Vulcan Celox. Reúne a memória de cada sessão de terminal "
        "(o que foi executado, tarefas, post-its e tags) e o índice de tarefas dos projetos.",
        "",
        f"- [Tarefas de todos os projetos]({INDEX_FILENAME})",
        *([f"- [Documentação dos projetos (gerada por IA)]({GENERAL_DOC_FILENAME})"]
          if (Path(data_dir) / GENERAL_DOC_FILENAME).is_file() else []),
        f"- Sessões: {len(records)} ({open_count} {'aberta' if open_count == 1 else 'abertas'}, "
        f"{len(records) - open_count} {'encerrada' if len(records) - open_count == 1 else 'encerradas'})",
        f"- Tarefas vinculadas a sessões: {progress(linked_tasks).label}",
        f"- Post-its vinculados a sessões: {sum(by_session_notes.values())}",
        "",
    ]
    groups: Dict[Optional[str], list] = {}
    for record in records:
        groups.setdefault(record.site, []).append(record)
    order = sorted(groups, key=lambda k: (k is not None, (k or "").casefold()))

    lines += ["## Sumário", ""]
    if not order:
        lines += ["_Nenhuma sessão de terminal ainda._", ""]
        return "\n".join(lines).rstrip("\n") + "\n"
    for key in order:
        label = key or "Global"
        count = len(groups[key])
        lines.append(f"- [{label}](#{anchor(label)}) · {count} {'sessão' if count == 1 else 'sessões'}")
    lines.append("")

    for key in order:
        lines += [f"## {key or 'Global'}", "",
                  "| Data | Sessão | Duração | Comandos | Agente | Tarefas | Post-its | Tags | Documentação |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for record in sorted(groups[key], key=lambda r: r.created_at, reverse=True):
            dt = parse_iso(record.created_at)
            title = _cell(record.title or record.id) + (" (aberta)" if record.is_open else "")
            link = _relative_link(record.memory_file, data_dir)
            session_cell = f"[{title}]({link})" if link else title
            p = progress(by_session_tasks.get(record.id, []))
            task_cell = f"{p.done}/{p.total}" if p.total else "-"
            doc = doc_path(record.memory_file)
            doc_link = _relative_link(str(doc), data_dir) if doc and doc.is_file() else None
            lines.append(
                f"| {dt.strftime('%Y-%m-%d %H:%M') if dt else '-'} | {session_cell} | "
                f"{format_duration(record.created_at, record.closed_at)} | {len(record.commands)} | "
                f"{', '.join(sorted(set((agents_by_tab or {}).get(record.id, [])))) or '-'} | {task_cell} | "
                f"{by_session_notes.get(record.id, 0)} | {_tag_list(record.tags, tags) or '-'} | "
                f"{f'[documentação]({doc_link})' if doc_link else '-'} |")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
