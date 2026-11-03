# Vulcan Celox: packages

Packages built by `bash scripts/package.sh` (on macOS). Check integrity with `shasum -a 256 -c SHA256SUMS` (macOS) or `sha256sum -c SHA256SUMS` (Linux).

| Folder | File | For |
|--------|------|-----|
| `macos/` | `Vulcan-Celox-<version>-macos.dmg` | installing by dragging to Applications |
| `macos/` | `Vulcan-Celox-<version>-macos.zip` | the same app, compressed |
| `linux/` | `vulcan-celox_<version>_all.deb` | Debian, Ubuntu, Mint and derivatives |
| `linux/` | `vulcan-celox-<version>-linux.tar.gz` | any distribution, no sudo |

The interface is in English by default. Press ⌘K (Ctrl+Shift+K on Linux) and search for "Language" to switch to Portuguese.

## macOS (13 or newer, Apple Silicon or Intel)

1. Open the `.dmg` and drag **Vulcan Celox** to **Applications**.
2. Requirement: Python 3.9 or newer. If it is missing, the app says so when it opens and offers **Install Apple tools** (`xcode-select --install`) or **Install with Homebrew**; nothing is installed without your confirmation. To only check: `"/Applications/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --verificar-dependencias`.
3. The app is not signed with an Apple certificate. The first time, right click the app, choose **Open** and confirm. If macOS says the app "is damaged", run `xattr -dr com.apple.quarantine "/Applications/Vulcan Celox.app"`.

User data: `~/Library/Application Support/VulcanCelox/`. To remove the app, delete it from Applications (your data stays).

## Linux

### Build the packages directly on Linux Mint

The full code is in this repository. With Python 3.9 or newer:

```bash
python3 scripts/package_linux.py
cd executaveis/linux
sha256sum -c SHA256SUMS
sudo apt install ./vulcan-celox_<version>_all.deb
vulcan-celox --check
vulcan-celox
```

This command produces the `.deb`, the `.tar.gz`, the instructions and the SHA-256
sums without needing Swift, macOS, pip or Node.js. The product's own icons are
included in `packaging/linux/icons/`. `apt` fetches the system libraries;
Lerd or Valet are optional for managing PHP sites and are installed separately.
Personal data and API keys are not part of the packages.

### Required libraries (with your permission)

The program checks what is missing and installs it only after you authorize it (it asks for the administrator password):

```bash
vulcan-celox --verificar-dependencias   # only checks and shows the command
vulcan-celox --instalar-dependencias    # shows what is missing, asks [s/N] and installs
vulcan-celox --instalar-dependencias -y # authorizes without asking
```

It works with apt (Debian, Ubuntu, Mint), dnf (Fedora) and pacman (Arch). Required: Python 3.9+. Recommended: a native window (PyGObject + WebKit2GTK), `secret-tool` and `xdg-open`. When opened from the menu without Python, the program asks in a dialog (zenity or kdialog) and uses `pkexec`.

### .deb

```bash
sudo apt install ./vulcan-celox_<version>_all.deb
vulcan-celox
```

`apt` also installs the recommended packages: a native window (`python3-gi` and `gir1.2-webkit2-4.1`), a keyring (`libsecret-tools`) and `xdg-utils`. To remove: `sudo apt remove vulcan-celox`.

### .tar.gz (no sudo)

```bash
tar xzf vulcan-celox-<version>-linux.tar.gz
sh vulcan-celox-<version>/install.sh      # installs in ~/.local and asks before installing the libraries
# -y authorizes the libraries; --sem-dependencias only copies the program
vulcan-celox
```

To remove: `sh vulcan-celox-<version>/uninstall.sh` (your data is not deleted).

### How the window opens

1. Its own window (GTK + WebKit) when `python3-gi` and `gir1.2-webkit2-4.1` are installed.
2. Otherwise, an app window of Chromium, Chrome, Brave or Edge.
3. Otherwise, the default browser (the program quits by itself a few minutes after the tab closes).

Linux shortcuts: **Ctrl+Shift+K** search, **Ctrl+Shift+T** new terminal, **Ctrl+Shift+1 to 9** switch terminal.

Requirements: Python 3.9 or newer. Optional: Lerd or Valet for the sites, `libsecret-tools` to keep the Anthropic key in the system keyring.

User data: `~/.local/share/vulcan-celox/` (or `$XDG_DATA_HOME/vulcan-celox`).

Diagnostics without a window: `vulcan-celox --check` (starts the server, checks and exits) and `vulcan-celox --doctor`.
