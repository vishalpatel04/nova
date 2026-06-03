import SwiftUI

struct MacMissionRoomView: View {
    private let missions = [
        ("System Status Check", "completed"),
        ("Code Review", "running"),
    ]

    var body: some View {
        List(missions, id: \.0) { mission in
            HStack {
                Text(mission.0)
                Spacer()
                Text(mission.1.capitalized)
                    .font(.caption)
                    .foregroundStyle(mission.1 == "completed" ? .green : MacDesignTokens.novaBlue)
            }
        }
        .navigationTitle("Mission Room")
    }
}

#Preview {
    MacMissionRoomView()
}
