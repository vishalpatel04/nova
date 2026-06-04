import Foundation

/// Structured hotkey / menu-bar lifecycle events (injectable for tests).
enum NovaHotkeyTelemetry {
    static var eventSink: ((String) -> Void)?

    static func emit(_ event: String) {
        eventSink?(event)
    }
}
