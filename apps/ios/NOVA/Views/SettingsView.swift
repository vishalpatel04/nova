import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        Form {
            Section("Connection") {
                TextField("API URL", text: $appState.apiBaseURL)
                    .textInputAutocapitalization(.never)
                Button("Save") { appState.updateBaseURL(appState.apiBaseURL) }
                LabeledContent("Paired", value: appState.isPaired ? "Yes" : "No")
                NavigationLink("Pair device") { PairingView() }
                if appState.isPaired {
                    Button("Sign out", role: .destructive) {
                        appState.api.clearToken()
                        appState.refreshPairingState()
                    }
                }
            }
            Section("Permissions") {
                LabeledContent("Microphone", value: label(appState.microphonePermission))
                LabeledContent("Speech", value: label(appState.speechPermission))
                Button("Request permissions") {
                    Task {
                        await appState.requestMicrophonePermission()
                        await appState.requestSpeechPermission()
                    }
                }
            }
            Section("Shortcuts") {
                Text("Add “Start NOVA Listening” from the Shortcuts app to assign Action Button or Control Center.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Section("About") {
                LabeledContent("Version", value: "0.2.0")
            }
        }
        .navigationTitle("Settings")
    }

    private func label(_ mic: MicrophonePermission) -> String {
        mic == .authorized ? "Granted" : "Not granted"
    }

    private func label(_ speech: SpeechPermission) -> String {
        speech == .authorized ? "Granted" : "Not granted"
    }
}
