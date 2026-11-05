// Pure logic of the live Code screen: which lines changed, the mark of each path and when to jump to a file. No DOM.

const MAX_LINES = 5000;
const MAX_TABLE = 4000000;

/** Lines of `next` (1-based) that differ from `prev`. Above 5,000 lines, or with too large a changed region to compare,
 * it returns the whole stretch between the common start and the common end. */
export function changedLines(prev, next) {
  if (prev === next) return [];
  const a = prev.split("\n");
  const b = next.split("\n");
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start += 1;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
    endA -= 1;
    endB -= 1;
  }
  const region = () => {
    const out = [];
    for (let i = start; i < endB; i += 1) out.push(i + 1);
    return out;
  };
  if (endA === start) return region();  // only additions
  if (endB === start) return [Math.min(start + 1, b.length)];  // only removals: the line where they were
  const n = endA - start;
  const m = endB - start;
  if (a.length > MAX_LINES || b.length > MAX_LINES || n * m > MAX_TABLE) return region();
  // longest common subsequence of the middle: what is not in it was written now
  const w = m + 1;
  const table = new Uint16Array((n + 1) * w);
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      table[i * w + j] = a[start + i] === b[start + j]
        ? table[(i + 1) * w + j + 1] + 1
        : Math.max(table[(i + 1) * w + j], table[i * w + j + 1]);
    }
  }
  const out = [];
  let i = 0;
  let j = 0;
  while (j < m) {
    if (i < n && a[start + i] === b[start + j]) {
      i += 1;
      j += 1;
    } else if (i < n && table[(i + 1) * w + j] >= table[i * w + j + 1]) {
      i += 1;
    } else {
      out.push(start + j + 1);
      j += 1;
    }
  }
  return out.length ? out : [Math.min(start + 1, b.length)];
}

/** Mark of a path relative to the opening photo, after one more change. null: back to how it was at the opening. */
export function nextMark(mark, change) {
  if (change === "added") return mark === "D" ? "M" : "A";
  if (change === "deleted") return mark === "A" ? null : "D";
  return mark === "A" ? "A" : "M";
}

export function ancestors(rel) {
  const parts = rel.split("/");
  const out = [];
  for (let i = 1; i < parts.length; i += 1) out.push(parts.slice(0, i).join("/"));
  return out;
}

export class Marks {
  constructor() {
    this.items = new Map();  // rel -> { mark, agent }
  }

  apply(event) {
    const before = this.items.get(event.rel);
    const mark = nextMark(before ? before.mark : null, event.change);
    if (mark) this.items.set(event.rel, { mark, agent: event.agent || (before && before.agent) || null });
    else this.items.delete(event.rel);
    return mark;
  }

  /** The record of the agent may arrive after the write. */
  attribute(rel, agent) {
    const item = this.items.get(rel);
    if (!item || (item.agent && item.agent.session === agent.session)) return false;
    item.agent = agent;
    return true;
  }

  get(rel) {
    return this.items.get(rel) || null;
  }

  /** A folder holding something marked: it shows a dot while collapsed. */
  hasInside(folder) {
    const prefix = `${folder}/`;
    for (const rel of this.items.keys()) if (rel.startsWith(prefix)) return true;
    return false;
  }

  clear() {
    this.items.clear();
  }
}

/** During a burst it waits `quiet` ms without changes and stays at least `dwell` ms in each file. Time comes from outside, for the test. */
export class FollowPacer {
  constructor({ quiet = 300, dwell = 1500 } = {}) {
    this.quiet = quiet;
    this.dwell = dwell;
    this.pending = null;
    this.lastEvent = 0;
    this.lastShown = -Infinity;
  }

  /** A followable file changed. */
  push(rel, now) {
    this.pending = rel;
    this.lastEvent = now;
  }

  /** The file to go to now, if any. The caller reports back with `shown`. */
  due(now) {
    if (!this.pending) return null;
    if (now - this.lastEvent < this.quiet || now - this.lastShown < this.dwell) return null;
    const rel = this.pending;
    this.pending = null;
    return rel;
  }

  shown(now) {
    this.lastShown = now;
  }

  reset() {
    this.pending = null;
  }
}
