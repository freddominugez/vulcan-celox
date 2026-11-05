"""Memory of a terminal session in Markdown: what was run and what was noted."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from vulcan_celox.core.i18n import tr
from vulcan_celox.core.models import PRIORITY_LABELS, Note, Tag, Task
from vulcan_celox.core.redact import redact
from vulcan_celox.core.textutil import normalize

MAX_TRANSCRIPT_LINES = 2000
TRANSCRIPT_START = "<!-- vulcan:registro:inicio -->"
TRANSCRIPT_END = "<!-- vulcan:registro:fim -->"
SESSIONS_DIR = "sessoes"

_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_CSI = re.compile(r"\x1b\[([0-?]*)[ -/]*([@-~])")
_ESC2 = re.compile(r"\x1b[@-Z\\-_]")


# ── registro do terminal ─────────────────────────────────────────────────────
def strip_terminal(data, cols: Optional[int] = None) -> Tuple[str, bool]:
    """Converts the raw PTY output into readable text. Returns (text, truncated).

        Removes colors and control sequences, applies carriage return, backspace and
        line erase the way the terminal would show them. With `cols`, a line longer than the
        width wraps into rows of one logical line, as in the terminal: zsh writes a space and a
        carriage return at the edge to move to the next row, and without the rows the rest of a
        long command overwrote its start.
    """
    text = data.decode("utf-8", errors="replace") if isinstance(data, (bytes, bytearray)) else str(data)
    text = _OSC.sub("", text)
    lines: List[str] = []
    line: List[str] = []
    col = 0
    row = 0  # where the current row starts inside the logical line (0 without `cols`)
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\x1b":
            m = _CSI.match(text, i)
            if m:
                params, final = m.group(1), m.group(2)
                n = int(params) if params.isdigit() else 1
                if final == "K":  # erase to the end of the line (mode 0)
                    if params in ("", "0"):
                        del line[col:]
                    elif params == "2":
                        del line[row:]
                        col = row
                elif final == "J" and params in ("", "0"):
                    del line[col:]
                elif final == "C":
                    col += n
                elif final == "D":
                    col = max(row, col - n)
                elif final == "G":
                    col = row + max(0, n - 1)
                elif final == "A" and cols:  # up, into an earlier row of the same wrapped line
                    up = min(n, row // cols)
                    row -= up * cols
                    col -= up * cols
                i = m.end()
                continue
            m2 = _ESC2.match(text, i)
            i = m2.end() if m2 else i + 1
            continue
        if ch == "\n":
            lines.append("".join(line).rstrip())
            line, col, row = [], 0, 0
        elif ch == "\r":
            col = row
        elif ch == "\b":
            col = max(row, col - 1)
        elif ch == "\t":
            target = row + ((col - row) // 8 + 1) * 8
            while col < target:
                _put(line, col, " ")
                col += 1
        elif ord(ch) >= 0x20:
            if cols and col - row >= cols:  # the cursor waits at the edge; the next character opens a row
                row += cols
                col = max(col, row)
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
    # mask before cutting: a secret cut in half would lose the prefix that the mask recognizes
    compact = redact("\n".join(compact))[0].split("\n")
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
    """Recovers the record of an already saved memory (to regenerate ended sessions)."""
    start = markdown.find(TRANSCRIPT_START)
    end = markdown.find(TRANSCRIPT_END, start + 1)
    if start == -1 or end == -1:
        return "", False
    block = markdown[start + len(TRANSCRIPT_START):end]
    truncated = "_Mostrando as últimas" in block or "_Showing the last" in block
    fence = re.search(r"^(`{3,}|~{3,})text\n(.*?)\n\1$", block, re.S | re.M)
    return (fence.group(2) if fence else ""), truncated


# ── session Markdown ───────────────────────────────────────────────────────
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
        return tr("em andamento")
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
    """AI-generated documentation sits next to the memory: <memory>.doc.md."""
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
                  "pr_open": "PR aberto"}  # tr() goes into the output
MAX_AGENT_FILES = 15


def agent_lines(agents) -> List[str]:
    """Summary of each agent session paired with the tab, the same in the memory and in the text for the AI."""
    lines: List[str] = []
    for s in agents:
        root = (s.project_root or s.cwd or "").rstrip("/") + "/"
        edited = [f.path[len(root):] if f.path.startswith(root) else f.path for f in s.files if f.kind != "read"]
        tests = sum(1 for c in s.commands if c.kind == "test")
        lines += [f"### {AGENT_LABELS.get(s.agent, s.agent)} · `{s.id}`", ""]
        if s.first_user_message:
            lines.append(tr("- Pedido: {request}", request=" ".join(s.first_user_message.split())[:300]))
        lines.append(tr("- Branch: {branch} · modelo {model} · {turns}", branch=s.git_branch or tr("não informado"),
                        model=s.model or tr("não informado"),
                        turns=tr("{n} pedido", n=s.turns) if s.turns == 1 else tr("{n} pedidos", n=s.turns)))
        lines.append(tr("- Publicação: {state}", state=tr(PUBLISH_LABELS.get(s.published, s.published))))
        if edited:
            shown = ", ".join(f"`{p}`" for p in edited[:MAX_AGENT_FILES])
            lines.append(tr("- Arquivos editados ({n}): {shown}", n=len(edited), shown=shown) + (tr(" e outros") if len(edited) > MAX_AGENT_FILES else ""))
        else:
            lines.append(tr("- Arquivos editados: nenhum"))
        lines.append(tr("- Comandos: {n}", n=s.commands_total) + (tr(" (testes: {tests})", tests=tests) if tests else ""))
        if s.loop_alert:
            lines.append(tr("- Possível loop: `{command}` rodou {count} vezes sem commit", command=s.loop_alert["command"], count=s.loop_alert["count"]))
        lines.append("")
    return lines


def render_session_md(record, tasks: List[Task], notes: List[Note], tags: Dict[str, Tag],
                      transcript: str, truncated: bool = False, agents=None) -> str:
    status = (tr("aberta") if record.is_open else tr("encerrada")
              + (tr(" (código {code})", code=record.exit_code) if record.exit_code is not None else ""))
    lines = [
        tr("# Sessão: {title}", title=record.title or record.id),
        "",
        tr("> Memória gerada pelo Vulcan Celox. Tarefas, post-its e tags continuam editáveis no app; este arquivo é regravado quando eles mudam."),
        "",
        tr("| Campo | Valor |"),
        "|---|---|",
        tr("| Site | {site} |", site=_cell(record.site or tr("Global"))),
        tr("| Pasta | `{cwd}` |", cwd=_cell(record.cwd)),
        tr("| Início | {when} |", when=format_when(record.created_at)),
        tr("| Fim | {when} |", when=format_when(record.closed_at) if record.closed_at else "-"),
        tr("| Duração | {duration} |", duration=format_duration(record.created_at, record.closed_at)),
        tr("| Estado | {status} |", status=status),
        tr("| Sessão | `{id}` |", id=record.id),
        "",
        tr("## Tags"),
        "",
        _tag_list(record.tags, tags) or tr("_Nenhuma._"),
        "",
    ]

    done = sum(1 for t in tasks if t.status == "done")
    lines += [tr("## Tarefas ({done}/{total})", done=done, total=len(tasks)), ""]
    if not tasks:
        lines += [tr("_Nenhuma tarefa nesta sessão._"), ""]
    else:
        order = {"doing": 0, "todo": 1, "done": 2}
        for task in sorted(tasks, key=lambda t: (order.get(t.status, 1), t.priority, t.due or "9999", t.title.casefold())):
            extra = [tr(PRIORITY_LABELS.get(task.priority, ""))]
            if task.status == "doing":
                extra.append(tr("em andamento"))
            if task.assignee:
                extra.append(tr("responsável {name}", name=task.assignee))
            if task.due:
                extra.append(tr("prazo {date}", date=task.due))
            if task.done_at:
                extra.append(tr("concluída em {date}", date=task.done_at[:10]))
            tag_text = _tag_list(task.tags, tags)
            lines.append(f"- [{'x' if task.status == 'done' else ' '}] {task.title} · {' · '.join(extra)}"
                         f"{f' · {tag_text}' if tag_text else ''}")
        lines.append("")

    lines += [tr("## Post-its ({n})", n=len(notes)), ""]
    if not notes:
        lines += [tr("_Nenhum post-it nesta sessão._"), ""]
    else:
        for note in sorted(notes, key=lambda n: (not n.pinned, n.order, n.created_at)):
            title = note.title or tr("(sem título)")
            tag_text = _tag_list(note.tags, tags)
            lines.append(f"### {title}" + (tr(" (fixado)") if note.pinned else ""))
            lines.append("")
            body = note.text.strip().splitlines()[1:] if note.text.strip() else []
            for row in body:
                lines.append(f"> {row}" if row.strip() else ">")
            if body:
                lines.append("")
            if tag_text:
                lines += [tr("Tags: {tags}", tags=tag_text), ""]

    commands = record.commands
    if agents:
        lines += [tr("## Sessões de agente ({n})", n=len(agents)), ""] + agent_lines(agents)
    lines += [tr("## Comandos executados ({n})", n=len(commands)), ""]
    if not commands:
        lines += [tr("_Nenhum comando digitado registrado._"), ""]
    else:
        lines += [tr("| Hora (UTC) | Comando |"), "|---|---|"]
        for item in commands:
            dt = parse_iso(item.get("ts"))
            cmd = _cell(item.get("cmd", ""))
            code = f"`` {cmd} ``" if "`" in cmd else f"`{cmd}`"
            lines.append(f"| {dt.strftime('%H:%M:%S') if dt else '-'} | {code} |")
        lines.append("")

    lines += [tr("## Registro do terminal"), "", TRANSCRIPT_START]
    if truncated:
        lines += [tr("_Mostrando as últimas {n} linhas._", n=MAX_TRANSCRIPT_LINES), ""]
    if transcript:
        fence = _fence_for(transcript)
        lines += [f"{fence}text", transcript, fence]
    else:
        lines.append(tr("_Sem saída registrada._"))
    lines += [TRANSCRIPT_END, ""]
    return redact("\n".join(lines))[0]  # also covers an older record brought back from a file saved without the mask


# ── general index ─────────────────────────────────────────────────────────────
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
    from vulcan_celox.core.markdown_index import INDEX_FILENAME, anchor
    from vulcan_celox.core.progress import progress

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
        tr("# Índice geral"),
        "",
        tr("> Gerado automaticamente pelo Vulcan Celox. Reúne a memória de cada sessão de terminal (o que foi executado, tarefas, post-its e tags) e o índice de tarefas dos projetos."),
        "",
        tr("- [Tarefas de todos os projetos]({file})", file=INDEX_FILENAME),
        *([tr("- [Documentação dos projetos (gerada por IA)]({file})", file=GENERAL_DOC_FILENAME)]
          if (Path(data_dir) / GENERAL_DOC_FILENAME).is_file() else []),
        tr("- Sessões: {total} ({open} {open_word}, {closed} {closed_word})", total=len(records), open=open_count,
           open_word=tr("aberta") if open_count == 1 else tr("abertas"), closed=len(records) - open_count,
           closed_word=tr("encerrada") if len(records) - open_count == 1 else tr("encerradas")),
        tr("- Tarefas vinculadas a sessões: {progress}", progress=progress(linked_tasks).label),
        tr("- Post-its vinculados a sessões: {n}", n=sum(by_session_notes.values())),
        "",
    ]
    groups: Dict[Optional[str], list] = {}
    for record in records:
        groups.setdefault(record.site, []).append(record)
    order = sorted(groups, key=lambda k: (k is not None, (k or "").casefold()))

    lines += [tr("## Sumário"), ""]
    if not order:
        lines += [tr("_Nenhuma sessão de terminal ainda._"), ""]
        return "\n".join(lines).rstrip("\n") + "\n"
    for key in order:
        label = key or tr("Global")
        count = len(groups[key])
        lines.append(f"- [{label}](#{anchor(label)}) · " + (tr("{n} sessão", n=count) if count == 1 else tr("{n} sessões", n=count)))
    lines.append("")

    for key in order:
        lines += [f"## {key or tr('Global')}", "",
                  tr("| Data | Sessão | Duração | Comandos | Agente | Tarefas | Post-its | Tags | Documentação |"),
                  "|---|---|---|---|---|---|---|---|---|"]
        for record in sorted(groups[key], key=lambda r: r.created_at, reverse=True):
            dt = parse_iso(record.created_at)
            title = _cell(record.title or record.id) + (tr(" (aberta)") if record.is_open else "")
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
                f"{tr('[documentação]({link})', link=doc_link) if doc_link else '-'} |")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
