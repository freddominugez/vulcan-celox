# Internal HTTP API

This API exists for the app's own interface. It is **not a public contract** and can change in any version. It is documented so you can debug and extend the app. The source of truth is the `@srv.route` declarations in `vulcan_terminal/server/`, and `tests/test_docs_api.py` fails when a route is missing from this page or listed here without existing.

See [security.md](security.md) for the threat model and [configuration.md](configuration.md) for environment variables.

## Calling it

```bash
export VULCAN_TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
python3 -m vulcan_terminal --serve     # prints VULCAN_PORT=<n>
curl -H "X-Vulcan-Token: $VULCAN_TOKEN" http://127.0.0.1:<n>/api/state

curl -X POST -H "X-Vulcan-Token: $VULCAN_TOKEN" -H "Content-Type: application/json" \
     -d '{"title": "Review the log"}' http://127.0.0.1:<n>/api/tasks
```

`--port <n>` picks the port; the default is a random free one. `VULCAN_TOKEN` must have at least 32 characters, or the server refuses to start. Without the variable the server generates a token and does not print it, so set it when you want to call the API by hand.

## General rules

Checks run in this order on every request:

1. **Host.** The server listens only on `127.0.0.1`. The `Host` header must be `127.0.0.1:<port>` or `localhost:<port>`, otherwise 421. This also applies to static files.
2. **Token.** Everything under `/api/` and `/ws/` needs the `X-Vulcan-Token` header, otherwise 401. A token in the query string is ignored on `/api/`. Only `/ws/` also accepts `?token=`, because a browser cannot set headers when opening a WebSocket.
3. **Origin.** If an `Origin` header is present, it must be `http://127.0.0.1:<port>` or `http://localhost:<port>`, otherwise 403. The server sends no CORS headers.
4. **JSON on writes.** `POST`, `PUT` and `PATCH` under `/api/` need `Content-Type: application/json`, otherwise 415, even when the route reads no body. `DELETE` does not need it and takes its parameters in the query string.

Bodies:

- An empty body counts as `{}`.
- A body must be a JSON object, otherwise 400. Invalid JSON is also 400.
- The limit is 1 MiB, otherwise 413.

Responses:

- Success is JSON with `Cache-Control: no-store`. The only exception is `GET /api/agents/usage.csv`, which is a CSV download.
- Errors are JSON: `{"error": "..."}`, with messages in Portuguese. Some errors add fields the interface needs, such as `needs_terminal`, `needs_confirmation`, `needs_parent`, `suggestion` or `missing`. Those fields are named in the tables below.
- Routes marked "command result" return `{"ok": bool, "code": int, "output": "..."}` with status 200, even when the command failed. Read `ok`, not the status. `output` holds the last lines of the output.
- Routes marked "tab" run a long command in a new terminal tab and return 201 with the terminal's description (`id`, `title`, `site`, `cwd`, `alive`, `theme`, `command` and others).

Static files: any path outside `/api/` and `/ws/` serves the interface, `GET` only and with no token. The files are read once when the server starts.

### Status codes

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 201 | Created, or a terminal tab was opened |
| 202 | Background job accepted (AI documentation) |
| 400 | Invalid parameter or body |
| 401 | Missing or invalid token, or a token only in the query string of `/api/` |
| 403 | `Origin` not allowed |
| 404 | Route or item not found |
| 405 | The path exists, but not with this method |
| 409 | State conflict, such as a prompt with no agent in the tab (`needs_terminal`) or no Lerd or Valet available |
| 410 | Nothing to undo |
| 413 | Body above 1 MiB |
| 415 | Write without `Content-Type: application/json` |
| 421 | `Host` not allowed |
| 500 | Internal error, or a system command failed |
| 502 | Lerd refused the operation |
| 503 | The tab did not read the pasted text |

### Path parameters

| Parameter | Accepted values |
|-----------|-----------------|
| `<sid>` in `/api/agents/sessions/` and `/api/debug/agent/` | Agent session id: starts with a letter or digit, then letters, digits, `.`, `_` or `-`, up to 80 characters |
| `<sid>` in `/api/sessions/` and `/api/ai/` | Terminal session id: lowercase hexadecimal |
| `<tid>`, `<nid>` | Terminal, tag, task or note id: lowercase hexadecimal |
| `<name>` in `/api/sites/` | Starts with a letter or digit, then letters, digits, `.`, `_` or `-`, up to 100 characters |
| `<name>` in `/api/node-projects/` | Starts with a lowercase letter or digit, then lowercase letters, digits, `.`, `_` or `-`, up to 64 characters |
| `<version>` | PHP: 3 or 4 characters of digits and dots, such as `8.4`. The `ini` routes also accept `shared`. Node: `22`, `20.11` or `lts` |

