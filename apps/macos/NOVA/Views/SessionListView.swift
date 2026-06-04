import SwiftUI

struct SessionListView: View {
    @EnvironmentObject private var appState: MacAppState
    @State private var sessions: [MacChatSessionSummary] = []
    @State private var loadError: String?

    var body: some View {
        List {
            if let loadError {
                Text(loadError).font(.caption).foregroundStyle(.red)
            }
            ForEach(sessions) { session in
                Button {
                    Task { await appState.restoreSession(sessionId: session.id) }
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(session.title).font(.headline)
                        Text(session.updatedAt, style: .relative)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .buttonStyle(.plain)
            }
        }
        .navigationTitle("Sessions")
        .task { await loadSessions() }
        .refreshable { await loadSessions() }
    }

    private func loadSessions() async {
        guard appState.isPaired else { return }
        do {
            sessions = try await appState.api.fetchChatSessionSummaries()
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }
}