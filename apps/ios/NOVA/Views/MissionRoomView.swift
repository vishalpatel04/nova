import SwiftUI

struct MissionRoomView: View {
    @State private var missions = MockData.missions

    var body: some View {
        List(missions) { mission in
            VStack(alignment: .leading, spacing: 4) {
                Text(mission.title)
                    .font(.headline)
                HStack {
                    Text(mission.missionType)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    StatusBadge(status: mission.status)
                }
            }
            .padding(.vertical, 4)
        }
        .navigationTitle("Mission Room")
    }
}

struct StatusBadge: View {
    let status: String

    var color: Color {
        switch status {
        case "completed": return .green
        case "running": return DesignTokens.novaBlue
        case "failed": return .red
        default: return .orange
        }
    }

    var body: some View {
        Text(status.capitalized)
            .font(.caption2.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}

#Preview {
    NavigationStack { MissionRoomView() }
}
