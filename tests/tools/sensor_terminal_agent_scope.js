// Actual dialog and workspace, with terminal creation captured so no agent CLI runs.
(async () => {
  const tag = "agente herdado entre terminais";
  window.__vtErrors.push(tag);
  const waitFor = async (fn) => {
    for (let i = 0; i < 100; i++) {
      const value = fn();
      if (value) return value;
      await new Promise((resolve) => setTimeout(resolve, 40));
    }
    throw new Error("terminal dialog timeout");
  };
  const assert = (value, message) => { if (!value) throw new Error(message); };
  try {
    const api = await import("./js/api.mjs");
    const { askFolder } = await import("./js/folder-dialog.mjs");
    const { TerminalWorkspace } = await import("./js/terminal-workspace.mjs");
    const { terminals } = await import("./js/terminal-pool.mjs");
    const themes = await import("./js/themes.mjs");
    const folder = (await api.get("/api/fs/recent")).home.path;
    await api.patch("/api/preferences", { new_terminal: { agent: "codex", skip_folder: false } });
    const first = askFolder({ suggested: folder });
    let dialog = await waitFor(() => document.querySelector(".folder-dialog [data-ok]:not(:disabled)"));
    document.querySelector('.folder-dialog [data-agent="codex"]').click();
    dialog.closest("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    assert((await first).agent === "codex", "explicit Codex selection was lost");
    const next = askFolder({ suggested: folder });
    dialog = await waitFor(() => document.querySelector(".folder-dialog [data-ok]:not(:disabled)"));
    assert(document.querySelector('.folder-dialog [data-agent="shell"]').getAttribute("aria-checked") === "true", "next dialog inherited Codex");
    dialog.closest("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    assert((await next).agent === "shell", "next dialog did not return shell");
    await api.patch("/api/preferences", { new_terminal: { skip_folder: true, agent: "codex" } });
    const oldCreate = terminals.create;
    const captured = [];
    terminals.create = async (options) => {
      captured.push(options);
      return { info: { id: "sensor-tab" }, focus() {} };
    };
    try {
      const workspace = Object.create(TerminalWorkspace.prototype);
      workspace.options = {};
      workspace.setMode = () => {};
      // Force stale cached state too: newTerminal refreshes themes before it uses preferences.
      themes.themes.newTerminal = { skip_folder: true, agent: "codex" };
      await workspace.newTerminal();
      workspace.root = { contains: () => true };
      workspace.sessions = () => [];
      const split = { dataset: { action: "split" }, closest: () => null };
      workspace.onClick({ target: { closest: () => split } });
      await waitFor(() => captured.length === 2);
      await workspace.newTerminal("npm run build", "build");
      assert(captured.length === 3, "terminal creation missing");
      assert(captured[0].agent === "shell" && captured[1].agent === "shell", "direct opening inherited agent");
      assert(captured[2].command === "npm run build" && !captured[2].agent, "explicit command changed");
    } finally { terminals.create = oldCreate; }
    window.__vtErrors.splice(window.__vtErrors.indexOf(tag), 1);
    window.__terminalAgentScopePassed = true;
  } catch (err) { window.__vtErrors.push(String(err)); }
})();
