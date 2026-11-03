# Development

## Setup

Requirements on macOS: Command Line Tools (`xcode-select --install`). For the Linux suite: podman or docker. There is nothing else to install: no `pip install`, no `npm install`.

```bash
git clone https://github.com/freddominugez/vulcan-hub-painel.git
cd vulcan-hub-painel
bash scripts/build_app.sh
open "dist/Vulcan Celox.app"
```

## Daily commands

```bash
python3 -m vulcan_terminal --serve           # server, prints VULCAN_PORT
python3 -m unittest discover -s tests -t .   # tests
python3 -m unittest tests.test_agents_api    # one file
bash scripts/validate.sh                     # all sensors
bash scripts/test_linux.sh                   # suite in a Linux container
bash scripts/build_app.sh                    # dist/Vulcan Celox.app
bash scripts/install_app.sh                  # ~/Applications and Desktop shortcut
bash scripts/package.sh                      # packages in executaveis/
```

Use `VULCAN_TERMINAL_HOME=$(mktemp -d)` to keep your real data away from experiments, and `VULCAN_KEYSTORE=memory` to keep the Keychain out of it.

## Code rules

The list is in [CONTRIBUTING.md](../../CONTRIBUTING.md). Python must stay compatible with 3.9: no `match`, no `X | Y` in runtime annotations.

## Where to change what

| To change | Look at |
|-----------|---------|
| A screen | `web/js/views/<screen>.mjs`, `web/styles/` |
| An endpoint | `server/<area>_api.py` |
| Logic | `core/`, with a test that needs no window |
| How a session is read | `core/agents/claude_reader.py`, `codex_reader.py`, `rules.py` |
| A new theme | A dictionary in `core/themes.py` |
| Model prices | `core/agents/pricing.py`, with the source and date |
| Help text | `web/help/conteudo.json`, then `python3 scripts/manual_md.py` |
| Help screenshots | `scripts/manual_shots.sh` (fixtures and a fake Lerd, never real data) |

## Seeing the interface without a person

```bash
"dist/Vulcan Celox.app/Contents/MacOS/vulcan-terminal" --snapshot out.png --route "#/agentes"
```

`--snapshot` renders a route to PNG and fails on a JavaScript error, and `--eval` runs a script in the page. `validate.sh` uses them as sensors.

## Releasing

1. Update `vulcan_terminal/__init__.py`, the workflow in `.github/workflows/`, `README` files, `CHANGELOG` in both languages.
2. `bash scripts/validate.sh` and `bash scripts/test_linux.sh`.
3. `bash scripts/package.sh`, `bash scripts/install_app.sh`.
4. Tag, push, create the release with the packages and `SHA256SUMS`, then download and check the sums.

Until the Linux acceptance is done, releases carry only the macOS files.
