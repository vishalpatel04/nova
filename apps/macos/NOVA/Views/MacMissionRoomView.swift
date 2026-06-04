import SwiftUI

struct MacMissionRoomView: View {
    @EnvironmentObject private var appState: MacAppState
    @State private var missions: [MacMissionDetail] = []
    @State private var selectedId: String?
    @State private var events: [MacTimelineEvent] = []
    @State private var streaming = "disconnected"

    var body: some View {
        HSplitView {
            List(missions, selection: $selectedId) { m in
                Text(m.title).tag(m.id as String?)
            }
            .frame(minWidth: 160)
            List(events) { e in
                VStack(alignment: .leading) {
                    Text(e.message)
                    Text(e.eventType).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .toolbar {
            Button("New mission") { Task { await create() } }
            Text(streaming).font(.caption)
        }
        .task(id: selectedId) {
            guard let selectedId else { return }
            await loadTimeline(missionId: selectedId)
        }
    }

    private func create() async {
        guard let mission = try? await appState.api.createMission(type: "system_status", title: "macOS mission") else {
            return
        }
        missions.insert(mission, at: 0)
        selectedId = mission.id
    }

    private func loadTimeline(missionId: String) async {
        guard let response = try? await appState.api.fetchTimeline(missionId: missionId) else { return }
        events = response.events
        streaming = response.streaming
    }
}
