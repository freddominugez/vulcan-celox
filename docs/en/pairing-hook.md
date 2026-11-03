# Claude Code pairing hook

Vulcan Celox links each terminal tab to the Claude Code session started in it, so the tab and the session share a color and prompts use the right data. Without the hook, it does this by folder and time (the session that started up to 60 seconds after the tab opened, or after `claude` was typed in it). With the hook, the pair is exact, even with two sessions in the same folder.

## What the hook does

- Each Vulcan Celox tab has `VULCAN_SESSION_ID` (the tab id) in its environment and, when it has a theme, `VULCAN_THEME`.
- When Claude Code starts a session, it runs the `SessionStart` hooks and passes a JSON with the `session_id` on stdin.
- The Vulcan script reads the tab id from the environment and writes `<data>/pairings/<session_id>.json`, with the session, tab, theme, folder and source. Outside a Vulcan tab, it does nothing. It never fails: any problem ends with exit code 0, so it does not get in Claude Code's way.
- `<data>` is `~/Library/Application Support/VulcanCelox/` on macOS and `~/.local/share/vulcan-celox/` on Linux (or `$XDG_DATA_HOME/vulcan-celox/`). `VULCAN_CELOX_HOME` changes the folder on both.

The hook's file wins over pairing by folder and time.

## Install

```bash
# from the repository:
python3 -m vulcan_celox --instalar-hook
# or with the code of the installed app on macOS (the native shell does not pass this option on):
cd ~ && PYTHONPATH="$HOME/Applications/Vulcan Celox.app/Contents/Resources" python3 -m vulcan_celox --instalar-hook
```

The command:

1. writes the script to `<data>/hooks/vulcan-pareamento.py`;
2. if `~/.claude/settings.json` exists, copies it to `~/.claude/settings.json.vulcan-backup-<date>`, where `<date>` is the time in seconds since 1970;
3. adds the entry below to `hooks.SessionStart`, touching nothing else (running it again does not duplicate it);
4. prints a JSON with `script`, `settings`, `backup` and `already_installed`.

```json
{ "hooks": [ { "type": "command", "command": "'/Users/<you>/Library/Application Support/VulcanCelox/hooks/vulcan-pareamento.py'" } ] }
```

The path goes in single quotes because Claude Code runs the command through the shell and, on macOS, the space in `Application Support` would break the path. Up to version 0.3.0 the command was written without quotes; running the command again fixes the old entry instead of duplicating it.

If `settings.json` is not a valid JSON object, the command reports it, exits with code 1 and does not change that file.

This is Vulcan Celox's only write to `~/.claude`, and it happens only through this command. It respects `CLAUDE_CONFIG_DIR`.

## Check

1. In `~/.claude/settings.json`, the `hooks.SessionStart` entry with `vulcan-pareamento.py` is in single quotes.
2. Open a tab in Vulcan Celox and run `claude`. Within a few seconds `<data>/pairings/<session_id>.json` appears, and the session shows "pareada" (paired) on the Agents screen and in the tab's prompt bar.
3. Outside Vulcan, the hook writes nothing.

## Remove

Delete the entry with `vulcan-pareamento.py` from `hooks.SessionStart` in `~/.claude/settings.json` (or restore the backup). Pairing goes back to folder and time.

## Codex

Codex has no stable equivalent to `SessionStart` that reads the tab's environment. For Codex only pairing by folder and time applies, using the moment `codex` was typed in the tab. Sessions from Codex subagents and the desktop app do not start in a tab and stay out of pairing.
