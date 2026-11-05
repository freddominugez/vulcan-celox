// Vulcan Celox: native macOS shell (AppKit + WKWebView).
// Starts the embedded Python server, opens the web interface and handles windows,
// menus, the menu bar item and the --snapshot mode used as a visual sensor.

import AppKit
import Security
import WebKit

// MARK: - Configuration

struct LaunchOptions {
    var snapshotPath: String?
    var route = ""
    var size = NSSize(width: 1440, height: 900)
    var wait: Double = 2.5
    var evalScript: String?
    var checkDependencies = false

    init(arguments: [String]) {
        var it = arguments.dropFirst().makeIterator()
        while let arg = it.next() {
            switch arg {
            case "--snapshot": snapshotPath = it.next()
            case "--route": route = it.next() ?? route
            case "--wait": wait = Double(it.next() ?? "") ?? wait
            case "--eval": evalScript = it.next()
            case "--verificar-dependencias", "--check-deps": checkDependencies = true
            case "--size":
                let parts = (it.next() ?? "").split(separator: "x").compactMap { Double($0) }
                if parts.count == 2 { size = NSSize(width: parts[0], height: parts[1]) }
            default: break
            }
        }
    }
}

func randomToken() -> String {
    var bytes = [UInt8](repeating: 0, count: 32)
    _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
    return bytes.map { String(format: "%02x", $0) }.joined()
}

let bgColor = NSColor.windowBackgroundColor  // follows the system until the page paints the theme

// MARK: - Python server: packaging/macos/server.swift

// MARK: - WebView with a window drag area

final class AppWebView: WKWebView {
        /// Rectangles (in points, origin at the top) where a click drags the window.
    var dragRegions: [CGRect] = []
        /// Interactive rectangles inside the drag area.
    var noDragRegions: [CGRect] = []

    private func topLeftPoint(_ event: NSEvent) -> CGPoint {
        let p = convert(event.locationInWindow, from: nil)
        return CGPoint(x: p.x, y: isFlipped ? p.y : bounds.height - p.y)
    }

    override func mouseDown(with event: NSEvent) {
        let p = topLeftPoint(event)
        if dragRegions.contains(where: { $0.contains(p) }) && !noDragRegions.contains(where: { $0.contains(p) }) {
            if event.clickCount == 2 {
                window?.performZoom(nil)
            } else {
                window?.performDrag(with: event)
            }
            return
        }
        super.mouseDown(with: event)
    }
}

// MARK: - Windows

final class WebWindowController: NSObject, NSWindowDelegate, WKScriptMessageHandler, WKNavigationDelegate {
    let window: NSWindow
    let webView: AppWebView
    weak var app: AppDelegate?
    let kind: String
    var onLoad: (() -> Void)?
    var appOrigin = ""
    var popoutId: String?

    init(app: AppDelegate, route: String, size: NSSize, kind: String, title: String) {
        self.app = app
        self.kind = kind
        let config = WKWebViewConfiguration()
        let controller = WKUserContentController()
        let origin = "http://127.0.0.1:\(app.server.port ?? 0)"
        self.appOrigin = origin
        controller.addUserScript(bootstrapScript(origin: origin, token: app.server.token, kind: kind))
        config.userContentController = controller
        let inspect = ProcessInfo.processInfo.environment["VULCAN_INSPECT"] == "1"  // inspector for development only
        configureWebPreferences(config.preferences, inspect: inspect)
        webView = AppWebView(frame: NSRect(origin: .zero, size: size), configuration: config)
        webView.setValue(false, forKey: "drawsBackground")
        if #available(macOS 13.3, *) { webView.isInspectable = inspect }

        window = NSWindow(contentRect: NSRect(origin: .zero, size: size),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                          backing: .buffered, defer: false)
        window.title = title
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.appearance = nil  // follows the system: the WebView's prefers-color-scheme depends on this
        window.backgroundColor = bgColor
        window.minSize = NSSize(width: 900, height: 480)
        window.isReleasedWhenClosed = false
        window.contentView = webView
        super.init()
        controller.add(self, name: "vulcan")
        webView.navigationDelegate = self
        window.delegate = self
        if let port = app.server.port, let url = URL(string: "http://127.0.0.1:\(port)/\(route)") {
            webView.load(URLRequest(url: url))
        }
    }

    func evaluate(_ js: String) {
        webView.evaluateJavaScript(js, completionHandler: nil)
    }

