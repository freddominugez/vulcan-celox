"""Textos e referências da Biblioteca Celox."""

import json
from pathlib import Path

VERSION = json.loads((Path(__file__).resolve().parents[1] / "settings.json").read_text())["version"]
REPO = "https://github.com/freddominugez/vulcan-celox"
MANUAL = REPO + "/blob/main/docs/pt-BR/user-guide.md"
RELEASE = f"{REPO}/releases/tag/v{VERSION}"
ASSETS = f"{REPO}/releases/download/v{VERSION}/"
HARPYA = "https://www.harpya.org"
RSS = HARPYA + "/rss.xml"
CASCADE = HARPYA + "/noticias/2026-11-19-cascata-modelos-agentes-codigo/"
KV_CACHE = HARPYA + "/noticias/2026-11-20-kaist-prkv-cache-contexto-longo/"
TOKENS = HARPYA + "/comecando/tokens/"
GLOSSARY = HARPYA + "/biblioteca/glossario/"
HARPYA_TERMS = HARPYA + "/termos-de-uso/"
HARPY_LICENSE = "https://creativecommons.org/licenses/by/4.0/deed.pt-br"

HUB = "/recursos/"
WORKFLOW = "/guias/claude-code-e-codex-no-mac/"
INSTALL = "/guias/instalar-vulcan-celox-no-macos/"
CONTEXT = "/artigos/contexto-memoria-e-prompts-para-agentes/"
TRACK = "/artigos/acompanhar-branches-commits-e-prs/"
PROMPT_LIBRARY = "/prompts/"
REPO_DIR = "/repositorios/"
RADAR = "/radar/"

PAGES = {
    HUB: ("Guias e recursos para agentes de código", "Guias do Celox, prompts reutilizáveis, projetos do GitHub e leituras da Harpya para quem usa agentes no Mac.", "Biblioteca"),
    WORKFLOW: ("Como organizar sessões de Claude Code e Codex no Mac", "Use abas nomeadas, cores e post-its vinculados para trabalhar com Claude Code e Codex e retomar projetos no Vulcan Celox.", "Guia"),
    INSTALL: ("Como instalar o Vulcan Celox no macOS", "Instale o Celox em Macs Apple Silicon ou Intel. Confira requisitos, pacotes oficiais, SHA-256 e os primeiros passos.", "Guia"),
    CONTEXT: ("Contexto, memória e prompts para agentes de código", "Entenda a diferença entre janela de contexto, histórico do agente e memória local do terminal. Monte um prompt curto de retomada.", "Artigo"),
    TRACK: ("Como acompanhar branches, commits e PRs de agentes de código", "Use a trilha do Celox para revisar uma sessão de Claude Code ou Codex e confirme o estado do trabalho no Git e no GitHub.", "Artigo"),
    PROMPT_LIBRARY: ("Prompts para Claude Code e Codex", "Copie modelos para retomar uma sessão, revisar uma mudança, investigar um teste e preparar o handoff de um projeto.", "Prompts"),
    REPO_DIR: ("Repositórios GitHub úteis para agentes e terminais", "Referências oficiais para Claude Code, Codex, Agent Skills, Lerd e xterm.js. Saiba quando consultar cada repositório.", "GitHub"),
    RADAR: ("Radar Harpya para quem usa agentes de código", "Leituras selecionadas do RSS público da Harpya, com fontes primárias e aplicações práticas para quem usa o Celox.", "Harpya"),
}

