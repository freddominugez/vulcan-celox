"""vt-23 C1: leitor de harness dos dois formatos, só leitura."""

import hashlib
import shutil

from tests.helpers import FIXTURES, TempDirTestCase
from vulcan_terminal.core import harness

H = FIXTURES / "harness"


def digest(root):
    return {str(p.relative_to(root)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class HarnessReaderTest(TempDirTestCase):
    def copy(self, name):
        dst = self.tmp / name
        shutil.copytree(H / name, dst)
        return dst

    def test_formato_do_repo(self):
        root = self.copy("repo")
        before = digest(root)
        info = harness.read(root)
        self.assertEqual((info["tipo"], info["estado"]), ("repo", "ok"))
        self.assertEqual(info["contrato"]["id"], "vt-22-uso-e-custo")
        self.assertTrue(info["contrato"]["existe"])
        self.assertEqual([i["estado"] for i in info["itens"]], ["feito", "feito", "andamento", "bloqueado", "pendente"])
        self.assertEqual(info["itens"][3]["causa"], "pendência registrada")
        self.assertEqual(info["itens"][0]["titulo"], "Uso por turno no índice")
        self.assertEqual(info["proximo"], "C3")
        self.assertTrue(info["ultimo_commit_verde"].startswith("1f024ff"))
        self.assertEqual(info["fila"], ["specs/vt-23-harness-pela-interface/contract.md"])
        self.assertIn("C3 em andamento.", info["handoff"])
        self.assertEqual(harness.summary(info), "vt-22-uso-e-custo: 2 de 5 itens feitos, próximo C3")
        self.assertEqual(digest(root), before)

    def test_formato_minimo(self):
        root = self.copy("minimo")
        info = harness.read(root)
        self.assertEqual((info["tipo"], info["estado"], info["status"]), ("minimo", "ok", "RUNNING"))
        self.assertEqual(info["contrato"]["caminho"], ".vulcan/tasks/drive-upload-retry.md")
        self.assertEqual(info["contrato"]["aprovacao"], "pendente")
        ids = [(i["id"], i["estado"], i["faixa"]) for i in info["itens"]]
        self.assertEqual(ids, [("C1", "feito", "verde"), ("C2", "bloqueado", "amarela"), ("C3", "pendente", "vermelha")])
        self.assertEqual(info["itens"][1]["causa"], "mock do Redis não sobe no CI")
        self.assertEqual(info["itens"][0]["evidencia"], "npm run build exit 0")
        self.assertEqual(info["itens"][2]["sensor"], "rate-limit.test.ts + revisão separada + rollback")
        self.assertEqual((info["proximo"], info["ultimo_commit_verde"]), ("C3", "a1b2c3d"))
        self.assertTrue(info["handoff"][0].startswith("Onde paramos"))

    def test_json_corrompido_e_ilegivel_e_o_arquivo_fica_igual(self):
        for name, rel in (("repo", ".harness/state.json"), ("minimo", ".vulcan/state/execution.json")):
            root = self.copy(name)
            (root / rel).write_text('{"items": [', encoding="utf-8")
            before = digest(root)
            info = harness.read(root)
            self.assertEqual(info["estado"], "ilegivel", name)
            self.assertIn("JSON inválido", info["erro"])
            self.assertEqual(digest(root), before)
            self.assertIsNone(harness.summary(info))

    def test_sem_harness_e_limites(self):
        self.assertEqual(harness.read(self.tmp)["tipo"], "nenhum")
        root = self.copy("minimo")
        (root / ".vulcan/state/execution.json").write_text("[1]", encoding="utf-8")
        self.assertEqual(harness.read(root)["estado"], "ilegivel")
        (root / ".vulcan/state/execution.json").write_bytes(b"{" + b" " * (harness.MAX_FILE + 1) + b"}")
        self.assertIn("1 MB", harness.read(root)["erro"])
        (self.tmp / "so-pasta" / ".vulcan").mkdir(parents=True)
        info = harness.read(self.tmp / "so-pasta")
        self.assertEqual((info["tipo"], info["estado"]), ("minimo", "ilegivel"))

    def test_contrato_fora_da_pasta_nao_e_lido(self):
        root = self.copy("repo")
        state = (root / ".harness/state.json").read_text(encoding="utf-8")
        (root / ".harness/state.json").write_text(state.replace("specs/vt-22-uso-e-custo/contract.md", "../../etc/passwd"),
                                                  encoding="utf-8")
        info = harness.read(root)
        self.assertFalse(info["contrato"]["existe"])
