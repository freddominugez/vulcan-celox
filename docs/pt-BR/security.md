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

## Pastas dos agentes

- Nunca são escritas, com uma exceção: `--instalar-hook`, rodado pelo usuário, com backup. O script do hook sempre termina com 0, para não atrapalhar o Claude Code.
- Leitura em stream, linha por linha. Linha acima de 5 MB é descartada e registrada.

## Visor de código

- `GET /api/code/*` só lê; não existe rota de escrita. O arquivo precisa ficar, com links resolvidos, dentro da pasta da sessão. Sessão que rodou numa pasta que contém os dados dos agentes, como a pasta pessoal, não abre.
- Recusados: acima de 1 MB, binários, `.env*`, `*.pem`, `*.key`, `id_rsa*`, `credentials*` e o que estiver em `.git`, `.ssh`, `.aws` ou `.gnupg`. O diff segue as mesmas regras, porque traz o conteúdo.
- O repositório comparado é de terceiros, então nada dele pode rodar: o lado de HEAD vem de `git cat-file blob`, que não passa por `diff.external`, `textconv` nem filtros, e o lado atual é lido direto.
- O índice guarda onde cada edição está no arquivo da sessão, nunca o conteúdo. O conteúdo chega à página como texto do editor, nunca como HTML.

## Consulta opcional ao GitHub

Vem desligada, e assim nenhum comando roda. Se você ligar "Estado do PR pelo GitHub" no ⌘K, o app roda o seu `gh pr view` na pasta da sessão, no máximo uma vez por minuto por pasta, só com a tela visível. Essa chamada vai ao GitHub com o login do seu próprio `gh`. O app nunca pede nem guarda token do GitHub, e nunca abre, integra ou comenta PR.

## Executar coisas

- Subprocess é lista argv por `core/runner.py`.
- O git roda com `-c core.fsmonitor=false -c core.untrackedCache=false --no-optional-locks`. Conferido com git real: sem isso, o `git status` executou um hook do repositório analisado.
- Ajudantes em Python rodam com `python -I` a partir de uma pasta fixa, para que uma pasta hostil não plante módulo. Conferido por teste com `json.py` e `re.py` falsos.
- Prompts são colados por bracketed paste, sem caracteres de controle e **nunca com Enter**. O envio é recusado (409) se a aba não estiver viva, se a sessão não for a pareada mais nova dela ou se o agente não estiver em primeiro plano, para o texto não cair num shell. O Windows não diz qual programa está em primeiro plano, então lá vale a aba estar viva e pareada.
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
