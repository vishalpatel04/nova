import Foundation

@MainActor
final class MacMissionStreamClient: ObservableObject {
    @Published var events: [MacTimelineEvent] = []
    @Published var streamingStatus: String = "disconnected"
    @Published var badge: MissionStreamBadge = .disconnected
    @Published var lastSequence: Int = 0

    private var task: URLSessionWebSocketTask?
    private var session: URLSession?
    private var missionId: String = ""
    private var reconnectAttempt = 0
    private let api = NOVAAPIClient.shared
    private var useRestFallbackOnly = false

    func connect(missionId: String) async {
        self.missionId = missionId
        reconnectAttempt = 0
        useRestFallbackOnly = false
        await openStream()
    }

    func disconnect() {
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        session = nil
        streamingStatus = "disconnected"
        badge = .disconnected
    }

    private func openStream() async {
        disconnect()
        if useRestFallbackOnly {
            await restRefresh()
            return
        }
        badge = reconnectAttempt > 0 ? .reconnecting : .disconnected
        do {
            let ticket = try await api.issueWebSocketTicket(scope: "mission_events", missionId: missionId)
            let wsBase = api.baseURL
                .replacingOccurrences(of: "https://", with: "wss://")
                .replacingOccurrences(of: "http://", with: "ws://")
            var components = URLComponents(string: "\(wsBase)/api/v1/ws/missions/\(missionId)/events")!
            components.queryItems = [
                URLQueryItem(name: "ticket", value: ticket.ticket),
                URLQueryItem(name: "after_sequence", value: String(lastSequence)),
            ]
            guard let url = components.url else { return }

            let history = try await api.fetchTimeline(missionId: missionId, afterSequence: lastSequence)
            events = MacTimelineMerger.merge(existing: events, incoming: history.events)
            lastSequence = MacTimelineMerger.maxSequence(in: events, current: lastSequence)
            streamingStatus = history.streaming
            badge = MissionStreamBadge(streamingStatus: history.streaming)

            session = URLSession(configuration: .default)
            task = session?.webSocketTask(with: url)
            task?.resume()
            reconnectAttempt = 0
            receiveLoop()
        } catch {
            streamingStatus = "offline"
            badge = .offline
            await scheduleReconnect()
        }
    }

    private func receiveLoop() {
        task?.receive { [weak self] result in
            guard let self else { return }
            Task { @MainActor in
                switch result {
                case .success(let message):
                    if case .string(let text) = message,
                       let data = text.data(using: .utf8),
                       let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                        if let type = json["type"] as? String, type == "streaming_status" {
                            let status = json["status"] as? String ?? "degraded"
                            self.streamingStatus = status
                            self.badge = MissionStreamBadge(streamingStatus: status)
                        } else if let seq = json["sequence_number"] as? Int {
                            let event = MacTimelineEvent(
                                id: json["event_id"] as? String ?? UUID().uuidString,
                                eventType: json["event_type"] as? String ?? "event",
                                message: json["message"] as? String ?? "",
                                sequenceNumber: seq
                            )
                            self.events = MacTimelineMerger.merge(existing: self.events, incoming: [event])
                            self.lastSequence = MacTimelineMerger.maxSequence(in: self.events, current: self.lastSequence)
                        }
                    }
                    self.receiveLoop()
                case .failure:
                    self.streamingStatus = "reconnecting"
                    self.badge = .reconnecting
                    await self.scheduleReconnect()
                }
            }
        }
    }

    private func scheduleReconnect() async {
        reconnectAttempt += 1
        if reconnectAttempt >= 5 {
            useRestFallbackOnly = true
            badge = .degraded
            await restRefresh()
            return
        }
        let delay = min(pow(2.0, Double(reconnectAttempt)), 30.0)
        try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
        guard !missionId.isEmpty else { return }
        await openStream()
    }

    private func restRefresh() async {
        guard !missionId.isEmpty else { return }
        do {
            let history = try await api.fetchTimeline(missionId: missionId, afterSequence: lastSequence)
            events = MacTimelineMerger.merge(existing: events, incoming: history.events)
            lastSequence = MacTimelineMerger.maxSequence(in: events, current: lastSequence)
            streamingStatus = history.streaming
            badge = .degraded
        } catch {
            badge = .offline
        }
    }
}
