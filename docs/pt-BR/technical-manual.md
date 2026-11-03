# Vulcan Celox: manual técnico

Referência para quem desenvolve e nunca viu este projeto. Descreve a versão 1.0.0. Para um passeio mais curto, leia [architecture.md](architecture.md).

Caminhos escritos como `core/...`, `server/...`, `web/...` e `ui/...` são relativos a `vulcan_celox/`.

## 1. Visão geral e objetivos

O Vulcan Celox é um painel desktop para quem desenvolve sozinho com agentes de código e projetos locais em PHP/Laravel e Node. Ele reúne:

1. **Gestão de ambiente**: sites `.test` locais, TLS, versões de PHP e Node, serviços, compartilhamento, logs e dumps, pelo Lerd ou pelo Laravel Valet.
2. **Terminais por projeto**: PTYs reais com saída ao vivo, histórico, comandos rápidos e uma memória em Markdown de cada sessão.
3. **Painel de agentes**: lê os arquivos de sessão do Claude Code e do Codex, sem chave de API, e mostra sessões, arquivos, comandos, estado de publicação, tokens, custo estimado e busca no histórico.
4. **Caderno do projeto**: post-its, tags, tarefas com progresso e um índice Markdown das tarefas gerado automaticamente.
5. **Aba Harness**: mostra em que ponto do contrato de um projeto os agentes estão, a partir de arquivos desse projeto.
6. **Documentação com IA**: só por clique, com a chave da Anthropic do próprio usuário.

Objetivos que moldam o código:

- Nada a instalar além do Python 3.9. Sem pip, sem npm, sem etapa de build para a interface.
- Não abrir porta nova na máquina: o servidor escuta só em `127.0.0.1` e exige token. Veja [security.md](security.md).
- Nunca escrever nas pastas dos agentes, salvo um comando rodado pelo usuário.
- Nunca apagar nada de forma definitiva.
- Tudo testável sem janela, sem Lerd real e sem agentes reais.

Estado da entrega: a 1.0.0 sai para macOS 13 ou mais novo, Apple Silicon e Intel. O código de Linux continua no repositório e no CI, mas nenhum pacote de Linux é publicado até passar no aceite em um desktop real.

## 2. Decisões de arquitetura

Estas decisões valem como regra. Várias são garantidas por testes.

| # | Decisão | Motivo |
|---|---------|--------|
| D1 | **Núcleo em Python 3.9 só com a biblioteca padrão, casca nativa em Swift (WKWebView), interface web sem build.** Nenhuma dependência pip. A interface tkinter fica como reserva. | Roda no Python que o Mac já tem, nas duas arquiteturas, sem instalar nada. O código precisa ser compatível com 3.9: sem `match`, sem `X \| Y` em anotações de runtime. |
| D2 | **Orquestrar, não reimplementar.** Lerd (github.com/lerd-env/lerd) ou Laravel Valet, ambos MIT, são os backends, nesta prioridade. Sem nenhum dos dois, o app roda em modo local. | Compilar PHP, nginx e DNS está fora do alcance. O Herd é produto comercial e nunca é backend. No modo local, post-its, tags, tarefas e o índice continuam funcionando. |
| D3 | **Não alterar serviços do sistema.** O app nunca edita arquivos globais dessas ferramentas. | Ele só chama a CLI ou a API delas, ou escreve nas próprias pastas. Toda escrita em pasta de projeto é opt-in e reversível. |
| D4 | **Núcleo sem tkinter.** `core/` não importa tkinter. | Toda a lógica (parsers, store, runner, Markdown, progresso) pode ser testada com `unittest`, sem janela. `tests/test_arquitetura.py` garante isso. |
| D5 | **Subprocesso só por `core/runner.py`.** Comandos são listas argv. | Testável com `FakeRunner`, e nenhum valor é interpretado por shell. A única exceção é o texto livre do terminal, que roda explicitamente como `<shell> -lc` por `run_shell`. Um teste recusa `import subprocess` em qualquer outro lugar. |
| D6 | **Persistência JSON atômica.** `tempfile` mais `os.replace`, campo `schema_version`, e arquivo corrompido vira `*.corrupt-<timestamp>` enquanto o app sobe com o padrão. | Uma queda ou um disco cheio nunca deixa arquivo pela metade, e um arquivo ruim nunca impede a abertura. |
| D7 | **Nada é apagado de forma irreversível.** Pastas vão para a Lixeira, com confirmação digitando o nome. | `shutil.rmtree`, `rm -rf` e parecidos são proibidos, e um teste varre o fonte e os scripts. |
| D8 | **Sensores só de biblioteca padrão e ferramentas do sistema.** `compileall`, `unittest`, `plutil`, `swiftc`, `--selftest` e `--snapshot`, orquestrados por `scripts/validate.sh`. | Sem framework de teste nem ferramenta externa para instalar. |
| D9 | **Implementação própria, sem copiar ativos do Herd.** | O Herd é proprietário: nada de binários, extensões `.so`, ícones ou textos dele no repositório. O Valet é MIT e pode ser consultado. |

## 3. Estrutura do repositório

Confira a qualquer momento com `git ls-files`.

```
packaging/macos/main.swift   casca macOS: WKWebView, janelas, menus, item na barra de menu, servidor filho, --snapshot, --eval
packaging/macos/AppIcon.icns   ícone do app, do kit da marca; o build só copia
packaging/linux/             lançador, script de dependências, entrada .desktop, ícones, controle do .deb, instalar e desinstalar
packaging/LEIA-ME.md         instruções de instalação que vão dentro dos pacotes
vulcan_celox/
  __main__.py                linha de comando do pacote Python
  desktop_linux.py           casca Linux: GTK 3 + WebKit2GTK, Chromium --app ou navegador
  core/                      lógica sem interface
  core/agents/               sessões de agente: descoberta, leitores, índice, observador, pareamento, uso
  core/backends/             Lerd, Valet e modo local
  server/                    servidor HTTP e WebSocket, um módulo por área da API
  web/                       interface sem build: index.html, styles/, js/, js/views/, help/, img/, vendor/
  ui/                        interface tkinter antiga, só reserva (--selftest e padrão do ponto de entrada Python)
scripts/                     validate.sh, test_linux.sh, build_app.sh, install_app.sh, package.sh, package_linux.py,
                             make_deb.py, manual_md.py, manual_shots.sh, help_json.py
tests/                       suíte unittest, fixtures/, golden/, tools/ (Lerd falso)
docs/en/, docs/pt-BR/        documentação pública, mesmas páginas nas duas línguas
.github/                     modelos de issue e pull request, workflow de Linux
```

`dist/`, `build/` e `executaveis/` são saída de build e ficam fora do git.

## 4. Execução e modelo de processos

No macOS o app são dois processos: a casca Swift e um servidor Python filho. No Linux o servidor roda dentro do próprio processo da casca.

```
Casca Swift (AppKit + WKWebView)
   | inicia com VULCAN_TOKEN no ambiente, lê VULCAN_PORT=<n> do stdout
   v
python3 -m vulcan_celox --serve   <--- JSON + WebSocket --->   interface web dentro da WKWebView
   |
   +-- threads: HTTP por conexão, uma leitora por PTY, uma de envio por cliente WebSocket,
   |            observador de agentes, gravação de memórias, início do ambiente, tarefas de IA
   +-- filhos: shell em PTY por aba, lerd, valet, git, zstd, security
```

### Início no macOS

1. `applicationDidFinishLaunching` procura um Python utilizável: `VULCAN_PYTHON` se definido, depois (a menos que `VULCAN_PYTHON_ONLY=1`) `/opt/homebrew/bin/python3`, `/usr/local/bin/python3` e `/usr/bin/python3`. O candidato precisa ser 3.9 ou mais novo. `/usr/bin/python3` só é tentado se `xcode-select -p` der certo, porque sem as Command Line Tools ele é um atalho que abre o instalador da Apple. Sem Python, o app explica, oferece instalar e sai com 1.
2. `BackendServer.start` gera o token (32 bytes aleatórios de `SecRandomCopyBytes`, em 64 caracteres hexadecimais) e roda `python -m vulcan_celox --serve` com a pasta de trabalho em `Resources` do bundle. Com `-m`, a pasta atual vai para o começo do `sys.path`, então essa pasta fixa impede uma pasta hostil de plantar um módulo. O ambiente recebe `PYTHONPATH=<Resources>`, `PYTHONDONTWRITEBYTECODE=1`, `VULCAN_TOKEN`, `VULCAN_WATCH_PARENT=1`, e `SHELL` e `LANG` quando faltam.
3. O Python roda `serve()` em `server/app.py`:
   - `VulcanApp.__init__` aplica `secure_data_dir`, abre o `Store`, migra uma vez os dados do protótipo antigo, carrega o `Notebook`, detecta o backend, escolhe o guarda-chaves, cria o `LocalServer` (porta 0 significa que o sistema escolhe, e o token vem de `VULCAN_TOKEN`, que precisa ter ao menos 32 caracteres), o `TerminalManager` e o `SessionHub`, e registra cada módulo da API.
   - `SIGTERM` é mapeado para `KeyboardInterrupt`, para o encerramento normal rodar.
   - Imprime `VULCAN_PORT=<n>` e descarrega a saída.
   - Inicia `autostart.begin()` e `agents.start()`, mais o vigia do processo pai se `VULCAN_WATCH_PARENT=1`, e entra em `serve_forever`.
