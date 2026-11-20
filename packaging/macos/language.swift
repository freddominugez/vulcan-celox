// Shared offline locale manifest and menus that follow the selected interface language.
import AppKit
import WebKit

private struct ProductLocale: Decodable {
    let id: String
    let locale: String
    let label: String
    let aliases: [String]
    let help: String
}

enum ShellLanguage {
    private static let folder = Bundle.main.resourceURL?.appendingPathComponent("vulcan_celox/web/i18n")
    private static let locales: [ProductLocale] = {
        guard let url = folder?.appendingPathComponent("languages.json"), let data = try? Data(contentsOf: url),
              let values = try? JSONDecoder().decode([ProductLocale].self, from: data) else { return [] }
        return values
    }()
    static func normalize(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: "_", with: "-").lowercased() else { return nil }
        return locales.first(where: { $0.aliases.contains(value) })?.id
    }
    private static var current: String = {
        let env = ProcessInfo.processInfo.environment
        if let chosen = env["VULCAN_LANGUAGE"], !chosen.isEmpty { return normalize(chosen) ?? "en" }
        let home = env["VULCAN_CELOX_HOME"].map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/VulcanCelox")
        guard let data = try? Data(contentsOf: home.appendingPathComponent("preferences.json")),
              let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return "en" }
        return normalize(((root["data"] as? [String: Any]) ?? root)["language"] as? String) ?? "en"
    }()
    private static func dictionary(_ code: String) -> [String: String] {
        guard code != "pt", let url = folder?.appendingPathComponent("\(code).json"),
              let data = try? Data(contentsOf: url),
              let values = (try? JSONSerialization.jsonObject(with: data)) as? [String: String] else { return [:] }
        return values
    }
    private static var table = dictionary(current)

    static func text(_ value: String) -> String { current == "pt" ? value : (table[value] ?? value) }

    static func apply(_ value: String?, source: WKWebView) {
        guard let chosen = normalize(value), let app = NSApp.delegate as? AppDelegate else { return }
        current = chosen
        table = dictionary(chosen)
        EnvMenu.notices.removeAll()
        app.buildMenus()
        if let old = app.statusItem {
            NSStatusBar.system.removeStatusItem(old)
            app.statusItem = nil
            app.buildStatusItem()
        }
        let windows = [app.main].compactMap { $0 } + Array(app.popouts.values)
        windows.filter { $0.webView !== source }.forEach { $0.webView.reload() }
        let result: [String: Any] = ["language": chosen, "menus": NSApp.mainMenu?.items.map { $0.submenu?.title ?? $0.title } ?? []]
        if let data = try? JSONSerialization.data(withJSONObject: result), let json = String(data: data, encoding: .utf8) {
            source.evaluateJavaScript("window.dispatchEvent(new CustomEvent('vulcan-language-applied', {detail: \(json)}))")
        }
    }
}

func L(_ text: String, _ values: [String: String] = [:]) -> String {
    var output = ShellLanguage.text(text)
    for (name, value) in values { output = output.replacingOccurrences(of: "{\(name)}", with: value) }
    return output
}
