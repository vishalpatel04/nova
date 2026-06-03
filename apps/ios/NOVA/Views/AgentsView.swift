import SwiftUI

struct AgentsView: View {
    @State private var agents = MockData.agents

    var body: some View {
        List(agents) { agent in
            HStack(spacing: 12) {
                Circle()
                    .fill(DesignTokens.agentColor(for: agent.colourToken))
                    .frame(width: 40, height: 40)
                    .overlay(
                        Text(String(agent.displayName.prefix(1)))
                            .font(.headline.bold())
                            .foregroundStyle(.white)
                    )
                VStack(alignment: .leading) {
                    Text(agent.displayName)
                        .font(.headline)
                    Text(agent.description ?? agent.role)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle("Agents")
    }
}

#Preview {
    NavigationStack { AgentsView() }
}
