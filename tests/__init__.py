"""Suíte do Vulcan Celox.

Vigia: se a suíte passar de 15 min (normal: cerca de 2 min), despeja a pilha de todas as threads e sai com erro,
para o validate.sh falhar com a causa em vez de ficar parado. Uma rodada travou uma vez em 2026-10-31
e não se repetiu em cinco rodadas seguidas; se voltar, a pilha mostra onde.
"""

import faulthandler
import sys

faulthandler.dump_traceback_later(900, repeat=False, file=sys.stderr, exit=True)

import os  # noqa: E402

# a suíte confere o texto-fonte, inclusive nos subprocessos; o inglês tem teste próprio (tests/test_i18n.py)
os.environ["VULCAN_LANGUAGE"] = "pt"

from vulcan_celox.core import i18n  # noqa: E402

i18n.DEFAULT = "pt"
i18n.set_language("pt")
