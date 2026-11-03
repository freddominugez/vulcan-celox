"""Marcas de pedido no terminal, rodando o módulo de verdade no node."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "vulcan_terminal" / "web" / "js" / "terminal-turns.mjs"

SCRIPT = """
import { TurnMarks } from %s;
function fake() {
  const term = { line: 0, scrolled: null, buffer: { active: { type: "normal", viewportY: 0 } },
    registerMarker() { const m = { line: term.line, isDisposed: false, cb: null, onDispose(f) { m.cb = f; }, dispose() { m.isDisposed = true; if (m.cb) m.cb(); } }; return m; },
    scrollToLine(l) { term.scrolled = l; term.buffer.active.viewportY = l; } };
  return term;
}
const out = {};
let t = fake(); let warned = 0;
let m = new TurnMarks(t, { warn: () => { warned += 1; } });
for (const l of [10, 50, 90]) { t.line = l; await m.enter(); }
t.buffer.active.viewportY = 60;
out.anterior = m.step(-1);
out.anterior2 = m.step(-1);
out.extremo_inicio = m.step(-1);
out.seguinte = m.step(1);
t.buffer.active.viewportY = 90;
out.extremo_fim = m.step(1);
const sumiu = m.marks[1]; sumiu.dispose();
out.descartada = m.lines();
m.marks[0].line = -1;
out.fora_do_historico = m.lines();
t = fake(); warned = 0;
m = new TurnMarks(t, { warn: () => { warned += 1; } });
t.buffer.active.type = "alternate";
out.alt_marca = await m.enter();
out.alt_step = [m.step(-1), m.step(1)];
out.alt_avisos = warned;
out.alt_scroll = t.scrolled;
t = fake();
m = new TurnMarks(t, { isAgent: () => Promise.resolve(false) });
t.line = 5; await m.enter();
out.sem_agente = m.lines();
t = fake();
m = new TurnMarks(t, { isAgent: () => Promise.reject(new Error("x")) });
t.line = 5; await m.enter();
out.sem_saber = m.lines();
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "sem node")
class TerminalTurnsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = subprocess.run(["node", "--input-type=module", "-e", SCRIPT % json.dumps(MODULE.as_uri())],
                             capture_output=True, text=True, timeout=30)
        cls.error = run.stderr
        cls.data = json.loads(run.stdout) if run.returncode == 0 else {}

    def test_anterior_e_seguinte(self):
        self.assertEqual(self.data.get("anterior"), 50, self.error)
        self.assertEqual(self.data["anterior2"], 10)
        self.assertEqual(self.data["seguinte"], 50)

    def test_extremos_nao_saem_do_lugar(self):
        self.assertIsNone(self.data["extremo_inicio"])
        self.assertIsNone(self.data["extremo_fim"])

    def test_marca_descartada_nao_conta(self):
        self.assertEqual(self.data["descartada"], [10, 90])
        self.assertEqual(self.data["fora_do_historico"], [90])

    def test_tela_alternativa_avisa_uma_vez(self):
        self.assertIsNone(self.data["alt_marca"])
        self.assertEqual(self.data["alt_step"], [None, None])
        self.assertEqual(self.data["alt_avisos"], 1)
        self.assertIsNone(self.data["alt_scroll"])

    def test_aba_sem_agente_nao_guarda_marca(self):
        self.assertEqual(self.data["sem_agente"], [])
        self.assertEqual(self.data["sem_saber"], [5])


class AtalhosTest(unittest.TestCase):
    def test_atalho_sem_conflito_com_menus(self):
        shell = (ROOT / "packaging" / "macos" / "main.swift").read_text(encoding="utf-8")
        self.assertNotIn("NSUpArrowFunctionKey", shell)
        self.assertNotIn("NSDownArrowFunctionKey", shell)
