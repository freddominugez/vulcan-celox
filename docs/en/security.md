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
- Session memory is masked when saved, with `[secret]` in English and `[segredo]` in Portuguese (both spellings count as already masked), before the 2,000 line cut, using the same patterns as AI documentation. Input typed with echo off in canonical mode, which is what `sudo`, `ssh` and `getpass` use, is left out of the command list. Windows does not expose that mode, so there it is still recorded. Patterns can miss an unusual secret.
- Not masked: `notes.json` and `tasks.json`, which hold your own editable text, and `agentes.db`, which indexes what is already in the agent JSONL files. Memories saved before this change stay as they are until you use **Mask** in Settings.
- A backup is a `.zip` with mode 0600, not encrypted. It holds everything in the data folder except temporary files, `logs/` and `.restauros/`, and it does not hold the Anthropic key. Restoring refuses absolute paths, `..`, links, the app's own reserved names, an unknown format and a size above the free disk space. The swap happens on the next start, once the previous instance has left (on Windows it does not wait), and the previous data moves to `.restauros/`. If the swap fails, the app opens with the data as it is and says so.
- Before restoring, **Check** reads the zip without extracting anything (`POST /api/data/backup/inspect`) and shows date, version, size and counts. A zip with more than 20 thousand members or more than 2 GB uncompressed, adding up the sizes it declares, is refused without being checked. Restore only shows up when nothing would be refused.
- Copies in `.restauros/` leave through the screen only to the Trash, and only with a listed name in the date format. Links and names off the list get 400.
- The server log (`logs/servidor.log`, 1 MB and 3 files) and the process error output (`logs/servidor-erro.log`) have mode 0600, go through the mask line by line and never hold the session token, which becomes `[token]`. Nothing leaves the machine.
- The new version check is on by default, at most once a day. It sends one `GET` to the GitHub API with the app version in the `User-Agent`. If that fails, for example while the repository is private, it runs your own `gh api` for the same address, with your `gh` login. The link it shows must be a release page of this repository. It never downloads or installs anything. Turn it off in Settings or with `VULCAN_UPDATE_CHECK=0`.

## Agent folders

- Never written, with one exception: `--instalar-hook`, run by the user, with a backup. The hook script always exits with 0, so it cannot break Claude Code.
- Read as a stream, line by line. Lines above 5 MB are dropped and recorded.


## Code viewer

- `GET /api/code/*` only reads; there is no write route. A file must resolve, links included, inside the session folder. A session that ran in a folder containing the agents' data, such as the home folder, cannot be opened.
- Refused: above 1 MB, binaries, `.env*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_dsa*`, `id_ecdsa*`, `id_ed25519*`, `credentials*`, `.netrc`, `.git-credentials`, `.npmrc`, `.pypirc`, `auth.json`, `secrets.*`, and anything under `.git`, `.ssh`, `.aws` or `.gnupg`. The diff applies the same rules, because it holds the content.
- The repository being compared belongs to someone else, so nothing in it may run: the HEAD side comes from `git cat-file blob`, which skips `diff.external`, `textconv` and filters, and the current side is read directly.
- The index stores where each edit is in the session file, never the content. File content reaches the page as editor text, never as HTML.


## Code screen

- `/api/files/*` only reads: the one write route adds or removes a folder from the app's own list, `code_roots.json`, with at most 50 chosen folders. Removing one deletes nothing.
- A folder opens only if the app knows it (site, Node project, session) or you chose it. The whole home folder, the root of the disk, the app's data folder and any folder inside or containing the agents' data are refused.
- A path comes relative to the folder. Absolute paths and `..` are refused. Symbolic links appear in the tree and are not followed, and a file link that resolves out of the folder is refused. `.git` is hidden. The file rules are the same as the Code viewer's.
- The repository being read belongs to someone else, so nothing in it may run. A test creates a repository whose `filter`, `core.fsmonitor`, `textconv`, `diff.external`, `core.sshCommand` and `remote.*.uploadpack` point to programs, including a real partial clone, and fails if any of them runs: `git status`, `git diff` on the worktree and `ls-files -m` do run them, so they are not used. The only commands used are `ls-files -o -i`, `ls-files -s --debug`, `ls-files -o --directory`, `grep --no-textconv`, `rev-parse`, `symbolic-ref` and `cat-file blob`.
- Git marks (`GET /api/files/git`) compare the index with `lstat`, without reading content, so a file that was only touched counts as changed. git runs again only when the sweep sees a change or every 30 s, with a budget of 20 thousand entries.
- Live marks come from comparing `os.scandir` photos of the disk: no content is read. A file name is data and goes into the tree as text.

## Optional GitHub lookup

Off by default, and with it off this option runs no command. If you turn on "Check the PR state on GitHub" in Settings or in ⌘K, the app runs your own `gh pr view` in the session folder, at most once a minute per folder, only while the screen is visible. That call goes to GitHub with your own `gh` login. The app never asks for or stores a GitHub token, and never opens, merges or comments on a PR.

## Executing things

- Subprocesses are argv lists through `core/runner.py`.
- Git runs with `core.fsmonitor=false`, `core.untrackedCache=false`, `--no-optional-locks` and every transfer protocol set to `never`, by name. The last one stops a partial clone from fetching a missing object by itself, which would run `core.sshCommand` or `remote.*.uploadpack`. `git status` is not used anywhere: it runs the `clean` filter and no option turns that off. The Branches screen counts changed files by comparing size and date with the index, so a file that was only touched counts as changed.
- Python helpers run with `python -I` from a fixed working directory, so a hostile folder cannot plant a module. Verified by a test with fake `json.py` and `re.py`.
- Prompts are pasted using bracketed paste, with control characters removed, and **never with Enter**. Sending is refused (409) unless the tab is alive, the session is still the newest paired to it and the agent is in the foreground, so text cannot fall into a shell.
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