4. A casca espera até 20 segundos por `VULCAN_PORT=`. Se não chegar, encerra o filho e mostra um erro.
5. A casca monta os menus e o item na barra de menu e abre uma janela em `http://127.0.0.1:<n>/`. Um script de usuário no início do documento define `window.VULCAN = {token, native: true, kind}` só se `location.origin` for a origem do app.
6. A interface lê o token de `window.VULCAN` e chama a API.

### Janelas e a ponte nativa

Fechar a última janela não encerra: o app fica na barra de menu. `WebWindowController` prende a janela à origem do app em `decidePolicyFor`. Links externos `http` e `https` abrem no navegador padrão, e o resto é cancelado. A ponte é o script handler `vulcan`, e ela só aceita mensagens da origem do app. Tipos de mensagem: `dragRegions`, `popout`, `focusPopout`, `setTitle`, `close`, `relaunch`, `pickFolder`, `copy`. Os menus nativos chamam a página por `window.vulcanCommand(name)`. Um terminal destacado é outra janela na rota `#/popout/<id>`.

### Encerramento

| Gatilho | O que acontece |
|---------|----------------|
| Sair do app | `applicationWillTerminate` chama `server.stop()`: `SIGTERM`, espera até 6 segundos, depois `SIGKILL`. A janela nunca congela por mais que isso. |
| `SIGTERM` ou Ctrl-C no Python | `VulcanApp.shutdown()` nesta ordem: grava o índice de tarefas, `hub.finalize_all()` (grava toda memória aberta), `terminals.close_all()`, `hub.stop()`, `server.shutdown()`, `agents.stop()`. O servidor HTTP para antes de o banco dos agentes fechar. |
| A casca morre de forma anormal | `_watch_parent` confere `getppid()` a cada segundo. Quando muda, roda `shutdown` em uma thread com prazo de 3 segundos e chama `os._exit(0)`. Nenhum servidor ou PTY fica órfão. |

### Linux

`desktop_linux.py` cria o `VulcanApp` no próprio processo, com token de `secrets.token_urlsafe(32)`, e escolhe um modo de janela (`VULCAN_LINUX_MODE` ou `--mode` podem forçar):

1. `gtk`: GTK 3 e WebKit2GTK com a ponte `vulcan`. O token entra por um script guardado pela origem, e `decide-policy` prende a janela à origem.
2. `app`: Chromium, Chrome, Brave ou Edge com `--app` e perfil próprio em `<dados>/janela`.
3. `browser`: `xdg-open`. Não há janela para observar, então ele sai quando a interface para de consultar (`IDLE_EXIT_SECONDS`, 150 segundos, o dobro antes da primeira requisição).

Nos dois últimos modos o token nunca vai para uma linha de comando. Uma página 0600, `<dados>/abrir-janela.html`, redireciona para o app com o token no fragmento da URL, e `web/js/api.mjs` passa o token para o `sessionStorage` e o tira da barra de endereço.

## 5. Módulos do núcleo

### Geral

| Módulo | Faz |
|--------|-----|
| `core/paths.py` | Pasta de dados e locais das ferramentas. Todo caminho pode ser trocado por variável de ambiente nos testes. |
| `core/oscompat.py` | O que muda entre macOS e Linux: shell padrão (`$SHELL`, depois zsh, bash, sh), pasta de dados, `open_argv`. |
| `core/store.py` | JSON atômico (`write_json_atomic`, `read_json`), `Store` com envelope `{schema_version, data}`, permissões privadas (`secure_data_dir`, `make_private`), migração única do protótipo antigo. |
| `core/runner.py` | Único módulo que usa `subprocess`: `Runner.run`, `run_shell`, `stream`, `open_pipe`, `spawn_pty`, `terminate_pty`, `terminate_many` e o duplo de teste `FakeRunner`. Texto em `input=` vai pelo stdin, nunca pela linha de comando. |
| `core/trash.py` | `move_to_trash`: Finder no macOS, `gio trash` no Linux, e `<dados>/lixeira/` com data no nome se nenhum funcionar. |
| `core/debounce.py` | `Debouncer` com relógio injetável. |
| `core/textutil.py` | Normalização para busca (sem acento, sem caixa) e `headline`, o título curto de um pedido colado. |
| `core/redact.py` | Mascara segredos antes de o texto sair da máquina. Devolve o texto e a contagem. |
| `core/doctor.py` | Monta o JSON do `--doctor`. |
| `core/miniyaml.py` | Parser mínimo de YAML em bloco, sem dependência, usado nos arquivos do Lerd e nos cabeçalhos de prompt. |
| `core/tables.py` | Parser das tabelas ASCII impressas pela CLI do Valet. |

### Caderno

| Módulo | Faz |
|--------|-----|
| `core/models.py` | Dataclasses `Tag`, `Note`, `Task`, tolerantes a chaves desconhecidas e cores antigas. |
| `core/notebook.py` | `Notebook`: CRUD, filtros, ordem, desfazer a exclusão de tarefa (5 segundos), exportar e importar, ouvintes de mudança. |
| `core/progress.py` | `done / total`, por site, por tag e global. Sem tarefas dá 0% e o rótulo `sem tarefas`. |
| `core/markdown_index.py` | `TAREFAS.md`: global sempre, e por projeto com opt-in, escrevendo só entre `<!-- vulcan:tarefas:inicio -->` e `<!-- vulcan:tarefas:fim -->`. Saída determinística, e só grava quando o conteúdo muda. |
| `core/search.py` | Busca global em sites, tarefas, post-its e tags. |

Modelo de dados. `site = null` significa item global, fora de projeto. `terminal` liga o item a uma sessão de terminal, e o item criado com `terminal` herda o site dessa sessão.

```
Tag  {id, name, color}
Note {id, site|null, text, color, tags[], pinned, created_at, updated_at, order, terminal|null}
Task {id, site|null, title, status: todo|doing|done, priority: 1..3, tags[], due|null, order,
      created_at, done_at|null, terminal|null, assignee|null}
```

### Terminais e sessões

| Módulo | Faz |
|--------|-----|
| `core/pty_session.py` | `PtySession` e `TerminalManager`. Veja a seção 7. |
| `core/sessions.py` | `SessionRecord`, `SessionStore`, `InputTracker`. |
| `core/session_memory.py` | Gera a memória da sessão e o `INDICE.md`, e limpa os escapes do terminal. |
| `core/procinfo.py` | Processos do grupo em primeiro plano de um terminal: `/proc` no Linux, `ps` no macOS. |
| `core/quick_commands.py` | Comandos de um projeto (composer, artisan, npm), comandos recentes e `is_long_running`. |
| `core/themes.py` | Os quatro temas de sessão e a rotação deles. Tema é dado: um item em `THEMES` e um id em `ROTATION`. |

### Ambiente e projetos

| Módulo | Faz |
|--------|-----|
| `core/backends/base.py` | Interface `Backend`, `EnvStatus`, validação das ações de site. |
| `core/backends/lerd.py` | `LerdBackend`: CLI, API do painel (`api_get`, `api_post`), lista de sites. |
| `core/backends/valet.py` | `ValetBackend`: CLI. |
| `core/backends/null.py` | `NullBackend`: modo local, sem ambiente. |
| `core/sites.py` | `Site` e `discover_sites` (parked, linked, manual). |
| `core/site_list.py` | Ordem da barra lateral: favoritos primeiro, depois ordem alfabética, com filtro. |
| `core/site_runtime.py` | Lê `lerd which` e `php -v`, e confere se a aba chega nos shims do Lerd. |
| `core/environment.py` | Lê o estado do Lerd, serviços, `php:list`, `php -m`, `php:ext list` e `xdebug status`. |
| `core/php_ini.py` | Seis ajustes comuns do `php.ini`. Também roda como ajudante `EDITOR` do `lerd php:ini`. |
| `core/laravel_log.py` | `storage/logs/laravel.log` lido por posição no arquivo, entradas com nível. |
| `core/lerd_dumps.py` | Eventos da ponte de dumps do Lerd: filtros, agrupar por requisição, queries repetidas, janela de uma sessão de agente, resumo mascarado. |
| `core/lerd_quirks.py` | Contornos para defeitos do Lerd, para o `--doctor`. |
| `core/node_project.py` | Leitor só leitura de um projeto Node. |
| `core/harness.py` | Leitor do harness de um projeto e instalador do formato mínimo. |

### Prompts e IA

| Módulo | Faz |
|--------|-----|
| `core/prompts.py` | Prompts como arquivos Markdown com cabeçalho, variáveis, `paste_bytes`, escolha da sessão atual. |
| `core/ai.py` | Cliente mínimo da Messages API da Anthropic, com transporte injetável. |
| `core/keychain.py` | Chave de API no Keychain ou no Secret Service, ou em memória. |
| `core/doc_prompts.py` | Monta o que é enviado à IA. |

### Agentes

