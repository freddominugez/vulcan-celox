# API HTTP interna

Esta API existe para a própria interface do app. **Não é um contrato público** e pode mudar em qualquer versão. Está documentada para ajudar a depurar e estender o app. A fonte da verdade são as declarações `@srv.route` em `vulcan_terminal/server/`, e o `tests/test_docs_api.py` falha quando uma rota falta nesta página ou aparece aqui sem existir.

Veja [security.md](security.md) para o modelo de ameaças e [configuration.md](configuration.md) para as variáveis de ambiente.

## Como chamar

```bash
export VULCAN_TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
python3 -m vulcan_terminal --serve     # imprime VULCAN_PORT=<n>
curl -H "X-Vulcan-Token: $VULCAN_TOKEN" http://127.0.0.1:<n>/api/state

curl -X POST -H "X-Vulcan-Token: $VULCAN_TOKEN" -H "Content-Type: application/json" \
     -d '{"title": "Revisar o log"}' http://127.0.0.1:<n>/api/tasks
```

`--port <n>` escolhe a porta; o padrão é uma livre, aleatória. `VULCAN_TOKEN` precisa ter pelo menos 32 caracteres, senão o servidor não sobe. Sem a variável, o servidor gera um token e não o imprime, então defina a variável quando quiser chamar a API à mão.

## Regras gerais

As verificações rodam nesta ordem em toda requisição:

1. **Host.** O servidor escuta só em `127.0.0.1`. O cabeçalho `Host` precisa ser `127.0.0.1:<porta>` ou `localhost:<porta>`, senão 421. Isso vale também para os arquivos estáticos.
2. **Token.** Tudo em `/api/` e `/ws/` exige o cabeçalho `X-Vulcan-Token`, senão 401. Token na query é ignorado em `/api/`. Só `/ws/` aceita também `?token=`, porque o navegador não define cabeçalhos ao abrir um WebSocket.
3. **Origem.** Se houver cabeçalho `Origin`, ele precisa ser `http://127.0.0.1:<porta>` ou `http://localhost:<porta>`, senão 403. O servidor não envia cabeçalhos CORS.
4. **JSON na escrita.** `POST`, `PUT` e `PATCH` em `/api/` exigem `Content-Type: application/json`, senão 415, mesmo quando a rota não lê corpo. `DELETE` não exige e recebe os parâmetros na query.

Corpo:

- Corpo vazio vale como `{}`.
- O corpo precisa ser um objeto JSON, senão 400. JSON inválido também é 400.
- O limite é 1 MiB, senão 413.

Respostas:

- Sucesso é JSON com `Cache-Control: no-store`. A única exceção é `GET /api/agents/usage.csv`, um download em CSV.
- Erros vêm em JSON: `{"error": "..."}`, com mensagens em português. Alguns erros trazem campos de que a interface precisa, como `needs_terminal`, `needs_confirmation`, `needs_parent`, `suggestion` ou `missing`. Esses campos estão indicados nas tabelas abaixo.
- As rotas marcadas com "resultado do comando" devolvem `{"ok": bool, "code": int, "output": "..."}` com status 200, mesmo quando o comando falhou. Leia `ok`, não o status. `output` traz as últimas linhas da saída.
- As rotas marcadas com "aba" rodam um comando demorado numa aba de terminal nova e devolvem 201 com a descrição do terminal (`id`, `title`, `site`, `cwd`, `alive`, `theme`, `command` e outros).

Arquivos estáticos: qualquer caminho fora de `/api/` e `/ws/` serve a interface, só com `GET` e sem token. Os arquivos são lidos uma vez, quando o servidor sobe.

### Códigos de status

| Código | Significa |
|--------|-----------|
| 200 | Sucesso |
| 201 | Criado, ou uma aba de terminal foi aberta |
| 202 | Tarefa em segundo plano aceita (documentação com IA) |
| 400 | Parâmetro ou corpo inválido |
| 401 | Token ausente ou inválido, ou token só na query de `/api/` |
| 403 | `Origin` não permitida |
| 404 | Rota ou item não encontrado |
| 405 | O caminho existe, mas não com este método |
| 409 | Conflito de estado, como prompt sem agente na aba (`needs_terminal`) ou sem Lerd nem Valet disponível |
| 410 | Nada para desfazer |
| 413 | Corpo acima de 1 MiB |
| 415 | Escrita sem `Content-Type: application/json` |
| 421 | `Host` não permitido |
| 500 | Erro interno, ou um comando do sistema falhou |
| 502 | O Lerd recusou a operação |
| 503 | A aba não leu o texto colado |

