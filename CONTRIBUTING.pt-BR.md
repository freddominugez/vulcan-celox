# Como contribuir

Versão em inglês: [CONTRIBUTING.md](CONTRIBUTING.md).

Obrigado pelo interesse. Relatos de defeito, testes em outras máquinas (principalmente **Linux com área de trabalho**) e correções na documentação são as contribuições mais úteis agora.

## Antes de começar

- Abra uma issue antes de mudanças grandes, para combinarmos o escopo.
- Leia [docs/pt-BR/development.md](docs/pt-BR/development.md) para preparar o ambiente e [docs/pt-BR/architecture.md](docs/pt-BR/architecture.md) para a estrutura.
- Issues e pull requests são bem-vindos em português ou inglês.

## Regras duras

São conferidas por teste ou na revisão. Pull request que as quebra não entra.

- Só biblioteca padrão do Python 3.9. Nada de dependência pip.
- Sem etapa de build em `vulcan_celox/web/` e sem recurso externo na interface. Só o xterm.js e seus addons oficiais MIT são vendorizados.
- `vulcan_celox/core/` não importa tkinter. Subprocess só por `core/runner.py`; `shell=True` só em `run_shell`.
- O servidor só atende em `127.0.0.1`, com token obrigatório.
- Nunca escrever em `~/.claude`, `~/.codex`, `~/.claude.json` ou `~/.codex/config.toml`. Arquivos de sessão só em stream, linha por linha. A única exceção é o `--instalar-hook`, rodado pelo usuário.
- Sem exclusão definitiva (`shutil.rmtree`, `rm -rf`). Pastas vão para a Lixeira.
- Não editar arquivos globais do Lerd, do Valet ou do Herd. Escrita em pasta de projeto só com opt-in e dentro de bloco marcado.
- O Herd é comercial: nunca copiar binários, extensões, ícones ou textos dele, nem usá-lo como backend.
- Nenhum arquivo acima de 400 linhas (`tests/test_tamanho_arquivos.py`). As exceções existentes estão no teste e não podem crescer.
- Texto gerado sem travessão.

## Pull requests

1. Escreva primeiro um teste que falha, depois a correção.
2. Rode `bash scripts/validate.sh` num Mac antes de abrir o pull request. Enquanto o repositório for privado, essa rodada local é a conferência do macOS: os pull requests rodam Linux, Windows e lint automaticamente, e o workflow de macOS roda só sob demanda. No Linux, ou para testar o Linux a partir do Mac, rode `bash scripts/test_linux.sh`.
3. Uma mudança lógica por commit. Mensagens no formato `tipo(escopo): resumo`, por exemplo `fix(terminal): ...`.
4. Atualize a documentação atingida, nas duas línguas quando a página existir nas duas. Não edite `docs/pt-BR/user-guide.md` à mão: ele é gerado de `vulcan_celox/web/help/conteudo.json` por `scripts/manual_md.py`.
5. Nunca enfraqueça um teste para passar. Se o comportamento mudou de propósito, explique no pull request.

## Usando ferramentas de IA

Contribuições assistidas por IA são bem-vindas. A responsabilidade pelo que você envia continua sua: rode os sensores, leia o diff e diga no pull request o que foi conferido e o que não foi.

## Fixtures de teste

Anonimize caminhos, e-mails e tokens (`/Users/dev/projeto`). Testes nunca leem o `~/.claude` nem o `~/.codex` reais.

## Licença

Ao contribuir, você concorda que sua contribuição fica sob a [Licença MIT](LICENSE).
