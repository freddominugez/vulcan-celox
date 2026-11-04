// Local API client. The token comes from the native shell (window.VULCAN) or from the hash in browser mode.

function stored(value) {
  // sessionStorage may be blocked in browser mode: the token just does not survive a reload
  try {
    if (value === undefined) return sessionStorage.getItem("vulcan-token") || "";
    sessionStorage.setItem("vulcan-token", value);
  } catch (_) { /* no storage */ }
  return value || "";
}

function readToken() {
  if (window.VULCAN && window.VULCAN.token) return window.VULCAN.token;
  const match = /token=([^&]+)/.exec(location.hash) || /token=([^&]+)/.exec(location.search);
  if (match) {
    stored(match[1]);
    // removes the token from the address bar and history; the Linux launcher sends the route in route=
    const route = /route=([^&]+)/.exec(location.hash);
    history.replaceState(null, "", `${location.pathname}#${route ? route[1] : "/overview"}`);
    return match[1];
  }
  return stored();
}

export const token = readToken();
export const isNative = Boolean(window.VULCAN && window.VULCAN.native);
/** There is a bridge to the shell (Swift on macOS, GTK on Linux): folder picker, detached windows. */
export const hasBridge = Boolean(window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.vulcan);
export const isMac = /Mac/.test(navigator.platform || navigator.userAgent);

export class ApiError extends Error {
  constructor(status, message, data = null) {
    super(message);
    this.status = status;
    this.data = data;  // error body, with the extra fields from the server (e.g. needs_terminal)
  }
}

const TIMEOUT_MS = 20000;

export async function api(path, { method = "GET", body, timeout = TIMEOUT_MS } = {}) {
  // deadline: a busy server does not leave queries piling up forever
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), timeout);
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: { "X-Vulcan-Token": token, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: abort.signal,
    });
  } catch (err) {
    if (err && err.name === "AbortError") throw new ApiError(0, "o servidor local não respondeu a tempo");
    throw err;
  } finally {
    clearTimeout(timer);
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    throw new ApiError(response.status, (data && data.error) || `erro ${response.status}`, data);
  }
  return data;
}

export const get = (path) => api(path);
export const post = (path, body = {}) => api(path, { method: "POST", body });
export const patch = (path, body = {}) => api(path, { method: "PATCH", body });
export const put = (path, body = {}) => api(path, { method: "PUT", body });
export const del = (path) => api(path, { method: "DELETE" });

/** Repeats `fn` every `ms` after the previous one finished, and does not poll while the window is hidden.
  *  Returns the function that stops it. */
export function every(ms, fn) {
  let timer = null;
  let stopped = false;
  const tick = async () => {
    if (stopped) return;
    if (!document.hidden) {
      try {
        await fn();
      } catch {
        /* the caller handles the error; the repetition continues */
      }
    }
    if (!stopped) timer = setTimeout(tick, ms);
  };
  timer = setTimeout(tick, ms);
  return () => {
    stopped = true;
    clearTimeout(timer);
  };
}

export function wsUrl(path) {
  const sep = path.includes("?") ? "&" : "?";
  return `ws://${location.host}${path}${sep}token=${encodeURIComponent(token)}`;
}

export function native(message) {
  const handler = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.vulcan;
  if (handler) {
    handler.postMessage(message);
    return true;
  }
  return false;
}
