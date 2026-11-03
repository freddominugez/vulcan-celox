// Projetos Node: lista com sugestões e a página de cada projeto. Scripts rodam numa aba de terminal à
// vista; parar é Ctrl-C na aba do próprio projeto. O app não fala com a Vercel nem com o Supabase remoto.

import { every, get, hasBridge, post } from "../api.mjs";
import { esc, icon, reportError, shortPath, toast } from "../dom.mjs";
import { confirmDialog } from "../ai.mjs";
import { pickNative } from "../folder-dialog.mjs";
import { terminals } from "../terminals.mjs";

const NAME = /^[a-z0-9][a-z0-9._-]{0,63}$/;
const MAIN_SCRIPTS = ["dev", "start", "build", "preview", "test", "lint"];

function slug(text) {
  return (text.split("/").filter(Boolean).pop() || "projeto").toLowerCase().replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^[-._]+|[-._]+$/g, "").slice(0, 64) || "projeto";
}

/** Diálogo de adicionar: pasta (com seletor nativo) e nome; o servidor confere o package.json. */
export async function addNodeDialog(path = "") {
  let data = null;
  const body = `<p>Escolha a pasta raiz do projeto, onde fica o <code>package.json</code>. Nada é gravado nela.</p>
    <div class="folder-field">${icon("folder")}<input class="folder-input" data-np="path" spellcheck="false"
      placeholder="/Users/voce/Code/projeto" aria-label="Pasta" value="${esc(path)}">
      ${hasBridge ? `<button type="button" class="btn btn-sm" data-np-pick>Escolher…</button>` : ""}</div>
    <label class="field-label" for="np-name">Nome na lista</label>
    <input id="np-name" class="input mono" data-np="name" value="${esc(path ? slug(path) : "")}" spellcheck="false">`;
  const picker = (e) => {
    if (!e.target.closest("[data-np-pick]")) return;
    const root = e.target.closest(".dialog");
    pickNative(root.querySelector("[data-np=path]").value || "").then((picked) => {
      if (!picked) return;
      root.querySelector("[data-np=path]").value = picked;
      root.querySelector("[data-np=name]").value = slug(picked);
    });
  };
  document.addEventListener("click", picker);
  const ok = await confirmDialog({
    title: "Adicionar projeto Node", body, confirmLabel: "Adicionar",
    onDecide: (answer, root) => {
      if (answer) data = { path: root.querySelector("[data-np=path]").value.trim(), name: root.querySelector("[data-np=name]").value.trim() };
    },
  });
  document.removeEventListener("click", picker);
  if (!ok || !data) return null;
  if (data.name && !NAME.test(data.name)) throw new Error("Nome só com letras minúsculas, números, ponto, hífen e sublinhado.");
  const added = await post("/api/node-projects", data.name ? data : { path: data.path });
  toast(`Projeto ${added.name} adicionado.`, { kind: "ok" });
  return added;
}

function showTerminal(id) {
  window.dispatchEvent(new CustomEvent("vulcan-show-terminal", { detail: { id } }));
}

