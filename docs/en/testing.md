# Testing

`bash scripts/validate.sh` is the single sensor: **its exit code decides**. At version 1.0.0 it ran 701 tests.

## What validate.sh runs

| Step | Checks |
|------|--------|
| `compileall` | Python syntax |
| Manual comparison | `docs/pt-BR/user-guide.md` equals what `scripts/manual_md.py` generates |
| `unittest` | Full suite, on the current Python and on the system's Python 3.9 |
| `--selftest` | tkinter fallback, also with a fake Lerd and the panel down |
| Bundle build | `swiftc`, `plutil`, the icon |
| Native snapshot | Real app rendering routes to PNG |
| Screens with a fake Lerd | Selectors start as errors and clear only when they appear |
| Typed text survives | Composer fields while the site list changes |
| Window confined | Window stays on the app origin |
| Hostile folder | The server does not import modules from the current folder |
| Installation | Install into temporary folders |

`bash scripts/test_linux.sh` runs the suite in a `python:3.9-slim` container (podman or docker). GitHub Actions also builds the Linux packages, checks the hashes and installs the `.deb` on Ubuntu 22.04.

## Principles

- **The sensor decides, not the author.** A contract item is done when its sensor is green.
- **Fail first.** A fix starts with a test that reproduces the defect and fails.
- **Do not weaken tests.**
- **Real fixtures.** `tests/fixtures/agents/` holds anonymized real sessions from Claude Code and Codex, plus synthetic cases marked as such.
- **Never touch the real world.** Tests use `VULCAN_TERMINAL_HOME`, `tests/tools/fake_lerd_api.py` and `tests/tools/fake-lerd`. They never read the real `~/.claude` or `~/.codex`, and they never touch the real Lerd.
- **Guard the guards.** A sensor that passes without verifying anything is a defect. Snapshot scripts carry a mark that fails if the script did not run.

## End-to-end acceptance

`tests/test_aceite_pareamento.py` walks the path tab, session, prompt with a real PTY, a real shell and a fake `claude` executable that writes a session. It does not run the real agents, since that would use quota and write to real folders.


## Writing a test

Use `unittest`, the standard library only. For anything that runs a process, use `FakeRunner`. For a screen, add a route with selectors to `validate.sh`. Server tests in `tests/` use a base class that starts a real server on a free port with a temporary data folder.
