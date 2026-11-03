# Installation

## macOS (released)

Requirements: macOS 13 or newer, Apple Silicon or Intel, Python 3.9 or newer.

1. Download `Vulcan-Celox-<version>-macos.dmg` from [Releases](https://github.com/freddominugez/vulcan-celox/releases).
2. Check it, with `SHA256SUMS` in the same folder: `shasum -a 256 -c SHA256SUMS`. A missing `.zip` will be reported if you downloaded only the `.dmg`; that is fine.
3. Open the `.dmg` and drag **Vulcan Celox** to Applications.
4. The app has no Apple certificate and is not notarized. The first time, right click it, choose **Open** and confirm. If macOS says the app is damaged:

   ```bash
   xattr -dr com.apple.quarantine "/Applications/Vulcan Celox.app"
   ```

If Python is missing, the app says so when it opens and offers **Instalar ferramentas da Apple** (`xcode-select --install`) or **Instalar com Homebrew**. Nothing is installed without your confirmation.

User data lives in `~/Library/Application Support/VulcanCelox/`. Removing the app keeps that folder.

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
python3 -m vulcan_celox --instalar-hook
```

This is the only thing that writes to `~/.claude/settings.json`, and it keeps a backup next to the file. See [pairing-hook.md](pairing-hook.md).

## Build from source on macOS

Requirements: Command Line Tools (Swift and Python 3).

```bash
bash scripts/validate.sh     # optional: all sensors
bash scripts/install_app.sh  # builds with swiftc, installs in ~/Applications, creates a Desktop shortcut
bash scripts/package.sh      # packages for macOS and Linux in executaveis/
```

## Windows (test build)

Windows 10 version 1809 or newer, or Windows 11. Python is included, so there is nothing else to install.

1. Download `Vulcan-Celox-<version>-windows.zip` from Releases and check it against `SHA256SUMS-windows`.
2. Extract the folder wherever you like and open `Vulcan Celox.cmd`.
3. The package is not signed, so Windows may warn about an unknown publisher: choose **More info**, then **Run anyway**.

The app opens in its own Microsoft Edge or Chrome window. The default shell is PowerShell. Data stays in `%APPDATA%\VulcanCelox`, and the Anthropic key goes to the Windows Credential Manager.

Not available on Windows: Lerd and Valet (PHP sites run in local mode), the optional agent hook (`--instalar-hook`), and clicking `C:\...` paths in the terminal. Without the foreground check, a paired tab counts as long as it is open.

## Linux (not released yet)

The code is in the repository and its tests run in a container and in CI, including `.deb` installation on Ubuntu 22.04. It has **not** been accepted on a real desktop, so no Linux package is published. If you want to help, build it and try it on a real desktop:

```bash
python3 scripts/package_linux.py
cd executaveis/linux
sha256sum -c SHA256SUMS
sudo apt install ./vulcan-celox_<version>_all.deb
vulcan-celox --check
```

Python 3.9+ is the only build requirement. The window uses GTK and WebKit, or Chromium/Chrome in app mode, or the browser. Shortcuts use Ctrl+Shift. Libraries can be installed with `vulcan-celox --instalar-dependencias` (apt, dnf or pacman), with your permission.

