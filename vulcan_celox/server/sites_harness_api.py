"""Harness de um site pela interface."""

from __future__ import annotations

from pathlib import Path

from vulcan_celox.core import harness
from vulcan_celox.server.local_http import HttpError, Request


def register_site_harness_api(srv, site_or_404, site_name: str) -> None:
    @srv.route("GET", rf"/api/sites/{site_name}/harness")
    def site_harness(req: Request):
        """Contrato, itens, próximo, último commit verde e handoff do projeto; só leitura."""
        site = site_or_404(req.params["name"])
        root = Path(site.path)
        info = harness.read(root)
        info["assinatura"] = harness.signature(root)
        info["pasta"] = str(root)
        if info["contrato"] and info["contrato"].get("existe"):
            info["contrato"]["absoluto"] = str(root / info["contrato"]["caminho"])
        info["pode_instalar"] = info["tipo"] == "nenhum" and root.is_dir()
        info["resumo"] = harness.summary(info)
        return info

    @srv.route("GET", rf"/api/sites/{site_name}/harness/install")
    def site_harness_plan(req: Request):
        """Lista exata dos arquivos e do conteúdo que a instalação criaria; nada é gravado."""
        site = site_or_404(req.params["name"])
        try:
            return {"arquivos": harness.install_plan(Path(site.path))}
        except harness.InstallRefused as exc:
            raise HttpError(exc.status, str(exc)) from None

    @srv.route("POST", rf"/api/sites/{site_name}/harness/install")
    def site_harness_install(req: Request):
        """Instala o formato mínimo só com confirm: true. Arquivo existente nunca é sobrescrito; CLAUDE.md e
        AGENTS.md existentes só ganham o bloco marcado."""
        site = site_or_404(req.params["name"])
        if req.json().get("confirm") is not True:
            raise HttpError(400, "confirme a instalação (confirm: true) depois de ver a lista de arquivos")
        try:
            return {"feito": harness.install(Path(site.path))}
        except harness.InstallRefused as exc:
            raise HttpError(exc.status, str(exc)) from None

    @srv.route("POST", rf"/api/sites/{site_name}/harness/tasks")
    def site_harness_task(req: Request):
        """Novo contrato no formato mínimo, preenchido pelo formulário; APROVAÇÃO fica pendente."""
        site = site_or_404(req.params["name"])
        try:
            return harness.create_task(Path(site.path), req.json())
        except harness.InstallRefused as exc:
            raise HttpError(exc.status, str(exc)) from None
