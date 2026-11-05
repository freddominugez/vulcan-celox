import json
import os
import sqlite3
import stat
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.helpers import TempDirTestCase
from vulcan_celox.core.backup import (ASIDE_DIR, MANIFEST, PENDING_DIR, PHASE_FILE, BackupError, apply_pending_restore,
                                      create_backup, open_data_folder, prepare_restore)
from vulcan_celox.core.backup_inspect import MAX_MEMBERS, inspect_backup
from vulcan_celox.core.data_lock import DataLock


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
        aside = self.data / ASIDE_DIR / "20261105-120000"
        aside.mkdir(parents=True)
        os.replace(self.data / "sessoes", aside / "sessoes")  # fell over after moving one entry
        (pending / PHASE_FILE).write_text(json.dumps({"step": "leaving", "stamp": "20261105-120000"}), encoding="utf-8")
        self.assertEqual(apply_pending_restore(self.data), aside)
        self.assertEqual((aside / "tasks.json").read_text(encoding="utf-8"), '{"tarefa": 2}')
        self.assertEqual((self.data / "tasks.json").read_text(encoding="utf-8"), '{"tarefa": 1}')

    def test_retoma_sem_tratar_restaurado_como_antigo(self):
        backup = create_backup(self.data, self.dest, "1")["path"]
        prepare_restore(backup, self.data)
        pending = self.data / PENDING_DIR
        aside = self.data / ASIDE_DIR / "20261105-120000"
        aside.mkdir(parents=True)
        for name in ("tasks.json", "sessoes"):
            os.replace(self.data / name, aside / name)
        os.replace(pending / "tasks.json", self.data / "tasks.json")  # fell over while entering
        (pending / PHASE_FILE).write_text(json.dumps({"step": "entering", "stamp": "20261105-120000"}), encoding="utf-8")
        apply_pending_restore(self.data)
        self.assertEqual((self.data / "tasks.json").read_text(encoding="utf-8"), '{"tarefa": 1}')
        self.assertTrue((self.data / "sessoes" / "global" / "a.md").is_file())
        self.assertFalse((self.data / PENDING_DIR).exists())

    def test_arquivo_preso_nao_troca_nada_e_tenta_depois(self):
        backup = create_backup(self.data, self.dest, "1")["path"]
        (self.data / "tasks.json").write_text('{"tarefa": 2}', encoding="utf-8")
        prepare_restore(backup, self.data)
        real = os.replace

        def locked(source, target):
            if Path(source).name == "tasks.json":
                raise PermissionError(32, "em uso")
            real(source, target)

        with mock.patch("vulcan_celox.core.backup.os.replace", locked), mock.patch("vulcan_celox.core.backup.SWAP_WAIT", 0):
            self.assertIsNone(apply_pending_restore(self.data))
        self.assertEqual((self.data / "tasks.json").read_text(encoding="utf-8"), '{"tarefa": 2}')
        self.assertTrue((self.data / "sessoes" / "global" / "a.md").is_file())  # what had moved came back
        self.assertTrue((self.data / PENDING_DIR).is_dir())
        apply_pending_restore(self.data)  # next start: free now
        self.assertEqual((self.data / "tasks.json").read_text(encoding="utf-8"), '{"tarefa": 1}')

    def test_recusas_nao_tocam_nos_dados(self):
        bad = [({"x.json": "{}"}, False), ({"../fora.json": "{}"}, True), ({"/abs.json": "{}"}, True),
               ({f"{ASIDE_DIR}/x": "{}"}, True)]
        if os.name != "nt":  # on Windows, zipfile itself turns the backslash into a plain folder separator
            bad.append(({"a\\b": "{}"}, True))
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


