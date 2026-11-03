// Tela Início: guia de quatro passos que se confere sozinho, a captura da Visão geral com o destaque do
// passo escolhido e um cartão por área da interface. Aparece na abertura até os passos estarem feitos ou o usuário
// marcar "Não mostrar mais o guia"; depois fica em Início e em Ajuda.

import { get, put } from "../api.mjs";
import { esc, icon, reportError } from "../dom.mjs";

// destaques sobre img/manual/visao-geral.png (porcentagens da captura gerada por scripts/manual_shots.sh)
export const SPOTS = {
  lerd: { box: [73.6, 1.0, 16.7, 3.0], text: "O estado do Lerd fica no alto, à direita: verde quando nginx, DNS .test e PHP respondem. O item Lerd da barra lateral leva à tela dele." },
  projetos: { box: [19.1, 7.3, 49.6, 30.0], text: "Sites PHP do Lerd e projetos Node aparecem na Visão geral. Clique num deles para abrir a página do projeto." },
  agentes: { box: [0.5, 35.4, 16.1, 19.0], text: "Sessões dos agentes, prompts, uso e custo, branches e histórico ficam no grupo Agentes da barra lateral." },
  terminal: { box: [17.4, 69.0, 82.6, 31.0], text: "O painel de terminal fica embaixo (⌘J mostra ou esconde). ⌘T abre um terminal novo na pasta escolhida." },
  organizar: { box: [70.0, 7.3, 28.3, 11.0], text: "Tarefas abertas aparecem na Visão geral. Tarefas, post-its, tags e índice ficam no grupo Organizar da barra lateral." },
};

export const AREAS = [
  { id: "projetos", icon: "globe", title: "Projetos", text: "Sites PHP do Lerd e projetos Node: abrir, ligar o servidor, ver logs e a depuração.", go: "#/overview" },
  { id: "terminal", icon: "terminal", title: "Terminais", text: "Um terminal por projeto, com tarefas e notas que viram memória em Markdown.", go: "#/terminals" },
  { id: "lerd", icon: "database", title: "Lerd", text: "PHP, nginx, banco e HTTPS local dos sites. Ligar, parar e ver o que está rodando.", go: "#/lerd" },
  { id: "agentes", icon: "spark", title: "Agentes", text: "Sessões do Claude Code e do Codex lidas do disco, com custo estimado e branches.", go: "#/agentes" },
  { id: "agentes", icon: "text", title: "Prompts", text: "Instruções prontas preenchidas com a sessão atual, para mandar ao agente.", go: "#/prompts" },
  { id: "organizar", icon: "check-square", title: "Organizar", text: "Tarefas, post-its, tags e o índice de tudo o que foi feito em cada projeto.", go: "#/tasks" },
];

export class HomeView {
  constructor(root, options) {
    this.root = root;
    this.options = options;
    this.spot = null;
    this.root.addEventListener("click", (e) => this.onClick(e));
    this.root.addEventListener("keydown", (e) => this.onKey(e));
    this.root.innerHTML = `<div class="loading"><span class="skeleton w-40"></span><span class="skeleton w-70"></span></div>`;
    this.load();
  }

  async load() {
    try {
      this.guide = await get("/api/guide");
      if (!this.spot) {
        const next = this.guide.steps.find((s) => !s.ok);
        this.spot = next ? next.id : "projetos";
      }
      this.render();
      // o índice dos agentes ainda está na primeira leitura: confere de novo em instantes (até 40 vezes)
      if (this.guide.steps.some((st) => st.lendo) && (this.retries = (this.retries || 0) + 1) <= 40) {
        this.timer = setTimeout(() => this.load(), 500);
      }
    } catch (err) {
      reportError(err);
    }
  }

  destroy() {
    clearTimeout(this.timer);
  }

  greeting() {
    const h = new Date().getHours();
    return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
  }

