// Cliente da API local. O token chega pela casca nativa (window.VULCAN) ou pelo hash em modo navegador.

function stored(value) {
  // sessionStorage pode estar bloqueado no modo navegador: o token só não sobrevive ao recarregar
  try {
    if (value === undefined) return sessionStorage.getItem("vulcan-token") || "";
    sessionStorage.setItem("vulcan-token", value);
  } catch (_) { /* sem armazenamento */ }
  return value || "";
}

function readToken() {
  if (window.VULCAN && window.VULCAN.token) return window.VULCAN.token;
  const match = /token=([^&]+)/.exec(location.hash) || /token=([^&]+)/.exec(location.search);
  if (match) {
    stored(match[1]);
    // tira o token da barra e do histórico (vt-20 C4); o lançador do Linux manda a rota em route=
    const route = /route=([^&]+)/.exec(location.hash);
    history.replaceState(null, "", `${location.pathname}#${route ? route[1] : "/overview"}`);
    return match[1];
  }
  return stored();
}

export const token = readToken();
export const isNative = Boolean(window.VULCAN && window.VULCAN.native);
/** Há ponte com a casca (Swift no macOS, GTK no Linux): seletor de pasta, janelas destacadas. */
export const hasBridge = Boolean(window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.vulcan);
export const isMac = /Mac/.test(navigator.platform || navigator.userAgent);

export class ApiError extends Error {
  constructor(status, message, data = null) {
    super(message);
    this.status = status;
    this.data = data;  // corpo do erro, com os campos a mais do servidor (ex.: needs_terminal)
  }
}

const TIMEOUT_MS = 20000;

export async function api(path, { method = "GET", body, timeout = TIMEOUT_MS } = {}) {
  // prazo: um servidor ocupado não deixa consultas empilhadas para sempre (vt-20 C8)
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

/** Repete `fn` a cada `ms` depois que a anterior terminou, e não consulta com a janela oculta (vt-20 C8).
 *  Devolve a função que para. */
export function every(ms, fn) {
  let timer = null;
  let stopped = false;
  const tick = async () => {
    if (stopped) return;
    if (!document.hidden) {
      try {
        await fn();
      } catch {
        /* quem chama trata o erro; a repetição continua */
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
