# Testes

`bash scripts/validate.sh` é o sensor único: **o código de saída decide**. Na versão 1.0.0 ele rodou 701 testes.

## O que o validate.sh roda

| Passo | Confere |
|-------|---------|
| `compileall` | Sintaxe do Python |
| Comparação do manual | `docs/pt-BR/user-guide.md` igual ao que o `scripts/manual_md.py` gera |
| `unittest` | Suíte inteira, no Python atual e no Python 3.9 do sistema |
| `--selftest` | Reserva em tkinter, também com Lerd falso e painel fora do ar |
| Build do bundle | `swiftc`, `plutil`, o ícone |
| Snapshot nativo | App real desenhando rotas em PNG |
| Telas com Lerd falso | Seletores começam como erro e só saem quando aparecem |
| Texto digitado sobrevive | Campos do compositor enquanto a lista de sites muda |
| Janela presa | A janela fica na origem do app |
| Pasta hostil | O servidor não importa módulo da pasta atual |
| Instalação | Instala em pastas temporárias |

`bash scripts/test_linux.sh` roda a suíte num contêiner `python:3.9-slim` (podman ou docker). O GitHub Actions também gera os pacotes de Linux, confere os hashes e instala o `.deb` no Ubuntu 22.04.

## Princípios

- **O sensor decide, não quem escreveu.** Um item do contrato está pronto quando o sensor dele está verde.
- **Falha primeiro.** A correção começa por um teste que reproduz o defeito e falha.
- **Não enfraquecer teste.**
- **Fixtures reais.** `tests/fixtures/agents/` tem sessões reais anonimizadas do Claude Code e do Codex, e casos sintéticos marcados.
- **Nunca tocar no mundo real.** Os testes usam `VULCAN_CELOX_HOME`, `tests/tools/fake_lerd_api.py` e `tests/tools/fake-lerd`. Nunca leem o `~/.claude` nem o `~/.codex` reais e nunca tocam no Lerd real.
- **Vigiar o vigia.** Sensor que passa sem verificar nada é defeito. Os roteiros de snapshot levam uma marca que falha se o roteiro não rodou.

## Aceite de ponta a ponta

`tests/test_aceite_pareamento.py` percorre o caminho aba, sessão, prompt com PTY real, shell real e um executável `claude` falso que grava uma sessão. Não roda os agentes de verdade, porque gastaria cota e gravaria nas pastas reais.


## Escrever um teste

Use `unittest`, só biblioteca padrão. Para o que roda processo, use o `FakeRunner`. Para uma tela, acrescente uma rota com seletores ao `validate.sh`. Os testes de servidor em `tests/` usam uma classe base que sobe um servidor real numa porta livre, com pasta de dados temporária.
