"""Prompts por botão (vt-17): arquivos Markdown com cabeçalho, globais e por projeto, com variáveis da sessão.

Globais em <dados>/prompts/, do projeto em <projeto>/.vulcan/prompts/ (lidos sempre; a pasta só é criada com
confirmação do usuário). O do projeto sobrescreve o global pelo `id`. Categoria pelo campo `category` ou pela
subpasta. Variáveis `{{nome}}` sem lógica; a ausente fica como está e é listada em `missing`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from vulcan_terminal.core.agents import rules
from vulcan_terminal.core.agents.model import AgentSession
from vulcan_terminal.core.agents.repos import SAFE_GIT
from vulcan_terminal.core.miniyaml import MiniYamlError, loads
from vulcan_terminal.core.store import make_private

DEFAULT_CATEGORIES = ["Comportamento", "Parâmetros", "Segurança", "Publicação", "Testes"]
FALLBACK_CATEGORY = "Outros"
NAME_FILE = ".nome"  # nome de exibição de uma categoria criada pelo usuário (a pasta é só o slug)
VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
VARIABLES = ("projectName", "branch", "base", "sessionId", "agent", "cwd")
# rótulo legível de cada variável (vt-27): aparece nos cartões e nos campos do compositor, nunca o {{nome}}
LABELS = {"projectName": "Projeto", "branch": "Branch", "base": "Base", "sessionId": "Sessão", "agent": "Agente",
          "cwd": "Pasta"}
ICON_NAME = re.compile(r"^[a-z][a-z-]{0,23}$")
DESCRIPTION_MAX = 160


@dataclass
class Prompt:
    id: str
    title: str
    category: str
    scope: str            # "global" ou "project"
    body: str
    path: Path
    pin: bool = False
    overrides: bool = False
    description: str = ""  # campo `descricao` do cabeçalho; vazio = primeira frase do texto (ver summary)
    icon: str = ""          # campo `icone`: nome de um ícone da interface; vazio ou desconhecido = ícone padrão

    def to_dict(self) -> Dict:
        return {"id": self.id, "title": self.title, "category": self.category, "scope": self.scope,
                "body": self.body, "path": str(self.path), "pin": self.pin, "overrides": self.overrides,
                "description": self.description, "icon": self.icon, "variables": variables_in(self.body)}


def slugify(text: str, fallback: str = "prompt") -> str:
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    return slug[:60].strip("-") or fallback


def _humanize(stem: str) -> str:
    words = stem.replace("_", " ").replace("-", " ").strip()
    return (words[:1].upper() + words[1:]) if words else stem


def project_dir(project_root) -> Path:
    return Path(project_root) / ".vulcan" / "prompts"


# ── leitura ─────────────────────────────────────────────────────────────────
def _category_name(folder: Path) -> str:
    try:
        name = (folder / NAME_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        name = ""
    return name or folder.name


def categories(root: Path) -> List[str]:
    """Categorias que existem como pasta (inclusive vazias), pelo nome de exibição."""
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(_category_name(d) for d in root.iterdir() if d.is_dir() and not d.name.startswith("."))


def parse_file(path: Path, scope: str, default_category: str) -> Tuple[Optional[Prompt], Optional[str]]:
    """(prompt, aviso). Cabeçalho inválido ou sem fim: o arquivo é ignorado e devolve o aviso."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{path.name}: não deu para ler ({exc.__class__.__name__})"
    meta: Dict = {}
    body = text
    normalized = text.replace("\r\n", "\n")
    if normalized.startswith("---\n"):
        end = normalized.find("\n---", 3)
        if end < 0:
            return None, f"{path.name}: cabeçalho sem a linha --- de fechamento"
        try:
            meta = loads(normalized[4:end]) or {}
        except MiniYamlError as exc:
            return None, f"{path.name}: cabeçalho inválido ({exc})"
        if not isinstance(meta, dict):
            return None, f"{path.name}: cabeçalho não é um mapa"
        body = normalized[end + 4:].lstrip("\n")
    pid = str(meta.get("id") or path.stem).strip()
    title = str(meta.get("title") or _humanize(path.stem)).strip()
    category = str(meta.get("category") or default_category).strip() or FALLBACK_CATEGORY
    description = " ".join(str(meta.get("descricao") or meta.get("description") or "").split())[:DESCRIPTION_MAX]
    icon = str(meta.get("icone") or meta.get("icon") or "").strip()
    return Prompt(pid, title, category, scope, body.rstrip() + "\n", path, pin=meta.get("pin") is True,
                  description=description, icon=icon if ICON_NAME.match(icon) else ""), None


