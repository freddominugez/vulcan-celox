"""Documentação com IA: prévia do que será enviado, geração em segundo plano e leitura dos arquivos gerados."""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any, Dict

from vulcan_terminal.core.doc_prompts import Prompt, SessionEntry, general_doc_prompt, relative_link, session_doc_prompt
from vulcan_terminal.core.session_memory import GENERAL_DOC_FILENAME, doc_path, extract_transcript
from vulcan_terminal.core.store import write_text_atomic
from vulcan_terminal.server.ai_jobs import AiJobs
from vulcan_terminal.server.local_http import HttpError, Request

SESSION_MAX_TOKENS = 8000
GENERAL_MAX_TOKENS = 12000
HEADER = re.compile(r"\A<!-- vulcan:documentacao[^\n]*-->\n(?:>[^\n]*\n)*\n?")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def doc_header(kind: str, model: str, source: str) -> str:
    return (f"<!-- vulcan:documentacao {kind} modelo={model} gerado={_now()} -->\n"
            f"> Gerado por IA ({model}) em {_now()} a partir de {source}. Confira antes de usar; "
            f"segredos foram mascarados antes do envio.\n\n")


class AiDocs:
    def __init__(self, app) -> None:
        self.app = app
        self.jobs = AiJobs()

    # ── sessão ───────────────────────────────────────────────────────────
    def record(self, session_id: str):
        record = self.app.hub.sessions.get(session_id)
        if record is None:
            raise HttpError(404, "sessão não encontrada")
        return record

    def session_prompt(self, record) -> Prompt:
        hub, nb = self.app.hub, self.app.notebook
        with self.app.notebook_api.lock:
            tasks = [t for t in nb.tasks if t.terminal == record.id]
            notes = [n for n in nb.notes if n.terminal == record.id]
            tags = dict(nb.tags)
        memory = hub.memory_text(record) or ""
        transcript, _ = extract_transcript(memory) if memory else ("", False)
        return session_doc_prompt(record, tasks, notes, tags, transcript, agents=self.app.hub.agents_for(record.id))

    def preview(self, prompt: Prompt) -> Dict[str, Any]:
        return {"chars": prompt.chars, "redactions": prompt.redactions, "truncated": prompt.truncated,
                "stats": prompt.stats, "model": self.app.ai.model(), "configured": bool(self.app.ai.key())}

    def generate_session(self, record) -> Dict[str, Any]:
        client = self.app.ai.client()  # 409 sem chave, antes de criar a tarefa
        model = self.app.ai.model()
        if not record.memory_file:
            self.app.hub.write_memory(record.id)
            record = self.record(record.id)

        def work():
            prompt = self.session_prompt(record)
            result = client.complete(prompt.system, prompt.user, model=model, max_tokens=SESSION_MAX_TOKENS)
            target = doc_path(record.memory_file)
            source = f"[memória da sessão]({Path(record.memory_file).name})"
            text = doc_header(f"sessao={record.id}", result.model, source) + result.text.strip() + "\n"
            if result.stop_reason == "max_tokens":
                text += "\n> A resposta atingiu o limite de tamanho e pode estar incompleta.\n"
            write_text_atomic(target, text)
            self.app.hub.write_index()
            note = f" ({prompt.redactions} segredos mascarados)" if prompt.redactions else ""
            return str(target), f"documentação de “{record.title}” gerada{note}"

        return self.jobs.start("session", record.id, record.title, work)

    # ── geral ────────────────────────────────────────────────────────────
    def general_path(self) -> Path:
        return Path(self.app.data_dir) / GENERAL_DOC_FILENAME

    def general_prompt(self) -> Prompt:
        nb, data_dir = self.app.notebook, self.app.data_dir
        with self.app.notebook_api.lock:
            tasks, notes, tags = list(nb.tasks), list(nb.notes), dict(nb.tags)
        entries = []
        for record in self.app.hub.sessions.list():  # mais recentes primeiro
            doc = doc_path(record.memory_file)
            doc_text = None
            if doc and doc.is_file():
                doc_text = HEADER.sub("", doc.read_text(encoding="utf-8"))
            link = relative_link(str(doc) if doc_text else record.memory_file, data_dir)
            entries.append(SessionEntry(record, [t for t in tasks if t.terminal == record.id],
                                        [n for n in notes if n.terminal == record.id], link, doc_text))
        return general_doc_prompt(entries, tags)

    def generate_general(self) -> Dict[str, Any]:
        client = self.app.ai.client()
        model = self.app.ai.model()
        if not self.app.hub.sessions.list():
            raise HttpError(409, "ainda não há sessões de terminal para documentar")

        def work():
            prompt = self.general_prompt()
            result = client.complete(prompt.system, prompt.user, model=model, max_tokens=GENERAL_MAX_TOKENS)
            text = doc_header("geral", result.model, "[índice geral](INDICE.md)") + result.text.strip() + "\n"
            if result.stop_reason == "max_tokens":
                text += "\n> A resposta atingiu o limite de tamanho e pode estar incompleta.\n"
            write_text_atomic(self.general_path(), text)
            self.app.hub.write_index()
            note = f" ({prompt.redactions} segredos mascarados)" if prompt.redactions else ""
            return str(self.general_path()), f"documentação geral gerada{note}"

        return self.jobs.start("general", "all", "documentação geral", work)


def register_ai_docs_api(app) -> AiDocs:
    srv = app.server
    docs = AiDocs(app)

    @srv.route("GET", r"/api/ai/preview/session/(?P<sid>[0-9a-f]+)")
    def preview_session(req: Request):
        return docs.preview(docs.session_prompt(docs.record(req.params["sid"])))

    @srv.route("POST", r"/api/ai/docs/session/(?P<sid>[0-9a-f]+)")
    def generate_session(req: Request):
        return 202, docs.generate_session(docs.record(req.params["sid"]))

    @srv.route("GET", "/api/ai/preview/general")
    def preview_general(_req: Request):
        return docs.preview(docs.general_prompt())

    @srv.route("POST", "/api/ai/docs/general")
    def generate_general(_req: Request):
        return 202, docs.generate_general()

    @srv.route("GET", "/api/index/documentation")
    def general_doc(_req: Request):
        path = docs.general_path()
        if not path.is_file():
            raise HttpError(404, "a documentação geral ainda não foi gerada")
        return {"path": str(path), "markdown": path.read_text(encoding="utf-8")}

    @srv.route("GET", "/api/ai/jobs")
    def list_jobs(_req: Request):
        return {"jobs": docs.jobs.list(), "running": docs.jobs.running()}

    @srv.route("GET", r"/api/sessions/(?P<sid>[0-9a-f]+)/doc")
    def session_doc(req: Request):
        record = docs.record(req.params["sid"])
        path = doc_path(record.memory_file)
        if not path or not path.is_file():
            raise HttpError(404, "esta sessão ainda não tem documentação")
        return {"path": str(path), "markdown": path.read_text(encoding="utf-8")}

    return docs
