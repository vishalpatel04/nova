import SwiftUI

struct AgentsView: View {
    @EnvironmentObject private var appState: AppState
    @State private var agents: [Agent] = []
    @State private var errorMessage: String?

    var body: some View {
        Group {
            if agents.isEmpty {
                ContentUnavailableView(
                    "Agents",
                    systemImage: "person.3",
                    description: Text(errorMessage ?? "Loading commanders…")
                )
            } else {
                List(agents) { agent in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(agent.displayName).font(.headline)
                        Text(agent.role.replacingOccurrences(of: "_", with: " "))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .navigationTitle("Agents")
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        guard appState.isPaired else {
            errorMessage = "Pair device to load agents."
            return
        }
        do {
            agents = try await appState.api.fetchAgents()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
