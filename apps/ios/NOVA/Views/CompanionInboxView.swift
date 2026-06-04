import SwiftUI

struct CompanionInboxView: View {
    @EnvironmentObject private var appState: AppState
    @State private var items: [CompanionInboxItem] = []
    @State private var loadError: String?
    @State private var sendText = ""

    var body: some View {
        VStack(spacing: 0) {
            List {
                if let loadError {
                    Text(loadError).font(.caption).foregroundStyle(.red)
                }
                if items.isEmpty {
                    Text("No companion prompts yet.")
                        .foregroundStyle(.secondary)
                }
                ForEach(items) { item in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(item.message)
                        Text(item.status)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }
            }
            HStack {
                TextField("Prompt", text: $sendText)
                    .textFieldStyle(.roundedBorder)
                Button("Send to Mac") { Task { await sendPrompt() } }
                    .disabled(sendText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding()
        }
        .navigationTitle("Companion")
        .task { await refresh() }
        .refreshable { await refresh() }
    }

    private func refresh() async {
        guard appState.isPaired else { return }
        do {
            items = try await appState.api.fetchCompanionInbox(deviceId: appState.pairedDeviceId)
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func sendPrompt() async {
        let text = sendText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let target = appState.companionTargetDeviceId else {
            loadError = "No paired Mac target configured."
            return
        }
        do {
            _ = try await appState.api.sendCompanionPrompt(message: text, targetDeviceId: target)
            sendText = ""
            await refresh()
        } catch {
            loadError = error.localizedDescription
        }
    }
}