## Routes

### App

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/state` | App, backend, environment status, autostart, sites, favorites and progress | | |
| GET | `/api/app/build` | Version and fingerprint of the loaded and installed interface | | |
| PATCH | `/api/preferences` | Change preferences | `autostart_env` (bool), `new_terminal` (`skip_folder`, `agent`) | 400 |
| POST | `/api/open` | Open something outside the app | `kind`: `url`, `dashboard`, `finder`, `editor`, `prompt`, `source` or `file`; `target` | 400, 404, 409, 500 |
| GET | `/api/guide` | Steps of the start guide | | |
| PUT | `/api/guide` | Skip or restore the guide | `skipped` (bool) | 400 |
| GET | `/api/themes` | Tab themes, rotation, themes in use and terminal preferences | | |

`POST /api/open` limits each `kind`: `url` needs `http://` or `https://`; `finder` and `editor` need an existing folder, and `finder` refuses application packages; `prompt` opens only `.md` files from a prompts folder; `source` opens only files inside a registered site; `file` opens only `.md` files from the app's data folder.

### Agents

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/agents/revision` | Index revision, last scan and last error | | |
| GET | `/api/agents/sessions` | Session list with KPIs, projects and read folders | Query: `agent`, `project`, `cwd`, `active`, `unpublished` (`1` or `true`) | |
| GET | `/api/agents/sessions/<sid>` | Session detail, events, estimated cost and harness line | Query: `from` (default 0), `limit` (default 200, 1 to 1000) | 400, 404 |
| POST | `/api/agents/sessions/<sid>/resume` | Resume the session in a new tab | | 201, 404, 409 |
| GET | `/api/agents/history` | Search across session history | Query: `q`, `kind` (`pedidos`, `respostas`, `comandos`, `arquivos`), `agent`, `project`, `limit` (default 100, 1 to 500) | 400 |
| GET | `/api/agents/repos` | Git state of the projects, read-only, with a 30 second cache | Query: `fresh` (`1` or `true` clears the cache) | |
| GET | `/api/agents/paired` | Agent session paired with a tab | Query: `terminal` | |
| GET | `/api/agents/current` | Current session and prompt context | | |
| PUT | `/api/agents/current` | Choose the current session | `session_id` (text, or `null` for automatic) | 400, 404 |
| POST | `/api/agents/refresh` | Scan the session files now | | |

### Usage

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/agents/usage` | Tokens and estimated cost per group, with the total | Query: `from`, `to` (`YYYY-MM-DD`, local days; default is the last 30 days, maximum 400), `group` (`day` by default, `project`, `model`, `agent`, `session`) | 400 |
| GET | `/api/agents/usage.csv` | The same report as a CSV download | Same query, with `group` defaulting to `session` | 400 |

### Prompts

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/prompts` | Prompts rendered with a session's context | Query: `session`, `terminal`, `cwd`, `pinned` (`1` or `true`) | 404 |
| POST | `/api/prompts` | Create a prompt file | `title`, `category`, `scope` (`global` or `project`), `project_root`, `confirm_project_dir` | 400, 409 (`needs_confirmation`, `dir`) |
| POST | `/api/prompts/categories` | Create a category | `name`, `scope`, `project_root`, `confirm_project_dir` | 400, 409 (`needs_confirmation`, `dir`) |
| POST | `/api/prompts/send` | Paste a prompt into the tab paired with the session, without Enter | `prompt`, `session`, `values` (name to text) | 400 (`missing`), 404, 409 (`needs_terminal`, `session`), 503 (`terminal`) |

Project scope works only for the folder of a site, a saved Node project or an indexed agent session, and never for the agents' own data folders.

### Terminals

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/terminals` | Open tabs | | |
| POST | `/api/terminals` | Open a tab | `site`, `cwd`, `command`, `theme` (a name or `auto`), `agent` (`shell`, `claude` or `codex`), `title`, `rows`, `cols` (1 to 1000; default 24 by 80) | 201, 400, 404 |
| PATCH | `/api/terminals/<tid>` | Rename the tab | `title` (up to 60 characters) | 404 |
| DELETE | `/api/terminals/<tid>` | Close the tab and record its memory | | 404 |
| GET | `/api/terminals/<tid>/busy` | Whether the tab has child processes running | | 404 |
| GET | `/api/terminals/<tid>/public-url` | First tunnel URL in the output of a shared site's tab | | 404 |

