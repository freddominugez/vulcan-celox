// Decides when the viewer follows the agent. No DOM: the caller touches the screen only if `next` says so. Scrolling done by the
// viewer itself does not pass through here, so only user interaction pauses.

export class Follow {
  constructor(active = false, lastSeq = 0) {
    this.active = active;
    this.paused = false;
    this.lastSeq = lastSeq;
  }

  /** A stopped session has nothing to follow; when it runs again, the pause the user chose is respected. */
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

  /** Is there a new edit and should we go to it? An edit seen during the pause stays counted, and `resume` goes to the last one. */
  next(lastSeq) {
    const fresh = lastSeq > this.lastSeq;
    this.lastSeq = Math.max(this.lastSeq, lastSeq);
    return fresh && this.state === "following";
  }
}
