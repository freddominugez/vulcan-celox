# Roadmap

[English](ROADMAP.md) | **Português**

Direção, não promessa. Como o projeto chegou aqui: [história do desenvolvimento](docs/pt-BR/history.md).

## Entregue na 1.0.0 (macOS)

Painel de agentes para Claude Code e Codex, busca no histórico, prompts, uso e custo, branches, aba Harness, terminais reais, sites PHP pelo Lerd ou Valet, projetos Node, caderno, Ajuda e manual. Detalhes no [registro de mudanças](CHANGELOG.pt-BR.md).

## Agora

- **Release para Linux.** Testar numa área de trabalho Linux Mint real, corrigir o que falhar e publicar `.deb` e `.tar.gz`. Ajuda é bem-vinda.
- **Aceite no Windows.** A versão de teste 1.2.1 só rodou nas máquinas da CI. Testar em Windows 10 e 11 reais e depois decidir sobre instalador e assinatura.
- **Terminar as conferências manuais no macOS:** pareamento com o Claude Code real, dividir, buscar e redimensionar.

## Entregue na 1.1.0 (macOS)

Nome novo Vulcan Celox com temas claro e escuro, aba Código (um visor: ela não edita arquivos), sinais de atenção, ⌘-clique em caminho, salto entre pedidos, portas por aba e estado do PR opcional. Detalhes no [registro de mudanças](CHANGELOG.pt-BR.md).

Ainda espera: a Release de Linux, depois do aceite no Mint.

## Depois, sem decisão

- App do macOS assinado e notarizado, e Python embutido.
- Outros agentes: Gemini CLI e Cursor CLI estão suspensos.
- Pareamento exato para o Codex. Depende de mudança no próprio Codex.
- Dividir os sete arquivos acima de 400 linhas.

## Fora dos planos

- Herd como backend.
- Reimplementar chat, editor ou os protocolos dos agentes. O terminal continua sendo a CLI oficial, e a aba Código só exibe arquivos.
