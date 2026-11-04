// Notices that programs send through the terminal itself (OSC 9, 99 and 777 and the bell). Works with any program.
// The text comes from the program running in the tab, so it is always data: it goes through cleanText and never becomes markup.

const MAX_TEXT = 200;
const MIN_INTERVAL_MS = 5000;

export function cleanText(raw) {
  return String(raw == null ? "" : raw).replace(/[\u0000-\u001f\u007f-\u009f]/g, " ").replace(/\s+/g, " ").trim().slice(0, MAX_TEXT);
}

/** Notice text, or null when the sequence is not a notice (`9;4` is the progress bar, not a message). */
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

/** At most one notice per tab every `interval` ms: a looping program must not flood the interface. */
export function rateLimiter(interval = MIN_INTERVAL_MS, clock = Date.now) {
  const last = new Map();
  return (id) => {
    const now = clock();
    if (last.has(id) && now - last.get(id) < interval) return false;
    last.set(id, now);
    return true;
  };
}

/** Wires up the notices of an xterm tab. `report(id, texto)` receives only what passed the filter and the limit. */
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
