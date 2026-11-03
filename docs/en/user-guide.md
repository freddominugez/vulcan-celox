# Vulcan Celox manual

> Screen names stay in Portuguese because the interface is in Portuguese: this guide shows the Portuguese name you see in the app. This is a translation of [the Portuguese manual](../pt-BR/user-guide.md), which has the same content as the app's Ajuda (Help) screen (⌘?).

## Contents

- [First steps](#primeiros-passos): What Vulcan Celox does and how to get started in four steps.
- [PHP sites](#projetos-php): Lerd sites: opening them, changing PHP, HTTPS, logs and terminal.
- [Lerd](#lerd): The environment that runs PHP, nginx, the database and HTTPS for the sites.
- [Node projects](#node): Next.js, Vite, local Supabase and the Vercel link.
- [Terminals and sessions](#terminais): Tabs, the bottom panel and the memory of each session.
- [Debugging and logs](#depuracao): Dumps, queries, exceptions and laravel.log.
- [Agents](#agentes): Claude Code and Codex sessions read from disk.
- [Usage and cost](#custo): Tokens and estimated cost by day, project, model and session.
- [Prompts](#prompts): Ready-made instructions you send to the agent with one click.
- [Harness](#harness): The contract, items and handoff that agents follow.
- [Tasks, post-its, tags and index](#organizar): What gets recorded for each project.
- [Keyboard shortcuts](#atalhos): The shortcuts that save the most time.
- [Security and privacy](#seguranca): What the app reads, what it writes and what it never does.
- [Frequently asked questions](#perguntas-frequentes)

<a id="primeiros-passos"></a>

## First steps

The app comes in light and dark. ⌘K, "Tema", picks System, Light or Dark. The terminal area stays dark in both, with each tab's color.

*What Vulcan Celox does and how to get started in four steps.*

Vulcan Celox is a panel for people who program alone with code agents. It brings together in one place the PHP sites that **Lerd** runs on your Mac, your Node projects (Next.js, Vite and the like), the terminals of each project and the sessions of **Claude Code** and **Codex**.

![Visão geral (Overview) with PHP sites, a Node project, tasks and the terminal panel](../../vulcan_celox/web/img/manual/visao-geral.png)

1. **Start Lerd.** The green dot at the top right, and on the Lerd item in the sidebar, shows that nginx, `.test` DNS and PHP are responding. Without Lerd, Node projects and agents work just the same.
2. **Find your projects.** Sites registered in Lerd appear on their own. Node projects come in through the + of the Projetos Node (Node projects) section, or through suggestions taken from the folders where your agents worked.
3. **Let the app read the agent sessions.** It reads the Claude Code and Codex files from disk, line by line, with no API key and without writing anything to those folders.
4. **Open a terminal in a project** with ⌘T. Tasks, post-its and tags created in it become the session's Markdown memory when the terminal closes.

The **Início** (Start) screen checks these steps by itself and stops appearing when the app opens once all four are done. Tick **Não mostrar mais o guia** (Do not show the guide again) to make the app open directly on Visão geral (Overview). The guide remains available from the Início item in the sidebar.

<a id="projetos-php"></a>

## PHP sites

*Lerd sites: opening them, changing PHP, HTTPS, logs and terminal.*

Each Lerd site appears on Visão geral (Overview) and in the Sites section of the sidebar, with its `.test` domain, PHP version and HTTPS. Clicking a site opens its page, with tabs for terminal, tasks, post-its, logs, debugging and harness.

- **Add a site:** the + of the Sites section links a folder to a domain (`lerd link`) or registers a folder full of projects (`lerd park`). Lerd writes `.php-version` in the folder when registering it.
- **Change the site's PHP, HTTPS or Node:** on the site's page. Actions that build an image run in a terminal tab, with the output in view.
- **Share:** opens a public tunnel and shows the address when it appears in the output.
- **Remove:** taking a site off the app's list deletes nothing. Deleting the folder sends it to the Trash, never permanently.

The sites belong to Lerd. The app only calls Lerd's own CLI and API and never edits its global files.

<a id="lerd"></a>

## Lerd

*The environment that runs PHP, nginx, the database and HTTPS for the sites.*

**Lerd** is an open source PHP development environment (MIT license). It runs nginx, PHP-FPM, DNS for `.test`, a database and HTTPS certificates in containers, without you configuring a web server by hand. Vulcan Celox is the panel on top of it.

![Lerd screen with components, services and PHP versions](../../vulcan_celox/web/img/manual/lerd.png)

- **Lerd item in the sidebar:** the dot shows the state (green running, pink stopped, gray absent). The screen has Ligar (Start), Parar (Stop) and Painel do Lerd (Lerd panel).
- **Services:** database, Redis and others, with start and stop.
- **PHP:** installed versions, extensions, Xdebug and six common php.ini settings, written by `lerd php:ini` itself.
- **Lerd's Node:** versions that Lerd manages for PHP sites with a JavaScript front end.
- **Start with the app:** the lightning bolt button, at the top, starts Lerd together with Vulcan Celox.

Laravel Valet also works as an alternative. Herd is commercial and is not used.

<a id="node"></a>

## Node projects

*Next.js, Vite, local Supabase and the Vercel link.*

Node projects do not use Lerd. The app reads `package.json`, finds the package manager from the lockfile (pnpm, npm, yarn or bun), the framework from the dependencies and the likely port, and shows local Supabase and the Vercel link.

![Page of a Next.js project with scripts, local Supabase and project data](../../vulcan_celox/web/img/manual/node-projeto.png)

1. Click the + of the **Projetos Node** (Node projects) section and choose the root folder, where `package.json` is. Nothing is written to it.
2. On the project page, **Rodar** (Run) opens a terminal tab and types `pnpm run dev` (or the project's package manager). The tab appears in the bottom panel.
3. When the server shows its local address, the **Abrir no navegador** (Open in browser) button appears.
4. **Parar** (Stop) sends Ctrl-C to the project's own tab. The tab stays open with the output.

- **Local Supabase:** with `supabase/config.toml` in the project, the buttons run `supabase start`, `status` and `stop` in a terminal, and Abrir Studio (Open Studio) takes you to the local dashboard.
- **Vercel:** the app only shows whether the folder is linked (`.vercel/project.json`). Deploys and logs stay in the Vercel dashboard or in the `vercel` command in the terminal.
- The app never opens the project's `.env` and does not talk to Vercel or to remote Supabase.

<a id="terminais"></a>

## Terminals and sessions

*Tabs, the bottom panel and the memory of each session.*

Each terminal is a session. It opens in the chosen folder, with a color theme that identifies the session, and can start with Claude Code or Codex already running.

- **⌘T** opens a new terminal; **⌘J** shows or hides the bottom terminal panel, which follows you across all screens.
- The project's **quick commands** (composer, artisan, npm) are on the terminal bar.
- **Memory:** when a terminal closes, its commands, tasks, post-its and tags become a Markdown file, which appears in Sessões recentes (Recent sessions) and in Índice (Index).
- **Destacar (Detach):** a tab can become its own window and come back later.

<a id="depuracao"></a>

Tabs show the ports their processes opened, such as `:5173 +2`, in the tab bar and in the session list. A click opens `http://localhost:<port>` in your browser. Only the tab's own processes count.

## Debugging and logs

*Dumps, queries, exceptions and laravel.log.*

The **Depuração** (Debugging) screen (⇧⌘E) shows what arrives through Lerd's dump bridge: `dump()`, queries, logs and exceptions, grouped by request, with a warning for repeated queries. The site's Logs tab reads `storage/logs/laravel.log` by level.

In an agent's session, the **Depuração no período** (Debugging in the period) panel shows only what happened while the agent was working, with a summary that can be copied and that first goes through a secret cleanup.

<a id="agentes"></a>

## Agents

*Claude Code and Codex sessions read from disk.*

The **Agentes** (Agents) screen lists the Claude Code and Codex sessions on this machine, with project, branch, last request, files touched and state (active, stopped, in a loop). Clicking a session opens its timeline.

![List of agent sessions with project, branch and activity](../../vulcan_celox/web/img/manual/agentes.png)

- **Histórico de agentes (Agent history):** searches everything the agents did, by text, file or command.
- **Branches e worktrees (Branches and worktrees):** which branch each agent is working on, so work does not get mixed up.
- **Retomar (Resume):** opens a terminal in the session's folder with the agent's resume command already in place.
- **⌘-click a path in the terminal:** `a/b.py`, `./b.py`, `/abs/b.py`, `b.py:12`, `b.py:12:3` and `b.py(12)` become links while ⌘ is held, only if the file exists inside a known folder. With a paired session the file opens in the Código tab at that line; without one, in your editor; a folder opens in Finder. Relative paths count from the session folder, or from the folder the tab opened in: after a `cd`, a relative path may not resolve.
- **Jump between requests:** ⌘⇧↑ and ⌘⇧↓. In the terminal, each Enter in a tab with a live agent becomes a mark, and nothing is drawn on the screen. If the agent uses the terminal's full screen there is no history to navigate, and the app says so once. In the session, **Linha do tempo** groups by request, with files and commands, and each edited file links to the diff of that request.
- **Código tab:** inside a session, the files the agent touched, each one with syntax highlighting or as a diff: of one edit, of a whole request or against the last commit. In an active session the viewer follows the agent; scrolling, clicking or selecting pauses it, and **Voltar a seguir** resumes. It only reads: nothing is edited in the app, and binaries and sensitive names such as `.env` are not shown.
- **PR state:** by default the app estimates it from the session's commands, and says so. Turn on "Estado do PR pelo GitHub" in ⌘K to read number, draft, state and checks with your own `gh`. This one uses the network.
- **Pairing:** the terminal that opened an agent stays linked to its session, so prompts come out filled in. On Codex the link is by folder and time: two sessions opened almost together in the same folder can still swap tabs. Subagents and the Codex desktop app do not link to tabs.

The app only reads these files, line by line. It never writes to `~/.claude` or `~/.codex`. The only exception is the pairing hook, which you install on purpose with `--instalar-hook`, and which keeps a backup.

<a id="custo"></a>

## Usage and cost

*Tokens and estimated cost by day, project, model and session.*

The **Uso e custo** (Usage and cost) screen adds up the tokens each agent turn spent and estimates the cost at each model's public API price, by day, project, model and session. The Copiar CSV (Copy CSV) button takes the numbers to a spreadsheet.

![Uso e custo with bars per day split by agent and tables by project](../../vulcan_celox/web/img/manual/uso-e-custo.png)

The value is an **estimate at the API price**. People on a subscription plan pay a different amount. A model with no known price appears with no cost, never as zero. Prices can be changed in the `precos.json` file in the app's data folder.

<a id="prompts"></a>

## Prompts

*Ready-made instructions you send to the agent with one click.*

Prompts are instructions you always send to the agent: working in small steps, reviewing before the commit, the limits of the task. Each card says what the prompt does and shows the data it uses, such as **Branch: main**, already filled in from the current session.

1. **Click the card.** The composer opens alongside, with one field for each value (project, branch, folder, session) and a preview of the text with the values highlighted.
2. **Check or adjust the fields.** The preview changes as you type. An empty field appears in amber and blocks sending until it is filled in.
3. **Click Enviar ao terminal** (Send to terminal), or press ⌘Enter. The text enters the agent's field as a paste, **without pressing Enter**: check it in the terminal and send it yourself.
4. **With no paired terminal, or with the agent already closed in that tab,** the text is not pasted, so it does not land in the shell. The composer offers to resume the session in a terminal. Copiar (Copy) remains available for pasting elsewhere with ⌘V.

![Prompts screen with cards and the composer open](../../vulcan_celox/web/img/manual/prompts.png)

- Global prompts live in the app's data folder; project prompts live in `.vulcan/prompts` inside the project and override the global one with the same id. The paths appear in the Novo prompt (New prompt) dialog.
- In the file header, `descricao` sets the card text and `icone` the icon. Without `descricao`, the card uses the first sentence of the prompt.
- Pinned prompts (`pin: true`) appear on the terminal bar. In the tab paired with an agent, one click pastes the text, also without Enter.

<a id="harness"></a>

## Harness

*The contract, items and handoff that agents follow.*

The harness is the contract with verifiable items, the execution state and the handoff that agents read to resume work. Each site's **Harness** tab shows the active contract, the item bar (done, in progress, blocked, pending), the next item and the last green commit.

![Harness tab with the item bar, a blocked item and the handoff](../../vulcan_celox/web/img/manual/harness.png)

- **Copiar prompt de retomada (Copy resume prompt):** ready-made text for the agent to continue from the right item.
- **Instalar harness (Install harness):** in a project with no harness, creates the minimal format after showing the exact list of files. Nothing is overwritten; an existing `CLAUDE.md` or `AGENTS.md` only gets a marked block.
- **Novo contrato (New contract):** a form that writes `.vulcan/tasks/<id>.md`, always with APROVAÇÃO (approval) pending until you approve it in the file.

<a id="organizar"></a>

## Tasks, post-its, tags and index

*What gets recorded for each project.*

- **Tarefas (Tasks):** per site or global, with due date and state. Open ones appear on Visão geral (Overview).
- **Post-its:** quick notes, per site or global.
- **Tags:** mark sessions, tasks and notes so you can find them later.
- **Índice (Index):** all session memories in Markdown, with search. AI documentation is optional, by click only, and uses your own Anthropic key stored in the Keychain.

<a id="atalhos"></a>

## Keyboard shortcuts

*The shortcuts that save the most time.*

| Shortcut | Action |
|----------|--------|
| `⌘K` | Search sites, projects, tasks and commands |
| `⌘T` | New terminal |
| `⇧⌘T` | New terminal, asking for the folder |
| `⌘J` | Show or hide the terminal panel |
| `⌘F` | Search in the terminal |
| `⇧⌘P` | Prompts |
| `⇧⌘E` | Depuração (Debugging) |
| `⌘1 to ⌘5` | Visão geral (Overview), Terminais (Terminals), Tarefas (Tasks), Post-its and Tags |
| `⌘?` | Ajuda (Help) |

<a id="seguranca"></a>

## Security and privacy

*What the app reads, what it writes and what it never does.*

- The internal server only answers on `127.0.0.1`, with a per-run token. Nothing is exposed on the network.
- Agent sessions: read only, line by line. The app never writes to `~/.claude`, `~/.codex` or their configuration files, except for the pairing hook you install on purpose, with a backup.
- Nothing is permanently deleted: a removed folder goes to the Trash.
- In a project folder, the app only writes with your confirmation and inside a marked block.
- The projects' `.env` is never opened.
- The Anthropic key, if you register one, stays in the Keychain and is only used when you click to document a session.

<a id="perguntas-frequentes"></a>

## Frequently asked questions

**What is Lerd for?**

It is the environment that runs your PHP and Laravel sites on your Mac: `.test` domain, a PHP version per project, database and local HTTPS, without configuring a server by hand. Vulcan Celox is the panel on top of it.

**Do I need Lerd to use the app?**

No. Without Lerd or Valet the app opens in local mode: Node projects, terminals, agents, prompts, tasks and notes all work. Only the PHP sites part is limited.

**My project is Next.js with Supabase and Vercel. Does the app help?**

Yes. Add the folder under Projetos Node (Node projects): the app starts and stops the development server in a visible terminal, shows the port, runs `supabase start` and `stop`, and indicates whether the folder is linked to Vercel.

**Lerd is stopped. How do I start it?**

Click Ligar (Start) on the Lerd screen, or the play button at the top. The first time can take up to a minute, because Lerd brings up its containers. To always start it together with the app, use the lightning bolt button.

**I clicked Rodar (Run) and saw nothing.**

The script runs in a tab of the bottom terminal panel. If the panel is hidden, press ⌘J. The tab has the name of the project and the script.

**The server says the port is already in use.**

Another process is using the same port, often an old forgotten `dev`. Stop the script from the project page or close the old tab. The app does not kill processes by port: it only sends Ctrl-C to the project's own tabs.

**Does the app write to the Claude Code or Codex folders?**

No. It only reads the sessions, line by line. The only exception is the pairing hook, which you install on purpose with `--instalar-hook`, and which keeps a backup of the original file.

**Is the cost shown what I paid?**

No. It is an estimate at each model's public API price. People on a subscription plan pay a different amount. A model with no price appears with no cost, never as zero.

**How do I change a model's price?**

Edit `precos.json` in the app's data folder (`~/Library/Application Support/VulcanCelox/`). The value in the file takes precedence over the built-in table.

**An agent does not appear in the list.**

The app reads Claude Code and Codex. Compressed Codex sessions (`.jsonl.zst`) are read when the `zstd` command is installed; without it, they are left out and `--doctor` counts how many there are. Gemini and Cursor are not among the agents read for now.

**Why does a prompt field appear in amber?**

That value is missing from the current session, for example the branch. Fill in the field in the composer or choose another session in Trocar sessão (Change session). While any field is empty, Enviar ao terminal (Send to terminal) stays blocked.

**Where are the prompts stored?**

`.md` files: global ones in the app's data folder and project ones in `.vulcan/prompts` inside the project. The exact paths appear in the Novo prompt (New prompt) dialog.

**What happens when I close a terminal?**

Its commands, tasks, post-its and tags become a Markdown memory file. It appears in Sessões recentes (Recent sessions), on Visão geral (Overview), and in Índice (Index).

**I removed a site by mistake. Did I lose the folder?**

No. Taking it off the list deletes nothing. Even when you ask to delete the folder, it goes to the Mac's Trash and can be restored.

**What is the harness?**

It is the contract agents follow: items with a sensor, the execution state and the handoff. The Harness tab shows which item the work is on and what is blocked.

**Does installing the harness touch my files?**

Only with your confirmation, and after showing the exact list. An existing file is never overwritten; `CLAUDE.md` or `AGENTS.md` only gets a marked block, which can be replaced later.

**How do I see the Início (Start) guide again?**

Click Início in the sidebar. To make it open with the app again, untick Não mostrar mais o guia (Do not show the guide again).

**I opened it in the browser and it asks for a token.**

The interface needs the token the native app creates on each run. Open it through Vulcan Celox, from the Desktop shortcut or in Applications.

**Does a prompt sent to the terminal run right away?**

No. The text enters the agent's field as a paste and nothing is sent by itself. You review it in the terminal and press Enter.