### Parâmetros de caminho

| Parâmetro | Valores aceitos |
|-----------|-----------------|
| `<sid>` em `/api/agents/sessions/` e `/api/debug/agent/` | Id de sessão de agente: começa com letra ou dígito, depois letras, dígitos, `.`, `_` ou `-`, até 80 caracteres |
| `<sid>` em `/api/sessions/` e `/api/ai/` | Id de sessão de terminal: hexadecimal minúsculo |
| `<tid>`, `<nid>` | Id de terminal, tag, tarefa ou nota: hexadecimal minúsculo |
| `<name>` em `/api/sites/` | Começa com letra ou dígito, depois letras, dígitos, `.`, `_` ou `-`, até 100 caracteres |
| `<name>` em `/api/node-projects/` | Começa com letra minúscula ou dígito, depois letras minúsculas, dígitos, `.`, `_` ou `-`, até 64 caracteres |
| `<version>` | PHP: 3 ou 4 caracteres de dígitos e pontos, como `8.4`. As rotas `ini` aceitam também `shared`. Node: `22`, `20.11` ou `lts` |

## Rotas

### App

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/state` | App, backend, estado do ambiente, início automático, sites, favoritos e progresso | | |
| GET | `/api/app/build` | Versão e impressão digital da interface carregada e da instalada | | |
| PATCH | `/api/preferences` | Mudar preferências | `autostart_env` (bool), `new_terminal` (`skip_folder`, `agent`) | 400 |
| POST | `/api/open` | Abrir algo fora do app | `kind`: `url`, `dashboard`, `finder`, `editor`, `prompt`, `source` ou `file`; `target` | 400, 404, 409, 500 |
| GET | `/api/guide` | Passos do guia do Início | | |
| PUT | `/api/guide` | Pular ou restaurar o guia | `skipped` (bool) | 400 |
| GET | `/api/themes` | Temas das abas, rotação, temas em uso e preferências de terminal | | |

`POST /api/open` limita cada `kind`: `url` exige `http://` ou `https://`; `finder` e `editor` exigem pasta existente, e `finder` recusa pacotes de aplicativo; `prompt` abre só arquivos `.md` de uma pasta de prompts; `source` abre só arquivos dentro de um site registrado; `file` abre só arquivos `.md` da pasta de dados do app.

### Agentes

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/agents/revision` | Revisão do índice, última varredura e último erro | | |
| GET | `/api/agents/sessions` | Lista de sessões com KPIs, projetos e pastas lidas | Query: `agent`, `project`, `cwd`, `active`, `unpublished` (`1` ou `true`) | |
| GET | `/api/agents/sessions/<sid>` | Detalhe da sessão, eventos, custo estimado e linha do harness | Query: `from` (padrão 0), `limit` (padrão 200, de 1 a 1000) | 400, 404 |
| POST | `/api/agents/sessions/<sid>/resume` | Retomar a sessão numa aba nova | | 201, 404, 409 |
| GET | `/api/agents/history` | Busca no histórico das sessões | Query: `q`, `kind` (`pedidos`, `respostas`, `comandos`, `arquivos`), `agent`, `project`, `limit` (padrão 100, de 1 a 500) | 400 |
| GET | `/api/agents/repos` | Estado git dos projetos, só leitura, com cache de 30 segundos | Query: `fresh` (`1` ou `true` limpa o cache) | |
| GET | `/api/agents/paired` | Sessão de agente pareada com uma aba | Query: `terminal` | |
| GET | `/api/agents/current` | Sessão atual e contexto dos prompts | | |
| PUT | `/api/agents/current` | Escolher a sessão atual | `session_id` (texto, ou `null` para automático) | 400, 404 |
| POST | `/api/agents/refresh` | Varrer os arquivos de sessão agora | | |

### Uso

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/agents/usage` | Tokens e custo estimado por grupo, com o total | Query: `from`, `to` (`AAAA-MM-DD`, dias locais; o padrão são os últimos 30 dias, no máximo 400), `group` (`day` por padrão, `project`, `model`, `agent`, `session`) | 400 |
| GET | `/api/agents/usage.csv` | O mesmo relatório como download em CSV | A mesma query, com `group` em `session` por padrão | 400 |

