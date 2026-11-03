// Pedidos feitos ao agente numa aba: uma marca do xterm a cada Enter, e ⌘⇧↑/↓ salta entre elas. Nada é desenhado na área
// do terminal. Sem dependência de outro módulo do app, para rodar também no teste.

export class TurnMarks {
  /** `isAgent()` diz, depois do Enter, se a aba roda um agente vivo; `warn` avisa uma vez que não há o que navegar. */
  constructor(term, { isAgent = () => Promise.resolve(true), warn = () => {} } = {}) {
    this.term = term;
    this.isAgent = isAgent;
    this.warn = warn;
    this.marks = [];
    this.warned = false;
  }

  alternate() {
    return this.term.buffer.active.type === "alternate";
  }

  /** Tela alternativa não tem histórico: nem marca. A marca nasce já no Enter, senão a linha certa muda antes da resposta. */
  enter() {
    if (this.alternate()) return Promise.resolve(null);
    const marker = this.term.registerMarker(0);
    if (!marker) return Promise.resolve(null);
    this.marks.push(marker);
    marker.onDispose(() => this.forget(marker));
    return Promise.resolve(this.isAgent()).then((yes) => {
      if (!yes) marker.dispose();
      return yes ? marker : null;
    }, () => marker);  // sem como saber: fica a marca, que não desenha nada
  }

  forget(marker) {
    this.marks = this.marks.filter((m) => m !== marker);
  }

  /** Marcas vivas, em ordem. A que saiu do histórico (linha -1 ou descartada) não conta. */
  lines() {
    return this.marks.filter((m) => !m.isDisposed && m.line >= 0).map((m) => m.line).sort((a, b) => a - b);
  }

  /** Rola até a marca anterior (-1) ou seguinte (1). Devolve a linha, ou null se não saiu do lugar. */
  step(direction) {
    if (this.alternate()) {
      if (!this.warned) this.warn();
      this.warned = true;
      return null;
    }
    const here = this.term.buffer.active.viewportY;
    const lines = this.lines();
    const target = direction < 0 ? lines.filter((l) => l < here).pop() : lines.find((l) => l > here);
    if (target === undefined) return null;
    this.term.scrollToLine(target);
    return target;
  }
}
