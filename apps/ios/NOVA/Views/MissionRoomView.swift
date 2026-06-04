import SwiftUI

struct MissionRoomView: View {
    @EnvironmentObject private var appState: AppState
    @State private var missions: [MissionDetail] = []
    @State private var loadError: String?

    var body: some View {
        Group {
            if missions.isEmpty {
                ContentUnavailableView(
                    "Mission Room",
                    systemImage: "list.bullet.rectangle",
                    description: Text(loadError ?? "Start a system status mission to open the live timeline.")
                )
            } else {
                List(missions) { mission in
                    NavigationLink(value: mission.id) {
                        MissionRow(mission: mission)
                    }
                }
            }
        }
        .navigationTitle("Mission Room")
        .navigationDestination(for: String.self) { missionId in
            MissionDetailView(missionId: missionId)
        }
        .toolbar {
            Button("New status mission") { Task { await createMission() } }
        }
    }

    private func createMission() async {
        guard appState.isPaired else {
            loadError = "Pair this device first."
            return
        }
        do {
            let mission = try await appState.api.createMission(
                type: "system_status",
                title: "iOS Mission Room",
                idempotencyKey: "ios-room-\(UUID().uuidString)"
            )
            missions.insert(mission, at: 0)
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }
}

struct MissionRow: View {
    let mission: MissionDetail

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(mission.title).font(.headline)
            HStack {
                Text(mission.missionType).font(.caption).foregroundStyle(.secondary)
                Spacer()
                StatusBadge(status: mission.status)
            }
        }
        .padding(.vertical, 4)
    }
}

struct MissionDetailView: View {
    let missionId: String
    @StateObject private var stream = MissionStreamClient()

    var body: some View {
        List {
            Section("Streaming") {
                Label(stream.streamingStatus, systemImage: "antenna.radiowaves.left.and.right")
            }
            Section("Timeline") {
                if stream.events.isEmpty {
                    Text("Waiting for events…").foregroundStyle(.secondary)
                } else {
                    ForEach(stream.events) { event in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(event.message).font(.body)
                            Text(event.eventType).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .navigationTitle("Mission")
        .task { await stream.connect(missionId: missionId) }
        .onDisappear { stream.disconnect() }
    }
}

struct StatusBadge: View {
    let status: String

    var color: Color {
        switch status {
        case "completed": return .green
        case "running": return DesignTokens.novaBlue
        case "failed": return .red
        case "queued_waiting_for_worker": return .orange
        default: return .orange
        }
    }

    var label: String {
        status == "queued_waiting_for_worker" ? "Queued — worker offline" : status.capitalized
    }

    var body: some View {
        Text(label)
            .font(.caption2.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}
