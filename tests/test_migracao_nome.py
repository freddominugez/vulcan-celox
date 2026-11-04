"""Whoever already uses the app loses nothing with the new name: data folder and Keychain key."""

import tempfile
import unittest
from pathlib import Path

from vulcan_celox.core import keychain, oscompat, paths
from vulcan_celox.core.runner import FakeRunner, Result

OLD = "VulcanTerminal"
KEY = "sk-ant-" + "a" * 40


class PastaTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.home = Path(self.dir.name)
        self.support = self.home / "Library" / "Application Support"
        self.support.mkdir(parents=True)

    def folder(self):
        env = {"HOME": str(self.home)}
        oscompat.migrate_old_folder(env, system="darwin")
        return oscompat.default_data_dir(env, system="darwin")

    def test_calcular_o_caminho_nao_move_nada(self):
        old = self.support / OLD
        old.mkdir()
        oscompat.default_data_dir({"HOME": str(self.home)}, system="darwin")
        self.assertFalse(old.is_symlink())
        self.assertFalse((self.support / "VulcanCelox").exists())

    def test_com_pasta_definida_por_variavel_nao_migra(self):
        old = self.support / OLD
        old.mkdir()
        paths.migrate_data_folder({"HOME": str(self.home), paths.ENV_HOME: str(self.home / "outra")})
        self.assertFalse(old.is_symlink())

    def test_muda_de_nome_e_deixa_link(self):
        old = self.support / OLD
        old.mkdir()
        (old / "agentes.db").write_text("dados", encoding="utf-8")
        new = self.folder()
        self.assertEqual(new.name, "VulcanCelox")
        self.assertEqual((new / "agentes.db").read_text(encoding="utf-8"), "dados")
        self.assertTrue(old.is_symlink())
        self.assertEqual((old / "agentes.db").read_text(encoding="utf-8"), "dados")  # the old hook still finds it

    def test_segunda_abertura_nao_mexe(self):
        (self.support / OLD).mkdir()
        new = self.folder()
        (new / "x").write_text("1", encoding="utf-8")
        self.assertEqual(self.folder(), new)
        self.assertEqual((new / "x").read_text(encoding="utf-8"), "1")

    def test_com_as_duas_nao_apaga_nada(self):
        (self.support / OLD).mkdir()
        (self.support / OLD / "a").write_text("velho", encoding="utf-8")
        (self.support / "VulcanCelox").mkdir()
        self.folder()
        self.assertEqual((self.support / OLD / "a").read_text(encoding="utf-8"), "velho")
        self.assertFalse((self.support / OLD).is_symlink())

    def test_sem_pasta_antiga(self):
        self.assertFalse(self.folder().exists())

    def test_linux(self):
        base = self.home / "xdg"
        old = base / ("vulcan-" + "terminal")
        old.mkdir(parents=True)
        env = {"HOME": str(self.home), "XDG_DATA_HOME": str(base)}
        oscompat.migrate_old_folder(env, system="linux")
        new = oscompat.default_data_dir(env, system="linux")
        self.assertEqual(new, base / "vulcan-celox")
        self.assertTrue(new.is_dir() and old.is_symlink())


class KeychainTest(unittest.TestCase):
    def store(self, old_value):
        runner = FakeRunner()
        store = keychain.KeychainStore(runner=runner, security="/bin/seg")
        runner.respond(["/bin/seg", "find-generic-password", "-s", keychain.SERVICE, "-a", store.account, "-w"], Result(44))
        runner.respond(["/bin/seg", "find-generic-password", "-s", keychain.OLD_SERVICE, "-a", store.account, "-w"], old_value)
        return runner, store

    def test_le_a_antiga_e_copia(self):
        runner, store = self.store(Result(0, KEY + "\n"))
        self.assertEqual(store.get(), KEY)
        escritas = [c for c in runner.calls if c.input and keychain.SERVICE in c.input]
        self.assertEqual(len(escritas), 1)
        self.assertFalse([c for c in runner.calls if "delete-generic-password" in c.argv], "a antiga fica")

    def test_sem_nenhuma(self):
        _, store = self.store(Result(44))
        self.assertIsNone(store.get())
