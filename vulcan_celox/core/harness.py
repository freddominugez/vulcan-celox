"""Reader for a project's harness. Read-only.

Two formats:
- "repo": this repository's (`.harness/state.json`, `specs/<feature>/contract.md`, `.harness/handoff.md`);
- "minimo": that of Harness Vulcan 3.0.0-rc1 (`.vulcan/state/execution.json`, `.vulcan/tasks/<task_id>.md`,
  `.vulcan/handoff.md`).

An unreadable or corrupted file becomes `estado: ilegivel` with the error, never an empty state. Each file has a limit
of 1 MB. The app never changes an item's status: the project's sensor is what validates.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from vulcan_celox.core.i18n import tr
MAX_FILE = 1024 * 1024
HANDOFF_LINES = 60
REPO_STATE = Path(".harness") / "state.json"
REPO_HANDOFF = Path(".harness") / "handoff.md"
MIN_STATE = Path(".vulcan") / "state" / "execution.json"
MIN_HANDOFF = Path(".vulcan") / "handoff.md"
MIN_TASKS = Path(".vulcan") / "tasks"
TASK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
# item line of the minimal contract: "C1 [verde]  objetivo   sensor: build"
_ITEM_LINE = re.compile(r"^\s*(C\d+)\s*\[(verde|amarela|vermelha)\]\s*(.*?)(?:\s+sensor:\s*(.*))?\s*$", re.I)
_TABLE_ROW = re.compile(r"^\|\s*(C\d+)\s*\|\s*(.+?)\s*\|")
DONE = ("done", "feito", "validated")
RUNNING = ("in_progress", "running", "andamento")
BLOCKED = ("blocked", "bloqueado")
MIN_STATUSES = ("RUNNING", "VERIFIED", "INCOMPLETE", "BLOCKED", "CANCELLED", "REVOKED")


class Unreadable(Exception):
    pass


def _read_text(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise Unreadable(f"{path.name}: {exc.strerror or exc}") from None
    if size > MAX_FILE:
        raise Unreadable(f"{path.name}: maior que 1 MB")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read(MAX_FILE + 1)
    except (OSError, UnicodeDecodeError) as exc:
        raise Unreadable(f"{path.name}: {exc}") from None


def _read_json(path: Path) -> Dict:
    text = _read_text(path)
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise Unreadable(f"{path.name}: JSON inválido ({exc})") from None
    if not isinstance(data, dict):
        raise Unreadable(f"{path.name}: esperado um objeto JSON")
    return data


def _handoff(path: Path) -> Optional[List[str]]:
    if not path.is_file():
        return None
    try:
        return _read_text(path).splitlines()[:HANDOFF_LINES]
    except Unreadable as exc:
        return [tr("(handoff ilegível: {exc})", exc=exc)]


def _state_of(item: Dict) -> str:
    status = str(item.get("status") or "").lower()
    if item.get("validated") is True or status in DONE:
        return "feito"
    if status in BLOCKED or item.get("pending") is True:
        return "bloqueado"
    if status in RUNNING:
        return "andamento"
    return "pendente"


def _items(raw: Any, titles: Dict[str, Dict]) -> List[Dict]:
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        extra = titles.get(item["id"], {})
        cause = item.get("cause") or item.get("blocked_reason")
        if cause is None and item.get("pending") is True:
            cause = tr("pendência registrada")
        out.append({"id": item["id"], "titulo": str(item.get("title") or extra.get("titulo") or ""),
                    "status": str(item.get("status") or ""), "estado": _state_of(item),
                    "validated": item.get("validated") is True, "causa": str(cause) if cause else None,
                    "faixa": extra.get("faixa"), "sensor": extra.get("sensor"),
                    "evidencia": str(item["evidence"]) if item.get("evidence") else None})
    return out


def parse_min_contract(text: str) -> Dict:
    """TAREFA, items (id, band, title, sensor), FORA, ESCRITA, ORÇAMENTO and APROVAÇÃO of the minimal format."""
    out: Dict[str, Any] = {"itens": {}}
    for line in text.splitlines():
        m = _ITEM_LINE.match(line)
        if m:
            out["itens"][m.group(1).upper()] = {"faixa": m.group(2).lower(), "titulo": m.group(3).strip(),
                                                "sensor": (m.group(4) or "").strip() or None}
            continue
        key, _, value = line.partition(":")
        key = key.strip().upper()
        if key in ("TAREFA", "FORA", "ESCRITA", "ORÇAMENTO", "APROVAÇÃO"):
            out[key.lower()] = value.strip()
    return out


def _repo_titles(text: str) -> Dict[str, Dict]:
    """Item titles in the repo's contract.md table (| C1 | **Título.** descrição | sensor |)."""
    out = {}
    for line in text.splitlines():
        m = _TABLE_ROW.match(line)
        if m:
            title = re.sub(r"\*\*(.+?)\*\*.*", r"\1", m.group(2)).strip().rstrip(".")
            out[m.group(1)] = {"titulo": title[:160]}
    return out


