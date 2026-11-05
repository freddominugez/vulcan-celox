"""Lines changed, marks and pacing of the Code screen, running the real module in node."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

LIVE = Path(__file__).resolve().parent.parent / "vulcan_celox" / "web" / "js" / "views" / "code" / "code-live.mjs"

SCRIPT = """
import { ancestors, changedLines, FollowPacer, Marks, nextMark } from %s;
const out = {};
const c = (a, b) => changedLines(a.join("\\n"), b.join("\\n"));
out.igual = c(["a", "b"], ["a", "b"]);
out.troca = c(["a", "b", "c"], ["a", "X", "c"]);
out.novas = c(["a", "c"], ["a", "b1", "b2", "c"]);
out.fim = c(["a"], ["a", "b"]);
out.removida = c(["a", "b", "c"], ["a", "c"]);
out.removida_fim = c(["a", "b"], ["a"]);
out.vazio = c([""], ["a", "b"]);
out.separadas = c(["a", "b", "c", "d", "e"], ["a", "X", "c", "Y", "e"]);
const grande = Array.from({ length: 6000 }, (_, i) => "l" + i);
const mudado = grande.slice(); mudado[10] = "x"; mudado[20] = "y";
out.grande = c(grande, mudado);
const medio = Array.from({ length: 5000 }, (_, i) => "l" + i);
const m2 = medio.slice(); m2[10] = "x"; m2[20] = "y";
out.medio = c(medio, m2);
out.marcas = [[null, "added"], [null, "modified"], [null, "deleted"], ["A", "modified"], ["A", "deleted"], ["M", "modified"], ["M", "deleted"], ["D", "added"], ["D", "modified"]].map(([m, e]) => nextMark(m, e));
const m = new Marks();
m.apply({ rel: "a/b/c.txt", change: "added", agent: null });
out.dentro = [m.hasInside("a"), m.hasInside("a/b"), m.hasInside("a/x"), m.hasInside("a/b/c.txt")];
out.autor = [m.attribute("a/b/c.txt", { agent: "claude", session: "s" }), m.get("a/b/c.txt").agent.agent, m.attribute("a/b/c.txt", { agent: "claude", session: "s" }), m.attribute("nada", { agent: "claude", session: "s" })];
m.apply({ rel: "a/b/c.txt", change: "deleted" });
out.saiu = m.get("a/b/c.txt");
out.anc = ancestors("a/b/c.txt");
const p = new FollowPacer({ quiet: 300, dwell: 1500 });
const seq = [];
p.push("a", 0); seq.push(p.due(100)); p.push("b", 200); seq.push(p.due(400)); seq.push(p.due(500)); p.shown(500);
p.push("c", 600); seq.push(p.due(1000)); seq.push(p.due(1999)); seq.push(p.due(2000)); seq.push(p.due(2100));
out.ritmo = seq;
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "sem node")
class CodeLiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = subprocess.run(["node", "--input-type=module", "-e", SCRIPT % json.dumps(LIVE.as_uri())], capture_output=True, text=True, timeout=60)
        cls.error = run.stderr
        cls.data = json.loads(run.stdout) if run.returncode == 0 else {}

    def test_linhas(self):
        d = self.data
        self.assertEqual(d.get("igual"), [], self.error)
        self.assertEqual(d["troca"], [2])
        self.assertEqual(d["novas"], [2, 3])
        self.assertEqual(d["fim"], [2])
        self.assertEqual(d["removida"], [2])
        self.assertEqual(d["removida_fim"], [1])
        self.assertEqual(d["vazio"], [1, 2])
        self.assertEqual(d["separadas"], [2, 4])

    def test_acima_de_5000_linhas_destaca_o_trecho(self):
        self.assertEqual(self.data["grande"], list(range(11, 22)))
        self.assertEqual(self.data["medio"], [11, 21])

    def test_marcas(self):
        self.assertEqual(self.data["marcas"], ["A", "M", "D", "A", None, "M", "D", "M", "M"])
        self.assertEqual(self.data["dentro"], [True, True, False, False])
        self.assertEqual(self.data["autor"], [True, "claude", False, False])
        self.assertIsNone(self.data["saiu"])
        self.assertEqual(self.data["anc"], ["a", "a/b"])

    def test_ritmo_fica_no_ultimo(self):
        self.assertEqual(self.data["ritmo"], [None, None, "b", None, None, "c", None])
