# Modelo de segurança

Quem isto protege: um dev na própria máquina, cujos terminais e agentes já têm muito poder. O objetivo é o app não abrir nenhuma porta nova.

## Servidor local

- Só atende em `127.0.0.1`.
- Token: 32 bytes aleatórios por execução. Na API vem só no cabeçalho `X-Vulcan-Token`; token na query só no WebSocket.
- `Origin` conferida. Escrita (`POST`, `PUT`, `PATCH`) exige `application/json`. `Content-Length` validado.
- A janela não navega para fora da origem do app. Link externo abre no navegador padrão. A ponte nativa só aceita mensagem dessa origem.
- O token nunca vai na linha de comando (no Linux vai por arquivo 0600) e sai do ambiente das abas de terminal.
- O inspetor web só existe com `VULCAN_INSPECT=1`.

## Dados

- Pasta de dados 0700, arquivos 0600. No Windows esses modos não têm efeito, e a proteção é a do perfil do usuário (`%APPDATA%`).
- Chave da Anthropic no Keychain (macOS), no Secret Service (Linux) ou no Gerenciador de Credenciais (Windows). No macOS e no Linux, sempre pelo stdin, nunca por argv. Nunca aparece na interface nem em arquivo.
- Documentação com IA só por clique. Um diálogo mostra antes o tamanho do texto e quantos segredos foram mascarados. A máscara roda antes de cortar o texto.
- O `.env` dos projetos nunca é aberto.
- A memória da sessão é mascarada ao gravar, com `[segredo]` em português e `[secret]` em inglês (as duas grafias contam como já mascaradas), antes do corte de 2.000 linhas, com os mesmos padrões da documentação com IA. O que é digitado com eco desligado em modo canônico, que é o que `sudo`, `ssh` e `getpass` usam, fica fora da lista de comandos. O Windows não expõe esse modo, então lá ainda é registrado. Os padrões podem deixar passar um segredo incomum.
- Não são mascarados: `notes.json` e `tasks.json`, que guardam o seu próprio texto editável, e `agentes.db`, que indexa o que já está nos JSONL dos agentes. Memórias gravadas antes desta mudança ficam como estão até você usar **Mascarar** em Configurações.
- O backup é um `.zip` com modo 0600, sem criptografia. Leva tudo da pasta de dados, menos temporários, `logs/` e `.restauros/`, e não leva a chave da Anthropic. A restauração recusa caminho absoluto, `..`, links, os nomes reservados do app, formato desconhecido e tamanho acima do espaço livre. A troca acontece no próximo início, depois que a instância anterior saiu (no Windows ela não espera), e os dados anteriores vão para `.restauros/`. Se a troca falhar, o app abre com os dados como estão e avisa.
- Antes de restaurar, **Conferir** lê o zip sem extrair nada (`POST /api/data/backup/inspect`) e mostra data, versão, tamanho e contagens. Zip com mais de 20 mil membros ou mais de 2 GB descomprimidos, somando os tamanhos que ele declara, é recusado sem ser conferido. Restaurar só aparece quando nada seria recusado.
- As cópias em `.restauros/` saem pela tela só para a Lixeira, e só com um nome da listagem no formato de data. Link e nome fora da lista recebem 400.
- O log do servidor (`logs/servidor.log`, 1 MB e 3 arquivos) e a saída de erro do processo (`logs/servidor-erro.log`) ficam com modo 0600, passam pela máscara linha por linha e nunca levam o token da sessão, que vira `[token]`. Nada sai da máquina.
- A consulta de versão nova vem ligada, no máximo uma vez por dia. Ela manda um `GET` à API do GitHub com a versão do app no `User-Agent`. Se falhar, por exemplo enquanto o repositório for privado, roda o seu `gh api` no mesmo endereço, com o seu login do `gh`. O link mostrado precisa ser uma página de versão deste repositório. Nunca baixa nem instala nada. Desligue em Configurações ou com `VULCAN_UPDATE_CHECK=0`.

## Pastas dos agentes

- Nunca são escritas, com uma exceção: `--instalar-hook`, rodado pelo usuário, com backup. O script do hook sempre termina com 0, para não atrapalhar o Claude Code.
- Leitura em stream, linha por linha. Linha acima de 5 MB é descartada e registrada.


## Visor de código

