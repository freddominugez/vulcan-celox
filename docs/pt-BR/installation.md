# Instalação

## macOS (distribuído)

Requisitos: macOS 13 ou mais novo, Apple Silicon ou Intel, Python 3.9 ou mais novo.

1. Baixe `Vulcan-Terminal-<versão>-macos.dmg` em [Releases](https://github.com/freddominugez/vulcan-hub-painel/releases).
2. Confira, com o `SHA256SUMS` na mesma pasta: `shasum -a 256 -c SHA256SUMS`. Se baixou só o `.dmg`, ele avisa que falta o `.zip`, e tudo bem.
3. Abra o `.dmg` e arraste o **Vulcan Terminal** para Aplicativos.
4. O app não tem certificado da Apple e não é notarizado. Na primeira vez, clique com o botão direito, escolha **Abrir** e confirme. Se o macOS disser que o app está danificado:

   ```bash
   xattr -dr com.apple.quarantine "/Applications/Vulcan Terminal.app"
   ```

Se faltar Python, o app avisa ao abrir e oferece **Instalar ferramentas da Apple** (`xcode-select --install`) ou **Instalar com Homebrew**. Nada é instalado sem a sua confirmação.

Os dados ficam em `~/Library/Application Support/VulcanTerminal/`. Remover o app mantém essa pasta.

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
python3 -m vulcan_terminal --instalar-hook
```

É a única coisa que escreve no `~/.claude/settings.json`, e guarda um backup ao lado. Veja [pairing-hook.md](pairing-hook.md).

## Compilar no macOS

Requisito: Command Line Tools (Swift e Python 3).

```bash
bash scripts/validate.sh     # opcional: todos os sensores
bash scripts/install_app.sh  # compila com swiftc, instala em ~/Applications e cria o atalho na Mesa
bash scripts/package.sh      # pacotes de macOS e Linux em executaveis/
```

## Linux (ainda não distribuído)

O código está no repositório e os testes rodam em contêiner e no CI, incluindo a instalação do `.deb` no Ubuntu 22.04. Ele **não** foi aceito numa área de trabalho real, então nenhum pacote de Linux é publicado. Para ajudar, gere o pacote e experimente numa área de trabalho real:

```bash
python3 scripts/package_linux.py
cd executaveis/linux
sha256sum -c SHA256SUMS
sudo apt install ./vulcan-terminal_<versão>_all.deb
vulcan-terminal --check
```

Python 3.9+ é o único requisito para gerar. A janela usa GTK e WebKit, ou Chromium/Chrome em modo app, ou o navegador. Os atalhos usam Ctrl+Shift. As bibliotecas podem ser instaladas com `vulcan-terminal --instalar-dependencias` (apt, dnf ou pacman), com a sua permissão.

Windows não é suportado: o módulo `pty` do Python não existe lá.
