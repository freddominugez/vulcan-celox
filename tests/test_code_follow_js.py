"""Lógica de seguir o agente e de achar o trecho, rodando os módulos de verdade no node."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent / "vulcan_terminal" / "web" / "js" / "views" / "code"

SCRIPT = """
import { Follow } from %s;
import { findSnippet } from %s;
const out = {};
let f = new Follow(true, 3);
out.inicio = f.state;
out.mesma = f.next(3);
out.nova = f.next(4);
f.userInteracted();
out.pausado = f.state;
out.durante_pausa = f.next(5);
f.resume();
out.retomado = f.state;
out.ja_contada = f.next(5);
out.outra = f.next(6);
f = new Follow(false, 0);
out.parada = f.state;
out.parada_nova = f.next(9);
f.userInteracted();
out.parada_nao_pausa = f.state;
f = new Follow(true, 0);
f.userInteracted();
f.setActive(true);
out.pausa_fica = f.state;
f.setActive(false);
f.setActive(true);
out.parou_limpa = f.state;
out.acha = findSnippet("aaa\\nbbb\\nccc", "bbb");
out.ultimo_pedaco = findSnippet("um\\ndois\\ntres", "tres\\n…\\ndois");
out.primeira_linha = findSnippet("um\\ndois\\ntres", "\\ndois\\nmudou");
out.nada = findSnippet("um", "zzz");
out.vazio = findSnippet("um", "");
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "sem node")
class CodeFollowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = SCRIPT % (json.dumps((CODE / "code-follow.mjs").as_uri()), json.dumps((CODE / "code-editor.mjs").as_uri()))
        run = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, timeout=30)
        cls.error = run.stderr
        cls.data = json.loads(run.stdout) if run.returncode == 0 else {}

    def test_segue_so_edicao_nova(self):
        self.assertEqual(self.data.get("inicio"), "following", self.error)
        self.assertFalse(self.data["mesma"])
        self.assertTrue(self.data["nova"])

    def test_interacao_pausa_e_retoma(self):
        self.assertEqual(self.data["pausado"], "paused")
        self.assertFalse(self.data["durante_pausa"])
        self.assertEqual(self.data["retomado"], "following")
        self.assertFalse(self.data["ja_contada"])
        self.assertTrue(self.data["outra"])

    def test_sessao_parada_fica_desligada(self):
        self.assertEqual(self.data["parada"], "off")
        self.assertFalse(self.data["parada_nova"])
        self.assertEqual(self.data["parada_nao_pausa"], "off")

    def test_pausa_so_vale_enquanto_a_sessao_roda(self):
        self.assertEqual(self.data["pausa_fica"], "paused")
        self.assertEqual(self.data["parou_limpa"], "following")

    def test_acha_o_trecho(self):
        self.assertEqual(self.data["acha"], 4)
        self.assertEqual(self.data["ultimo_pedaco"], 3)
        self.assertEqual(self.data["primeira_linha"], 3)
        self.assertEqual(self.data["nada"], -1)
        self.assertEqual(self.data["vazio"], -1)
