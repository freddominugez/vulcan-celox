# Roadmap

**English** | [Português](ROADMAP.pt-BR.md)

Direction, not a promise. How the project got here: [development history](docs/en/history.md).

## Delivered in 1.0.0 (macOS)

Agent panel for Claude Code and Codex, history search, prompts, usage and cost, branches, Harness tab, real terminals, PHP sites through Lerd or Valet, Node projects, notebook, Help and manual. Details in the [CHANGELOG](CHANGELOG.md).

## Next

- **Linux release.** Test on a real Linux Mint desktop, fix what fails, publish `.deb` and `.tar.gz`. Help welcome.
- **Finish the manual checks on macOS:** pairing with the real Claude Code, split, search and resize.

## Planned for 1.1

- **Know when an agent needs you.** A ring on the tab, a counter in the sidebar and a system notification when a session finishes its turn or may be waiting. It also reads standard terminal sequences (OSC 9, 99 and 777), so it works with any program. The optional hook makes the permission state exact for Claude Code.
- **Live Code tab, read-only.** The files a session touched, the code with syntax highlighting, and diffs by edit, by turn and against git, following the agent as it works, plus an "Open in editor" button.
- **Command-click a path in the terminal.** Opens the file at the right line.
- **Move between turns.** Shortcuts jump between your requests, in the terminal and on the session screen.
- **Listening ports and pull request status.** Each tab shows the ports it opened. Real pull request status through your own `gh` is optional and off by default, because it uses the network.

## Later, not decided

- English interface. The interface is in Portuguese today.
- Signed and notarized macOS build, and a bundled Python.
- Other agents: Gemini CLI and Cursor CLI are suspended.
- Exact pairing for Codex. It depends on a change in Codex itself.
- Splitting the seven files above 400 lines.

## Not planned

- Windows: Python's `pty` module does not exist there.
- Herd as a backend.
- Reimplementing a chat, an editor or the agents' protocols. The terminal stays the official CLI, and the Code tab only displays files.
