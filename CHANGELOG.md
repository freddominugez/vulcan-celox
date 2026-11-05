# Changelog

All notable changes to Vulcan Celox, called Vulcan Terminal until 1.0. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Portuguese version: [CHANGELOG.pt-BR.md](CHANGELOG.pt-BR.md).

## [Unreleased]

### Added
- **Settings screen.** Choose which items and lists the sidebar shows, plus theme, language, opening screen, Lerd start, folder prompt, notices, PR check, the Anthropic key, version and data folder.
- **Opening screen.** Home opens with the app until you check the box, and explains every item in cards. Each sidebar item also has a hint.

- **Backup and restore.** Settings saves all of the app's data in a `.zip`, and restores one when you reopen the app. The current data moves to `.restauros/` and nothing is deleted.
- **New version notice.** The app checks GitHub at most once a day and tells you when a newer Release exists. It only reads the version number and never downloads anything. It is on by default and can be turned off in Settings.

### Security
- Session memory is now saved with recognized secrets masked. A **Mask** button in Settings rewrites memories saved earlier.
- A password typed at a hidden prompt (`sudo`, `ssh`) no longer ends up in the command list. Windows cannot detect this prompt.

### Changed
- The empty terminal panel stays collapsed until you open a terminal or press ⌘J. The large logo is only on Home. The Anthropic key moved from Index to Settings.

### Removed
- The "PHP sites" sidebar item, which opened the same screen as Overview, and the Lerd state at the foot of the sidebar, already shown twice above. The site list stays.

### Fixed
- The manual claimed things the code does not do: that the green dot covers DNS and PHP (it means nginx), that nothing is ever deleted, that the Index has search, and what session memory holds. It keeps recent terminal output on disk without masking secrets, and the manual now says so.
- The native menus and alerts appeared in Portuguese in the English interface.
- ⇧⌘T did nothing in the native app. A Node project with a broken `package.json` showed a raw internal word. Shortcuts in Help and on Home showed ⌘ on Windows and Linux.

## [1.2.1] - 2026-11-04

### Changed
- **Lerd is optional.** It no longer starts with the app until you turn on the bolt button, and without it the top bar shows no environment controls. On the Home screen, the Lerd step does not hold the guide back, offers **Install** with the official command in a visible terminal, and **I don't use it**. A Lerd installed while the app is open is noticed without restarting. On Windows the Lerd item is gone.
- Code comments and docstrings are in English.
- CI covers lint and the whole suite on Windows. The macOS workflow runs on request before each release, and each pull request runs the sensors on a Mac. A test keeps the version cited in the documentation equal to the code.

### Fixed
- A tab whose command ended right after it opened could stay listed as open.
- "Could not start Lerd" with a progress line as the reason. The app now waits for the environment to answer after `lerd start`, and a progress line is never shown as a failure.
- The automatic start no longer shows a floating message: the state stays in the top bar, and a failure on the Lerd and Home screens.
- A command typed by the app into a PowerShell tab did not run. Other Windows defects found by running the whole suite there.
- Documentation that no longer matched the code: the technical names after the rename, versions, Linux and Windows status, and the supported versions in the security policy.

## [1.2.0] - 2026-11-03

### Added
- **Windows, as a test build.** Real terminal through ConPTY, PowerShell by default, Recycle Bin, Credential Manager and ports per tab, in a portable package with Python included. See the installation guide for what is not available there.

### Fixed
- A corrupted agent index could stop the app from opening on Windows.

## [1.1.1] - 2026-11-03

### Fixed
- Opening a terminal from the dialog failed with "unknown theme": any click in the dialog took the interface theme as the tab theme.
- Build and test copies of the app no longer show up as extra icons on macOS.

## [1.1.0] - 2026-11-03

**Vulcan Terminal is now Vulcan Celox.** Your data, Keychain item and preferences stay where they were. Installing moves the old app to the Trash.