ARTICLES = {
    WORKFLOW: f"""
<section><h2 id="antes">Prepare o Mac e os agentes</h2>
<p>Instale o Celox e os agentes que pretende usar. Claude Code e Codex têm instalação e autenticação próprias. Abra o mesmo projeto no Celox pelo painel e confirme a pasta antes de iniciar o agente. O guia de instalação explica os requisitos do aplicativo. Os repositórios oficiais documentam a configuração de cada agente.</p>
<div class="links"><a href="{INSTALL}">Instalar o Celox</a><a href="{REPO_DIR}">Consultar os repositórios oficiais</a></div>
</section>
<figure class="article-figure"><img src="/assets/screens/terminals-pt.png" width="1800" height="1145" alt="Vulcan Celox com a área de terminais, abas de sessões e painel lateral" loading="lazy"><figcaption>Captura do Celox com dados de demonstração.</figcaption></figure>
<section><h2 id="duas-abas">Divida o trabalho em duas abas</h2>
<ol class="steps">
<li><strong>Abra uma aba com Claude Code.</strong> No diálogo de novo terminal, selecione a pasta do projeto e escolha Claude Code naquela aba. Dê a ela o nome <code>Checkout · implementação</code> e selecione uma cor.</li>
<li><strong>Abra outra aba com Codex.</strong> Escolha a pasta que você quer inspecionar. Chame a aba de <code>Checkout · revisão</code> e use outra cor. Cada diálogo começa em shell, e a escolha do agente vale para a aba criada.</li>
<li><strong>Determine o que cada aba pode fazer.</strong> Na primeira, peça a alteração. Na segunda, peça uma revisão em leitura. Se os dois agentes precisarem editar ao mesmo tempo, use diretórios de trabalho distintos e confirme o branch em cada terminal.</li>
<li><strong>Anote o ponto de retorno.</strong> No caderno da sessão, crie um post-it com o próximo passo. Exemplo <code>Conferir o teste do carrinho vazio depois da revisão.</code> Ao abrir a nota, use <strong>Ir para o terminal</strong> ou <strong>Ver no Histórico</strong> se a sessão estiver encerrada.</li>
</ol>
</section>
<section><h2 id="retomar">Retome pelo projeto e pelo branch</h2>
<p>Na tela Agentes, abra a sessão e confira nome do projeto, branch e arquivos tocados. Se duas sessões do Codex começarem quase juntas na mesma pasta, o pareamento por pasta e horário pode associá-las à aba errada. Valide o vínculo antes de colar um prompt. A memória local ajuda a encontrar o último teste e a razão de uma decisão.</p>
<div class="links"><a href="{PROMPT_LIBRARY}#retomar">Usar o prompt de retomada</a><a href="{TRACK}">Conferir branch, commit e PR</a></div>
</section>""",
    INSTALL: f"""
<section><h2 id="requisitos">Confira os requisitos do seu Mac</h2>
<p>A edição estável universal {VERSION} aceita macOS 13 ou posterior em Apple Silicon e Intel e pede Python 3.9 ou mais recente. Você pode conferir a versão do sistema em <strong>Sobre Este Mac</strong> ou consultar no Terminal.</p>
<pre><code>sw_vers -productVersion
uname -m
python3 --version</code></pre>
<p>Em um terminal nativo, <code>arm64</code> identifica Apple Silicon e <code>x86_64</code> identifica Intel. Se o Terminal estiver rodando sob Rosetta, confira o chip em Sobre Este Mac.</p>
</section>
<section><h2 id="baixar">Baixe o pacote e compare o SHA-256</h2>
<p>Use os arquivos da Release {VERSION}. O DMG abre em uma janela para arrastar o aplicativo. O ZIP contém o mesmo aplicativo universal em um arquivo compactado. Na mesma pasta do download, compare o resultado abaixo com a linha correspondente no arquivo <code>SHA256SUMS</code>.</p>
<div class="links"><a class="button" href="{ASSETS}Vulcan-Celox-{VERSION}-macos.dmg">Baixar DMG</a><a href="{ASSETS}Vulcan-Celox-{VERSION}-macos.zip">Baixar ZIP</a><a href="{ASSETS}SHA256SUMS">Ver SHA256SUMS</a></div>
<pre><code>shasum -a 256 Vulcan-Celox-{VERSION}-macos.dmg</code></pre>
<p>Para o ZIP, troque o nome do arquivo no comando. Se a soma divergir, baixe o pacote novamente pela página oficial da Release antes de abri-lo.</p>
</section>
<section><h2 id="abrir">Abra o primeiro terminal</h2>
<p>Coloque o Vulcan Celox em Aplicativos e abra-o. A distribuição tem assinatura ad hoc e a notarização Apple está pendente. Se houver um aviso na primeira abertura, consulte a mensagem exibida e a orientação da Apple para a sua versão do sistema. Se faltar Python, o próprio aplicativo oferece opções de instalação.</p>
<p>Ao entrar, escolha o idioma, selecione uma pasta de projeto e abra um terminal em shell. Para usar Claude Code ou Codex, instale o agente separadamente e depois selecione-o no diálogo da aba. Lerd ou Laravel Valet são opcionais para quem trabalha com sites PHP.</p>
<div class="links"><a href="{RELEASE}">Ver a Release e os requisitos</a><a href="https://support.apple.com/pt-br/102445">Consultar a orientação da Apple</a><a href="{WORKFLOW}">Organizar duas sessões no Mac</a></div>
</section>""",
    CONTEXT: f"""
<section><h2 id="tres-camadas">O que fica em cada lugar</h2>
<p>Quando você volta para um projeto, três coisas podem ajudar. Identifique qual delas tem a informação que falta.</p>
<dl class="definitions">
<div><dt>Janela de contexto do modelo</dt><dd>É o limite de entrada e saída que o modelo pode processar em uma chamada, conforme o modelo e o provedor. Um arquivo aberto no Mac só entra no contexto se a ferramenta o consultar ou se você fornecer o trecho. A Harpya explica por que os textos são fracionados em tokens.</dd></div>
<div><dt>Histórico do agente</dt><dd>Claude Code e Codex registram seu trabalho localmente. O Celox lê os registros compatíveis e usa as informações para apresentar projeto, branch, pedidos e arquivos tocados. A retomada usa o comando do próprio agente.</dd></div>
<div><dt>Memória do terminal</dt><dd>O Celox mantém uma memória local em Markdown com comandos, tarefas, post-its, tags e a saída recente. Após fechar a aba, consulte Sessões recentes ou abra o post-it vinculado e escolha Ver no Histórico.</dd></div>
</dl>
<div class="links"><a href="{TOKENS}">Ler sobre tokens na Harpya</a><a href="{MANUAL}#terminais">Conferir a memória do terminal no manual</a></div>
</section>
<section><h2 id="exemplo">Monte uma retomada em quatro linhas</h2>
<p>Imagine que você deixou uma correção no branch <code>feat/checkout-pix</code>. Antes de enviar a instrução, compare a memória da sessão com o estado atual do Git. Use um trecho curto de log e omita dados de clientes, chaves e caminhos pessoais.</p>
<pre><code>Objetivo: corrigir o total no checkout quando há cupom.
Escopo: CheckoutTotal e o teste da regra de desconto.
Já conferido: checkout sem cupom passou; falta cupom vencido.
Próximo passo: leia o diff e diga qual teste cobre o cenário.</code></pre>
<p>Separe a ação de ler da ação de editar. Se a próxima tarefa for só localizar a falha, peça a análise e espere a resposta. Um bom retorno informa qual arquivo sustenta a conclusão, qual teste passou e qual cenário ainda está em aberto.</p>
</section>
<section><h2 id="leitura">Leitura cruzada com a Harpya</h2>
<p>Use o artigo sobre tokens para entender o custo de anexar texto indiscriminadamente. O exemplo acima aplica essa leitura a uma tarefa concreta com registros e evidências do seu projeto. O Radar também inclui uma pesquisa sobre custo e prazo de agentes, com o escopo do estudo separado da prática no Celox.</p>
<div class="links"><a href="{RADAR}">Abrir o Radar Harpya do Celox</a><a href="{PROMPT_LIBRARY}#retomar">Copiar o prompt de retomada</a></div>
</section>""",
    TRACK: f"""
<section><h2 id="trilha">Leia a trilha da sessão</h2>
<p>Em Agentes, abra a sessão e confira projeto, branch e arquivos tocados. A trilha mostra evidências de edição, commit, push e pull request a partir dos registros disponíveis. Uma indicação na trilha ajuda a localizar o trabalho. Para tomar decisões de publicação, confirme o estado no Git e no GitHub.</p>
<figure class="article-figure"><img src="/assets/screens/agents-pt.png" width="1800" height="1145" alt="Tela Agentes do Celox com sessões de projetos e estado do trabalho" loading="lazy"><figcaption>Captura do Celox com sessões de demonstração.</figcaption></figure>
</section>
<section><h2 id="git">Confira o histórico no seu checkout</h2>
<p>Abra um terminal na pasta do projeto. Estes comandos mostram o branch atual, o estado dos arquivos e o último commit. O quarto consulta a referência upstream quando ela existe. Essa referência local reflete o último conhecimento do remoto e pode estar desatualizada.</p>
<pre><code>git branch --show-current
git status --short --branch
git log -1 --oneline
git rev-list --left-right --count @{{upstream}}...HEAD</code></pre>
<p>Se o upstream ainda não estiver configurado, registre essa condição. Para confirmar o PR no GitHub, abra a página do repositório ou rode <code>gh pr status</code> em um repositório com GitHub CLI autenticada. No Celox, a consulta opcional de PR em Configurações usa a sua própria autenticação do <code>gh</code>.</p>
</section>
<section><h2 id="caso">Exemplo de revisão antes de publicar</h2>
<p>Em <code>feat/checkout-pix</code>, a linha do tempo mostra a alteração e um commit. O próximo passo é revisar o diff, executar o teste do checkout e confirmar se esse commit já chegou ao PR. Registre no post-it o teste executado e o link do PR, quando houver. Em seguida, confirme a decisão de publicar de acordo com as regras do projeto.</p>
<div class="links"><a href="{PROMPT_LIBRARY}#revisar">Usar o prompt de revisão</a><a href="{MANUAL}#agentes">Ler a seção Agentes do manual</a></div>
</section>""",
}

