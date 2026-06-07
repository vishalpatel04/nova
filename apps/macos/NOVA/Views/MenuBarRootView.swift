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

            if appState.isPaired {
                HStack(spacing: 8) {
                    Circle()
                        .fill(appState.schedulerActive ? Color.green : Color.gray)
                        .frame(width: 6, height: 6)
                    Text("Scheduler")
                        .font(.caption2)
                    Text("tasks \(appState.activeTasksCount)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    if appState.failedTasksCount > 0 {
                        Text("failed \(appState.failedTasksCount)")
                            .font(.caption2)
                            .foregroundStyle(.orange)
                    }
                    if appState.unreadNotificationsCount > 0 {
                        Text("• \(appState.unreadNotificationsCount) unread")
                            .font(.caption2)
                            .foregroundStyle(.blue)
                    }
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .task { await appState.refreshBackgroundStatus() }
                Divider()
            }

            MenuBarView()
        }
        .onAppear {
            appState.menuBarCoordinator.initialize(appState: appState)
        }
    }
}
