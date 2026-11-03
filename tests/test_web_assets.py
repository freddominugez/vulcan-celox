"""A interface web só referencia arquivos locais que existem e são servidos."""

import re
import subprocess
import shutil
import unittest
from pathlib import Path

from tests.server_helpers import ServerTestCase

WEB = Path(__file__).resolve().parent.parent / "vulcan_terminal" / "web"
REF = re.compile(r'(?:src|href)="([^"#]+)"')
IMPORT = re.compile(r'from\s+"(\.{1,2}/[^"]+)"')
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc")
EXTERNAL = re.compile(r'(?:src|href)="https?://|@import\s+url\(\s*["\']?https?://|url\(\s*["\']?https?://|from\s+"https?://')


def local_refs():
    refs = {"index.html"}
    html = (WEB / "index.html").read_text(encoding="utf-8")
    refs.update(r for r in REF.findall(html) if not r.startswith(("http", "data:")))
    for module in WEB.glob("js/**/*.mjs"):
        for rel in IMPORT.findall(module.read_text(encoding="utf-8")):
            refs.add(str((module.parent / rel).resolve().relative_to(WEB.resolve())))
    return sorted(refs)


class WebAssetsTest(ServerTestCase):
    def test_referencias_existem_e_sao_servidas(self):
        refs = local_refs()
        self.assertIn("js/app.mjs", refs)
        self.assertIn("js/views/site.mjs", refs)
        for ref in refs:
            self.assertTrue((WEB / ref).is_file(), ref)
            status, _, resp = self.request("GET", "/" + ref, token=False)
            self.assertEqual(status, 200, ref)
            if ref.endswith((".mjs", ".js")):
                self.assertTrue(resp.getheader("Content-Type").startswith("text/javascript"), ref)

    def test_sem_recurso_externo(self):
        for path in [WEB / "index.html", *WEB.glob("styles/*.css"), *WEB.glob("js/**/*.mjs")]:
            self.assertIsNone(EXTERNAL.search(path.read_text(encoding="utf-8")), path.name)

    @unittest.skipUnless(shutil.which("node"), "node ausente")
    def test_sintaxe_dos_modulos(self):
        for module in WEB.glob("js/**/*.mjs"):
            proc = subprocess.run(["node", "--check", str(module)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"{module.name}: {proc.stderr}")

    @unittest.skipUnless(JSC.is_file() and not shutil.which("node"), "jsc ausente ou node disponível")
    def test_sintaxe_dos_modulos_com_javascriptcore(self):
        # sem node no macOS: o jsc do sistema roda o módulo; fora do navegador ele para em ReferenceError
        # (window, document), mas um erro de sintaxe aparece como SyntaxError antes de executar
        for module in WEB.glob("js/**/*.mjs"):
            proc = subprocess.run([str(JSC), "-m", str(module)], capture_output=True, text=True, timeout=20)
            self.assertNotIn("SyntaxError", proc.stdout + proc.stderr, module.name)


# Campo sem contorno de foco precisa de outro sinal de foco, no próprio campo ou no contêiner
FOCO_SUBSTITUTO = {
    ".ag-search input": ".ag-search:focus-within",
    ".term-search-input": ".term-search-input:focus",
    ".side-filter input, .search-field input": ".side-filter:focus-within",
    ".task-add-input": ".task-add:focus-within",
    ".input-bare": ".task-add-field:focus-within",
    ".input, .select": ".input:focus, .select:focus",
    ".note-text": ".note:focus-within",
    ".note-tag-input": ".note:focus-within",
    ".palette-field input": ".palette-field:focus-within",
    ".folder-input": ".folder-field:focus-within",
    ".hp-search input": ".hp-search:focus-within",
}


class FocoVisivelTest(unittest.TestCase):
    def test_outline_none_tem_substituto(self):
        css = "\n".join(p.read_text(encoding="utf-8") for p in sorted((WEB / "styles").glob("*.css")))
        rules = re.findall(r"([^{}]+)\{([^}]*)\}", css)
        sem_contorno = []
        for selector, body in rules:
            selector = " ".join(selector.split())
            if re.search(r"outline:\s*(none|0)\b", body) and ":focus" not in selector:
                sem_contorno.append(selector)
        for selector in sem_contorno:
            with self.subTest(selector=selector):
                self.assertIn(selector, FOCO_SUBSTITUTO, "outline: none sem substituto de foco conhecido")
                self.assertIn(FOCO_SUBSTITUTO[selector], css)

    def test_teclado_nas_abas_e_tarefas(self):
        terminals = (WEB / "js" / "terminals.mjs").read_text(encoding="utf-8")
        self.assertIn('role="tab" tabindex=', terminals)
        self.assertIn("onTabKey", terminals)
        tasks = (WEB / "js" / "views" / "tasks.mjs").read_text(encoding="utf-8")
        self.assertIn('class="task-title" data-action="edit" tabindex="0"', tasks)


EVERY_SCRIPT = r"""
globalThis.window = {};
globalThis.location = { hash: "", search: "", pathname: "/", host: "127.0.0.1:1" };
globalThis.sessionStorage = { getItem: () => "t", setItem: () => {} };
globalThis.history = { replaceState: () => {} };
globalThis.document = { hidden: true };
const { every } = await import(process.argv[1]);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
let calls = 0;
let running = 0;
let overlap = 0;
const stop = every(10, async () => {
  calls += 1; running += 1; if (running > 1) overlap += 1;
  await wait(30); running -= 1;
});
await wait(120);
const hidden = calls;
document.hidden = false;
await wait(200);
const visible = calls;
stop();
await wait(100);
console.log(JSON.stringify({ hidden, visible, after: calls, overlap }));
"""


class PollingTest(unittest.TestCase):
    """Repetição encadeada, sem sobreposição, pausada com a janela oculta."""

    @unittest.skipUnless(shutil.which("node"), "node ausente")
    def test_every(self):
        import json
        api = (WEB / "js" / "api.mjs").as_uri()
        proc = subprocess.run(["node", "--input-type=module", "-e", EVERY_SCRIPT, api], capture_output=True,
                              text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["hidden"], 0)
        self.assertGreaterEqual(result["visible"], 2)
        self.assertEqual(result["overlap"], 0)
        self.assertEqual(result["after"], result["visible"])  # parou de verdade


REMOUNT_SCRIPT = """
const m = await import(process.argv[1]);
const out = {};
for (const r of ["overview", "terminals", "tasks", "depuracao", "desconhecida", "prompts", "node-projeto", "node",
                 "site", "agentes", "inicio", "ajuda", "ambiente"]) out[r] = m.remountsOnSites(r);
console.log(JSON.stringify(out));
"""


class AtalhosLinuxTest(unittest.TestCase):
    def test_busca_aceita_o_shift_do_linux(self):
        """No Linux o modificador é Ctrl+Shift; exigir "sem Shift" fazia o atalho nunca disparar."""
        src = (WEB / "js" / "global-events.mjs").read_text(encoding="utf-8")
        self.assertIn('key === "f" && (!isMac || !event.shiftKey)', src)


class RemountTest(unittest.TestCase):
    """Só remonta com a lista de sites nova a tela que recebeu essa lista."""

    @unittest.skipUnless(shutil.which("node"), "node ausente")
    def test_regra(self):
        import json
        mod = (WEB / "js" / "remount.mjs").as_uri()
        proc = subprocess.run(["node", "--input-type=module", "-e", REMOUNT_SCRIPT, mod], capture_output=True,
                              text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        for route in ("overview", "terminals", "tasks", "depuracao", "desconhecida"):
            self.assertTrue(out[route], route)
        for route in ("prompts", "node-projeto", "node", "site", "agentes", "inicio", "ajuda", "ambiente"):
            self.assertFalse(out[route], route)

    def test_app_usa_a_regra(self):
        app = (WEB / "js" / "app.mjs").read_text(encoding="utf-8")
        self.assertIn("sitesChanged && remountsOnSites(app.route.name)", app)
