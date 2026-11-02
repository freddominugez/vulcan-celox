"""Gera docs/pt-BR/user-guide.md a partir de vulcan_terminal/web/help/conteudo.json (vt-26 C4).

Uso: python3 scripts/manual_md.py [saida.md]   (padrão: docs/pt-BR/user-guide.md)
O conteúdo da Ajuda do app e o manual em Markdown saem do mesmo arquivo; o validate.sh compara os dois.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "vulcan_terminal" / "web" / "help" / "conteudo.json"
IMG = "../../vulcan_terminal/web/img/manual"


def block(b):
    if "p" in b:
        return b["p"]
    if "ul" in b:
        return "\n".join(f"- {t}" for t in b["ul"])
    if "passos" in b:
        return "\n".join(f"{i}. {t}" for i, t in enumerate(b["passos"], 1))
    if "img" in b:
        return f"![{b.get('alt', '')}]({IMG}/{b['img']})"
    if "atalhos" in b:
        rows = "\n".join(f"| `{k}` | {d} |" for k, d in b["atalhos"])
        return "| Atalho | Faz |\n|--------|-----|\n" + rows
    return ""


def render(data):
    out = ["# Manual do Vulcan Terminal", "",
           "> Gerado por `scripts/manual_md.py` a partir de `vulcan_terminal/web/help/conteudo.json`, o mesmo conteúdo da tela Ajuda do app (⌘?). Não edite este arquivo à mão.",
           "", "## Sumário", ""]
    out += [f"- [{s['titulo']}](#{s['id']}): {s['resumo']}" for s in data["secoes"]]
    out += ["- [Perguntas frequentes](#perguntas-frequentes)", ""]
    for s in data["secoes"]:
        out += [f'<a id="{s["id"]}"></a>', "", f"## {s['titulo']}", "", f"*{s['resumo']}*", ""]
        for b in s["blocos"]:
            out += [block(b), ""]
    out += ['<a id="perguntas-frequentes"></a>', "", "## Perguntas frequentes", ""]
    for f in data["faq"]:
        out += [f"**{f['q']}**", "", f["a"], ""]
    return "\n".join(out).rstrip() + "\n"


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "pt-BR" / "user-guide.md"
    target.write_text(render(json.loads(SRC.read_text(encoding="utf-8"))), encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