    func command(_ name: String) {
        evaluate("window.vulcanCommand && window.vulcanCommand(\(jsString(name)))")
    }

        /// The window only shows the app itself; external links open in the default browser.
    func isAppURL(_ url: URL?) -> Bool {
        guard let url = url else { return false }
        if url.absoluteString == "about:blank" { return true }
        guard let scheme = url.scheme, let host = url.host, let port = url.port else { return false }
        return "\(scheme)://\(host):\(port)" == appOrigin
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let url = navigationAction.request.url
        if isAppURL(url) {
            decisionHandler(.allow)
            return
        }
        decisionHandler(.cancel)
        if navigationAction.navigationType == .linkActivated, let url = url,
           let scheme = url.scheme, scheme == "http" || scheme == "https" {
            NSWorkspace.shared.open(url)
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        onLoad?()
        onLoad = nil
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        let source = message.frameInfo.securityOrigin
        guard "\(source.protocol)://\(source.host):\(source.port)" == appOrigin,
              let body = message.body as? [String: Any], let type = body["type"] as? String else { return }
        switch type {
        case "dragRegions":
            webView.dragRegions = rects(body["drag"])
            webView.noDragRegions = rects(body["noDrag"])
        case "popout":
            if let id = body["id"] as? String {
                app?.openPopout(id: id, title: body["title"] as? String ?? "Terminal")
            }
        case "focusPopout":
            if let id = body["id"] as? String { app?.focusPopout(id: id) }
        case "setTitle":
            if let title = body["title"] as? String { window.title = title }
        case "close":
            window.performClose(nil)
        case "relaunch":
            app?.relaunch()
        case "openServerLog":
            NSWorkspace.shared.open(BackendServer.logToShow())
        case "restartServer":
            app?.restartServer()
        case "pickFolder":
            pickFolder(id: body["id"] as? String ?? "", start: body["start"] as? String, purpose: body["purpose"] as? String)
        case "copy":
                        // clipboard through the shell: does not depend on the user gesture or on WebKit permission
            if let text = body["text"] as? String {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(text, forType: .string)
            }
        default:
            SystemNotice.handle(type, body, webView)
        }
    }

        /// Native folder picker; answers the interface with the `vulcan-folder-picked` event (null path if cancelled).
    private func pickFolder(id: String, start: String?, purpose: String?) {
        let panel = makePickPanel(purpose: purpose)
        if let start = start, !start.isEmpty {
            panel.directoryURL = URL(fileURLWithPath: (start as NSString).expandingTildeInPath, isDirectory: true)
        }
        panel.beginSheetModal(for: window) { [weak self] response in
            let path = response == .OK ? panel.url?.path : nil
            let value = path.map { jsString($0) } ?? "null"
            self?.evaluate("window.dispatchEvent(new CustomEvent('vulcan-folder-picked', {detail: {id: \(jsString(id)), path: \(value)}}))")
        }
    }

    private func rects(_ value: Any?) -> [CGRect] {
        guard let list = value as? [[String: Any]] else { return [] }
        return list.compactMap { r in
            guard let x = r["x"] as? Double, let y = r["y"] as? Double,
                  let w = r["w"] as? Double, let h = r["h"] as? Double else { return nil }
            return CGRect(x: x, y: y, width: w, height: h)
        }
    }

    func windowWillClose(_ notification: Notification) {
        if kind == "popout", let id = popoutId {
            app?.popoutClosed(id: id)
        } else if kind == "main" {
            app?.mainWindowClosed()
        }
    }
}

func jsString(_ value: String) -> String {
    let data = try? JSONSerialization.data(withJSONObject: [value])
    let array = data.flatMap { String(data: $0, encoding: .utf8) } ?? "[\"\"]"
    return String(array.dropFirst().dropLast())
}

// MARK: - App

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let options: LaunchOptions
    let server = BackendServer()
    var main: WebWindowController?
    var popouts: [String: WebWindowController] = [:]
    var statusItem: NSStatusItem?

    init(options: LaunchOptions) {
        self.options = options
    }

