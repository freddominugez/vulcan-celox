# Vulcan Celox: technical manual

Reference for a developer who has never seen this project. It describes version 1.2.1. For a shorter tour, read [architecture.md](architecture.md). Many identifiers and source strings in the code are in Brazilian Portuguese; this manual keeps those names as they are so you can search for them.

Paths written as `core/...`, `server/...`, `web/...` and `ui/...` are relative to `vulcan_celox/`.

## 1. Overview and goals

Vulcan Celox is a desktop panel for a solo developer who works with coding agents and local PHP/Laravel and Node projects. It brings together:

1. **Environment management**: local `.test` sites, TLS, PHP and Node versions, services, sharing, logs and dumps, through Lerd or Laravel Valet.
2. **Terminals per project**: real PTYs with live output, history, quick commands and a Markdown memory of each session.
3. **Agent panel**: reads the session files of Claude Code and Codex, with no API key, and shows sessions, files, commands, publication state, tokens, estimated cost and history search.
4. **Project notebook**: notes, tags, tasks with progress and a generated Markdown index of tasks.
5. **Harness tab**: shows where the agents are in a project's contract, read from files in that project.
6. **Documentation with AI**: on click only, with the user's own Anthropic key.

Goals that shape the code:

- Nothing to install beyond Python 3.9. No pip, no npm, no build step for the interface.
- Add no new door to the machine: the server listens only on `127.0.0.1` and requires a token. See [security.md](security.md).
- Never write to the agents' folders, apart from one command run by the user.
- Never delete anything for good.
- Everything testable without a window, a real Lerd or real agents.

Release state: stable releases ship for macOS 13 or newer, Apple Silicon and Intel; the latest is 1.1.1. Since 1.2.0 there are test builds for Windows 10 (1809 or newer) and 11 and for Linux, published as pre-releases until they pass acceptance on real machines.

## 2. Design decisions

These decisions work as rules. Several are enforced by tests.

| # | Decision | Reason |
|---|----------|--------|
| D1 | **Python 3.9 standard library core, native Swift shell (WKWebView), web interface with no build.** No pip dependency. The tkinter interface stays as a fallback. | Runs on the Python a Mac already has, on both architectures, with nothing to install. Code must stay compatible with 3.9: no `match`, no `X \| Y` in runtime annotations. |
| D2 | **Orchestrate, do not reimplement.** Lerd (github.com/lerd-env/lerd) or Laravel Valet, both MIT, are the backends, in this priority. Without either, the app runs in local mode. | Building PHP, nginx and DNS is out of scope. Herd is a commercial product and is never a backend. In local mode, notes, tags, tasks and the index still work. |
| D3 | **Do not alter system services.** The app never edits global files of those tools. | It only calls their CLI or API, or writes in its own folders. Any write in a project folder is opt-in and reversible. |
| D4 | **Core without tkinter.** `core/` does not import tkinter. | All logic (parsers, store, runner, Markdown, progress) can be tested with `unittest` and no window. `tests/test_arquitetura.py` enforces it. |
| D5 | **Subprocesses only through `core/runner.py`.** Commands are argv lists. | Testable with `FakeRunner`, and no shell interpretation of values. The one exception is free text from the terminal, which runs explicitly as `<shell> -lc` through `run_shell`. A test rejects `subprocess` imports anywhere else. |
| D6 | **Atomic JSON persistence.** `tempfile` plus `os.replace`, a `schema_version` field, and a corrupted file becomes `*.corrupt-<timestamp>` while the app starts with defaults. | A crash or a full disk never leaves a half-written file, and a bad file never blocks startup. |
| D7 | **Nothing is deleted irreversibly.** Folders go to the Trash, with confirmation by typing the name. | `shutil.rmtree`, `rm -rf` and similar are forbidden, and a test scans the source and the scripts. |
| D8 | **Sensors use only the standard library and system tools.** `compileall`, `unittest`, `plutil`, `swiftc`, `--selftest` and `--snapshot`, orchestrated by `scripts/validate.sh`. | No test framework or external tool to install. |
| D9 | **Own implementation, no assets copied from Herd.** | Herd is proprietary: no binaries, `.so` extensions, icons or text from it in the repository. Valet is MIT and may be consulted. |

## 3. Repository layout

Verify at any time with `git ls-files`.

```
packaging/macos/main.swift   macOS shell: WKWebView, windows, menus, menu bar item, child server, --snapshot, --eval
packaging/macos/AppIcon.icns   app icon from the brand kit; the build copies it
packaging/linux/             launcher, dependency script, .desktop entry, icons, .deb control, install and uninstall
packaging/LEIA-ME.md         install notes shipped inside the packages
vulcan_celox/
  __main__.py                command line of the Python package
  desktop_linux.py           Linux shell: GTK 3 + WebKit2GTK, Chromium --app or browser
  desktop_windows.py         Windows shell: the same as Linux, in an Edge or Chrome app window
  core/                      logic with no interface
  core/agents/               agent sessions: discovery, readers, index, watcher, pairing, usage
  core/backends/             Lerd, Valet and local mode
  server/                    HTTP and WebSocket server, one module per API area
  web/                       interface with no build: index.html, styles/, js/, js/views/, help/, img/, vendor/
  ui/                        old tkinter interface, fallback only (--selftest and default of the Python entry point)
scripts/                     validate.sh, test_linux.sh, build_app.sh, install_app.sh, package.sh, package_linux.py,
                             make_deb.py, manual_md.py, manual_shots.sh, help_json.py
tests/                       unittest suite, fixtures/, golden/, tools/ (fake Lerd)
docs/en/, docs/pt-BR/        public documentation, same pages in both languages
.github/                     issue and pull request templates, workflows for Linux, Windows and macOS
```

`dist/`, `build/` and `executaveis/` are build output and are ignored by git.

## 4. Runtime and process model

The app is two processes on macOS: a Swift shell and a Python child server. On Linux the server runs inside the shell's own process.

```
Swift shell (AppKit + WKWebView)
   | starts with VULCAN_TOKEN in the environment, reads VULCAN_PORT=<n> from stdout
   v
python3 -m vulcan_celox --serve   <--- JSON + WebSocket --->   web interface inside WKWebView
   |
   +-- threads: HTTP per connection, one reader per PTY, one sender per WebSocket client,
   |            agent watcher, memory writer, environment autostart, AI jobs
   +-- children: shell in a PTY per tab, lerd, valet, git, zstd, security
```

### Startup on macOS

1. `applicationDidFinishLaunching` looks for a usable Python: `VULCAN_PYTHON` if set, then (unless `VULCAN_PYTHON_ONLY=1`) `/opt/homebrew/bin/python3`, `/usr/local/bin/python3` and `/usr/bin/python3`. A candidate must be 3.9 or newer. `/usr/bin/python3` is only tried if `xcode-select -p` succeeds, because without the Command Line Tools it is a stub that opens the Apple installer. With no Python, the app explains and offers to install it, then exits with 1.
2. `BackendServer.start` generates the token (32 random bytes from `SecRandomCopyBytes`, as 64 hex characters) and runs `python -m vulcan_celox --serve` with the working directory set to the bundle's `Resources`. With `-m`, the current folder goes first in `sys.path`, so this fixed folder stops a hostile folder from planting a module. The environment gets `PYTHONPATH=<Resources>`, `PYTHONDONTWRITEBYTECODE=1`, `VULCAN_TOKEN`, `VULCAN_WATCH_PARENT=1`, and `SHELL` and `LANG` when missing.
3. Python runs `serve()` in `server/app.py`:
   - `VulcanApp.__init__` applies `secure_data_dir`, opens the `Store`, migrates data from the old prototype once, loads the `Notebook`, detects the backend, picks the key store, creates `LocalServer` (port 0 means the OS picks one, and the token comes from `VULCAN_TOKEN`, which must have at least 32 characters), `TerminalManager`, `SessionHub`, and registers every API module.
   - `SIGTERM` is mapped to `KeyboardInterrupt`, so the normal shutdown path runs.
   - It prints `VULCAN_PORT=<n>` and flushes.
   - It starts `autostart.begin()` and `agents.start()`, plus the parent watcher if `VULCAN_WATCH_PARENT=1`, then enters `serve_forever`.
4. The shell waits up to 20 seconds for `VULCAN_PORT=`. If it does not arrive, it terminates the child and shows an error.
5. The shell builds menus and the menu bar item, then opens a window on `http://127.0.0.1:<n>/`. A user script at document start defines `window.VULCAN = {token, native: true, kind}` only if `location.origin` is the app's origin.
6. The interface reads the token from `window.VULCAN` and calls the API.