  render() {
    const g = this.guide;
    const missing = g.steps.filter((s) => !s.ok).length;
    const head = g.done ? "Tudo pronto. Os quatro passos estão feitos."
      : `Falta${missing === 1 ? "" : "m"} ${missing} ${missing === 1 ? "passo" : "passos"} para tudo funcionar.`;
    const spot = SPOTS[this.spot] || SPOTS.projetos;
    const [x, y, w, h] = spot.box;
    const action = {
      lerd: `<button class="btn btn-sm" data-service="start">${icon("play")}<span>Ligar</span></button>`,
      projetos: `<button class="btn btn-sm" data-go="#/node">${icon("plus")}<span>Adicionar</span></button>`,
      agentes: `<button class="btn btn-sm" data-go="#/agentes">${icon("spark")}<span>Ver agentes</span></button>`,
      terminal: `<button class="btn btn-primary btn-sm" data-home="terminal">${icon("terminal")}<span>Abrir terminal</span></button>`,
    };
    this.root.innerHTML = `<div class="page in-page">
      <div class="in-hello">
        <div class="in-left">
          <h1>${this.greeting()}. ${esc(head)}</h1>
          <p class="dim">${g.done ? "O guia sai da abertura do app. Ele continua aqui e em Ajuda." : "O guia confere sozinho o que já está pronto e some da abertura quando terminar."}</p>
          <label class="in-dismiss"><input type="checkbox" data-home="dismiss" ${g.skipped ? "checked" : ""}>
            <span>Não mostrar mais o guia <span class="dim">(o app abre na Visão geral; o guia continua em Início e em Ajuda)</span></span></label>
          <ol class="in-steps">${g.steps.map((s, i) => `<li class="in-step ${s.ok ? "is-done" : ""} ${s.id === this.spot ? "is-on" : ""}" data-spot="${s.id}" tabindex="0">
            <span class="in-ck" aria-hidden="true">${s.ok ? icon("check") : i + 1}</span>
            <span class="in-step-main"><b>${esc(s.title)}</b><span class="dim">${esc(s.detail)}</span></span>
            ${s.ok ? `<span class="sr-only">feito</span>` : action[s.id] || ""}</li>`).join("")}</ol>
        </div>
        <figure class="in-shot">
          <div class="in-shot-frame"><img src="img/manual/visao-geral.png" alt="Captura da Visão geral do Vulcan Terminal com a área do passo escolhido destacada">
            <span class="in-hl" style="left:${x}%;top:${y}%;width:${w}%;height:${h}%"></span></div>
          <figcaption>${esc(spot.text)}</figcaption>
        </figure>
      </div>
      <h2 class="in-sub">O que cada parte faz</h2>
      <div class="in-areas">${AREAS.map((a) => `<a class="in-area" href="${a.go}" data-spot-hover="${a.id}">
          <span class="in-ic">${icon(a.icon)}</span><b>${esc(a.title)}</b><span class="dim">${esc(a.text)}</span></a>`).join("")}</div>
      <p class="dim in-help">Dúvidas? Abra <a href="#/ajuda" data-go="#/ajuda">Ajuda</a> (⌘?) ou use o botão ? no alto de cada tela.</p>
    </div>`;
  }

  // O passo tem tabindex, então responde a Enter e Espaço como ao clique
  onKey(event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    const step = event.target.closest && event.target.closest("[data-spot]");
    if (!step || event.target !== step) return;  // botão ou link dentro do passo segue o próprio comportamento
    event.preventDefault();
    this.pick(step.dataset.spot, true);
  }

  // redesenha com o passo escolhido e, se o foco estava nele, devolve o foco ao passo novo
  pick(spot, keepFocus) {
    this.spot = spot;
    this.render();
    if (keepFocus) {
      const again = this.root.querySelector(`[data-spot="${CSS.escape(spot)}"]`);
      if (again) again.focus();
    }
  }

  async onClick(event) {
    const step = event.target.closest("[data-spot]");
    const btn = event.target.closest("[data-home]");
    try {
      if (btn && btn.dataset.home === "dismiss") {
        this.guide = await put("/api/guide", { skipped: btn.checked });
        return this.render();
      }
      if (btn && btn.dataset.home === "terminal") {
        if (window.vulcanCommand) await window.vulcanCommand("newTerminal");
        return setTimeout(() => this.load(), 1500);
      }
      if (step && !event.target.closest("button")) this.pick(step.dataset.spot, step.contains(document.activeElement));
    } catch (err) {
      reportError(err);
    }
    return null;
  }
}
