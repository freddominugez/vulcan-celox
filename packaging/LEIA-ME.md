# Vulcan Celox: instalação

Pacotes gerados por `bash scripts/package.sh` (no macOS). Confira a integridade com `shasum -a 256 -c SHA256SUMS` (macOS) ou `sha256sum -c SHA256SUMS` (Linux).

| Pasta | Arquivo | Para |
|-------|---------|------|
| `macos/` | `Vulcan-Celox-<versão>-macos.dmg` | instalar arrastando para Aplicativos |
| `macos/` | `Vulcan-Celox-<versão>-macos.zip` | o mesmo app, compactado |
| `linux/` | `vulcan-celox_<versão>_all.deb` | Debian, Ubuntu, Mint e derivados |
| `linux/` | `vulcan-celox-<versão>-linux.tar.gz` | qualquer distribuição, sem sudo |

## macOS (13 ou mais novo, Apple Silicon ou Intel)

1. Abra o `.dmg` e arraste **Vulcan Celox** para **Aplicativos**.
2. Requisito: Python 3.9 ou mais novo. Se faltar, o app avisa ao abrir e oferece **Instalar ferramentas da Apple** (`xcode-select --install`) ou **Instalar com Homebrew**; nada é instalado sem a sua confirmação. Para só verificar: `"/Applications/Vulcan Celox.app/Contents/MacOS/vulcan-celox" --verificar-dependencias`.
3. O app não é assinado com certificado da Apple. Na primeira vez: clique com o botão direito no app, **Abrir**, e confirme. Se o macOS disser que o app "está danificado", rode `xattr -dr com.apple.quarantine "/Applications/Vulcan Celox.app"`.

Dados do usuário: `~/Library/Application Support/VulcanCelox/`. Para remover, apague o app de Aplicativos (os dados ficam).

## Linux

### Gerar os pacotes diretamente no Linux Mint

O código completo está neste repositório. Com Python 3.9 ou mais novo:

```bash
python3 scripts/package_linux.py
cd executaveis/linux
sha256sum -c SHA256SUMS
sudo apt install ./vulcan-celox_<versão>_all.deb
vulcan-celox --check
vulcan-celox
```

Esse comando gera o `.deb`, o `.tar.gz`, as instruções e as somas SHA-256 sem
precisar de Swift, macOS, pip ou Node.js. Os ícones próprios do produto estão
incluídos em `packaging/linux/icons/`. O `apt` obtém as bibliotecas do sistema;
Lerd ou Valet são opcionais para gerenciar sites PHP, e são instalados à parte.
Os dados pessoais e as chaves da API não fazem parte dos pacotes.

### Bibliotecas necessárias (com a sua permissão)

O programa verifica o que falta e só instala depois que você autoriza (pede a senha de administrador):

```bash
vulcan-celox --verificar-dependencias   # só verifica e mostra o comando
vulcan-celox --instalar-dependencias    # mostra o que falta, pergunta [s/N] e instala
vulcan-celox --instalar-dependencias -y # autoriza sem perguntar
```

Funciona com apt (Debian, Ubuntu, Mint), dnf (Fedora) e pacman (Arch). Obrigatório: Python 3.9+. Recomendados: janela nativa (PyGObject + WebKit2GTK), `secret-tool` e `xdg-open`. Aberto pelo menu sem Python, o programa pergunta numa janela (zenity ou kdialog) e usa o `pkexec`.

### .deb

```bash
sudo apt install ./vulcan-celox_<versão>_all.deb
vulcan-celox
```

O `apt` também instala o recomendado: janela nativa (`python3-gi` e `gir1.2-webkit2-4.1`), chaveiro (`libsecret-tools`) e `xdg-utils`. Remover: `sudo apt remove vulcan-celox`.

### .tar.gz (sem sudo)

```bash
tar xzf vulcan-celox-<versão>-linux.tar.gz
sh vulcan-celox-<versão>/install.sh      # instala em ~/.local e pergunta antes de instalar as bibliotecas
# -y autoriza as bibliotecas; --sem-dependencias só copia o programa
vulcan-celox
```

Remover: `sh vulcan-celox-<versão>/uninstall.sh` (os seus dados não são apagados).

### Como a janela abre

1. Janela própria (GTK + WebKit) quando `python3-gi` e `gir1.2-webkit2-4.1` estão instalados.
2. Senão, janela de aplicativo do Chromium, Chrome, Brave ou Edge.
3. Senão, no navegador padrão (o programa encerra sozinho alguns minutos depois que a aba fecha).

Atalhos no Linux: **Ctrl+Shift+K** busca, **Ctrl+Shift+T** novo terminal, **Ctrl+Shift+1 a 9** troca de terminal.

Requisitos: Python 3.9 ou mais novo. Opcionais: Lerd ou Valet para os sites, `libsecret-tools` para guardar a chave da Anthropic no chaveiro do sistema.

Dados do usuário: `~/.local/share/vulcan-celox/` (ou `$XDG_DATA_HOME/vulcan-celox`).

Diagnóstico sem janela: `vulcan-celox --check` (sobe o servidor, verifica e sai) e `vulcan-celox --doctor`.