### Added
- **Code tab** in the agent session: tree of touched files, syntax highlighting, and diffs per edit, per request or against the last commit, side by side or unified. Read only. In an active session it follows the agent; any gesture pauses it, and **Voltar a seguir** resumes.
- **Who is waiting for you:** ring on the tab, count in the sidebar, ⌘⇧U to jump, and a system notice with the window out of focus. It also reads OSC 9, 99, 777 and the bell. An optional hook shows permission requests at once.
- **⌘-click a path in the terminal:** opens in the Code tab at the line, in your editor, or in Finder.
- **Jump between requests:** ⌘⇧↑ and ⌘⇧↓ in the terminal, and **Linha do tempo** grouped by request, linking to the diff of that request.
- **Ports per tab:** a badge such as `:5173 +2` in the tab bar and the session list.
- **Real PR state, optional and off by default:** number, draft, state and checks through your own `gh`. With it off no command runs.
- Light and dark themes (System by default), Inter, Phosphor icons, the new logo and app icon.

### Security
- The Code tab refuses anything outside the session folder, links included, as well as binaries, files above 1 MB and sensitive names such as `.env`. The diff follows the same rules.
- The diff against git cannot run anything from the analyzed repository: `diff.external`, `textconv` and filters never run.

### Changed
- The session index stores where each edit is, never its content. The index is rebuilt once when you update.

### Known limits
- The app icon lost its 16 and 32 px sizes by brand decision; macOS scales down from the larger ones.
- A relative path printed after a `cd` may not resolve for ⌘-click: it counts from the session folder or the folder the tab opened in.

## [1.0.0] - 2026-11-01

First stable release, **macOS only** (`.dmg`, `.zip`, `SHA256SUMS`). The Linux code stays in the repository and in CI, but no Linux package ships until it passes the acceptance script on a real desktop.

### Added
- End-to-end acceptance test with a real PTY, a real shell and a fake agent executable (`tests/test_aceite_pareamento.py`).

### Fixed
- An agent session without a folder created a blank option in the project filter of the Agents screen.
- Ctrl+Shift+F never opened terminal search on Linux, and its tooltip showed the macOS shortcut.
- Agent session titles showed the whole pasted request, including code fences. They now show the first sentence or up to 120 characters; the full request stays in the First request panel.

### Known limitations
- The app has no Apple certificate and is not notarized, and Python 3.9+ must be on the machine.
- Codex has no exact link between a terminal tab and a session. Two Codex sessions started in the same folder less than 60 seconds apart can swap tabs.
- Gemini CLI and Cursor CLI are not supported.

## [0.9.0] - 2026-11-01

### Changed
- AI documentation defaults to Claude Sonnet 5.5. Prices were checked against the official pages.
- `app.mjs`, `server/app.py` and `sites_api.py` were split. A test now blocks new files above 400 lines.

### Fixed
- GitHub Actions job, broken by a permission failure in `tar`.
- A refusal from the Anthropic API now shows a clear error.

## [0.8.1] - 2026-11-01

### Added
- Reading of compressed Codex sessions (`.jsonl.zst`) through the system `zstd`, when available.

### Fixed
- Codex subagents and the Codex desktop app no longer pair with a terminal tab.
- Competing sessions now pair in time order.

## [0.8.0] - 2026-11-01

