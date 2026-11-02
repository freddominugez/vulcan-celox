# Desenvolvimento

## Preparar

No macOS: Command Line Tools (`xcode-select --install`). Para a suíte em Linux: podman ou docker. Não há mais nada a instalar: nem `pip install`, nem `npm install`.

```bash
git clone https://github.com/freddominugez/vulcan-hub-painel.git
cd vulcan-hub-painel
bash scripts/build_app.sh
open "dist/Vulcan Terminal.app"
```

## Comandos do dia a dia

```bash
python3 -m vulcan_terminal --serve           # servidor, imprime VULCAN_PORT
python3 -m unittest discover -s tests -t .   # testes
python3 -m unittest tests.test_agents_api    # um arquivo
bash scripts/validate.sh                     # todos os sensores
bash scripts/test_linux.sh                   # suíte num contêiner Linux
bash scripts/build_app.sh                    # dist/Vulcan Terminal.app
bash scripts/install_app.sh                  # ~/Applications e atalho na Mesa
bash scripts/package.sh                      # pacotes em executaveis/
```

Use `VULCAN_TERMINAL_HOME=$(mktemp -d)` para manter seus dados reais longe dos experimentos e `VULCAN_KEYSTORE=memory` para deixar o Keychain de fora.

## Regras de código

A lista está em [CONTRIBUTING.pt-BR.md](../../CONTRIBUTING.pt-BR.md). O Python precisa continuar compatível com a 3.9: sem `match`, sem `X | Y` em anotação de runtime.

## Onde mudar o quê

| Para mudar | Olhe |
|------------|------|
| Uma tela | `web/js/views/<tela>.mjs`, `web/styles/` |
| Um endpoint | `server/<área>_api.py` |
| Lógica | `core/`, com um teste que não precisa de janela |
| Como a sessão é lida | `core/agents/claude_reader.py`, `codex_reader.py`, `rules.py` |
| Um tema novo | Um dicionário em `core/themes.py` |
| Preços de modelos | `core/agents/pricing.py`, com fonte e data |
| Texto da Ajuda | `web/help/conteudo.json`, depois `python3 scripts/manual_md.py` |
| Capturas da Ajuda | `scripts/manual_shots.sh` (fixtures e Lerd falso, nunca dado real) |

## Ver a interface sem uma pessoa

```bash
"dist/Vulcan Terminal.app/Contents/MacOS/vulcan-terminal" --snapshot out.png --route "#/agentes"
```

O `--snapshot` desenha uma rota em PNG e falha com erro de JavaScript, e o `--eval` roda um script na página. O `validate.sh` os usa como sensores.

## Lançar versão

1. Atualize `vulcan_terminal/__init__.py`, o workflow em `.github/workflows/`, os `README` e o registro de mudanças nas duas línguas.
2. `bash scripts/validate.sh` e `bash scripts/test_linux.sh`.
3. `bash scripts/package.sh`, `bash scripts/install_app.sh`.
4. Tag, push, Release com os pacotes e o `SHA256SUMS`; depois baixe e confira as somas.

Até o aceite no Linux, as Releases levam só os arquivos do macOS.