| Módulo | Faz |
|--------|-----|
| `core/agents/discovery.py` | Onde ficam os arquivos de sessão. |
| `core/agents/jsonl_stream.py` | Leitura incremental por linha, `LineStream` e `ZstdLineStream`. |
| `core/agents/claude_reader.py`, `core/agents/codex_reader.py` | Transformam linhas em fatos sobre a sessão. |
| `core/agents/rules.py` | Heurísticas como dados: ferramenta para efeito, o que é teste, o que é publicação, onde fica a worktree. |
| `core/agents/builder.py` | `SessionBuilder`: monta o `AgentSession`, com estado que sobrevive entre leituras. |
| `core/agents/model.py` | Modelo normalizado: `AgentSession`, `FileTouch`, `CommandRun`, `SessionEvent`, e conversões seguras. |
| `core/agents/reading.py` | `read_session`: continua do offset salvo com o estado salvo do leitor. |
| `core/agents/index.py` | `AgentIndex`, SQLite em `agentes.db`. |
| `core/agents/history.py` | Tabela FTS5 e busca, com queda para `LIKE`. |
| `core/agents/watcher.py` | `AgentWatcher`: polling com `os.stat`. |
| `core/agents/loops.py` | `LoopTracker`: o mesmo teste rodado 3 vezes ou mais sem commit entre elas. |
| `core/agents/repos.py` | Branches e worktrees, cruzando sessões com o git real. |
| `core/agents/pairing.py` | Liga aba e sessão, e instala o hook. |
| `core/agents/pricing.py` | Preço por modelo e custo de um turno. |
| `core/agents/usage.py` | Agregação de uso, CSV, resumo para o `--doctor`. |
| `core/agents/status.py` | Diagnóstico só leitura das fontes de agentes, para o `--doctor` e a tela de histórico. |

### Servidor

| Módulo | Faz |
|--------|-----|
| `server/app.py` | `VulcanApp`: estado, serviços, `spawn_terminal`, rotas centrais (`/api/state`, `/api/services/<action>`, `/api/app/build`, `/api/preferences`, `/api/open`), `serve`. |
| `server/local_http.py` | HTTP em loopback, conferências de segurança, roteador, estáticos. |
| `server/websocket.py` | RFC 6455 mínimo. |
| `server/terminals_api.py` | Terminais por REST e WebSocket, `ClientSender`, `/api/themes`. |
| `server/session_hub.py` | Liga PTYs, registros de sessão, comandos, memória e `INDICE.md`. |
| `server/sessions_api.py` | `/api/sessions`, `/api/sessions/tree`, `/api/index/general`. |
| `server/notebook_api.py` | Tags, post-its, tarefas, progresso, busca, `TAREFAS.md`. |
| `server/agents_api.py` | `/api/agents/*`: sessões, revisão, histórico, uso, repositórios, retomar, pareamento, sessão atual. |
| `server/prompts_api.py` | `/api/prompts`, incluindo o envio. |
| `server/sites_api.py` | `/api/sites/*`: adicionar, versões, ações, favoritos, compartilhar, remover, Lixeira, runtime, comandos, log. |
| `server/sites_harness_api.py` | `/api/sites/<nome>/harness`: leitura, instalação, novas tarefas. |
| `server/env_api.py` | `/api/environment/*`: serviços, PHP, `php.ini`, extensões, Xdebug, Node. |
| `server/debug_api.py` | `/api/debug/*`: eventos da ponte, interruptor, limpar, erros de uma sessão de agente. |
| `server/node_api.py` | `/api/node-projects/*`. |
| `server/guide_api.py` | `/api/guide`: os quatro passos da tela Início e a escolha de pular. |
| `server/fs_api.py` | Conferência de pasta e pastas recentes para o diálogo "abrir terminal em". |
| `server/autostart.py` | `EnvAutostart`: inicia o Lerd ou o Valet junto com o app, em segundo plano, se estiver parado. |
| `server/ai_api.py` | Chave, validação na Anthropic, escolha do modelo. |
| `server/ai_docs.py` | Prévia do que será enviado, geração e leitura dos arquivos gerados. |
| `server/ai_jobs.py` | Tarefas de IA em segundo plano: uma por alvo, com estado que a interface consulta. |

### Aba Código, atenção, portas e estado do PR (1.1)

- `core/agents/edits.py`: tabela `session_edits` com caminho, hora, ferramenta, turno e offset. O conteúdo é lido sob demanda do arquivo da sessão por `edit_detail()`, então sessão apagada pelo agente fica sem diff. No Claude Code as fontes são `Edit`, `MultiEdit` e `Write`; `originalFile` só é lido, nunca guardado. No Codex o item `FileChange` traz o diff, e o patch legível cobre o formato antigo.
- `core/code_files.py`, `core/code_diff.py`, `server/code_api.py`, `server/known_roots.py`: visor só leitura. O lado de HEAD vem de `git cat-file blob`, e o atual é lido direto, então `diff.external`, `textconv` e filtros `clean` do repositório analisado nunca rodam.
- `core/agents/attention.py`, `core/agents/attention_hook.py`: estado do turno por sessão e o hook opcional dos pedidos de permissão.
- `core/agents/turns.py`: eventos e edições agrupados por pedido, na mesma contagem do leitor.
- `core/listening_ports.py`: portas de cada PTY e seus descendentes, com `lsof` no macOS e `/proc/net` no Linux, com cache de 10 s.
- `core/pr_status.py`, `server/pr_api.py`: estado do PR pelo `gh` do usuário, só com a preferência `pr_status` ligada, com cache de 60 s.
- Interface: `web/js/views/code/`, `web/js/terminal-watch.mjs` (atenção, links de caminho e marcas de pedido de cada terminal), `web/js/terminal-ports.mjs`, `web/js/pr-status.mjs`, `web/js/theme.mjs`, `web/styles/tokens.css` (único arquivo com cor solta) e `web/vendor/codemirror.js`, carregado na primeira vez que a aba Código abre.

## 6. Servidor HTTP e WebSocket

`server/local_http.py` usa `ThreadingHTTPServer`, com uma thread por conexão. As rotas, por grupo, estão em [http-api.md](http-api.md). O modelo de ameaça está em [security.md](security.md). As regras do próprio servidor:

| Regra | Comportamento no código |
|-------|-------------------------|
| Interface | Escuta em `127.0.0.1` por padrão, em porta escolhida pelo sistema. |
| `Host` | Precisa ser `127.0.0.1:<porta>` ou `localhost:<porta>`, senão 421. Vale para toda requisição, inclusive estáticos. |
| Token | Em `/api/`, só no cabeçalho `X-Vulcan-Token`, comparado com `hmac.compare_digest`, senão 401. Em `/ws/` a query `token=` também é aceita, porque o navegador não deixa pôr cabeçalho em WebSocket. O cabeçalho próprio também força um preflight entre origens, e esse preflight falha aqui. |
| `Origin` | Se vier, precisa ser a origem do app, senão 403. |
| Escrita | `POST`, `PUT` e `PATCH` em `/api/` precisam de `Content-Type: application/json`, senão 415. |
| Corpo | `Content-Length` é validado (400 se inválido), limite de 1 MB (413), e precisa ser um objeto JSON. Corpo que a rota não leu é descartado antes da resposta, para não corromper a próxima requisição da mesma conexão. |
| Estáticos | Servidos de uma cópia de `web/` feita quando o servidor sobe, buscada por chave, então travessia de caminho não tem o que alcançar. Arquivos e pastas começados por `.` ficam de fora. Só `GET`, senão 405. Estáticos não pedem token, porque a página não tem segredo: o token chega a ela pela casca. |
| Cabeçalhos | `X-Content-Type-Options: nosniff` em tudo, e `Cache-Control: no-store` na API. O HTML recebe esta CSP: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws://127.0.0.1:* ws://localhost:*; frame-ancestors 'none'`. |
| Erros | JSON `{"error": "..."}`, com mensagens em português. `HttpError` pode levar campos a mais, como `needs_terminal` ou `needs_confirmation`. |

Ler a interface uma vez também faz com que reinstalar o app com ele aberto não misture interface nova com servidor antigo. `GET /api/app/build` compara o SHA-256 da cópia carregada com os arquivos no disco, e a interface oferece reabrir quando diferem.

Despacho: `LocalServer.route(method, pattern)` compila uma expressão regular ancorada, e os grupos nomeados viram `req.params`. O handler devolve dados para JSON, uma tupla `(status, dados)` ou um `RawResponse` (usado pelo CSV de uso), ou levanta `HttpError`. Caminho que casa com o método errado recebe 405, e caminho desconhecido recebe 404.

`server/websocket.py` implementa o handshake, os quadros e a fragmentação, com limite de 16 MB por mensagem, e responde a ping. A única rota WebSocket é `/ws/terminals/<id>`, descrita na próxima seção.

## 7. Terminais e sessões PTY, memória de sessão

### PTY

Cada aba é um PTY real criado por `os.forkpty` em `runner.spawn_pty`. `TerminalManager.argv_for` roda o shell do usuário em modo login (`<shell> -l`). Com um comando inicial, roda `<shell> -l -i -c "<comando>; exec <shell> -l"`, para a aba continuar como shell interativo depois.

`terminal_env` põe os shims do Lerd, `~/.local/bin`, `/opt/homebrew/bin` e `/usr/local/bin` no começo do `PATH`. Define `TERM=xterm-256color`, `COLORTERM=truecolor` e `TERM_PROGRAM=VulcanCelox`, e remove `VULCAN_TOKEN` e `VULCAN_WATCH_PARENT`, para o token do servidor nunca chegar ao shell do usuário. Cada aba recebe `VULCAN_SESSION_ID`, e `VULCAN_THEME` quando tem tema.

`PtySession`:

- Uma thread leitora por PTY guarda até 256 KB de histórico e entrega a saída aos ouvintes.
- Só ela fecha o descritor de arquivo. `close()` a acorda por um self-pipe e espera. Fechar de outra thread deixaria o número livre para outra aba enquanto a leitora ainda poderia ler dele.
- `write` faz uma escrita por vez, com lock, em mestre não bloqueante, com prazo de 5 segundos sem progresso, e devolve `True` só se escreveu tudo. Uma colagem grande não se mistura com teclas, e uma aba que não lê não prende a thread que escreve.
- `subscribe(listener, prime)` devolve o histórico e chama `prime` dentro do lock, então o que `prime` enfileira vem antes de qualquer saída nova.

