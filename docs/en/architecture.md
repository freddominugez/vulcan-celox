# Architecture

Overview. The detailed reference, kept in sync by a test, is the [technical manual](technical-manual.md).

## The shape of it

```
Native shell (Swift + WKWebView)        Linux and Windows shell (GTK + WebKit, or Edge/Chromium --app)
        | starts, with a token                     |
        v                                          v
Python server on 127.0.0.1  <-- JSON + WebSocket --> Web interface (no build, xterm.js)
        |
        +-- core/            logic with no interface
        +-- core/agents/     read JSONL -> SQLite index
        +-- PTYs             real terminals
        |
        +-- reads ~/.claude, ~/.codex (line by line, read only)
        +-- calls lerd / valet CLI and the Lerd API
        +-- writes only to its own data folder
```

Startup: the Swift executable generates a random token, starts `python3 -m vulcan_celox --serve` from the bundle's resources with the token in the environment, reads `VULCAN_PORT=<n>` from stdout, and loads `http://127.0.0.1:<n>/` in a WKWebView, with the token available only for that origin. Closing the app ends the server and the PTYs. If the parent dies, the server writes memories within 3 seconds and exits.

## Stack and why

| Choice | Reason |
|--------|--------|
| Python 3.9 standard library, zero pip | Runs on the Python a Mac already has; nothing to install; easy to test |
| Web interface with no build | No toolchain to maintain; modules loaded directly |
| Thin Swift shell, not Electron | Native menus and windows at a few megabytes |
| xterm.js 6 (vendored, MIT) | Real terminal emulator |
| SQLite with FTS5 | Disposable index and accent-insensitive search |
| Lerd, then Valet, then local mode | Orchestrate MIT tools rather than rebuild PHP, nginx and DNS |

## Decisions that work as rules

| # | Rule |
|---|------|
| D1 | Python 3.9 stdlib core, Swift shell, web interface with no build |
| D2 | Orchestrate, do not reimplement: Lerd or Valet as backend. Herd is commercial and is never a backend |
| D3 | Do not alter system services or global files of those tools |
| D4 | `core/` has no interface code. A test enforces it |
| D5 | Subprocesses only through `core/runner.py`, as an argv list. `shell=True` is never used; `run_shell` calls the login shell with `-lc` |
| D6 | Atomic JSON persistence (`tempfile` + `os.replace`, `schema_version`). Corrupted files become `*.corrupt-<ts>` |
| D7 | Nothing is deleted for good. A test scans the source for `shutil.rmtree` and `rm -rf` |
| D8 | Sensors use only the standard library and system tools |
| D9 | Own implementation, no assets copied from Herd |

## Layout

| Path | What it is |
|------|------------|
| `packaging/macos/` | macOS shell: windows, menus, menu bar item, `--snapshot`, `--eval` |
| `vulcan_celox/core/` | Store, runner, PTY, backends, sites, notebook, memory, redaction, prompts, themes, harness, Node |
| `vulcan_celox/core/agents/` | Discovery, JSONL stream, Claude and Codex readers, builder, index, history, watcher, loops, repos, pairing, pricing, usage |
| `vulcan_celox/server/` | HTTP and WebSocket server and one `*_api.py` per area |
| `vulcan_celox/web/` | `index.html`, `styles/`, `js/`, `js/views/`, `help/`, `vendor/` |
| `vulcan_celox/desktop_linux.py`, `desktop_windows.py` | Linux and Windows shells |
| `vulcan_celox/ui/` | Old tkinter interface, fallback only |
| `scripts/` | `validate.sh`, `test_linux.sh`, `build_app.sh`, `install_app.sh`, `package.sh` |
| `packaging/linux/` | Launcher, menu entry, icons, `.deb` control |
| `tests/` | `unittest` suite, fixtures, fake Lerd |

## Agent panel

1. `discovery` finds session files. `jsonl_stream` reads by line and keeps an offset, tolerating a cut last line, invalid JSON, lines above 5 MB and files that shrink.
2. `claude_reader` and `codex_reader`, with the `rules` table, turn lines into events. `builder` assembles an `AgentSession`.
3. `index` stores summaries, events with FTS5, and usage per turn in `agentes.db`. The index is disposable; the JSONL is the source of truth.
4. `watcher` polls with `os.stat` every 2 seconds with a 300 ms debounce, outside the lock. The interface polls a revision number and reloads only when it changes.
5. `repos` reads git only with `-c core.fsmonitor=false --no-optional-locks`, so analyzing a repository never runs its hooks. `loops` flags the same test repeated without a commit. `pairing` links a tab and a session.

## Terminals

One real PTY per tab (`os.forkpty`, or ConPTY on Windows), with the user's shell in login mode. One reader thread per PTY keeps up to 256 KB of history. WebSocket `/ws/terminals/<id>` carries input and output as binary frames, and `resize`, `input` and `exit` as JSON. Each client has a bounded queue (4 MB) and its own sender thread; a client that falls behind is dropped without stopping the reader. The server token is removed from the tab's environment.

## Known debt

Six files above 400 lines are frozen by a test and cannot grow: `packaging/macos/main.swift`, `ui/app.py`, `web/js/views/tasks.mjs`, `core/notebook.py`, `core/harness.py`, `web/js/views/site.mjs`. Risks are listed in section 17 of the [technical manual](technical-manual.md).
