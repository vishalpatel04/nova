import SwiftUI

struct PairingView: View {
    @EnvironmentObject private var appState: AppState
    @State private var code = ""
    @State private var deviceName = "My iPhone"
    @State private var deviceId = "iphone-\(UUID().uuidString.prefix(8))"
    @State private var pastedToken = ""
    @State private var statusMessage = ""
    @State private var isWaitingApproval = false
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
            if isWaitingApproval {
                Section("Waiting for approval") {
                    Text(statusMessage)
                        .foregroundStyle(.secondary)
                    Text("After an operator approves this device, paste the issued token below.")
                        .font(.caption)
                    SecureField("Device token", text: $pastedToken)
                    Button("Save token") { savePastedToken() }
                }
            }
            Section("Development") {
                SecureField("Paste device token", text: $pastedToken)
                Button("Store token in Keychain") { savePastedToken() }
            }
            if let err = appState.globalError {
                Section { Text(err).foregroundStyle(.red) }
            }
        }
        .navigationTitle("Pair Device")
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
            statusMessage = response.message
            if let token = response.token, !token.isEmpty {
                try appState.api.saveToken(token)
                appState.refreshPairingState()
                appState.completeOnboarding()
            } else if response.status == "pending_approval" {
                isWaitingApproval = true
            }
        } catch {
            appState.globalError = error.localizedDescription
        }
    }

    private func savePastedToken() {
        guard !pastedToken.isEmpty else { return }
        do {
            try appState.api.saveToken(pastedToken)
            appState.refreshPairingState()
            appState.completeOnboarding()
            isWaitingApproval = false
        } catch {
            appState.globalError = error.localizedDescription
        }
    }
}
