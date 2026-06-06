import AppKit
import SwiftUI

/// Menu-bar shell with always-visible commands, independent of hotkey registration.
struct MenuBarRootView: View {
    static let commandTitles = ["Open NOVA", "Pair Device", "Settings", "Quit NOVA"]

    @EnvironmentObject private var appState: MacAppState
    @Environment(\.openSettings) private var openSettings

    var body: some View {
        VStack(spacing: 0) {
            Group {
                Button("Open NOVA") { appState.openCompactChat() }
                Button("Pair Device") { appState.openPairingWindow() }
                Button("Settings") { openSettings() }
                Button("Quit NOVA") { NSApplication.shared.terminate(nil) }
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)

            Divider()

            MenuBarView()
        }
        .onAppear {
            appState.menuBarCoordinator.initialize(appState: appState)
        }
    }
}