### Prompts

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/prompts` | Prompts renderizados com o contexto de uma sessão | Query: `session`, `terminal`, `cwd`, `pinned` (`1` ou `true`) | 404 |
| POST | `/api/prompts` | Criar um arquivo de prompt | `title`, `category`, `scope` (`global` ou `project`), `project_root`, `confirm_project_dir` | 400, 409 (`needs_confirmation`, `dir`) |
| POST | `/api/prompts/categories` | Criar uma categoria | `name`, `scope`, `project_root`, `confirm_project_dir` | 400, 409 (`needs_confirmation`, `dir`) |
| POST | `/api/prompts/send` | Colar um prompt na aba pareada à sessão, sem Enter | `prompt`, `session`, `values` (nome para texto) | 400 (`missing`), 404, 409 (`needs_terminal`, `session`), 503 (`terminal`) |

O escopo de projeto vale só para a pasta de um site, de um projeto Node salvo ou de uma sessão de agente indexada, e nunca para as pastas de dados dos próprios agentes.

### Terminais

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/terminals` | Abas abertas | | |
| POST | `/api/terminals` | Abrir uma aba | `site`, `cwd`, `command`, `theme` (um nome ou `auto`), `agent` (`shell`, `claude` ou `codex`), `title`, `rows`, `cols` (de 1 a 1000; padrão 24 por 80) | 201, 400, 404 |
| PATCH | `/api/terminals/<tid>` | Renomear a aba | `title` (até 60 caracteres) | 404 |
| DELETE | `/api/terminals/<tid>` | Fechar a aba e gravar a memória | | 404 |
| GET | `/api/terminals/<tid>/busy` | Se a aba tem processos filhos rodando | | 404 |
| GET | `/api/terminals/<tid>/public-url` | Primeira URL de túnel na saída da aba de um site compartilhado | | 404 |

