import json
from pathlib import Path

from tests.helpers import TempDirTestCase, unix_only, MODOS
from vulcan_celox.core import paths
from vulcan_celox.core.store import Store, migrate_legacy, read_json, write_json_atomic


class PathsTest(TempDirTestCase):
    def test_overrides(self):
        env = {"VULCAN_CELOX_HOME": str(self.tmp / "h"), "VULCAN_LEGACY_HOME": str(self.tmp / "l"),
               "VULCAN_VALET_HOME": str(self.tmp / "v"), "VULCAN_VALET_BIN": str(self.tmp / "b")}
        self.assertEqual(paths.data_dir(env), self.tmp / "h")
        self.assertEqual(paths.legacy_dir(env), self.tmp / "l")
        self.assertEqual(paths.valet_home(env), self.tmp / "v")
        self.assertEqual(paths.valet_bin_candidates(env), [self.tmp / "b"])

    def test_defaults(self):
        import sys
        expected = {"darwin": "Library/Application Support/VulcanCelox", "win32": "VulcanCelox"}.get(sys.platform, "vulcan-celox")
        self.assertTrue(str(paths.data_dir({})).endswith(expected))
        self.assertTrue(paths.valet_home({}).as_posix().endswith(".config/valet"))
        self.assertEqual(len(paths.valet_bin_candidates({})), 4)


class StoreTest(TempDirTestCase):
    def test_roundtrip_com_schema_version(self):
        store = Store(self.tmp)
        store.save("tags", [{"id": "1", "name": "bug"}])
        self.assertEqual(store.load("tags", []), [{"id": "1", "name": "bug"}])
        raw = json.loads(store.path("tags").read_text(encoding="utf-8"))
        self.assertEqual(raw["schema_version"], 1)

    def test_default_quando_ausente_e_copia(self):
        store = Store(self.tmp)
        default = {"a": []}
        value = store.load("nada", default)
        value["a"].append(1)
        self.assertEqual(default, {"a": []})

    def test_escrita_atomica_preserva_original(self):
        target = self.tmp / "x.json"
        write_json_atomic(target, {"ok": True})
        with self.assertRaises(TypeError):
            write_json_atomic(target, {"ruim": {1, 2}})
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["x.json"])

    @unix_only(MODOS)
    def test_permissao_do_arquivo(self):
        novo = self.tmp / "novo.md"
        write_json_atomic(novo, {})
        self.assertEqual(novo.stat().st_mode & 0o777, 0o644)
        existente = self.tmp / "existente.md"
        existente.write_text("x", encoding="utf-8")
        existente.chmod(0o664)
        write_json_atomic(existente, {})
        self.assertEqual(existente.stat().st_mode & 0o777, 0o664)

    def test_corrompido_vira_corrupt(self):
        target = self.tmp / "notes.json"
        target.write_text("{isto não é json", encoding="utf-8")
        self.assertEqual(read_json(target, {"d": 1}), {"d": 1})
        self.assertFalse(target.exists())
        corrupt = [p.name for p in self.tmp.iterdir() if p.name.startswith("notes.json.corrupt-")]
        self.assertEqual(len(corrupt), 1)

    def test_arquivo_sem_envelope_e_aceito(self):
        store = Store(self.tmp)
        store.path("sites").write_text('{"loja": "/x"}', encoding="utf-8")
        self.assertEqual(store.load("sites", {}), {"loja": "/x"})


class MigracaoTest(TempDirTestCase):
    def _legacy(self):
        legacy = self.tmp / "ValetGUI"
        legacy.mkdir()
        (legacy / "notes.json").write_text(json.dumps({
            "loja": [{"texto": "a", "cor": "rosa"}, {"texto": "b", "cor": "azul"}],
            "blog": [{"texto": "c", "cor": "verde"}, {"texto": "d", "cor": "amarelo"}],
        }), encoding="utf-8")
        (legacy / "sites.json").write_text(json.dumps({"loja": "/p/loja", "blog": "/p/blog"}),
                                           encoding="utf-8")
        return legacy

    def test_migra_e_e_idempotente(self):
        legacy = self._legacy()
        original = (legacy / "notes.json").read_text(encoding="utf-8")
        store = Store(self.tmp / "home")
        r1 = migrate_legacy(store, legacy)
        self.assertEqual((r1["notes_sites"], r1["sites"]), (2, 2))
        self.assertEqual(store.load("sites", {}), {"loja": "/p/loja", "blog": "/p/blog"})
        self.assertEqual(len(store.load("legacy_notes", {})["loja"]), 2)

        r2 = migrate_legacy(store, legacy)
        self.assertEqual(r2["skipped"], 1)
        self.assertEqual(len(store.load("sites", {})), 2)
        self.assertEqual((legacy / "notes.json").read_text(encoding="utf-8"), original)

    def test_sem_legado(self):
        store = Store(self.tmp / "home")
        r = migrate_legacy(store, Path(self.tmp / "inexistente"))
        self.assertEqual((r["notes_sites"], r["sites"]), (0, 0))
        self.assertTrue(store.migration_done("valetgui"))