- `GET /api/code/*` só lê; não existe rota de escrita. O arquivo precisa ficar, com links resolvidos, dentro da pasta da sessão. Sessão que rodou numa pasta que contém os dados dos agentes, como a pasta pessoal, não abre.
- Recusados: acima de 1 MB, binários, `.env*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_dsa*`, `id_ecdsa*`, `id_ed25519*`, `credentials*`, `.netrc`, `.git-credentials`, `.npmrc`, `.pypirc`, `auth.json`, `secrets.*` e o que estiver em `.git`, `.ssh`, `.aws` ou `.gnupg`. O diff segue as mesmas regras, porque traz o conteúdo.
- O repositório comparado é de terceiros, então nada dele pode rodar: o lado de HEAD vem de `git cat-file blob`, que não passa por `diff.external`, `textconv` nem filtros, e o lado atual é lido direto.
- O índice guarda onde cada edição está no arquivo da sessão, nunca o conteúdo. O conteúdo chega à página como texto do editor, nunca como HTML.


## Tela Código

- `/api/files/*` só lê: a única rota de escrita acrescenta ou tira uma pasta da lista do próprio app, `code_roots.json`, com no máximo 50 pastas escolhidas. Tirar da lista não apaga nada.
- Uma pasta só abre se o app a conhece (site, projeto Node, sessão) ou se você a escolheu. A pasta pessoal inteira, a raiz do disco, a pasta de dados do app e qualquer pasta dentro dos dados dos agentes ou que os contenha são recusadas.
- O caminho vem relativo à pasta. Caminho absoluto e `..` são recusados. Links simbólicos aparecem na árvore e não são seguidos, e link de arquivo que leva para fora da pasta é recusado. `.git` fica oculta. As regras de arquivo são as mesmas do visor de código.
- O repositório lido é de terceiros, então nada dele pode rodar. Um teste cria um repositório cujo `filter`, `core.fsmonitor`, `textconv`, `diff.external`, `core.sshCommand` e `remote.*.uploadpack` apontam para programas, inclusive um clone parcial de verdade, e falha se algum rodar: `git status`, `git diff` no arquivo de trabalho e `ls-files -m` executam esses programas, então não são usados. Os únicos comandos usados são `ls-files -o -i`, `ls-files -s --debug`, `ls-files -o --directory`, `grep --no-textconv`, `rev-parse`, `symbolic-ref` e `cat-file blob`.
- As marcas de Git (`GET /api/files/git`) comparam o índice com `lstat`, sem ler conteúdo, então um arquivo só tocado conta como alterado. O git roda de novo só quando a varredura vê mudança ou a cada 30 s, com orçamento de 20 mil entradas.
- As marcas ao vivo vêm da comparação de fotos do disco com `os.scandir`: nenhum conteúdo é lido. Nome de arquivo é dado e entra na árvore como texto.

## Consulta opcional ao GitHub

Vem desligada, e assim esta opção não roda nenhum comando. Se você ligar "Consultar o estado do PR no GitHub" em Configurações ou no ⌘K, o app roda o seu `gh pr view` na pasta da sessão, no máximo uma vez por minuto por pasta, só com a tela visível. Essa chamada vai ao GitHub com o login do seu próprio `gh`. O app nunca pede nem guarda token do GitHub, e nunca abre, integra ou comenta PR.

## Executar coisas

- Subprocess é lista argv por `core/runner.py`.
- O git roda com `core.fsmonitor=false`, `core.untrackedCache=false`, `--no-optional-locks` e todos os protocolos de transferência em `never`, um por um. O último impede que um clone parcial busque sozinho um objeto que falta, o que rodaria `core.sshCommand` ou `remote.*.uploadpack`. `git status` não é usado em lugar nenhum: ele roda o filtro `clean`, e nenhuma opção desliga isso. A tela Branches conta os arquivos alterados comparando tamanho e data com o índice, então um arquivo só tocado conta como alterado.
- Ajudantes em Python rodam com `python -I` a partir de uma pasta fixa, para que uma pasta hostil não plante módulo. Conferido por teste com `json.py` e `re.py` falsos.
- Prompts são colados por bracketed paste, sem caracteres de controle e **nunca com Enter**. O envio é recusado (409) se a aba não estiver viva, se a sessão não for a pareada mais nova dela ou se o agente não estiver em primeiro plano, para o texto não cair num shell.
- A interface escapa o que mostra e não carrega nenhum recurso externo.

## Apagar

Não há exclusão definitiva no código: pastas vão para a Lixeira, com confirmação digitando o nome. Um teste varre o fonte.

## Riscos aceitos

| Risco | Por que foi aceito |
|-------|--------------------|
| Outro processo do mesmo usuário pode ler a memória do app, ou o item do Keychain pelo `/usr/bin/security` | Fora do modelo de ameaça; limitação da plataforma |
| O app do macOS tem só assinatura ad hoc e não é notarizado; o pacote do Windows não é assinado | Decisão até aqui. Confira o download com o `SHA256SUMS` |
| Um agente ou site que você roda pode fazer o que o seu usuário pode | O app mostra o que aconteceu; ele não é um sandbox |

Relatar vulnerabilidade: [SECURITY.pt-BR.md](../../SECURITY.pt-BR.md).