        /// Opens a new instance of the installed app and quits this one (the interface asked, after the user clicked).
    func relaunch() {
        let config = NSWorkspace.OpenConfiguration()
        config.createsNewApplicationInstance = true
        NSWorkspace.shared.openApplication(at: Bundle.main.bundleURL, configuration: config) { _, _ in
            DispatchQueue.main.async { NSApp.terminate(nil) }
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        if options.snapshotPath == nil, BackendServer.usablePython() == nil {
            offerPythonInstall()
            exit(1)
        }
        do {
            _ = try server.start()
        } catch {
            let alert = NSAlert()
            alert.messageText = L("Não foi possível iniciar o Vulcan Celox")
            alert.informativeText = error.localizedDescription
            if options.snapshotPath == nil { alert.runModal() }
            fputs("erro: \(error.localizedDescription)\n", stderr)
            exit(1)
        }
        server.onUnexpectedExit = { [weak self] code in self?.serverDied(code) }
        buildMenus()
        if options.snapshotPath != nil {
            runSnapshot()
            return
        }
        buildStatusItem()
        openMain()
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { openMain() }
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false  // stays in the menu bar, like Herd
    }

    func applicationWillTerminate(_ notification: Notification) {
        server.stop()
    }

    // MARK: windows
    func openMain() {
        if let main = main {
            main.window.makeKeyAndOrderFront(nil)
            return
        }
        let controller = WebWindowController(app: self, route: options.route, size: NSSize(width: 1320, height: 840),
                                             kind: "main", title: "Vulcan Celox")
        controller.window.setFrameAutosaveName("VulcanCeloxMain")
        if controller.window.frame.origin == .zero { controller.window.center() }
        controller.window.makeKeyAndOrderFront(nil)
        main = controller
    }

    func mainWindowClosed() {
        main = nil
    }

    func openPopout(id: String, title: String) {
        if let existing = popouts[id] {
            existing.window.makeKeyAndOrderFront(nil)
            return
        }
        let controller = WebWindowController(app: self, route: "#/popout/\(id)", size: NSSize(width: 900, height: 560),
                                             kind: "popout", title: title)
        controller.popoutId = id
        let origin = main?.window.frame.origin ?? .zero
        controller.window.setFrameOrigin(NSPoint(x: origin.x + 60, y: origin.y + 60))
        controller.window.makeKeyAndOrderFront(nil)
        popouts[id] = controller
    }

    func focusPopout(id: String) {
        popouts[id]?.window.makeKeyAndOrderFront(nil)
    }

    func popoutClosed(id: String) {
        popouts[id] = nil
        main?.evaluate("window.dispatchEvent(new CustomEvent('vulcan-popout-closed', {detail: \(jsString(id))}))")
    }

    // MARK: menus
    func buildMenus() {
        let menubar = NSMenu()

        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: L("Sobre o Vulcan Celox"), action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: L("Ocultar Vulcan Celox"), action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: L("Sair do Vulcan Celox"), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        menubar.addItem(appItem)

        let fileItem = NSMenuItem()
        let fileMenu = NSMenu(title: L("Arquivo"))
        fileMenu.addItem(item("Novo terminal", #selector(newTerminal), "t"))
        fileMenu.addItem(item("Destacar terminal em janela", #selector(popoutTerminal), "d", [.command, .shift]))
        fileMenu.addItem(.separator())
        fileMenu.addItem(item("Buscar…", #selector(openPalette), "k"))
        fileMenu.addItem(.separator())
        fileMenu.addItem(withTitle: L("Fechar janela"), action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        fileItem.submenu = fileMenu
        menubar.addItem(fileItem)

        let editItem = NSMenuItem()
        let editMenu = NSMenu(title: L("Editar"))
        editMenu.addItem(withTitle: L("Desfazer"), action: Selector(("undo:")), keyEquivalent: "z")
        editMenu.addItem(withTitle: L("Refazer"), action: Selector(("redo:")), keyEquivalent: "Z")
        editMenu.addItem(.separator())
        editMenu.addItem(withTitle: L("Recortar"), action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: L("Copiar"), action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: L("Colar"), action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: L("Selecionar tudo"), action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = editMenu
        menubar.addItem(editItem)

        let goItem = NSMenuItem()
        let goMenu = NSMenu(title: L("Ir"))
        goMenu.addItem(item("Visão geral", #selector(goOverview), "1"))
        goMenu.addItem(item("Terminais", #selector(goTerminals), "2"))
        goMenu.addItem(item("Tarefas", #selector(goTasks), "3"))
        goMenu.addItem(item("Post-its", #selector(goNotes), "4"))
        goMenu.addItem(item("Tags", #selector(goTags), "5"))
        goMenu.addItem(item("Depuração", #selector(goDebug), "e", [.command, .shift]))
        goItem.submenu = goMenu
        menubar.addItem(goItem)

        let envItem = NSMenuItem()
        let envMenu = NSMenu(title: L("Ambiente"))
        envMenu.delegate = self
        envMenu.addItem(EnvMenu.notice())
        envMenu.addItem(item("Iniciar ambiente", #selector(startEnv), ""))
        envMenu.addItem(item("Parar ambiente", #selector(stopEnv), ""))
        envMenu.addItem(item("Reiniciar ambiente", #selector(restartEnv), ""))
        envMenu.addItem(.separator())
        envMenu.addItem(item("Abrir painel do Lerd", #selector(openDashboard), ""))
        envItem.submenu = envMenu
        menubar.addItem(envItem)

        let windowItem = NSMenuItem()
        let windowMenu = NSMenu(title: L("Janela"))
        windowMenu.addItem(withTitle: L("Minimizar"), action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: L("Zoom"), action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        windowMenu.addItem(.separator())
        windowMenu.addItem(item("Janela principal", #selector(showMain), "0"))
        windowItem.submenu = windowMenu
        menubar.addItem(windowItem)
        NSApp.windowsMenu = windowMenu

                // macOS Help menu; ⌘? opens Help at the section of the current screen
        let helpItem = NSMenuItem()
        let helpMenu = NSMenu(title: L("Ajuda"))
        helpMenu.addItem(item("Ajuda do Vulcan Celox", #selector(goHelp), "?"))
        helpMenu.addItem(item("Início e guia", #selector(goHome), ""))
        helpItem.submenu = helpMenu
        menubar.addItem(helpItem)
        NSApp.helpMenu = helpMenu

        NSApp.mainMenu = menubar
    }

    func item(_ title: String, _ action: Selector, _ key: String, _ mods: NSEvent.ModifierFlags = [.command]) -> NSMenuItem {
        let menuItem = NSMenuItem(title: L(title), action: action, keyEquivalent: key)
        menuItem.keyEquivalentModifierMask = mods
        menuItem.target = self
        return menuItem
    }

    func buildStatusItem() {
        let status = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let button = status.button {
            button.image = NSImage(systemSymbolName: "terminal", accessibilityDescription: "Vulcan Celox")
        }
        let menu = NSMenu()
        menu.delegate = self
        menu.addItem(item("Abrir Vulcan Celox", #selector(showMain), ""))
        menu.addItem(item("Novo terminal", #selector(newTerminal), ""))
        menu.addItem(.separator())
        menu.addItem(EnvMenu.notice())
        menu.addItem(item("Abrir painel do Lerd", #selector(openDashboard), ""))
        menu.addItem(item("Iniciar ambiente", #selector(startEnv), ""))
        menu.addItem(item("Parar ambiente", #selector(stopEnv), ""))
        menu.addItem(.separator())
        let quit = NSMenuItem(title: L("Sair"), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        menu.addItem(quit)
        status.menu = menu
        statusItem = status
    }

        // MARK: actions
    func withMain(_ body: @escaping (WebWindowController) -> Void) {
        if main == nil { openMain() }
        guard let main = main else { return }
        main.window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        body(main)
    }

    func keyController() -> WebWindowController? {
        if let key = NSApp.keyWindow {
            if key === main?.window { return main }
            return popouts.values.first { $0.window === key }
        }
        return main
    }

    @objc func showMain() { withMain { _ in } }
    @objc func newTerminal() { withMain { $0.command("newTerminal") } }
    @objc func popoutTerminal() { main?.command("popoutTerminal") }
    @objc func openPalette() { withMain { $0.command("palette") } }
    @objc func goOverview() { withMain { $0.command("go:overview") } }
    @objc func goTerminals() { withMain { $0.command("go:terminals") } }
    @objc func goTasks() { withMain { $0.command("go:tasks") } }
    @objc func goNotes() { withMain { $0.command("go:notes") } }
    @objc func goTags() { withMain { $0.command("go:tags") } }
    @objc func goDebug() { withMain { $0.command("go:depuracao") } }
    @objc func goHelp() { withMain { $0.command("help") } }
    @objc func goHome() { withMain { $0.command("go:inicio") } }
    @objc func startEnv() { server.post("/api/services/start"); main?.command("refresh") }
    @objc func stopEnv() { server.post("/api/services/stop"); main?.command("refresh") }
    @objc func restartEnv() { server.post("/api/services/restart"); main?.command("refresh") }
    @objc func openDashboard() {
        if let url = EnvMenu.dashboard { NSWorkspace.shared.open(url) }
    }

    // MARK: snapshot (visual sensor)
    func runSnapshot() {
        let controller = WebWindowController(app: self, route: options.route, size: options.size,
                                             kind: "main", title: "Vulcan Celox")
        controller.window.setFrameOrigin(NSPoint(x: -20000, y: -20000))  // offscreen
        controller.window.orderFront(nil)
        main = controller
        controller.onLoad = { [weak self] in
            guard let self = self else { return }
            if let js = self.options.evalScript {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { controller.evaluate(js) }
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + self.options.wait) {
                            // the visual sensor also fails if the interface threw a JavaScript error
              if !controller.isAppURL(controller.webView.url) {
                  fputs("snapshot: a janela saiu do app para \(controller.webView.url?.absoluteString ?? "nada")\n", stderr)
                  self.server.stop()
                  exit(4)
              }
              controller.webView.evaluateJavaScript("JSON.stringify(window.__vtErrors || [])") { result, _ in
                if let errors = result as? String, errors != "[]" {
                    fputs("snapshot: erro de JavaScript na interface: \(errors)\n", stderr)
                    self.server.stop()
                    exit(3)
                }
                let snapConfig = WKSnapshotConfiguration()
                snapConfig.afterScreenUpdates = true
                controller.webView.takeSnapshot(with: snapConfig) { image, error in
                    guard let image = image, let tiff = image.tiffRepresentation,
                          let rep = NSBitmapImageRep(data: tiff),
                          let png = rep.representation(using: .png, properties: [:]),
                          let path = self.options.snapshotPath else {
                        fputs("snapshot falhou: \(error?.localizedDescription ?? "sem imagem")\n", stderr)
                        self.server.stop()
                        exit(1)
                    }
                    do {
                        try png.write(to: URL(fileURLWithPath: path))
                        print("snapshot: \(path)")
                        self.server.stop()
                        exit(0)
                    } catch {
                        fputs("snapshot falhou ao gravar: \(error)\n", stderr)
                        self.server.stop()
                        exit(1)
                    }
                }
              }
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + max(30, options.wait + 20)) {
            fputs("snapshot: tempo esgotado\n", stderr)
            self.server.stop()
            exit(2)
        }
    }
}

// MARK: - Dependencies

/// No usable Python: explains and offers to install. Nothing is installed without the user's confirmation
/// (Apple's installer and Terminal with Homebrew ask for their own confirmation).
func offerPythonInstall() {
    NSApplication.shared.activate(ignoringOtherApps: true)
    let brew = ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"].first { FileManager.default.isExecutableFile(atPath: $0) }
    let alert = NSAlert()
    alert.messageText = L("O Vulcan Celox precisa do Python 3")
    alert.informativeText = L("Não encontramos um Python 3.9 ou mais novo neste Mac. Escolha como instalar; " +
        "nada é instalado sem a sua confirmação. Quando terminar, abra o Vulcan Celox de novo.")
    alert.addButton(withTitle: L("Instalar ferramentas da Apple"))
    if brew != nil { alert.addButton(withTitle: L("Instalar com Homebrew")) }
    alert.addButton(withTitle: L("Cancelar"))
    let response = alert.runModal()
    if response == .alertFirstButtonReturn {
                // opens the system dialog "Install command line developer tools"
        _ = BackendServer.exitStatus("/usr/bin/xcode-select", ["--install"])
    } else if let brew = brew, response == .alertSecondButtonReturn {
        let script = "tell application \"Terminal\"\nactivate\ndo script \"\(brew) install python\"\nend tell"
        _ = BackendServer.exitStatus("/usr/bin/osascript", ["-e", script])
    }
}

/// `vulcan-celox --verificar-dependencias`: says which Python will be used (0) or what is missing (1).
func checkDependenciesAndExit() -> Never {
    if let python = BackendServer.usablePython() {
        print(L("Vulcan Celox: dependências ok (Python: {python})", ["python": python]))
        exit(0)
    }
    print(L("Vulcan Celox: falta o Python 3.9 ou mais novo. Instale com `xcode-select --install` ou `brew install python`."))
    exit(1)
}

// MARK: - main

let options = LaunchOptions(arguments: CommandLine.arguments)
if options.checkDependencies { checkDependenciesAndExit() }
let application = NSApplication.shared
application.setActivationPolicy(options.snapshotPath == nil ? .regular : .accessory)
let delegate = AppDelegate(options: options)
application.delegate = delegate
application.run()
