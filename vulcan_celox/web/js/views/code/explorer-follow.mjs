// The Following button of the Code screen. The decision comes from Follow, with the watcher's cursor as the sequence: any gesture
// pauses, and one click resumes going to the last change. Only readable text that is neither sensitive nor ignored is followed.

import { icon } from "../../dom.mjs";
import { t } from "../../i18n.mjs";
import { Follow } from "./code-follow.mjs";
import { FollowPacer } from "./code-live.mjs";

const TICK = 100;

export class ExplorerFollow {
  constructor(button, go) {
    this.button = button;
    this.go = go;
    this.follow = new Follow(true, 0);
    this.pacer = new FollowPacer();
    this.last = null;
    this.render();
    this.timer = setInterval(() => this.tick(), TICK);
  }

  get following() {
    return this.follow.state === "following";
  }

  render() {
    const paused = !this.following;
    this.button.classList.toggle("is-paused", paused);
    this.button.setAttribute("aria-pressed", String(!paused));
    this.button.title = paused ? t("Voltar a acompanhar: vai à última mudança") : t("O visor vai ao arquivo que acabou de mudar. Qualquer gesto pausa.");
    this.button.innerHTML = `<span class="ce-follow-dot"></span>${paused ? icon("play") : ""}<span>${paused ? t("Pausado") : t("Acompanhando")}</span>`;
  }

  /** New changes from the server. The open file reloads anyway; here only the jump to another file is decided. */
  events(list, cursor, openPath) {
    const usable = list.filter((e) => e.kind === "file" && e.change !== "deleted" && !e.sensitive && !e.ignored);
    if (usable.length) this.last = usable[usable.length - 1].rel;
    const go = this.follow.next(cursor);
    if (go && usable.length && this.last !== openPath) this.pacer.push(this.last, performance.now());
  }

  tick() {
    if (!this.following) return;
    const rel = this.pacer.due(performance.now());
    if (!rel) return;
    this.pacer.shown(performance.now());
    this.go(rel);
  }

  gesture() {
    if (!this.following) return;
    this.follow.userInteracted();
    this.pacer.reset();
    this.render();
  }

  toggle() {
    if (this.following) return this.gesture();
    this.follow.resume();
    this.render();
    if (this.last) {
      this.pacer.shown(performance.now());
      this.go(this.last);
    }
    return undefined;
  }

  /** Another folder: the button state stays, the references do not. */
  reset() {
    this.last = null;
    this.pacer.reset();
    this.follow.lastSeq = 0;
  }

  destroy() {
    clearInterval(this.timer);
  }
}
