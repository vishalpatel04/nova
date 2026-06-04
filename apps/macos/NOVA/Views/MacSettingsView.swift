import SwiftUI

struct MacSettingsView: View {
    @EnvironmentObject private var appState: MacAppState
    @State private var pairingCode = ""
    @State private var pastedToken = ""

    var body: some View {
        TabView {
            Form {
                TextField("API URL", text: $appState.apiBaseURL)
                Button("Save URL") { appState.updateBaseURL(appState.apiBaseURL) }
                LabeledContent("Paired", value: appState.isPaired ? "Yes" : "No")
                SecureField("Paste device token", text: $pastedToken)
                Button("Save token") {
                    try? appState.api.saveToken(pastedToken)
                    appState.refreshPairing()
                }
                Picker("Voice mode", selection: $appState.voiceMode) {
                    ForEach(MacAppState.VoiceMode.allCases, id: \.self) { mode in
                        Text(mode.displayName).tag(mode)
                    }
                }
                Text("Wake word: pluggable provider reserved for a future slice. No always-on daemon in 2B.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding()
            .tabItem { Label("General", systemImage: "gear") }

            MacDevicesView()
                .tabItem { Label("Devices", systemImage: "desktopcomputer") }

            MacAgentsView()
                .tabItem { Label("Agents", systemImage: "person.3") }

            MacMissionRoomView()
                .tabItem { Label("Missions", systemImage: "list.bullet") }
        }
        .frame(width: 480, height: 400)
    }
}