Encerramento: `terminate_pty` manda `SIGHUP` e `SIGTERM` ao grupo e `SIGKILL` depois de 2 segundos. `close_all` usa `terminate_many`, com sinal para todas e uma espera só, então dez abas que ignoram `SIGHUP` levam 2 segundos no total.

### WebSocket e clientes

`/ws/terminals/<id>` leva entrada e saída em quadros binários. Quadros de texto levam JSON: `resize` (1 a 1000 linhas e colunas), `input` e `exit`. `ClientSender` dá a cada cliente uma fila limitada a 4 MB e uma thread de envio própria. A leitora do PTY só enfileira, então um cliente lento nunca para a leitora, os outros clientes nem o processo. Cliente acima do limite é desligado.

Do lado da interface, `web/js/terminals.mjs` usa xterm.js 6 com os addons fit, web-links, search, WebGL, unicode 11 e serialize. Reconecta sozinho até 5 vezes, com espera crescente. Depois a aba avisa, e Enter tenta de novo.

### Criar uma aba

`POST /api/terminals` aceita site ou pasta, título, tema (`auto` gasta o próximo da rotação), tamanho, `command` e `agent` (`shell`, `claude` ou `codex`). O comando do agente vem de uma tabela fixa, então ali nada do cliente vira comando. `VulcanApp.spawn_terminal` cria o PTY, registra a sessão e, se vier `typed`, escreve essa linha no shell na hora e a registra como comando, o que o pareamento usa. `GET /api/terminals/<id>/busy` usa `pgrep` para avisar antes de fechar uma aba com filho rodando.

### Registro e memória da sessão

`SessionRecord {id, title, site, cwd, tags[], commands[{ts, cmd}], created_at, closed_at, exit_code, memory_file, theme}` fica em `terminal_sessions.json`, com até 2000 comandos por sessão.

`InputTracker` reconstrói as linhas digitadas a partir dos bytes que o WebSocket recebe: teclas de edição, sequências de escape, colagem entre colchetes e UTF-8 partido entre blocos. É uma aproximação consciente: comando recuperado do histórico do shell pelas setas não aparece na entrada e fica só no registro de saída.

`server/session_hub.py` grava a memória:

- quando a sessão é criada, quando o processo sai, quando a aba fecha e quando o app sai;
- a cada 15 segundos se a sessão teve entrada ou saída;
- quando tarefas, post-its ou tags mudam, com debounce de 1 segundo.

Sessão ainda marcada como aberta na inicialização é encerrada, porque nenhum PTY sobrevive a um reinício do servidor. A thread de gravação não morre com exceção: o último erro vai para o arquivo `memoria_status`, e o `--doctor` o mostra.

O arquivo de memória é `<dados>/sessoes/<site ou global>/<AAAA-MM-DD-HHMM>-<título>-<id>.md`. Ele guarda metadados, tags, tarefas, post-its, sessões de agente pareadas, comandos e a transcrição limpa de escapes (`strip_terminal`), até as últimas 2000 linhas, entre `<!-- vulcan:registro:inicio -->` e `<!-- vulcan:registro:fim -->`. Para sessão encerrada, a transcrição é relida do arquivo, então regravar depois de uma tarefa mudar não a perde. `<dados>/INDICE.md` é o índice geral. Apagar uma sessão encerrada manda a memória e a documentação para a Lixeira, e `items=keep` ou `items=delete` decide o destino das tarefas e dos post-its.

## 8. Sessões de agente

Os formatos estão em [agent-file-formats.md](agent-file-formats.md). O hook opcional está em [pairing-hook.md](pairing-hook.md).

O app lê os arquivos do Claude Code (`CLAUDE_CONFIG_DIR` ou `~/.claude`) e do Codex (`CODEX_HOME`, lista separada por vírgula, ou `~/.codex`) em stream, por linha. Nunca escreve nessas pastas, com uma exceção: `--instalar-hook`, rodado pelo usuário.

### Leitura

1. `discovery` lista `projects/*/*.jsonl` do Claude, deixando `agent-*.jsonl` de fora e apenas contando os subagentes. Do Codex, lista `.jsonl` e `.jsonl.zst` em `sessions/` e `archived_sessions/`. Se um rollout existe nas duas formas, vale o `.jsonl`. Sem o comando `zstd`, os comprimidos são ignorados e contados.
2. `jsonl_stream.LineStream` começa em um offset em bytes e consome só linhas completas. Uma última linha cortada espera a próxima passada. JSON inválido, valor que não é objeto e linha acima de 5 MB são registrados como erro e pulados. Arquivo menor que o offset recomeça do zero. `ZstdLineStream` lê por `zstd -dcq`, sempre do início.
3. `reading.read_session` escolhe o leitor e o alimenta linha a linha. Uma exceção em uma linha é registrada e a leitura segue.
4. `claude_reader` e `codex_reader` chamam o `SessionBuilder`, usando as tabelas de `rules`. `builder` aplica o estado de publicação (`none`, `committed`, `pushed`, `pr_open`, em que cada etapa exige a anterior desde a última edição), corta o texto dos eventos em 2000 caracteres e guarda os últimos 200 comandos.

Particularidades que importam ao mexer neles:

- Claude: um turno vira várias linhas com o mesmo `message.id` e o mesmo `usage`, então os tokens contam uma vez por id. A publicação espera o `tool_result` e só conta se não foi erro. Linhas com `isSidechain` atualizam o horário, mas não o conteúdo.
- Codex: o arquivo guarda totais acumulados, então o uso de um turno é a diferença para o total anterior, e um total menor recomeça a conta. `session_origin` marca subagentes e o app desktop, que não nascem de uma aba.

### Índice

`index.AgentIndex` é SQLite em `<dados>/agentes.db`, em modo WAL para `--doctor`, `--reindexar-agentes` e `--podar-agentes` funcionarem com o app aberto. É descartável: a fonte da verdade é o JSONL, mas uma sessão cujo arquivo sumiu continua no índice.

| Tabela | Guarda |
|--------|--------|
| `meta` | `schema_version`, `revision`, `last_error` |
| `sessions` | Resumo leve, offset, estado do leitor, identidade do arquivo |
| `session_files`, `session_commands` | Listas que só o detalhe usa |
| `events`, mais a FTS5 `history` | Pedidos, respostas, comandos e arquivos para a busca |
| `agent_usage` | Tokens por turno |
| `parse_errors` | Arquivo, offset e motivo |

A identidade de um arquivo é o inode mais um hash do começo, o que detecta um arquivo trocado por outro de mesmo nome e tamanho maior. O JSONL é lido fora do lock, então a API não espera um arquivo grande. A gravação só acontece se ninguém gravou aquele arquivo no meio. Esquema abaixo da versão 5 provoca uma reconstrução, e banco que falha no `quick_check` é renomeado para `agentes.db.corrupt-<ts>` e recriado. Cada mudança incrementa `revision`.

Uma sessão está **ativa** quando o arquivo mudou há menos de 90 segundos e o último evento tem menos de 10 minutos. A segunda condição existe porque copiar uma pasta muda as datas dos arquivos, mas não as dos eventos.

`history` usa `unicode61 remove_diacritics 2`, então a busca ignora acentos. Sem FTS5 no SQLite, cai para `LIKE`, que não ignora acentos, e o `--doctor` avisa. `status` também lê `cleanupPeriodDays` das configurações do Claude (padrão 30), porque o Claude apaga as sessões antigas.

### Observador

`watcher.AgentWatcher` varre com `os.stat` a cada 2 segundos, e cada arquivo alterado espera 300 ms sem nova mudança. `VULCAN_AGENTS=0` o desliga. A interface consulta `GET /api/agents/revision` e só recarrega quando muda. `settled()` diz às telas se a primeira varredura terminou.

### Estado do git

`repos` cruza as sessões com o git real para mostrar branches e worktrees com trabalho sem conciliar. Toda chamada usa `git -c core.fsmonitor=false -c core.untrackedCache=false --no-optional-locks`, porque o repositório analisado é de terceiros: `core.fsmonitor` faria o `git status` rodar um programa definido no `.git/config` dele. As chamadas têm prazo de 5 segundos e cache de 30 segundos por pasta. O app nunca faz commit, push nem remove worktree.

`loops` marca o mesmo teste rodado 3 vezes ou mais sem commit entre elas, usando os padrões de teste de `rules`.

### Pareamento

`pairing.resolve` liga uma sessão de agente a uma aba de terminal, e as duas passam a dividir o tema:

1. **Arquivo do hook** (exato). O hook `SessionStart` lê `VULCAN_SESSION_ID` do ambiente e grava `<dados>/pairings/<sessão>.json`. Só é instalado por `--instalar-hook`, com backup do `settings.json`.
2. **Pasta e horário** (reserva, e o único caminho para o Codex). Mesma pasta, e a sessão começou até 60 segundos depois de a aba abrir ou de `claude` ou `codex` ser digitado nela. Sessões com `origin` ficam de fora. Na disputa, os pares seguem a ordem no tempo, com o maior número de pares e, no empate, os menores intervalos (`_match`).

O resultado fica em cache e só é refeito quando a revisão do índice, as abas ou a pasta do hook mudam.

