// Terminals: entry point. The session pool is in terminal-pool.mjs and the tabs in terminal-workspace.mjs.

import { native } from "./api.mjs";
import { $, reportError, shortPath } from "./dom.mjs";
import { t } from "./i18n.mjs";
import { terminals } from "./terminal-pool.mjs";

export { terminals };
export { TerminalWorkspace } from "./terminal-workspace.mjs";

export function mountPopout(root, id) {
  root.innerHTML = `<div class="popout"><div class="popout-bar" data-drag><span class="session-color" aria-hidden="true"></span><span class="popout-title"></span></div><div class="pane popout-pane"></div></div>`;
  terminals.watch().then(() => {
    const session = terminals.get(id);
    const title = $(".popout-title", root);
    if (!session) {
      $(".popout-pane", root).innerHTML = `<div class="term-empty"><div class="term-empty-inner"><h3>${t("Terminal encerrado")}</h3>
        <p>${t("Esta sessão não existe mais.")}</p><button class="btn" data-close>${t("Fechar janela")}</button></div></div>`;
      root.querySelector("[data-close]").addEventListener("click", () => native({ type: "close" }) || window.close());
      return;
    }
    const update = () => {
      if (session.disposed) return;
      const color = session.info.tab_color || session.info.theme;
      title.parentElement.className = color ? `popout-bar has-theme t-${color}` : "popout-bar";
      title.textContent = `${session.info.title} · ${shortPath(session.info.cwd)}`;
      document.title = `${session.info.title} · Vulcan Celox`;
      native({ type: "setTitle", title: document.title });
    };
    update();
    terminals.subscribe(update);
    window.vulcanFocusTerminal = () => session.focus();
    session.mount($(".popout-pane", root));
    new ResizeObserver(() => session.resizeSoon()).observe($(".popout-pane", root));
    session.focus();
  }).catch(reportError);
}
