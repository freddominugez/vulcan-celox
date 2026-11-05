// Asks the server what changed on disk: every second, every 5 s with the window in the background. On error it tries again
// more slowly, with no repeated message: the tree keeps showing what it knows.

import { get } from "../../api.mjs";
import { query } from "./explorer-viewer.mjs";

const FOREGROUND = 1000;
const BACKGROUND = 5000;
const SLOWEST = 15000;
const MAX_FOLDERS = 100;

export class LivePoll {
  constructor(root, scope, onData) {
    this.root = root;
    this.scope = scope;
    this.onData = onData;
    this.cursor = null;
    this.failures = 0;
    this.stopped = false;
    this.timer = null;
    this.onVisible = () => {
      if (!document.hidden && !this.stopped) this.schedule(0);
    };
    document.addEventListener("visibilitychange", this.onVisible);
    this.schedule(0);
  }

  schedule(ms) {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.tick(), ms);
  }

  url() {
    const { file, open } = this.scope();
    const params = { root: this.root };
    if (this.cursor !== null) params.since = this.cursor;
    if (file) params.file = file;
    const folders = open.slice(-MAX_FOLDERS).map((f) => `&open=${encodeURIComponent(f)}`).join("");
    return `/api/files/changes?${query(params)}${folders}`;
  }

  async tick() {
    if (this.stopped || this.busy) return;
    this.busy = true;
    try {
      const data = await get(this.url());
      if (this.stopped) return;
      this.cursor = data.cursor;
      this.failures = 0;
      await this.onData(data);
      if (data.missing) return;
    } catch (_) {
      this.failures += 1;
    } finally {
      this.busy = false;
    }
    if (this.stopped) return;
    const base = document.hidden ? BACKGROUND : FOREGROUND;
    this.schedule(this.failures ? Math.min(SLOWEST, base * 2 ** this.failures) : base);
  }

  stop() {
    this.stopped = true;
    clearTimeout(this.timer);
    document.removeEventListener("visibilitychange", this.onVisible);
  }
}