`POST /api/prompts/send` depende do pareamento. Escreve só na aba pareada, como colagem entre colchetes, sem caracteres de controle e **nunca com Enter**. Antes de escrever, confere se a aba está viva, se esta é a sessão pareada mais nova e se o agente está no grupo em primeiro plano (`procinfo`; quando não dá para saber, basta a aba viva). Senão responde 409 com `needs_terminal`, e a interface oferece retomar a sessão. Se a aba não lê a colagem a tempo, responde 503.

`POST /api/agents/sessions/<id>/resume` abre uma aba nova na pasta da sessão e digita `claude --resume <id>` ou `codex resume <id>`. O id vem do índice e passa por um padrão que precisa começar com letra ou dígito, então não vira opção.

### Uso e custo

Cada turno vira uma linha em `agent_usage` com `input`, `output`, `cache_read`, `cache_write_5m`, `cache_write_1h` e `reasoning`.

`pricing` guarda uma tabela padrão em USD por milhão de tokens, com a data da conferência (`CONFERIDO_EM`) e as fontes. Não há consulta de rede. `<dados>/precos.json`, com um objeto `modelos`, sobrescreve modelo por modelo. Os nomes são normalizados (sem sufixo de data nem variante). Uma entrada pode ter `acima`, o preço de contexto longo acima de um tamanho de prompt. Modelo ou tipo de token sem preço dá `None`, nunca 0.

`usage.aggregate` agrupa por `day`, `project`, `model`, `agent` ou `session`, em dias locais, com padrão dos últimos 30 e limite de 400. `reasoning` não é cobrado à parte, pois já está em `output`. Grupo em que só parte do uso tem preço fica marcado com `cost_partial`. O resultado é uma **estimativa no preço da API**, e assinatura cobra de outro jeito, como a tela informa. `GET /api/agents/usage.csv` leva só ids, projetos, modelos e números, nenhum texto de sessão.

## 9. Backends de ambiente e projetos Node

### Interface de backend

`core/backends/base.py`. Detecção (`detect_backend`): Lerd, depois Valet, depois `NullBackend`. Cada lista de locais pode ser trocada por uma variável de ambiente, e com a variável definida só aquele caminho conta.

| Backend | Procurado em | Variável |
|---------|--------------|----------|
| Lerd | `~/.local/bin/lerd`, `/opt/homebrew/bin/lerd`, `/usr/local/bin/lerd` | `VULCAN_LERD_BIN` |
| Valet | `/opt/homebrew/bin/valet`, `/usr/local/bin/valet`, `~/.composer/vendor/bin/valet`, `~/.config/composer/vendor/bin/valet` | `VULCAN_VALET_BIN` |

| Membro | Para quê |
|--------|----------|
| `name`, `label`, `available`, `bin_path`, `runner` | Identidade e como rodar as coisas |
| `start()`, `stop()`, `restart()` | Serviços, devolvendo `Result` |
| `status()` | `EnvStatus(running, summary, details)` |
| `list_sites(manual)` | Lista de `Site` |
| `site_command(action, *args)` | Devolve o argv e a pasta de trabalho de uma ação. Cada backend implementa este único método |
| `link`, `unlink`, `park`, `unpark`, `secure`, `unsecure`, `isolate`, `isolate_node` | Construídos sobre `site_command`, com validação |
| `site_argv(action, *args)` | argv validado, para rodar em uma aba de terminal em vez de esperar |
| `share_argv(name, tool)`, `php_versions()` | Compartilhamento e o seletor de PHP |
| `project_writes` | O que o backend escreve no projeto em cada ação, para a interface avisar antes |

Valor que começa com `-` é recusado em `_check`, porque viraria opção da CLI.

### Lerd

A fronteira com o Lerd (formato de dumps conferido na 1.37.1, MIT) tem dois canais:

- **API do painel** em `http://127.0.0.1:7073` (`VULCAN_LERD_API`). Leituras têm prazo curto (`api_get`, 1,5 segundo, devolvendo `None` se o painel estiver fora), e todo POST leva `X-Lerd-CSRF: 1`, que o Lerd exige (`api_post`). Proxies do ambiente são ignorados, porque é loopback. Rotas usadas: `/api/status`, `/api/sites`, `/api/services`, `/api/dumps`, `/api/dumps/status`, `/api/dumps/toggle`, `/api/dumps/clear`, `/api/node-versions`. Com o painel fora, a lista de sites cai para o `sites.yaml` em `~/.local/share/lerd/` (`VULCAN_LERD_DATA`).
- **CLI** por `core/runner.py`. Comando rápido roda e devolve a saída. Comando que constrói imagem ou fica rodando (`fetch`, `php:update`, `xdebug on|off`, `node:install`, `logs -f`, `share`, `db:shell`, `site:doctor`) abre em uma aba de terminal por `spawn_terminal`, com a saída à vista. Leituras repetidas da tela Ambiente (`php:list`, `xdebug status`) ficam 60 segundos em cache, e qualquer ação limpa o cache.

Mudanças no `php.ini` passam pelo próprio `lerd php:ini`, com `EDITOR` apontando para `<dados>/hooks/php-ini-editor.sh`. Esse script roda `core/php_ini.py` com `python -I`, então a pasta atual não entra no `sys.path`. O ajudante faz uma cópia `.bak-<data>` e muda só as linhas pedidas, e o Lerd então reaplica o PHP-FPM como faz depois de uma edição normal.

Não há servidor de dumps nem helper PHP próprios. A ponte é a do Lerd (`127.0.0.1:9913`). `core/lerd_quirks.py` lista os contornos e a versão que corrige cada um, e o comportamento não muda com a versão. O `--doctor` diz quais ainda são necessários. Uma correção foi enviada ao projeto: lerd-env/lerd#2404.

`POST /api/services/<action>` e o início automático dividem uma trava, então duas operações de serviço nunca se sobrepõem. `lerd start` pode levar minutos, porque pode baixar imagens e subir a VM do Podman, por isso o prazo é de 300 segundos.

### Valet

Só CLI. Os sites vêm de `~/.config/valet/config.json` (`paths` são as pastas parked, mais `tld`), dos symlinks em `~/.config/valet/Sites/` (linked) e do `sites.json` do app (manual). `VULCAN_VALET_HOME` troca a pasta. Em domínio duplicado, a prioridade é linked, depois parked, depois manual. `unpark` vira `valet forget`, e `isolate_node` não está disponível. As telas Ambiente e Depuração só existem para o Lerd, e as rotas delas respondem 409 para os outros backends.

### Remover um site

Duas etapas. `POST /api/sites/<nome>/remove` recebe `level=list` para site manual ou `level=backend` para site registrado. Para site parked do Valet, exige `parent`, porque esquecer a pasta mãe afeta todos os sites dela. Só depois disso `POST /api/sites/trash` pode mover a pasta para a Lixeira, com o nome digitado em `confirm`. Recusa a pasta home, caminhos muito curtos e pasta que o backend ainda lista.

### Projetos Node

`core/node_project.py` lê, só leitura e com limite de 1 MB por arquivo:

- o `package.json` da raiz, e JSON inválido vira `estado: ilegivel` com o erro, nunca projeto vazio;
- o lockfile, para escolher o gerenciador (pnpm, bun, yarn, npm);
- o framework pelas dependências, e a porta provável (opção de porta no script `dev` ou `start`, senão o padrão do framework);
- a versão do Node pedida (`.nvmrc`, `.node-version`, `engines.node`);
- o Supabase local (`supabase/config.toml`, só `project_id` e portas);
- o vínculo com a Vercel (`.vercel/project.json`, só `projectId` e `orgId`).

Nunca abre `.env`. `server/node_api.py` guarda a lista em `node_projects` no Store, então tirar um projeto da lista não toca na pasta. As sugestões vêm das pastas onde os agentes trabalharam. Um script roda em uma aba de terminal à vista, com a linha `<gerenciador> run <script>` montada pelo servidor a partir de valores validados, e parar manda Ctrl-C só para uma aba que este projeto abriu. As ações do Supabase são `start`, `stop` e `status`, também em aba. O app não fala com a Vercel nem com o Supabase remoto. A primeira URL local vista na saída de uma aba aparece na tela do projeto.

## 10. Aba Harness

A aba mostra em que ponto do contrato de um **projeto do usuário** os agentes estão. `core/harness.py` lê dois formatos. É só leitura, com limite de 1 MB por arquivo. Arquivo ilegível vira `estado: ilegivel` com o erro, nunca estado vazio. O app não muda status de item e não roda sensor: quem valida é o sensor do próprio projeto.

| | Formato completo (`tipo: repo`) | Formato mínimo (`tipo: minimo`) |
|---|---|---|
| Detectado por | `.harness/` | `.vulcan/` |
| Estado | `.harness/state.json` | `.vulcan/state/execution.json` |
| Contrato | Caminho no campo `contract`, como `specs/<feature>/contract.md`, sempre dentro do projeto | `.vulcan/tasks/<task_id>.md` |
| Handoff | `.harness/handoff.md` | `.vulcan/handoff.md` |

`detect` tenta primeiro o formato completo. `read` devolve o contrato, os itens (cada um no estado `feito`, `andamento`, `bloqueado` ou `pendente`), o próximo item, o último commit verde, até 60 linhas do handoff, a fila e, no formato mínimo, o status e o motivo de bloqueio. Valores de status do formato mínimo: `RUNNING`, `VERIFIED`, `INCOMPLETE`, `BLOCKED`, `CANCELLED`, `REVOKED`. Uma linha de item no contrato mínimo tem a forma `C1 [verde] objetivo sensor: build`, com as faixas `verde`, `amarela` e `vermelha`. Item do contrato que o estado ainda não citou conta como pendente.

