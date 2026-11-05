import json
import os
import sqlite3
import stat
import zipfile
from pathlib import Path

from tests.helpers import TempDirTestCase
from vulcan_celox.core.backup import (ASIDE_DIR, MANIFEST, PENDING_DIR, PHASE_FILE, BackupError, apply_pending_restore,
                                      create_backup, prepare_restore)


class BackupCase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.data = self.tmp / "dados"
        (self.data / "sessoes" / "global").mkdir(parents=True)
        (self.data / "tasks.json").write_text('{"tarefa": 1}', encoding="utf-8")
        (self.data / "sessoes" / "global" / "a.md").write_text("memória", encoding="utf-8")
        self.dest = self.tmp / "destino"

    def names(self, path):
        with zipfile.ZipFile(path) as archive:
            return set(archive.namelist())

    def zip_with(self, members, manifest=True):
        path = self.tmp / "feito.zip"
        with zipfile.ZipFile(path, "w") as archive:
            if manifest:
                archive.writestr(MANIFEST, json.dumps({"format": 1}))
            for name, text in members.items():
                archive.writestr(name, text)
        return path


class CreateTest(BackupCase):
    def test_leva_tudo_e_fica_privado(self):
        result = create_backup(self.data, self.dest, "1.2.3")
        self.assertEqual(self.names(result["path"]), {"tasks.json", "sessoes/global/a.md", MANIFEST})
        self.assertEqual(result["files"], 2)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(result["path"]).st_mode), 0o600)
        self.assertEqual([p.name for p in self.dest.iterdir()], [Path(result["path"]).name])

    def test_recusa_destino_dentro_dos_dados(self):
        for inside in (self.data, self.data / "backups"):
            with self.assertRaises(BackupError):
                create_backup(self.data, inside, "1")

    def test_fora_temporarios_restauros_e_links(self):
        (self.data / ".tasks.json.123.tmp").write_text("x")
        (self.data / ASIDE_DIR / "antigo").mkdir(parents=True)
        (self.data / ASIDE_DIR / "antigo" / "tasks.json").write_text("velho")
        (self.data / "agentes.db-wal").write_text("x")
        if os.name != "nt":
            os.symlink("/etc/hosts", self.data / "link")
        names = self.names(create_backup(self.data, self.dest, "1")["path"])
        self.assertEqual(names, {"tasks.json", "sessoes/global/a.md", MANIFEST})

    def test_sqlite_em_uso_sai_consistente(self):
        db = sqlite3.connect(str(self.data / "agentes.db"))
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE t (v)")
        db.execute("INSERT INTO t VALUES (42)")
        db.commit()  # the row is only in the WAL, which stays out of the zip
        result = create_backup(self.data, self.dest, "1")
        db.close()
        out = self.tmp / "extraido"
        with zipfile.ZipFile(result["path"]) as archive:
            archive.extractall(out)
        copy = sqlite3.connect(str(out / "agentes.db"))
        self.assertEqual(copy.execute("SELECT v FROM t").fetchone(), (42,))
        copy.close()