class ZipMontadoTest(BackupCase):
    """The zips of the audit: a valid manifest and no forbidden path, with something more inside."""

    def backup_with(self, extra):
        made = create_backup(self.data, self.dest, "9.9")["path"]
        out = self.tmp / "montado.zip"
        with zipfile.ZipFile(made) as source, zipfile.ZipFile(out, "w") as archive:
            for name in source.namelist():
                archive.writestr(name, source.read(name))
            for name, text in extra.items():
                archive.writestr(name, text)
        return out

    def test_recusa_fase_e_pasta_reservada_em_qualquer_caixa(self):
        for name in (".fase.json", ".FASE.JSON", ".restauros/x.txt", ".RESTAUROS/x.txt", ".Restauro-Pendente/y", ".app.lock"):
            with self.subTest(name=name):
                with self.assertRaises(BackupError):
                    prepare_restore(self.backup_with({name: "{}"}), self.data)
                self.assertFalse((self.data / PENDING_DIR).exists())

    def pending(self, phase_text):
        """A pending restore already on disk with that phase file, as a version before this check could leave it."""
        pending = self.data / PENDING_DIR
        pending.mkdir()
        (pending / "tasks.json").write_text('{"tarefa": 2}', encoding="utf-8")
        (pending / MANIFEST).write_text("{}", encoding="utf-8")
        (pending / PHASE_FILE).write_text(phase_text, encoding="utf-8")

    def assert_old_kept(self):
        kept = list((self.data / ASIDE_DIR).glob("*/tasks.json"))
        self.assertEqual(len(kept), 1, "os dados antigos sumiram")
        self.assertIn('"tarefa": 1', kept[0].read_text(encoding="utf-8"))
        self.assertIn('"tarefa": 2', (self.data / "tasks.json").read_text(encoding="utf-8"))

    def test_fase_ilegivel_nao_derruba_e_guarda_os_dados(self):
        self.pending("isto nao e json")
        apply_pending_restore(self.data)
        self.assert_old_kept()

    def test_stamp_para_fora_nao_tira_dados_da_pasta(self):
        self.pending(json.dumps({"step": "leaving", "stamp": "../../fora"}))
        apply_pending_restore(self.data)
        self.assertFalse((self.tmp / "fora").exists())
        self.assert_old_kept()

    def test_fase_que_diz_entrando_sem_stamp_valido_guarda_os_dados(self):
        self.pending(json.dumps({"step": "entering"}))
        apply_pending_restore(self.data)
        self.assert_old_kept()