`signature` (data de modificação e tamanho dos arquivos lidos) diz à tela quando redesenhar, e `web/js/views/harness.mjs` consulta a cada 5 segundos. `summary` dá uma linha para a tela da sessão de agente, e `find_project` escolhe o site mais específico que contém a pasta da sessão.

A escrita só acontece a pedido, em `server/sites_harness_api.py`:

- `GET .../harness/install` lista os arquivos e o conteúdo exatos, e não grava nada.
- `POST .../harness/install` exige `confirm: true` e instala o formato mínimo. Arquivos novos usam `O_EXCL`, então arquivo existente nunca é sobrescrito. `AGENTS.md` e `CLAUDE.md` do projeto são criados se nenhum dos dois existir. Se um existir, ele só ganha um bloco entre `<!-- vulcan:harness:inicio -->` e `<!-- vulcan:harness:fim -->`. Link simbólico é recusado, assim como alvo fora do projeto.
- `POST .../harness/tasks` grava um novo `.vulcan/tasks/<task_id>.md` a partir de um formulário, com a aprovação pendente, e nunca sobrescreve.

Os dois são recusados com 409 se o projeto tiver `.harness/`.

## 11. Interface web

`web/` não tem build. `index.html` carrega o xterm.js e os addons como scripts comuns, e `js/app.mjs` como módulo. Tudo é local: `vendor/` guarda o xterm.js 6 com as licenças em `LICENSES.md`, e os ícones são símbolos SVG embutidos. Não há framework.

### Casca da interface

| Arquivo | Papel |
|---------|-------|
| `js/app.mjs` | `parseRoute`, `navigate`, `route`, atualização do estado, barra superior, comandos, boot |
| `js/app-state.mjs` | Estado `app`, `NAV`, `AGENT_NAV`, `HELP_NAV`, `NAV_GROUPS` |
| `js/view-mount.mjs` | `mountView`: um elemento raiz novo por tela, depois a classe de tela da rota |
| `js/remount.mjs` | Quais telas remontam quando a lista de sites muda. As outras mantêm o texto digitado |
| `js/sidebar.mjs`, `js/session-tree.mjs` | Grupos da barra lateral, listas de sites e a seção Sessões |
| `js/palette.mjs` | Paleta de comandos (⌘K) |
| `js/global-events.mjs` | Ouvintes e atalhos globais |
| `js/terminals.mjs`, `js/terminal-panel.mjs` | Área de terminais e o painel inferior nas telas sem terminal |
| `js/api.mjs` | Cliente da API, `every`, `wsUrl`, `native`, `isNative`, `hasBridge`, `isMac` |
| `js/dom.mjs`, `js/markdown.mjs`, `js/themes.mjs`, `js/ai.mjs`, `js/agents-ui.mjs`, `js/current-session.mjs`, `js/prompt-bar.mjs`, `js/folder-dialog.mjs`, `js/site-add.mjs`, `js/help-content.mjs` | Peças comuns |

`every(ms, fn)` repete depois que a chamada anterior terminou, e não consulta com a janela oculta. O estado atualiza a cada 5 segundos. `api()` tem prazo padrão de 20 segundos. `isNative` significa casca Swift com menus, `hasBridge` significa que há ponte (Swift ou GTK), e `isMac` escolhe ⌘ ou Ctrl+Shift.

### Rotas

As rotas usam o hash da URL.

| Rota | Tela (`js/views/`) |
|------|--------------------|
| `#/inicio` | `home.mjs` |
| `#/overview` (também `#/sites` e rotas desconhecidas) | `overview.mjs` |
| `#/sites/<site>/<aba>/<sessão>/<item>` | `site.mjs`, abas `terminal`, `tasks`, `notes`, `tags`, `harness`, `logs`, e `debug` no Lerd |
| `#/terminals/<aba>/<sessão>/<item>` | `site.mjs` (`TerminalsView`) |
| `#/popout/<id>` | Terminal destacado, sem barra lateral |
| `#/node`, `#/node/<nome>` | `node.mjs` |
| `#/lerd`, `#/ambiente` | `environment.mjs` |
| `#/depuracao` | `debug.mjs` |
| `#/agentes`, `#/agentes/<id>` | `agents.mjs`, `agent-session.mjs` |
| `#/agentes/historico` | `agents-history.mjs` |
| `#/agentes/branches` | `agents-branches.mjs` |
| `#/agentes/uso`, `#/agentes/uso/<AAAA-MM-DD>` | `agents-usage.mjs`; a data fixa o fim do período |
| `#/prompts` | `prompts.mjs` |
| `#/tasks`, `#/notes`, `#/tags`, `#/index` | `tasks.mjs`, `notes.mjs`, `tags.mjs`, `index.mjs` |
| `#/ajuda`, `#/ajuda/<seção>` | `help.mjs` |

Telas de apoio: `logs.mjs` e `harness.mjs` são abas de site, e `session-tags.mjs` pertence a uma sessão.

Quando só muda a sessão, a aba ou o item na mesma tela, o roteador chama `reveal` e não remonta, então os terminais sobrevivem. Uma tela é uma classe com `constructor(root, options)` e, opcionalmente, `update(state)`, `reveal(route)`, `command(name)` e `destroy()`. A primeira tela é `#/inicio` até os quatro passos do guia estarem feitos ou pulados (`GET /api/guide`), depois o último site ou a visão geral.

### Conteúdo da Ajuda

`web/help/conteudo.json` é a única fonte da tela Ajuda e do `docs/pt-BR/user-guide.md`, gerado por `scripts/manual_md.py`. O `validate.sh` compara os dois, então edite o JSON e gere de novo. Ele guarda `secoes` (blocos `p`, `ul`, `passos`, `img`, `atalhos`) e `faq`. `ROUTE_SECTION` em `js/help-content.mjs` liga cada rota a uma seção, para o ⌘?. As capturas em `web/img/manual/` vêm de `scripts/manual_shots.sh`, com fixtures e Lerd falso, nunca com dado real. `scripts/help_json.py` regrava o JSON no layout do repositório.

### Temas

`core/themes.py` fornece a paleta do xterm e os tokens `--t`, `--t-bg` e `--t-ink` por `GET /api/themes`, e a página injeta o CSS, por isso a CSP permite estilo inline. Homebrew, Clássico, Oceano e Ardósia entram em rotação, com a posição guardada no Store. A aba e a sessão de agente pareada usam o mesmo tema.

### Prompts

Arquivos Markdown com cabeçalho (`id`, `title`, `category`, `pin`, `descricao`, `icone`), globais em `<dados>/prompts/` e por projeto em `<projeto>/.vulcan/prompts/`. Essa pasta só é criada depois de confirmação. Um prompt do projeto sobrescreve o global de mesmo `id`. As variáveis `{{projectName}}`, `{{branch}}`, `{{base}}`, `{{sessionId}}`, `{{agent}}` e `{{cwd}}` não têm lógica. A que falta fica como está e entra em `missing`. O compositor dá um campo por variável, com prévia. A sessão atual é a escolhida, senão a ativa mais recente, senão a mais recente.

## 12. Documentação com IA

Roda **só por clique**, e o fluxo sempre mostra um diálogo antes. O app não tem chave própria: quem fornece é o usuário.

| Etapa | Código |
|-------|--------|
| Chave | `PUT /api/ai/key` confere o formato (`sk-ant-...`), valida listando os modelos na API e só então guarda. A API devolve só a forma mascarada |
| Guarda | `core/keychain.py`: Keychain do macOS, serviço `com.byvulcan.celox.anthropic`, gravado com `security -i` e o comando pelo stdin, nunca por argv. No Linux, Secret Service por `secret-tool`, valor pelo stdin. `VULCAN_KEYSTORE=memory` guarda em memória, para testes e capturas |
| Prévia | `GET /api/ai/preview/session/<id>` ou `/general` devolve tamanho, segredos mascarados, se houve corte e o modelo. Nada sai da máquina ainda |
| Montagem | `core/doc_prompts.py`. Sessão: os últimos 60 mil caracteres da transcrição e os últimos 300 comandos. Geral: orçamento de 120 mil caracteres, usando a documentação de cada sessão quando existe, da mais nova para trás; as demais ficam com uma linha cada. O texto instrui o modelo a se basear só no material dado |
| Máscara | `core/redact.py` roda **antes** do corte, porque um segredo cortado ao meio perderia o prefixo que a máscara reconhece, e de novo no texto final. Cobre formatos de chave de API, JWT, `Bearer`, senhas em URLs, pares `CHAVE=valor` sensíveis, `--password` e `mysql -p` |
| Chamada | `POST /api/ai/docs/...` devolve 202 e roda em `server/ai_jobs.py`, uma tarefa por alvo, com 409 para duplicata. `core/ai.py` chama `POST /v1/messages` da API da Anthropic com `anthropic-version: 2023-06-01`, modelo padrão `claude-sonnet-5-5`, só com a biblioteca padrão. Tenta de novo uma vez em 429 e 5xx, tira a chave dos textos de erro, e trata `stop_reason: refusal` como erro, para texto parcial nunca virar documento |
| Saída | `<memória>.doc.md` ao lado da memória e `<dados>/DOCUMENTACAO.md`, com cabeçalho dizendo que foi gerado por IA, o modelo e a data. Resposta cortada por `max_tokens` ganha um aviso. O `INDICE.md` aponta para os documentos |

