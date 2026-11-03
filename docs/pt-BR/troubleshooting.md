# Problemas comuns

Primeiro passo para quase tudo: `python3 -m vulcan_terminal --doctor`. Mais perguntas no [manual](user-guide.md#perguntas-frequentes).

| Sintoma | Causa e solução |
|---------|-----------------|
| O macOS diz que o app está danificado | Quarentena em app não assinado: `xattr -dr com.apple.quarantine "/Applications/Vulcan Celox.app"` |
| O app pede Python | Aceite a oferta de instalar, ou instale o Python 3.9+ |
| Abrir no navegador pede token | A interface precisa do token criado pelo app nativo. Abra pelo app |
| Lerd parado | **Ligar** na tela Lerd ou o play no alto. A primeira vez pode levar um minuto. O botão de raio liga junto com o app |
| Problema no DNS `.test` | Faltam os passos do Lerd que pedem a senha de administrador. No terminal: `sudo /opt/homebrew/bin/podman-mac-helper install` e depois `lerd install`. A senha é a do seu usuário do Mac. O app nunca pede nem guarda |
| Um agente não aparece | Só Claude Code e Codex são lidos. Sessões `.jsonl.zst` precisam do `zstd`; o `--doctor` conta as ignoradas |
| Sessões antigas sumiram do Claude Code | O Claude Code apaga depois de um tempo (30 dias por padrão). O índice do app guarda o que já leu |
| Índice estranho | `python3 -m vulcan_terminal --reindexar-agentes`. O índice é descartável |
| **Rodar** não mostrou nada | O script roda numa aba do painel de baixo. Aperte ⌘J |
| Porta em uso | Muitas vezes um `dev` antigo. Pare o script ou feche a aba antiga. O app nunca mata processo por porta |
| Campo do prompt em âmbar | Falta esse dado na sessão. Preencha ou troque de sessão. O envio fica bloqueado |
| **Enviar ao terminal** recusado | O agente não está em primeiro plano naquela aba, ou uma sessão mais nova assumiu. Use a retomada oferecida |
| Enviei o prompt e nada aconteceu | Nada é enviado sozinho. O texto está no campo do agente. Aperte Enter |
| O custo não é o que paguei | É estimativa no preço da API. Assinatura cobra de outro jeito |
| Modelo sem custo | Sem preço conhecido. Acrescente em `precos.json` |
| Removi um site por engano | Saiu da lista, a pasta está intacta. Pasta apagada está na Lixeira |
| Duas sessões do Codex trocaram de aba | Limitação conhecida: o Codex não oferece vínculo exato |

Não está aqui? [Abra uma issue](https://github.com/freddominugez/vulcan-hub-painel/issues/new/choose) com a saída do `--doctor`, depois de tirar o que não quer publicar.
