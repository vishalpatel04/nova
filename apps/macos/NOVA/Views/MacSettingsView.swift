import SwiftUI

struct MacSettingsView: View {
    @EnvironmentObject private var appState: MacAppState
    @StateObject private var poller = MacPairingPoller()
    @State private var pairingCode = ""
    @State private var deviceName = "My Mac"
    @State private var deviceId = NovaDeviceIdentity.resolvedDeviceId()
        ?? "mac-genie-\(UUID().uuidString.prefix(8))"
    @State private var pairingId = ""
    @State private var launchAtLogin = LaunchAtLoginHelper.isEnabled
    @State private var launchStatus = LaunchAtLoginHelper.statusLabel
    @State private var providerKeyDraft = ""
    @State private var selectedProvider = NovaProviderSettings.defaultProvider

    var body: some View {
        TabView {
            Form {
                TextField("API URL", text: $appState.apiBaseURL)
                Button("Save URL") { appState.updateBaseURL(appState.apiBaseURL) }
                LabeledContent("Paired", value: appState.isPaired ? "Yes" : "No")
                if let deviceId = appState.pairedDeviceId {
                    LabeledContent("Device ID", value: deviceId)
                }

                Section("Providers") {
                    Picker("Default provider", selection: $selectedProvider) {
                        ForEach(NovaProviderName.allCases) { provider in
                            Text(provider.displayName).tag(provider)
                        }
                    }
                    .onChange(of: selectedProvider) { _, value in
                        NovaProviderSettings.defaultProvider = value
                    }
                    TextField("Model name", text: Binding(
                        get: { NovaProviderSettings.modelName },
                        set: { NovaProviderSettings.modelName = $0 }
                    ))
                    TextField("Local endpoint", text: Binding(
                        get: { NovaProviderSettings.localEndpointURL },
                        set: { NovaProviderSettings.localEndpointURL = $0 }
                    ))
                    Toggle("Prefer free/local for low-level tasks", isOn: Binding(
                        get: { NovaProviderSettings.preferFreeLocal },
                        set: { NovaProviderSettings.preferFreeLocal = $0 }
                    ))
                    SecureField("API key (stored in Keychain)", text: $providerKeyDraft)
                    HStack {
                        Button("Save key") {
                            guard !providerKeyDraft.isEmpty else { return }
                            try? NovaProviderSettings.saveAPIKey(providerKeyDraft, provider: selectedProvider)
                            providerKeyDraft = ""
                        }
                        Button("Clear key") {
                            NovaProviderSettings.deleteAPIKey(provider: selectedProvider)
                        }
                    }
                    Text("Key status: \(NovaProviderSettings.maskedKeyStatus(provider: selectedProvider))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("Provider keys live only in macOS Keychain (service com.nova.macos.providers). Never logged.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Pair device") {
                    TextField("Pairing code", text: $pairingCode)
                    TextField("Device name", text: $deviceName)
                    Button("Claim code") { Task { await claim() } }
                    pairingStatusView
                }

                Section("Global hotkey") {
                    Toggle("Enable summon hotkey", isOn: $appState.hotkey.isEnabled)
                        .onChange(of: appState.hotkey.isEnabled) { _, _ in appState.hotkey.applyRegistration() }
                    Text("Default: \(GlobalHotkeyManager.defaultShortcutLabel) — opens NOVA and starts tap-to-talk")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let err = appState.hotkey.registrationError {
                        Text(err).font(.caption).foregroundStyle(.orange)
                        Text("The menu-bar Open NOVA and Pair Device actions still work.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
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

                Section("Voice") {
                    Toggle("Enable microphone input", isOn: Binding(
                        get: { appState.voiceInputEnabled },
                        set: { appState.voiceInputEnabled = $0; appState.saveVoicePreferences() }
                    ))
                    Toggle("Enable “Hey Nova” while popup is open", isOn: Binding(
                        get: { appState.voiceWakeWordEnabled },
                        set: { appState.voiceWakeWordEnabled = $0; appState.saveVoicePreferences() }
                    ))
                    Toggle("Start listening when popup opens", isOn: Binding(
                        get: { appState.voiceStartListeningOnOpen },
                        set: { appState.voiceStartListeningOnOpen = $0; appState.saveVoicePreferences() }
                    ))
                    Toggle("Auto-send after voice transcription", isOn: Binding(
                        get: { appState.voiceAutoSendAfterTranscription },
                        set: { appState.voiceAutoSendAfterTranscription = $0; appState.saveVoicePreferences() }
                    ))
                    Toggle("Sound cue on wake", isOn: Binding(
                        get: { appState.voiceWakeSoundEnabled },
                        set: { appState.voiceWakeSoundEnabled = $0; appState.saveVoicePreferences() }
                    ))
                    Toggle("Stop listening when popup closes", isOn: Binding(
                        get: { appState.voiceStopListeningOnClose },
                        set: { appState.voiceStopListeningOnClose = $0; appState.saveVoicePreferences() }
                    ))
                    Toggle("Voice Off kill switch", isOn: Binding(
                        get: { appState.voiceKillSwitch },
                        set: { appState.voiceKillSwitch = $0; appState.saveVoicePreferences() }
                    ))
                    Text("Background listening when NOVA is closed is coming later and requires a separate privacy review.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("If on-device speech recognition is unavailable, wake-word mode stays disabled.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding()
            .tabItem { Label("General", systemImage: "gear") }

            MacDevicesView().tabItem { Label("Devices", systemImage: "desktopcomputer") }
            NavigationStack { SessionListView() }
                .tabItem { Label("Sessions", systemImage: "clock.arrow.circlepath") }
            NavigationStack { CompanionInboxView() }
                .tabItem { Label("Companion", systemImage: "tray.full") }
            NavigationStack { BackgroundTasksView() }
                .tabItem { Label("Background", systemImage: "clock.arrow.circlepath") }
            NavigationStack { AgentOrchestrationView() }
                .tabItem { Label("Orchestration", systemImage: "person.3.sequence") }
            NavigationStack { NotificationsView() }
                .tabItem { Label("Notifications", systemImage: "bell") }
            NavigationStack { ApprovalQueueView() }
                .tabItem { Label("Approvals", systemImage: "checkmark.shield") }
            NavigationStack { MemoryCenterView() }
                .tabItem { Label("Memory", systemImage: "brain.head.profile") }
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
            let resolvedDeviceId = response.deviceId.isEmpty ? deviceId : response.deviceId
            deviceId = resolvedDeviceId
            if let token = response.token, !token.isEmpty {
                try appState.api.saveToken(token, deviceId: resolvedDeviceId)
                appState.refreshPairing()
            } else if response.status == "pending" {
                poller.start(pairingId: pairingId, deviceId: resolvedDeviceId) { _ in
                    appState.refreshPairing()
                }
            }
        } catch {
            appState.globalError = error.localizedDescription
        }
    }
}