### Windows and the native bridge

Closing the last window does not quit: the app stays in the menu bar. `WebWindowController` keeps the window on the app's origin in `decidePolicyFor`. External `http` and `https` links open in the default browser, and everything else is cancelled. The bridge is the script handler `vulcan`, and it accepts messages only from the app's origin. Message types: `dragRegions`, `popout`, `focusPopout`, `setTitle`, `close`, `relaunch`, `pickFolder`, `copy`. Native menus call back into the page through `window.vulcanCommand(name)`. A detached terminal is another window on the route `#/popout/<id>`.

### Shutdown

| Trigger | What happens |
|---------|--------------|
| Quit the app | `applicationWillTerminate` calls `server.stop()`: `SIGTERM`, wait up to 6 seconds, then `SIGKILL`. The window never freezes for longer than that. |
| `SIGTERM` or Ctrl-C in Python | `VulcanApp.shutdown()` in this order: flush the task index, `hub.finalize_all()` (writes every open memory), `terminals.close_all()`, `hub.stop()`, `server.shutdown()`, `agents.stop()`. The HTTP server stops before the agent database closes. |
| Shell dies abnormally | `_watch_parent` checks `getppid()` every second. When it changes, it runs `shutdown` on a thread with a 3 second limit, then calls `os._exit(0)`. No server or PTY is left orphaned. |

### Linux

`desktop_linux.py` creates `VulcanApp` in its own process with a token from `secrets.token_urlsafe(32)`, then picks a window mode (`VULCAN_LINUX_MODE` or `--mode` can force it):

1. `gtk`: GTK 3 and WebKit2GTK with a `vulcan` bridge. The token goes in through a bootstrap script guarded by the origin, and `decide-policy` keeps the window on the origin.
2. `app`: Chromium, Chrome, Brave or Edge with `--app` and its own profile in `<data>/janela`.
3. `browser`: `xdg-open`. No window can be observed, so it exits when the interface stops polling (`IDLE_EXIT_SECONDS`, 150 seconds, doubled before the first request).

In the last two modes the token never goes on a command line. A 0600 page, `<data>/abrir-janela.html`, redirects to the app with the token in the URL fragment, and `web/js/api.mjs` moves it to `sessionStorage` and removes it from the address bar.

### Windows

`desktop_windows.py` reuses the Linux shell with `VulcanApp` in its own process, in the `app` mode with Edge or Chrome, and the `browser` mode as a fallback. The token follows the same 0600-page path as Linux. The packaged `.zip` carries an embedded Python and a `Vulcan Celox.cmd` launcher. Terminals use ConPTY through `ctypes` (`core/pty_windows.py`), with PowerShell by default. Process creation goes through `core/runner.py` with `CREATE_NO_WINDOW`, and URLs, folders and editors open without passing through `cmd.exe`, so a file name cannot become a command.

## 5. Core modules

### General

| Module | Does |
|--------|------|
| `core/paths.py` | Data folder and tool locations. Every path can be overridden by environment variable for tests. |
| `core/oscompat.py` | What differs between macOS and Linux: default shell (`$SHELL`, then zsh, bash, sh), data folder, `open_argv`. |
| `core/pty_windows.py` | Windows terminal: `WinPty` over ConPTY through `ctypes`, with no dependency. Open, read, write, resize and close, ending the whole process tree. |
| `core/win32.py` | Windows calls through `ctypes`: Recycle Bin, Credential Manager, process table. |
| `core/store.py` | Atomic JSON (`write_json_atomic`, `read_json`), `Store` with envelope `{schema_version, data}`, private permissions (`secure_data_dir`, `make_private`), one-time migration from the old prototype. |
| `core/runner.py` | The only module that uses `subprocess`: `Runner.run`, `run_shell`, `stream`, `open_pipe`, `spawn_pty`, `terminate_pty`, `terminate_many`, and the test double `FakeRunner`. Text for `input=` goes by stdin, never on the command line. |
| `core/trash.py` | `move_to_trash`: Finder on macOS, `gio trash` on Linux, and `<data>/lixeira/` with a date in the name if neither works. |
| `core/debounce.py` | `Debouncer` with an injectable clock. |
| `core/textutil.py` | Search normalization (no accents, no case) and `headline`, the short title of a pasted request. |
| `core/redact.py` | Masks secrets before text leaves the machine. Returns the text and the count. |
| `core/doctor.py` | Builds the `--doctor` JSON. |
| `core/miniyaml.py` | Minimal block YAML parser with no dependency, used for Lerd files and prompt headers. |
| `core/tables.py` | Parser of the ASCII tables printed by the Valet CLI. |

### Notebook

| Module | Does |
|--------|------|
| `core/models.py` | Dataclasses `Tag`, `Note`, `Task`, tolerant of unknown keys and old colors. |
| `core/notebook.py` | `Notebook`: CRUD, filters, ordering, undo of a task delete (5 seconds), export and import, change listeners. |
| `core/progress.py` | `done / total`, by site, by tag and overall. No tasks gives 0% and the label `sem tarefas`. |
| `core/markdown_index.py` | `TAREFAS.md`: global always, and per project by opt-in, writing only between `<!-- vulcan:tarefas:inicio -->` and `<!-- vulcan:tarefas:fim -->`. Deterministic output, and it writes only when the content changes. |
| `core/search.py` | Global search over sites, tasks, notes and tags. |

Data model. `site = null` means a global item, outside any project. `terminal` links an item to a terminal session, and an item created with `terminal` inherits that session's site.

```
Tag  {id, name, color}
Note {id, site|null, text, color, tags[], pinned, created_at, updated_at, order, terminal|null}
Task {id, site|null, title, status: todo|doing|done, priority: 1..3, tags[], due|null, order,
      created_at, done_at|null, terminal|null, assignee|null}
```

### Terminals and sessions

| Module | Does |
|--------|------|
| `core/pty_session.py` | `PtySession` and `TerminalManager`. See section 7. |
| `core/sessions.py` | `SessionRecord`, `SessionStore`, `InputTracker`. |
| `core/session_memory.py` | Renders the session memory and `INDICE.md`, and cleans terminal escapes. |
| `core/procinfo.py` | Processes in a terminal's foreground group: `/proc` on Linux, `ps` on macOS. |
| `core/quick_commands.py` | Commands for a project (composer, artisan, npm), recent commands, and `is_long_running`. |
| `core/themes.py` | The four session themes and their rotation. A theme is data: one item in `THEMES` and an id in `ROTATION`. |

### Environment and projects

| Module | Does |
|--------|------|
| `core/backends/base.py` | `Backend` interface, `EnvStatus`, validation of site actions. |
| `core/backends/lerd.py` | `LerdBackend`: CLI, panel API (`api_get`, `api_post`), site list. |
| `core/backends/valet.py` | `ValetBackend`: CLI. |
| `core/backends/null.py` | `NullBackend`: local mode with no environment. |
| `core/sites.py` | `Site` and `discover_sites` (parked, linked, manual). |
| `core/site_list.py` | Sidebar order: favorites first, then alphabetical, with a filter. |
| `core/site_runtime.py` | Parses `lerd which` and `php -v`, and checks whether the tab reaches the Lerd shims. |
| `core/environment.py` | Parses Lerd status, services, `php:list`, `php -m`, `php:ext list` and `xdebug status`. |
| `core/php_ini.py` | Six common `php.ini` settings. It also runs as the `EDITOR` helper of `lerd php:ini`. |
| `core/laravel_log.py` | `storage/logs/laravel.log` read by file position, entries with level. |
| `core/lerd_dumps.py` | Events of the Lerd dump bridge: filters, grouping by request, repeated queries, the window of an agent session, a redacted summary. |
| `core/lerd_quirks.py` | Workarounds for Lerd defects, for `--doctor`. |
| `core/node_project.py` | Read-only reader of a Node project. |
| `core/harness.py` | Reader of a project's harness and installer of the minimal format. |

### Prompts and AI

| Module | Does |
|--------|------|
| `core/prompts.py` | Prompts as Markdown files with a header, variables, `paste_bytes`, current session selection. |
| `core/ai.py` | Minimal Anthropic Messages API client with an injectable transport. |
| `core/keychain.py` | API key in Keychain or Secret Service, or in memory. |
| `core/doc_prompts.py` | Builds what is sent to the AI. |

### Agents

