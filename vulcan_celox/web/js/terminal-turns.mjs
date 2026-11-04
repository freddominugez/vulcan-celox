// Requests made to the agent in a tab: an xterm marker on every Enter, and ⌘⇧↑/↓ jumps between them. Nothing is drawn in the terminal
// area. No dependency on another app module, so it also runs in the test.

export class TurnMarks {
  /** `isAgent()` says, after Enter, whether the tab runs a live agent; `warn` notifies once that there is nothing to navigate. */
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

  /** The alternate screen keeps no history, so it gets no marker. The marker is created right at Enter, otherwise the right line shifts before the answer. */
  enter() {
    if (this.alternate()) return Promise.resolve(null);
    const marker = this.term.registerMarker(0);
    if (!marker) return Promise.resolve(null);
    this.marks.push(marker);
    marker.onDispose(() => this.forget(marker));
    return Promise.resolve(this.isAgent()).then((yes) => {
      if (!yes) marker.dispose();
      return yes ? marker : null;
    }, () => marker);  // no way to know: the marker stays, and it draws nothing
  }

  forget(marker) {
    this.marks = this.marks.filter((m) => m !== marker);
  }

  /** Live markers, in order. One that left the history (line -1 or disposed) does not count. */
  lines() {
    return this.marks.filter((m) => !m.isDisposed && m.line >= 0).map((m) => m.line).sort((a, b) => a - b);
  }

  /** Scrolls to the previous (-1) or next (1) marker. Returns the line, or null if it did not move. */
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
