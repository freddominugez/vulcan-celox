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
const destinationKey = (draft, root) => JSON.stringify([draft.session ? "session" : "terminal", draft.session || draft.terminal.id, root]);

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
    this.adopt(origin);
    return this.origins.get(key) || this.read(key, { origin, terminal: null, session: null, pairing: null });
  }

  // A null root is not a root. When the same tab gets its first root, its own drafts change key ([id, null] -> [id, root]
  // and [kind, destination, null] -> [kind, destination, root]): nothing moves between drafts, and two non-null roots never
  // share one. A slot that already holds text is left alone.
  adopt(origin) {
    if (origin.root == null) return;
    const before = originKey({ id: origin.id, root: null });
    const after = originKey(origin);
    const free = (key) => !this.entries.has(key) || this.entries.get(key).text === "";
    const bound = this.origins.get(before);
    if (bound && !this.origins.has(after)) {
      const from = destinationKey(bound, null);
      const to = destinationKey(bound, origin.root);
      if (this.entries.get(from) === bound && free(to)) {
        this.entries.delete(from);
        this.entries.set(to, bound);
        bound.origin = { ...bound.origin, root: origin.root };
      }
      if (this.entries.get(to) === bound) {
        this.origins.delete(before);
        this.origins.set(after, bound);
      }
    }
    const loose = this.entries.get(before);
    if (loose && !loose.terminal && loose.text && !this.origins.has(after) && free(after)) {
      this.entries.delete(before);
      this.entries.set(after, loose);
      loose.origin = { ...loose.origin, root: origin.root };
    }
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
