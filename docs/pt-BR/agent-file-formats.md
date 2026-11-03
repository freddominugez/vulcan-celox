# Formatos dos JSONL do Claude Code e do Codex

Referência do parser de `vulcan_celox/core/agents/`. Base: leitura de arquivos reais em 30/10/2026 (Claude Code com `api-request-blob`, Codex CLI 0.166.0). Estes formatos são privados de cada ferramenta e mudam sem aviso, por isso a leitura é tolerante. **Quando o arquivo real divergir deste documento, o arquivo real vence**, e o parser e este documento mudam no mesmo commit.

Regra geral: o app só lê. Nunca escreve em `~/.claude`, `~/.codex`, `~/.claude.json` nem `~/.codex/config.toml`. A única exceção é o comando descrito em [pairing-hook.md](pairing-hook.md), rodado pelo usuário.

## Onde ficam

| Agente | Caminho | Variável |
|--------|---------|----------|
| Claude Code | `~/.claude/projects/*/*.jsonl` | `CLAUDE_CONFIG_DIR` |
| Sub-agentes do Claude Code | `agent-*.jsonl` e `<session-id>/subagents/*.jsonl`: contam para a sessão-mãe, não são sessão própria | |
| Codex | `~/.codex/sessions/AAAA/MM/DD/rollout-*.jsonl`, `archived_sessions/` | `CODEX_HOME` (separado por vírgula) |
| Codex comprimido | `*.jsonl.zst`, pelo comando `zstd` | `VULCAN_ZSTD_BIN` |

## Regras de leitura

- Leitura sempre em stream, por linha (`open(path, "rb")`), nunca o arquivo inteiro. O app guarda o offset em bytes e continua dele na leitura seguinte.
- Só contam linhas terminadas em quebra de linha. Uma última linha cortada, enquanto a sessão escreve, espera a próxima leitura.
- JSON inválido, valor que não é objeto e linha acima de 5 MB são descartados e registrados em `parse_errors`, e a leitura continua. O mesmo vale para uma linha que faça o leitor falhar.
- Arquivo que encolheu recomeça do zero.
- Tipos de linha desconhecidos são ignorados sem erro.
- Uma sessão está ativa quando o arquivo mudou há menos de 90 segundos **e** o último evento dentro dele tem menos de 10 minutos. A segunda condição existe porque copiar uma pasta muda a data dos arquivos, mas não a dos eventos.

## 1. Claude Code

### 1.1 Onde ficam

- `$CLAUDE_CONFIG_DIR/projects/<slug>/<session-id>.jsonl`, ou `~/.claude/projects/...` sem a variável.
- Slug: caminho absoluto do diretório de trabalho com todo caractere não alfanumérico trocado por `-`. `/Users/dev/projeto` vira `-Users-dev-projeto`. Worktrees em `.claude/worktrees/x` geram pasta própria terminando em `--claude-worktrees-x`.
- Ao lado do arquivo pode existir a pasta `<session-id>/` com `subagents/` e `tool-results/`.
- O Claude Code apaga sessões com mais de 30 dias por padrão (`cleanupPeriodDays` em `~/.claude/settings.json`). O índice do app guarda o resumo para além disso.

### 1.2 Linhas que importam

| `type` | Uso |
|--------|-----|
| `user` com `message.content` texto | Pedido do usuário (turno). Ignorar `isMeta: true`, `isSidechain: true` e textos que começam com `<command-name>`, `<command-message>`, `<command-args>`, `<local-command-`, `<system-reminder>`, `Caveat:` ou `[Request interrupted` |
| `user` com `content` lista | Blocos `text` contam como pedido; blocos `tool_result` são só resultado de ferramenta |
| `assistant` | `message.model`, `message.id`, `message.usage`, `message.content[]` com `text`, `thinking`, `tool_use` (`id`, `name`, `input`) |
| `ai-title` | `aiTitle`: título da sessão gerado pelo próprio Claude Code |
| `api-request-blob`, `api-request`, `api-request-shape` | Cópia do que foi enviado à API. **Ignorar**: repetem mensagens e ferramentas e duplicariam contagens |
| `attachment`, `system`, `mode`, `permission-mode`, `last-prompt`, `queue-operation`, `file-history-snapshot`, `file-history-delta`, `tools-used`, `atis-latch` | Ignorar |

