# Configuração

## Linha de comando

Do código-fonte, com `python3 -m vulcan_celox <opção>`.

| Opção | Faz |
|-------|-----|
| (nenhuma) | Abre a interface antiga em tkinter, um recurso de reserva. A interface principal vem do app compilado |
| `--serve [--port N]` | Só o servidor local; imprime `VULCAN_PORT` |
| `--doctor` | JSON com backend, ambiente, sites, agentes, preços e uso em 30 dias |
| `--reindexar-agentes` | Reconstrói o índice das sessões de agentes |
| `--podar-agentes [DIAS]` | Apaga eventos de sessões paradas há mais de DIAS (padrão 180). Nunca é automático. Os resumos ficam |
| `--instalar-hook` | Acrescenta o hook de pareamento ao `~/.claude/settings.json`, com backup |
| `--tk` | Interface tkinter antiga (reserva) |
| `--selftest` | Teste rápido da interface tkinter |
| `--version` | Versão |

Casca nativa, como sensor:

```bash
"dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --snapshot out.png --route "#/overview"
```

Lançador do Linux: `vulcan-celox --check`, `vulcan-celox --instalar-dependencias`.

## Arquivos

| Caminho | Guarda |
|---------|--------|
| `~/Library/Application Support/VulcanCelox/` | Pasta de dados no macOS (0700; arquivos 0600) |
| `$XDG_DATA_HOME/vulcan-celox` | Pasta de dados no Linux |
| `%APPDATA%\VulcanCelox` | Pasta de dados no Windows |
| `<dados>/agentes.db` | Índice SQLite descartável das sessões de agentes |
| `<dados>/precos.json` | Seus preços; valem mais que a tabela embutida |
| `<dados>/code_roots.json` | Pastas escolhidas na tela Código, no máximo 50 |
| `<dados>/prompts/` | Prompts globais |
| `<dados>/sessoes/` | Memórias de sessão em Markdown |
| `<dados>/.app.lock` | Marca a pasta como em uso, para a restauração esperar a instância anterior sair. Não entra no backup |
| `<dados>/.restauros/` | Dados guardados por uma restauração, uma pasta por data. Não entram no backup |
| `<dados>/logs/` | `servidor.log` (log do servidor, 1 MB e 3 arquivos) e `servidor-erro.log` (saída de erro do processo, truncada na partida acima de 1 MB). Mascarados, 0600, fora do backup |
| `<dados>/pairings/` | Gravado pelo hook opcional |
| `<dados>/TAREFAS.md`, `INDICE.md` | Índices gerados |
| `<projeto>/.vulcan/prompts/` | Prompts do projeto, criados só com confirmação |
| `<projeto>/TAREFAS.md` | Opt-in, escrito só dentro de um bloco marcado |

Arquivo que não é JSON válido, ou banco corrompido, vira `*.corrupt-<data>` e o app sobe com o padrão. Arquivo válido com a forma errada é ignorado onde é lido, e o app abre mesmo assim.

## Variáveis de ambiente

| Variável | Efeito |
|----------|--------|
| `VULCAN_CELOX_HOME` | Pasta de dados (usada em teste) |
| `CLAUDE_CONFIG_DIR` | Pasta do Claude Code |
| `CODEX_HOME` | Pasta ou pastas do Codex, separadas por vírgula |
| `VULCAN_AUTOSTART=0` | Não inicia o Lerd junto com o app |
| `VULCAN_UPDATE_CHECK=0` | Nunca consulta versão nova (testes e capturas) |
| `VULCAN_AGENTS=0` | Não liga o índice de agentes |
| `VULCAN_LERD_BIN`, `VULCAN_VALET_BIN`, `VULCAN_ZSTD_BIN` | Caminho de cada ferramenta |
| `VULCAN_LERD_API`, `VULCAN_LERD_DATA`, `VULCAN_VALET_HOME` | Endereço da API do Lerd, dados do Lerd, pasta do Valet |
| `VULCAN_ANTHROPIC_BASE_URL` | Base da API da Anthropic (proxy ou servidor de teste) |
| `VULCAN_KEYSTORE=memory` | Guarda a chave na memória (testes e capturas) |
| `VULCAN_EDITOR` | Editor aberto pelo app |
| `VULCAN_PYTHON`, `VULCAN_PYTHON_ONLY=1` | Python usado pela casca do macOS; `ONLY` ignora os outros candidatos |
| `VULCAN_INSPECT=1` | Liga o inspetor web (só desenvolvimento) |
| `VULCAN_LINUX_MODE` | Força o modo de janela no Linux |
| `VULCAN_INSTALL_DEST`, `VULCAN_DESKTOP`, `VULCAN_UNIVERSAL=1` | Destino da instalação, pasta da Mesa, build universal |
| `VULCAN_LINUX_IMAGE` | Imagem do contêiner do `test_linux.sh` |

`VULCAN_LEGACY_HOME` aponta para os dados do protótipo antigo, para a migração. Definidas pelo próprio app, não são para você mudar: `VULCAN_TOKEN`, `VULCAN_PORT`, `VULCAN_WATCH_PARENT`, `VULCAN_PHP_INI_SET`. Dentro de cada aba de terminal o app define `VULCAN_SESSION_ID` e `VULCAN_THEME`.