def _inside(root: Path, rel: str) -> Optional[Path]:
    """Relative path of the state inside the project folder; outside it, None."""
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute():
        return None
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def detect(root) -> str:
    root = Path(root)
    if (root / REPO_STATE).exists() or (root / ".harness").is_dir():
        return "repo"
    if (root / MIN_STATE).exists() or (root / ".vulcan").is_dir():
        return "minimo"
    return "nenhum"


def read(root) -> Dict[str, Any]:
    root = Path(root)
    kind = detect(root)
    base: Dict[str, Any] = {"tipo": kind, "estado": "nenhum", "erro": None, "contrato": None, "itens": [],
                            "proximo": None, "ultimo_commit_verde": None, "handoff": None, "fila": [],
                            "status": None}
    if kind == "nenhum":
        return base
    try:
        if kind == "repo":
            base.update(_read_repo(root))
        else:
            base.update(_read_min(root))
        base["estado"] = "ok"
    except Unreadable as exc:
        base.update(estado="ilegivel", erro=tr(str(exc)))
    return base


def _read_repo(root: Path) -> Dict:
    state_path = root / REPO_STATE
    if not state_path.exists():
        raise Unreadable(".harness/state.json não existe")
    state = _read_json(state_path)
    contract_rel = state.get("contract")
    titles: Dict[str, Dict] = {}
    contract = None
    if isinstance(contract_rel, str) and contract_rel:
        path = _inside(root, contract_rel)
        contract = {"id": state.get("feature"), "caminho": contract_rel, "existe": bool(path and path.is_file())}
        if path and path.is_file():
            try:
                titles = _repo_titles(_read_text(path))
            except Unreadable:
                titles = {}
    queue = [q for q in state.get("queue") or [] if isinstance(q, str)]
    done = [c for c in state.get("completed") or [] if isinstance(c, str)]
    return {"contrato": contract, "itens": _items(state.get("items"), titles),
            "proximo": state.get("next") if isinstance(state.get("next"), str) else None,
            "ultimo_commit_verde": state.get("last_green_commit") if isinstance(state.get("last_green_commit"), str)
            else None, "handoff": _handoff(root / REPO_HANDOFF), "fila": queue, "concluidos": len(done)}


