"""Table of Lerd workarounds and the --doctor block (behavior does not change with the version)."""
import unittest

from tests.helpers import TempDirTestCase, unix_only, SEM_LERD
from tests.lerd_api_stub import LerdApiStub, closed_port_url
from tests import test_doctor
from vulcan_celox.core import lerd_quirks
from vulcan_celox.core.doctor import collect
from vulcan_celox.core.lerd_quirks import Quirk


class QuirksTest(unittest.TestCase):
    def test_tres_contornos_sem_correcao_publicada(self):
        ids = [q.id for q in lerd_quirks.QUIRKS]
        self.assertEqual(ids, ["dump-clear-csrf", "dump-status-addr", "php-ini-names"])
        self.assertTrue(all(q.corrigido_em is None for q in lerd_quirks.QUIRKS))
        self.assertEqual(lerd_quirks.status("1.37.1")["necessarios"], 3)

    def test_correcao_simulada_por_versao(self):
        quirks = (Quirk("a", "d", "c", corrigido_em="1.38.2"), Quirk("b", "d", "c"))
        antes = lerd_quirks.status("1.38.1", quirks)
        depois = lerd_quirks.status("v1.38.2", quirks)
        self.assertEqual([r["necessario"] for r in antes["contornos"]], [True, True])
        self.assertEqual([r["necessario"] for r in depois["contornos"]], [False, True])
        self.assertEqual(depois["necessarios"], 1)
        desconhecida = lerd_quirks.status("", quirks)  # no version: everything stays needed
        self.assertEqual(desconhecida["necessarios"], 2)
        self.assertEqual(lerd_quirks.version_tuple("1.38.0-beta.3"), (1, 38, 0))
        self.assertIsNone(lerd_quirks.version_tuple("lerd"))


class DoctorContornosTest(TempDirTestCase):
    _fake_lerd = test_doctor.DoctorTest._fake_lerd  # without importing the class: its tests do not run twice
    _env = test_doctor.DoctorTest._env

    @unix_only(SEM_LERD)
    def test_bloco_no_doctor(self):
        with LerdApiStub() as stub:
            data = collect(self._env(stub.url, self._fake_lerd()))
        block = data["lerd_contornos"]
        self.assertEqual((block["versao"], block["necessarios"]), ("1.34.3", 3))
        self.assertEqual({r["id"] for r in block["contornos"]}, {"dump-clear-csrf", "dump-status-addr", "php-ini-names"})

    def test_sem_lerd_sem_bloco(self):
        self.assertIsNone(collect(self._env(closed_port_url()))["lerd_contornos"])
