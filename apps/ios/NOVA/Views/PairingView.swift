import SwiftUI

struct PairingView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var poller = PairingPoller()
    @State private var code = ""
    @State private var deviceName = "My iPhone"
    @State private var deviceId = "iphone-\(UUID().uuidString.prefix(8))"
    @State private var pairingId = ""

    var body: some View {
        Form {
            Section("API") {
                TextField("Base URL", text: $appState.apiBaseURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button("Save URL") { appState.updateBaseURL(appState.apiBaseURL) }
            }
            Section("Pair with NOVA") {
                TextField("6-digit code", text: $code)
                    .keyboardType(.asciiCapable)
                TextField("Device name", text: $deviceName)
                TextField("Device ID", text: $deviceId)
                    .textInputAutocapitalization(.never)
                Button("Claim pairing code") { Task { await claim() } }
                    .disabled(code.count < 4 || appState.isLoading)
            }
            pairingStatusSection
            if let err = appState.globalError {
                Section { Text(err).foregroundStyle(.red) }
            }
        }
        .navigationTitle("Pair Device")
        .onDisappear { poller.stop() }
    }

    @ViewBuilder
    private var pairingStatusSection: some View {
        switch poller.stateMachine.phase {
        case .waitingApproval, .polling, .retrievingToken:
            Section("Waiting for approval") {
                ProgressView()
                Text(poller.statusMessage)
                    .foregroundStyle(.secondary)
            }
        case .success:
            Section {
                Label("Paired successfully", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
            }
        case .expired:
            Section {
                Label("Pairing code expired", systemImage: "clock.badge.xmark")
                    .foregroundStyle(.orange)
            }
        case .rejected:
            Section {
                Label("Pairing rejected", systemImage: "xmark.circle")
                    .foregroundStyle(.red)
            }
        case .failed(let message):
            Section {
                Text(message).foregroundStyle(.red)
            }
        case .idle:
            EmptyView()
        }
    }

    private func claim() async {
        appState.isLoading = true
        appState.globalError = nil
        defer { appState.isLoading = false }
        do {
            let response = try await appState.api.claimPairing(
                code: code.uppercased(),
                deviceId: deviceId,
                name: deviceName,
                deviceType: "iphone_client"
            )
            pairingId = response.pairingId
            if let token = response.token, !token.isEmpty {
                try appState.api.saveToken(token)
                appState.refreshPairingState()
                appState.completeOnboarding()
            } else if response.status == "pending" {
                poller.start(pairingId: pairingId, deviceId: deviceId) { _ in
                    appState.refreshPairingState()
                    appState.completeOnboarding()
                }
            }
        } catch {
            appState.globalError = error.localizedDescription
        }
    }
}
