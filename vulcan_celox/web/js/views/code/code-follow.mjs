// Decide quando o visor acompanha o agente. Sem DOM: quem chama mexe na tela só se `next` mandar. Rolagem feita pelo
// próprio visor não passa por aqui, então só a interação do usuário pausa.

export class Follow {
  constructor(active = false, lastSeq = 0) {
    this.active = active;
    this.paused = false;
    this.lastSeq = lastSeq;
  }

  /** Sessão parada não tem o que seguir; ao voltar a rodar, respeita a pausa que o usuário escolheu. */
  setActive(active) {
    this.active = Boolean(active);
    if (!this.active) this.paused = false;
  }

  get state() {
    if (!this.active) return "off";
    return this.paused ? "paused" : "following";
  }

  userInteracted() {
    if (this.active) this.paused = true;
  }

  resume() {
    this.paused = false;
  }

  /** Há edição nova e é para ir até ela? A edição vista durante a pausa fica contada, e `resume` leva até a última. */
  next(lastSeq) {
    const fresh = lastSeq > this.lastSeq;
    this.lastSeq = Math.max(this.lastSeq, lastSeq);
    return fresh && this.state === "following";
  }
}
