"""App server in temporary directories for API tests."""

import http.client
import json

from tests.helpers import TempDirTestCase
from vulcan_celox.core.runner import FakeRunner
from vulcan_celox.server.app import VulcanApp


class ServerTestCase(TempDirTestCase):
    token = "token-de-teste-123"

    def env(self):
        return {"VULCAN_CELOX_HOME": str(self.tmp / "home"), "VULCAN_LEGACY_HOME": str(self.tmp / "legacy"),
                "VULCAN_VALET_HOME": str(self.tmp / "valet"), "VULCAN_VALET_BIN": str(self.tmp / "sem-valet"),
                "VULCAN_LERD_BIN": str(self.tmp / "sem-lerd"), "VULCAN_LERD_DATA": str(self.tmp / "lerd"),
                "VULCAN_LERD_API": "http://127.0.0.1:1", "HOME": str(self.tmp), "VULCAN_LANGUAGE": "pt"}

    def setUp(self):
        super().setUp()
        self.fake = FakeRunner()
        self.app = VulcanApp(env=self.env(), runner=self.fake, token=self.token)
        self.app.autostart.start_wait = 0  # a fake start must not wait for an environment that never answers
        self.app.start()

    def tearDown(self):
        self.app.shutdown()
        super().tearDown()

    def request(self, method, path, body=None, token=True, host=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.app.server.port, timeout=10)
        hdrs = {"Host": host or f"127.0.0.1:{self.app.server.port}"}
        if token:
            hdrs["X-Vulcan-Token"] = self.token if token is True else token
        if body is not None or method in ("POST", "PUT", "PATCH"):
            hdrs["Content-Type"] = "application/json"  # as the interface (api.mjs) and the shell do
        hdrs.update(headers or {})
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        ctype = resp.getheader("Content-Type") or ""
        data = json.loads(raw) if ctype.startswith("application/json") and raw else raw
        return resp.status, data, resp
