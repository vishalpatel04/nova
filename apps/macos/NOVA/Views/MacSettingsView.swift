import SwiftUI

struct MacSettingsView: View {
    @EnvironmentObject var appState: MacAppState

    var body: some View {
        TabView {
            Form {
                Section("Connection") {
                    TextField("API URL", text: $appState.apiBaseURL)
                }
                Section("Worker") {
                    Picker("Health", selection: $appState.workerHealth) {
                        Text("Unknown").tag(MacAppState.WorkerHealth.unknown)
                        Text("Healthy").tag(MacAppState.WorkerHealth.healthy)
                        Text("Degraded").tag(MacAppState.WorkerHealth.degraded)
                        Text("Offline").tag(MacAppState.WorkerHealth.offline)
                    }
                }
                Section("Launch") {
                    Toggle("Launch at Login", isOn: .constant(false))
                        .disabled(true)
                    Text("Launch-at-login ready — enable in Slice 2")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .tabItem { Label("General", systemImage: "gear") }

            MacMissionRoomView()
                .tabItem { Label("Missions", systemImage: "list.bullet") }

            MacAgentsView()
                .tabItem { Label("Agents", systemImage: "person.3") }

            MacDevicesView()
                .tabItem { Label("Devices", systemImage: "desktopcomputer") }
        }
        .frame(width: 500, height: 400)
    }
}

#Preview {
    MacSettingsView()
        .environmentObject(MacAppState())
}
