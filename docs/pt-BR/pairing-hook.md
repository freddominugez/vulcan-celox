# Hook de pareamento do Claude Code

O Vulcan Celox liga cada aba de terminal à sessão do Claude Code iniciada nela, para a aba e a sessão terem a mesma cor e os prompts usarem os dados certos. Sem o hook, ele faz isso por pasta e horário (a sessão que começou até 60 segundos depois de a aba abrir, ou de `claude` ser digitado nela). Com o hook, o par é exato, mesmo com duas sessões na mesma pasta.

## O que o hook faz

- Cada aba do Vulcan Celox tem no ambiente `VULCAN_SESSION_ID` (o id da aba) e, quando há tema, `VULCAN_THEME`.
- Quando o Claude Code inicia uma sessão, ele roda os hooks `SessionStart` e passa no stdin um JSON com o `session_id`.
- O script do Vulcan lê o id da aba no ambiente e grava `<dados>/pairings/<session_id>.json`, com a sessão, a aba, o tema, a pasta e a origem. Fora de uma aba do Vulcan, não faz nada. Ele nunca falha: qualquer problema termina com código 0, para não atrapalhar o Claude Code.
- `<dados>` é `~/Library/Application Support/VulcanTerminal/` no macOS e `~/.local/share/vulcan-terminal/` no Linux (ou `$XDG_DATA_HOME/vulcan-terminal/`). `VULCAN_TERMINAL_HOME` troca a pasta nos dois.

O arquivo do hook vence o pareamento por pasta e horário.

## Instalar

```bash
# a partir do repositório:
python3 -m vulcan_terminal --instalar-hook
# ou com o código do app instalado no macOS (a casca nativa não repassa esta opção):
cd ~ && PYTHONPATH="$HOME/Applications/Vulcan Celox.app/Contents/Resources" python3 -m vulcan_terminal --instalar-hook
```

O comando:

1. grava o script em `<dados>/hooks/vulcan-pareamento.py`;
2. se o `~/.claude/settings.json` existir, copia-o para `~/.claude/settings.json.vulcan-backup-<data>`, onde `<data>` é o horário em segundos desde 1970;
3. acrescenta a entrada abaixo em `hooks.SessionStart`, sem mexer em mais nada (rodar de novo não duplica);
4. imprime um JSON com `script`, `settings`, `backup` e `already_installed`.

```json
{ "hooks": [ { "type": "command", "command": "'/Users/<você>/Library/Application Support/VulcanTerminal/hooks/vulcan-pareamento.py'" } ] }
```

O caminho vai entre aspas simples porque o Claude Code roda o comando pelo shell e, no macOS, o espaço de `Application Support` quebraria o caminho. Até a versão 0.3.0 o comando era gravado sem aspas; rodar o comando de novo corrige a entrada antiga em vez de duplicá-la.

Se o `settings.json` não for um objeto JSON válido, o comando avisa, sai com código 1 e não muda esse arquivo.

Esta é a única escrita do Vulcan Celox em `~/.claude`, e só acontece por este comando. Respeita `CLAUDE_CONFIG_DIR`.

## Conferir

1. Em `~/.claude/settings.json`, a entrada de `hooks.SessionStart` com `vulcan-pareamento.py` está entre aspas simples.
2. Abra uma aba no Vulcan Celox e rode `claude`. Em poucos segundos aparece `<dados>/pairings/<session_id>.json`, e a sessão mostra "pareada" na tela Agentes e na barra de prompts da aba.
3. Fora do Vulcan, o hook não grava nada.

## Remover

Apague a entrada com `vulcan-pareamento.py` de `hooks.SessionStart` no `~/.claude/settings.json` (ou restaure o backup). O pareamento volta a ser por pasta e horário.

## Codex

O Codex não tem um equivalente estável ao `SessionStart` que leia o ambiente da aba. Para ele vale só o pareamento por pasta e horário, que usa o momento em que `codex` foi digitado na aba. Sessões de sub-agente e do app desktop do Codex não nascem de uma aba e ficam fora do pareamento.