`VULCAN_ANTHROPIC_BASE_URL` troca a base, para proxy ou servidor de teste. Precisa ser `https`, e `http` só é aceito para `127.0.0.1`, `localhost` e `::1`, para a chave nunca sair em claro da máquina. O transporte é injetável em `AnthropicClient`, então os testes nunca chegam à rede.

## 13. Dados em disco e configuração

Todos os caminhos, opções e variáveis estão em [configuration.md](configuration.md).

A pasta de dados é `~/Library/Application Support/VulcanCelox/` no macOS e `$XDG_DATA_HOME/vulcan-celox` no Linux, e `VULCAN_CELOX_HOME` a substitui. `secure_data_dir` põe a pasta e as subpastas em 0700 e os arquivos em 0600 a cada abertura, sem seguir links simbólicos. Scripts continuam executáveis, só para o usuário.

| Arquivo ou pasta | Guarda |
|------------------|--------|
| `tags.json`, `notes.json`, `tasks.json` | Caderno |
| `sites.json`, `favorites.json`, `quick.json` | Sites manuais, favoritos, comandos rápidos do usuário |
| `preferences.json`, `new_terminal.json`, `themes.json`, `guide.json` | Início automático, modelo de IA, padrões do novo terminal, rotação, guia |
| `settings.json` | Sites com o `TAREFAS.md` de projeto ligado |
| `node_projects.json`, `agents_current.json` | Lista de projetos Node, sessão atual escolhida |
| `terminal_sessions.json`, `memoria_status.json` | Registros de sessão, último erro de memória |
| `migrations.json`, `legacy_notes.json` | Migração do protótipo antigo |
| `agentes.db` (com `-wal` e `-shm`) | Índice de agentes |
| `precos.json` | Preços opcionais do usuário |
| `prompts/` | Prompts globais, criados com exemplos no primeiro uso |
| `sessoes/` | Memórias e arquivos `.doc.md` |
| `TAREFAS.md`, `INDICE.md`, `DOCUMENTACAO.md` | Índices e documentação gerados |
| `pairings/`, `hooks/` | Arquivos gravados pelo hook; `vulcan-pareamento.py`, `php-ini-editor.sh` |
| `lixeira/` | Reserva quando não há Lixeira do sistema |
| `abrir-janela.html`, `janela/` | Só Linux: página de lançamento e perfil do navegador |

Cada arquivo JSON tem o envelope `{"schema_version": 1, "data": ...}`. Arquivo sem envelope é aceito como dado bruto. Arquivo corrompido é renomeado para `<nome>.corrupt-<timestamp>`.

Fora da pasta de dados o app só escreve: `<projeto>/TAREFAS.md` (opt-in, bloco marcado), `<projeto>/.vulcan/` (com confirmação), os blocos em `AGENTS.md` e `CLAUDE.md` de um projeto onde o usuário instalou o harness, e o que o Lerd ou o Valet escrevem em uma ação do usuário (`project_writes` avisa antes). A única escrita em `~/.claude` é a instalação do hook.

## 14. Opções de linha de comando

### Pacote Python

`python3 -m vulcan_celox <opção>`, de `vulcan_celox/__main__.py`. Conferidas nesta ordem: `--instalar-hook`, `--reindexar-agentes`, `--podar-agentes`, `--serve`, `--doctor`, depois a interface tkinter.

| Opção | Faz |
|-------|-----|
| `--serve` | Servidor local, API e interface web. Imprime `VULCAN_PORT=<n>` |
| `--port N` | Porta do `--serve`. 0, o padrão, significa aleatória |
| `--doctor` | JSON: versão, pasta de dados, backend, estado, sites, contornos do Lerd, fontes de agentes, preços, uso de 30 dias, último erro de memória |
| `--reindexar-agentes` | Reconstrói do zero o índice de agentes e imprime os totais |
| `--podar-agentes [DIAS]` | Apaga do índice os eventos de sessões paradas há mais de DIAS (padrão 180). Resumo, arquivos e comandos ficam. Nunca é automático |
| `--instalar-hook` | Instala o hook de pareamento, com backup do `settings.json`. Veja [pairing-hook.md](pairing-hook.md) |
| `--selftest` | Abre a interface tkinter, exercita e sai. 0 significa sucesso |
| `--tk` | Aceita, mas não muda nada: sem outra opção, o ponto de entrada já abre o tkinter |
| `--version` | Versão |

`python3 -m vulcan_celox` sem opção abre a reserva em **tkinter**, não a interface web. A interface web precisa de uma casca ou do `--serve`.

### Casca macOS

`dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox`. Não repassa as opções do Python.

| Opção | Faz |
|-------|-----|
| `--snapshot <arquivo.png>` | Desenha fora da tela e grava um PNG |
| `--route "#/..."` | Rota inicial |
| `--wait <segundos>` | Espera depois de carregar (padrão 2,5) |
| `--size <L>x<A>` | Tamanho da janela (padrão 1440x900) |
| `--eval "<js>"` | Com `--snapshot`, roda um script na página 0,8 segundo depois de carregar |
| `--verificar-dependencias`, `--check-deps` | Diz qual Python seria usado (0) ou o que falta (1) |

Códigos de saída do `--snapshot`: 0 sucesso, 1 falha, 2 tempo esgotado, 3 erro de JavaScript na página, 4 a janela saiu da origem do app.

### Linux

`vulcan-celox` (`packaging/linux/vulcan-celox` e depois `desktop_linux.py`): `--check` sobe o servidor sem janela, verifica e sai; `--mode gtk|app|browser`; `--doctor`; `--version`. O lançador trata `--instalar-dependencias` (`--install-deps`), com `-y` opcional, e `--verificar-dependencias` (`--check-deps`).

## 15. Build e empacotamento

Requisitos: no macOS, as Command Line Tools. Não há `pip install` nem `npm install`.

| Script | Faz |
|--------|-----|
| `scripts/build_app.sh` | Cria `dist/Vulcan Celox.app`: copia `vulcan_celox/` para `Contents/Resources` com `rsync`, grava o `Info.plist` (id `com.byvulcan.celox`, macOS mínimo 13.0, versão de `vulcan_celox/__init__.py`), compila `packaging/macos/main.swift` com `swiftc` para a arquitetura atual, ou arm64 e x86_64 unidos por `lipo` com `VULCAN_UNIVERSAL=1`, roda `packaging/macos/icon.swift` para desenhar o ícone, e `iconutil` gera o `AppIcon.icns`. Os PNGs vão para `build/icon/` |
| `scripts/install_app.sh` | Instala em `~/Applications` e cria um atalho na Mesa. A versão anterior vai para a Lixeira. `VULCAN_INSTALL_DEST` e `VULCAN_DESKTOP` redirecionam |
| `scripts/package.sh` | No macOS, gera tudo em `executaveis/`: app universal, assinatura ad hoc (`codesign --sign -`), `.zip` e `.dmg`, `.tar.gz` e `.deb` de Linux, e `SHA256SUMS` |
| `scripts/package_linux.py` | Gera os instaladores de Linux só com Python 3.9+, sem Swift nem ferramentas do macOS. Saída em `executaveis/linux` por padrão (`--output`), com `SOURCE-MANIFEST.json` trazendo um SHA-256 por arquivo. Usado pelo CI |
| `scripts/make_deb.py` | Monta um `.deb` só com a biblioteca padrão, sem `dpkg-deb` |
| `scripts/manual_md.py`, `scripts/manual_shots.sh`, `scripts/help_json.py` | Manual do usuário a partir do conteúdo da Ajuda, as capturas dele e o layout do JSON |

`packaging/` guarda os fontes: `macos/main.swift`, `macos/AppIcon.icns`, `linux/vulcan-celox` (lançador: roda de dentro da pasta da biblioteca para um `json.py` do repositório atual não ser importado), `linux/vulcan-celox-deps` (verifica e instala bibliotecas com permissão, usando apt, dnf ou pacman), `linux/install.sh` e `linux/uninstall.sh` (sem sudo, em `~/.local` por padrão), `linux/vulcan-celox.desktop`, `linux/icons/`, `linux/deb/control` e `linux/deb/postinst`, e `LEIA-ME.md`, que vai nos pacotes.

Os pacotes de Linux deixam `ui/` de fora, e o `.deb` instala em `/opt/vulcan-celox` com um link em `/usr/bin`.

`.github/workflows/linux-mint.yml` roda no Ubuntu 22.04: `scripts/test_linux.sh`, `scripts/package_linux.py`, conferência das somas, instalação do `.deb`, `--check` e `--doctor`, e instalação pelo `.tar.gz`.

Os passos de uma versão estão em [development.md](development.md).

## 16. Testes e sensores

A descrição completa está em [testing.md](testing.md). Em resumo, `bash scripts/validate.sh` é o único sensor, e o código de saída dele decide.

Etapas do script: `compileall`; manual do usuário igual à forma gerada; `unittest` no Python atual e no Python 3.9 do sistema; `--selftest` sem backend e com Lerd falso e painel fora do ar; build do bundle, `plutil`, tamanho do ícone; `--snapshot` das rotas principais com fixtures; telas com `tests/tools/fake_lerd_api.py` e `tests/tools/fake-lerd`, em que cada seletor esperado começa como erro e só sai quando aparece; texto digitado sobrevivendo à lista de sites mudando; janela presa à origem; servidor sem importar da pasta atual; instalação em pastas temporárias.

Outras ferramentas: `bash scripts/test_linux.sh` roda a suíte em um contêiner `python:3.9-slim` (`VULCAN_LINUX_IMAGE`, podman ou docker).