class RestoreTest(BackupCase):
    def test_ida_e_volta(self):
        backup = create_backup(self.data, self.dest, "1.2.3")["path"]
        (self.data / "tasks.json").write_text('{"tarefa": 2}', encoding="utf-8")
        (self.data / "novo.json").write_text("{}", encoding="utf-8")

        info = prepare_restore(backup, self.data)
        self.assertEqual(info["version"], "1.2.3")
        self.assertEqual((self.data / "tasks.json").read_text(encoding="utf-8"), '{"tarefa": 2}')  # nothing until the restart

        aside = apply_pending_restore(self.data)
        self.assertEqual((self.data / "tasks.json").read_text(encoding="utf-8"), '{"tarefa": 1}')
        self.assertEqual((self.data / "sessoes" / "global" / "a.md").read_text(encoding="utf-8"), "memória")
        self.assertFalse((self.data / "novo.json").exists())
        self.assertFalse((self.data / MANIFEST).exists())
        self.assertFalse((self.data / PENDING_DIR).exists())
        # the data that was there is kept
        self.assertEqual((aside / "tasks.json").read_text(encoding="utf-8"), '{"tarefa": 2}')
        self.assertTrue((aside / "novo.json").is_file())
        self.assertIsNone(apply_pending_restore(self.data))

    def test_retoma_troca_interrompida_ao_sair(self):
        backup = create_backup(self.data, self.dest, "1")["path"]
        (self.data / "tasks.json").write_text('{"tarefa": 2}', encoding="utf-8")
        prepare_restore(backup, self.data)
        pending = self.data / PENDING_DIR
        aside = self.data / ASIDE_DIR / "parou"
        aside.mkdir(parents=True)
        os.replace(self.data / "sessoes", aside / "sessoes")  # fell over after moving one entry
        (pending / PHASE_FILE).write_text(json.dumps({"step": "leaving", "stamp": "parou"}), encoding="utf-8")
        self.assertEqual(apply_pending_restore(self.data), aside)
        self.assertEqual((aside / "tasks.json").read_text(encoding="utf-8"), '{"tarefa": 2}')
        self.assertEqual((self.data / "tasks.json").read_text(encoding="utf-8"), '{"tarefa": 1}')

    def test_retoma_sem_tratar_restaurado_como_antigo(self):
        backup = create_backup(self.data, self.dest, "1")["path"]
        prepare_restore(backup, self.data)
        pending = self.data / PENDING_DIR
        aside = self.data / ASIDE_DIR / "parou"
        aside.mkdir(parents=True)
        for name in ("tasks.json", "sessoes"):
            os.replace(self.data / name, aside / name)
        os.replace(pending / "tasks.json", self.data / "tasks.json")  # fell over while entering
        (pending / PHASE_FILE).write_text(json.dumps({"step": "entering", "stamp": "parou"}), encoding="utf-8")
        apply_pending_restore(self.data)
        self.assertEqual((self.data / "tasks.json").read_text(encoding="utf-8"), '{"tarefa": 1}')
        self.assertTrue((self.data / "sessoes" / "global" / "a.md").is_file())
        self.assertFalse((self.data / PENDING_DIR).exists())

    def test_recusas_nao_tocam_nos_dados(self):
        bad = [({"x.json": "{}"}, False), ({"../fora.json": "{}"}, True), ({"/abs.json": "{}"}, True),
               ({f"{ASIDE_DIR}/x": "{}"}, True), ({"a\\b": "{}"}, True)]
        for members, manifest in bad:
            with self.assertRaises(BackupError, msg=str(members)):
                prepare_restore(self.zip_with(members, manifest), self.data)
            self.assertEqual(sorted(p.name for p in self.data.iterdir()), ["sessoes", "tasks.json"])
        self.assertFalse((self.tmp / "fora.json").exists())

    def test_recusa_link_simbolico_no_zip(self):
        path = self.tmp / "link.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(MANIFEST, json.dumps({"format": 1}))
            info = zipfile.ZipInfo("tasks.json")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "/etc/passwd")
        with self.assertRaises(BackupError):
            prepare_restore(path, self.data)

    def test_recusa_arquivo_que_nao_e_zip_e_formato_novo(self):
        fake = self.tmp / "nao.zip"
        fake.write_text("texto")
        with self.assertRaises(BackupError):
            prepare_restore(fake, self.data)
        with zipfile.ZipFile(self.tmp / "novo.zip", "w") as archive:
            archive.writestr(MANIFEST, json.dumps({"format": 99}))
        with self.assertRaises(BackupError):
            prepare_restore(self.tmp / "novo.zip", self.data)
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), ["sessoes", "tasks.json"])

    def test_segunda_restauracao_espera_a_primeira(self):
        backup = create_backup(self.data, self.dest, "1")["path"]
        prepare_restore(backup, self.data)
        with self.assertRaises(BackupError):
            prepare_restore(backup, self.data)

    def test_caminho_da_memoria_acompanha_a_pasta_nova(self):
        memory = self.data / "sessoes" / "global" / "a.md"
        doc = {"schema_version": 1, "data": [{"id": "s1", "memory_file": str(memory)}, {"id": "s2", "memory_file": "/outra/b.md"}]}
        (self.data / "terminal_sessions.json").write_text(json.dumps(doc), encoding="utf-8")
        backup = create_backup(self.data, self.dest, "1")["path"]
        novo = self.tmp / "outro-usuario" / "dados"
        novo.mkdir(parents=True)
        prepare_restore(backup, novo)
        apply_pending_restore(novo)
        data = json.loads((novo / "terminal_sessions.json").read_text(encoding="utf-8"))["data"]
        self.assertEqual(data[0]["memory_file"], str(novo / "sessoes" / "global" / "a.md"))
        self.assertEqual(data[1]["memory_file"], "/outra/b.md")