Campos comuns nas linhas `user` e `assistant`: `uuid`, `parentUuid`, `sessionId`, `timestamp` (ISO 8601), `cwd`, `gitBranch`, `version`, `isSidechain`.

### 1.3 Regras de parsing

- Tokens: um turno da API é gravado em várias linhas `assistant`, uma por bloco, todas com o mesmo `usage`. Deduplicar por `message.id`.
- Cache: `cache_creation_input_tokens` é o total gravado, e `cache_creation.ephemeral_1h_input_tokens` separa a parte de 1 hora; o resto é de 5 minutos. O modelo `<synthetic>` é mensagem do próprio Claude Code e fica fora do uso.
- Linhas `isSidechain` contam como atividade (data), mas não como conteúdo da sessão.
- Arquivos: `tool_use` com `name` `Edit`, `MultiEdit`, `NotebookEdit` (edição), `Write` (novo, ou edição se o arquivo já apareceu na sessão), `Read`, `NotebookRead` (leitura). Caminho em `input.file_path` ou `input.notebook_path`.
- Comandos: `Bash` (`input.command`).
- Publicação: heurística em comandos `git commit`, `git push`, `gh pr create`. As regras ficam em tabela em `core/agents/rules.py`, não em `if` espalhado. Um comando de publicação só conta quando o `tool_result` dele não voltou com `is_error`. Cada etapa exige a anterior desde a última edição: push precisa de commit, e PR precisa de push.

## 2. Codex CLI

### 2.1 Onde ficam

- `$CODEX_HOME/sessions/AAAA/MM/DD/rollout-AAAA-MM-DDTHH-MM-SS-<uuid>.jsonl` e `$CODEX_HOME/archived_sessions/`. `CODEX_HOME` pode ser lista separada por vírgula; sem a variável, `~/.codex`.
- Arquivos `.jsonl.zst` (comprimidos) são lidos em stream pelo comando `zstd`, sempre do início. O app procura o comando no `PATH` e em `/opt/homebrew/bin`, `/usr/local/bin` e `/usr/bin`; `VULCAN_ZSTD_BIN` escolhe outro, e vazio desliga. Sem o comando, são ignorados e contados no `--doctor`. Com o mesmo rollout nas duas formas, vale o `.jsonl`.
- Não há pasta por projeto: o projeto vem do `cwd` da primeira linha.

### 2.2 Envelope

`{timestamp, ordinal, type, payload}`. `ordinal` é monotônico.

| `type` / `payload.type` | Uso |
|-------------------------|-----|
| `session_meta` (primeira linha) | `payload.id` (usado em `codex resume`), `timestamp`, `cwd`, `cli_version`, `originator`, `source`. A origem separa as sessões de aba dos sub-agentes e do app desktop. Git (`git.branch` ou `git_branch`) quando presente; **no 0.166.0 não vem**, então a sessão fica sem branch e o app usa `git`, só leitura, ao montar a tela de repositórios e o contexto dos prompts. Sessão retomada pode ter segunda `session_meta`: vale a primeira |
| `turn_context` | `model`, `cwd` |
| `event_msg` / `item_completed` | **Fonte principal no 0.166.0**. `payload.item.type`: `UserMessage` (pedido, `content[].text`), `AgentMessage` (resposta), `CommandExecution` (`parsed_cmd[].cmd` ou `command[]`, `cwd` em URL `file://`, `exit_code`), `FileChange` (`changes`: caminho para `{type: add, update, delete, move_path}`) |
| `event_msg` / `user_message`, `agent_message` | Pedido e resposta em versões anteriores. O mesmo pedido pode chegar também como `UserMessage`: conta uma vez |
| `event_msg` / `token_count` | `info.total_token_usage` acumulado: `input_tokens`, `cached_input_tokens`, `output_tokens`, `cache_write_input_tokens`, `reasoning_output_tokens` |
| `response_item` / `function_call`, `custom_tool_call` | Versões anteriores: `apply_patch` (linhas `*** Add File:`, `*** Update File:`, `*** Delete File:`, `*** Move to:`), `shell`, `exec_command`, `container.exec`, `local_shell` (`arguments.command` lista ou texto). No 0.166.0 a ferramenta se chama `exec` e leva código JavaScript: ignorar, o `item_completed` já registra comandos e arquivos |
| `response_item` / `message` com `role: user` | Só como reserva quando não houver nenhum `UserMessage` nem `user_message`; ignorar textos que começam com `<` ou `#` (contexto injetado) |
| `token_usage_record`, `world_state`, `compacted`, `reasoning`, demais | Ignorar |

