# Roadmap

**English** | [Português](ROADMAP.pt-BR.md)

Direction, not a promise. How the project got here: [development history](docs/en/history.md).

## Delivered in 1.0.0 (macOS)

Agent panel for Claude Code and Codex, history search, prompts, usage and cost, branches, Harness tab, real terminals, PHP sites through Lerd or Valet, Node projects, notebook, Help and manual. Details in the [CHANGELOG](CHANGELOG.md).

## Next

- **Linux release.** Test on a real Linux Mint desktop, fix what fails, publish `.deb` and `.tar.gz`. Help welcome.
- **Windows acceptance.** Test build 1.2.0 ran only on CI machines. Test on real Windows 10 and 11, then decide on an installer and signature.
- **Finish the manual checks on macOS:** pairing with the real Claude Code, split, search and resize.

## Delivered in 1.1.0 (macOS)

New name Vulcan Celox with light and dark themes, Code tab (a viewer: it does not edit files), attention signals, ⌘-click on paths, jumping between requests, ports per tab and optional PR state. Details in the [changelog](CHANGELOG.md).

Still waiting: the Linux release after the acceptance on Mint.

## Later, not decided

- Signed and notarized macOS build, and a bundled Python.
- Other agents: Gemini CLI and Cursor CLI are suspended.
- Exact pairing for Codex. It depends on a change in Codex itself.
- Splitting the seven files above 400 lines.

## Not planned

- Herd as a backend.
- Reimplementing a chat, an editor or the agents' protocols. The terminal stays the official CLI, and the Code tab only displays files.
