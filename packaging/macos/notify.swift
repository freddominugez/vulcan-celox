// Aviso do sistema e número no ícone do Dock, pedidos pela interface.
// A assinatura é ad hoc, então o macOS pode recusar a autorização: fica o número no Dock e a interface é avisada.

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

/// O sensor visual roda com a janela fora da tela, às vezes com o Mac de tela apagada: o WebKit suspenderia a página
/// e nenhum timer rodaria. No app de verdade vale o padrão do sistema, que poupa energia com a janela oculta.
func configureWebPreferences(_ preferences: WKPreferences, inspect: Bool) {
    preferences.setValue(inspect, forKey: "developerExtrasEnabled")
    if CommandLine.arguments.contains("--snapshot"), #available(macOS 14.0, *) {
        preferences.inactiveSchedulingPolicy = .none
    }
}

// MARK: - Idioma da casca

/// Idioma da casca: VULCAN_LANGUAGE, senão `language` em preferences.json na pasta de dados; padrão en.
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

/// O mesmo dicionário da interface (texto-fonte em português -> inglês), lido uma vez dos Resources do bundle.
private let shellDictionary: [String: String] = {
    guard let url = Bundle.main.resourceURL?.appendingPathComponent("vulcan_celox/web/i18n/en.json"),
          let data = try? Data(contentsOf: url),
          let table = (try? JSONSerialization.jsonObject(with: data)) as? [String: String] else { return [:] }
    return table
}()

/// Texto na língua atual; `{nome}` é preenchido com `values`. Em português devolve o texto-fonte.
func L(_ text: String, _ values: [String: String] = [:]) -> String {
    var out = shellLanguage == "pt" ? text : (shellDictionary[text] ?? text)
    for (name, value) in values { out = out.replacingOccurrences(of: "{\(name)}", with: value) }
    return out
}
