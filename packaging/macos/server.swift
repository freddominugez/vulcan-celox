// The embedded Python server: finds a usable Python, starts it with the session token, sends its error output to
// the error log in the data folder and tells the app when the process ends on its own.

import AppKit
import WebKit

final class BackendServer {
    private(set) var token = randomToken()
    private(set) var port: Int?
    private var process: Process?
    private var stopping = false
        /// Called on the main thread with the exit code when the server ends without the app asking.
    var onUnexpectedExit: ((Int32) -> Void)?

        /// Runs a windowless executable and returns the exit code (nil if it could not run).
    static func exitStatus(_ path: String, _ arguments: [String]) -> Int32? {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: path)
        proc.arguments = arguments
        proc.standardOutput = FileHandle.nullDevice
        proc.standardError = FileHandle.nullDevice
        do { try proc.run() } catch { return nil }
        proc.waitUntilExit()
        return proc.terminationStatus
    }

        /// Python 3.9+ that really works. macOS's /usr/bin/python3 is only a stub that opens the installer for
        /// Apple's Command Line Tools when they are missing: it is only tested if `xcode-select -p` confirms they exist.
    static func usablePython() -> String? {
        let env = ProcessInfo.processInfo.environment
        var candidates: [String] = []
        if let custom = env["VULCAN_PYTHON"] { candidates.append(custom) }
        if env["VULCAN_PYTHON_ONLY"] != "1" {
            candidates += ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
        }
        let versionCheck = ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"]
        for path in candidates where FileManager.default.isExecutableFile(atPath: path) {
            if path == "/usr/bin/python3", exitStatus("/usr/bin/xcode-select", ["-p"]) != 0 { continue }
            if exitStatus(path, versionCheck) == 0 { return path }
        }
        return nil
    }

    func pythonPath() -> String {
        return BackendServer.usablePython() ?? "/usr/bin/python3"
    }

        /// Same folder the Python side uses on macOS.
    static var dataDir: URL {
        let env = ProcessInfo.processInfo.environment
        return env["VULCAN_CELOX_HOME"].map { URL(fileURLWithPath: ($0 as NSString).expandingTildeInPath) }
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/VulcanCelox")
    }

    static var errorLog: URL { dataDir.appendingPathComponent("logs/servidor-erro.log") }

        /// The error log, opened for appending; it starts over when it grew past 1 MB. Before the first launch there is no data
        /// folder yet: creating it here would stop the Python side from moving the folder with the old name, so the output stays on the console.
    private func errorLogHandle() -> FileHandle? {
        let fm = FileManager.default
        guard fm.fileExists(atPath: BackendServer.dataDir.path) else { return nil }
        let url = BackendServer.errorLog
        try? fm.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true,
                                attributes: [.posixPermissions: 0o700])
        let size = (try? fm.attributesOfItem(atPath: url.path)[.size] as? Int) ?? nil
        if size == nil || size! > 1_048_576 {
            fm.createFile(atPath: url.path, contents: Data(), attributes: [.posixPermissions: 0o600])
        }
        guard let handle = try? FileHandle(forWritingTo: url) else { return nil }
        handle.seekToEndOfFile()
        return handle
    }

        /// The last lines of the error log. Python masks what it writes there, so the lines arrive masked.
    static func errorTail(_ count: Int = 20) -> [String] {
        guard let handle = try? FileHandle(forReadingFrom: errorLog) else { return [] }
        defer { try? handle.close() }
        let size = handle.seekToEndOfFile()
        handle.seek(toFileOffset: size > 65_536 ? size - 65_536 : 0)
        let text = String(decoding: handle.readDataToEndOfFile(), as: UTF8.self)
        let lines = text.split(separator: "\n").map(String.init).filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        return Array(lines.suffix(count))
    }

    func start() throws -> Int {
        let resources = Bundle.main.resourceURL?.path ?? FileManager.default.currentDirectoryPath
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: pythonPath())
        proc.arguments = ["-m", "vulcan_celox", "--serve"]
                // with -m the current folder goes to the start of sys.path: runs inside the bundle resources
        proc.currentDirectoryURL = URL(fileURLWithPath: resources)
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = resources
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["VULCAN_TOKEN"] = token
        env["VULCAN_WATCH_PARENT"] = "1"
        if env["SHELL"] == nil { env["SHELL"] = "/bin/zsh" }
        if env["LANG"] == nil { env["LANG"] = "pt_BR.UTF-8" }
        proc.environment = env
        let out = Pipe()
        proc.standardOutput = out
        proc.standardError = errorLogHandle() ?? FileHandle.standardError

        let found = DispatchSemaphore(value: 0)
        var buffer = ""
        var parsed: Int?
        out.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; found.signal(); return }
            buffer += String(decoding: data, as: UTF8.self)
            if parsed == nil, let range = buffer.range(of: "VULCAN_PORT=") {
                let digits = buffer[range.upperBound...].prefix { $0.isNumber }
                if let value = Int(digits) {
                    parsed = value
                    found.signal()
                }
            }
        }
        proc.terminationHandler = { [weak self] ended in
            let code = ended.terminationStatus
            DispatchQueue.main.async {
                guard let self = self, self.process === ended, !self.stopping else { return }
                self.onUnexpectedExit?(code)
            }
        }
        stopping = false
        try proc.run()
        process = proc
        _ = found.wait(timeout: .now() + 20)
        guard let value = parsed else {
            stopping = true
            proc.terminate()
            throw NSError(domain: "VulcanCelox", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: L("O servidor local não iniciou ({python}).", ["python": pythonPath()])])
        }
        port = value
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { EnvMenu.refresh(self) }  // the menus know about Lerd from the start
        return value
    }

        /// A new process, with a new port and a new token. The page must be loaded again, with the new token.
    func restart() throws -> Int {
        stop()
        token = randomToken()
        port = nil
        return try start()
    }

    func stop() {
        stopping = true
        guard let proc = process, proc.isRunning else { return }
        proc.terminate()
                // waits with a deadline: the server saves the memories and closes the tabs; the window never freezes
        let deadline = Date().addingTimeInterval(6)
        while proc.isRunning && Date() < deadline { usleep(50_000) }
        if proc.isRunning { kill(proc.processIdentifier, SIGKILL) }
    }

    func post(_ path: String) {
        guard let port = port, let url = URL(string: "http://127.0.0.1:\(port)\(path)") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue(token, forHTTPHeaderField: "X-Vulcan-Token")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = Data("{}".utf8)
        URLSession.shared.dataTask(with: req).resume()
    }
}

