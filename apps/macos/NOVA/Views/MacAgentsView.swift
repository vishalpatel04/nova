import SwiftUI

struct MacAgentsView: View {
    @EnvironmentObject private var appState: MacAppState
    @State private var agents: [MacAgent] = []

    var body: some View {
        List(agents) { agent in
            VStack(alignment: .leading) {
                Text(agent.displayName).font(.headline)
                Text(agent.role).font(.caption).foregroundStyle(.secondary)
            }
        }
        .task {
            guard appState.isPaired else { return }
            agents = (try? await appState.api.fetchAgents()) ?? []
        }
    }
}
