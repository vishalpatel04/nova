import AppKit
import SwiftUI

/// Menu-bar startup: register summon hotkey once and emit readiness telemetry.
@MainActor
final class MenuBarCoordinator {
    private var didInitialize = false
    private(set) var startupWindowRequestCount = 0
    private(set) var readinessCount = 0

    func initialize(appState: MacAppState) {
        guard !didInitialize else { return }
        didInitialize = true
        appState.hotkey.registerAtStartup()
        readinessCount += 1
        NovaHotkeyTelemetry.emit("nova_menu_bar_ready")
        startupWindowRequestCount += 1
        appState.requestInitialWindowOpen()
    }

    func resetForTesting() {
        didInitialize = false
        startupWindowRequestCount = 0
        readinessCount = 0
    }
}
