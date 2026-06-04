import AppKit
import SwiftUI

/// Menu-bar startup: register summon hotkey once and emit readiness telemetry.
@MainActor
enum MenuBarCoordinator {
    private static var didInitialize = false

    static func initialize(appState: MacAppState) {
        guard !didInitialize else { return }
        didInitialize = true
        appState.hotkey.registerAtStartup()
        NovaHotkeyTelemetry.emit("nova_menu_bar_ready")
    }

    static func resetForTesting() {
        didInitialize = false
    }
}
