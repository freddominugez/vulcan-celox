"""Per-button prompts: Markdown files with a header, global and per project, with session variables.

Global ones in <data>/prompts/, the project's in <project>/.vulcan/prompts/ (always read; the folder is only created with
user confirmation). The project's overrides the global one by `id`. Category from the `category` field or the
subfolder. `{{nome}}` variables without logic; a missing one stays as is and is listed in `missing`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from vulcan_celox.core.agents import rules
from vulcan_celox.core.agents.model import AgentSession
from vulcan_celox.core.agents.repos import SAFE_GIT
from vulcan_celox.core.i18n import tr
from vulcan_celox.core.miniyaml import MiniYamlError, loads
from vulcan_celox.core.store import make_private

DEFAULT_CATEGORIES = ["Comportamento", "Parâmetros", "Segurança", "Publicação", "Testes"]
FALLBACK_CATEGORY = "Outros"
NAME_FILE = ".nome"  # display name of a user-created category (the folder is just the slug)
VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
VARIABLES = ("projectName", "branch", "base", "sessionId", "agent", "cwd")
# readable label of each variable: shown on cards and composer fields, never {{nome}}
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
    description: str = ""  # `descricao` header field; empty = first sentence of the text (see summary)
    icon: str = ""          # `icone` field: name of an interface icon; empty or unknown = default icon

    def to_dict(self) -> Dict:
        return {"id": self.id, "title": self.title, "category": self.category, "scope": self.scope,
                "body": self.body, "path": str(self.path), "pin": self.pin, "overrides": self.overrides,
                "description": self.description, "icon": self.icon, "variables": variables_in(self.body)}


NEW_PROMPT_TEXT = ("Escreva aqui o texto que vai para o terminal. Variáveis preenchidas pela sessão atual: "
                   "{{projectName}}, {{branch}}, {{base}}, {{sessionId}}, {{agent}} e {{cwd}}.\n")


def default_categories() -> List[str]:
    """Default categories in the current language (the example folders are born with these names)."""
    return [tr(c) for c in DEFAULT_CATEGORIES]


def label_names() -> Dict[str, str]:
    return {k: tr(v) for k, v in LABELS.items()}


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
    """Categories that exist as a folder (including empty ones), by display name."""
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(_category_name(d) for d in root.iterdir() if d.is_dir() and not d.name.startswith("."))


def parse_file(path: Path, scope: str, default_category: str) -> Tuple[Optional[Prompt], Optional[str]]:
    """(prompt, warning). An invalid or unterminated header: the file is ignored and the warning is returned."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, tr("{name}: não deu para ler ({kind})", name=path.name, kind=exc.__class__.__name__)
    meta: Dict = {}
    body = text
    normalized = text.replace("\r\n", "\n")
    if normalized.startswith("---\n"):
        end = normalized.find("\n---", 3)
        if end < 0:
            return None, tr("{name}: cabeçalho sem a linha --- de fechamento", name=path.name)
        try:
            meta = loads(normalized[4:end]) or {}
        except MiniYamlError as exc:
            return None, tr("{name}: cabeçalho inválido ({exc})", name=path.name, exc=tr(str(exc)))
        if not isinstance(meta, dict):
            return None, tr("{name}: cabeçalho não é um mapa", name=path.name)
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
    """Global and project prompts together; the project's overrides the global one with the same id."""
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
    """Variables used in the text, in order of appearance, without repeats."""
    seen: List[str] = []
    for match in VAR.finditer(body or ""):
        if match.group(1) not in seen:
            seen.append(match.group(1))
    return seen


def summary(prompt: Prompt, context: Dict[str, str]) -> str:
    """What the card says the prompt does: the header's `descricao` or the first sentence of the text, with
        variables replaced by the session value or by an ellipsis when missing (never `{{nome}}`)."""
    text = prompt.description or ""
    if not text:
        flat = " ".join((prompt.body or "").split())
        end = re.search(r"[.!?:](\s|$)", flat)
        text = flat[:end.start() + 1] if end else flat
    text = VAR.sub(lambda m: str(context.get(m.group(1)) or "…"), text).replace("….", "…")
    return text if len(text) <= DESCRIPTION_MAX else text[:DESCRIPTION_MAX - 1].rstrip() + "…"


# ── sending to the terminal ───────────────────────────────────────────
PASTE_START, PASTE_END = b"\x1b[200~", b"\x1b[201~"
VALUE_MAX = 2000
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # tudo de controle, menos \t e \n


