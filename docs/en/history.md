# Development history

How Vulcan Terminal reached version 1.0.0, from September to November 2026. The changes in each version are in the [CHANGELOG](../../CHANGELOG.md), and what comes next is in the [ROADMAP](../../ROADMAP.md).

## In numbers

| | |
|---|---|
| First commit to 1.0.0 | 2026-09-13 to 2026-11-01 (50 days) |
| Days with commits | 7 |
| Commits | 245 in the original development |
| Automated tests | 224 at 0.2.0, 405 at 0.3.0, 617 at 0.5.0, about 700 at 1.0.0 |
| Dependencies to install with pip | 0 |

The code was created with AI assistance, directed and reviewed by the author. For this publication, the history was consolidated into a single commit, which is why the 245 commits do not appear here.

## Phase 1: the PHP panel (September)

It started as a 394-line tkinter prototype, a panel for local PHP sites with sticky notes.

- **Sep 13, first commit.** The initial plan had Herd as the preferred tool. Because it is commercial, it was dropped early: the app came to orchestrate Laravel Valet and then Lerd, with priority, both MIT.
- **Sep 13, first version.** 0.1.0 brought the foundation and the notebook of tasks and notes.
- **Sep 13, interface change.** The app opened blank with the system's Tk 8.5, and the tkinter interface was rejected. The current architecture was born the same day: a local server, real PTY terminals, xterm.js and a native Swift shell with WKWebView. Each terminal became a session with a Markdown memory.
- **Sep 14, version 0.2.0.** Native app, an icon drawn in code, on-click AI session documentation, and packages for macOS and Linux.

## Phase 2: the pause and the idea (October)

- **Oct 10, Linux.** A Linux Mint package, built on Linux itself.
- **Oct 29, the agent panel.** The new idea was to follow Claude Code and Codex sessions. The first scope was a separate app in Node, React and Tauri. An analysis showed that about 70% of the required infrastructure already existed here, and the decision was to integrate.

## Phase 3: the three days (Oct 30 to Nov 1)

Of the 245 commits, 168 happened in these three days.

| When | What happened |
|------|---------------|
| Oct 30 | Session reader, index and file watcher. The machine's Command Line Tools had to be installed first |
| Oct 31 | An app defect on Linux wrongly marked sessions as active. It was fixed in the app, not in the test that revealed it |
| Oct 31 | First independent review: 14 defects, including a risk of `git status` running a hook from the analyzed repository |
| Oct 31 | Prompts by button, pairing between tab and session, themes and terminal panel. **Version 0.3.0** |
| Oct 31 | Full documentation of the app's state and two reviews: 33 defects, with the first round of fixes in **0.3.1** |
| Oct 31 | Sites, Environment and Debug rewritten on Lerd. **Version 0.4.0** |
| Oct 31 | Usage and cost, and the Harness tab. **Version 0.5.0** |
| Nov 1 | Node projects, Home screen, manual and Help (**0.6.0**). Prompts as actions (**0.7.0**) |
| Nov 1 | New independent reviews (**0.7.1** and **0.7.2**) |
| Nov 1 | Gemini CLI and Cursor CLI suspended: the focus stayed on Claude Code and Codex |
| Nov 1 | Workarounds for Lerd defects and a fix [sent to that project](https://github.com/lerd-env/lerd/pull/2404) (**0.8.0**). Improvements to Codex pairing (**0.8.1**) |
| Nov 1 | macOS acceptance and quality (**0.9.0**) |
| Nov 1 | **Version 1.0.0**, the first stable one, macOS only |

## Decisions that shaped the project

- **Orchestrate, do not reimplement.** The PHP environment stays with Lerd or Valet, and the chat stays with each agent's official CLI.
- **Read, do not write.** The app reads the files that agents already write, with no API key and without writing to their folders. The one exception is the optional pairing hook, installed by the user, with a backup.
- **No dependencies.** Python with only the standard library, a web interface with no build step, and xterm.js included in the repository.
- **Nothing is deleted for good.** A removed folder goes to the Trash.
- **The test decides.** `scripts/validate.sh` says whether a change passes, and a test is never weakened to pass.
- **macOS first.** Linux has tests in a container and in CI, but it has not been accepted on a real desktop, so it did not count as delivered.

## Versions

| Version | Date | Theme |
|---------|------|-------|
| 0.1.0 | 2026-09-13 | Foundation and notebook |
| 0.2.0 | 2026-09-14 | Native app, real terminal, memory, packages |
| 0.3.0 | 2026-10-31 | Agent panel |
| 0.3.1 | 2026-10-31 | Review fixes |
| 0.4.0 | 2026-10-31 | Sites and environment on Lerd |
| 0.5.0 | 2026-10-31 | Usage and cost, Harness |
| 0.6.0 | 2026-11-01 | Node, Home and Help |
| 0.7.0 | 2026-11-01 | Prompts as actions |
| 0.7.1, 0.7.2 | 2026-11-01 | Review fixes |
| 0.8.0, 0.8.1 | 2026-11-01 | Lerd and Codex |
| 0.9.0 | 2026-11-01 | Quality |
| **1.0.0** | **2026-11-01** | **First stable version, macOS only** |
| 1.1.0 | 2026-11-03 | New name Vulcan Celox, Code tab, attention, path links, requests, ports and PR |
| 1.1.1 | 2026-11-03 | New terminal failing with an unknown theme |
| 1.2.0 | 2026-11-03 | Windows and Linux as test builds |

## 1.1.0: the name changes

The product was called Vulcan Terminal until 1.0. From 1.1.0 it is Vulcan Celox, with its own visual identity. The technical names changed too: the data folder is now `VulcanCelox`, the app id `com.byvulcan.celox`, the Python package `vulcan_celox`. Nobody loses anything when updating: the old folder is moved when the app starts, and the Anthropic key is copied to the new Keychain item the first time it is read.