class ConferirTest(ZipMontadoTest):
    """The summary shown before restoring: read from the zip, nothing extracted, nothing touched."""

    def test_zip_valido_com_contagens(self):
        (self.data / "terminal_sessions.json").write_text(json.dumps({"schema_version": 1, "data": [{}, {}, {}]}))
        (self.data / "notes.json").write_text(json.dumps({"schema_version": 1, "data": [{}]}))
        (self.data / "prompts").mkdir()
        (self.data / "prompts" / "a.md").write_text("x")
        (self.data / "agentes.db").write_bytes(b"x" * 100)
        made = create_backup(self.data, self.dest, "1.0.0")["path"]
        info = inspect_backup(made, self.data, "1.2.1")
        self.assertTrue(info["ok"])
        self.assertEqual(info["warnings"], [])
        self.assertEqual(info["version"], "1.0.0")
        self.assertTrue(info["created_at"])
        self.assertEqual(info["size"], Path(made).stat().st_size)
        self.assertEqual(info["counts"], {"terminal_sessions": 3, "tasks": None, "notes": 1, "prompts": 1,
                                          "memories": 1, "agent_index": 100})
        self.assertFalse((self.data / PENDING_DIR).exists())

    def test_versao_mais_nova_avisa_sem_impedir(self):
        info = inspect_backup(create_backup(self.data, self.dest, "9.0.0")["path"], self.data, "1.2.1")
        self.assertTrue(info["ok"])
        self.assertEqual([w["level"] for w in info["warnings"]], ["warn"])
        self.assertIn("9.0.0", info["warnings"][0]["text"])

    def test_os_quatro_zips_do_relatorio_nao_deixam_restaurar(self):
        for extra in ({".fase.json": json.dumps({"step": "entering"})}, {".fase.json": "isto nao e json"},
                      {".fase.json": json.dumps({"step": "leaving", "stamp": "../../fora"})}, {".RESTAUROS/x.txt": "x"}):
            with self.subTest(extra=list(extra)):
                info = inspect_backup(self.backup_with(extra), self.data, "1.2.1")
                self.assertFalse(info["ok"])
                self.assertEqual(info["warnings"][0]["level"], "error")
                self.assertFalse((self.data / PENDING_DIR).exists())
                self.assertFalse((self.tmp / "fora").exists())

    def test_manifesto_ausente_e_nao_zip(self):
        info = inspect_backup(self.zip_with({"tasks.json": "{}"}, manifest=False), self.data, "1.2.1")
        self.assertFalse(info["ok"])
        self.assertIn("manifesto", info["warnings"][0]["text"])
        bad = self.tmp / "nao.zip"
        bad.write_text("texto")
        self.assertFalse(inspect_backup(bad, self.data, "1.2.1")["ok"])
        with self.assertRaises(BackupError):
            inspect_backup(self.tmp / "sumiu.zip", self.data, "1.2.1")

    def test_acima_dos_limites_recusa(self):
        many = {f"m/{n}.txt": "" for n in range(MAX_MEMBERS + 1)}
        info = inspect_backup(self.zip_with(many), self.data, "1.2.1")
        self.assertFalse(info["ok"])
        self.assertIn(str(MAX_MEMBERS), info["warnings"][0]["text"])
        # the sizes the zip declares count, as a zip bomb would declare them; the limit is lowered to fit the test
        big = self.zip_with({"a.bin": "x" * 64})
        with mock.patch("vulcan_celox.core.backup_inspect.MAX_UNCOMPRESSED", 32):
            info = inspect_backup(big, self.data, "1.2.1")
        self.assertFalse(info["ok"])
        self.assertIn("2 GB", info["warnings"][0]["text"])


class AbrirComRestauracaoTest(BackupCase):
    def test_falha_na_troca_abre_e_avisa(self):
        prepare_restore(create_backup(self.data, self.dest, "9.9")["path"], self.data)
        with mock.patch("vulcan_celox.core.backup.apply_pending_restore", side_effect=OSError("disco")):
            lock, error = open_data_folder(self.data)
        self.addCleanup(lock.release)
        self.assertIn("disco", error)

    @unittest.skipIf(os.name == "nt", "sem trava compartilhada no Windows")
    def test_espera_a_instancia_velha_sair(self):
        other = DataLock(self.data)
        other.share()
        prepare_restore(create_backup(self.data, self.dest, "9.9")["path"], self.data)
        (self.data / "tasks.json").write_text('{"tarefa": "depois do backup"}', encoding="utf-8")
        with mock.patch("vulcan_celox.core.backup.RESTORE_WAIT", 0.2):
            lock, error = open_data_folder(self.data)
        self.assertIsNone(error)
        self.assertTrue((self.data / PENDING_DIR).is_dir(), "trocou com a outra instância aberta")
        lock.release()
        threading.Timer(0.3, other.release).start()
        with mock.patch("vulcan_celox.core.backup.RESTORE_WAIT", 5.0):
            lock, error = open_data_folder(self.data)
        self.addCleanup(lock.release)
        self.assertIsNone(error)
        self.assertFalse((self.data / PENDING_DIR).exists())
        self.assertIn('"tarefa": 1', (self.data / "tasks.json").read_text(encoding="utf-8"))

    def test_sem_restauracao_nao_espera(self):
        other = DataLock(self.data)
        other.share()
        self.addCleanup(other.release)
        started = time.monotonic()
        lock, error = open_data_folder(self.data)
        self.addCleanup(lock.release)
        self.assertLess(time.monotonic() - started, 1)
        self.assertIsNone(error)
