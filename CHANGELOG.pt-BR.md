# Registro de mudanças

Mudanças relevantes do Vulcan Celox, chamado Vulcan Terminal até a 1.0. O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem o [Versionamento Semântico](https://semver.org/lang/pt-BR/). Versão em inglês: [CHANGELOG.md](CHANGELOG.md).

## [1.1.0] - 2026-11-03

**O Vulcan Terminal agora é Vulcan Celox.** Seus dados, o item do Keychain e as preferências ficam onde estavam. Ao instalar, o app antigo vai para a Lixeira.

### Adicionado
- **Aba Código** na sessão de agente: árvore dos arquivos tocados, realce de sintaxe e diff por edição, por pedido ou contra o último commit, lado a lado ou unificado. Só leitura. Em sessão ativa ela segue o agente; qualquer gesto pausa, e **Voltar a seguir** retoma.
- **Quem espera por você:** anel na aba, contador na barra lateral, ⌘⇧U para ir até lá e aviso do sistema com a janela sem foco. Também lê OSC 9, 99, 777 e o sino. Um hook opcional mostra na hora os pedidos de permissão.
- **⌘-clique em caminho no terminal:** abre na aba Código na linha, no seu editor ou no Finder.
- **Saltar entre pedidos:** ⌘⇧↑ e ⌘⇧↓ no terminal, e **Linha do tempo** agrupada por pedido, com link para o diff daquele pedido.
- **Portas por aba:** um selo como `:5173 +2` na barra de abas e na lista de sessões.
- **Estado real do PR, opcional e desligado por padrão:** número, rascunho, estado e checagens pelo seu próprio `gh`. Desligado, nenhum comando roda.
- Temas claro e escuro (Sistema por padrão), Inter, ícones Phosphor, o logo novo e o ícone do app.

### Segurança
- A aba Código recusa o que estiver fora da pasta da sessão, inclusive por link, além de binários, arquivos acima de 1 MB e nomes sensíveis como `.env`. O diff segue as mesmas regras.
- O diff contra o git não consegue executar nada do repositório analisado: `diff.external`, `textconv` e filtros nunca rodam.

### Mudou
- O índice das sessões guarda onde cada edição está, nunca o conteúdo. Ele é refeito uma vez ao atualizar.

### Limites conhecidos
- O ícone do app ficou sem os tamanhos de 16 e 32 px por decisão da marca; o macOS reduz a partir dos maiores.
- Caminho relativo impresso depois de um `cd` pode não ser encontrado pelo ⌘-clique: ele conta a partir da pasta da sessão ou da pasta em que a aba abriu.

## [1.0.0] - 2026-11-01

Primeira versão estável, **só para macOS** (`.dmg`, `.zip`, `SHA256SUMS`). O código do Linux segue no repositório e no CI, mas nenhum pacote de Linux é distribuído até passar pelo roteiro de aceite numa área de trabalho real.

### Adicionado
- Teste de ponta a ponta com PTY real, shell real e um executável falso de agente (`tests/test_aceite_pareamento.py`).

### Corrigido
- Sessão de agente sem pasta criava uma opção vazia no filtro de projeto da tela Agentes.
- Ctrl+Shift+F nunca abria a busca do terminal no Linux, e a dica mostrava o atalho do macOS.
- O título da sessão mostrava o pedido colado inteiro, com as crases. Agora mostra a primeira frase ou até 120 caracteres; o pedido inteiro segue no painel Primeiro pedido.

### Limitações conhecidas
- O app não tem certificado da Apple e não é notarizado, e precisa de Python 3.9+ na máquina.
- O Codex não oferece vínculo exato entre aba e sessão. Duas sessões iniciadas na mesma pasta com menos de 60 segundos de diferença podem trocar de aba.
- Gemini CLI e Cursor CLI não são suportados.

## [0.9.0] - 2026-11-01

### Alterado
- Documentação com IA usa o Claude Sonnet 5.5 por padrão. Preços conferidos nas páginas oficiais.
- `app.mjs`, `server/app.py` e `sites_api.py` divididos. Um teste barra arquivo novo acima de 400 linhas.

### Corrigido
- Job do GitHub Actions, quebrado por falha de permissão no `tar`.
- Recusa da API da Anthropic agora mostra um erro claro.

## [0.8.1] - 2026-11-01

### Adicionado
- Leitura das sessões comprimidas do Codex (`.jsonl.zst`) pelo `zstd` do sistema, quando existe.

### Corrigido
- Subagentes e o app desktop do Codex não pareiam mais com uma aba.
- Sessões em disputa pareiam em ordem no tempo.

## [0.8.0] - 2026-11-01

### Adicionado
- `core/lerd_quirks.py` e um bloco no `--doctor` com os contornos do Lerd e a versão que corrige cada um.
- Correção enviada ao Lerd: [lerd-env/lerd#2404](https://github.com/lerd-env/lerd/pull/2404).

## [0.7.2] - 2026-11-01

### Corrigido
- Prompt é recusado (HTTP 409) quando o agente não está mais em primeiro plano na aba ou quando uma sessão mais nova assumiu a aba.
- Escrita no PTY não trava mais em aba que não lê a entrada; desiste depois de 5 segundos sem progresso.
- Arquivos de prompt com permissão privada (0600 e 0700) na pasta de dados.
- Campos do compositor voltavam ao valor da sessão quando a lista de sites mudava.
- Foco do teclado se perdia na barra lateral e no guia do Início depois de redesenhar.

## [0.7.1] - 2026-11-01

### Corrigido
- Achados de duas revisões independentes da 0.7.0: caracteres de controle em valores da sessão, respostas antigas nas telas de Uso e Histórico, validação do tamanho do terminal, trava na lista de projetos Node e validação da raiz do projeto.

## [0.7.0] - 2026-11-01

### Adicionado
- Prompts como ação: cartões, compositor com um campo por variável, prévia ao vivo e **Enviar ao terminal**, que cola o texto no agente pareado **sem apertar Enter**.
- Barra lateral em grupos recolhíveis, com listas separadas de sites PHP e projetos Node.
- Caixa "Não mostrar mais o guia" na tela Início.

## [0.6.0] - 2026-11-01

### Adicionado
- Projetos Node: `package.json`, lockfile, framework e porta, Supabase local, vínculo com a Vercel e scripts numa aba de terminal à vista.
- Lerd como item da barra lateral, com ponto de estado.
- Tela Início com guia de quatro passos que se confere sozinho, tela Ajuda com manual e perguntas frequentes, botão `?` em cada tela e `docs/MANUAL.md` gerado do mesmo conteúdo.

## [0.5.0] - 2026-10-31

### Adicionado
- Uso e custo: tokens e custo estimado no preço da API, por dia, projeto, modelo e sessão, com CSV. Preços editáveis em `precos.json`.
- Harness do projeto na interface: contrato, itens, próximo item, último commit verde, handoff, **Instalar harness** e **Novo contrato**.

### Notas
- Leitores de Gemini CLI e Cursor CLI foram planejados aqui e depois suspensos.

## [0.4.0] - 2026-10-31

### Adicionado
- Gestão completa de sites sobre o Lerd: adicionar, link, park, PHP, Node e HTTPS por site, compartilhar, logs.
- Tela Ambiente: serviços, versões de PHP, extensões, Xdebug e seis ajustes comuns do `php.ini`.
- Tela Depuração: dumps, queries, logs e exceções da ponte do Lerd, agrupados por requisição, com aviso de query repetida, e o painel "Depuração no período" em cada sessão de agente.

### Corrigido
- Pasta de trabalho hostil podia influenciar o ajudante do `php.ini` (agora roda com `python -I`).
- Painéis cortados, lacuna do sensor com API falsa do Lerd e chamadas repetidas à CLI (cache de 60 segundos).

## [0.3.1] - 2026-10-31

### Segurança
- Token aceito só no cabeçalho `X-Vulcan-Token` na API. Escrita exige JSON. `Origin` e `Content-Length` validados. A janela não navega para fora da origem do app.
- Pasta de dados 0700 e arquivos 0600. Segredos mascarados antes de cortar o texto da documentação com IA. O token saiu da linha de comando no Linux.

### Corrigido
- Corridas no fechamento do PTY, filas sem limite no WebSocket, disputa de lock no índice durante leituras longas e hook de pareamento quebrando em caminho com espaço.

## [0.3.0] - 2026-10-31

### Adicionado
- Painel de Agentes: índice só de leitura dos JSONL do Claude Code e do Codex, cartões de sessão, linha do tempo, arquivos tocados, trilha de publicação e alerta de possível loop.
- Histórico unificado com busca sem acento; branches e worktrees cruzados com o git real.
- Biblioteca de prompts em Markdown, global e por projeto, preenchida pela sessão.
- Temas de cor por aba, pareamento entre aba e sessão, `--instalar-hook` opcional, retomar sessão numa aba.
- Painel inferior de terminal: redimensionar, dividir, buscar, WebGL.

## [0.2.0] - 2026-09-14

### Adicionado
- Lerd como backend prioritário, com Valet e modo local como alternativas.
- Casca nativa do macOS (Swift, WKWebView), servidor local, terminais PTY reais com xterm.js.
- Sessões de terminal com memória em Markdown e índice geral; árvore de sessões na barra lateral.
- Documentação de sessão com IA, só por clique, com a chave do próprio usuário no Keychain e segredos mascarados.
- Pacotes para macOS e Linux e instalação de dependências com permissão.
- Pacotes para Linux Mint refeitos a partir do código em 2026-10-10 (`v0.2.0-mint-20261010`).

## [0.1.0] - 2026-09-13

### Adicionado
- Fundação: núcleo em Python stdlib, backends Valet e Null, descoberta de sites, interface tkinter.
- Caderno: tags, post-its, tarefas, progresso, `TAREFAS.md`, busca global, exportar e importar.

[1.0.0]: https://github.com/freddominugez/vulcan-celox/releases/tag/v1.0.0