export class NodeListView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.load();
  }

  async load() {
    try {
      [this.list, this.suggest] = await Promise.all([get("/api/node-projects"), get("/api/node-projects/suggest").catch(() => ({ suggestions: [] }))]);
      this.render();
    } catch (err) {
      reportError(err);
    }
  }

  render() {
    const projects = this.list.projects;
    const rows = projects.map((p) => `<tr data-go="#/node/${encodeURIComponent(p.name)}" class="np-row">
        <td><span class="np-mark">${icon("hex")}</span><b>${esc(p.name)}</b></td>
        <td>${esc(p.framework || (p.estado === "ok" ? "Node" : p.estado))}</td>
        <td class="mono">${esc(p.gerenciador || "")}</td>
        <td class="num">${p.porta || ""}</td>
        <td>${p.supabase ? `<span class="badge">Supabase</span>` : ""}${p.vercel ? `<span class="badge">Vercel</span>` : ""}</td>
        <td class="dim mono np-path">${esc(shortPath(p.path))}</td></tr>`).join("");
    const sug = this.suggest.suggestions;
    this.root.innerHTML = `<div class="page np-page">
      <section class="panel">
        <header class="panel-head">${icon("hex")}<h2>Projetos Node</h2><span class="count">${projects.length}</span><span class="spacer"></span>
          <button class="btn btn-primary btn-sm" data-np-add>${icon("plus")}<span>Adicionar projeto</span></button></header>
        ${projects.length ? `<table class="table np-table"><thead><tr><th>Projeto</th><th>Framework</th><th>Gerenciador</th><th class="num">Porta</th><th>Serviços</th><th>Pasta</th></tr></thead>
          <tbody>${rows}</tbody></table>` : `<div class="empty-block"><h3>Nenhum projeto Node ainda</h3>
          <p>Next.js, Vite, Nuxt, Astro e afins: o app lê o <code>package.json</code>, liga e para o servidor de desenvolvimento
          num terminal à vista e mostra o Supabase local e o vínculo com a Vercel.</p></div>`}
      </section>
      ${sug.length ? `<section class="panel"><header class="panel-head">${icon("spark")}<h2>Sugestões</h2>
          <span class="dim hint">pastas com package.json onde seus agentes trabalharam</span></header>
        <ul class="np-sug">${sug.map((s) => `<li><span class="mono">${esc(shortPath(s.path))}</span><span class="spacer"></span>
          <button class="btn btn-sm" data-np-add="${esc(s.path)}">${icon("plus")}<span>Adicionar</span></button></li>`).join("")}</ul></section>` : ""}
    </div>`;
  }

  async onClick(event) {
    const add = event.target.closest("[data-np-add]");
    if (!add) return;
    try {
      const added = await addNodeDialog(add.dataset.npAdd || "");
      if (added) {
        window.dispatchEvent(new CustomEvent("vulcan-node-changed"));
        this.options.navigate(`#/node/${encodeURIComponent(added.name)}`);
      }
    } catch (err) {
      reportError(err);
    }
  }
}