| Module | Does |
|--------|------|
| `core/agents/discovery.py` | Where the session files are. |
| `core/agents/jsonl_stream.py` | Incremental line reading, `LineStream` and `ZstdLineStream`. |
| `core/agents/claude_reader.py`, `core/agents/codex_reader.py` | Turn lines into facts about a session. |
| `core/agents/rules.py` | Heuristics as data: tool to effect, what is a test, what is a publication, where a worktree is. |
| `core/agents/builder.py` | `SessionBuilder`: assembles `AgentSession`, with state that survives between reads. |
| `core/agents/model.py` | Normalized model: `AgentSession`, `FileTouch`, `CommandRun`, `SessionEvent`, and safe conversions. |
| `core/agents/reading.py` | `read_session`: continues from the saved offset with the saved reader state. |
| `core/agents/index.py` | `AgentIndex`, SQLite in `agentes.db`. |
| `core/agents/history.py` | FTS5 table and search, with a fallback to `LIKE`. |
| `core/agents/watcher.py` | `AgentWatcher`: polling with `os.stat`. |
| `core/agents/loops.py` | `LoopTracker`: the same test run 3 times or more with no commit between. |
| `core/agents/repos.py` | Branches and worktrees, crossing sessions with real git. |
| `core/agents/pairing.py` | Links tab and session, and installs the hook. |
| `core/agents/pricing.py` | Price per model and the cost of a turn. |
| `core/agents/usage.py` | Aggregation of usage, CSV, summary for `--doctor`. |
| `core/agents/status.py` | Read-only diagnostics of agent sources for `--doctor` and the history screen. |

### Server

| Module | Does |
|--------|------|
| `server/app.py` | `VulcanApp`: state, services, `spawn_terminal`, core routes (`/api/state`, `/api/services/<action>`, `/api/app/build`, `/api/preferences`, `/api/open`), `serve`. |
| `server/local_http.py` | HTTP on loopback, security checks, router, static files. |
| `server/websocket.py` | Minimal RFC 6455. |
| `server/terminals_api.py` | Terminals over REST and WebSocket, `ClientSender`, `/api/themes`. |
| `server/session_hub.py` | Connects PTYs, session records, commands, memory and `INDICE.md`. |
| `server/sessions_api.py` | `/api/sessions`, `/api/sessions/tree`, `/api/index/general`. |
| `server/notebook_api.py` | Tags, notes, tasks, progress, search, `TAREFAS.md`. |
| `server/agents_api.py` | `/api/agents/*`: sessions, revision, history, usage, repos, resume, pairing, current session. |
| `server/prompts_api.py` | `/api/prompts`, including send. |
| `server/sites_api.py` | `/api/sites/*`: add, versions, actions, favorites, share, remove, Trash, runtime, commands, log. |
| `server/sites_harness_api.py` | `/api/sites/<name>/harness`: read, install, new tasks. |
| `server/env_api.py` | `/api/environment/*`: services, PHP, `php.ini`, extensions, Xdebug, Node. |
| `server/debug_api.py` | `/api/debug/*`: bridge events, switch, clear, errors for an agent session. |
| `server/node_api.py` | `/api/node-projects/*`. |
| `server/guide_api.py` | `/api/guide`: the four steps of the Home screen and the choice to skip them. |
| `server/fs_api.py` | Folder check and recent folders for the "open terminal in" dialog. |
| `server/autostart.py` | `EnvAutostart`: starts Lerd or Valet with the app, in the background, if it is stopped. |
| `server/ai_api.py` | Key, validation against Anthropic, choice of model. |
| `server/ai_docs.py` | Preview of what will be sent, generation and reading of generated files. |
| `server/ai_jobs.py` | Background AI jobs: one per target, with state the interface can poll. |

### Code tab, attention, ports and PR state (1.1)

- `core/agents/edits.py`: table `session_edits` with path, time, tool, turn and offset. Content is read on demand from the session file by `edit_detail()`, so a session deleted by the agent has no diff. On Claude Code the sources are `Edit`, `MultiEdit` and `Write`; `originalFile` is only read, never stored. On Codex the `FileChange` item carries the diff, and a readable patch covers the older format.
- `core/code_files.py`, `core/code_diff.py`, `server/code_api.py`, `server/known_roots.py`: read-only viewer. The HEAD side comes from `git cat-file blob`, and the current side is read directly, so `diff.external`, `textconv` and clean filters from the analyzed repository never run.
- `core/agents/attention.py`, `core/agents/attention_hook.py`: turn state per session and the optional hook for permission requests.
- `core/agents/turns.py`: events and edits grouped by request, with the same count as the reader.
- `core/listening_ports.py`: ports of each PTY and its descendants, with `lsof` on macOS and `/proc/net` on Linux, cached for 10 s.
- `core/pr_status.py`, `server/pr_api.py`: PR state through the user's `gh`, only with the `pr_status` preference on, cached for 60 s.
- Interface: `web/js/views/code/`, `web/js/terminal-watch.mjs` (attention, path links and request marks for each terminal), `web/js/terminal-ports.mjs`, `web/js/pr-status.mjs`, `web/js/theme.mjs`, `web/styles/tokens.css` (the only file with loose colors), and `web/vendor/codemirror.js`, loaded the first time the Code tab opens.

- `core/i18n.py`, `web/js/i18n.mjs`: interface language. `web/i18n/en.json` is the dictionary, and `HttpError` passes through `tr()` when answering.

### Windows

`core/pty_windows.py` is the terminal on Windows, using ConPTY through `ctypes`, and `core/win32.py` holds the Recycle Bin, Credential Manager and process list. `core/runner.py` picks the path by system. Opening a file on Windows never goes through `cmd.exe`, because an `&` in a name would become another command. The window is the same as `desktop_linux.py`, in Edge or Chrome app mode, started by `desktop_windows.py`. `scripts/package_windows.py` builds the portable zip with embedded Python, and `scripts/smoke_windows.py` checks it in CI.

## 6. HTTP server and WebSocket

`server/local_http.py` wraps `ThreadingHTTPServer` with one handler thread per connection. Routes, by group, are in [http-api.md](http-api.md). The threat model is in [security.md](security.md). The rules of the server itself:

| Rule | Code behavior |
|------|---------------|
| Interface | Binds `127.0.0.1` by default, on a port chosen by the OS. |
| `Host` | Must be `127.0.0.1:<port>` or `localhost:<port>`, otherwise 421. This applies to every request, static files included. |
| Token | On `/api/`, only in the `X-Vulcan-Token` header, compared with `hmac.compare_digest`, otherwise 401. On `/ws/` the query `token=` is also accepted, because a browser cannot set a header on a WebSocket. A custom header also forces a preflight between origins, and that preflight fails here. |
| `Origin` | If present, it must be the app's origin, otherwise 403. |
| Writes | `POST`, `PUT` and `PATCH` on `/api/` need `Content-Type: application/json`, otherwise 415. |
| Body | `Content-Length` is validated (400 if invalid), 1 MB limit (413), and it must be a JSON object. A body that a route did not read is discarded before answering, so it cannot corrupt the next request on the same connection. |
| Static files | Served from a copy of `web/` made when the server starts, looked up by key, so path traversal has nothing to reach. Files and folders starting with `.` are left out. Only `GET`, otherwise 405. Static files need no token, because the page has no secret: the token reaches it from the shell. |
| Headers | `X-Content-Type-Options: nosniff` everywhere, and `Cache-Control: no-store` on the API. HTML gets this CSP: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws://127.0.0.1:* ws://localhost:*; frame-ancestors 'none'`. |
| Errors | JSON `{"error": "..."}` with messages in the interface language. `HttpError` can carry extra fields, such as `needs_terminal` or `needs_confirmation`. |

Reading the interface once also means reinstalling the app while it is open does not mix a new interface with an old server. `GET /api/app/build` compares the SHA-256 of the loaded copy with the files on disk, and the interface offers to reopen when they differ.

Dispatch: `LocalServer.route(method, pattern)` compiles an anchored regular expression, and named groups become `req.params`. A handler returns data for JSON, a `(status, data)` tuple or a `RawResponse` (used by the usage CSV), or raises `HttpError`. A path that matches with the wrong method gets 405, and an unknown path gets 404.

`server/websocket.py` implements the handshake, frames and fragmentation with a 16 MB limit per message, and it answers ping. The only WebSocket route is `/ws/terminals/<id>`, described in the next section.

## 7. Terminals and PTY sessions, session memory

### PTY

Each tab is a real PTY created by `os.forkpty` in `runner.spawn_pty`. `TerminalManager.argv_for` runs the user's shell in login mode (`<shell> -l`). With an initial command it runs `<shell> -l -i -c "<command>; exec <shell> -l"`, so the tab continues as an interactive shell afterwards.