PROMPTS = [
    ("retomar", "Retomar uma sessão", "Para voltar a uma tarefa sem perder o ponto em que ela parou.", "Sessões", f"{CONTEXT}#exemplo", """Projeto {{projectName}}, branch {{branch}}.
Leia o resumo anterior, o diff local e os testes citados na sessão.
Separe fatos confirmados de hipóteses e cite arquivos ou resultados.
Entregue objetivo, última evidência, pendência e o próximo passo.
Nesta etapa, trabalhe em leitura e apresente o plano antes de editar."""),
    ("revisar", "Revisar antes do PR", "Para conferir uma alteração antes de enviar ou integrar.", "Git", TRACK, """Revise as mudanças do branch {{branch}} em {{projectName}}.
Liste possíveis regressões e caminhos afetados, em ordem de gravidade.
Para cada achado, cite o arquivo, o cenário e o teste que deve cobri-lo.
Informe os testes já executados e a saída esperada dos que faltam.
Pare após a revisão. Qualquer commit, push ou merge depende de autorização."""),
    ("investigar", "Investigar um teste que falhou", "Para transformar um erro em uma hipótese verificável.", "Testes", WORKFLOW, """No projeto {{projectName}}, examine o teste que falhou neste terminal.
Registre entrada, resultado esperado e resultado observado, sem expor dados privados.
Identifique a menor reprodução que distingue as hipóteses.
Execute apenas verificações autorizadas no workspace. Relate comando e resultado.
Ao final, proponha a próxima mudança e o teste que a confirmaria."""),
    ("handoff", "Preparar o handoff", "Para que outra sessão consiga continuar com a mesma evidência.", "Sessões", TRACK, """Resuma o trabalho de {{projectName}} no branch {{branch}}.
Inclua objetivo, alterações por arquivo, comandos de teste, evidências e pendências.
Identifique o último commit conferido e o estado de push ou PR, com link se disponível.
Destaque decisões ainda abertas e indique a próxima verificação.
Use caminhos relativos e omita dados privados e credenciais."""),
]