def clean(text: str) -> str:
    """No ESC or other control character: nothing in the text closes the paste or becomes a key in the terminal."""
    return _CONTROL.sub("", (text or "").replace("\r\n", "\n").replace("\r", "\n"))


def paste_bytes(body: str, context: Dict[str, str], values: Dict[str, str]) -> Tuple[bytes, List[str]]:
    """Prompt text as a paste (bracketed paste), without Enter: the agent receives the text in its input field and the
        user reviews and sends it. Field values take priority over the session. Returns (bytes, missing variables)."""
    flat = lambda v: " ".join(clean(str(v)).split())  # noqa: E731  one line, no control characters
    merged = {k: flat(v) for k, v in context.items() if v is not None}  # folder and branch come from the JSONL and from git
    merged.update({k: flat(v) for k, v in values.items() if v and v.strip()})
    text, missing = render(clean(body).strip(), merged)
    return PASTE_START + text.encode("utf-8") + PASTE_END, missing


# ── current session and context ────────────────────────────────────────────
AGENT_LABELS = {"claude": "Claude Code", "codex": "Codex"}
GIT_TIMEOUT = 5.0


def choose_current(sessions: Sequence[AgentSession], chosen_id: Optional[str]) -> Optional[AgentSession]:
    """The one chosen by the user; otherwise the most recent active one; otherwise the most recent (list already sorted)."""
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
    """Prompt variables. Read-only git only: branch (when the JSONL does not bring it) and the remote's default branch."""
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


# ── writing (only in the prompts folder) ────────────────────────────────────
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
    """Header value in single quotes: ` #` does not become a comment and `: ` does not break the parsing."""
    return "'" + value.replace("'", "''") + "'"


def create_prompt(root, title: str, category: str, body: Optional[str] = None) -> Path:
    """New file from a template, in the category subfolder. Never overwrites: appends -2, -3."""
    title = " ".join((title or "").split()) or tr("Novo prompt")
    category = " ".join((category or "").split()) or FALLBACK_CATEGORY  # one line: does not inject a key into the header
    folder = create_category(root, category)
    path = _free_path(folder, slugify(title))
    text = body if body is not None else (
        tr(NEW_PROMPT_TEXT))
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


def _in(language: str, text: str) -> str:
    """Text of an example in a given language, whatever the current one is."""
    from vulcan_celox.core import i18n
    return text if language == "pt" else i18n.dictionary().get(text, text)


def _example(example, language: str) -> Tuple[str, str]:
    """(category, file text) of an example exactly as seed_global writes it in that language."""
    category, pid, title, pin, body = example
    category, title, body = _in(language, category), _in(language, title), _in(language, body)
    return category, (f"---\nid: {pid}\ntitle: {title}\ncategory: {category}\npin: {'true' if pin else 'false'}\n---\n"
                      f"{body}\n")


def seed_global(root) -> List[Path]:
    """Creates the examples on first run. If the folder already exists, it touches nothing."""
    root = Path(root)
    if root.exists():
        return []
    from vulcan_celox.core import i18n
    created = []
    for example in EXAMPLES:
        category, text = _example(example, i18n.language())
        folder = create_category(root, category)
        path = folder / f"{example[1]}.md"
        path.write_text(text, encoding="utf-8")
        make_private(path)
        created.append(path)
    return created


def _same(path: Path, text: str) -> bool:
    try:
        return path.is_file() and not path.is_symlink() and path.read_text(encoding="utf-8") == text
    except (OSError, UnicodeDecodeError):
        return False


def follow_language(root) -> List[Path]:
    """The examples nobody edited (same text as seed_global wrote in the other language) move to the current language,
    in place. An edited example stays as it is. Returns what was rewritten."""
    from vulcan_celox.core import i18n
    root = Path(root)
    current = i18n.language()
    changed = []
    for language in (lang for lang in i18n.LANGUAGES if lang != current):
        for example in EXAMPLES:
            old_category, old_text = _example(example, language)
            new_category, new_text = _example(example, current)
            # the folder keeps the name of the language the examples were born in
            path = next((c for c in sorted(root.glob(f"*/{example[1]}.md")) if _same(c, old_text)), None)
            if path is None or old_text == new_text:
                continue
            path.write_text(new_text, encoding="utf-8")
            make_private(path)
            name = path.parent / NAME_FILE
            if _category_name(path.parent) == old_category and not name.is_symlink():
                name.write_text(new_category + "\n", encoding="utf-8")
                make_private(name)
            changed.append(path)
    return changed
