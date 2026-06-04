import SwiftUI

struct CompactPairingView: View {
    @EnvironmentObject private var appState: MacAppState
    @StateObject private var poller = MacPairingPoller()
    @State private var pairingCode = ""
    @State private var deviceName = "My Mac"
    @State private var deviceId = NovaDeviceIdentity.resolvedDeviceId()
        ?? "mac-genie-\(UUID().uuidString.prefix(8))"
    @State private var pairingId = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                MacNovaOrbView(size: 36)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Pair Device")
                        .font(.headline)
                    Text("Connect this Mac before using NOVA chat.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }

            TextField("Pairing code", text: $pairingCode)
                .textFieldStyle(.roundedBorder)
            TextField("Device name", text: $deviceName)
                .textFieldStyle(.roundedBorder)

            HStack {
                Button("Pair Device") { Task { await claim() } }
                    .keyboardShortcut(.defaultAction)
                    .disabled(pairingCode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Button("Refresh") { appState.refreshPairing() }
                Spacer()
            }

            pairingStatusView
            Spacer()
        }
        .padding(18)
        .frame(width: 380, height: 300, alignment: .topLeading)
        .onAppear {
            NovaHotkeyTelemetry.emit("nova_pairing_view_opened")
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
            if !appState.isPaired {
                Text("Enter the code from the NOVA pairing page.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func claim() async {
        do {
            let response = try await appState.api.claimPairing(
                code: pairingCode.trimmingCharacters(in: .whitespacesAndNewlines).uppercased(),
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
