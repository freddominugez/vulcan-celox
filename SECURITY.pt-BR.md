# Política de segurança

Versão em inglês: [SECURITY.md](SECURITY.md).

## Versões com suporte

| Versão | Suporte |
|--------|---------|
| 1.1.x (macOS) | Sim |
| Anteriores | Não |
| Versões de teste 1.2.0 (Windows, Linux) | Ainda não estáveis; relatos são bem-vindos |

## Como relatar uma vulnerabilidade

Não abra issue pública. Use o relato privado do GitHub: **Security > Report a vulnerability** neste repositório, ou escreva para manager@byvulcan.com. Informe a versão, os passos para reproduzir e o impacto.

O projeto é mantido por uma pessoa, então não há prazo garantido de resposta. Os relatos são lidos assim que possível, e as correções dão crédito no registro de mudanças, se você quiser.

## Escopo

O modelo de ameaça está em [docs/pt-BR/security.md](docs/pt-BR/security.md). Interessa em especial:

- Acesso ao servidor local sem o token ou a partir de outra origem.
- Qualquer coisa que escreva em `~/.claude` ou `~/.codex`, ou que apague dados de vez.
- Execução de código a partir de uma pasta de projeto, de um arquivo de sessão ou de um prompt lido.
- Segredos chegando à Anthropic ou a um log apesar do mascaramento.

Fora do escopo, por decisão: outro processo do mesmo usuário ler a memória do app ou o item do Keychain, e rodar um app não assinado. Os dois estão documentados como riscos aceitos.