`terminal_env` prepends the Lerd shims, `~/.local/bin`, `/opt/homebrew/bin` and `/usr/local/bin` to `PATH`. It sets `TERM=xterm-256color`, `COLORTERM=truecolor` and `TERM_PROGRAM=VulcanCelox`, and removes `VULCAN_TOKEN` and `VULCAN_WATCH_PARENT`, so the server's token never reaches the user's shell. Each tab receives `VULCAN_SESSION_ID`, and `VULCAN_THEME` when it has a theme.

`PtySession`:

- One reader thread per PTY keeps up to 256 KB of history and delivers output to listeners.
- Only that thread closes the file descriptor. `close()` wakes it through a self-pipe and waits. Closing from another thread would free the number for another tab while the reader could still read from it.
- `write` takes one lock per write on a non-blocking master, with a 5 second limit without progress, and returns `True` only if everything was written. A large paste does not mix with keystrokes, and a tab that is not reading does not hold the writing thread.
- `subscribe(listener, prime)` returns the history and calls `prime` inside the lock, so whatever `prime` queues comes before any new output.

Ending: `terminate_pty` sends `SIGHUP` and `SIGTERM` to the group and `SIGKILL` after 2 seconds. `close_all` uses `terminate_many`, with a signal to all and a single wait, so ten tabs that ignore `SIGHUP` take 2 seconds in total.

### WebSocket and clients

`/ws/terminals/<id>` carries input and output as binary frames. Text frames carry JSON: `resize` (1 to 1000 rows and columns), `input` and `exit`. `ClientSender` gives each client a queue limited to 4 MB and its own sending thread. The PTY reader only queues, so a slow client never stops the reader, the other clients or the process. A client over the limit is dropped.

On the interface side, `web/js/terminals.mjs` uses xterm.js 6 with the addons fit, web-links, search, WebGL, unicode 11 and serialize. It reconnects automatically up to 5 times, with a growing delay. After that the tab warns, and Enter tries again.

### Creating a tab

`POST /api/terminals` accepts a site or folder, title, theme (`auto` takes the next in the rotation), size, `command` and `agent` (`shell`, `claude` or `codex`). The agent command comes from a fixed table, so nothing from the client becomes a command there. `VulcanApp.spawn_terminal` creates the PTY, registers the session and, if `typed` is given, writes that line to the shell at once and records it as a command, which the pairing uses. `GET /api/terminals/<id>/busy` uses `pgrep` to warn before closing a tab with a running child.

### Session record and memory

`SessionRecord {id, title, site, cwd, tags[], commands[{ts, cmd}], created_at, closed_at, exit_code, memory_file, theme}` lives in `terminal_sessions.json`, with up to 2000 commands per session.

`InputTracker` rebuilds typed lines from the bytes the WebSocket receives: editing keys, escape sequences, bracketed paste, and UTF-8 split between chunks. It is a conscious approximation: a command recalled from shell history with the arrow keys is not visible in the input, and stays only in the output record.

`server/session_hub.py` writes the memory:

- when a session is created, when its process exits, when the tab closes, and when the app exits;
- every 15 seconds if the session had input or output;
- when tasks, notes or tags change, with a 1 second debounce.

A session still marked as open at startup is closed, because no PTY survives a server restart. The writer thread does not die on an exception: the last error goes to the `memoria_status` file, and `--doctor` shows it.

The memory file is `<data>/sessoes/<site or global>/<YYYY-MM-DD-HHMM>-<title>-<id>.md`. It holds metadata, tags, tasks, notes, paired agent sessions, commands, and the transcript cleaned of escapes (`strip_terminal`), up to the last 2000 lines, between `<!-- vulcan:registro:inicio -->` and `<!-- vulcan:registro:fim -->`. For a closed session the transcript is read back from the file, so regenerating after a task changes does not lose it. `<data>/INDICE.md` is the general index. Deleting a closed session sends its memory and documentation to the Trash, and `items=keep` or `items=delete` decides what happens to its tasks and notes.

## 8. Agent sessions

Formats are in [agent-file-formats.md](agent-file-formats.md). The optional hook is in [pairing-hook.md](pairing-hook.md).

The app reads the files of Claude Code (`CLAUDE_CONFIG_DIR` or `~/.claude`) and Codex (`CODEX_HOME`, a comma separated list, or `~/.codex`) as streams, by line. It never writes to those folders, with one exception: `--instalar-hook`, run by the user.

### Reading

1. `discovery` lists `projects/*/*.jsonl` for Claude, leaving `agent-*.jsonl` out and only counting subagents. For Codex it lists `.jsonl` and `.jsonl.zst` under `sessions/` and `archived_sessions/`. If a rollout exists in both forms, the `.jsonl` wins. Without the `zstd` command, compressed files are ignored and counted.
2. `jsonl_stream.LineStream` starts at a byte offset and consumes only complete lines. A cut last line waits for the next pass. Invalid JSON, a value that is not an object, and a line above 5 MB are recorded as errors and skipped. A file smaller than the offset restarts from zero. `ZstdLineStream` reads through `zstd -dcq`, always from the start.
3. `reading.read_session` chooses the reader and feeds it line by line. An exception on one line is recorded and reading continues.
4. `claude_reader` and `codex_reader` call `SessionBuilder`, using the tables in `rules`. `builder` applies the publication state (`none`, `committed`, `pushed`, `pr_open`, where each step needs the previous one since the last edit), clips event text to 2000 characters, and keeps the last 200 commands.

Specifics that matter when changing them:

- Claude: one turn becomes several lines with the same `message.id` and `usage`, so tokens count once per id. Publication waits for the `tool_result` and counts only if it was not an error. `isSidechain` lines update the time but not the content.
- Codex: the file holds accumulated totals, so a turn's usage is the difference from the previous total, and a smaller total restarts the count. `session_origin` marks subagents and the desktop app, which are not born from a tab.

### Index

`index.AgentIndex` is SQLite in `<data>/agentes.db`, in WAL mode so that `--doctor`, `--reindexar-agentes` and `--podar-agentes` work while the app is open. It is disposable: the JSONL is the source of truth, but a session whose file was removed stays in the index.

| Table | Holds |
|-------|-------|
| `meta` | `schema_version`, `revision`, `last_error` |
| `sessions` | Light summary, offset, reader state, file identity |
| `session_files`, `session_commands` | Lists that only the detail view needs |
| `events`, plus FTS5 `history` | Requests, answers, commands and files for search |
| `agent_usage` | Tokens per turn |
| `parse_errors` | File, offset and reason |

A file's identity is its inode plus a hash of its start, which detects a file replaced by another with the same name and a larger size. The JSONL is read outside the lock, so the API does not wait for a big file. The write happens only if no one else wrote that file meanwhile. A schema below version 5 triggers a rebuild, and a database that fails `quick_check` is renamed to `agentes.db.corrupt-<ts>` and recreated. Every change increments `revision`.

A session is **active** when its file changed less than 90 seconds ago and its last event is less than 10 minutes old. The second condition exists because copying a folder changes file dates but not event dates.

`history` uses `unicode61 remove_diacritics 2`, so search ignores accents. Without FTS5 in SQLite it falls back to `LIKE`, which does not ignore accents, and `--doctor` warns. `status` also reads `cleanupPeriodDays` from Claude's settings (default 30), because Claude deletes old sessions.

### Watcher

`watcher.AgentWatcher` scans with `os.stat` every 2 seconds, and each changed file waits 300 ms with no new change. `VULCAN_AGENTS=0` turns it off. The interface polls `GET /api/agents/revision` and reloads only when it changes. `settled()` tells the screens whether the first scan has finished.

### Git state

`repos` crosses sessions with real git to show branches and worktrees with unreconciled work. Every git call uses `git -c core.fsmonitor=false -c core.untrackedCache=false --no-optional-locks`, because the analyzed repository belongs to someone else: `core.fsmonitor` would make `git status` run a program named in that repository's `.git/config`. Calls have a 5 second timeout and a 30 second cache per folder. The app never commits, pushes or removes a worktree.

`loops` flags the same test run 3 times or more with no commit between, using the test patterns in `rules`.

### Pairing

`pairing.resolve` links an agent session to a terminal tab, and both then share a theme:

1. **Hook file** (exact). The `SessionStart` hook reads `VULCAN_SESSION_ID` from the environment and writes `<data>/pairings/<session>.json`. Installed only by `--instalar-hook`, with a backup of `settings.json`.
2. **Folder and time** (fallback, and the only way for Codex). Same folder, and the session started up to 60 seconds after the tab opened or after `claude` or `codex` was typed in it. Sessions with an `origin` stay out. When sessions compete, pairs follow time order, with the largest number of pairs and, on a tie, the smallest gaps (`_match`).

