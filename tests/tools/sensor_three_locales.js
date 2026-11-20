// Catalog, help, native menu acknowledgement and live terminal preservation.
(async () => {
  const pending = "three locale verification pending";
  window.__vtErrors.push(pending);
  const assert = (ok, text) => { if (!ok) throw new Error(text); };
  try {
    const i18n = await import("./js/i18n.mjs");
    const api = await import("./js/api.mjs");
    const expected = window.__VT_LANGUAGE || "en";
    const locale = { en: "en-US", pt: "pt-BR", es: "es-ES" }[expected];
    assert(i18n.currentLanguage() === expected, "wrong interface language");
    assert(document.documentElement.lang === locale, "wrong document locale");
    const prefs = await api.patch("/api/preferences", {});
    assert(prefs.language === expected, "wrong saved language");
    assert(i18n.languageOptions.length === 3, "missing locale options");
    const { loadHelp } = await import("./js/help-content.mjs");
    const help = await loadHelp();
    assert(help.secoes.length === 15 && help.faq.length === 29, "incomplete localized help");
    const translated = { en: "Settings", pt: "Configurações", es: "Configuración" }[expected];
    assert(i18n.t("Configurações") === translated, "wrong catalog");
    const { terminals } = await import("./js/terminal-pool.mjs");
    const cwd = (await api.get("/api/fs/recent")).home.path;
    const session = await terminals.create({ cwd, title: "locale sensor", command: "printf 'locale verification\\n'", agent: "shell" });
    assert(window.Terminal.strings.promptLabel === i18n.t("Entrada do terminal"), "terminal accessible label was not translated");
    if (window.__VT_SWITCH) {
      for (const language of ["es", "pt", "en"]) {
        await api.patch("/api/preferences", { language });
        const receipt = await new Promise((resolve, reject) => {
          const timer = setTimeout(() => { window.removeEventListener("vulcan-language-applied", done); reject(new Error("native menu receipt timeout")); }, 2500);
          const done = (event) => { clearTimeout(timer); window.removeEventListener("vulcan-language-applied", done); resolve(event.detail); };
          window.addEventListener("vulcan-language-applied", done);
          if (!api.native({ type: "language", language })) reject(new Error("native bridge unavailable"));
        });
        const title = { es: "Archivo", pt: "Arquivo", en: "File" }[language];
        assert(receipt.language === language && receipt.menus.includes(title), "native menus were not translated");
        const live = (await api.get("/api/terminals")).terminals.find((item) => item.id === session.info.id);
        assert(live && live.alive, "language switch stopped the terminal");
      }
    }
    await terminals.close(session.info.id);
    window.__vtErrors.splice(window.__vtErrors.indexOf(pending), 1);
    window.__threeLocalesVerified = true;
  } catch (error) { window.__vtErrors.push(String(error)); }
})();