def _read_min(root: Path) -> Dict:
    state_path = root / MIN_STATE
    if not state_path.exists():
        raise Unreadable(".vulcan/state/execution.json não existe")
    state = _read_json(state_path)
    task_id = state.get("task_id") if isinstance(state.get("task_id"), str) else None
    contract = None
    parsed: Dict[str, Any] = {"itens": {}}
    if task_id and TASK_ID.match(task_id):
        rel = (MIN_TASKS / f"{task_id}.md").as_posix()
        path = root / rel
        contract = {"id": task_id, "caminho": rel, "existe": path.is_file()}
        if path.is_file():
            try:
                parsed = parse_min_contract(_read_text(path))
                contract["aprovacao"] = parsed.get("aprovação")
            except Unreadable:
                pass
    status = state.get("status") if state.get("status") in MIN_STATUSES else None
    items = _items(state.get("items"), parsed["itens"])
    known = {i["id"] for i in items}
    for cid, info in parsed["itens"].items():  # contract item the state has not cited yet: pending
        if cid not in known:
            items.append({"id": cid, "titulo": info["titulo"], "status": "", "estado": "pendente",
                          "validated": False, "causa": None, "faixa": info["faixa"], "sensor": info["sensor"],
                          "evidencia": None})
    items.sort(key=lambda i: int(i["id"][1:]) if i["id"][1:].isdigit() else 0)
    return {"contrato": contract, "itens": items, "status": status,
            "proximo": state.get("next") if isinstance(state.get("next"), str) else None,
            "ultimo_commit_verde": state.get("last_green_commit")
            if isinstance(state.get("last_green_commit"), str) else None,
            "handoff": _handoff(root / MIN_HANDOFF), "fila": [],
            "bloqueio": state.get("blocked_reason") if isinstance(state.get("blocked_reason"), str) else None,
            "checks_ok": state.get("required_checks_passed") is True}


def signature(root) -> str:
    """mtime and size of the files read: the screen only redraws when this changes."""
    root = Path(root)
    parts = []
    for rel in (REPO_STATE, REPO_HANDOFF, MIN_STATE, MIN_HANDOFF):
        try:
            st = (root / rel).stat()
            parts.append(f"{rel}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            continue
    try:
        for p in sorted((root / MIN_TASKS).glob("*.md"))[:200]:
            st = p.stat()
            parts.append(f"{p.name}:{st.st_mtime_ns}:{st.st_size}")
    except OSError:
        pass
    return "|".join(parts)


def find_project(path: str, sites) -> Optional[Any]:
    """Registered site that contains the folder (the most specific), to link the agent session to the Harness tab."""
    if not path:
        return None
    target = Path(path)
    best = None
    for site in sites:
        if not getattr(site, "path", None):
            continue
        root = Path(site.path)
        if target == root or root in target.parents:
            if best is None or len(str(root)) > len(str(best.path)):
                best = site
    return best


def summary(info: Dict) -> Optional[str]:
    """One line for the agent session: contract, items done and next."""
    if info.get("estado") != "ok" or not info.get("contrato"):
        return None
    items, done = info["itens"], sum(1 for i in info["itens"] if i["estado"] == "feito")
    return (tr("{id}: {done} de {total} itens feitos", id=info["contrato"].get("id") or tr("contrato"), done=done, total=len(items))
            + (tr(", próximo {next}", next=info["proximo"]) if info.get("proximo") else ""))


# ── installing the minimal format ────────────────────────────────
BLOCK_START = "<!-- vulcan:harness:inicio -->"
BLOCK_END = "<!-- vulcan:harness:fim -->"
FIRST_TASK = "primeira-tarefa"
_BLOCK = re.compile(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END), re.S)


class InstallRefused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def task_template(task_id: str, objetivo: str = "", itens: Optional[List[Dict]] = None, fora: str = "",
                  escrita: str = "", orcamento: str = "") -> str:
    """Contract in the Harness Vulcan minimal format (references/technical.md). APROVAÇÃO always pending."""
    itens = itens or [{"faixa": "verde", "objetivo": "<objetivo verificável>", "sensor": "build"}]
    lines = [f"TAREFA: {task_id} {objetivo or '<objetivo em uma frase>'}".rstrip()]
    for n, item in enumerate(itens, 1):
        faixa = f"[{item.get('faixa') or 'verde'}]"
        lines.append(f"C{n} {faixa:<10} {item.get('objetivo') or '<objetivo verificável>'}"
                     f"      sensor: {item.get('sensor') or '<sensor>'}")
    lines += [f"FORA: {fora or '<o que não será feito agora>'}", f"ESCRITA: {escrita or '<caminhos permitidos>'}",
              f"ORÇAMENTO: {orcamento or '3 tentativas por item'}", "APROVAÇÃO: pendente"]
    return "\n".join(lines) + "\n"