### Added
- `core/lerd_quirks.py` and a `--doctor` block listing Lerd workarounds and the version that fixes each one.
- Upstream fix for Lerd: [lerd-env/lerd#2404](https://github.com/lerd-env/lerd/pull/2404).

## [0.7.2] - 2026-11-01

### Fixed
- Prompts are refused (HTTP 409) when the agent is no longer in the foreground of the tab or when a newer session owns it.
- PTY writes no longer hang on a tab that does not read its input; they time out after 5 seconds without progress.
- Prompt files now get private permissions (0600 and 0700) inside the data folder.
- Prompt composer fields kept resetting while the site list changed.
- Keyboard focus was lost in the sidebar and in the Home guide after a redraw.

## [0.7.1] - 2026-11-01

### Fixed
- Findings from two independent reviews of 0.7.0: control characters in session values, stale responses in the Usage and History screens, terminal size validation, a lock around the Node project list, and project root validation.

## [0.7.0] - 2026-11-01

### Added
- Prompts as actions: cards, a composer with one field per variable, a live preview and **Send to terminal**, which pastes the text into the paired agent **without pressing Enter**.
- Sidebar in collapsible groups, with separate lists for PHP sites and Node projects.
- "Do not show the guide again" checkbox on the Home screen.

## [0.6.0] - 2026-11-01

### Added
- Node projects: `package.json`, lockfile, framework and port detection, local Supabase, Vercel link status, scripts running in a visible terminal tab.
- Lerd as a sidebar item with a status dot.
- Home screen with a self-checking four-step guide, Help screen with manual and FAQ, `?` button on every screen, and `docs/MANUAL.md` generated from the same content.

## [0.5.0] - 2026-10-31

### Added
- Usage and cost: tokens and estimated cost at API list prices, by day, project, model and session, with CSV export. Prices can be overridden in `precos.json`.
- Project harness in the interface: contract, items, next item, last green commit, handoff, **Install harness** and **New contract**.

### Notes
- Gemini CLI and Cursor CLI readers were planned here and later suspended.

## [0.4.0] - 2026-10-31

### Added
- Full site management on top of Lerd: add, link, park, PHP, Node and HTTPS per site, share, logs.
- Environment screen: services, PHP versions, extensions, Xdebug, six common `php.ini` settings.
- Debug screen: dumps, queries, logs and exceptions from the Lerd dump bridge, grouped by request, with repeated query warnings, plus a "Debug in this period" panel on each agent session.

### Fixed
- Hostile working folder could influence the `php.ini` helper (now started with `python -I`).
- Clipped panels, a sensor gap with a fake Lerd API, and repeated CLI calls (60 second cache).

## [0.3.1] - 2026-10-31

### Security
- Token accepted only in the `X-Vulcan-Token` header on the API. Writes require JSON. `Origin` and `Content-Length` are validated. The window cannot navigate away from the app origin.
- Data folder 0700 and files 0600. Secrets are masked before text is cut for AI documentation. The token is no longer on the Linux command line.

### Fixed
- PTY shutdown races, unbounded WebSocket queues, index lock contention during long reads, and the pairing hook breaking on paths with spaces.

## [0.3.0] - 2026-10-31

### Added
- Agent panel: read-only indexing of Claude Code and Codex JSONL sessions, session cards, timeline, files touched, publication trail and a possible-loop alert.
- Unified history with accent-insensitive search; branches and worktrees cross-checked with real git.
- Prompt library in Markdown, global and per project, filled in from the session.
- Color themes per tab, pairing between tab and agent session, optional `--instalar-hook`, resume a session in a tab.
- Bottom terminal panel: resize, split, search, WebGL.

## [0.2.0] - 2026-09-14

### Added
- Lerd as the priority backend, with Valet and a local mode as alternatives.
- Native macOS shell (Swift, WKWebView), local server, real PTY terminals with xterm.js.
- Terminal sessions with Markdown memory and a general index; sessions tree in the sidebar.
- AI documentation of a session, by click only, with the user's own Anthropic key in the Keychain and secrets masked.
- Packages for macOS and Linux and dependency installation with permission.
- Linux Mint packages rebuilt from source on 2026-10-10 (`v0.2.0-mint-20261010`).

## [0.1.0] - 2026-09-13

### Added
- Foundation: Python standard library core, Valet and Null backends, site discovery, tkinter interface.
- Notebook: tags, sticky notes, tasks, progress, `TAREFAS.md`, global search, export and import.

[1.0.0]: https://github.com/freddominugez/vulcan-celox/releases/tag/v1.0.0
