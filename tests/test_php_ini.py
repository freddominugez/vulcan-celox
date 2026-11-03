"""Os seis ajustes comuns do php.ini de usuário do Lerd, gravados pelo próprio `lerd php:ini`.

Prova de 2026-10-31 nesta máquina (registrada no progresso): com EDITOR apontando para um ajudante, o Lerd passou
~/.local/share/lerd/php/8.5/98-user.ini ao editor e reaplicou o PHP 8.5; memory_limit foi de 128M a 256M e voltou.
`lerd-98-user.ini` é o arquivo real de usuário do Lerd 1.37.1 (só comentários).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.helpers import FIXTURES, TempDirTestCase
from tests.server_helpers import ServerTestCase
from vulcan_terminal.core.php_ini import KEYS, parse_directives, set_directive

REAL = (FIXTURES / "lerd-98-user.ini").read_text(encoding="utf-8")


class DiretivaTest(TempDirTestCase):
    def test_arquivo_real_so_com_comentarios(self):
        self.assertEqual(parse_directives(REAL), {})
        text = set_directive(REAL, "memory_limit", "512M")
        self.assertTrue(text.startswith(REAL.rstrip("\n")))  # comentários e ordem preservados
        self.assertEqual(parse_directives(text), {"memory_limit": "512M"})
        self.assertIn("; memory_limit = 512M", text)  # o exemplo comentado continua

    def test_troca_a_linha_existente_sem_tocar_nas_outras(self):
        text = "; topo\nmemory_limit = 128M\n; meio\ndate.timezone = America/Sao_Paulo\n"
        changed = set_directive(text, "memory_limit", "1G")
        self.assertEqual(changed, "; topo\nmemory_limit = 1G\n; meio\ndate.timezone = America/Sao_Paulo\n")
        self.assertEqual(set_directive(changed, "memory_limit", None), "; topo\n; meio\ndate.timezone = America/Sao_Paulo\n")

    def test_seis_chaves(self):
        self.assertEqual(KEYS, ("memory_limit", "upload_max_filesize", "post_max_size", "max_execution_time",
                                "display_errors", "error_reporting"))
        with self.assertRaises(ValueError):
            set_directive("", "extension", "x.so")
        with self.assertRaises(ValueError):
            set_directive("", "memory_limit", "1G\nextension=evil.so")


class AjudanteTest(TempDirTestCase):
    def test_ajudante_de_editor_grava_com_backup(self):
        target = self.tmp / "98-user.ini"
        target.write_text(REAL, encoding="utf-8")
        env = dict(os.environ, VULCAN_PHP_INI_SET=json.dumps({"memory_limit": "256M", "display_errors": "On"}),
                   PYTHONPATH=str(Path(__file__).resolve().parent.parent))
        proc = subprocess.run([sys.executable, "-m", "vulcan_terminal.core.php_ini", str(target)], env=env,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(parse_directives(target.read_text(encoding="utf-8")),
                         {"memory_limit": "256M", "display_errors": "On"})
        backups = list(self.tmp.glob("98-user.ini.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), REAL)


class ApiTest(ServerTestCase):
    def env(self):
        env = super().env()
        lerd = self.tmp / "bin" / "lerd"
        lerd.parent.mkdir(parents=True, exist_ok=True)
        lerd.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(lerd, 0o755)
        self.lerd = lerd
        data = self.tmp / "lerd-data"
        (data / "php" / "8.5").mkdir(parents=True)
        (data / "php" / "8.5" / "98-user.ini").write_text("memory_limit = 128M\n", encoding="utf-8")
        (data / "php" / "shared").mkdir(parents=True)
        (data / "php" / "shared" / "95-shared.ini").write_text("; nada\n", encoding="utf-8")
        env.update({"VULCAN_LERD_BIN": str(lerd), "VULCAN_LERD_DATA": str(data), "SHELL": "/bin/sh",
                    "PATH": os.environ.get("PATH", "")})
        return env

    def tearDown(self):
        self.app.terminals.close_all()
        super().tearDown()

    def test_ler(self):
        data = self.request("GET", "/api/environment/php/8.5/ini")[1]
        self.assertEqual(data["values"], {"memory_limit": "128M"})
        self.assertTrue(data["path"].endswith("php/8.5/98-user.ini"))
        self.assertEqual(self.request("GET", "/api/environment/php/shared/ini")[1]["values"], {})

    def test_gravar_pelo_lerd_com_o_ajudante(self):
        status, data, _ = self.request("POST", "/api/environment/php/8.5/ini", body={"values": {"memory_limit": "512M"}})
        self.assertEqual(status, 200, data)
        call = self.fake.calls[-1]
        self.assertEqual(list(call.argv)[1:], ["php:ini", "8.5"])
        self.assertIn("php-ini-editor", call.env["EDITOR"])
        self.assertEqual(json.loads(call.env["VULCAN_PHP_INI_SET"]), {"memory_limit": "512M"})

    def test_invalidos(self):
        for body in ({"values": {"extension": "x.so"}}, {"values": {"memory_limit": "1G;evil"}}, {"values": {}}, {}):
            with self.subTest(body=body):
                self.assertEqual(self.request("POST", "/api/environment/php/8.5/ini", body=body)[0], 400)
        self.assertEqual(self.request("GET", "/api/environment/php/9.9/ini")[0], 400)

    def test_abrir_no_editor_numa_aba(self):
        status, info, _ = self.request("POST", "/api/environment/php/8.5/ini/open")
        self.assertEqual(status, 201, info)
        self.assertIn(f"{self.lerd} php:ini 8.5", " ".join(self.app.terminals.get(info["id"]).argv))

    def test_ajudante_ignora_a_pasta_atual(self):
        # `python -m` punha a pasta atual em sys.path; um re.py ou json.py ali era importado
        self.request("POST", "/api/environment/php/8.5/ini", body={"values": {"memory_limit": "512M"}})
        wrapper = self.fake.calls[-1].env["EDITOR"]
        script = Path(wrapper).read_text(encoding="utf-8")
        self.assertNotIn(" -m ", script)
        hostile = self.tmp / "hostil"
        hostile.mkdir()
        marker = self.tmp / "importou"
        for name in ("re.py", "json.py", "runpy.py", "vulcan_terminal.py"):
            (hostile / name).write_text(f"open({str(marker)!r}, 'w').write('x')\n", encoding="utf-8")
        target = self.tmp / "98-user.ini"
        target.write_text("memory_limit = 128M\n", encoding="utf-8")
        env = dict(os.environ, VULCAN_PHP_INI_SET=json.dumps({"memory_limit": "256M"}))
        env.pop("PYTHONPATH", None)
        done = subprocess.run([wrapper, str(target)], cwd=str(hostile), env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(marker.exists(), "o ajudante importou um módulo da pasta atual")
        self.assertEqual(parse_directives(target.read_text(encoding="utf-8")), {"memory_limit": "256M"})