O WebSocket de cada aba está descrito em [WebSocket](#websocket).

### Sessões de terminal

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/sessions` | Sessões abertas e encerradas | Query: `site` (`*` para todos; vazio é Global) | |
| GET | `/api/sessions/tree` | Sessões com tarefas e notas, para a barra lateral | Query: `closed` (de 0 a 200, padrão 30) | 400 |
| GET | `/api/sessions/<sid>` | Detalhe da sessão, últimos 200 comandos e memória | | 404 |
| PATCH | `/api/sessions/<sid>` | Mudar título ou tags | `title`, `tags` | 400, 404 |
| DELETE | `/api/sessions/<sid>` | Apagar uma sessão encerrada; memória e documentação vão para a Lixeira | Query: `items` (`keep` por padrão, ou `delete`) | 400, 404, 409 |
| GET | `/api/sessions/<sid>/doc` | Documentação gerada da sessão | | 404 |
| GET | `/api/index/general` | Índice geral das sessões, em Markdown | | |
| GET | `/api/index/documentation` | Documentação geral gerada | | 404 |

### Sites

As rotas que precisam de backend devolvem 409 quando não há Lerd nem Valet. Toda rota com `<name>` devolve 404 para site desconhecido.

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/sites/suggest` | Sugerir um domínio a partir de uma pasta | Query: `path` | |
| POST | `/api/sites` | Registrar uma pasta ou estacionar uma pasta mãe (resultado do comando) | `kind` (`link` ou `park`), `path` (absoluto), `domain` (para `link`, sem `.test`) | 400 (`suggestion`), 409 |
| POST | `/api/sites/trash` | Mover para a Lixeira a pasta de um site já removido pelo app nesta execução | `name`, `confirm` (o nome exato) | 400, 409 |
| PATCH | `/api/sites/<name>` | Mudar HTTPS (resultado do comando), ou PHP ou Node (aba) | Um entre: `secured` (bool), `php`, `node` | 201, 400, 404, 409 |
| GET | `/api/sites/<name>/versions` | Opções de PHP, valores atuais e o que o backend escreve no projeto | | 404 |
| POST | `/api/sites/<name>/actions/<action>` | `db` ou `doctor` (aba), `dashboard` (abre o painel) | | 201, 404, 409, 500 |
| PUT | `/api/sites/<name>/favorite` | Marcar ou desmarcar a estrela de favorito | `favorite` (bool) | 400, 404 |
| POST | `/api/sites/<name>/share` | Túnel público numa aba; fechar a aba encerra o túnel | `tool` (opcional; no Lerd: `cloudflare`, `expose`, `ngrok`, `localhost-run`, `serveo`, `pinggy`) | 201, 400, 404, 409 |
| POST | `/api/sites/<name>/remove` | Tirar da lista ou desregistrar do backend (resultado do comando) | `level` (`list` ou `backend`), `parent` (confirma esquecer uma pasta mãe inteira) | 400, 404, 409 (`needs_parent`) |
| GET | `/api/sites/<name>/runtime` | PHP e Node do site, com cache de 30 segundos | | 404 |
| GET | `/api/sites/<name>/commands` | Comandos do projeto e comandos próprios | | 404 |
| POST | `/api/sites/<name>/commands` | Salvar um comando próprio | `command` (uma linha, até 500 caracteres), `label` | 201, 400, 404 |
| DELETE | `/api/sites/<name>/commands` | Apagar um comando próprio | Query: `command` | 404 |
| GET | `/api/sites/<name>/recent` | Últimos 20 comandos das abas do site | | 404 |
| GET | `/api/sites/<name>/log` | `storage/logs/laravel.log` em pedaços: o fim do arquivo, ou o que veio depois de um offset | Query: `offset` | 404 |
| POST | `/api/sites/<name>/lerd-logs/<target>` | Logs do Lerd numa aba | `<target>`: `php`, `nginx` ou um serviço instalado | 201, 404, 409 |

### Harness

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/sites/<name>/harness` | Contrato, itens, próximo passo e handoff do projeto, só leitura | | 404 |
| GET | `/api/sites/<name>/harness/install` | Lista exata dos arquivos que a instalação criaria; não grava nada | | 404, 409 |
| POST | `/api/sites/<name>/harness/install` | Instalar o formato mínimo. Arquivo existente nunca é sobrescrito | `confirm` (precisa ser `true`) | 400, 404, 409 |
| POST | `/api/sites/<name>/harness/tasks` | Novo contrato no formato mínimo, com aprovação pendente | `task_id`, `itens` (cada um com `faixa`, `objetivo`, `sensor`), `objetivo`, `fora`, `escrita`, `orcamento` | 400, 404, 409 |

### Ambiente

Fora as duas primeiras linhas, estas rotas precisam do Lerd e devolvem 409 sem ele.

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/environment` | Backend, componentes e serviços | | |
| POST | `/api/services/<action>` | Iniciar, parar ou reiniciar o backend | `<action>`: `start`, `stop`, `restart` | 404, 409 |
| POST | `/api/environment/services/<name>/<action>` | Agir sobre um serviço instalado (resultado do comando) | `<action>`: `start`, `stop`, `restart` | 404, 409 |
| GET | `/api/environment/php` | Versões de PHP instaladas e instaláveis | | 409 |
| POST | `/api/environment/php/<version>/<op>` | `use` (resultado do comando), `update` ou `install` (aba) | | 201, 400, 409 |
| GET | `/api/environment/xdebug` | Xdebug por versão e a porta dele | | 409 |
| POST | `/api/environment/php/<version>/xdebug` | Ligar ou desligar o Xdebug (aba) | `enabled` (bool), `mode` (`debug`, `coverage` ou `debug,coverage`), `on_demand` (bool) | 201, 400, 409 |
| GET | `/api/environment/php/<version>/ini` | Valores do `php.ini` de usuário | | 400, 409 |
| POST | `/api/environment/php/<version>/ini` | Mudar valores (resultado do comando) | `values` (chave para valor; `null` ou vazio limpa) | 400, 409 |
| POST | `/api/environment/php/<version>/ini/open` | Abrir o `php.ini` no editor do usuário (aba) | | 201, 400, 409 |
| GET | `/api/environment/php/<version>/extensions` | Extensões carregadas e declaradas, só leitura | | 400, 409 |
| GET | `/api/environment/node` | Versão padrão, gerenciador e versões de Node instaladas | | 409 |
| POST | `/api/environment/node/<version>/<op>` | `install` (aba), `use` ou `remove` (resultado do comando) | `confirm` (precisa ser `true` em `remove`) | 201, 400, 409 |

### Depuração

Estas rotas leem a ponte de dumps do Lerd e devolvem 409 sem ele, menos a última.

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/debug/events` | Eventos de dump | Query: `site`, `branch`, `kind`, `limit` (padrão 500, até 2000), `q`, `min_ms`, `group` (`1` agrupa por requisição) | 409 |
| GET | `/api/debug/bridge` | Estado da ponte | | 409 |
| PUT | `/api/debug/bridge` | Ligar ou desligar a ponte | `enabled` (bool) | 400, 409, 502 |
| POST | `/api/debug/clear` | Limpar os eventos | | 409, 502 |
| GET | `/api/debug/agent/<sid>` | Exceções e logs de erro do site da sessão, durante a sessão. Devolve `available: false` sem Lerd ou sem site correspondente | | 404 |

### Projetos Node

A lista é do app: tirar um projeto dela não toca na pasta.

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/node-projects` | Projetos salvos | | |
| POST | `/api/node-projects` | Adicionar uma pasta com `package.json` | `path` (absoluto), `name` | 400, 409 |
| GET | `/api/node-projects/suggest` | Pastas usadas por agentes que têm `package.json` e não estão na lista, até 12 | | |
| GET | `/api/node-projects/<name>` | Detalhe do projeto e scripts rodando | | 404 |
| POST | `/api/node-projects/<name>/run` | Rodar um script do `package.json` numa aba | `script` | 201, 400, 404, 409 |
| POST | `/api/node-projects/<name>/stop` | Mandar Ctrl-C para uma aba que roda script deste projeto; a aba fica aberta | `terminal` | 404, 409 |
| POST | `/api/node-projects/<name>/supabase/<action>` | Comando `supabase` numa aba | `<action>`: `start`, `stop`, `status`. O projeto precisa de `supabase/config.toml` | 201, 400, 404, 409 |
| POST | `/api/node-projects/<name>/remove` | Tirar da lista | | 404 |

### Documentação com IA

A chave nunca sai do servidor: as respostas mostram só a forma mascarada. Nada vai para a Anthropic a não ser por estas rotas de escrita.

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/ai/config` | Provedor, chave mascarada, modelo e modelos disponíveis | | |
| PATCH | `/api/ai/config` | Escolher o modelo | `model` | 400 |
| PUT | `/api/ai/key` | Validar a chave na Anthropic e guardá-la | `key` | 400, 500 |
| DELETE | `/api/ai/key` | Apagar a chave | | |
| GET | `/api/ai/preview/session/<sid>` | Tamanho e estatísticas do que seria enviado para uma sessão; não envia nada | | 404 |
| GET | `/api/ai/preview/general` | O mesmo para a documentação geral | | |
| POST | `/api/ai/docs/session/<sid>` | Gerar a documentação de uma sessão em segundo plano | | 202, 404, 409 |
| POST | `/api/ai/docs/general` | Gerar a documentação geral em segundo plano | | 202, 409 |
| GET | `/api/ai/jobs` | Gerações e quantas estão rodando | | |

As respostas 409 significam que não há chave configurada, que já existe uma geração em andamento para o mesmo item ou (documentação geral) que ainda não há sessões de terminal.

### Caderno

Id desconhecido devolve 404. Valor inválido devolve 400. Em `site`, `*` significa todos os sites, e vazio ou ausente significa Global.

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/tags` | Tags, paleta, uso e progresso | | |
| POST | `/api/tags` | Criar uma tag | `name`, `color` | 201, 400, 409 |
| PATCH | `/api/tags/<tid>` | Renomear ou mudar a cor | `name`, `color` | 400, 404, 409 |
| DELETE | `/api/tags/<tid>` | Apagar uma tag de todos os itens | | 404 |
| GET | `/api/notes` | Notas | Query: `site`, `q`, `tag`, `terminal` | |
| POST | `/api/notes` | Criar uma nota | `text`, `color` (padrão `amarelo`), `tags`, `site`, `terminal` | 201, 400, 404 |
| PATCH | `/api/notes/<nid>` | Mudar uma nota | `text`, `color`, `pinned`, `terminal`, `tags` | 400, 404 |
| POST | `/api/notes/<nid>/move` | Reordenar | `target` (id de uma nota) ou `index` | 400, 404 |
| DELETE | `/api/notes/<nid>` | Apagar | | 404 |
| GET | `/api/tasks` | Tarefas, progresso, resumo e `can_undo` | Query: `site`, `status` (lista por vírgula de `todo`, `doing`, `done`), `tag`, `sort` (`priority`, `due`, `manual`, `assignee`), `terminal`, `assignee`, `due` (`late`, `today`, `week`) | |
| GET | `/api/tasks/assignees` | Responsáveis com contagem de abertas e total | | |
| POST | `/api/tasks` | Criar uma tarefa | `title`, `priority` (padrão 2), `tags`, `due` (`AAAA-MM-DD`), `terminal`, `assignee`, `site` | 201, 400, 404 |
| PATCH | `/api/tasks/<tid>` | Mudar uma tarefa | `title`, `priority`, `due`, `status`, `assignee`, `terminal`, `tags` | 400, 404 |
| POST | `/api/tasks/<tid>/cycle` | Passar ao próximo status | | 404 |
| POST | `/api/tasks/<tid>/move` | Reordenar | `delta` | 400, 404 |
| DELETE | `/api/tasks/<tid>` | Apagar; dá para desfazer | | 404 |
| POST | `/api/tasks/undo` | Desfazer a última exclusão | | 410 |
| GET | `/api/progress` | Progresso geral, por site e por tag | | |
| GET | `/api/search` | Buscar em sites, tarefas, notas e tags | Query: `q` | |
| GET | `/api/index` | Índice global de tarefas em Markdown | | |
| GET | `/api/index/project` | Bloco de tarefas de um projeto e se está ligado | Query: `site` | |
| POST | `/api/index/project` | Ligar ou desligar a escrita do índice de tarefas na pasta do projeto | `site`, `enabled` | 400, 404 |

### Arquivos

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| GET | `/api/fs/folder` | Conferir uma pasta digitada; aceita `~` | Query: `path` | 400 |
| GET | `/api/fs/recent` | Pasta pessoal e até 12 pastas recentes | | |

## WebSocket

| Método | Caminho | Para quê | Parâmetros ou corpo | Status relevantes |
|--------|---------|----------|---------------------|-------------------|
| WS | `/ws/terminals/<tid>` | Entrada e saída de uma aba de terminal | Query: `token` (ou o cabeçalho `X-Vulcan-Token`) | 101, 400, 401, 403, 404 |

O handshake exige `Upgrade: websocket`, `Sec-WebSocket-Version: 13` e `Sec-WebSocket-Key`, senão 400. Aba desconhecida devolve 404.

| Direção | Quadro | Conteúdo |
|---------|--------|----------|
| Servidor para cliente | Binário | Saída do terminal. O histórico chega primeiro, antes de qualquer saída nova |
| Servidor para cliente | Texto | `{"type": "exit", "code": <n>}` quando o processo termina. Também é enviado ao conectar, se o processo já terminou |
| Cliente para servidor | Binário | Entrada do terminal |
| Cliente para servidor | Texto | `{"type": "input", "data": "..."}`: entrada do terminal como texto |
| Cliente para servidor | Texto | `{"type": "resize", "rows": <n>, "cols": <n>}`: de 1 a 1000 linhas e colunas; outros valores são ignorados |

Quadros de texto que não sejam um objeto JSON, ou com outro `type`, são ignorados. Uma mensagem tem limite de 16 MiB. Um cliente que fica mais de 4 MiB atrasado ao receber é desligado, para não segurar o terminal nem os outros clientes.