The result is cached and rebuilt only when the index revision, the tabs or the hook folder change.

`POST /api/prompts/send` depends on pairing. It writes only to the paired tab, as bracketed paste with control characters removed, and **never with Enter**. Before writing it checks that the tab is alive, that this is the newest session paired to it, and that the agent is in the foreground group (`procinfo`; when that cannot be known, a live tab is enough). Otherwise it answers 409 with `needs_terminal`, and the interface offers to resume the session. If the tab does not read the paste in time, it answers 503.

`POST /api/agents/sessions/<id>/resume` opens a new tab in the session's folder and types `claude --resume <id>` or `codex resume <id>`. The id comes from the index and passes a pattern that must start with a letter or digit, so it cannot become an option.

### Usage and cost

Each turn becomes a row in `agent_usage` with `input`, `output`, `cache_read`, `cache_write_5m`, `cache_write_1h` and `reasoning`.

`pricing` holds a default table in USD per million tokens, with the date it was checked (`CONFERIDO_EM`) and its sources. There are no network requests. `<data>/precos.json`, with a `modelos` object, overrides it model by model. Names are normalized (date suffix and variant removed). An entry may carry `acima`, the long context price above a given prompt size. A model or token type with no price gives `None`, never 0.

`usage.aggregate` groups by `day`, `project`, `model`, `agent` or `session`, in local days, defaulting to the last 30 and limited to 400. `reasoning` is not billed separately, since it is already in `output`. A group where only part of the usage has a price is marked `cost_partial`. The result is an **estimate at API prices**, and subscriptions charge differently, as the screen states. `GET /api/agents/usage.csv` holds only ids, projects, models and numbers, with no session text.

## 9. Environment backends and Node projects

### Backend interface

`core/backends/base.py`. Detection (`detect_backend`): Lerd, then Valet, then `NullBackend`. Each location list can be replaced by an environment variable, and if the variable is set, only that path counts.

| Backend | Looked up in | Override |
|---------|--------------|----------|
| Lerd | `~/.local/bin/lerd`, `/opt/homebrew/bin/lerd`, `/usr/local/bin/lerd` | `VULCAN_LERD_BIN` |
| Valet | `/opt/homebrew/bin/valet`, `/usr/local/bin/valet`, `~/.composer/vendor/bin/valet`, `~/.config/composer/vendor/bin/valet` | `VULCAN_VALET_BIN` |

| Member | Purpose |
|--------|---------|
| `name`, `label`, `available`, `bin_path`, `runner` | Identity and how to run things |
| `start()`, `stop()`, `restart()` | Services, returning `Result` |
| `status()` | `EnvStatus(running, summary, details)` |
| `list_sites(manual)` | `Site` list |
| `site_command(action, *args)` | Returns the argv and working directory of an action. Each backend implements this one method |
| `link`, `unlink`, `park`, `unpark`, `secure`, `unsecure`, `isolate`, `isolate_node` | Built on `site_command`, with validation |
| `site_argv(action, *args)` | Validated argv, to run in a terminal tab instead of waiting |
| `share_argv(name, tool)`, `php_versions()` | Sharing and the PHP selector |
| `project_writes` | What the backend writes in the project for each action, so the interface can warn first |

A value starting with `-` is refused in `_check`, because it would become a CLI option.

### Lerd

The boundary with Lerd (dump format checked on 1.37.1, MIT) has two channels:

- **Panel API** on `http://127.0.0.1:7073` (`VULCAN_LERD_API`). Reads have a short limit (`api_get`, 1.5 seconds, returning `None` if the panel is down), and every POST carries `X-Lerd-CSRF: 1`, which Lerd requires (`api_post`). Proxies in the environment are ignored, because this is loopback. Routes used: `/api/status`, `/api/sites`, `/api/services`, `/api/dumps`, `/api/dumps/status`, `/api/dumps/toggle`, `/api/dumps/clear`, `/api/node-versions`. With the panel down, the site list falls back to `sites.yaml` in `~/.local/share/lerd/` (`VULCAN_LERD_DATA`).
- **CLI** through `core/runner.py`. A quick command runs and returns its output. A command that builds an image or keeps running (`fetch`, `php:update`, `xdebug on|off`, `node:install`, `logs -f`, `share`, `db:shell`, `site:doctor`) opens in a terminal tab through `spawn_terminal`, with its output in view. Repeated reads on the Environment screen (`php:list`, `xdebug status`) are cached for 60 seconds, and any action clears the cache.

`php.ini` changes go through `lerd php:ini` itself, with `EDITOR` pointing to `<data>/hooks/php-ini-editor.sh`. That script runs `core/php_ini.py` with `python -I`, so the current folder is not in `sys.path`. The helper keeps a `.bak-<date>` copy and changes only the requested lines, and Lerd then reapplies PHP-FPM as it does after a normal edit.

There is no dump server or PHP helper of the app's own. The bridge is Lerd's (`127.0.0.1:9913`). `core/lerd_quirks.py` lists the workarounds and the version that fixes each one, and the behavior does not change with the version. `--doctor` reports which are still needed. A fix was sent upstream as lerd-env/lerd#2404.

`POST /api/services/<action>` and autostart share a lock, so two service operations never overlap. `lerd start` can take minutes, because it may download images and start the Podman VM, so its limit is 300 seconds.

### Valet

CLI only. Sites come from `~/.config/valet/config.json` (`paths` are parked folders, plus `tld`), symlinks in `~/.config/valet/Sites/` (linked), and the app's `sites.json` (manual). `VULCAN_VALET_HOME` changes the folder. On a duplicate domain the priority is linked, then parked, then manual. `unpark` maps to `valet forget`, and `isolate_node` is not available. The Environment and Debug screens exist only for Lerd, and their routes answer 409 for other backends.

### Removing a site

Two steps. `POST /api/sites/<name>/remove` takes `level=list` for a manual site or `level=backend` for a registered one. For a parked Valet site it demands `parent`, because forgetting the parent folder affects every site in it. Only then can `POST /api/sites/trash` move the folder to the Trash, with the name typed in `confirm`. It refuses the home folder, very short paths, and a folder the backend still lists.

### Node projects

`core/node_project.py` reads, read-only and with a 1 MB limit per file:

- root `package.json`, and invalid JSON becomes `estado: ilegivel` with the error, never an empty project;
- lockfile, to choose the package manager (pnpm, bun, yarn, npm);
- framework from dependencies, and the probable port (a port flag in the `dev` or `start` script, otherwise the framework default);
- requested Node version (`.nvmrc`, `.node-version`, `engines.node`);
- local Supabase (`supabase/config.toml`, only `project_id` and ports);
- Vercel link (`.vercel/project.json`, only `projectId` and `orgId`).

It never opens `.env`. `server/node_api.py` keeps the list in `node_projects` in the Store, so removing a project from the list does not touch its folder. Suggestions come from folders where agents worked. A script runs in a visible terminal tab, with the line `<manager> run <script>` built by the server from validated values, and stopping sends Ctrl-C only to a tab that this project opened. Supabase actions are `start`, `stop` and `status`, also in a tab. The app does not talk to Vercel or to remote Supabase. The first local URL seen in a tab's output is shown on the project screen.

## 10. Harness tab

The tab shows where agents are in a contract of the **user's project**. `core/harness.py` reads two formats. It is read-only with a 1 MB limit per file. An unreadable file becomes `estado: ilegivel` with the error, never an empty state. The app does not change item status and does not run sensors: the project's own sensor validates.

| | Full format (`tipo: repo`) | Minimal format (`tipo: minimo`) |
|---|---|---|
| Detected by | `.harness/` | `.vulcan/` |
| State | `.harness/state.json` | `.vulcan/state/execution.json` |
| Contract | Path in the `contract` field, such as `specs/<feature>/contract.md`, kept inside the project | `.vulcan/tasks/<task_id>.md` |
| Handoff | `.harness/handoff.md` | `.vulcan/handoff.md` |

`detect` tries the full format first. `read` returns the contract, items (each in the state `feito`, `andamento`, `bloqueado` or `pendente`), next item, last green commit, up to 60 handoff lines, queue and, for the minimal format, status and blocking reason. Status values of the minimal format: `RUNNING`, `VERIFIED`, `INCOMPLETE`, `BLOCKED`, `CANCELLED`, `REVOKED`. An item line in a minimal contract looks like `C1 [verde] objective sensor: build`, with the bands `verde`, `amarela` and `vermelha`. An item in the contract that the state does not mention yet counts as pending.

