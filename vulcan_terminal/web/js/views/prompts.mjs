// Prompts: quadro de botões por categoria; um clique copia o texto já preenchido com a sessão atual.

import { get, post } from "../api.mjs";
import { esc, icon, reportError, toast } from "../dom.mjs";
import { AGENT_NAMES, copy, keepScroll } from "../agents-ui.mjs";

const VAR = /\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g;

/** Texto final: cada variável trocada pelo valor do campo (vazio fica como estava, para o aviso pegar). */
export function compose(body, values) {
  return body.replace(VAR, (m, name) => (values[name] ? values[name] : m));
}

/** Prévia em texto corrido com os valores destacados; o que falta aparece pelo rótulo, em âmbar. */
function previewHtml(body, values, label) {
  return esc(body).replace(VAR, (m, name) => (values[name]
    ? `<mark>${esc(values[name])}</mark>`
    : `<mark class="is-empty">${esc(label(name))}</mark>`));
}

function short(value, size = 8) {
  return value.length > 24 ? `${value.slice(0, size)}…` : value;
}

export class PromptsView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.data = null;
    this.picked = null;
    this.values = {};  // valores dos campos por prompt, guardados enquanto a tela está aberta
    this.typed = {};  // só o que o usuário digitou: sobrevive à troca de sessão e à recarga (vt-29 C4)
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.addEventListener("input", (e) => {
      if (!e.target.closest(".pc-field")) return;
      if (this.picked && e.target.name) (this.typed[this.picked] = this.typed[this.picked] || {})[e.target.name] = e.target.value.trim();
      this.refreshPreview();
    });
    this.root.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.picked) { this.picked = null; keepScroll(this.root, () => this.render()); }
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && this.picked) {
        e.preventDefault();
        const main = this.root.querySelector(".pc [data-pc=send]") || this.root.querySelector(".pc [data-pc=copy]");
        if (main && !main.disabled) main.click();
      }
    });
    // só recarrega (e zera os campos) se a sessão mudou de fato: o primeiro aviso, de nenhuma para a mesma
    // sessão que a tela já mostra, chegava depois do usuário digitar e apagava o texto (vt-29 C4)
    this.onCurrent = (e) => {
      const next = e.detail && e.detail.session ? e.detail.session.id : null;
      const shown = this.data && this.data.session ? this.data.session.id : null;
      if (this.data && next === shown) return;
      this.load();
    };
    window.addEventListener("vulcan-current-changed", this.onCurrent);
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.load();
  }

  async load() {
    try {
      this.data = await get("/api/prompts");
      this.values = {};  // sessão nova: os campos não editados voltam aos valores dela; o digitado fica
      keepScroll(this.root, () => this.render());
    } catch (err) {
      reportError(err);
    }
  }

  render() {
    const d = this.data;
    const s = d.session;
    const groups = d.categories.map((c) => ({ ...c, items: d.prompts.filter((p) => p.category === c.name) }));
    this.root.innerHTML = `
      <div class="page ag-page pr-page ${this.picked ? "has-composer" : ""}">
       <div class="pr-main">
        <div class="pr-ctx t-${esc((s && s.theme) || "neutro")}">
          <span class="dot ${s && s.is_active ? "dot-ok" : ""}"></span>
          ${s ? `<span>Os campos vêm preenchidos com <b>${esc(AGENT_NAMES[s.agent] || s.agent)} · ${esc(s.project || "sem projeto")}${s.branch ? ` · ${esc(s.branch)}` : ""}</b>${d.automatic ? ` <span class="dim">(sessão mais recente)</span>` : ""}</span>`
            : `<span class="dim">Nenhuma sessão de agente: você preenche os campos à mão.</span>`}
          <span class="spacer"></span>
          ${s ? `<button class="btn btn-sm" data-action="switch">${icon("restart")}<span>Trocar sessão</span></button>` : ""}
          <button class="btn btn-sm" data-action="new-category">${icon("plus")}<span>Nova categoria</span></button>
          <button class="btn btn-primary btn-sm" data-action="new-prompt">${icon("plus")}<span>Novo prompt</span></button>
        </div>
        ${d.warnings.length ? `<div class="ag-note">${icon("alert")}<div><b>Arquivos ignorados</b><p>${d.warnings.map(esc).join("<br>")}</p></div></div>` : ""}
        ${groups.map((g) => `
          <section class="pr-cat">
            <div class="pr-cat-head"><h3>${esc(g.name)}</h3>${g.user ? `<span class="pr-scope is-user">criada por você</span>` : ""}<span class="count">${g.items.length}</span></div>
            <div class="pr-grid">
              ${g.items.map((p) => this.button(p)).join("")}
              <button type="button" class="pr-btn pr-add" data-action="new-prompt" data-category="${esc(g.name)}">${icon("plus")}<span>Prompt em ${esc(g.name)}</span></button>
            </div>
          </section>`).join("")}
       </div>
       ${this.picked && this.prompt(this.picked) ? `<aside class="pc" aria-label="Compositor do prompt">${this.composer(this.prompt(this.picked))}</aside>` : ""}
      </div>`;
    if (this.picked) this.refreshPreview();
  }

  /** Painel ao lado: um campo por variável (Tab entre eles), prévia com os valores e o alvo. */
  composer(p) {
    const s = this.data.session;
    const values = this.values[p.id] || (this.values[p.id] = Object.fromEntries(p.variables.map((v) => [v,
      this.typed[p.id] && v in this.typed[p.id] ? this.typed[p.id][v] : this.data.context[v] || ""])));
    return `<div class="pc-head"><span class="pr-ic">${icon(p.icon && document.getElementById(`i-${p.icon}`) ? p.icon : "text")}</span>
        <h2>${esc(p.title)}</h2><button type="button" class="icon-btn icon-btn-sm" data-pc="close" aria-label="Fechar o compositor" title="Fechar (Esc)">${icon("x")}</button></div>
      <p class="pc-target">${icon("terminal")}<span>Para: ${s ? `<b>${esc(AGENT_NAMES[s.agent] || s.agent)} · ${esc(s.project || "sem projeto")}${s.branch ? ` · ${esc(s.branch)}` : ""}</b>` : `<b>nenhuma sessão</b>`}</span></p>
      ${p.variables.length ? `<div class="pc-fields">${p.variables.map((v, i) => `<label class="pc-field"><span>${esc(this.label(v))}</span>
          <input class="input" name="${esc(v)}" value="${esc(values[v] || "")}" autocomplete="off" spellcheck="false" ${i === 0 ? "data-first" : ""}
            placeholder="${esc(this.label(v))}"></label>`).join("")}</div>` : ""}
      <div class="pc-label">Texto que vai para o agente</div>
      <div class="pc-preview" aria-live="polite"></div>
      <p class="pc-missing" hidden></p>
      <div class="pc-actions">
        <button type="button" class="btn btn-primary" data-pc="send" title="Cola o texto no terminal do agente (⌘Enter). Você revisa e aperta Enter lá.">${icon("terminal")}<span>Enviar ao terminal</span></button>
        <button type="button" class="btn" data-pc="copy">${icon("copy")}<span>Copiar</span></button>
        <button type="button" class="btn btn-ghost btn-sm" data-pc="edit">${icon("edit")}<span>Editar o arquivo</span></button>
      </div>
      <div class="pc-result" hidden></div>
      <p class="dim hint">O texto entra no campo do agente como colagem, sem apertar Enter: confira no terminal e envie você.</p>
      <p class="dim hint">${p.scope === "project" ? "Prompt do projeto" : "Prompt global"} · ${esc(p.category)}</p>`;
  }

  /** Valores atuais, a prévia e o aviso do que falta. */
  refreshPreview() {
    const p = this.prompt(this.picked);
    const box = this.root.querySelector(".pc");
    if (!p || !box) return null;
    const values = this.values[p.id];
    box.querySelectorAll(".pc-field input").forEach((input) => { values[input.name] = input.value.trim(); });
    box.querySelector(".pc-preview").innerHTML = previewHtml(p.body.trim(), values, (n) => this.label(n));
    const missing = p.variables.filter((v) => !values[v]);
    const note = box.querySelector(".pc-missing");
    note.hidden = !missing.length;
    note.innerHTML = missing.length ? `${icon("alert")}<span>Preencha ${missing.map((m) => `<b>${esc(this.label(m))}</b>`).join(", ")} para enviar.</span>` : "";
    box.querySelectorAll("[data-pc=copy], [data-pc=send]").forEach((b) => { b.disabled = missing.length > 0; });
    return { text: compose(p.body.trim(), values), missing };
  }

  pick(id) {
    this.picked = id;
    keepScroll(this.root, () => this.render());
    const first = this.root.querySelector(".pc [data-first]") || this.root.querySelector(".pc [data-pc=copy]");
    if (first) first.focus();
  }

  label(name) {
    return (this.data.labels && this.data.labels[name]) || name.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/^./, (c) => c.toUpperCase());
  }

  /** Etiqueta "Branch: main"; sem valor, "Branch: a preencher". Nunca o marcador {{nome}}. */
  tag(name) {
    const value = this.data.context[name];
    const shown = value ? (name === "sessionId" ? short(value) : value) : "a preencher";
    return `<span class="pr-tag ${value ? "" : "is-missing"}"><b>${esc(this.label(name))}</b>${esc(shown)}</span>`;
  }

  button(p) {
    const ic = p.icon && document.getElementById(`i-${p.icon}`) ? p.icon : "text";
    return `<button type="button" class="pr-btn ${this.picked === p.id ? "is-on" : ""}" data-pick="${esc(p.id)}" aria-label="${esc(p.title)}: ${esc(p.summary)}">
      <span class="pr-head"><span class="pr-ic">${icon(ic)}</span><span class="pr-title">${esc(p.title)}</span></span>
      <span class="pr-desc">${esc(p.summary)}</span>
      ${p.variables.length ? `<span class="pr-tags">${p.variables.map((v) => this.tag(v)).join("")}</span>` : ""}
      <span class="pr-foot"><span class="pr-scope ${p.scope === "project" ? "is-project" : ""}">${p.scope === "project" ? (p.overrides ? "projeto, sobrescreve" : "projeto") : "global"}</span>
        ${p.pin ? `<span class="dim">fixado no terminal</span>` : ""}
        <span class="pr-go"><span>Usar</span>${icon("chevron-right")}</span></span>
    </button>`;
  }

  prompt(id) {
    return this.data.prompts.find((p) => p.id === id);
  }

  /** vt-27 C3: cola o texto na aba pareada à sessão, sem Enter. Sem aba, oferece retomar a sessão num terminal. */
  async send() {
    const out = this.refreshPreview();
    if (!out || out.missing.length) return;
    const p = this.prompt(this.picked);
    const s = this.data.session;
    const values = this.values[p.id];
    const result = this.root.querySelector(".pc-result");
    try {
      const data = await post("/api/prompts/send", { prompt: p.id, session: s ? s.id : null, values });
      result.hidden = true;
      window.dispatchEvent(new CustomEvent("vulcan-show-terminal", { detail: { id: data.terminal } }));
      toast(`${p.title}: texto colado no terminal. Revise e aperte Enter para enviar.`, { kind: "ok" });
    } catch (err) {
      if (err.status !== 409 || !err.data || !err.data.needs_terminal) return reportError(err);
      result.hidden = false;
      result.innerHTML = `${icon("info")}<span>${err.data.session ? "Esta sessão não tem um terminal aberto e pareado." : "Nenhuma sessão de agente para receber o texto."}</span>
        ${err.data.session ? `<button type="button" class="btn btn-sm btn-primary" data-pc="resume">${icon("play")}<span>Retomar a sessão num terminal</span></button>` : ""}
        <span class="dim">Ou use Copiar e cole com ⌘V.</span>`;
      const resume = result.querySelector("[data-pc=resume]");
      if (resume) resume.addEventListener("click", () => this.resume(err.data.session, result));
    }
    return null;
  }

  async resume(sessionId, result) {
    try {
      const tab = await post(`/api/agents/sessions/${encodeURIComponent(sessionId)}/resume`, {});
      window.dispatchEvent(new CustomEvent("vulcan-show-terminal", { detail: { id: tab.id } }));
      result.innerHTML = `${icon("check")}<span>Terminal aberto com o agente. Quando ele estiver pronto, clique em Enviar ao terminal.</span>`;
    } catch (err) {
      reportError(err);
    }
  }

  async copyComposed() {
    const out = this.refreshPreview();
    if (!out || out.missing.length) return;
    const p = this.prompt(this.picked);
    await copy(out.text, `Copiado: ${p.title}. Cole no terminal com ⌘V.`);
  }

  dialog(html, onSubmit) {
    const backdrop = document.createElement("div");
    backdrop.className = "dialog-backdrop";
    backdrop.innerHTML = html;
    const close = () => backdrop.remove();
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop || e.target.closest("[data-cancel]")) close();
    });
    backdrop.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
    });
    const form = backdrop.querySelector("form");
    if (form) form.addEventListener("submit", (e) => {
      e.preventDefault();
      onSubmit(new FormData(form), close, form);
    });
    document.body.appendChild(backdrop);
    const first = backdrop.querySelector("input");
    if (first) first.focus();
    return backdrop;
  }

  edit(path) {
    post("/api/open", { kind: "prompt", target: path }).catch(reportError);
  }

  newPrompt(category) {
    const d = this.data;
    const projectRoot = d.project.root;
    this.dialog(`
      <form class="dialog" role="dialog" aria-modal="true" aria-labelledby="np-title" autocomplete="off">
        <h2 id="np-title">Novo prompt</h2>
        <label class="field-label" for="np-name">Título</label>
        <input id="np-name" name="title" class="input" maxlength="80" required placeholder="Ex.: Rodar só os testes do módulo">
        <label class="field-label" for="np-cat">Categoria</label>
        <select id="np-cat" name="category" class="select">${d.categories.map((c) => `<option ${c.name === category ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>
        <span class="field-label">Onde</span>
        <div class="segmented" role="radiogroup">
          <label class="seg is-on"><input type="radio" name="scope" value="global" checked hidden>Global</label>
          <label class="seg ${projectRoot ? "" : "is-disabled"}" title="${projectRoot ? esc(d.project.dir) : "sem sessão com projeto"}"><input type="radio" name="scope" value="project" hidden ${projectRoot ? "" : "disabled"}>Só neste projeto</label>
        </div>
        <p class="dim hint">Cria um arquivo .md com cabeçalho e abre no editor. Variáveis: ${d.variables.map((v) => `{{${v}}}`).join(", ")}.
          Campos opcionais do cabeçalho: <code>descricao</code> (o que o cartão mostra) e <code>icone</code>.</p>
        <p class="dim hint">Globais em <code>${esc(d.global_dir)}</code>${projectRoot ? `; do projeto em <code>${esc(d.project.dir)}</code>` : ""}. O do projeto sobrescreve o global de mesmo id.</p>
        <div class="dialog-actions"><button type="button" class="btn" data-cancel>Cancelar</button>
          <button type="submit" class="btn btn-primary">Criar e abrir no editor</button></div>
      </form>`, (form, close, el) => this.create(form, close, el, projectRoot));
    this.bindSegments();
  }

  bindSegments() {
    const box = document.querySelector(".dialog-backdrop:last-child");
    box.querySelectorAll(".segmented label").forEach((label) => label.addEventListener("click", () => {
      if (label.classList.contains("is-disabled")) return;
      box.querySelectorAll(".segmented label").forEach((l) => l.classList.toggle("is-on", l === label));
    }));
  }

  async create(form, close, el, projectRoot, confirmed = false) {
    const body = { title: form.get("title"), category: form.get("category"), scope: form.get("scope") || "global" };
    if (body.scope === "project") Object.assign(body, { project_root: projectRoot, confirm_project_dir: confirmed });
    try {
      const data = await post("/api/prompts", body);
      close();
      toast(`Prompt criado em ${data.path}. Abrindo no editor.`, { kind: "ok" });
      this.edit(data.path);
      this.load();
    } catch (err) {
      if (err.status === 409 && !confirmed) {
        const note = el.querySelector(".pr-confirm") || el.insertBefore(document.createElement("div"), el.querySelector(".dialog-actions"));
        note.className = "pr-confirm";
        note.innerHTML = `${icon("alert")}<span>Isso cria a pasta <code>${esc(this.data.project.dir)}</code> dentro do projeto.</span>
          <button type="button" class="btn btn-sm btn-primary">Criar a pasta e o prompt</button>`;
        note.querySelector("button").addEventListener("click", () => this.create(form, close, el, projectRoot, true));
        return;
      }
      reportError(err);
    }
  }

  newCategory() {
    this.dialog(`
      <form class="dialog" role="dialog" aria-modal="true" aria-labelledby="nc-title" autocomplete="off">
        <h2 id="nc-title">Nova categoria</h2>
        <label class="field-label" for="nc-name">Nome</label>
        <input id="nc-name" name="name" class="input" maxlength="60" required placeholder="Ex.: Laravel">
        <p class="dim hint">Vira uma pasta em ${esc(this.data.global_dir)}. Os prompts dela aparecem como uma nova seção de botões.</p>
        <div class="dialog-actions"><button type="button" class="btn" data-cancel>Cancelar</button>
          <button type="submit" class="btn btn-primary">Criar categoria</button></div>
      </form>`, async (form, close) => {
      try {
        await post("/api/prompts/categories", { name: form.get("name"), scope: "global" });
        close();
        toast(`Categoria ${form.get("name")} criada.`, { kind: "ok" });
        this.load();
      } catch (err) {
        reportError(err);
      }
    });
  }

  onClick(event) {
    const card = event.target.closest("[data-pick]");
    if (card) return this.pick(card.dataset.pick);
    const pc = event.target.closest("[data-pc]");
    if (pc) {
      if (pc.dataset.pc === "close") { this.picked = null; return keepScroll(this.root, () => this.render()); }
      if (pc.dataset.pc === "copy") return this.copyComposed();
      if (pc.dataset.pc === "edit") return this.edit(this.prompt(this.picked).path);
      if (pc.dataset.pc === "send") return this.send();
    }
    const action = event.target.closest("[data-action]");
    if (!action) return null;
    if (action.dataset.action === "new-prompt") this.newPrompt(action.dataset.category || "");
    if (action.dataset.action === "new-category") this.newCategory();
    if (action.dataset.action === "switch") {
      const toggle = document.querySelector("[data-current-toggle]");
      if (toggle) setTimeout(() => toggle.click(), 0);
    }
    return null;
  }

  destroy() {
    window.removeEventListener("vulcan-current-changed", this.onCurrent);
  }
}