Testes que sustentam as regras da seção 2:

| Teste | Sustenta |
|-------|----------|
| `tests/test_arquitetura.py` | Sem tkinter em `core/`, sem apagamento definitivo, `subprocess` e `shell=True` só no runner |
| `tests/test_arquitetura_doc.py` | Este manual cita todo módulo de `core/` e `server/` |
| `tests/test_tamanho_arquivos.py` | Nenhum arquivo novo de código acima de 400 linhas, e os congelados não crescem |
| `tests/test_docs_abertos.py` | Mesmas páginas nas duas línguas, links internos existem, sem o caractere de travessão |
| `tests/test_vendor_licenses.py` | Licenças do código vendorizado |
| `tests/test_web_assets.py` | Sintaxe do JavaScript com `node --check` ou `jsc` quando disponíveis, e outras conferências da interface |
| `tests/test_aceite_pareamento.py` | O caminho aba, sessão, prompt, com PTY real, shell real e um `claude` falso |

Classes base: `tests/helpers.py` (`TempDirTestCase`) e `tests/server_helpers.py` (`ServerTestCase`, que sobe um servidor real em porta livre, com pasta de dados temporária e `FakeRunner`). Os testes nunca tocam no Lerd real, em `~/.claude` ou em `~/.codex`. As fixtures em `tests/fixtures/` cobrem agentes (sessões reais anonimizadas e casos sintéticos), Lerd, harness e Node.

## 17. Limites conhecidos e dívida

| Item | Situação |
|------|----------|
| Sete arquivos acima de 400 linhas: `web/js/terminals.mjs` (1126), `packaging/macos/main.swift` (687), `ui/app.py` (594), `web/js/views/tasks.mjs` (523), `core/notebook.py` (493), `core/harness.py` (462), `web/js/views/site.mjs` (440) | Aceito para o 1.0, porque dividir terminal e janela sem teste de navegador traz mais risco que ganho. `tests/test_tamanho_arquivos.py` impede que cresçam e barra arquivo novo acima de 400 |
| O pacote macOS não embute Python e não é notarizado | Tem só assinatura ad hoc. `--verificar-dependencias` explica e oferece instalar. `packaging/LEIA-ME.md` explica como abrir um app sem certificado da Apple |
| Linux | Código e CI existem, sem versão publicada até o aceite em um desktop real |
| Idioma da interface | A interface e as mensagens de erro estão em português |
| Os formatos JSONL do Claude Code e do Codex mudam sem aviso | Leitura tolerante: linha estranha vira `parse_errors` e a leitura segue. As fixtures vêm de sessões reais |
| Pareamento do Codex | Não existe vínculo exato no Codex 0.166.0, nem hook estável. O pareamento é por pasta e horário, então duas sessões do Codex iniciadas na mesma pasta com menos de 60 segundos de diferença podem trocar de aba |
| Rollouts `.jsonl.zst` | Lidos pelo comando `zstd` quando existe, sempre do início. Senão são ignorados e contados no `--doctor` |
| Gemini CLI e Cursor CLI | Não têm suporte. `procinfo.AGENT_EXECUTABLES` tem entradas para eles, mas não existe leitor |
| Comandos digitados | Comandos recuperados do histórico do shell pelas setas não são capturados |
| Comandos do Lerd que pedem senha de administrador | O app só chama a CLI e mostra a saída. Nunca pede nem guarda senha |
| CLI ou API do Lerd mudam entre versões | Os parsers são testados contra fixtures, e uma falha mostra a saída bruta |
| Token do servidor | Outro processo do mesmo usuário pode ler a memória do app. Fora do modelo de ameaça |
| Chave criada por `/usr/bin/security` | Outros processos do mesmo usuário podem conseguir lê-la pelo `security`. Limitação do macOS |
| `core/tables.py` | Coberto por testes, sem quem o chame em produção hoje |
| Ponto de entrada de reserva | `python3 -m vulcan_celox` sem opção abre a interface tkinter antiga, e `--tk` não tem efeito próprio |
| Custo | Estimativa no preço da API. A tabela padrão envelhece, e o `precos.json` a sobrescreve |

## 18. Como estender

Cada arquivo novo precisa ficar abaixo de 400 linhas, e o Python precisa continuar compatível com 3.9. Leia também [development.md](development.md). Mudança de comportamento atualiza a documentação nas duas línguas.

### Adicionar uma rota da API

1. Em `server/<área>_api.py`, ou em um módulo novo com `register_<área>_api(app)`:

   ```python
   def register_exemplo_api(app):
       srv = app.server

       @srv.route("GET", r"/api/exemplo/(?P<name>[a-z0-9-]+)")
       def detail(req):
           if req.arg("x") == "bad":
               raise HttpError(400, "x inválido")
           return {"name": req.params["name"]}
   ```

   `req.params` guarda os grupos nomeados, `req.arg(nome)` a query e `req.json()` o corpo. Devolva dados, `(status, dados)` ou `RawResponse`.
2. Em um módulo novo, chame `register_exemplo_api(self)` em `VulcanApp.__init__` (`server/app.py`), como os outros. As conferências de token, `Host`, `Origin` e Content-Type já valem.
3. Valide cada valor. O que chega a um comando vai em lista argv pelo runner, ou por uma tabela fixa. Valor que começa com `-` não pode virar opção.
4. Teste com `ServerTestCase` de `tests/server_helpers.py` e `FakeRunner`.
5. Acrescente a rota em [http-api.md](http-api.md), nas duas línguas.

### Adicionar uma tela

1. Crie `web/js/views/<nome>.mjs` com uma classe que recebe `(root, options)` e, conforme a necessidade, `update(state)`, `reveal(route)`, `command(name)`, `destroy()`. Escape os dados mostrados com `esc` de `dom.mjs`. Nada de recurso externo: a CSP bloqueia. Para repetir, use `every` de `api.mjs`, e pare em `destroy`.
2. Importe e acrescente um `case` em `web/js/view-mount.mjs`.
3. Para um item na barra lateral, acrescente em `NAV` (ou `AGENT_NAV`) e em um grupo de `NAV_GROUPS` em `web/js/app-state.mjs`. Rota com parâmetros também precisa de `parseRoute` em `web/js/app.mjs`.
4. Ligue a rota a uma seção da Ajuda em `ROUTE_SECTION` (`web/js/help-content.mjs`); `tests/test_help_routes.py` confere se toda rota da barra lateral está lá. Se a tela não recebe a lista de sites, acrescente em `KEEP_ON_SITES` em `web/js/remount.mjs`.
5. Acrescente a rota com os seletores esperados em `scripts/validate.sh`. A conferência de `#/overview` guarda o número de itens e grupos da barra lateral, então atualize ao acrescentar um.
6. Documente em `web/help/conteudo.json` e rode `python3 scripts/manual_md.py`.

### Adicionar um backend

1. Crie `core/backends/<nome>.py` com uma subclasse de `Backend`: `name`, `label`, `available = True`, `start`, `stop`, `restart`, `site_command(action, *args)` devolvendo `(argv, cwd)`, e `share_argv`. Sobrescreva conforme a necessidade: `status`, `list_sites`, `php_versions`, `version`, `project_writes`, e `dashboard_url` se houver painel. `Backend` já fornece `link`, `secure`, `isolate` e os outros a partir de `site_command`, com validação.
2. Acrescente os locais e uma variável em `core/paths.py`, e a detecção em `detect_backend` (`core/backends/__init__.py`), na prioridade desejada.
3. Rode só por `self.runner`, para os testes poderem usar `FakeRunner`. Não edite arquivos globais da ferramenta.
4. `server/env_api.py` e `server/debug_api.py` exigem `name == "lerd"`, então essas telas ficam indisponíveis para outro backend, a menos que você as estenda.

### Adicionar um leitor de agente

1. Crie `core/agents/<nome>_reader.py` seguindo `claude_reader` e `codex_reader`: `new_session(path)` devolvendo um `AgentSession`, e uma classe com `agent`, `__init__(session, state)`, `state()` (serializável, para a leitura incremental), `feed(obj)` (uma linha já lida) e `drain_usage()`. Monte pelo `SessionBuilder`, exposto como `self.b`, porque `read_session` chama `reader.b.drain_events()`.
2. Registre em `_readers()` (`core/agents/reading.py`) e acrescente o id em `AGENTS` (`core/agents/model.py`).
3. Liste os arquivos em `core/agents/discovery.py` e inclua em `AgentWatcher.files()` e `roots()`. Acrescente em `core/agents/status.py` o que o `--doctor` deve mostrar.
4. Ponha ferramentas e padrões nas tabelas de `core/agents/rules.py`, não em `if`s no leitor.
5. Acrescente o comando em `RESUME_COMMANDS` (`server/agents_api.py`), que `resume` consulta direto, em `AGENT_COMMANDS` (`server/terminals_api.py`) e `NEW_TERMINAL_AGENTS` (`server/app.py`) se puder abrir pelo diálogo de novo terminal, em `_AGENT_COMMAND` (`core/agents/pairing.py`), em `AGENT_EXECUTABLES` (`core/procinfo.py`) e em `AGENT_LABELS` (`core/session_memory.py` e `core/prompts.py`).
6. Acrescente os preços em `core/agents/pricing.py`, com a fonte e a data.
7. Acrescente fixtures de sessões reais anonimizadas em `tests/fixtures/agents/`. Os testes nunca podem ler a pasta real.
8. Leia em stream, por linha, e nunca escreva na pasta do agente. Atualize [agent-file-formats.md](agent-file-formats.md).