`signature` (modification time and size of the files read) tells the screen when to redraw, and `web/js/views/harness.mjs` polls every 5 seconds. `summary` gives one line for the agent session screen, and `find_project` picks the most specific site containing a session's folder.

Writing happens only on request, in `server/sites_harness_api.py`:

- `GET .../harness/install` lists the exact files and content, and writes nothing.
- `POST .../harness/install` needs `confirm: true` and installs the minimal format. New files use `O_EXCL`, so an existing file is never overwritten. `AGENTS.md` and `CLAUDE.md` of the project are created if neither exists. If one exists, it only gains a block between `<!-- vulcan:harness:inicio -->` and `<!-- vulcan:harness:fim -->`. A symlink is refused, and so is a target outside the project.
- `POST .../harness/tasks` writes a new `.vulcan/tasks/<task_id>.md` from a form, with approval pending, and never overwrites.

Both are refused with 409 if the project has `.harness/`.

## 11. Web interface

`web/` has no build. `index.html` loads xterm.js and its addons as plain scripts, and `js/app.mjs` as a module. Everything is local: `vendor/` holds xterm.js 6 with licenses in `LICENSES.md`, and icons are inline SVG symbols. There is no framework.

### Shell of the interface

| File | Role |
|------|------|
| `js/app.mjs` | `parseRoute`, `navigate`, `route`, state refresh, toolbar, commands, boot |
| `js/app-state.mjs` | `app` state, `NAV`, `AGENT_NAV`, `HELP_NAV`, `NAV_GROUPS` |
| `js/view-mount.mjs` | `mountView`: a new root element per screen, then the view class of the route |
| `js/remount.mjs` | Which screens remount when the site list changes. The others keep typed text |
| `js/sidebar.mjs`, `js/session-tree.mjs` | Sidebar groups, site lists and the Sessions section |
| `js/palette.mjs` | Command palette (⌘K) |
| `js/global-events.mjs` | Global listeners and shortcuts |
| `js/terminals.mjs`, `js/terminal-panel.mjs` | Terminal workspace and the bottom panel on screens with no terminal |
| `js/api.mjs` | API client, `every`, `wsUrl`, `native`, `isNative`, `hasBridge`, `isMac` |
| `js/dom.mjs`, `js/markdown.mjs`, `js/themes.mjs`, `js/ai.mjs`, `js/agents-ui.mjs`, `js/current-session.mjs`, `js/prompt-bar.mjs`, `js/folder-dialog.mjs`, `js/site-add.mjs`, `js/help-content.mjs` | Shared pieces |

`every(ms, fn)` repeats after the previous call finished, and it does not poll while the window is hidden. The state refreshes every 5 seconds. `api()` has a 20 second default limit. `isNative` means the Swift shell with menus, `hasBridge` means a bridge exists (Swift or GTK), and `isMac` chooses ⌘ or Ctrl+Shift.

### Routes

Routes are hash based.

| Route | View (`js/views/`) |
|-------|--------------------|
| `#/inicio` | `home.mjs` |
| `#/overview` (also `#/sites` and unknown routes) | `overview.mjs` |
| `#/sites/<site>/<tab>/<session>/<item>` | `site.mjs`, tabs `terminal`, `tasks`, `notes`, `tags`, `harness`, `logs`, and `debug` on Lerd |
| `#/terminals/<tab>/<session>/<item>` | `site.mjs` (`TerminalsView`) |
| `#/popout/<id>` | Detached terminal, no sidebar |
| `#/node`, `#/node/<name>` | `node.mjs` |
| `#/lerd`, `#/ambiente` | `environment.mjs` |
| `#/depuracao` | `debug.mjs` |
| `#/agentes`, `#/agentes/<id>` | `agents.mjs`, `agent-session.mjs` |
| `#/agentes/historico` | `agents-history.mjs` |
| `#/agentes/branches` | `agents-branches.mjs` |
| `#/agentes/uso`, `#/agentes/uso/<YYYY-MM-DD>` | `agents-usage.mjs`; the date fixes the end of the period |
| `#/prompts` | `prompts.mjs` |
| `#/tasks`, `#/notes`, `#/tags`, `#/index` | `tasks.mjs`, `notes.mjs`, `tags.mjs`, `index.mjs` |
| `#/ajuda`, `#/ajuda/<section>` | `help.mjs` |

Supporting views: `logs.mjs` and `harness.mjs` are site tabs, and `session-tags.mjs` belongs to a session.

When only the session, tab or item changes on the same screen, the router calls `reveal` and does not remount, so terminals survive. A view is a class with `constructor(root, options)` and optional `update(state)`, `reveal(route)`, `command(name)` and `destroy()`. The first screen is `#/inicio` until the guide's four steps are done or skipped (`GET /api/guide`), then the last site or the overview.

### Help content

`web/help/conteudo.json` is the only source of the Help screen and of `docs/pt-BR/user-guide.md`, generated by `scripts/manual_md.py`. `validate.sh` compares the two, so edit the JSON and regenerate. It holds `secoes` (blocks `p`, `ul`, `passos`, `img`, `atalhos`) and `faq`. `ROUTE_SECTION` in `js/help-content.mjs` maps each route to a section, for ⌘?. Screenshots in `web/img/manual/` come from `scripts/manual_shots.sh`, using fixtures and a fake Lerd, never real data. `scripts/help_json.py` rewrites the JSON in the repository's layout.

### Themes

`core/themes.py` supplies the xterm palette and the tokens `--t`, `--t-bg` and `--t-ink` through `GET /api/themes`, and the page injects the CSS, which is why the CSP allows inline style. Homebrew, Clássico, Oceano and Ardósia rotate, with the position kept in the Store. A tab and its paired agent session use the same theme.

### Prompts

Markdown files with a header (`id`, `title`, `category`, `pin`, `descricao`, `icone`), global in `<data>/prompts/` and per project in `<project>/.vulcan/prompts/`. That folder is created only after confirmation. A project prompt overrides a global one with the same `id`. The variables `{{projectName}}`, `{{branch}}`, `{{base}}`, `{{sessionId}}`, `{{agent}}` and `{{cwd}}` have no logic. A missing one stays as it is and is listed in `missing`. The composer gives one field per variable, with a preview. The current session is the one chosen, otherwise the most recent active one, otherwise the most recent.

## 12. AI documentation

It runs **only on click**, and the flow always shows a dialog first. The app holds no key of its own: the user provides one.

| Step | Code |
|------|------|
| Key | `PUT /api/ai/key` checks the format (`sk-ant-...`), validates by listing models on the API, then stores it. The API returns only a masked form |
| Storage | `core/keychain.py`: macOS Keychain, service `com.byvulcan.celox.anthropic`, written with `security -i` and the command on stdin, never in argv. On Linux, Secret Service through `secret-tool`, value on stdin. `VULCAN_KEYSTORE=memory` keeps it in memory for tests and captures |
| Preview | `GET /api/ai/preview/session/<id>` or `/general` returns size, masked secrets, whether it was cut, and the model. Nothing leaves the machine yet |
| Build | `core/doc_prompts.py`. Session: the last 60 thousand characters of the transcript and the last 300 commands. General: a budget of 120 thousand characters, using each session's documentation when it exists, from the newest back; the rest gets one line each. The text instructs the model to rely only on the material given |
| Masking | `core/redact.py` runs **before** the cut, because a secret cut in half would lose the prefix the mask recognizes, and again on the final text. It covers API key formats, JWT, `Bearer`, passwords in URLs, sensitive `KEY=value` pairs, `--password` and `mysql -p` |
| Call | `POST /api/ai/docs/...` returns 202 and runs in `server/ai_jobs.py`, one job per target, with 409 for a duplicate. `core/ai.py` calls `POST /v1/messages` on the Anthropic API with `anthropic-version: 2023-06-01`, default model `claude-sonnet-5-5`, standard library only. It retries once on 429 and 5xx, removes the key from error text, and treats `stop_reason: refusal` as an error so that partial text never becomes a document |
| Output | `<memory>.doc.md` next to the memory and `<data>/DOCUMENTACAO.md`, with a header stating it was generated by AI, the model and the date. A response cut by `max_tokens` gains a warning. `INDICE.md` links the documents |

`VULCAN_ANTHROPIC_BASE_URL` changes the base for a proxy or test server. It must be `https`, and `http` is accepted only for `127.0.0.1`, `localhost` and `::1`, so the key never leaves the machine in clear text. The transport is injectable in `AnthropicClient`, so tests never reach the network.

