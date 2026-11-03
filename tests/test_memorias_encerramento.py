"""Memórias e encerramento."""

import sqlite3
import threading
import time
from unittest import mock

from tests.server_helpers import ServerTestCase
from vulcan_celox.core import doctor
from vulcan_celox.server import app as app_mod


class FlushTest(ServerTestCase):
    def setUp(self):
        super().setUp()
        for n in range(5):
            self.app.hub.sessions.create(f"aba00000000{n}", f"loja {n}", None, str(self.tmp))

    def test_excecao_numa_gravacao_nao_para_as_outras_nem_a_thread(self):
        hub = self.app.hub
        calls = []
        real = hub.write_memory

        def flaky(session_id, *args, **kwargs):
            calls.append(session_id)
            if session_id == "aba000000002":
                raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
            return real(session_id, *args, **kwargs)

        for n in range(5):
            hub.mark_dirty(f"aba00000000{n}")
        with mock.patch.object(hub, "write_memory", flaky):
            hub._flush_once()  # o que o laço da thread chama a cada 15 s
        self.assertEqual(sorted(calls), [f"aba00000000{n}" for n in range(5)])
        self.assertIn("aba000000002", hub._dirty)  # fica para a próxima volta
        self.assertIn("closed database", hub.last_error or "")
        info = doctor.collect(self.env())
        self.assertIn("closed database", info["memory_last_error"] or "")
        self.assertTrue(hub._flusher.is_alive())

    def test_indice_geral_uma_vez_por_flush(self):
        hub = self.app.hub
        for n in range(5):
            hub.mark_dirty(f"aba00000000{n}")
        with mock.patch.object(hub, "write_index", wraps=hub.write_index) as spy:
            hub.flush()
        self.assertEqual(spy.call_count, 1)


class VigiaTest(ServerTestCase):
    def test_vigia_grava_antes_de_sair(self):
        events = []
        app_mod._watch_parent(1234, shutdown=lambda: events.append("shutdown"), getppid=lambda: 1,
                              exit=lambda code: events.append(("exit", code)), interval=0.01)
        self.assertEqual(events, ["shutdown", ("exit", 0)])

    def test_shutdown_travado_nao_impede_a_saida(self):
        events = []
        started = time.monotonic()
        app_mod._watch_parent(1234, shutdown=lambda: time.sleep(30), getppid=lambda: 1,
                              exit=lambda code: events.append(("exit", code)), interval=0.01, grace=0.5)
        self.assertEqual(events, [("exit", 0)])
        self.assertLess(time.monotonic() - started, 3)

    def test_vigia_com_o_app_de_verdade_grava_a_memoria(self):
        self.app.hub.sessions.create("aba000000009", "loja", None, str(self.tmp))
        self.app.hub.mark_dirty("aba000000009")
        exited = threading.Event()
        app_mod._watch_parent(1234, shutdown=self.app.hub.flush, getppid=lambda: 1,
                              exit=lambda code: exited.set(), interval=0.01)
        record = self.app.hub.sessions.get("aba000000009")
        self.assertTrue(exited.is_set())
        self.assertTrue(record.memory_file)


class TimerTest(ServerTestCase):
    def test_timer_do_caderno_sob_lock(self):
        hub = self.app.hub
        threads = [threading.Thread(target=hub._on_notebook_change, args=("tasks",)) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        pending = [t for t in threading.enumerate() if isinstance(t, threading.Timer) and not t.finished.is_set()
                   and getattr(t.function, "__self__", None) is hub]
        self.assertLessEqual(len(pending), 1)  # um só timer deste hub continua valendo; os outros foram cancelados
