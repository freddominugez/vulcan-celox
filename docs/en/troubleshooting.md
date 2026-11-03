# Troubleshooting

First step for almost everything: `python3 -m vulcan_terminal --doctor`.

| Symptom | Cause and fix |
|---------|---------------|
| macOS says the app is damaged | Quarantine on an unsigned app: `xattr -dr com.apple.quarantine "/Applications/Vulcan Celox.app"` |
| The app asks for Python | Accept the offer to install, or install Python 3.9+ yourself |
| Opening in a browser asks for a token | The interface needs the token the native app creates. Open it through the app |
| Lerd is stopped | **Ligar** on the Lerd screen or play at the top. The first start can take a minute. The bolt button starts it with the app |
| `.test` DNS problem | Lerd's steps that need the administrator password were not finished. In a terminal: `sudo /opt/homebrew/bin/podman-mac-helper install`, then `lerd install`. The password is your Mac user's. The app never asks for it or stores it |
| An agent is missing | Only Claude Code and Codex are read. `.jsonl.zst` sessions need `zstd`; `--doctor` counts the skipped ones |
| Old Claude sessions disappeared from Claude Code | Claude Code removes them after a while (30 days by default). The app's index keeps what it already read |
| Index looks wrong | `python3 -m vulcan_terminal --reindexar-agentes`. The index is disposable |
| **Rodar** showed nothing | The script runs in a bottom panel tab. Press ⌘J |
| Port already in use | Often an old `dev` process. Stop the script or close the old tab. The app never kills a process by port |
| Prompt field is amber | That value is missing from the session. Fill it in or change session. Sending stays blocked |
| **Enviar ao terminal** refused | The agent is not in the foreground of that tab, or a newer session owns it. Use the offered resume |
| Sent a prompt, nothing happened | Nothing is sent by itself. The text is in the agent's input. Press Enter |
| Cost is not what I paid | It is an estimate at API list prices. Subscriptions bill differently |
| Model without a cost | No known price. Add it to `precos.json` |
| Removed a site by accident | The list entry is gone, the folder is intact. A deleted folder is in the Trash |
| Two Codex sessions swapped tabs | Known limitation: Codex offers no exact link |

Not listed? [Open an issue](https://github.com/freddominugez/vulcan-hub-painel/issues/new/choose) with the `--doctor` output, after removing what you do not want to publish.
