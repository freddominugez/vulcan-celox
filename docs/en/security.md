# Security model

Who this protects: one developer on their own machine, whose terminals and agents already hold a lot of power. The goal is that the app adds no new door.

## Local server

- Listens only on `127.0.0.1`.
- Token: 32 random bytes per run. On the API it comes only in the `X-Vulcan-Token` header; a query string token is accepted only on the WebSocket.
- `Origin` is checked. Writes (`POST`, `PUT`, `PATCH`) require `application/json`. `Content-Length` is validated.
- The window cannot navigate away from the app's origin. External links open in the default browser. The native bridge accepts messages only from that origin.
- The token never goes on a command line (on Linux it goes through a 0600 file) and is removed from the environment of terminal tabs.
- The web inspector exists only with `VULCAN_INSPECT=1`.

## Data

- Data folder 0700, files 0600. On Windows these modes have no effect, and the protection is that of the user profile (`%APPDATA%`).
- Anthropic key in the Keychain (macOS), Secret Service (Linux) or Credential Manager (Windows). On macOS and Linux it is always passed by stdin, never by argv. Never shown in the interface or written to a file.
- AI documentation happens only on click. A dialog first shows the size of the text and how many secrets were masked. Masking runs before the text is cut.
- `.env` files of projects are never opened.

## Agent folders

- Never written, with one exception: `--instalar-hook`, run by the user, with a backup. The hook script always exits with 0, so it cannot break Claude Code.
- Read as a stream, line by line. Lines above 5 MB are dropped and recorded.

## Code viewer

- `GET /api/code/*` only reads; there is no write route. A file must resolve, links included, inside the session folder. A session that ran in a folder containing the agents' data, such as the home folder, cannot be opened.
- Refused: above 1 MB, binaries, `.env*`, `*.pem`, `*.key`, `id_rsa*`, `credentials*`, and anything under `.git`, `.ssh`, `.aws` or `.gnupg`. The diff applies the same rules, because it holds the content.
- The repository being compared belongs to someone else, so nothing in it may run: the HEAD side comes from `git cat-file blob`, which skips `diff.external`, `textconv` and filters, and the current side is read directly.
- The index stores where each edit is in the session file, never the content. File content reaches the page as editor text, never as HTML.

## Optional GitHub lookup

Off by default, and with it off no command runs. If you turn on "Estado do PR pelo GitHub" in ⌘K, the app runs your own `gh pr view` in the session folder, at most once a minute per folder, only while the screen is visible. That call goes to GitHub with your own `gh` login. The app never asks for or stores a GitHub token, and never opens, merges or comments on a PR.

## Executing things

- Subprocesses are argv lists through `core/runner.py`.
- Git runs with `-c core.fsmonitor=false -c core.untrackedCache=false --no-optional-locks`. This is verified against real git: without it, `git status` ran a hook of the repository being analyzed.
- Python helpers run with `python -I` from a fixed working directory, so a hostile folder cannot plant a module. Verified by a test with fake `json.py` and `re.py`.
- Prompts are pasted using bracketed paste, with control characters removed, and **never with Enter**. Sending is refused (409) unless the tab is alive, the session is still the newest paired to it and the agent is in the foreground, so text cannot fall into a shell. Windows cannot tell which program is in the foreground, so there the tab being alive and paired is what counts.
- The interface escapes data it displays. It loads no external resource.

## Deleting

No permanent deletion in the code: folders go to the Trash, with confirmation by typing the name. A test scans the source.

## Accepted risks

| Risk | Why accepted |
|------|--------------|
| Another process of the same user can read the app's memory, or the Keychain item through `/usr/bin/security` | Outside the threat model; a limitation of the platform |
| The macOS app has only an ad hoc signature and is not notarized; the Windows package is not signed | Decision so far. Check downloads with `SHA256SUMS` |
| An agent or a site you run can do what your user can | The app shows what happened; it is not a sandbox |

Report a vulnerability: [SECURITY.md](../../SECURITY.md).
