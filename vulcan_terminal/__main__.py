"""Ponto de entrada: python3 -m vulcan_terminal [--selftest]."""

from __future__ import annotations

import argparse
import sys

from vulcan_terminal import APP_NAME, __version__


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="vulcan-terminal", description=APP_NAME)
    parser.add_argument("--selftest", action="store_true",
                        help="abre a janela, exercita a UI por 1 s e sai (0 = ok)")
    parser.add_argument("--doctor", action="store_true",
                        help="imprime em JSON o backend detectado, o estado do ambiente e os sites")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("--serve", action="store_true",
                        help="inicia o servidor local (API, terminais e interface web) e imprime VULCAN_PORT")
    parser.add_argument("--port", type=int, default=0, help="porta do --serve (0 = aleatória)")
    parser.add_argument("--tk", action="store_true", help="abre a interface tkinter antiga")
    parser.add_argument("--reindexar-agentes", action="store_true",
                        help="reconstrói do zero o índice das sessões do Claude Code e do Codex e imprime o total")
    parser.add_argument("--podar-agentes", type=int, nargs="?", const=180, metavar="DIAS",
                        help="apaga do índice os eventos de sessões de agente paradas há mais de DIAS (180); "
                             "resumo, arquivos e comandos ficam")
    parser.add_argument("--instalar-hook", action="store_true",
                        help="instala o hook SessionStart do Claude Code que pareia a aba com a sessão "
                             "(edita ~/.claude/settings.json com backup; ver docs/en/pairing-hook.md)")
    args = parser.parse_args(argv)

    if args.instalar_hook:
        return install_pairing_hook()
    if args.reindexar_agentes:
        return reindex_agents()
    if args.podar_agentes is not None:
        return prune_agents(args.podar_agentes)

    if args.serve:
        from vulcan_terminal.server.app import serve
        return serve(args.port)

    if args.doctor:
        try:
            from vulcan_terminal.core.doctor import render
            print(render())
        except Exception as exc:  # noqa: BLE001
            print(f"doctor falhou: {exc}", file=sys.stderr)
            return 1
        return 0

    try:
        from vulcan_terminal.ui.app import run
    except ImportError as exc:
        print(f"UI indisponível: {exc}", file=sys.stderr)
        return 1
    return run(selftest=args.selftest)


def reindex_agents() -> int:
    import json

    from vulcan_terminal.core import paths
    from vulcan_terminal.core.agents.index import AgentIndex, index_path
    from vulcan_terminal.core.agents.watcher import AgentWatcher

    index = AgentIndex(index_path(paths.data_dir()))
    index.rebuild()
    watcher = AgentWatcher(index)
    changed = watcher.run_once()
    print(json.dumps({"ok": True, "sessions": len(changed), "counts": index.counts(), "roots": watcher.roots(),
                      "zst_ignored": watcher.zst_ignored}, ensure_ascii=False))
    index.close()
    return 0


def install_pairing_hook() -> int:
    import json

    from vulcan_terminal.core import paths
    from vulcan_terminal.core.agents import discovery, pairing

    try:
        info = pairing.install_hook(discovery.claude_root(), paths.data_dir())
    except (OSError, ValueError) as exc:
        print(f"não deu para instalar o hook: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **info}, ensure_ascii=False))
    return 0


def prune_agents(days: int) -> int:
    import json

    from vulcan_terminal.core import paths
    from vulcan_terminal.core.agents.index import AgentIndex, index_path

    if days < 1:
        print("DIAS deve ser 1 ou mais", file=sys.stderr)
        return 2
    path = index_path(paths.data_dir())
    before = path.stat().st_size if path.is_file() else 0
    index = AgentIndex(path)
    removed = index.prune_events(days)
    index.close()
    print(json.dumps({"ok": True, "days": days, "events_removed": removed,
                      "bytes_before": before, "bytes_after": path.stat().st_size}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
