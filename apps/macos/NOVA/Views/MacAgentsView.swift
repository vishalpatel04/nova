import SwiftUI

struct MacAgentsView: View {
    private let agents = [
        ("NOVA", "nova_blue", "Chief of Staff"),
        ("MARS", "mars_red", "Engineering"),
        ("NEPTUNE", "neptune_teal", "Safety"),
    ]

    var body: some View {
        List(agents, id: \.0) { agent in
            HStack {
                Circle()
                    .fill(MacDesignTokens.agentColor(for: agent.1))
                    .frame(width: 32, height: 32)
                    .overlay(Text(String(agent.0.prefix(1))).font(.caption.bold()).foregroundStyle(.white))
                VStack(alignment: .leading) {
                    Text(agent.0).font(.headline)
                    Text(agent.2).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle("Agents")
    }
}

#Preview {
    MacAgentsView()
}