REPOSITORIES = [
    ("openai/codex", "Agente", "Código e documentação de referência do Codex CLI.", "Confira a instalação, as versões e as formas de retomar uma sessão. O CLI é instalado separadamente.", WORKFLOW),
    ("anthropics/claude-code", "Agente", "Repositório oficial do Claude Code, com guias e registro de problemas.", "Consulte as notas de versão antes de reproduzir um comportamento em uma aba do Celox.", WORKFLOW),
    ("anthropics/skills", "Referência", "Exemplos publicados pela Anthropic de Agent Skills.", "Estude a estrutura e as licenças de cada exemplo antes de adaptar instruções para o seu projeto.", PROMPT_LIBRARY),
    ("lerd-env/lerd", "Ambiente local", "Backend opcional para sites PHP e Laravel com domínios .test.", "Consulte a instalação do backend para a sua plataforma quando precisar trabalhar com sites PHP no Mac.", INSTALL),
    ("xtermjs/xterm.js", "Dependência", "Componente de terminal que o Celox usa na interface.", "Consulte o projeto para estudar entrada, seleção e renderização de terminal.", TRACK),
    ("freddominugez/vulcan-celox", "Produto", "Código, manual, issues e Releases do Vulcan Celox.", "Use a Release pública para baixar o aplicativo e o manual para reproduzir um fluxo.", INSTALL),
]
