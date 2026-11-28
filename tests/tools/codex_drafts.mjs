import assert from "node:assert/strict";
import { Drafts, validateDraft } from "../../vulcan_celox/web/js/codex-drafts.mjs";

assert.deepEqual(validateDraft(" \t/a {{literal}}\r\nOlá 🧭\r "), { text: " \t/a {{literal}}\nOlá 🧭\n ", error: "" });
assert.equal(validateDraft(" \t\n").error, "empty");
assert.equal(validateDraft("🙂".repeat(4000)).error, "");
assert.equal(validateDraft("🙂".repeat(4001)).error, "size");
for (const control of ["\u0000", "\u001b", "\u007f", "\u0085"]) assert.equal(validateDraft("x" + control).error, "control");
const book = new Drafts();
const a = { id: "a", label: "Igual", root: "/projeto" };
const b = { ...a, id: "b" };
const source = book.draft(a);
const bSource = book.draft(b);
source.text = "texto A";
assert.equal(bSource.text, "");
const target = book.bind(a, b);
assert.equal(target.text, "texto A");
assert.equal(source.text, "");
assert.equal(book.draft({ ...a, root: "/worktree" }).text, "");
assert.equal(book.draft(b).text, "");
assert.equal(book.draft(a), target);
assert.equal(book.draft(a).terminal.id, "b");
assert.equal(book.transfer(target, bSource), true);
assert.equal(bSource.text, "texto A");
assert.equal(target.text, "");

// A null root is not a root: the same tab keeps its text when it gets its first root ([id, null] -> [id, root]).
const loose = new Drafts();
const tab = { id: "t", label: "Aba", root: null };
loose.draft(tab).text = "antes da pasta";
const rooted = loose.draft({ ...tab, root: "/projeto" });
assert.equal(rooted.text, "antes da pasta");
assert.equal(rooted.origin.root, "/projeto");
assert.equal(loose.draft(tab).text, "");
assert.deepEqual(loose.list().map((d) => [d.origin.id, d.origin.root, d.text]), [["t", "/projeto", "antes da pasta"]]);
// between two non-null roots nothing goes along
assert.equal(loose.draft({ ...tab, root: "/outra" }).text, "");
assert.equal(loose.draft({ ...tab, root: "/projeto" }).text, "antes da pasta");
// a slot that already has text is not overwritten
const busy = new Drafts();
busy.draft({ ...tab, root: "/projeto" }).text = "já existia";
busy.draft(tab).text = "sem raiz";
assert.equal(busy.draft({ ...tab, root: "/projeto" }).text, "já existia");
assert.equal(busy.draft(tab).text, "sem raiz");

// The draft already bound with a null root follows the same tab to its first root ([destination, null] -> [destination, root]).
const early = new Drafts();
early.draft(tab).text = "vinculado sem raiz";
const boundEarly = early.bind(tab, { id: "dest" });
assert.equal(boundEarly.text, "vinculado sem raiz");
const afterRoot = early.draft({ ...tab, root: "/projeto" });
assert.equal(afterRoot, boundEarly);
assert.equal(afterRoot.text, "vinculado sem raiz");
assert.equal(afterRoot.terminal.id, "dest");
assert.equal(afterRoot.origin.root, "/projeto");
assert.equal(early.bind({ ...tab, root: "/projeto" }, { id: "dest" }), boundEarly);

// Confirming another destination does not move text; only the explicit Trazer does, and only once.
const swap = new Drafts();
const here = { id: "h", label: "Aqui", root: "/projeto" };
swap.draft(here).text = "pedido";
const toB = swap.bind(here, { id: "B" });
assert.equal(toB.text, "pedido");
const toA = swap.bind(here, { id: "A" });
assert.notEqual(toA, toB);
assert.equal(toA.text, "");
assert.equal(toB.text, "pedido");
assert.equal(swap.transfer(toB, toA), true);
assert.equal(toA.text, "pedido");
assert.equal(toB.text, "");
assert.equal(swap.transfer(toB, toA), false);
assert.equal(toA.text, "pedido");
