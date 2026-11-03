# Roadmap

[English](ROADMAP.md) | **Português**

Direção, não promessa. Como o projeto chegou aqui: [história do desenvolvimento](docs/pt-BR/history.md).

## Entregue na 1.0.0 (macOS)

Painel de agentes para Claude Code e Codex, busca no histórico, prompts, uso e custo, branches, aba Harness, terminais reais, sites PHP pelo Lerd ou Valet, projetos Node, caderno, Ajuda e manual. Detalhes no [registro de mudanças](CHANGELOG.pt-BR.md).

## Agora

- **Release para Linux.** Testar numa área de trabalho Linux Mint real, corrigir o que falhar e publicar `.deb` e `.tar.gz`. Ajuda é bem-vinda.
- **Terminar as conferências manuais no macOS:** pareamento com o Claude Code real, dividir, buscar e redimensionar.

## Previsto para a 1.1

- **Saber quando o agente precisa de você.** Anel na aba, contador na barra lateral e aviso do sistema quando uma sessão termina o turno ou pode estar esperando. Também lê as sequências padrão de terminal (OSC 9, 99 e 777), então funciona com qualquer programa. O hook opcional deixa exato o estado de permissão no Claude Code.
- **Aba Código ao vivo, só leitura.** Os arquivos que a sessão tocou, o código com realce de sintaxe e o diff por edição, por turno e contra o git, seguindo o agente enquanto ele trabalha, mais um botão "Abrir no editor".
- **⌘-clique em caminho no terminal.** Abre o arquivo na linha certa.
- **Navegar entre turnos.** Atalhos saltam entre os seus pedidos, no terminal e na tela da sessão.
- **Portas abertas e estado do PR.** Cada aba mostra as portas que abriu. O estado real do PR pelo seu próprio `gh` é opcional e vem desligado, porque usa a rede.
- **Nome novo e identidade visual.** O Vulcan Terminal passa a se chamar Vulcan Celox, com temas claro e escuro, paleta nova, fonte Inter, ícones minimalistas, e logo e ícone do app novos. Os dados de quem já usa ficam onde estão.

## Depois, sem decisão

- Interface em inglês. Hoje ela é em português.
- App do macOS assinado e notarizado, e Python embutido.
- Outros agentes: Gemini CLI e Cursor CLI estão suspensos.
- Pareamento exato para o Codex. Depende de mudança no próprio Codex.
- Dividir os sete arquivos acima de 400 linhas.

## Fora dos planos

- Windows: o módulo `pty` do Python não existe lá.
- Herd como backend.
- Reimplementar chat, editor ou os protocolos dos agentes. O terminal continua sendo a CLI oficial, e a aba Código só exibe arquivos.
