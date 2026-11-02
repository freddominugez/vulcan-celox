# História do desenvolvimento

Como o Vulcan Terminal chegou à versão 1.0.0, de setembro a novembro de 2026. As mudanças de cada versão estão no [CHANGELOG](../../CHANGELOG.pt-BR.md), e o que vem depois está no [ROADMAP](../../ROADMAP.pt-BR.md).

## Em números

| | |
|---|---|
| Do primeiro commit à 1.0.0 | 13/09/2026 a 01/11/2026 (50 dias) |
| Dias com commit | 7 |
| Commits | 245 no desenvolvimento original |
| Testes automatizados | 224 na 0.2.0, 405 na 0.3.0, 617 na 0.5.0, cerca de 700 na 1.0.0 |
| Dependências para instalar com pip | 0 |

O código foi criado com assistência de IA, sob direção e revisão do autor. Para esta publicação, o histórico foi consolidado num único commit: por isso os 245 commits não aparecem aqui.

## Fase 1: o painel PHP (setembro)

Tudo começou com um protótipo de 394 linhas em tkinter, um painel para sites PHP locais com post-its.

- **13/09, primeiro commit.** O plano inicial previa o Herd como ferramenta preferencial. Como ele é comercial, saiu logo no início: o app passou a orquestrar o Laravel Valet e, em seguida, o Lerd, com prioridade, ambos MIT.
- **13/09, primeira versão.** A 0.1.0 trouxe a fundação e o caderno de tarefas e notas.
- **13/09, troca de interface.** O app abria em branco com o Tk 8.5 do sistema, e a interface em tkinter foi rejeitada. No mesmo dia nasceu a arquitetura atual: servidor local, terminais PTY reais, xterm.js e uma casca nativa em Swift com WKWebView. Cada terminal virou uma sessão com memória em Markdown.
- **14/09, versão 0.2.0.** App nativo, ícone desenhado em código, documentação de sessões com IA só por clique, e pacotes para macOS e Linux.

## Fase 2: a pausa e a ideia (outubro)

- **10/10, Linux.** Pacote para Linux Mint gerado no próprio Linux.
- **29/10, o painel de agentes.** A ideia nova era acompanhar as sessões de Claude Code e Codex. O primeiro escopo previa um app separado em Node, React e Tauri. Uma análise mostrou que cerca de 70% da infraestrutura necessária já existia aqui, e a decisão foi integrar.

## Fase 3: os três dias (30/10 a 01/11)

Dos 245 commits, 168 aconteceram nesses três dias.

| Quando | O que aconteceu |
|--------|-----------------|
| 30/10 | Leitor das sessões, índice e observador de arquivos. As Command Line Tools da máquina precisaram ser instaladas antes de tudo |
| 31/10 | Um defeito do app em Linux marcava sessões como ativas por engano. Foi corrigido no app, e não no teste que o revelou |
| 31/10 | Primeira revisão independente: 14 defeitos, entre eles um risco de o `git status` executar um hook do repositório analisado |
| 31/10 | Prompts por botão, pareamento entre aba e sessão, temas e painel de terminal. **Versão 0.3.0** |
| 31/10 | Documentação completa do estado do app e duas revisões: 33 defeitos, com a primeira rodada de correções na **0.3.1** |
| 31/10 | Sites, Ambiente e Depuração reescritos sobre o Lerd. **Versão 0.4.0** |
| 31/10 | Uso e custo, e a aba Harness. **Versão 0.5.0** |
| 01/11 | Projetos Node, tela Início, manual e Ajuda (**0.6.0**). Prompts como ação (**0.7.0**) |
| 01/11 | Novas revisões independentes (**0.7.1** e **0.7.2**) |
| 01/11 | Gemini CLI e Cursor CLI suspensos: o foco ficou em Claude Code e Codex |
| 01/11 | Contornos para defeitos do Lerd e correção [enviada ao projeto](https://github.com/lerd-env/lerd/pull/2404) (**0.8.0**). Melhorias no pareamento do Codex (**0.8.1**) |
| 01/11 | Aceite no macOS e qualidade (**0.9.0**) |
| 01/11 | **Versão 1.0.0**, a primeira estável, só para macOS |

## Decisões que definiram o projeto

- **Orquestrar, não reimplementar.** O ambiente PHP fica com o Lerd ou o Valet, e o chat fica com a CLI oficial de cada agente.
- **Ler, sem escrever.** O app lê os arquivos que os agentes já gravam, sem chave de API e sem escrever nas pastas deles. A única exceção é o hook opcional de pareamento, instalado pelo próprio usuário, com backup.
- **Sem dependências.** Python só com a biblioteca padrão, interface web sem build e xterm.js incluído no repositório.
- **Nada é apagado de forma definitiva.** Pasta removida vai para a Lixeira.
- **O teste decide.** O `scripts/validate.sh` diz se uma mudança passa, e um teste não é enfraquecido para passar.
- **Só macOS primeiro.** O Linux tem testes em contêiner e no CI, mas não foi aceito numa área de trabalho real, então não entrou como entregue.

## Versões

| Versão | Data | Marca |
|--------|------|-------|
| 0.1.0 | 13/09/2026 | Fundação e caderno |
| 0.2.0 | 14/09/2026 | App nativo, terminal real, memória, pacotes |
| 0.3.0 | 31/10/2026 | Painel de Agentes |
| 0.3.1 | 31/10/2026 | Correções das revisões |
| 0.4.0 | 31/10/2026 | Sites e ambiente sobre o Lerd |
| 0.5.0 | 31/10/2026 | Uso e custo, Harness |
| 0.6.0 | 01/11/2026 | Node, Início e Ajuda |
| 0.7.0 | 01/11/2026 | Prompts como ação |
| 0.7.1, 0.7.2 | 01/11/2026 | Correções das revisões |
| 0.8.0, 0.8.1 | 01/11/2026 | Lerd e Codex |
| 0.9.0 | 01/11/2026 | Qualidade |
| **1.0.0** | **01/11/2026** | **Primeira versão estável, só macOS** |
