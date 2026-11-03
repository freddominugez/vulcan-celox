#!/usr/bin/env python3
"""Lista texto em português fora de t() nos módulos da interface. Uso: i18n_restos.py [arquivos]; sem argumento, todos."""

from __future__ import annotations

import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "vulcan_celox" / "web"
# módulos sem texto de interface: o t() não entra, e o teste os lê no node
FORA = {"i18n.mjs", "theme-boot.js"}
ACENTO = re.compile(r"[ãõáéíóúâêôçàÃÕÁÉÍÓÚÂÊÔÇ]")
PALAVRA = re.compile(r"\b(para|sem|com|não|nao|você|arquivo|arquivos|pasta|sessão|sessões|tarefa|tarefas|abrir|fechar|copiar|salvar|criar|buscar|nenhum|nenhuma|aba|abas|editar|remover|novo|nova|comando|comandos|site|sites|pedido|pedidos|agente|agentes|ligar|desligar|atualizar|carregar|voltar|ainda|erro|falhou|agora|hoje|ontem|dias)\b", re.I)
T_CALL = re.compile(r"""\bt\(\s*("(?:[^"\\]|\\.)*"|`[^`$]*`)""")
STRING = re.compile(r"""("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')""")


def sem_comentarios(linha: str) -> str:
    return "" if linha.strip().startswith(("//", "*", "/*")) else re.sub(r"\s//\s.*$", "", linha)


def restos(path: Path):
    achados = []
    for numero, linha in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        limpa = T_CALL.sub("t()", sem_comentarios(linha))
        if limpa.lstrip().startswith("import "):
            continue
        html = re.sub(r"\$\{[^{}]*\}", " ", limpa)
        textos = re.findall(r">([^<>]{2,})<", html) + re.findall(r'(?:title|aria-label|placeholder|alt)="([^"$]{2,})"', html)
        textos += [s[1:-1] for s in STRING.findall(limpa)]
        if any(ACENTO.search(x) or (PALAVRA.search(x) and " " in x.strip()) for x in textos) or ACENTO.search(html):
            achados.append((numero, linha.strip()))
    return achados


def main() -> int:
    alvos = [Path(a) for a in sys.argv[1:]] or [p for p in [*WEB.rglob("*.mjs"), WEB / "index.html"] if p.name not in FORA and "vendor" not in p.parts]
    total = 0
    for path in alvos:
        for numero, linha in restos(path):
            total += 1
            print(f"{path.name}:{numero}: {linha[:150]}")
    print(f"{total} linhas com texto fora de t()")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
