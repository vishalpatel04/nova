import Foundation
import os

/// Structured hotkey / menu-bar lifecycle events (injectable for tests).
enum NovaHotkeyTelemetry {
    static var eventSink: ((String) -> Void)?
    private static let logger = Logger(subsystem: "com.nova.macos.genie", category: "lifecycle")

    static func emit(_ event: String) {
        eventSink?(event)
        logger.info("\(event, privacy: .public)")
    }
}