The WebSocket for each tab is described in [WebSocket](#websocket).

### Terminal sessions

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/sessions` | Open and closed sessions | Query: `site` (`*` for all; empty is Global) | |
| GET | `/api/sessions/tree` | Sessions with their tasks and notes, for the sidebar | Query: `closed` (0 to 200, default 30) | 400 |
| GET | `/api/sessions/<sid>` | Session detail, last 200 commands and memory | | 404 |
| PATCH | `/api/sessions/<sid>` | Change title or tags | `title`, `tags` | 400, 404 |
| DELETE | `/api/sessions/<sid>` | Delete a closed session; memory and documentation go to the Trash | Query: `items` (`keep` by default, or `delete`) | 400, 404, 409 |
| GET | `/api/sessions/<sid>/doc` | Generated documentation of the session | | 404 |
| GET | `/api/index/general` | General index of the sessions, in Markdown | | |
| GET | `/api/index/documentation` | Generated general documentation | | 404 |

### Sites

Routes that need a backend return 409 when neither Lerd nor Valet is available. Every route with `<name>` returns 404 for an unknown site.

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/sites/suggest` | Suggest a domain from a folder | Query: `path` | |
| POST | `/api/sites` | Link a folder or park a parent folder (command result) | `kind` (`link` or `park`), `path` (absolute), `domain` (for `link`, without `.test`) | 400 (`suggestion`), 409 |
| POST | `/api/sites/trash` | Move the folder of a site already removed by the app in this run to the Trash | `name`, `confirm` (the exact name) | 400, 409 |
| PATCH | `/api/sites/<name>` | Change HTTPS (command result), or PHP or Node (tab) | One of: `secured` (bool), `php`, `node` | 201, 400, 404, 409 |
| GET | `/api/sites/<name>/versions` | PHP options, current values and what the backend writes to the project | | 404 |
| POST | `/api/sites/<name>/actions/<action>` | `db` or `doctor` (tab), `dashboard` (opens the panel) | | 201, 404, 409, 500 |
| PUT | `/api/sites/<name>/favorite` | Set or clear the favorite star | `favorite` (bool) | 400, 404 |
| POST | `/api/sites/<name>/share` | Public tunnel in a tab; closing the tab ends the tunnel | `tool` (optional; on Lerd: `cloudflare`, `expose`, `ngrok`, `localhost-run`, `serveo`, `pinggy`) | 201, 400, 404, 409 |
| POST | `/api/sites/<name>/remove` | Remove from the list, or unregister from the backend (command result) | `level` (`list` or `backend`), `parent` (confirms unparking a whole parent folder) | 400, 404, 409 (`needs_parent`) |
| GET | `/api/sites/<name>/runtime` | PHP and Node of the site, with a 30 second cache | | 404 |
| GET | `/api/sites/<name>/commands` | Project commands and custom commands | | 404 |
| POST | `/api/sites/<name>/commands` | Save a custom command | `command` (one line, up to 500 characters), `label` | 201, 400, 404 |
| DELETE | `/api/sites/<name>/commands` | Delete a custom command | Query: `command` | 404 |
| GET | `/api/sites/<name>/recent` | Last 20 commands from the site's tabs | | 404 |
| GET | `/api/sites/<name>/log` | `storage/logs/laravel.log` in chunks: the end of the file, or what came after an offset | Query: `offset` | 404 |
| POST | `/api/sites/<name>/lerd-logs/<target>` | Lerd logs in a tab | `<target>`: `php`, `nginx` or an installed service | 201, 404, 409 |

### Harness

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/sites/<name>/harness` | Contract, items, next step and handoff of the project, read-only | | 404 |
| GET | `/api/sites/<name>/harness/install` | Exact list of files an install would create; writes nothing | | 404, 409 |
| POST | `/api/sites/<name>/harness/install` | Install the minimal format. An existing file is never overwritten | `confirm` (must be `true`) | 400, 404, 409 |
| POST | `/api/sites/<name>/harness/tasks` | New contract in the minimal format, with approval pending | `task_id`, `itens` (each with `faixa`, `objetivo`, `sensor`), `objetivo`, `fora`, `escrita`, `orcamento` | 400, 404, 409 |

### Environment

Except for the first two rows, these routes need Lerd and return 409 without it.

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/environment` | Backend, components and services | | |
| POST | `/api/services/<action>` | Start, stop or restart the backend | `<action>`: `start`, `stop`, `restart` | 404, 409 |
| POST | `/api/environment/services/<name>/<action>` | Act on an installed service (command result) | `<action>`: `start`, `stop`, `restart` | 404, 409 |
| GET | `/api/environment/php` | Installed and installable PHP versions | | 409 |
| POST | `/api/environment/php/<version>/<op>` | `use` (command result), `update` or `install` (tab) | | 201, 400, 409 |
| GET | `/api/environment/xdebug` | Xdebug per version and its port | | 409 |
| POST | `/api/environment/php/<version>/xdebug` | Turn Xdebug on or off (tab) | `enabled` (bool), `mode` (`debug`, `coverage` or `debug,coverage`), `on_demand` (bool) | 201, 400, 409 |
| GET | `/api/environment/php/<version>/ini` | Values of the user `php.ini` | | 400, 409 |
| POST | `/api/environment/php/<version>/ini` | Change values (command result) | `values` (key to value; `null` or empty clears it) | 400, 409 |
| POST | `/api/environment/php/<version>/ini/open` | Open the `php.ini` in the user's editor (tab) | | 201, 400, 409 |
| GET | `/api/environment/php/<version>/extensions` | Loaded and declared extensions, read-only | | 400, 409 |
| GET | `/api/environment/node` | Default, manager and installed Node versions | | 409 |
| POST | `/api/environment/node/<version>/<op>` | `install` (tab), `use` or `remove` (command result) | `confirm` (must be `true` for `remove`) | 201, 400, 409 |

### Debug

These routes read the Lerd dump bridge and return 409 without Lerd, except for the last one.

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/debug/events` | Dump events | Query: `site`, `branch`, `kind`, `limit` (default 500, up to 2000), `q`, `min_ms`, `group` (`1` groups by request) | 409 |
| GET | `/api/debug/bridge` | Bridge state | | 409 |
| PUT | `/api/debug/bridge` | Turn the bridge on or off | `enabled` (bool) | 400, 409, 502 |
| POST | `/api/debug/clear` | Clear the events | | 409, 502 |
| GET | `/api/debug/agent/<sid>` | Exceptions and error logs of the session's site during the session. Returns `available: false` without Lerd or a matching site | | 404 |

### Node projects

The list belongs to the app: removing a project does not touch its folder.

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/node-projects` | Saved projects | | |
| POST | `/api/node-projects` | Add a folder with a `package.json` | `path` (absolute), `name` | 400, 409 |
| GET | `/api/node-projects/suggest` | Folders used by agents that have a `package.json` and are not on the list, up to 12 | | |
| GET | `/api/node-projects/<name>` | Project detail and running scripts | | 404 |
| POST | `/api/node-projects/<name>/run` | Run a `package.json` script in a tab | `script` | 201, 400, 404, 409 |
| POST | `/api/node-projects/<name>/stop` | Send Ctrl-C to a tab that runs a script of this project; the tab stays open | `terminal` | 404, 409 |
| POST | `/api/node-projects/<name>/supabase/<action>` | `supabase` command in a tab | `<action>`: `start`, `stop`, `status`. The project needs `supabase/config.toml` | 201, 400, 404, 409 |
| POST | `/api/node-projects/<name>/remove` | Remove from the list | | 404 |

### AI documentation

The key never leaves the server: responses show only a masked form. Nothing is sent to Anthropic except by these write routes.

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/ai/config` | Provider, masked key, model and available models | | |
| PATCH | `/api/ai/config` | Choose the model | `model` | 400 |
| PUT | `/api/ai/key` | Validate the key against Anthropic and save it | `key` | 400, 500 |
| DELETE | `/api/ai/key` | Delete the key | | |
| GET | `/api/ai/preview/session/<sid>` | Size and statistics of what would be sent for a session; sends nothing | | 404 |
| GET | `/api/ai/preview/general` | The same for the general documentation | | |
| POST | `/api/ai/docs/session/<sid>` | Generate a session's documentation in the background | | 202, 404, 409 |
| POST | `/api/ai/docs/general` | Generate the general documentation in the background | | 202, 409 |
| GET | `/api/ai/jobs` | Generation jobs and how many are running | | |

The 409 responses mean there is no key configured, a generation for the same item is already running, or (general documentation) there are no terminal sessions yet.

### Notebook

Unknown ids return 404. Invalid values return 400. In `site`, `*` means all sites, and empty or absent means Global.

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/tags` | Tags, palette, usage and progress | | |
| POST | `/api/tags` | Create a tag | `name`, `color` | 201, 400, 409 |
| PATCH | `/api/tags/<tid>` | Rename or recolor | `name`, `color` | 400, 404, 409 |
| DELETE | `/api/tags/<tid>` | Delete a tag from everywhere | | 404 |
| GET | `/api/notes` | Notes | Query: `site`, `q`, `tag`, `terminal` | |
| POST | `/api/notes` | Create a note | `text`, `color` (default `amarelo`), `tags`, `site`, `terminal` | 201, 400, 404 |
| PATCH | `/api/notes/<nid>` | Change a note | `text`, `color`, `pinned`, `terminal`, `tags` | 400, 404 |
| POST | `/api/notes/<nid>/move` | Reorder | `target` (a note id) or `index` | 400, 404 |
| DELETE | `/api/notes/<nid>` | Delete | | 404 |
| GET | `/api/tasks` | Tasks, progress, summary and `can_undo` | Query: `site`, `status` (comma list of `todo`, `doing`, `done`), `tag`, `sort` (`priority`, `due`, `manual`, `assignee`), `terminal`, `assignee`, `due` (`late`, `today`, `week`) | |
| GET | `/api/tasks/assignees` | Assignees with open and total counts | | |
| POST | `/api/tasks` | Create a task | `title`, `priority` (default 2), `tags`, `due` (`YYYY-MM-DD`), `terminal`, `assignee`, `site` | 201, 400, 404 |
| PATCH | `/api/tasks/<tid>` | Change a task | `title`, `priority`, `due`, `status`, `assignee`, `terminal`, `tags` | 400, 404 |
| POST | `/api/tasks/<tid>/cycle` | Move to the next status | | 404 |
| POST | `/api/tasks/<tid>/move` | Reorder | `delta` | 400, 404 |
| DELETE | `/api/tasks/<tid>` | Delete; can be undone | | 404 |
| POST | `/api/tasks/undo` | Undo the last delete | | 410 |
| GET | `/api/progress` | Overall progress, per site and per tag | | |
| GET | `/api/search` | Search sites, tasks, notes and tags | Query: `q` | |
| GET | `/api/index` | Global task index in Markdown | | |
| GET | `/api/index/project` | A project's task block and whether it is enabled | Query: `site` | |
| POST | `/api/index/project` | Turn on or off writing the task index in the project folder | `site`, `enabled` | 400, 404 |

### Files

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| GET | `/api/fs/folder` | Check a typed folder; accepts `~` | Query: `path` | 400 |
| GET | `/api/fs/recent` | Home folder and up to 12 recent folders | | |

## WebSocket

| Method | Path | Purpose | Parameters or body | Notable status |
|--------|------|---------|--------------------|----------------|
| WS | `/ws/terminals/<tid>` | Input and output of a terminal tab | Query: `token` (or the `X-Vulcan-Token` header) | 101, 400, 401, 403, 404 |

The handshake needs `Upgrade: websocket`, `Sec-WebSocket-Version: 13` and `Sec-WebSocket-Key`, otherwise 400. An unknown tab returns 404.

| Direction | Frame | Content |
|-----------|-------|---------|
| Server to client | Binary | Terminal output. History arrives first, before any new output |
| Server to client | Text | `{"type": "exit", "code": <n>}` when the process ends. It is also sent on connection if the process has already ended |
| Client to server | Binary | Terminal input |
| Client to server | Text | `{"type": "input", "data": "..."}`: terminal input as text |
| Client to server | Text | `{"type": "resize", "rows": <n>, "cols": <n>}`: 1 to 1000 rows and columns; other values are ignored |

Text frames that are not a JSON object, or that have another `type`, are ignored. A message is limited to 16 MiB. A client that falls more than 4 MiB behind in receiving is disconnected, so it cannot hold up the terminal or the other clients.
