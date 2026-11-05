# Arquitetura

Visão geral. A referência detalhada, mantida em dia por um teste, é o [manual técnico](technical-manual.md).

## O desenho

```
Casca nativa (Swift + WKWebView)         Casca Linux e Windows (GTK + WebKit, ou Edge/Chromium --app)
        | inicia, com um token                     |
        v                                          v
Servidor Python em 127.0.0.1  <-- JSON + WebSocket --> Interface web (sem build, xterm.js)
        |
        +-- core/            lógica sem interface
        +-- core/agents/     lê JSONL -> índice SQLite
        +-- PTYs             terminais reais
        |
        +-- lê ~/.claude, ~/.codex (por linha, só leitura)
        +-- chama a CLI lerd / valet e a API do Lerd
        +-- escreve só na própria pasta de dados
```

Abertura: o executável Swift gera um token aleatório, inicia `python3 -m vulcan_celox --serve` na pasta de recursos com o token no ambiente, lê `VULCAN_PORT=<n>` do stdout e carrega `http://127.0.0.1:<n>/` numa WKWebView, com o token disponível só para essa origem. Fechar o app encerra o servidor e os PTYs. Se o processo pai morrer, o servidor grava as memórias em até 3 segundos e sai.

## Pilha e motivo

| Escolha | Motivo |
|---------|--------|
| Python 3.9 stdlib, zero pip | Roda no Python que o Mac já tem; nada a instalar; fácil de testar |
| Interface web sem build | Nenhuma cadeia de ferramentas para manter; módulos carregados direto |
| Casca fina em Swift, sem Electron | Menus e janelas nativos em poucos megabytes |
| xterm.js 6 (vendorizado, MIT) | Emulador de terminal de verdade |
| SQLite com FTS5 | Índice descartável e busca sem acento |
| Lerd, depois Valet, depois modo local | Orquestrar ferramentas MIT em vez de refazer PHP, nginx e DNS |

## Decisões que valem como regra

| # | Regra |
|---|-------|
| D1 | Núcleo Python 3.9 stdlib, casca Swift, interface web sem build |
| D2 | Orquestrar, não reimplementar: Lerd ou Valet como backend. O Herd é comercial e nunca é backend |
| D3 | Não alterar serviços do sistema nem arquivos globais dessas ferramentas |
| D4 | `core/` não tem código de interface. Um teste garante |
| D5 | Subprocess só por `core/runner.py`, como lista argv. `shell=True` nunca é usado; `run_shell` chama o shell de login com `-lc` |
| D6 | Persistência JSON atômica (`tempfile` + `os.replace`, `schema_version`). Arquivo corrompido vira `*.corrupt-<ts>` |
| D7 | Nada é apagado de vez. Um teste varre o fonte atrás de `shutil.rmtree` e `rm -rf` |
| D8 | Sensores só com biblioteca padrão e ferramentas do sistema |
| D9 | Implementação própria, sem ativos copiados do Herd |

## Pastas

| Caminho | O que é |
|---------|---------|
| `packaging/macos/` | Casca macOS: janelas, menus, item na barra de menu, `--snapshot`, `--eval` |
| `vulcan_celox/core/` | Store, runner, PTY, backends, sites, caderno, memória, máscara de segredos, prompts, temas, harness, Node |
| `vulcan_celox/core/agents/` | Descoberta, stream JSONL, leitores do Claude e do Codex, builder, índice, histórico, observador, loops, repos, pareamento, preços, uso |
| `vulcan_celox/server/` | Servidor HTTP e WebSocket e um `*_api.py` por área |
| `vulcan_celox/web/` | `index.html`, `styles/`, `js/`, `js/views/`, `help/`, `vendor/` |
| `vulcan_celox/desktop_linux.py`, `desktop_windows.py` | Cascas Linux e Windows |
| `vulcan_celox/ui/` | Interface tkinter antiga, só reserva |
| `scripts/` | `validate.sh`, `test_linux.sh`, `build_app.sh`, `install_app.sh`, `package.sh` |
| `packaging/linux/` | Lançador, atalho de menu, ícones e controle do `.deb` |
| `tests/` | Suíte `unittest`, fixtures, Lerd falso |

## Painel de Agentes

1. `discovery` acha os arquivos de sessão. `jsonl_stream` lê por linha e guarda o offset, tolerando última linha cortada, JSON inválido, linha acima de 5 MB e arquivo que encolheu.
2. `claude_reader` e `codex_reader`, com a tabela `rules`, transformam linhas em eventos. `builder` monta a `AgentSession`.
3. `index` guarda resumos, eventos com FTS5 e uso por turno em `agentes.db`. O índice é descartável; o JSONL é a fonte da verdade.
4. `watcher` consulta com `os.stat` a cada 2 segundos, com debounce de 300 ms, fora do lock. A interface consulta um número de revisão e só recarrega quando ele muda.
5. `repos` lê o git só com `-c core.fsmonitor=false --no-optional-locks`, para que analisar um repositório nunca rode os hooks dele. `loops` marca o mesmo teste repetido sem commit. `pairing` liga aba e sessão.

## Terminais

Um PTY real por aba (`os.forkpty`, ou ConPTY no Windows), com o shell do usuário em modo login. Uma thread leitora por PTY guarda até 256 KB de histórico. O WebSocket `/ws/terminals/<id>` leva entrada e saída em quadros binários, e `resize`, `input` e `exit` em JSON. Cada cliente tem fila limitada (4 MB) e thread de envio própria; quem não acompanha é desligado sem parar a leitora. O token do servidor é tirado do ambiente da aba.

A memória da sessão é mascarada ao gravar (`core/redact.py`), antes do corte de 2.000 linhas. Entrada digitada com eco desligado em modo canônico é um pedido de senha e fica fora da lista de comandos.

## Seus dados

`core/backup.py` grava um `.zip` da pasta de dados, com o SQLite copiado pela API de backup dele. A restauração valida o zip e o extrai ao lado dos dados, e a troca roda no próximo início, antes de qualquer leitura. `core/update_check.py` lê no GitHub a versão da última Release estável, no máximo uma vez por dia, com o `gh` do usuário como alternativa.

## Dívida conhecida

Seis arquivos acima de 400 linhas estão travados por teste e não podem crescer: `packaging/macos/main.swift`, `ui/app.py`, `web/js/views/tasks.mjs`, `core/notebook.py`, `core/harness.py`, `web/js/views/site.mjs`. Os riscos estão na seção 17 do [manual técnico](technical-manual.md).