def _initial_state(task_id: str) -> str:
    state = {"task_id": task_id, "status": "RUNNING", "required_checks_passed": False, "items": [],
             "last_green_commit": None, "next": "C1", "blocked_reason": None}
    return json.dumps(state, ensure_ascii=False, indent=2) + "\n"


HANDOFF_TEMPLATE = """Onde paramos: nada começou; contrato em .vulcan/tasks/primeira-tarefa.md com APROVAÇÃO pendente
Próximo passo concreto: o usuário revisa e aprova o contrato; o agente começa por C1
Sensores: nenhum rodado
Âncoras: último commit verde nenhum, contrato .vulcan/tasks/primeira-tarefa.md
Avisos: validated só vira true com o sensor do item aprovado
"""

AGENTS_TEMPLATE = """# Instruções para agentes

Este projeto usa o formato mínimo do Harness Vulcan.

- Contrato da tarefa: `.vulcan/tasks/<task_id>.md`. Só comece com `APROVAÇÃO` preenchida pelo usuário.
- Estado: `.vulcan/state/execution.json`. Um item por vez; `validated` só vira `true` com o sensor do item aprovado.
- Ao parar, atualize `.vulcan/handoff.md` (cabe em uma tela) e faça commit e push.
- Falha repetida sem hipótese nova: registre o bloqueio no estado e pare.
"""

BLOCK_BODY = """## Harness Vulcan

Contratos em `.vulcan/tasks/`, estado em `.vulcan/state/execution.json` e handoff em `.vulcan/handoff.md`.
Um item por vez; `validated` só vira `true` com o sensor do item aprovado; sem `APROVAÇÃO` do usuário, não comece."""


def block_text() -> str:
    return f"{BLOCK_START}\n{BLOCK_BODY}\n{BLOCK_END}"


def with_block(text: str) -> str:
    """Replaces only the marked block; without a block, appends at the end. Every byte outside the block stays the same."""
    if _BLOCK.search(text):
        return _BLOCK.sub(lambda _m: block_text(), text, count=1)
    sep = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    return f"{text}{sep}{block_text()}\n"


def install_plan(root) -> List[Dict[str, str]]:
    """Exact list of what the installation would do: a new file (create) or a marked block in an existing file."""
    root = Path(root)
    if (root / ".harness").exists():
        raise InstallRefused(409, "o projeto tem harness próprio (.harness/); o app não instala o formato mínimo aqui")
    if not root.is_dir():
        raise InstallRefused(404, "pasta do site não existe")
    files = [
        ((MIN_TASKS / f"{FIRST_TASK}.md").as_posix(), task_template(FIRST_TASK)),
        (MIN_STATE.as_posix(), _initial_state(FIRST_TASK)),
        (MIN_HANDOFF.as_posix(), HANDOFF_TEMPLATE),
    ]
    plan = [{"caminho": rel, "acao": "criar", "conteudo": text} for rel, text in files if not (root / rel).exists()]
    docs = [name for name in ("AGENTS.md", "CLAUDE.md") if (root / name).exists()]
    if not docs:
        plan.append({"caminho": "AGENTS.md", "acao": "criar", "conteudo": AGENTS_TEMPLATE})
        plan.append({"caminho": "CLAUDE.md", "acao": "criar", "conteudo": "@AGENTS.md\n"})
    for name in docs:
        plan.append({"caminho": name, "acao": "bloco", "conteudo": block_text() + "\n"})
    return plan


def _create(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags, 0o644)  # O_EXCL: a file that already exists is never overwritten
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:  # on Windows, without turning \n into \r\n
        fh.write(text)


