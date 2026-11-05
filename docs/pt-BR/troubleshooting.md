# Problemas comuns

Primeiro passo para quase tudo: `python3 -m vulcan_celox --doctor`. Mais perguntas no [manual](user-guide.md#perguntas-frequentes).

| Sintoma | Causa e solução |
|---------|-----------------|
| O macOS diz que o app está danificado | Quarentena em app não assinado: `xattr -dr com.apple.quarantine "/Applications/Vulcan Celox.app"` |
| O app pede Python | Aceite a oferta de instalar, ou instale o Python 3.9+ |
| O Windows avisa de editor desconhecido | O pacote não é assinado: **Mais informações**, depois **Executar assim mesmo** |
| No Windows, o app abre numa aba comum do navegador | Edge ou Chrome não foi encontrado, e o app usou o navegador padrão. Instale um dos dois |
| Abrir no navegador pede token | A interface precisa do token criado pelo app nativo. Abra pelo app |
| A tela Código recusa uma pasta | A pasta pessoal inteira, a raiz do disco, a pasta de dados do app e pastas com os dados dos agentes nunca abrem. Escolha a própria pasta do projeto |
| Uma mudança não aparece na tela Código | Pode estar numa pasta ignorada e recolhida, ou a pasta tem mais de 20 mil itens e só o que está aberto é observado: a barra de baixo avisa. Abra a pasta. Sistemas de arquivos de rede podem ter data pouco confiável |
| A tela Código diz Mudança no disco para a escrita de um agente | O nome só aparece quando a sessão registrou a mesma edição em até 60 s. Espere alguns segundos pelo registro; sessão fora desta pasta não conta |
| Lerd parado | **Ligar** na tela Lerd ou o play no alto. A primeira vez pode levar um minuto. O botão de raio liga junto com o app. O app espera ele responder. O botão de raio vem desligado, porque o Lerd é opcional |
| Problema no DNS `.test` | Faltam os passos do Lerd que pedem a senha de administrador. No terminal: `sudo /opt/homebrew/bin/podman-mac-helper install` e depois `lerd install`. A senha é a do seu usuário do Mac. O app nunca pede nem guarda |
| O Claude Code fecha logo depois de abrir numa aba | A pergunta de confiança na pasta vem com "No, exit" marcado, então Enter fecha. Aperte a seta para baixo até "Yes, I trust this folder" e depois Enter. O Codex não tem essa pergunta |
| Um agente não aparece | Só Claude Code e Codex são lidos. Sessões `.jsonl.zst` precisam do `zstd`; o `--doctor` conta as ignoradas |
| Sessões antigas sumiram do Claude Code | O Claude Code apaga depois de um tempo (30 dias por padrão). O índice do app guarda o que já leu |
| Índice estranho | `python3 -m vulcan_celox --reindexar-agentes`. O índice é descartável |
| **Rodar** não mostrou nada | O script roda numa aba do painel de baixo. Aperte ⌘J |
| Porta em uso | Muitas vezes um `dev` antigo. Pare o script ou feche a aba antiga. O app nunca mata processo por porta |
| Campo do prompt em âmbar | Falta esse dado na sessão. Preencha ou troque de sessão. O envio fica bloqueado |
| **Enviar ao terminal** recusado | O agente não está em primeiro plano naquela aba, ou uma sessão mais nova assumiu. Use a retomada oferecida |
| Enviei o prompt e nada aconteceu | Nada é enviado sozinho. O texto está no campo do agente. Aperte Enter |
| O custo não é o que paguei | É estimativa no preço da API. Assinatura cobra de outro jeito |
| Modelo sem custo | Sem preço conhecido. Acrescente em `precos.json` |
| Removi um site por engano | Saiu da lista, a pasta está intacta. Pasta apagada está na Lixeira |
| Duas sessões do Codex trocaram de aba | Limitação conhecida: o Codex não oferece vínculo exato |
| A consulta de versão diz que não foi possível consultar | Enquanto o repositório for privado, a consulta depende do `gh` com acesso a ele. Nunca é um erro: Configurações mostra o motivo, e dá para desligar a consulta |
| O servidor local parou | O aviso no alto diz o código de saída e a última linha do erro. **Ver log** abre `logs/servidor-erro.log`; **Reiniciar servidor** sobe outro sem fechar o app. Os terminais abertos morrem junto e voltam como encerrados, com Retomar. No Linux e no Windows o servidor vive no processo da janela: reabra o app |
| Quero ver o que o servidor fez | `<dados>/logs/servidor.log` (início, porta, exceções das rotas, encerramento) e `<dados>/logs/servidor-erro.log` (saída de erro do processo). Os dois saem mascarados e sem o token; o `--doctor` mostra o caminho |
| Restaurar não aparece | Escolha o `.zip` e clique em **Conferir**. Restaurar só aparece depois do resumo, e nunca para um zip com erro |
| Restaurei um backup e nada mudou | A troca acontece quando o app abre de novo. Reabra. Os dados anteriores ficam em `.restauros/`, dentro da pasta de dados |
| Um segredo ainda aparece numa memória antiga | Memórias gravadas antes da máscara ficam como estão. Use **Mascarar** em Configurações. Senha digitada num pedido oculto não tem formato reconhecível, então confira a lista de comandos das sessões antigas e apague a sessão se precisar |

Não está aqui? [Abra uma issue](https://github.com/freddominugez/vulcan-celox/issues/new/choose) com a saída do `--doctor`, depois de tirar o que não quer publicar.
