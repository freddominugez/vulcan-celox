# Instalação

## macOS (distribuído)

Requisitos: macOS 13 ou mais novo, Apple Silicon ou Intel, Python 3.9 ou mais novo.

1. Baixe `Vulcan-Celox-<versão>-macos.dmg` em [Releases](https://github.com/freddominugez/vulcan-celox/releases).
2. Confira, com o `SHA256SUMS` na mesma pasta: `shasum -a 256 -c SHA256SUMS`. Se baixou só o `.dmg`, ele avisa que falta o `.zip`, e tudo bem.
3. Abra o `.dmg` e arraste o **Vulcan Celox** para Aplicativos.
4. O app não tem certificado da Apple e não é notarizado. Na primeira vez, clique com o botão direito, escolha **Abrir** e confirme. Se o macOS disser que o app está danificado:

   ```bash
   xattr -dr com.apple.quarantine "/Applications/Vulcan Celox.app"
   ```

Se faltar Python, o app avisa ao abrir e oferece **Instalar ferramentas da Apple** (`xcode-select --install`) ou **Instalar com Homebrew**. Nada é instalado sem a sua confirmação.

Os dados ficam em `~/Library/Application Support/VulcanCelox/`. Remover o app mantém essa pasta.

### Ferramentas opcionais

| Ferramenta | Para |
|------------|------|
| [Lerd](https://github.com/lerd-env/lerd) ou Laravel Valet | Sites PHP. Sem eles o app abre em modo local: terminais, agentes, prompts, projetos Node e o caderno continuam funcionando |
| Claude Code, Codex | Os agentes cujas sessões são lidas |
| `zstd` | Ler sessões comprimidas do Codex (`.jsonl.zst`). Sem ele ficam de fora e são contadas no `--doctor` |
| Chave da Anthropic | Só para a documentação de sessão com IA |

### Pareamento exato com o Claude Code (opcional)

Sem hook, aba e sessão são pareadas por pasta e horário. Para o vínculo exato:

```bash
python3 -m vulcan_celox --instalar-hook
```

É a única coisa que escreve no `~/.claude/settings.json`, e guarda um backup ao lado. Veja [pairing-hook.md](pairing-hook.md).

## Compilar no macOS

Requisito: Command Line Tools (Swift e Python 3).

```bash
bash scripts/validate.sh     # opcional: todos os sensores
bash scripts/install_app.sh  # compila com swiftc, instala em ~/Applications e cria o atalho na Mesa
bash scripts/package.sh      # pacotes de macOS e Linux em executaveis/
```

## O Lerd é opcional

O [Lerd](https://lerd.sh) só é preciso para rodar sites PHP e Laravel. Terminais, agentes e projetos Node funcionam sem ele. Na tela **Início**, **Instalar** mostra o comando oficial e o roda num terminal à vista, e **Não uso** dispensa o passo. Ele não inicia com o app, a menos que você ligue o botão de raio.

## Windows (versão de teste)

Windows 10 versão 1809 ou mais novo, ou Windows 11. O Python vem junto, então não há mais nada para instalar.

1. Baixe `Vulcan-Celox-<versão>-windows.zip` em Releases e confira com `SHA256SUMS-windows`.
2. Extraia a pasta onde quiser e abra `Vulcan Celox.cmd`.
3. O pacote não é assinado, então o Windows pode avisar de editor desconhecido: escolha **Mais informações** e depois **Executar assim mesmo**.

O app abre em janela própria do Microsoft Edge ou do Chrome. O shell padrão é o PowerShell. Os dados ficam em `%APPDATA%\VulcanCelox`, e a chave da Anthropic vai para o Gerenciador de Credenciais do Windows.

Sem suporte no Windows: Lerd e Valet (os sites PHP ficam em modo local), o hook opcional dos agentes (`--instalar-hook`) e clicar em caminhos `C:\...` no terminal. Sem a checagem de primeiro plano, a aba pareada vale enquanto estiver aberta.

## Linux (versão de teste)

Baixe o `.deb` ou o `.tar.gz` na pre-release em Releases, ou gere os pacotes. Os testes rodam em contêiner e no CI, incluindo a instalação do `.deb` no Ubuntu 22.04, mas ele **não** foi aceito numa área de trabalho real, então ainda não há Release estável para Linux. Para gerar:

```bash
python3 scripts/package_linux.py
cd executaveis/linux
sha256sum -c SHA256SUMS
sudo apt install ./vulcan-celox_<versão>_all.deb
vulcan-celox --check
```

Python 3.9+ é o único requisito para gerar. A janela usa GTK e WebKit, ou Chromium/Chrome em modo app, ou o navegador. Os atalhos usam Ctrl+Shift. As bibliotecas podem ser instaladas com `vulcan-celox --instalar-dependencias` (apt, dnf ou pacman), com a sua permissão.

