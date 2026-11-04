"""Contrast measured on the token pairs the interface really uses, in both themes. Target: 4.5:1 text; 3:1 focus and controls."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLES = ROOT / "vulcan_celox" / "web" / "styles"
TOKENS = (STYLES / "tokens.css").read_text(encoding="utf-8")
LOOSE = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(")

TEXT_PAIRS = [(fg, bg) for fg in ("--fg", "--fg-2", "--fg-3") for bg in ("--bg", "--bg-side", "--bg-raise", "--bg-input", "--bg-pop", "--bg-dialog")]
TEXT_PAIRS += [("--accent-text", "--bg"), ("--accent-text", "--bg-side"), ("--accent-text", "--bg-raise"), ("--link", "--bg"), ("--link", "--bg-raise"),
               ("--on-accent", "--accent"), ("--on-accent", "--accent-hover"), ("--on-accent", "--accent-strong"),
               ("--ok-text", "--bg-raise"), ("--warn-text", "--bg-raise"), ("--err-text", "--bg-raise"),
               ("--ok-text", "--bg"), ("--warn-text", "--bg"), ("--err-text", "--bg"),
               ("--alert-fg", "--alert-bg"), ("--code-fg", "--code-bg"), ("--code-keyword", "--code-bg"), ("--code-string", "--code-bg"),
               ("--code-number", "--code-bg"), ("--code-comment", "--code-bg"), ("--code-function", "--code-bg"), ("--code-type", "--code-bg"),
               ("--code-property", "--code-bg"), ("--on-dark", "--bg-term")]
TEXT_PAIRS += [(f"--note-{c}-fg", f"--note-{c}-bg") for c in ("amarelo", "rosa", "verde", "azul", "laranja", "roxo")]
SOFT_PAIRS = [("--ok-text", "--ok-soft", "--bg-raise"), ("--warn-text", "--warn-soft", "--bg-raise"), ("--err-text", "--err-soft", "--bg-raise"),
              ("--err-text", "--err-soft-2", "--bg-raise"), ("--accent-text", "--accent-soft", "--bg-raise"), ("--fg", "--selection", "--bg")]
CONTROL_PAIRS = [("--accent-line", "--bg"), ("--accent-line", "--bg-raise"), ("--line-strong", "--bg-input"), ("--accent", "--bg")]


def block(selector):
    match = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", TOKENS, re.S)
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", match.group(1)))


BASE = block(":root")
THEMES = {"claro": {**BASE, **block(':root, :root[data-theme="claro"]')}}
THEMES["escuro"] = {**THEMES["claro"], **block(':root[data-theme="escuro"]')}


def resolve(theme, name):
    value = THEMES[theme][name].strip()
    while value.startswith("var("):
        value = THEMES[theme][value[4:-1].strip()].strip()
    return value


def rgba(value):
    if value.startswith("#"):
        h = value[1:]
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (1.0,)
    parts = re.findall(r"[\d.]+", value)
    return (int(parts[0]), int(parts[1]), int(parts[2]), float(parts[3]) if len(parts) > 3 else 1.0)


def over(top, bottom):
    a = top[3]
    return tuple(top[i] * a + bottom[i] * (1 - a) for i in range(3)) + (1.0,)


def luminance(c):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(c[0]) + 0.7152 * channel(c[1]) + 0.0722 * channel(c[2])


def ratio(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class ContrasteTest(unittest.TestCase):
    def check(self, fg, bg, minimum, theme, under=None):
        back = rgba(resolve(theme, bg))
        if under:
            back = over(back, rgba(resolve(theme, under)))
        front = over(rgba(resolve(theme, fg)), back)
        got = ratio(front, back)
        self.assertGreaterEqual(got, minimum, f"{theme}: {fg} sobre {bg}{' sobre ' + under if under else ''} = {got:.2f}")

    def test_texto(self):
        for theme in THEMES:
            for fg, bg in TEXT_PAIRS:
                with self.subTest(tema=theme, par=(fg, bg)):
                    self.check(fg, bg, 4.5, theme)

    def test_texto_sobre_fundo_translucido(self):
        for theme in THEMES:
            for fg, soft, under in SOFT_PAIRS:
                with self.subTest(tema=theme, par=(fg, soft)):
                    self.check(fg, soft, 4.5, theme, under)

    def test_foco_e_controles(self):
        for theme in THEMES:
            for fg, bg in CONTROL_PAIRS:
                with self.subTest(tema=theme, par=(fg, bg)):
                    self.check(fg, bg, 3.0, theme)

    def test_escuro_so_redefine_o_que_o_claro_tem(self):
        claro, escuro = block(':root, :root[data-theme="claro"]'), block(':root[data-theme="escuro"]')
        self.assertEqual(set(escuro) - set(claro), set())


class AreaDoTerminalTest(unittest.TestCase):
    """Inside .ws-body the background is always dark, even in the light theme."""

    def test_texto_legivel(self):
        match = re.search(r"\.ws-body \{(.*?)\n\}", TOKENS, re.S)
        scope = dict(re.findall(r"(--[\w-]+):\s*([^;]+);", match.group(1)))
        for name in ("--fg", "--fg-2", "--fg-3", "--accent-text"):
            for back in ("--bg-raise", "--bg-input"):
                self.assertGreaterEqual(ratio(rgba(scope[name]), rgba(scope[back])), 4.5, (name, back))
            self.assertGreaterEqual(ratio(rgba(scope[name]), rgba(BASE["--bg-term"])), 4.5, name)


class TokensTest(unittest.TestCase):
    def test_nenhuma_cor_solta_fora_de_tokens(self):
        for path in STYLES.glob("*.css"):
            if path.name == "tokens.css":
                continue
            with self.subTest(arquivo=path.name):
                self.assertEqual(LOOSE.findall(path.read_text(encoding="utf-8")), [])

    def test_todo_token_usado_existe(self):
        known = set(THEMES["escuro"]) | set(re.findall(r"(--[\w-]+)\s*:", (STYLES / "app.css").read_text(encoding="utf-8")))
        known |= set(re.findall(r"(--[\w-]+)\s*:", (STYLES / "agents.css").read_text(encoding="utf-8")))
        known |= set(re.findall(r"(--[\w-]+)\s*:", (STYLES / "code.css").read_text(encoding="utf-8")))
        known |= {"--t", "--t-bg", "--t-ink", "--depth"}
        js = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "vulcan_celox" / "web" / "js").rglob("*.mjs"))
        known |= set(re.findall(r"(--[\w-]+)\s*:", js))
        missing = {}
        for path in STYLES.glob("*.css"):
            names = set(re.findall(r"var\((--[\w-]+)", path.read_text(encoding="utf-8"))) - known
            if names:
                missing[path.name] = sorted(names)
        self.assertEqual(missing, {})

    def test_laranja_saiu(self):
        for path in [*(ROOT / "vulcan_celox" / "web" / "styles").glob("*.css"), *(ROOT / "vulcan_celox" / "web" / "js").glob("*.mjs")]:
            self.assertNotRegex(path.read_text(encoding="utf-8").lower(), r"#ff4f2b|#ff6a4a|255, ?79, ?43", path.name)


class MovimentoEMarcaTest(unittest.TestCase):
    def test_nenhuma_transicao_acima_de_240_ms(self):
        for path in STYLES.glob("*.css"):
            for value, unit in re.findall(r"transition[^;{}]*?\b([\d.]+)(ms|s)\b", path.read_text(encoding="utf-8")):
                ms = float(value) * (1000 if unit == "s" else 1)
                self.assertLessEqual(ms, 240, f"{path.name}: {value}{unit}")

    def test_movimento_reduzido(self):
        self.assertIn("prefers-reduced-motion: reduce", TOKENS)

    def test_ativos_da_marca_existem(self):
        web = STYLES.parent
        html = (web / "index.html").read_text(encoding="utf-8") + (web / "js" / "brand.mjs").read_text(encoding="utf-8")
        refs = re.findall(r'(?:src|href)="(img/brand/[^"]+)"', html)
        self.assertGreaterEqual(len(refs), 6)
        for ref in refs:
            self.assertTrue((web / ref).is_file(), ref)
        self.assertFalse(re.search(r"filter:\s*(?!none)", (STYLES / "app.css").read_text(encoding="utf-8").split("/* Marca */")[1]))

    def test_sem_favicon_reprovado(self):
        index = (STYLES.parent / "index.html").read_text(encoding="utf-8")
        self.assertNotRegex(index, r'sizes="(16x16|32x32)"')
        self.assertFalse((STYLES.parent / "img" / "brand" / "favicon-16.png").exists())
