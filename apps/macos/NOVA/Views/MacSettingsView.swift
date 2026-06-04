import SwiftUI

struct MacSettingsView: View {
    @EnvironmentObject private var appState: MacAppState
    @StateObject private var poller = MacPairingPoller()
    @State private var pairingCode = ""
    @State private var deviceName = "My Mac"
    @State private var deviceId = "mac-genie-\(UUID().uuidString.prefix(8))"
    @State private var pairingId = ""
    @State private var launchAtLogin = LaunchAtLoginHelper.isEnabled
    @State private var launchStatus = LaunchAtLoginHelper.statusLabel

    var body: some View {
        TabView {
            Form {
                TextField("API URL", text: $appState.apiBaseURL)
                Button("Save URL") { appState.updateBaseURL(appState.apiBaseURL) }
                LabeledContent("Paired", value: appState.isPaired ? "Yes" : "No")

                Section("Pair device") {
                    TextField("Pairing code", text: $pairingCode)
                    TextField("Device name", text: $deviceName)
                    Button("Claim code") { Task { await claim() } }
                    pairingStatusView
                }

                Section("Global hotkey") {
                    Toggle("Enable summon hotkey", isOn: $appState.hotkey.isEnabled)
                        .onChange(of: appState.hotkey.isEnabled) { _, _ in appState.hotkey.applyRegistration() }
                    Text("Default: ⌥ Space — opens NOVA and starts tap-to-talk")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let err = appState.hotkey.registrationError {
                        Text(err).font(.caption).foregroundStyle(.orange)
                    }
                }

                Section("Launch at login") {
                    Toggle("Open NOVA at login", isOn: $launchAtLogin)
                        .onChange(of: launchAtLogin) { _, value in
                            do {
                                try LaunchAtLoginHelper.setEnabled(value)
                                launchStatus = LaunchAtLoginHelper.statusLabel
                            } catch {
                                appState.globalError = error.localizedDescription
                                launchAtLogin = LaunchAtLoginHelper.isEnabled
                            }
                        }
                    Text(launchStatus).font(.caption).foregroundStyle(.secondary)
                }

                Picker("Voice mode", selection: $appState.voiceMode) {
                    ForEach(MacAppState.VoiceMode.allCases, id: \.self) { mode in
                        Text(mode.displayName).tag(mode)
                    }
                }
                Text("Wake word: pluggable provider reserved — no daemon in this slice.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding()
            .tabItem { Label("General", systemImage: "gear") }

            MacDevicesView().tabItem { Label("Devices", systemImage: "desktopcomputer") }
            MacAgentsView().tabItem { Label("Agents", systemImage: "person.3") }
            MacMissionRoomView().tabItem { Label("Missions", systemImage: "list.bullet") }
        }
        .frame(width: 520, height: 440)
        .onAppear {
            appState.hotkey.applyRegistration()
            launchAtLogin = LaunchAtLoginHelper.isEnabled
            launchStatus = LaunchAtLoginHelper.statusLabel
        }
        .onDisappear { poller.stop() }
    }

    @ViewBuilder
    private var pairingStatusView: some View {
        switch poller.stateMachine.phase {
        case .waitingApproval, .polling, .retrievingToken:
            ProgressView(poller.statusMessage)
        case .success:
            Label("Paired", systemImage: "checkmark.circle")
        case .expired:
            Label("Expired", systemImage: "clock")
        case .rejected:
            Label("Rejected", systemImage: "xmark.circle")
        case .failed(let msg):
            Text(msg).foregroundStyle(.red)
        case .idle:
            EmptyView()
        }
    }

    private func claim() async {
        do {
            let response = try await appState.api.claimPairing(
                code: pairingCode.uppercased(),
                deviceId: deviceId,
                name: deviceName,
                deviceType: "macos_genie"
            )
            pairingId = response.pairingId
            if let token = response.token, !token.isEmpty {
                try appState.api.saveToken(token)
                appState.refreshPairing()
            } else if response.status == "pending" {
                poller.start(pairingId: pairingId, deviceId: deviceId) { _ in
                    appState.refreshPairing()
                }
            }
        } catch {
            appState.globalError = error.localizedDescription
        }
    }
}
