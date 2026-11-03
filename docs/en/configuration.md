# Configuration

## Command line

Run from source with `python3 -m vulcan_celox <flag>`.

| Flag | Does |
|------|------|
| (none) | Opens the old tkinter interface, a fallback. The main interface comes from the built app |
| `--serve [--port N]` | Local server only; prints `VULCAN_PORT` |
| `--doctor` | JSON with backend, environment, sites, agents, prices and 30-day usage |
| `--reindexar-agentes` | Rebuilds the agent session index |
| `--podar-agentes [DAYS]` | Deletes events of sessions idle for more than DAYS (default 180). Never automatic. Summaries stay |
| `--instalar-hook` | Adds the pairing hook to `~/.claude/settings.json`, with a backup |
| `--tk` | Old tkinter interface (fallback) |
| `--selftest` | Smoke test of the tkinter interface |
| `--version` | Version |

Native shell, as a sensor:

```bash
"dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot out.png --route "#/overview"
```

Linux launcher: `vulcan-celox --check`, `vulcan-celox --instalar-dependencias`.

## Files

| Path | Holds |
|------|-------|
| `~/Library/Application Support/VulcanCelox/` | macOS data folder (0700; files 0600) |
| `$XDG_DATA_HOME/vulcan-celox` | Linux data folder |
| `%APPDATA%\VulcanCelox` | Windows data folder |
| `<data>/agentes.db` | Disposable SQLite index of agent sessions |
| `<data>/precos.json` | Your price overrides; beats the built-in table |
| `<data>/prompts/` | Global prompts |
| `<data>/sessoes/` | Session memories in Markdown |
| `<data>/pairings/` | Written by the optional hook |
| `<data>/TAREFAS.md`, `INDICE.md` | Generated indexes |
| `<project>/.vulcan/prompts/` | Project prompts, created only with confirmation |
| `<project>/TAREFAS.md` | Opt-in, written only inside a marked block |

A corrupted JSON file or database is renamed to `*.corrupt-<timestamp>` and the app starts with defaults.

## Environment variables

| Variable | Effect |
|----------|--------|
| `VULCAN_CELOX_HOME` | Data folder (used in tests) |
| `CLAUDE_CONFIG_DIR` | Claude Code folder |
| `CODEX_HOME` | Codex folder or folders, comma separated |
| `VULCAN_AUTOSTART=0` | Do not start Lerd with the app |
| `VULCAN_AGENTS=0` | Do not start the agent index |
| `VULCAN_LERD_BIN`, `VULCAN_VALET_BIN`, `VULCAN_ZSTD_BIN` | Path of each tool |
| `VULCAN_LERD_API`, `VULCAN_LERD_DATA`, `VULCAN_VALET_HOME` | Lerd API address, Lerd data, Valet folder |
| `VULCAN_ANTHROPIC_BASE_URL` | Anthropic API base (proxy or test server) |
| `VULCAN_KEYSTORE=memory` | Keep the API key in memory (tests and captures) |
| `VULCAN_EDITOR` | Editor opened by the app |
| `VULCAN_PYTHON`, `VULCAN_PYTHON_ONLY=1` | Python used by the macOS shell; `ONLY` skips the other candidates |
| `VULCAN_INSPECT=1` | Enables the web inspector (development only) |
| `VULCAN_LINUX_MODE` | Forces the Linux window mode |
| `VULCAN_INSTALL_DEST`, `VULCAN_DESKTOP`, `VULCAN_UNIVERSAL=1` | Install destination, Desktop folder, universal build |
| `VULCAN_LINUX_IMAGE` | Container image of `test_linux.sh` |

`VULCAN_LEGACY_HOME` points to the data of the old prototype, for the migration. Set by the app itself, not meant for you to change: `VULCAN_TOKEN`, `VULCAN_PORT`, `VULCAN_WATCH_PARENT`, `VULCAN_PHP_INI_SET`. Inside each terminal tab the app sets `VULCAN_SESSION_ID` and `VULCAN_THEME`.
