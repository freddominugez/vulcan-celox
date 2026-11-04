// Installing Lerd from the app: the official command, shown first and run in a visible terminal.

import { get, post } from "./api.mjs";
import { esc, reportError } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { confirmDialog } from "./ai.mjs";

export async function installLerd() {
  try {
    const guide = await get("/api/guide");
    const step = guide.steps.find((s) => s.id === "lerd");
    if (!step) return;
    const yes = await confirmDialog({
      title: t("Instalar o Lerd"),
      body: `<p>${t("O Lerd roda sites PHP e Laravel na sua máquina: domínio .test, versão de PHP por projeto, banco e HTTPS local. É opcional.")}</p>
        <p>${t("Este comando baixa o instalador oficial e roda num terminal à vista. Se ele pedir a senha de administrador, quem pede é o sistema: o app nunca a vê.")}</p>
        <pre class="md-code">${esc(step.install_command)}</pre>`,
      confirmLabel: t("Abrir terminal e instalar"),
    });
    if (!yes) return;
    const session = await post("/api/guide/lerd/install", {});
    location.hash = `#/terminals/terminal/${encodeURIComponent(session.id)}`;
  } catch (err) {
    reportError(err);
  }
}
