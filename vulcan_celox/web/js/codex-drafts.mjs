// The window owns these drafts. The origin, the approved root and the destination are independent.
const MAX_CODE_POINTS = 4000;

export function validateDraft(raw) {
  const text = raw.replace(/\r\n?/g, "\n");
  for (const char of text) {
    const code = char.codePointAt(0);
    if ((code < 32 && code !== 9 && code !== 10) || (code >= 127 && code <= 159)) return { text, error: "control" };
  }
  if ([...text].length > MAX_CODE_POINTS) return { text, error: "size" };
  return { text, error: text.trim() ? "" : "empty" };
}

const originKey = ({ id, root }) => JSON.stringify([id, root]);

export class Drafts {
  constructor() {
    this.entries = new Map();
    this.origins = new Map();
  }

  read(key, details) {
    if (!this.entries.has(key)) this.entries.set(key, { ...details, text: "" });
    return this.entries.get(key);
  }

  draft(origin) {
    const key = originKey(origin);
    return this.origins.get(key) || this.read(key, { origin, terminal: null, session: null, pairing: null });
  }

  bind(origin, terminal, { session = null, pairing = null } = {}) {
    const from = this.draft(origin);
    const key = JSON.stringify([session ? "session" : "terminal", session || terminal.id, origin.root]);
    const to = this.read(key, { origin, terminal, session, pairing });
    if (!from.terminal) this.transfer(from, to);
    to.terminal = terminal;
    to.pairing = pairing;
    this.origins.set(originKey(origin), to);
    return to;
  }

  transfer(source, destination) {
    if (!source.text || !destination || destination.text || source === destination) return false;
    destination.text = source.text;
    source.text = "";
    return true;
  }

  list() {
    return [...this.entries.values()].filter((draft) => draft.text !== "");
  }
}

export const drafts = new Drafts();