## 13. Data on disk and configuration

All paths, flags and variables are in [configuration.md](configuration.md).

The data folder is `~/Library/Application Support/VulcanCelox/` on macOS and `$XDG_DATA_HOME/vulcan-celox` on Linux, and `VULCAN_CELOX_HOME` replaces it. `secure_data_dir` sets the folder and subfolders to 0700 and files to 0600 at each start, and does not follow symlinks. Scripts stay executable, for the user only.

| File or folder | Holds |
|----------------|-------|
| `tags.json`, `notes.json`, `tasks.json` | Notebook |
| `sites.json`, `favorites.json`, `quick.json` | Manual sites, favorites, user quick commands |
| `preferences.json`, `new_terminal.json`, `themes.json`, `guide.json` | Autostart, AI model, new terminal defaults, rotation, guide |
| `settings.json` | Sites with the project `TAREFAS.md` enabled |
| `node_projects.json`, `agents_current.json` | Node project list, chosen current session |
| `terminal_sessions.json`, `memoria_status.json` | Session records, last memory error |
| `migrations.json`, `legacy_notes.json` | Migration from the old prototype |
| `agentes.db` (with `-wal` and `-shm`) | Agent index |
| `precos.json` | Optional price overrides |
| `prompts/` | Global prompts, seeded with examples on first use |
| `sessoes/` | Memories and `.doc.md` files |
| `TAREFAS.md`, `INDICE.md`, `DOCUMENTACAO.md` | Generated indexes and documentation |
| `pairings/`, `hooks/` | Files written by the hook; `vulcan-pareamento.py`, `php-ini-editor.sh` |
| `lixeira/` | Fallback when no system Trash is available |
| `abrir-janela.html`, `janela/` | Linux only: launcher page and browser profile |

Each JSON file has the envelope `{"schema_version": 1, "data": ...}`. A file with no envelope is accepted as raw data. A corrupted file is renamed to `<name>.corrupt-<timestamp>`.

Outside the data folder the app writes only: `<project>/TAREFAS.md` (opt-in, marked block), `<project>/.vulcan/` (with confirmation), the blocks in `AGENTS.md` and `CLAUDE.md` of a project where the user installed the harness, and whatever Lerd or Valet write on a user action (`project_writes` warns first). The one write in `~/.claude` is the hook installation.

## 14. Command line flags

### Python package

`python3 -m vulcan_celox <flag>`, from `vulcan_celox/__main__.py`. Checked in this order: `--instalar-hook`, `--reindexar-agentes`, `--podar-agentes`, `--serve`, `--doctor`, then the tkinter interface.

| Flag | Does |
|------|------|
| `--serve` | Local server, API and web interface. Prints `VULCAN_PORT=<n>` |
| `--port N` | Port for `--serve`. 0, the default, means random |
| `--doctor` | JSON: version, data folder, backend, state, sites, Lerd workarounds, agent sources, prices, 30 day usage, last memory error |
| `--reindexar-agentes` | Rebuilds the agent index from zero and prints the totals |
| `--podar-agentes [DAYS]` | Deletes indexed events of sessions idle for more than DAYS (default 180). Summaries, files and commands stay. Never automatic |
| `--instalar-hook` | Installs the pairing hook, with a backup of `settings.json`. See [pairing-hook.md](pairing-hook.md) |
| `--selftest` | Opens the tkinter interface, exercises it and exits. 0 means success |
| `--tk` | Accepted, but it changes nothing: with no other flag, the entry point already opens tkinter |
| `--version` | Version |

`python3 -m vulcan_celox` with no flag opens the **tkinter** fallback, not the web interface. The web interface needs a shell or `--serve`.

### macOS shell

`dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox`. It does not forward the Python flags.

| Flag | Does |
|------|------|
| `--snapshot <file.png>` | Renders off screen and writes a PNG |
| `--route "#/..."` | Initial route |
| `--wait <seconds>` | Wait after load (default 2.5) |
| `--size <W>x<H>` | Window size (default 1440x900) |
| `--eval "<js>"` | With `--snapshot`, runs a script in the page 0.8 seconds after load |
| `--verificar-dependencias`, `--check-deps` | Says which Python would be used (0) or what is missing (1) |

Exit codes of `--snapshot`: 0 success, 1 failure, 2 timeout, 3 JavaScript error in the page, 4 the window left the app's origin.

### Linux

`vulcan-celox` (`packaging/linux/vulcan-celox` then `desktop_linux.py`): `--check` starts the server with no window, verifies and exits; `--mode gtk|app|browser`; `--doctor`; `--version`. The launcher handles `--instalar-dependencias` (`--install-deps`), with an optional `-y`, and `--verificar-dependencias` (`--check-deps`).

## 15. Build and packaging

Requirements: on macOS, the Command Line Tools. There is no `pip install` or `npm install`.

| Script | Does |
|--------|------|
| `scripts/build_app.sh` | Creates `dist/Vulcan Celox.app`: copies `vulcan_celox/` to `Contents/Resources` with `rsync`, writes `Info.plist` (id `com.byvulcan.celox`, minimum macOS 13.0, version from `vulcan_celox/__init__.py`), compiles `packaging/macos/main.swift` with `swiftc` for the current architecture, or arm64 and x86_64 joined by `lipo` with `VULCAN_UNIVERSAL=1`, runs `packaging/macos/icon.swift` to draw the icon, and `iconutil` makes `AppIcon.icns`. PNGs go to `build/icon/` |
| `scripts/install_app.sh` | Installs in `~/Applications` and creates a Desktop shortcut. The previous version goes to the Trash. `VULCAN_INSTALL_DEST` and `VULCAN_DESKTOP` redirect it |
| `scripts/package.sh` | On macOS, generates everything in `executaveis/`: universal app, ad hoc signature (`codesign --sign -`), `.zip` and `.dmg`, Linux `.tar.gz` and `.deb`, and `SHA256SUMS` |
| `scripts/package_linux.py` | Builds the Linux installers with Python 3.9+ only, with no Swift or macOS tools. Output in `executaveis/linux` by default (`--output`), with `SOURCE-MANIFEST.json` carrying a SHA-256 per file. Used by CI |
| `scripts/make_deb.py` | Assembles a `.deb` with the standard library only, with no `dpkg-deb` |
| `scripts/manual_md.py`, `scripts/manual_shots.sh`, `scripts/help_json.py` | User guide from the Help content, its screenshots, and JSON layout |

`packaging/` holds the sources: `macos/main.swift`, `macos/AppIcon.icns`, `linux/vulcan-celox` (launcher: runs from inside the library folder so that a `json.py` in the current repository is not imported), `linux/vulcan-celox-deps` (checks and installs libraries with permission, using apt, dnf or pacman), `linux/install.sh` and `linux/uninstall.sh` (no sudo, under `~/.local` by default), `linux/vulcan-celox.desktop`, `linux/icons/`, `linux/deb/control` and `linux/deb/postinst`, and `LEIA-ME.md`, which ships in the packages.

Linux packages leave `ui/` out, and the `.deb` installs under `/opt/vulcan-celox` with a link in `/usr/bin`.

`.github/workflows/linux-mint.yml` runs on Ubuntu 22.04: `scripts/test_linux.sh`, `scripts/package_linux.py`, verification of the sums, installation of the `.deb`, `--check` and `--doctor`, and installation from the `.tar.gz`.

`.github/workflows/windows.yml` runs `tests.test_windows` and the whole suite, builds the `.zip` with `scripts/package_windows.py`, extracts it and runs `scripts/smoke_windows.py` from it. `.github/workflows/macos.yml` builds the app and runs the suite on macOS.

Release steps are in [development.md](development.md).

## 16. Testing and sensors

Full description in [testing.md](testing.md). In short, `bash scripts/validate.sh` is the one sensor, and its exit code decides.

Steps of the script: `compileall`; user guide equals its generated form; `unittest` on the current Python and on the system's Python 3.9; `--selftest` with no backend and with a fake Lerd and the panel down; bundle build, `plutil`, icon size; `--snapshot` of the main routes with fixtures; screens with `tests/tools/fake_lerd_api.py` and `tests/tools/fake-lerd`, where each expected selector starts as an error and clears only when it appears; typed text surviving a changing site list; window confined to the origin; server not importing from the current folder; installation in temporary folders.

Other tools: `bash scripts/test_linux.sh` runs the suite in a `python:3.9-slim` container (`VULCAN_LINUX_IMAGE`, podman or docker).

