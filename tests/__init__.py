"""Suíte do Vulcan Terminal.

Vigia: se a suíte passar de 15 min (normal: cerca de 2 min), despeja a pilha de todas as threads e sai com erro,
para o validate.sh falhar com a causa em vez de ficar parado. Uma rodada travou uma vez em 2026-10-31
e não se repetiu em cinco rodadas seguidas; se voltar, a pilha mostra onde.
"""

import faulthandler
import sys

faulthandler.dump_traceback_later(900, repeat=False, file=sys.stderr, exit=True)
