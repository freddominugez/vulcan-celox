"""Terminal notices, running the real module in node."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "vulcan_celox" / "web" / "js" / "terminal-attention.mjs"

SCRIPT = """
import { cleanText, oscMessage, rateLimiter, watchTerminal } from %s;
let now = 0;
const allow = rateLimiter(5000, () => now);
const limit = [allow("a"), allow("a"), allow("b")];
now = 5000;
limit.push(allow("a"));
const handlers = {}; let bell = null; const got = [];
const term = { parser: { registerOscHandler: (c, f) => { handlers[c] = f; } }, onBell: (f) => { bell = f; } };
watchTerminal(term, "x", (id, text) => got.push([id, text]), () => true);
const handled = handlers[9]("4;1;50");
handlers[9]("terminou"); handlers[777]("notify;Claude;pronto"); handlers[777]("outro;a;b"); bell();
console.log(JSON.stringify({
  osc9: oscMessage(9, "terminou"), progress: oscMessage(9, "4;1;50"), progressEnd: oscMessage(9, "4"),
  osc99: oscMessage(99, "i=1:d=0;Pronto"), osc777: oscMessage(777, "notify;Título;Corpo"), other: oscMessage(777, "x;y"),
  html: oscMessage(9, "<img src=x onerror=alert(1)>"), control: cleanText("a\\u001b[31mb\\u0007\\n c"), long: cleanText("x".repeat(500)).length,
  empty: cleanText(null), unknown: oscMessage(52, "c;abc"), limit, got, handled }));
"""


@unittest.skipUnless(shutil.which("node"), "sem node")
class TerminalAttentionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = SCRIPT % json.dumps(MODULE.as_uri())
        out = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, timeout=30)
        cls.error = out.stderr
        cls.data = json.loads(out.stdout) if out.returncode == 0 else {}

    def test_rodou(self):
        self.assertTrue(self.data, self.error)

    def test_formatos(self):
        self.assertEqual(self.data["osc9"], "terminou")
        self.assertEqual(self.data["osc99"], "Pronto")
        self.assertEqual(self.data["osc777"], "Título: Corpo")

    def test_o_que_nao_e_aviso(self):
        for key in ("progress", "progressEnd", "other", "unknown"):
            self.assertIsNone(self.data[key], key)

    def test_texto_e_dado(self):
        self.assertEqual(self.data["html"], "<img src=x onerror=alert(1)>")  # the interface shows it via textContent
        self.assertEqual(self.data["long"], 200)
        self.assertEqual(self.data["empty"], "")
        self.assertNotIn("\u001b", self.data["control"])

    def test_limite_de_taxa(self):
        self.assertEqual(self.data["limit"], [True, False, True, True])

    def test_ligacao_ao_terminal(self):
        self.assertTrue(self.data["handled"])
        self.assertEqual(self.data["got"], [["x", "terminou"], ["x", "Claude: pronto"], ["x", ""]])


if __name__ == "__main__":
    unittest.main()
