// Who is waiting for you now: agent sessions (from the server) and tabs that signaled through their own terminal.
// The app marks tabs, panels and the sidebar, and the notice disappears when the tab is focused or the session opened.

import { get } from "./api.mjs";
import { t } from "./i18n.mjs";

const POLL_MS = 3000;
export const ATTENTION_LABELS = { your_turn: t("sua vez"), maybe_waiting: t("talvez esperando"), waiting_permission: t("pedindo permissão") };

const dismissed = new Map();  // session -> `since` already seen
const fromTerminal = new Map();  // aba -> { text, at }
let sessions = [];
let first = true;
let listeners = [];

/** Sessions not yet seen. One already in "sua vez" when the app opened does not count: it would be a stale notice. */
export function unreadSessions(items, seen, isFirst) {
  if (isFirst) items.forEach((s) => { if (s.state === "your_turn") seen.set(s.session, s.since); });
  return items.filter((s) => seen.get(s.session) !== s.since);
}

function unread() {
  return unreadSessions(sessions, dismissed, false);
}

export function attentionCount() {
  return unread().length + [...fromTerminal.keys()].filter((id) => !unread().some((s) => s.terminal_id === id)).length;
}

function activeTabId() {
  const tab = document.querySelector(".tab.is-active[data-id]");
  return tab ? tab.dataset.id : null;
}

function labelFor(id) {
  const session = unread().find((s) => s.terminal_id === id);
  if (session) return `${session.project || t("Sessão")}: ${ATTENTION_LABELS[session.state]}`;
  const local = fromTerminal.get(id);
  return local ? (local.text || t("A aba pediu atenção")) : "";
}

/** Reapplies the marks: called on every read and after the tab bar is redrawn. */
export function syncTabs() {
  document.querySelectorAll(".tab[data-id]").forEach((tab) => {
    const label = labelFor(tab.dataset.id);
    tab.classList.toggle("has-attention", Boolean(label));
    if (label) tab.dataset.attention = label;
    else delete tab.dataset.attention;
    tab.setAttribute("aria-description", label);
  });
  document.querySelectorAll(".xterm-host[data-tab-id]").forEach((host) => {
    host.classList.toggle("has-attention", Boolean(labelFor(host.dataset.tabId)));
  });
}

function changed() {
  syncTabs();
  window.dispatchEvent(new CustomEvent("vulcan-attention"));
}

export function attentionTerminal(id, text) {
  if (id === activeTabId() && document.hasFocus()) return;  // the user is already looking at this tab
  fromTerminal.set(id, { text, at: Date.now() });
  listeners.forEach((f) => f({ kind: "terminal", id, text }));
  changed();
}

export function clearTab(id) {
  fromTerminal.delete(id);
  sessions.filter((s) => s.terminal_id === id).forEach((s) => dismissed.set(s.session, s.since));
  changed();
}

export function dismissSession(id) {
  sessions.filter((s) => s.session === id).forEach((s) => dismissed.set(s.session, s.since));
  changed();
}

/** State of a session to show on the card, or "" if already seen. */
export function sessionAttention(id) {
  const found = unread().find((s) => s.session === id);
  return found ? ATTENTION_LABELS[found.state] : "";
}

/** The most recent notice, for the shortcut: { tab, session }. */
export function latestAttention() {
  const best = [...unread()].sort((a, b) => String(b.since).localeCompare(String(a.since)))[0];
  if (best) return { tab: best.terminal_id || null, session: best.session };
  const local = [...fromTerminal.entries()].sort((a, b) => b[1].at - a[1].at)[0];
  return local ? { tab: local[0], session: null } : null;
}

export function onAttention(listener) {
  listeners.push(listener);
}

async function poll() {
  try {
    const known = new Set(unread().map((s) => `${s.session}|${s.since}`));
    const data = await get("/api/agents/attention");
    sessions = data.items || [];
    unreadSessions(sessions, dismissed, first);
    first = false;
    const active = activeTabId();
    if (document.hasFocus()) sessions.filter((s) => s.terminal_id && s.terminal_id === active).forEach((s) => dismissed.set(s.session, s.since));
    unread().filter((s) => !known.has(`${s.session}|${s.since}`)).forEach((s) => listeners.forEach((f) => f({ kind: "session", item: s })));
    changed();
  } catch {
    // server restarting: the next round tries again, without notice
  }
}

export function startAttention() {
  poll();
  setInterval(poll, POLL_MS);
  window.addEventListener("focus", () => {
    const id = activeTabId();
    if (id) clearTab(id);
  });
}
