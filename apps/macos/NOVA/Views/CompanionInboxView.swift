import SwiftUI

struct CompanionInboxView: View {
    @EnvironmentObject private var appState: MacAppState
    @State private var items: [MacCompanionInboxItem] = []
    @State private var loadError: String?
    @State private var sendText = ""
    @State private var targetDeviceId = ""

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
                        HStack {
                            Text(item.status).font(.caption).foregroundStyle(.secondary)
                            if item.status != "read" {
                                Button("Mark read") {
                                    Task { await markRead(item.id) }
                                }
                                .font(.caption)
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
            HStack {
                TextField("Target device id", text: $targetDeviceId)
                    .textFieldStyle(.roundedBorder)
                TextField("Prompt", text: $sendText)
                    .textFieldStyle(.roundedBorder)
                Button("Send") { Task { await sendPrompt() } }
                    .disabled(sendText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(8)
        }
        .navigationTitle("Companion Inbox")
        .task {
            targetDeviceId = appState.pairedDeviceId ?? ""
            await refresh()
        }
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

    private func markRead(_ id: String) async {
        do {
            _ = try await appState.api.markCompanionInboxRead(itemId: id)
            await refresh()
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func sendPrompt() async {
        let text = sendText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !targetDeviceId.isEmpty else { return }
        do {
            _ = try await appState.api.sendCompanionPrompt(message: text, targetDeviceId: targetDeviceId)
            sendText = ""
            await refresh()
        } catch {
            loadError = error.localizedDescription
        }
    }
}
