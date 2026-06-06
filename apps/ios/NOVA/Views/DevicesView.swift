import SwiftUI

struct DevicesView: View {
    @EnvironmentObject private var appState: AppState
    @State private var devices: [Device] = []
    @State private var systemStatus: SystemStatus?
    @State private var errorMessage: String?

    var body: some View {
        List {
            if let status = systemStatus {
                Section("Workers") {
                    LabeledContent("Online", value: "\(status.workersOnline)/\(status.workersTotal)")
                    LabeledContent("Stale", value: "\(status.workersStale)")
                    LabeledContent("Offline", value: "\(status.workersOffline)")
                    if !status.hasEligibleOnlineWorker {
                        Label("No eligible worker online — missions may queue.", systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.orange)
                    }
                }
            }
            Section("Devices") {
                if devices.isEmpty {
                    Text(errorMessage ?? "No devices").foregroundStyle(.secondary)
                } else {
                    ForEach(devices) { device in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(device.name).font(.headline)
                            Text(device.deviceType).font(.caption).foregroundStyle(.secondary)
                            StatusBadge(status: device.status)
                        }
                    }
                }
            }
        }
        .navigationTitle("Devices")
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        guard appState.isPaired else {
            errorMessage = "Pair device to see live status."
            return
        }
        do {
            async let d = appState.api.fetchDevices()
            async let s = appState.api.fetchSystemStatus()
            devices = try await d
            systemStatus = try await s
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
