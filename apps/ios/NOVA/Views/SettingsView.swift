import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        Form {
            Section("Connection") {
                TextField("API URL", text: $appState.apiBaseURL)
                    .textContentType(.URL)
                    .autocapitalization(.none)
            }
            Section("Permissions") {
                HStack {
                    Text("Microphone")
                    Spacer()
                    Text(appState.microphonePermission == .authorized ? "Granted" : "Not granted")
                        .foregroundStyle(.secondary)
                }
            }
            Section("About") {
                HStack {
                    Text("Version")
                    Spacer()
                    Text("0.1.0")
                        .foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle("Settings")
    }
}

#Preview {
    NavigationStack { SettingsView().environmentObject(AppState()) }
}
