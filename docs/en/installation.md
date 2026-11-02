# Installation

## macOS (released)

Requirements: macOS 13 or newer, Apple Silicon or Intel, Python 3.9 or newer.

1. Download `Vulcan-Terminal-<version>-macos.dmg` from [Releases](https://github.com/freddominugez/vulcan-hub-painel/releases).
2. Check it, with `SHA256SUMS` in the same folder: `shasum -a 256 -c SHA256SUMS`. A missing `.zip` will be reported if you downloaded only the `.dmg`; that is fine.
3. Open the `.dmg` and drag **Vulcan Terminal** to Applications.
4. The app has no Apple certificate and is not notarized. The first time, right click it, choose **Open** and confirm. If macOS says the app is damaged:

   ```bash
   xattr -dr com.apple.quarantine "/Applications/Vulcan Terminal.app"
   ```

If Python is missing, the app says so when it opens and offers **Instalar ferramentas da Apple** (`xcode-select --install`) or **Instalar com Homebrew**. Nothing is installed without your confirmation.

User data lives in `~/Library/Application Support/VulcanTerminal/`. Removing the app keeps that folder.

### Optional tools

| Tool | For |
|------|-----|
| [Lerd](https://github.com/lerd-env/lerd) or Laravel Valet | PHP sites. Without them the app opens in local mode: terminals, agents, prompts, Node projects and the notebook still work |
| Claude Code, Codex | The agents whose sessions are read |
| `zstd` | Reading compressed Codex sessions (`.jsonl.zst`). Without it they are skipped and counted in `--doctor` |
| Anthropic API key | Only for AI documentation of sessions |

### Exact pairing with Claude Code (optional)

Without a hook, a tab and a session are paired by folder and time. For an exact link:

```bash
python3 -m vulcan_terminal --instalar-hook
```

This is the only thing that writes to `~/.claude/settings.json`, and it keeps a backup next to the file. See [pairing-hook.md](pairing-hook.md) (Portuguese).

## Build from source on macOS

Requirements: Command Line Tools (Swift and Python 3).

```bash
bash scripts/validate.sh     # optional: all sensors
bash scripts/install_app.sh  # builds with swiftc, installs in ~/Applications, creates a Desktop shortcut
bash scripts/package.sh      # packages for macOS and Linux in executaveis/
```

## Linux (not released yet)

The code is in the repository and its tests run in a container and in CI, including `.deb` installation on Ubuntu 22.04. It has **not** been accepted on a real desktop, so no Linux package is published. If you want to help, build it and try it on a real desktop:

```bash
python3 scripts/package_linux.py
cd executaveis/linux
sha256sum -c SHA256SUMS
sudo apt install ./vulcan-terminal_<version>_all.deb
vulcan-terminal --check
```

Python 3.9+ is the only build requirement. The window uses GTK and WebKit, or Chromium/Chrome in app mode, or the browser. Shortcuts use Ctrl+Shift. Libraries can be installed with `vulcan-terminal --instalar-dependencias` (apt, dnf or pacman), with your permission.

Windows is not supported: Python's `pty` module does not exist there.
