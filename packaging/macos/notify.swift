// System notification and Dock icon badge, requested by the interface.
// The signature is ad hoc, so macOS may refuse authorization: the Dock badge stays and the interface is informed.

import AppKit
import UserNotifications
import WebKit

enum SystemNotice {
    static func handle(_ type: String, _ body: [String: Any], _ webView: WKWebView) {
        switch type {
        case "notice":
            send(title: body["title"] as? String ?? "", text: body["text"] as? String ?? "", webView)
        case "badge":
            let count = body["count"] as? Int ?? 0
            NSApp.dockTile.badgeLabel = count > 0 ? String(count) : nil
        default:
            break
        }
    }

    private static func send(title: String, text: String, _ webView: WKWebView) {
        guard Bundle.main.bundleIdentifier != nil else { return }
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .badge]) { granted, _ in
            guard granted else {
                DispatchQueue.main.async {
                    NSApp.requestUserAttention(.informationalRequest)
                    webView.evaluateJavaScript("window.dispatchEvent(new CustomEvent('vulcan-notice-denied'))")
                }
                return
            }
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = text
            center.add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
        }
    }
}

/// The visual sensor runs with the window offscreen, sometimes with the Mac screen off: WebKit would suspend the page
/// and no timer would run. In the real app the system default applies, which saves energy with the window hidden.
func configureWebPreferences(_ preferences: WKPreferences, inspect: Bool) {
    preferences.setValue(inspect, forKey: "developerExtrasEnabled")
    if CommandLine.arguments.contains("--snapshot"), #available(macOS 14.0, *) {
        preferences.inactiveSchedulingPolicy = .none
    }
}

// MARK: - Shell language

/// Shell language: VULCAN_LANGUAGE, otherwise `language` in preferences.json in the data folder; default en.
private let shellLanguage: String = {
    let env = ProcessInfo.processInfo.environment
    if let chosen = env["VULCAN_LANGUAGE"], ["en", "pt"].contains(chosen) { return chosen }
    let home = env["VULCAN_CELOX_HOME"].map { URL(fileURLWithPath: $0) }
        ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/VulcanCelox")
    if let data = try? Data(contentsOf: home.appendingPathComponent("preferences.json")),
       let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
        let stored = ((root["data"] as? [String: Any]) ?? root)["language"] as? String
        if let language = stored, ["en", "pt"].contains(language) { return language }
    }
    return "en"
}()

/// The same dictionary as the interface (Portuguese source text -> English), read once from the bundle's Resources.
private let shellDictionary: [String: String] = {
    guard let url = Bundle.main.resourceURL?.appendingPathComponent("vulcan_celox/web/i18n/en.json"),
          let data = try? Data(contentsOf: url),
          let table = (try? JSONSerialization.jsonObject(with: data)) as? [String: String] else { return [:] }
    return table
}()

/// Text in the current language; `{nome}` is filled with `values`. In Portuguese it returns the source text.
func L(_ text: String, _ values: [String: String] = [:]) -> String {
    var out = shellLanguage == "pt" ? text : (shellDictionary[text] ?? text)
    for (name, value) in values { out = out.replacingOccurrences(of: "{\(name)}", with: value) }
    return out
}
