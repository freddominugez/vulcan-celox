"""Builds what goes to the AI: documentation of a session and general documentation. Everything goes through `redact` at the end."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from vulcan_celox.core.i18n import tr
from vulcan_celox.core.models import Note, Tag, Task
from vulcan_celox.core.redact import masked_count, redact
from vulcan_celox.core.session_memory import agent_lines, format_duration, format_when

TRANSCRIPT_LIMIT = 60_000
GENERAL_BUDGET = 120_000
STATUS = {"todo": "a fazer", "doing": "fazendo", "done": "feita"}

STYLE = (
    "Escreva em português do Brasil, em Markdown, com frases diretas. Nunca use travessão (o caractere —); "
    "use vírgula, dois-pontos ou parênteses. Baseie-se só no material fornecido: não invente comandos, arquivos ou "
    "resultados. Trechos marcados como [segredo] ou [chave privada removida] foram mascarados de propósito: "
    "mantenha a marcação e nunca tente reconstruir o valor."
)

SESSION_SYSTEM = STYLE + """

Você documenta uma sessão de terminal de um desenvolvedor PHP/Laravel. Produza exatamente estas seções:
# <título curto que descreve o trabalho>
## Resumo
(2 a 4 frases: objetivo e resultado)
## O que foi feito
(passos numerados na ordem em que aconteceram, com os comandos relevantes em blocos de código)
## Comandos principais
(tabela: Comando | Para que serve)
## Problemas e soluções
(erros ou avisos vistos na saída e como foram resolvidos; diga quando ficaram pendentes; escreva "Nenhum problema registrado." se não houver)
## Tarefas e anotações
(estado das tarefas e o essencial dos post-its)
## Próximos passos
(lista curta, a partir de tarefas abertas e do que ficou pendente)"""

GENERAL_SYSTEM = STYLE + """

Você escreve a documentação geral dos projetos locais de um desenvolvedor a partir das sessões de terminal abaixo.
Produza:
# Documentação dos projetos
(um parágrafo de visão geral)
Depois, uma seção `## <site>` por site (Global por último), cada uma com:
### Visão geral
### Linha do tempo
(tabela: Data | Sessão | O que foi feito; a coluna Sessão é um link Markdown para o arquivo indicado em "arquivo")
### Decisões e aprendizados
### Pendências
(tarefas abertas e problemas não resolvidos)
### Comandos recorrentes
Use os links exatamente como fornecidos. Sessões listadas sem detalhes entram só na linha do tempo."""


@dataclass
class Prompt:
    system: str
    user: str
    redactions: int
    truncated: bool = False
    stats: Dict[str, int] = field(default_factory=dict)

    @property
    def chars(self) -> int:
        return len(self.system) + len(self.user)


def _home_relative(path: str) -> str:
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if home and home != "/" and path.startswith(home) else path


def _items_block(tasks: List[Task], notes: List[Note], tags: Dict[str, Tag], note_limit: int = 2000) -> List[str]:
    lines = ["## Tarefas"]
    lines += [f"- [{STATUS.get(t.status, t.status)}] {t.title}"
              + (f" (responsável {t.assignee})" if t.assignee else "")
              + (f" (prazo {t.due})" if t.due else "")
              + (f" tags: {', '.join(tags[x].name for x in t.tags if x in tags)}" if t.tags else "") for t in tasks] or ["- nenhuma"]
    lines += ["", "## Post-its"]
    lines += [f"- {redact(n.text.strip())[0][:note_limit]}" for n in notes if n.text.strip()] or ["- nenhum"]
    return lines


def session_doc_prompt(record, tasks: List[Task], notes: List[Note], tags: Dict[str, Tag], transcript: str,
                       limit: int = TRANSCRIPT_LIMIT, agents=None) -> Prompt:
    # mask before truncating: a secret cut in half would lose the prefix that the mask recognizes
    transcript, _ = redact(transcript)
    truncated = len(transcript) > limit
    tail = transcript[-limit:] if truncated else transcript
    commands = record.commands[-300:]
    lines = [
        f"# Sessão: {record.title}",
        f"- Site: {record.site or 'Global'}",
        f"- Pasta: {_home_relative(record.cwd or '')}",
        f"- Início: {format_when(record.created_at)}",
        f"- Duração: {format_duration(record.created_at, record.closed_at)}",
        f"- Estado: {'aberta' if record.is_open else 'encerrada'}"
        + (f" (código de saída {record.exit_code})" if record.exit_code is not None else ""),
        f"- Tags da sessão: {', '.join(tags[t].name for t in record.tags if t in tags) or 'nenhuma'}",
        "",
        *_items_block(tasks, notes, tags),
        "",
        *([f"## Sessões de agente nesta aba ({len(agents)})", "", *agent_lines(agents)] if agents else []),
        f"## Comandos digitados ({len(record.commands)}{', últimos 300' if len(record.commands) > 300 else ''})",
        *[f"- {format_when(c.get('ts'))} `{c['cmd']}`" for c in commands],
        "",
        "## Saída do terminal" + (f" (últimos {limit} caracteres)" if truncated else ""),
        "```text",
        tail.replace("```", "ˋˋˋ"),
        "```",
    ]
    user, _ = redact("\n".join(lines))
    # counts the whole record, including what was cut, whether it was masked now or when the memory was saved
    count = masked_count(user) - masked_count(tail) + masked_count(transcript)
    return Prompt(tr(SESSION_SYSTEM), user, count, truncated,
                  {"commands": len(record.commands), "tasks": len(tasks), "notes": len(notes), "transcript": len(tail)})


@dataclass
class SessionEntry:
    record: object
    tasks: List[Task]
    notes: List[Note]
    link: str
    doc_text: Optional[str] = None


def general_doc_prompt(entries: List[SessionEntry], tags: Dict[str, Tag], budget: int = GENERAL_BUDGET) -> Prompt:
    """Sessions from newest to oldest; when the budget runs out, the rest go with just one line."""
    parts: List[str] = []
    brief: List[str] = []
    used = 0
    detailed = 0
    for entry in entries:
        r = entry.record
        head = (f"### {r.title}\n- site: {r.site or 'Global'}\n- data: {format_when(r.created_at)}\n"
                f"- duração: {format_duration(r.created_at, r.closed_at)}\n- arquivo: {entry.link}\n")
        if entry.doc_text:
            body = "Documentação da sessão:\n" + redact(entry.doc_text.strip())[0][:4000]
        else:
            cmds = "\n".join(f"- `{c['cmd']}`" for c in r.commands[-40:]) or "- nenhum"
            body = "\n".join(_items_block(entry.tasks, entry.notes, tags, note_limit=300)) + f"\n## Comandos\n{cmds}"
        block = f"{head}{body}\n"
        if used + len(block) <= budget:
            parts.append(block)
            used += len(block)
            detailed += 1
        else:
            brief.append(f"- {format_when(r.created_at)} · {r.site or 'Global'} · [{r.title}]({entry.link})")
    text = "# Sessões\n\n" + "\n".join(parts)
    if brief:
        text += "\n# Sessões sem detalhes (orçamento de contexto)\n" + "\n".join(brief)
    user, count = redact(text)
    return Prompt(tr(GENERAL_SYSTEM), user, count, bool(brief), {"sessions": len(entries), "detailed": detailed})


def relative_link(path: Optional[str], data_dir: Path) -> str:
    if not path:
        return ""
    try:
        return Path(path).resolve().relative_to(Path(data_dir).resolve()).as_posix()
    except ValueError:
        return Path(path).name