def load_dir(root, scope: str) -> Tuple[List[Prompt], List[str]]:
    root = Path(root)
    found: List[Prompt] = []
    warnings: List[str] = []
    if not root.is_dir():
        return found, warnings
    files = [(p, FALLBACK_CATEGORY) for p in sorted(root.glob("*.md"))]
    for folder in sorted(d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")):
        files += [(p, _category_name(folder)) for p in sorted(folder.glob("*.md"))]
    for path, default in files:
        prompt, warning = parse_file(path, scope, default)
        if warning:
            warnings.append(warning)
        elif prompt:
            found.append(prompt)
    return found, warnings


def load_all(global_dir, project_prompts: Optional[Path] = None) -> Tuple[List[Prompt], List[str]]:
    """Globais e do projeto juntos; o do projeto sobrescreve o global de mesmo id."""
    merged, warnings = load_dir(global_dir, "global")
    if project_prompts is not None:
        local, local_warnings = load_dir(project_prompts, "project")
        warnings += local_warnings
        by_id = {p.id: i for i, p in enumerate(merged)}
        for prompt in local:
            if prompt.id in by_id:
                prompt.overrides = True
                merged[by_id[prompt.id]] = prompt
            else:
                merged.append(prompt)
    return merged, warnings


def render(body: str, context: Dict[str, str]) -> Tuple[str, List[str]]:
    missing: List[str] = []

    def replace(match):
        name = match.group(1)
        value = context.get(name)
        if value is None or value == "":
            if name not in missing:
                missing.append(name)
            return match.group(0)
        return str(value)

    return VAR.sub(replace, body or ""), missing


def variables_in(body: str) -> List[str]:
    """Variáveis usadas no texto, na ordem em que aparecem, sem repetir."""
    seen: List[str] = []
    for match in VAR.finditer(body or ""):
        if match.group(1) not in seen:
            seen.append(match.group(1))
    return seen


def summary(prompt: Prompt, context: Dict[str, str]) -> str:
    """O que o cartão diz que o prompt faz: a `descricao` do cabeçalho ou a primeira frase do texto, com as
    variáveis trocadas pelo valor da sessão ou por reticências quando falta (nunca `{{nome}}`)."""
    text = prompt.description or ""
    if not text:
        flat = " ".join((prompt.body or "").split())
        end = re.search(r"[.!?:](\s|$)", flat)
        text = flat[:end.start() + 1] if end else flat
    text = VAR.sub(lambda m: str(context.get(m.group(1)) or "…"), text).replace("….", "…")
    return text if len(text) <= DESCRIPTION_MAX else text[:DESCRIPTION_MAX - 1].rstrip() + "…"


# ── envio ao terminal (vt-27 C3) ───────────────────────────────────────────
PASTE_START, PASTE_END = b"\x1b[200~", b"\x1b[201~"
VALUE_MAX = 2000
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # tudo de controle, menos \t e \n


def clean(text: str) -> str:
    """Sem ESC nem outro caractere de controle: nada no texto fecha a colagem ou vira tecla no terminal."""
    return _CONTROL.sub("", (text or "").replace("\r\n", "\n").replace("\r", "\n"))


def paste_bytes(body: str, context: Dict[str, str], values: Dict[str, str]) -> Tuple[bytes, List[str]]:
    """Texto do prompt como colagem (bracketed paste), sem Enter: o agente recebe o texto no campo de entrada e o
    usuário revisa e envia. Valores dos campos têm prioridade sobre a sessão. Devolve (bytes, variáveis faltando)."""
    flat = lambda v: " ".join(clean(str(v)).split())  # noqa: E731  uma linha, sem controle
    merged = {k: flat(v) for k, v in context.items() if v is not None}  # pasta e branch vêm do JSONL e do git
    merged.update({k: flat(v) for k, v in values.items() if v and v.strip()})
    text, missing = render(clean(body).strip(), merged)
    return PASTE_START + text.encode("utf-8") + PASTE_END, missing


# ── sessão atual e contexto ────────────────────────────────────────────────
AGENT_LABELS = {"claude": "Claude Code", "codex": "Codex"}
GIT_TIMEOUT = 5.0


def choose_current(sessions: Sequence[AgentSession], chosen_id: Optional[str]) -> Optional[AgentSession]:
    """A escolhida pelo usuário; senão a ativa mais recente; senão a mais recente (lista já ordenada)."""
    if chosen_id:
        for s in sessions:
            if s.id == chosen_id:
                return s
    for s in sessions:
        if s.is_active:
            return s
    return sessions[0] if sessions else None


def _git(runner, path: str, *args: str) -> Optional[str]:
    result = runner.run([*SAFE_GIT, "-C", path, *args], timeout=GIT_TIMEOUT)
    out = result.stdout.strip() if result.ok else ""
    return out or None


def context_for(session: Optional[AgentSession], runner) -> Dict[str, str]:
    """Variáveis dos prompts. Só git de leitura: branch (quando o JSONL não traz) e o branch padrão do remoto."""
    if session is None:
        return {}
    path = rules.worktree_path(session.cwd) or session.cwd or session.project_root
    branch = session.git_branch
    if not branch and path:
        head = _git(runner, path, "rev-parse", "--abbrev-ref", "HEAD")
        branch = head if head and head != "HEAD" else None
    remote_head = _git(runner, path, "symbolic-ref", "--short", "refs/remotes/origin/HEAD") if path else None
    base = remote_head.split("/", 1)[1] if remote_head and "/" in remote_head else "main"
    ctx = {"sessionId": session.id, "branch": branch, "base": base, "projectName": session.project_name,
           "cwd": session.cwd, "agent": AGENT_LABELS.get(session.agent, session.agent)}
    return {k: v for k, v in ctx.items() if v}


# ── escrita (só na pasta de prompts) ────────────────────────────────────────
def _free_path(folder: Path, stem: str) -> Path:
    path = folder / f"{stem}.md"
    n = 2
    while path.exists():
        path = folder / f"{stem}-{n}.md"
        n += 1
    return path


def create_category(root, name: str) -> Path:
    root = Path(root)
    name = " ".join((name or "").split()) or FALLBACK_CATEGORY
    folder = root / slugify(name, "categoria")
    folder.mkdir(parents=True, exist_ok=True)
    make_private(root)
    make_private(folder)
    if name != folder.name:
        (folder / NAME_FILE).write_text(name + "\n", encoding="utf-8")
        make_private(folder / NAME_FILE)
    return folder


def _quoted(value: str) -> str:
    """Valor do cabeçalho entre aspas simples: ` #` não vira comentário e `: ` não quebra a leitura."""
    return "'" + value.replace("'", "''") + "'"


def create_prompt(root, title: str, category: str, body: Optional[str] = None) -> Path:
    """Novo arquivo a partir de um modelo, na subpasta da categoria. Nunca sobrescreve: acrescenta -2, -3."""
    title = " ".join((title or "").split()) or "Novo prompt"
    category = " ".join((category or "").split()) or FALLBACK_CATEGORY  # uma linha: não injeta chave no cabeçalho
    folder = create_category(root, category)
    path = _free_path(folder, slugify(title))
    text = body if body is not None else (
        "Escreva aqui o texto que vai para o terminal. Variáveis preenchidas pela sessão atual: "
        "{{projectName}}, {{branch}}, {{base}}, {{sessionId}}, {{agent}} e {{cwd}}.\n")
    path.write_text(f"---\nid: {path.stem}\ntitle: {_quoted(title)}\ncategory: {_quoted(category)}\npin: false\n---\n{text}",
                    encoding="utf-8")
    make_private(path)
    return path


EXAMPLES = [
    ("Comportamento", "comportamento", "Comportamento padrão", False,
     "Trabalhe em passos pequenos no projeto {{projectName}}. Antes de editar, leia os arquivos que vai tocar. "
     "Ao terminar cada passo, rode os testes e me diga em uma linha o que mudou. Não altere arquivos fora de {{cwd}}."),
    ("Comportamento", "revisar", "Revisar antes do commit", False,
     "Antes do commit no branch {{branch}}, mostre o diff resumido por arquivo, aponte o que pode quebrar e só então "
     "faça o commit."),
    ("Parâmetros", "limites", "Limites da tarefa", False,
     "Trabalhe só dentro de {{cwd}}. No máximo 5 arquivos por passo. Não instale dependências novas sem me perguntar. "
     "Sessão {{sessionId}}."),
    ("Parâmetros", "formato", "Formato da resposta", False,
     "Responda em português, curto, em tópicos. Sempre termine com: arquivos alterados, testes rodados e próximo passo."),
    ("Segurança", "seguranca", "Regras de segurança do branch", True,
     "Você está no branch {{branch}} do projeto {{projectName}} (sessão {{sessionId}}). Não crie worktree, não troque "
     "de branch e não faça force push. Não apague arquivos; se precisar remover algo, me diga antes. Se precisar de "
     "outro branch, pare e me avise."),
    ("Publicação", "publicar", "Publicar e abrir PR", True,
     "Rode a suíte completa. Se passar, faça commit das mudanças pendentes, push de {{branch}} e abra um PR contra "
     "{{base}} com um resumo do que mudou e como testar. Referência: sessão {{sessionId}} ({{agent}})."),
    ("Publicação", "conciliar", "Conciliar branch e worktree", False,
     "Liste o que está sem commit e sem push em {{branch}} ({{cwd}}). Faça commit do que estiver pronto, push, e me "
     "diga se esta worktree pode ser removida depois do merge em {{base}}. Não remova sem me perguntar."),
    ("Testes", "loop", "Sair do loop de testes", True,
     "Você rodou o mesmo teste várias vezes sem commit no branch {{branch}}. Pare agora. Em três linhas: a hipótese "
     "atual, o que já tentou e o próximo passo diferente. Não rode o teste de novo antes de me mostrar isso."),
]


def seed_global(root) -> List[Path]:
    """Cria os exemplos na primeira execução. Se a pasta já existe, não toca em nada."""
    root = Path(root)
    if root.exists():
        return []
    created = []
    for category, pid, title, pin, body in EXAMPLES:
        folder = create_category(root, category)
        path = folder / f"{pid}.md"
        path.write_text(f"---\nid: {pid}\ntitle: {title}\ncategory: {category}\npin: {'true' if pin else 'false'}\n---\n"
                        f"{body}\n", encoding="utf-8")
        make_private(path)
        created.append(path)
    return created