Tokens: `input_tokens` inclui os de cache, por isso a entrada é `input_tokens` menos `cached_input_tokens`. O total é acumulado: o consumo de cada evento é a diferença para o anterior, e um total menor recomeça a conta a partir dele.

Rollouts passam de centenas de MB em sessões longas: nunca carregar inteiro, manter só o resumo no índice.

## 3. Modelo normalizado (Python 3.9)

Os dois leitores produzem o mesmo modelo, em `core/agents/model.py`:

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional

PUBLISH_STATES = ("none", "committed", "pushed", "pr_open")
FILE_KINDS = ("edit", "new", "read", "delete")
COMMAND_KINDS = ("shell", "test", "publish")
EVENT_KINDS = ("user", "assistant", "command", "file")


@dataclass
class FileTouch:
    path: str            # absoluto
    kind: str            # FILE_KINDS
    first_at: str = ""   # ISO
    last_at: str = ""


@dataclass
class CommandRun:
    text: str
    at: str = ""
    kind: str = "shell"  # COMMAND_KINDS
    exit_code: Optional[int] = None


@dataclass
class AgentSession:
    id: str                       # sessionId ou payload.id
    agent: str                    # "claude" | "codex"
    file_path: str
    cwd: str = ""
    project_name: str = ""        # basename do repositório (sem o sufixo da worktree)
    project_root: str = ""        # raiz do repositório (sem a pasta da worktree)
    git_branch: Optional[str] = None
    worktree: Optional[str] = None
    title: Optional[str] = None
    started_at: str = ""
    last_activity_at: str = ""
    is_active: bool = False
    model: Optional[str] = None
    cli_version: Optional[str] = None
    turns: int = 0
    files: List[FileTouch] = field(default_factory=list)
    commands: List[CommandRun] = field(default_factory=list)   # últimos 200
    commands_total: int = 0
    published: str = "none"       # nível alcançado desde a última edição
    pr_opened: bool = False
    tokens: Optional[Dict[str, int]] = None  # input, output, cache_read, cache_write
    first_user_message: Optional[str] = None
    subagents: int = 0
    origin: str = ""              # subagent ou desktop quando a sessão não nasce de uma aba
    pairing_id: Optional[str] = None
    theme: Optional[str] = None
    loop_alert: Optional[Dict] = None        # {command, count, since}
    parse_errors: int = 0
    files_count: int = 0          # contagens do resumo leve do índice
    edited_count: int = 0


@dataclass
class SessionEvent:
    at: str
    kind: str              # EVENT_KINDS
    text: str
    tool: Optional[str] = None
```

`published` é o nível alcançado desde a última edição de arquivo: editar depois de um commit volta a `none`, para a trilha mostrar o que está sem conciliar. `pr_opened` lembra que houve `gh pr create`; com push depois da última edição, a trilha mostra PR.

## 4. Adicionar um agente

Hoje o app lê só o Claude Code e o Codex. Um leitor novo precisa de:

- `new_session(path)` e uma classe com `feed(obj)` e `state()`, como em `core/agents/claude_reader.py`, registrados em `_readers()` de `core/agents/reading.py`. `state()` guarda o que é preciso para continuar do offset. `drain_usage()` é opcional e entrega as linhas de uso.
- A descoberta dos arquivos em `core/agents/discovery.py` e em `AgentWatcher.files()`, em `core/agents/watcher.py`.
- Os efeitos das ferramentas como dados em `core/agents/rules.py`.
- O nome em `AGENTS`, em `core/agents/model.py`, e o comando de retomar em `RESUME_COMMANDS`, em `server/agents_api.py`.

Os testes usam as amostras de `tests/fixtures/agents/`. Veja [testing.md](testing.md).