def _replace_block(path: Path) -> None:
    if path.is_symlink():
        raise InstallRefused(409, f"{path.name} é um link simbólico; o app não edita")
    try:
        if path.stat().st_size > MAX_FILE:
            raise InstallRefused(409, f"{path.name} maior que 1 MB")
        original = path.read_bytes().decode("utf-8")  # bytes as they are: without turning \r\n into \n
    except (OSError, UnicodeDecodeError) as exc:
        raise InstallRefused(409, f"{path.name}: {exc}") from None
    updated = with_block(original)
    if updated == original:
        return
    from vulcan_celox.core.store import write_text_atomic
    write_text_atomic(path, updated)


def install(root) -> List[Dict[str, str]]:
    """Applies the plan (call only after user confirmation). Returns what was done."""
    root = Path(root)
    plan = install_plan(root)
    done = []
    for step in plan:
        target = root / step["caminho"]
        try:
            target.resolve().relative_to(root.resolve())
        except ValueError:
            raise InstallRefused(409, f"{step['caminho']} aponta para fora do projeto") from None
        if step["acao"] == "criar":
            try:
                _create(target, step["conteudo"])
            except FileExistsError:
                continue  # appeared between the plan and the write: the user's stays
        else:
            _replace_block(target)
        done.append({"caminho": step["caminho"], "acao": step["acao"]})
    return done


# ── new contract via the interface ───────────────────────────────
FAIXAS = ("verde", "amarela", "vermelha")
MAX_ITEMS = 20
MAX_FIELD = 300


def _one_line(value, field: str) -> str:
    """One-line field: a line break would become another contract key (for example a forged APROVAÇÃO)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InstallRefused(400, f"{field} deve ser texto")
    text = " ".join(value.split())
    if len(text) > MAX_FIELD:
        raise InstallRefused(400, f"{field} passa de {MAX_FIELD} caracteres")
    return text


def create_task(root, data: Dict) -> Dict[str, str]:
    """Writes .vulcan/tasks/<task_id>.md in the minimal format. APROVAÇÃO always pending; never overwrites."""
    root = Path(root)
    if (root / ".harness").exists():
        raise InstallRefused(409, "o projeto tem harness próprio (.harness/); contratos ficam em specs/")
    if not root.is_dir():
        raise InstallRefused(404, "pasta do site não existe")
    task_id = data.get("task_id")
    if not isinstance(task_id, str) or not TASK_ID.match(task_id):
        raise InstallRefused(400, "task_id só com letras minúsculas, números e hífen (até 64)")
    raw_items = data.get("itens") or []
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= MAX_ITEMS:
        raise InstallRefused(400, f"de 1 a {MAX_ITEMS} itens")
    items = []
    for n, item in enumerate(raw_items, 1):
        if not isinstance(item, dict):
            raise InstallRefused(400, f"item {n} inválido")
        faixa = item.get("faixa") or "verde"
        if faixa not in FAIXAS:
            raise InstallRefused(400, f"faixa do item {n} deve ser verde, amarela ou vermelha")
        objetivo = _one_line(item.get("objetivo"), f"objetivo do item {n}")
        sensor = _one_line(item.get("sensor"), f"sensor do item {n}")
        if not objetivo or not sensor:
            raise InstallRefused(400, f"item {n} precisa de objetivo e sensor")
        items.append({"faixa": faixa, "objetivo": objetivo, "sensor": sensor})
    text = task_template(task_id, _one_line(data.get("objetivo"), "objetivo"), items,
                         _one_line(data.get("fora"), "fora"), _one_line(data.get("escrita"), "escrita"),
                         _one_line(data.get("orcamento"), "orçamento"))
    rel = (MIN_TASKS / f"{task_id}.md").as_posix()
    try:
        _create(root / rel, text)
    except FileExistsError:
        raise InstallRefused(409, f"já existe um contrato {task_id}") from None
    return {"caminho": rel, "conteudo": text}
