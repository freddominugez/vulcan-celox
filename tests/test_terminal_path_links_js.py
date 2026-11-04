"""Path recognition in the terminal, running the real module in node."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parent.parent / "vulcan_celox" / "web" / "js" / "terminal-path-links.mjs"

SCRIPT = """
import { buildLinks, findPaths, logicalLine, pathLinkProvider } from %s;
const paths = (t) => findPaths(t).map((c) => [c.path, c.line, c.column]);
function buffer(rows) {
  return { getLine: (y) => rows[y] && { isWrapped: rows[y].wrapped, length: rows[y].cells.length,
    getCell: (x) => { const c = rows[y].cells[x]; return c === undefined ? null : { getChars: () => c === null ? "" : c, getWidth: () => c === null ? 0 : (c === "界" ? 2 : 1) }; } } };
}
const row = (text, wrapped = false) => ({ wrapped, cells: [...text] });
const wrapped = logicalLine(buffer([row("ver a/b/"), row("c.py:9 ok", true), row("outra")]), 1);
const wide = { wrapped: false, cells: ["界", null, " ", ..."a/b.py"] };
const wideLine = logicalLine(buffer([wide]), 0);
const wideLinks = buildLinks(wideLine, findPaths(wideLine.text), { "a/b.py": { path: "/x/a/b.py" } }, 0, () => {});
const splitLinks = buildLinks(wrapped, findPaths(wrapped.text), { "a/b/c.py": { path: "/x/a/b/c.py" } }, 1, () => {});
let asked = 0;
const term = { buffer: { active: buffer([row("ver a/b.py")]) } };
const off = await new Promise((r) => pathLinkProvider(term, { modifier: () => false, resolve: () => { asked++; return Promise.resolve({}); }, activate() {} }).provideLinks(1, r));
let got;
const on = await new Promise((r) => pathLinkProvider(term, { modifier: () => true, resolve: (c) => { asked++; return Promise.resolve({ "a/b.py": { path: "/x", kind: "file" } }); },
  activate: (e, t) => { got = t; } }).provideLinks(1, r));
on[0].activate({}, "");
const none = await new Promise((r) => pathLinkProvider(term, { modifier: () => true, resolve: () => Promise.reject(new Error("x")), activate() {} }).provideLinks(1, r));
console.log(JSON.stringify({
  formatos: paths("a/b.py ./b.py /abs/b.py ../c.py b.py:12 b.py:12:3 b.py(12)"),
  pontuacao: paths('("a/b.py"), [c/d.php]; veja e/f.js. Erro:g/h.py: fim'),
  url: paths("https://site.test/a/b.py e file:///x/y.py e c/d.py"),
  soltos: paths("versão 1.2.3 de 2026 e palavra"),
  limite: findPaths(Array.from({ length: 80 }, (_, i) => `f${i}.py`).join(" ")).length,
  wrappedText: wrapped.text.slice(0, 18), splitRange: splitLinks[0] && splitLinks[0].range,
  wideRange: wideLinks[0] && wideLinks[0].range, off: off === undefined ? null : off, asked, activated: got, none: none === undefined ? null : none,
}));
"""


@unittest.skipUnless(shutil.which("node"), "sem node")
class PathLinksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = SCRIPT % json.dumps(MODULE.as_uri())
        run = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, timeout=30)
        cls.error = run.stderr
        cls.data = json.loads(run.stdout) if run.returncode == 0 else {}

    def test_formatos(self):
        self.assertEqual(self.data.get("formatos"), [
            ["a/b.py", None, None], ["./b.py", None, None], ["/abs/b.py", None, None], ["../c.py", None, None],
            ["b.py", 12, None], ["b.py", 12, 3], ["b.py", 12, None]], self.error)

    def test_pontuacao_em_volta(self):
        self.assertEqual([p[0] for p in self.data["pontuacao"]], ["a/b.py", "c/d.php", "e/f.js", "g/h.py"])

    def test_url_intacta(self):
        self.assertEqual([p[0] for p in self.data["url"]], ["c/d.py"])

    def test_numero_e_palavra_nao_entram(self):
        self.assertEqual(self.data["soltos"], [])

    def test_limite_de_candidatos(self):
        self.assertEqual(self.data["limite"], 50)

    def test_linha_quebrada(self):
        self.assertEqual(self.data["wrappedText"], "ver a/b/c.py:9 ok")
        self.assertEqual(self.data["splitRange"]["start"], {"x": 5, "y": 1})
        self.assertEqual(self.data["splitRange"]["end"], {"x": 6, "y": 2})

    def test_caractere_largo_nao_desloca_o_link(self):
        self.assertEqual(self.data["wideRange"]["start"], {"x": 4, "y": 1})

    def test_sem_tecla_nao_consulta_nem_sublinha(self):
        self.assertIsNone(self.data["off"])
        self.assertEqual(self.data["asked"], 1)  # only the call with the key pressed

    def test_clique_leva_linha_e_resultado(self):
        self.assertEqual(self.data["activated"], {"path": "/x", "kind": "file", "line": None, "column": None})

    def test_falha_do_servidor_nao_cria_link(self):
        self.assertIsNone(self.data["none"])
