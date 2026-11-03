// Avisos que os programas mandam pelo próprio terminal (OSC 9, 99 e 777 e o sino). Funciona com qualquer programa.
// O texto vem do programa que roda na aba, então é sempre dado: passa por cleanText e nunca vira marcação.

const MAX_TEXT = 200;
const MIN_INTERVAL_MS = 5000;

export function cleanText(raw) {
  return String(raw == null ? "" : raw).replace(/[\u0000-\u001f\u007f-\u009f]/g, " ").replace(/\s+/g, " ").trim().slice(0, MAX_TEXT);
}

/** Texto do aviso, ou null quando a sequência não é um aviso (`9;4` é a barra de progresso, não uma mensagem). */
export function oscMessage(code, data) {
  const text = String(data == null ? "" : data);
  if (code === 9) return /^4(;|$)/.test(text) ? null : cleanText(text);
  if (code === 99) return cleanText(text.slice(text.indexOf(";") + 1));
  if (code === 777) {
    const [kind, title, body] = text.split(";");
    return kind === "notify" ? cleanText([title, body].filter(Boolean).join(": ")) : null;
  }
  return null;
}

/** No máximo um aviso por aba a cada `interval` ms: um programa em laço não pode inundar a interface. */
export function rateLimiter(interval = MIN_INTERVAL_MS, clock = Date.now) {
  const last = new Map();
  return (id) => {
    const now = clock();
    if (last.has(id) && now - last.get(id) < interval) return false;
    last.set(id, now);
    return true;
  };
}

/** Liga os avisos de uma aba do xterm. `report(id, texto)` recebe só o que passou pelo filtro e pelo limite. */
export function watchTerminal(term, id, report, allow = rateLimiter()) {
  const send = (text) => { if (allow(id)) report(id, text); };
  for (const code of [9, 99, 777]) {
    term.parser.registerOscHandler(code, (data) => {
      const text = oscMessage(code, data);
      if (text !== null) send(text);
      return true;
    });
  }
  term.onBell(() => send(""));
}