Tests that hold rules from section 2:

| Test | Holds |
|------|-------|
| `tests/test_arquitetura.py` | No tkinter in `core/`, no definitive delete, `subprocess` and `shell=True` only in the runner |
| `tests/test_arquitetura_doc.py` | This manual names every module of `core/` and `server/` |
| `tests/test_tamanho_arquivos.py` | No new code file above 400 lines, and the frozen ones do not grow |
| `tests/test_docs_abertos.py` | Same pages in both languages, internal links exist, no long dash character |
| `tests/test_vendor_licenses.py` | Licenses of vendored code |
| `tests/test_web_assets.py` | JavaScript syntax with `node --check` or `jsc` when available, and other interface checks |
| `tests/test_aceite_pareamento.py` | The path tab, session, prompt, with a real PTY, a real shell and a fake `claude` |

Base classes: `tests/helpers.py` (`TempDirTestCase`) and `tests/server_helpers.py` (`ServerTestCase`, which starts a real server on a free port, with a temporary data folder and `FakeRunner`). Tests never touch the real Lerd, `~/.claude` or `~/.codex`. Fixtures in `tests/fixtures/` cover agents (anonymized real sessions and synthetic cases), Lerd, harness and Node.

## 17. Known limits and debt

| Item | Situation |
|------|-----------|
| Six files above 400 lines: `packaging/macos/main.swift` (687), `ui/app.py` (594), `web/js/views/tasks.mjs` (523), `core/notebook.py` (493), `core/harness.py` (462), `web/js/views/site.mjs` (440) | Accepted for 1.0, because splitting terminal and window code with no browser test carries more risk than gain. `tests/test_tamanho_arquivos.py` stops them from growing and blocks new files above 400 |
| macOS package has no embedded Python and is not notarized | It has only an ad hoc signature. `--verificar-dependencias` explains and offers to install. `packaging/LEIA-ME.md` explains how to open an app that is not signed with an Apple certificate |
| Linux | Test builds as pre-releases; no stable release until acceptance on a real desktop |
| Windows | Test builds as pre-releases, tested only on CI machines. Not available: Lerd and Valet, the optional hook, clicking `C:\...` paths, the foreground check before writing to a tab. No installer or code signature |
| Interface language | English by default, Portuguese from ⌘K. The source text in the code is Portuguese, and `web/i18n/en.json` is the only dictionary, shared by the interface, the server and the macOS shell |
| JSONL formats of Claude Code and Codex change without notice | Reading is tolerant: a strange line becomes `parse_errors` and reading continues. Fixtures come from real sessions |
| Codex pairing | No exact link exists on Codex 0.166.0, and no stable hook. Pairing is by folder and time, so two Codex sessions started in the same folder less than 60 seconds apart can swap tabs |
| `.jsonl.zst` rollouts | Read through the `zstd` command when present, always from the start. Otherwise they are ignored and counted in `--doctor` |
| Gemini CLI and Cursor CLI | Not supported. `procinfo.AGENT_EXECUTABLES` has entries for them, but no reader exists |
| Typed commands | Commands recalled from shell history with the arrow keys are not captured |
| Lerd commands that ask for an administrator password | The app only calls the CLI and shows the output. It never asks for or stores a password |
| Lerd CLI or API changes between versions | Parsers are tested against fixtures, and a failure shows the raw output |
| Server token | Another process of the same user can read the app's memory. Outside the threat model |
| Key created by `/usr/bin/security` | Other processes of the same user may read it through `security`. A macOS limitation |
| `core/tables.py` | Covered by tests, with no production caller today |
| Fallback entry point | `python3 -m vulcan_celox` with no flag opens the old tkinter interface, and `--tk` has no effect of its own |
| Cost | An estimate at API prices. The default table goes stale, and `precos.json` overrides it |

## 18. How to extend

Each file you add must stay under 400 lines, and Python must stay compatible with 3.9. Also read [development.md](development.md). A behavior change updates both language versions of the docs.

### Add an API route

1. In `server/<area>_api.py`, or a new module with `register_<area>_api(app)`:

   ```python
   def register_exemplo_api(app):
       srv = app.server

       @srv.route("GET", r"/api/exemplo/(?P<name>[a-z0-9-]+)")
       def detail(req):
           if req.arg("x") == "bad":
               raise HttpError(400, "x inválido")
           return {"name": req.params["name"]}
   ```

   `req.params` holds named groups, `req.arg(name)` the query and `req.json()` the body. Return data, `(status, data)` or `RawResponse`.
2. For a new module, call `register_exemplo_api(self)` in `VulcanApp.__init__` (`server/app.py`), as the others do. Token, `Host`, `Origin` and Content-Type checks already apply.
3. Validate every value. Anything that reaches a command goes in an argv list through the runner, or through a fixed table. A value starting with `-` must not become an option.
4. Test with `ServerTestCase` from `tests/server_helpers.py` and `FakeRunner`.
5. Add the route to [http-api.md](http-api.md), in both languages.

### Add a view

1. Create `web/js/views/<name>.mjs` with a class taking `(root, options)` and, as needed, `update(state)`, `reveal(route)`, `command(name)`, `destroy()`. Escape displayed data with `esc` from `dom.mjs`. No external resources: the CSP blocks them. For repetition, use `every` from `api.mjs`, and stop it in `destroy`.
2. Import it and add a `case` in `web/js/view-mount.mjs`.
3. For a sidebar item, add it to `NAV` (or `AGENT_NAV`) and to a group in `NAV_GROUPS` in `web/js/app-state.mjs`. A route with parameters also needs `parseRoute` in `web/js/app.mjs`.
4. Map the route to a Help section in `ROUTE_SECTION` (`web/js/help-content.mjs`); `tests/test_help_routes.py` checks that every sidebar route is there. If the screen does not receive the site list, add it to `KEEP_ON_SITES` in `web/js/remount.mjs`.
5. Add the route with expected selectors to `scripts/validate.sh`. Its `#/overview` check holds the number of sidebar items and groups, so update it when you add one.
6. Document it in `web/help/conteudo.json`, then run `python3 scripts/manual_md.py`.

### Add a backend

1. Create `core/backends/<name>.py` with a `Backend` subclass: `name`, `label`, `available = True`, `start`, `stop`, `restart`, `site_command(action, *args)` returning `(argv, cwd)`, and `share_argv`. Override as needed: `status`, `list_sites`, `php_versions`, `version`, `project_writes`, and `dashboard_url` if it has a panel. `Backend` already provides `link`, `secure`, `isolate` and the others from `site_command`, with validation.
2. Add locations and a variable in `core/paths.py`, and the detection in `detect_backend` (`core/backends/__init__.py`), in the desired priority.
3. Run through `self.runner` only, so that tests can use `FakeRunner`. Do not edit the tool's global files.
4. `server/env_api.py` and `server/debug_api.py` require `name == "lerd"`, so those screens stay unavailable for another backend unless you extend them.

### Add an agent reader

1. Create `core/agents/<name>_reader.py` following `claude_reader` and `codex_reader`: `new_session(path)` returning an `AgentSession`, and a class with `agent`, `__init__(session, state)`, `state()` (serializable, for incremental reading), `feed(obj)` (one parsed line) and `drain_usage()`. Build through `SessionBuilder`, exposed as `self.b`, because `read_session` calls `reader.b.drain_events()`.
2. Register it in `_readers()` (`core/agents/reading.py`) and add the id to `AGENTS` (`core/agents/model.py`).
3. List its files in `core/agents/discovery.py`, and include them in `AgentWatcher.files()` and `roots()`. Add to `core/agents/status.py` what `--doctor` should show.
4. Put tools and patterns in the tables of `core/agents/rules.py`, not in `if`s in the reader.
5. Add its command to `RESUME_COMMANDS` (`server/agents_api.py`), which `resume` looks up directly, to `AGENT_COMMANDS` (`server/terminals_api.py`) and `NEW_TERMINAL_AGENTS` (`server/app.py`) if it can open from the new terminal dialog, to `_AGENT_COMMAND` (`core/agents/pairing.py`), to `AGENT_EXECUTABLES` (`core/procinfo.py`), and to `AGENT_LABELS` (`core/session_memory.py` and `core/prompts.py`).
6. Add prices to `core/agents/pricing.py`, with the source and date.
7. Add fixtures from real anonymized sessions under `tests/fixtures/agents/`. Tests must never read the real folder.
8. Read as a stream, by line, and never write to the agent's folder. Update [agent-file-formats.md](agent-file-formats.md).
