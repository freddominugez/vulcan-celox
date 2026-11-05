# Troubleshooting

First step for almost everything: `python3 -m vulcan_celox --doctor`.

| Symptom | Cause and fix |
|---------|---------------|
| macOS says the app is damaged | Quarantine on an unsigned app: `xattr -dr com.apple.quarantine "/Applications/Vulcan Celox.app"` |
| The app asks for Python | Accept the offer to install, or install Python 3.9+ yourself |
| Windows warns about an unknown publisher | The package is not signed: **More info**, then **Run anyway** |
| The Windows window opens in a normal browser tab | Edge or Chrome was not found, so the app fell back to the default browser. Install either one |
| Opening in a browser asks for a token | The interface needs the token the native app creates. Open it through the app |
| The Code screen refuses a folder | The whole home folder, the root of the disk, the app's data folder and folders with the agents' data never open. Choose the project folder itself |
| A change does not show on the Code screen | It may be in an ignored folder that is collapsed, or the folder has more than 20 thousand items and only what is open is watched: the bottom bar says so. Open the folder. Network file systems may have unreliable dates |
| Code says Disk change for an agent's write | The name appears only when the session recorded the same edit within 60 s. Wait a few seconds for the record; a session outside this folder is not counted |
| Lerd is stopped | **Start** on the Lerd screen or play at the top. The first start can take a minute, and the app waits for it to answer. The bolt button starts it with the app; it comes off, because Lerd is optional |
| `.test` DNS problem | Lerd's steps that need the administrator password were not finished. In a terminal: `sudo /opt/homebrew/bin/podman-mac-helper install`, then `lerd install`. The password is your Mac user's. The app never asks for it or stores it |
| Claude Code closes right after opening in a tab | Its folder trust question has "No, exit" selected, so Enter closes it. Press the down arrow to "Yes, I trust this folder", then Enter. Codex has no such question |
| An agent is missing | Only Claude Code and Codex are read. `.jsonl.zst` sessions need `zstd`; `--doctor` counts the skipped ones |
| Old Claude sessions disappeared from Claude Code | Claude Code removes them after a while (30 days by default). The app's index keeps what it already read |
| Index looks wrong | `python3 -m vulcan_celox --reindexar-agentes`. The index is disposable |
| **Run** showed nothing | The script runs in a bottom panel tab. Press ⌘J |
| Port already in use | Often an old `dev` process. Stop the script or close the old tab. The app never kills a process by port |
| Prompt field is amber | That value is missing from the session. Fill it in or change session. Sending stays blocked |
| **Send to terminal** refused | The agent is not in the foreground of that tab, or a newer session owns it. Use the offered resume |
| Sent a prompt, nothing happened | Nothing is sent by itself. The text is in the agent's input. Press Enter |
| Cost is not what I paid | It is an estimate at API list prices. Subscriptions bill differently |
| Model without a cost | No known price. Add it to `precos.json` |
| Removed a site by accident | The list entry is gone, the folder is intact. A deleted folder is in the Trash |
| Two Codex sessions swapped tabs | Known limitation: Codex offers no exact link |
| The new version check says it could not check | While the repository is private, the check needs `gh` with access to it. It is never an error: Settings shows the reason, and you can turn the check off |
| The local server stopped | The notice at the top shows the exit code and the last error line. **Show log** opens `logs/servidor-erro.log`; **Restart server** starts another one without closing the app. Open terminals end with it and come back as ended, with Resume. On Linux and Windows the server lives in the window's process: reopen the app |
| I want to see what the server did | `<data>/logs/servidor.log` (startup, port, route exceptions, shutdown) and `<data>/logs/servidor-erro.log` (the process error output). Both are masked and never hold the token; `--doctor` shows the paths |
| Restore does not show up | Choose the `.zip` and click **Check**. Restore only shows up after the summary, and never for a zip with an error |
| I restored a backup and nothing changed | The swap happens when the app opens again. Reopen it. The previous data stays in `.restauros/` inside the data folder |
| A secret still appears in an old session memory | Memories saved before masking stay as they are. Use **Mask** in Settings. A password typed at a hidden prompt has no recognizable format, so check the command list of older sessions and delete the session if needed |

Not listed? [Open an issue](https://github.com/freddominugez/vulcan-celox/issues/new/choose) with the `--doctor` output, after removing what you do not want to publish.
