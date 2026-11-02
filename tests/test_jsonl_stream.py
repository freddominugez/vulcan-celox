"""vt-16 C2: leitura incremental de JSONL tolerante a linha cortada, lixo, linha grande e encolhimento."""

import json
import unittest

from tests.helpers import TempDirTestCase
from vulcan_terminal.core.agents.jsonl_stream import LineStream, iter_lines


def line(obj) -> bytes:
    return (json.dumps(obj) + "\n").encode("utf-8")


class JsonlStreamTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.path = self.tmp / "s.jsonl"

    def read(self, offset=0, **kw):
        stream = LineStream(self.path, offset, **kw)
        objs = [obj for _, obj in stream]
        return objs, stream

    def test_arquivo_crescendo_em_tres_escritas(self):
        self.path.write_bytes(line({"n": 1}))
        objs, s = self.read()
        self.assertEqual(objs, [{"n": 1}])
        with self.path.open("ab") as f:
            f.write(line({"n": 2}) + line({"n": 3}))
        objs, s = self.read(s.offset)
        self.assertEqual(objs, [{"n": 2}, {"n": 3}])
        with self.path.open("ab") as f:
            f.write(line({"n": 4}))
        objs, s2 = self.read(s.offset)
        self.assertEqual(objs, [{"n": 4}])
        self.assertEqual(s2.offset, self.path.stat().st_size)
        self.assertFalse(s2.reset)

    def test_linha_cortada_fica_para_a_proxima_leitura(self):
        full = line({"texto": "olá mundo"})
        self.path.write_bytes(line({"n": 1}) + full[:9])
        objs, s = self.read()
        self.assertEqual(objs, [{"n": 1}])
        self.assertEqual(s.offset, len(line({"n": 1})))
        self.assertEqual(s.errors, [])
        with self.path.open("ab") as f:
            f.write(full[9:])
        objs, s = self.read(s.offset)
        self.assertEqual(objs, [{"texto": "olá mundo"}])

    def test_json_invalido_e_registrado_e_pulado(self):
        self.path.write_bytes(line({"n": 1}) + b"{isto nao e json\n" + b"[1, 2]\n" + line({"n": 2}))
        objs, s = self.read()
        self.assertEqual(objs, [{"n": 1}, {"n": 2}])
        self.assertEqual([e[1] for e in s.errors], ["json inválido", "não é objeto"])
        self.assertEqual(s.offset, self.path.stat().st_size)

    def test_linha_grande_e_descartada(self):
        big = line({"blob": "x" * 2000})
        self.path.write_bytes(line({"n": 1}) + big + line({"n": 2}))
        objs, s = self.read(max_line=500)
        self.assertEqual(objs, [{"n": 1}, {"n": 2}])
        self.assertEqual(len(s.errors), 1)
        self.assertIn("linha acima", s.errors[0][1])

    def test_linha_grande_ainda_sendo_escrita_espera(self):
        self.path.write_bytes(line({"n": 1}) + b'{"blob": "' + b"x" * 2000)
        objs, s = self.read(max_line=500)
        self.assertEqual(objs, [{"n": 1}])
        self.assertEqual(s.offset, len(line({"n": 1})))
        self.assertEqual(s.errors, [])

    def test_arquivo_que_encolheu_recomeca_do_zero(self):
        self.path.write_bytes(line({"n": 1}) + line({"n": 2}))
        _, s = self.read()
        self.path.write_bytes(line({"n": 9}))
        objs, s2 = self.read(s.offset)
        self.assertTrue(s2.reset)
        self.assertEqual(objs, [{"n": 9}])

    def test_crlf_e_linhas_vazias(self):
        self.path.write_bytes(b'{"n": 1}\r\n\n' + line({"n": 2}))
        objs, s = self.read()
        self.assertEqual(objs, [{"n": 1}, {"n": 2}])
        self.assertEqual(s.errors, [])

    def test_arquivo_ausente_nao_quebra(self):
        objs, s = self.read()
        self.assertEqual(objs, [])
        self.assertEqual(s.offset, 0)
        self.assertTrue(s.missing)

    def test_iter_lines_devolve_ordinal_obj_e_offset(self):
        self.path.write_bytes(line({"n": 1}) + line({"n": 2}))
        out = list(iter_lines(self.path, 0))
        self.assertEqual([(o, obj) for o, obj, _ in out], [(0, {"n": 1}), (1, {"n": 2})])
        self.assertEqual(out[-1][2], self.path.stat().st_size)


if __name__ == "__main__":
    unittest.main()
