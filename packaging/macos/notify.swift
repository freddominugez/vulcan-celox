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
        case "language":
            ShellLanguage.apply(body["language"] as? String, source: webView)
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
