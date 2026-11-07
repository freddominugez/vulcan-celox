# Contributing

Portuguese version: [CONTRIBUTING.pt-BR.md](CONTRIBUTING.pt-BR.md).

Thanks for your interest. Bug reports, tests on other machines (especially **Linux desktops**) and documentation fixes are the most useful contributions right now.

## Before you start

- Open an issue before large changes, so we can agree on scope.
- Read [docs/en/development.md](docs/en/development.md) for setup and [docs/en/architecture.md](docs/en/architecture.md) for the structure.
- The interface is in English by default, with Portuguese available. Source strings are in Brazilian Portuguese because they are the dictionary keys; code comments and docstrings are in English; new strings need an entry in `vulcan_celox/web/i18n/en.json`. Issues and pull requests are welcome in English or Portuguese.

## Hard rules

These are checked by tests or reviewed by hand, and a pull request that breaks them will not be merged.

- Python 3.9 standard library only. No pip dependencies.
- No build step in `vulcan_celox/web/` and no external resource loaded by the interface. Only xterm.js and its official MIT addons are vendored.
- `vulcan_celox/core/` does not import tkinter. Subprocesses go only through `core/runner.py`; `shell=True` only in `run_shell`.
- The server listens only on `127.0.0.1`, with a mandatory token.
- Never write to `~/.claude`, `~/.codex`, `~/.claude.json` or `~/.codex/config.toml`. Read session files only as a stream, line by line. The one exception is `--instalar-hook`, run by the user.
- No permanent deletion (`shutil.rmtree`, `rm -rf`). Folders go to the Trash.
- Do not edit global files of Lerd, Valet or Herd. Write to a project folder only with opt-in and inside a marked block.
- Herd is commercial: never copy its binaries, extensions, icons or text, and never use it as a backend.
- No file above 400 lines (`tests/test_tamanho_arquivos.py`). Existing exceptions are listed in the test and cannot grow.
- No em dash in generated text.

## Pull requests

1. Write a test that fails first, then the fix.
2. Run `bash scripts/validate.sh` on a Mac before opening the pull request. This local run is the macOS check: pull requests run Linux, Windows and lint automatically, and the macOS workflow runs only on request. On Linux, or to test Linux from a Mac, run `bash scripts/test_linux.sh`.
3. One logical change per commit. Commit messages follow `type(scope): summary`, for example `fix(terminal): ...`.
4. Update the docs affected by the change, in both languages when the page exists in both. Do not edit `docs/pt-BR/user-guide.md` by hand: it is generated from `vulcan_celox/web/help/conteudo.json` by `scripts/manual_md.py`.
5. Never weaken a test to make it pass. If a behavior changed on purpose, explain it in the pull request.

## Using AI tools

AI-assisted contributions are welcome. You remain responsible for what you submit: run the sensors, read the diff, and say in the pull request what was verified and what was not.

## Test fixtures

Anonymize paths, e-mails and tokens (`/Users/dev/projeto`). Tests must never read the real `~/.claude` or `~/.codex`.

## License

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