extension BackendServer {
        /// What Show log opens: the error output, where a crash leaves its traceback; the server log if that is empty.
    static func logToShow() -> URL {
        let size = (try? FileManager.default.attributesOfItem(atPath: errorLog.path)[.size] as? Int) ?? 0
        return size > 0 ? errorLog : dataDir.appendingPathComponent("logs/servidor.log")
    }
}

/// The page's start: the token only exists on the app's own page, so another origin that manages to load here does not see it.
func bootstrapScript(origin: String, token: String, kind: String, restarted: Bool = false) -> WKUserScript {
    let source = """
    if (location.origin === "\(origin)") {
      window.VULCAN = { token: "\(token)", native: true, kind: "\(kind)", restarted: \(restarted) };
    }
    window.__vtErrors = [];
    window.addEventListener("error", function (e) { window.__vtErrors.push(String(e.message || e)); });
    window.addEventListener("unhandledrejection", function (e) { window.__vtErrors.push(String(e.reason)); });
    """
    return WKUserScript(source: source, injectionTime: .atDocumentStart, forMainFrameOnly: true)
}

extension AppDelegate {
        /// The server ended on its own: every window hears the exit code and the last lines of the error log.
    func serverDied(_ code: Int32) {
        let detail: [String: Any] = ["code": Int(code), "tail": BackendServer.errorTail()]
        guard let data = try? JSONSerialization.data(withJSONObject: detail),
              let json = String(data: data, encoding: .utf8) else { return }
        let js = "window.dispatchEvent(new CustomEvent('vulcan-server-died', {detail: \(json)}))"
        main?.evaluate(js)
        popouts.values.forEach { $0.evaluate(js) }
    }

        /// A new server, with a new port and token. Detached windows close, since their terminals died with the server;
        /// the main window loads the app again at the same screen.
    func restartServer() {
        do {
            _ = try server.restart()
        } catch {
            main?.evaluate("window.dispatchEvent(new CustomEvent('vulcan-server-restart-failed', {detail: \(jsString(error.localizedDescription))}))")
            return
        }
        popouts.values.forEach { $0.window.close() }
        popouts = [:]
        guard let main = main, let port = server.port else { return }
        let origin = "http://127.0.0.1:\(port)"
        let content = main.webView.configuration.userContentController
        content.removeAllUserScripts()
        content.addUserScript(bootstrapScript(origin: origin, token: server.token, kind: main.kind, restarted: true))
        main.appOrigin = origin
        if let script = options.evalScript, options.snapshotPath != nil {
            main.onLoad = { DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { main.evaluate(script) } }
        }
        let fragment = main.webView.url?.fragment.map { "#\($0)" } ?? ""
        if let url = URL(string: "\(origin)/\(fragment)") { main.webView.load(URLRequest(url: url)) }
    }
}

/// What the Environment menus know about Lerd, from /api/state: whether there is one, and the panel address it gives.
/// Asked again whenever a menu is about to open; the answer arrives in a moment and the next opening uses it.
enum EnvMenu {
    static var available: Bool?
    static var dashboard: URL?
    static var notices: [NSMenuItem] = []

        /// A line that only shows without Lerd, saying where to install it.
    static func notice() -> NSMenuItem {
        let item = NSMenuItem(title: L("Sem Lerd: instale pelo Início do app"), action: nil, keyEquivalent: "")
        item.isEnabled = false
        item.isHidden = available != false
        notices.append(item)
        return item
    }

    static func refresh(_ server: BackendServer) {
        guard let port = server.port, let url = URL(string: "http://127.0.0.1:\(port)/api/state") else { return }
        var req = URLRequest(url: url, timeoutInterval: 10)
        req.setValue(server.token, forHTTPHeaderField: "X-Vulcan-Token")
        URLSession.shared.dataTask(with: req) { data, _, _ in
            guard let data = data, let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                  let backend = root["backend"] as? [String: Any] else { return }
            let found = backend["available"] as? Bool ?? false
            let address = (backend["dashboard"] as? String).flatMap { URL(string: $0) }
            DispatchQueue.main.async {
                available = found
                dashboard = found ? address : nil
                notices.forEach { $0.isHidden = found }
            }
        }.resume()
    }
}

extension AppDelegate: NSMenuItemValidation {
    func menuNeedsUpdate(_ menu: NSMenu) {
        EnvMenu.refresh(server)
    }

        /// Without Lerd the environment actions are off; the panel item needs the address Lerd gave.
    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        switch item.action {
        case #selector(startEnv), #selector(stopEnv), #selector(restartEnv):
            return EnvMenu.available != false
        case #selector(openDashboard):
            return EnvMenu.dashboard != nil
        default:
            return true
        }
    }
}
