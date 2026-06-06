import SwiftUI

struct MacDevicesView: View {
    @EnvironmentObject private var appState: MacAppState
    @State private var devices: [MacDevice] = []
    @State private var status: MacSystemStatus?

    var body: some View {
        List {
            if let status {
                Section("Fleet") {
                    LabeledContent("Online", value: "\(status.workersOnline)/\(status.workersTotal)")
                    if !status.hasEligibleOnlineWorker {
                        Text("Missions may queue until a worker reconnects.")
                            .foregroundStyle(.orange)
                    }
                }
            }
            Section("Devices") {
                ForEach(devices) { d in
                    VStack(alignment: .leading) {
                        Text(d.name).font(.headline)
                        Text("\(d.deviceType) · \(d.status)").font(.caption)
                    }
                }
            }
        }
        .task { await load() }
    }

    private func load() async {
        guard appState.isPaired else { return }
        devices = (try? await appState.api.fetchDevices()) ?? []
        status = try? await appState.api.fetchSystemStatus()
    }
}
