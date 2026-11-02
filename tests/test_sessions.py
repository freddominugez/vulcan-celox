from tests.helpers import TempDirTestCase
from vulcan_terminal.core.sessions import InputTracker, SessionRecord, SessionStore
from vulcan_terminal.core.store import Store


class InputTrackerTest(TempDirTestCase):
    def feed(self, *chunks):
        tracker = InputTracker()
        out = []
        for chunk in chunks:
            out += tracker.feed(chunk if isinstance(chunk, bytes) else chunk.encode())
        return out

    def test_linha_simples(self):
        self.assertEqual(self.feed("ls -la\r"), ["ls -la"])

    def test_backspace_e_delete(self):
        self.assertEqual(self.feed("gti\x7f\x7fit status\r"), ["git status"])
        self.assertEqual(self.feed("pwdx\x08\r"), ["pwd"])

    def test_ctrl_u_ctrl_c_ctrl_w(self):
        self.assertEqual(self.feed("abc\x15pwd\r"), ["pwd"])
        self.assertEqual(self.feed("rm -rf algo\x03echo ok\r"), ["echo ok"])
        self.assertEqual(self.feed("git comit\x17commit\r"), ["git commit"])

    def test_setas_e_escape_ignorados(self):
        self.assertEqual(self.feed("\x1b[A\r"), [])
        self.assertEqual(self.feed("ls\x1b[D\x1bOC -l\r"), ["ls -l"])

    def test_escape_dividido_entre_pedacos(self):
        self.assertEqual(self.feed("echo a\x1b[", "1;5D b\r"), ["echo a b"])

    def test_colagem_com_marcadores(self):
        self.assertEqual(self.feed("\x1b[200~echo 1\x1b[201~\r"), ["echo 1"])
        self.assertEqual(self.feed("\x1b[200~echo 1\recho 2\x1b[201~\r"), ["echo 1", "echo 2"])

    def test_linhas_vazias_e_utf8_dividido(self):
        acao = "echo ação\r".encode()
        self.assertEqual(self.feed(b"\r\r", acao[:7], acao[7:]), ["echo ação"])


class SessionStoreTest(TempDirTestCase):
    def test_roundtrip_e_listagem(self):
        store = SessionStore(Store(self.tmp))
        a = store.create("aaa111", "loja", "loja", "/p/loja")
        store.create("bbb222", "blog", "blog", "/p/blog")
        store.create("ccc333", "loja 2", "loja", "/p/loja")
        store.add_commands("aaa111", ["ls", "git status"])
        store.set_tags("aaa111", ["t1", "t1", "t2"])
        store.close("aaa111", exit_code=0)
        store.rename("ccc333", "migrations")

        again = SessionStore(Store(self.tmp))
        rec = again.get("aaa111")
        self.assertEqual([c["cmd"] for c in rec.commands], ["ls", "git status"])
        self.assertEqual(rec.tags, ["t1", "t2"])
        self.assertFalse(rec.is_open)
        self.assertEqual(rec.exit_code, 0)
        split = again.split("loja")
        self.assertEqual([r.id for r in split["open"]], ["ccc333"])
        self.assertEqual([r.id for r in split["closed"]], ["aaa111"])
        self.assertEqual(again.get("ccc333").title, "migrations")
        self.assertEqual(len(again.list()), 3)
        self.assertIsNotNone(a.created_at)

    def test_fechar_de_novo_nao_muda_data(self):
        store = SessionStore(Store(self.tmp))
        store.create("x1", "t", None, "/")
        first = store.close("x1", 0).closed_at
        self.assertEqual(store.close("x1", 1).closed_at, first)
        self.assertEqual(store.get("x1").exit_code, 0)

    def test_orfas_na_inicializacao(self):
        store = SessionStore(Store(self.tmp))
        store.create("vivo", "a", None, "/")
        store.create("morto", "b", None, "/")
        closed = SessionStore(Store(self.tmp)).close_orphans(["vivo"])
        self.assertEqual([r.id for r in closed], ["morto"])
        reloaded = SessionStore(Store(self.tmp))
        self.assertTrue(reloaded.get("vivo").is_open)
        self.assertFalse(reloaded.get("morto").is_open)

    def test_registro_tolerante(self):
        self.assertIsNone(SessionRecord.from_dict({"title": "sem id"}))
        rec = SessionRecord.from_dict({"id": "z", "commands": [{"cmd": ""}, {"cmd": "ls"}, "lixo"], "tags": [1, "t"]})
        self.assertEqual((rec.commands, rec.tags), ([{"cmd": "ls"}], ["t"]))

    def test_remove_tag_everywhere(self):
        store = SessionStore(Store(self.tmp))
        store.create("s1", "a", None, "/")
        store.set_tags("s1", ["t1", "t2"])
        store.remove_tag_everywhere("t1")
        self.assertEqual(SessionStore(Store(self.tmp)).get("s1").tags, ["t2"])
