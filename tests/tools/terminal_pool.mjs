import assert from "node:assert/strict";

globalThis.window = new EventTarget();
globalThis.location = { hash: "", search: "" };

Object.defineProperty(globalThis, "navigator", { value: { platform: "Mac" } });
let response;
const snapshot = (terminals) => new Response(JSON.stringify({ terminals }), { status: 200 });
const info = (title, alive = true) => ({ id: "a", title, alive });
let pending;
globalThis.fetch = (path, options) => {
  if (path === "/api/themes") return Promise.reject(new Error("isolated"));
  if (options.method === "PATCH") return new Response(JSON.stringify(info("Confirmado")));
  if (pending) return new Promise((resolve) => { response = resolve; });
  if (pending === null) return Promise.reject(new Error("offline"));
  return snapshot([info("Confirmado")]);
};
const { terminals } = await import("../../vulcan_celox/web/js/terminal-pool.mjs");
const tab = { info: info("Antes"), alive: true };
terminals.sessions.set("a", tab);
terminals.order.push("a");
pending = true;
const old = terminals.sync();
await terminals.updateIdentity("a", { title: "Confirmado" });
pending = false;
response(snapshot([info("Antes")]));
await old;
assert.equal(tab.info.title, "Confirmado");

pending = null;
await terminals.sync();
assert.equal(terminals.stale, true);
assert.deepEqual(terminals.live().map((entry) => entry.info.id), ["a"]);
pending = false;
await terminals.sync();
assert.equal(terminals.stale, false);

pending = true;
const finishing = terminals.sync();
pending = false;
response(snapshot([info("Confirmado", false)]));
await finishing;
assert.equal(terminals.live().length, 0);
assert.equal(terminals.get("a"), tab);
await terminals.sync();
assert.equal(terminals.live().length, 0);
assert.equal(tab.alive, false);