export class NodeProjectView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.name = options.name;
    this.key = null;
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.stopTimer = every(3000, () => this.load());
    this.load();
  }

  destroy() {
    if (this.stopTimer) this.stopTimer();
  }

  async load() {
    try {
      const info = await get(`/api/node-projects/${encodeURIComponent(this.name)}`);
      const key = JSON.stringify(info);
      if (key === this.key) return;
      this.key = key;
      this.info = info;
      this.render();
    } catch (err) {
      if (err.status === 404) {
        this.root.innerHTML = `<div class="page"><div class="empty-block"><h3>Projeto “${esc(this.name)}” não está na lista</h3>
          <button class="btn" data-go="#/node">Projetos Node</button></div></div>`;
        this.stopTimer();
        return;
      }
      reportError(err);
    }
  }

  runsOf(label) {
    return (this.info.rodando || []).filter((r) => r.script === label);
  }

  render() {
    const i = this.info;
    if (i.estado !== "ok") {
      this.root.innerHTML = `<div class="page"><section class="panel"><header class="panel-head">${icon("alert")}<h2>${esc(this.name)}</h2></header>
        <p class="hs-pad">${i.estado === "sumiu" ? "A pasta não existe mais." : i.estado === "nenhum" ? "A pasta não tem package.json." : "O package.json não pôde ser lido."}</p>
        ${i.erro ? `<pre class="hs-pre mono">${esc(i.erro)}</pre>` : ""}
        <div class="hs-pad"><button class="btn btn-sm" data-np-remove>${icon("x")}<span>Tirar da lista</span></button></div></section></div>`;
      return;
    }
    const scripts = [...i.scripts].sort((a, b) => {
      const ia = MAIN_SCRIPTS.indexOf(a.nome), ib = MAIN_SCRIPTS.indexOf(b.nome);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
    const url = (i.rodando || []).map((r) => r.url).find(Boolean);
    const scriptRow = (s) => {
      const runs = this.runsOf(s.nome);
      const run = runs[runs.length - 1];
      return `<li class="np-svc">
        <span class="dot ${run ? "dot-ok" : "dot-idle"}"></span>
        <span class="np-svc-main"><b>${esc(s.nome)}</b><span class="dim mono">${esc(s.comando)}</span></span>
        ${run && run.url ? `<button class="btn btn-ghost btn-sm mono" data-np-open="${esc(run.url)}">${esc(run.url.replace(/^https?:\/\//, ""))}</button>` : ""}
        ${run ? `<button class="btn btn-ghost btn-sm" data-np-show="${run.terminal}">${icon("terminal")}<span>Ver</span></button>
          <button class="btn btn-sm" data-np-stop="${run.terminal}">${icon("stop")}<span>Parar</span></button>`
        : `<button class="btn btn-sm" data-np-run="${esc(s.nome)}">${icon("play")}<span>Rodar</span></button>`}</li>`;
    };
    const sb = i.supabase;
    const sbRuns = (i.rodando || []).filter((r) => r.script.startsWith("supabase "));
    const supa = sb ? `<section class="panel np-supabase"><header class="panel-head">${icon("database")}<h2>Supabase local</h2>
        ${sb.project_id ? `<span class="dim mono">${esc(sb.project_id)}</span>` : ""}</header>
      ${sb.estado === "ok" ? `<div class="hs-pad np-facts-inline"><span>API <span class="mono">localhost:${sb.porta_api}</span></span>
        <span>Studio <span class="mono">localhost:${sb.studio}</span></span></div>
      <div class="hs-pad np-actions">
        <button class="btn btn-sm" data-np-sb="start">${icon("play")}<span>supabase start</span></button>
        <button class="btn btn-sm" data-np-sb="status">${icon("info")}<span>status</span></button>
        <button class="btn btn-sm" data-np-sb="stop">${icon("stop")}<span>supabase stop</span></button>
        <button class="btn btn-ghost btn-sm" data-np-open="http://localhost:${sb.studio}">${icon("external")}<span>Abrir Studio</span></button>
        ${sbRuns.length ? `<span class="dim hint">${sbRuns.length} aba(s) do Supabase abertas</span>` : ""}</div>
      <p class="dim hint hs-pad">Os comandos rodam numa aba de terminal; o app não fala com o Supabase remoto.</p>`
      : `<pre class="hs-pre mono">${esc(sb.erro || "")}</pre>`}</section>` : "";
    const vc = i.vercel;
    const vercel = `<section class="panel np-vercel"><header class="panel-head">${icon("globe")}<h2>Vercel</h2></header>
      <p class="hs-pad">${vc ? (vc.estado === "ok" ? `Vinculado pelo <code>.vercel/project.json</code> (projeto <span class="mono">${esc(vc.projectId || "?")}</span>). Deploy e logs ficam no painel da Vercel ou no <code>vercel</code> do terminal.`
        : `O <code>.vercel/project.json</code> não pôde ser lido.`) : `Sem vínculo local. Rode <code>vercel link</code> no terminal do projeto se ele for publicado na Vercel.`}</p></section>`;
    const fw = i.framework;
    this.root.innerHTML = `<div class="page np-page">
      <div class="np-head"><span class="np-logo">${icon("hex")}</span>
        <div class="np-title"><h1>${esc(this.name)}</h1><span class="dim mono">${esc(shortPath(i.pasta))}</span></div><span class="spacer"></span>
        ${url ? `<button class="btn btn-sm" data-np-open="${esc(url)}">${icon("external")}<span>Abrir no navegador</span></button>` : ""}
        <button class="btn btn-sm" data-np-term>${icon("terminal")}<span>Terminal</span></button>
        <button class="btn btn-ghost btn-sm" data-np-remove title="Só tira da lista do app; a pasta fica intacta">${icon("x")}<span>Tirar da lista</span></button></div>
      <div class="np-grid">
        <div class="np-col">
          <section class="panel np-scripts"><header class="panel-head">${icon("play")}<h2>Scripts</h2><span class="count">${scripts.length}</span>
            <span class="dim hint">rodam com ${esc(i.gerenciador)} numa aba de terminal</span></header>
            ${scripts.length ? `<ul class="np-list">${scripts.map(scriptRow).join("")}</ul>` : `<p class="hs-pad dim">O package.json não tem scripts.</p>`}</section>
          ${supa}
        </div>
        <section class="panel np-facts"><header class="panel-head">${icon("info")}<h2>Projeto</h2></header>
          <dl class="np-dl">
            <div><dt>Nome no package.json</dt><dd>${esc(i.nome)}</dd></div>
            <div><dt>Framework</dt><dd>${fw ? `${esc(fw.nome)} <span class="dim mono">${esc(fw.versao)}</span>` : "não reconhecido"}</dd></div>
            <div><dt>Gerenciador</dt><dd class="mono">${esc(i.gerenciador)}</dd></div>
            <div><dt>Porta provável</dt><dd class="mono">${i.porta_provavel || "?"}</dd></div>
            <div><dt>Node pedido</dt><dd>${i.node ? `<span class="mono">${esc(i.node.valor)}</span> <span class="dim">(${esc(i.node.fonte)})</span>` : "não fixado"}</dd></div>
          </dl>
          <p class="dim hint hs-pad">O app nunca abre o <code>.env</code> do projeto.</p>
        </section>
      </div>
      ${vercel}
    </div>`;
  }

  async onClick(event) {
    const t = event.target;
    const base = `/api/node-projects/${encodeURIComponent(this.name)}`;
    try {
      const run = t.closest("[data-np-run]");
      if (run) {
        const res = await post(`${base}/run`, { script: run.dataset.npRun });
        await terminals.sync();
        showTerminal(res.terminal);
        toast(`Rodando ${res.comando}`, { kind: "ok" });
        this.key = null;
        return this.load();
      }
      const sb = t.closest("[data-np-sb]");
      if (sb) {
        const res = await post(`${base}/supabase/${sb.dataset.npSb}`, {});
        await terminals.sync();
        showTerminal(res.terminal);
        this.key = null;
        return this.load();
      }
      const stop = t.closest("[data-np-stop]");
      if (stop) {
        await post(`${base}/stop`, { terminal: stop.dataset.npStop });
        toast("Ctrl-C enviado. A aba continua aberta com a saída.", { kind: "ok" });
        setTimeout(() => { this.key = null; this.load(); }, 800);
        return null;
      }
      const show = t.closest("[data-np-show]");
      if (show) return showTerminal(show.dataset.npShow);
      const open = t.closest("[data-np-open]");
      if (open) return await post("/api/open", { kind: "url", target: open.dataset.npOpen });
      if (t.closest("[data-np-term]")) {
        const session = await terminals.create({ site: null, cwd: this.info.pasta, command: null, title: this.name, theme: "auto", agent: "shell" });
        return showTerminal(session.info.id);
      }
      if (t.closest("[data-np-remove]")) {
        const yes = await confirmDialog({ title: `Tirar ${this.name} da lista`, body: "<p>Só a lista do app muda. A pasta e os arquivos ficam como estão.</p>", confirmLabel: "Tirar da lista" });
        if (!yes) return null;
        await post(`${base}/remove`, {});
        window.dispatchEvent(new CustomEvent("vulcan-node-changed"));
        this.options.navigate("#/node");
      }
    } catch (err) {
      reportError(err);
    }
    return null;
  }
}
