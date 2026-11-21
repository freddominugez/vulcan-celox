/* Run inside the native snapshot against an isolated repository and PTY fixtures. */
(() => {
  const pending = "Terminais e Codex: verificação pendente";
  window.__vtErrors.push(pending);
  // The native snapshot is placed outside the screen. Exercise the visible-window polling cadence.
  Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
  const $ = (selector) => document.querySelector(selector);
  const check = (condition, label) => { if (!condition) throw new Error(label); };
  const wait = async (condition, label, ms = 9000) => {
    const end = performance.now() + ms;
    while (performance.now() < end) {
      const value = condition();
      if (value) return value;
      await new Promise((resolve) => setTimeout(resolve, 40));
    }
    throw new Error(label);
  };
  const events = [];
  const sent = [];
  const send = WebSocket.prototype.send;
  WebSocket.prototype.send = function (value) {
    if (typeof value !== "string") sent.push(this.url.split("?")[0]);
    return send.call(this, value);
  };
  const fetchOrig = window.fetch;
  window.fetch = async (url, options) => {
    const response = await fetchOrig(url, options);
    const path = new URL(url, document.baseURI);
    events.push({ path, body: options?.body, status: response.status });
    return response;
  };
  (async () => {
    const { root, executable, site, theme, cross = false } = window.__fixture;
    const [{ post, get, patch }, { terminals }, { t }, { setThemePref }] = await Promise.all([
      import("./js/api.mjs"), import("./js/terminal-pool.mjs"), import("./js/i18n.mjs"), import("./js/theme.mjs"),
    ]);
    const visible = (node) => node && !node.closest("[hidden]");
    const routeLink = (id) => `[data-live="${id}"]`;
    await setThemePref(theme);
    await patch("/api/preferences", { sidebar_collapsed: false });
    if ($("#app").classList.contains("is-rail")) $("#side-collapse").click();
    await wait(() => $("#side-live") && visible($("#side-live")), "sidebar ausente");
    check($("#side-live .tree-empty"), "lista inicial vazia ausente");
    await post("/api/files/roots", { path: root });
    const a = await post("/api/terminals", { site, cwd: root, title: "Codex fixture", command: `/usr/bin/python3 ${executable} recebido-a.txt` });
    const b = await post("/api/terminals", { site: cross ? null : site, cwd: root, title: "Codex fixture", command: `/usr/bin/python3 ${executable} leia.txt` });
    const shell = await post("/api/terminals", { site, cwd: root, title: "Shell fixture", command: "cat" });
    await patch(`/api/terminals/${b.id}`, { title: a.title });
    await terminals.sync();
    (await wait(() => $(routeLink(a.id)), "terminal A ausente")).click();
    await wait(() => $('.tab.is-active')?.dataset.id === a.id, "aba A fora de foco");
    check(!terminals.get(b.id).opened && terminals.live().length === 3, "WebSocket iniciado em aba não montada");
    $("[data-action=session-code]").click();
    await wait(() => events.some(({ path }) => path.pathname === "/api/files/changes"), "foto inicial ausente");
    $("[data-sc=files]").click();
    check(visible($(".session-files")), "Arquivos ocultos");
    if (window.innerWidth < 1080) {
      check($(".session-files").classList.contains("is-drawer"), "gaveta não apareceu");
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
      check(!visible($(".session-files")) && document.activeElement.dataset.sc === "files", "Escape e foco da gaveta");
      $("[data-sc=files]").click();
    }
    const tree = $(".session-code-tree .wunderbaum");
    (await wait(() => [...document.querySelectorAll(".session-code-tree .wb-title")].find((e) => e.textContent === "leia.txt"), "arquivo ausente da árvore")).click();
    await wait(() => $(".session-code .cm-content")?.textContent.includes("linha antiga"), "texto inteiro não exibido");
    if (window.innerWidth < 1080) $("[data-sc=close]").click();
    $("[data-sc=codex]").click();
    const area = $(".codex-input");
    const prompt = "/fixture {{literal}}\nOlá 🧭\t fim";
    const write = (text) => {
      area.value = text;
      area.dispatchEvent(new InputEvent("input", { bubbles: true }));
    };
    check($("[data-codex=copy]").disabled, "cópia vazia habilitada");
    write("a\u001bb");
    check($("[data-codex=copy]").disabled && area.getAttribute("aria-invalid") === "true", "controle aceito");
    write("🙂".repeat(4001));
    check($("[data-codex=copy]").disabled, "limite Unicode não aplicado");
    write(prompt);
    $("[data-codex=copy]").click();
    await wait(() => $(".codex-status").textContent === t("Confira a área de transferência"), "ponte declarou cópia confirmada");
    check(visible($("[data-codex=select]")), "fallback não disponível");
    $("[data-codex=select]").click();
    check(document.activeElement === area && area.selectionEnd === prompt.length, "fallback não selecionou o rascunho");
    $("[data-codex=open]").click();
    const select = $(".codex-picker select");
    check([...select.options].filter((o) => o.textContent.startsWith(a.title)).length === 2, "abas homônimas ausentes");
    check(select.options.namedItem(b.id) || [...select.options].find((o) => o.value === b.id)?.textContent.includes(b.id), "ID não exibido");
    select.value = b.id;
    select.dispatchEvent(new Event("change"));
    $(".codex-verify input").checked = true;
    $("[data-codex=confirm]").click();
    await wait(() => $(".codex-destination").textContent.includes(b.id), "destino B não confirmado");
    check(area.value === prompt && sent.length === 0, "confirmar destino transmitiu ou perdeu o rascunho");
    $("[data-codex=open]").click();
    await wait(() => $(".tab.is-active")?.dataset.id === b.id && terminals.get(b.id).ws?.readyState === WebSocket.OPEN,
      "foco não foi para B");
    check(document.activeElement.closest(".xterm-host")?.dataset.tabId === b.id, "entrada não focou B");
    check(sent.length === 0 && !events.some(({ body, path }) => body?.includes("{{literal}}") || path.href.includes("{{literal}}")),
      "compositor escreveu na API ou no PTY");
    if (cross) {
      check(location.hash.startsWith("#/terminals/terminal/"), "destino global não abriu a rota de Terminais");
      $("[data-action=window-drafts]").click();
      const preview = $(".codex-shelf textarea");
      preview.closest("details").open = true;
      check(preview.value === prompt, "rascunho não ficou disponível na rota de destino");
      window.__vtErrors.splice(window.__vtErrors.indexOf(pending), 1);
      return;
    }
    const session = terminals.get(b.id);
    await wait(() => session.term.modes.bracketedPasteMode, "fixture não entrou em modo de colagem");
    // The sensor performs the two manual steps on the test terminal, after proving the composer sent no bytes.
    session.term.paste(prompt);
    await new Promise((resolve) => setTimeout(resolve, 200));
    const read = () => get(`/api/files/read?root=${encodeURIComponent(root)}&path=leia.txt`);
    check((await read()).text.includes("linha antiga"), "a fixture recebeu Enter durante a colagem");
    const started = performance.now();
    session.term.input("\r", true);
    await wait(() => $(".session-code .cm-content")?.textContent.includes("Olá 🧭"), "arquivo aberto não atualizou em 3 s", 3000);
    check(performance.now() - started < 3000, "atualização acima de 3 s");
    check((await read()).text === prompt, "fixture recebeu texto diferente");
    check(sent.length === 2 && sent.every((url) => url.endsWith("/" + b.id)), "bytes em outro PTY");
    $("[data-action=session-code]").click();
    check($(".tab.is-active")?.dataset.id === a.id && area.value === prompt, "o contexto original ou o rascunho se perdeu");
    check(tree === $(".session-code-tree .wunderbaum"), "árvore remontada durante passagem ao PTY");
    check(new Set(events.filter(({ path }) => path.pathname === "/api/files/changes").map(({ path }) => path.searchParams.get("client"))).size === 1,
      "observador duplicado");
    $("[data-ce-mode=diff]").click();
    await wait(() => /HEAD [0-9a-f]{12}/.test($(".session-code .code-notes").textContent), "base do diff ausente");
    if ($(".session-files").hidden) $("[data-sc=files]").click();
    $("[data-sc=changes]").click();
    await wait(() => $(".session-events").textContent.includes(t("Mudança no disco")), "mudança sem rótulo de disco");
    check(document.documentElement.scrollWidth === window.innerWidth, "rolagem horizontal no documento");
    window.__vtErrors.splice(window.__vtErrors.indexOf(pending), 1);
  })().catch((error) => window.__vtErrors.push(String(error)));
})();
