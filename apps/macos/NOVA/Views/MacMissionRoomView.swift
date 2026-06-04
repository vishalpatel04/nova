import SwiftUI

struct MacMissionRoomView: View {
    @EnvironmentObject private var appState: MacAppState
    @StateObject private var stream = MacMissionStreamClient()
    @State private var missions: [MacMissionDetail] = []
    @State private var selectedId: String?

    var body: some View {
        HSplitView {
            List(missions, selection: $selectedId) { m in
                Text(m.title).tag(m.id as String?)
            }
            .frame(minWidth: 160)
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    StreamStatusBadge(badge: stream.badge)
                    Spacer()
                    if stream.badge == .degraded || stream.badge == .offline {
                        Button("Refresh") { Task { await stream.connect(missionId: selectedId ?? "") } }
                    }
                }
                .padding(8)
                List(stream.events) { e in
                    VStack(alignment: .leading) {
                        Text(e.message)
                        Text(e.eventType).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .toolbar {
            Button("New mission") { Task { await create() } }
        }
        .task(id: selectedId) {
            guard let selectedId else { stream.disconnect(); return }
            await stream.connect(missionId: selectedId)
        }
    }

    private func create() async {
        guard let mission = try? await appState.api.createMission(type: "system_status", title: "macOS mission") else {
            return
        }
        missions.insert(mission, at: 0)
        selectedId = mission.id
    }
}

struct StreamStatusBadge: View {
    let badge: MissionStreamBadge

    var body: some View {
        Label(badge.label, systemImage: badge.icon)
            .font(.caption)
            .foregroundStyle(badge.color)
    }
}

private extension MissionStreamBadge {
    var label: String {
        switch self {
        case .live: return "Live"
        case .reconnecting: return "Reconnecting"
        case .degraded: return "Degraded"
        case .offline: return "Offline"
        case .disconnected: return "Disconnected"
        }
    }

    var icon: String {
        switch self {
        case .live: return "dot.radiowaves.left.and.right"
        case .reconnecting: return "arrow.triangle.2.circlepath"
        case .degraded: return "exclamationmark.triangle"
        case .offline: return "wifi.slash"
        case .disconnected: return "circle"
        }
    }

    var color: Color {
        switch self {
        case .live: return .green
        case .reconnecting: return .orange
        case .degraded: return .yellow
        case .offline, .disconnected: return .secondary
        }
    }
}
