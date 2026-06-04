import Foundation

@MainActor
final class MissionStreamClient: NSObject, ObservableObject {
    @Published var events: [TimelineEvent] = []
    @Published var streamingStatus: String = "disconnected"
    @Published var lastSequence: Int = 0

    private var task: URLSessionWebSocketTask?
    private var session: URLSession?
    private var missionId: String = ""
    private let api = NOVAAPIClient.shared

    func connect(missionId: String) async {
        self.missionId = missionId
        disconnect()
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
            events = history.events
            lastSequence = history.events.compactMap(\.sequenceNumber).max() ?? lastSequence
            streamingStatus = history.streaming

            let config = URLSessionConfiguration.default
            session = URLSession(configuration: config, delegate: nil, delegateQueue: nil)
            task = session?.webSocketTask(with: url)
            task?.resume()
            streamingStatus = history.streaming == "live" ? "live" : "degraded"
            receiveLoop()
        } catch {
            streamingStatus = "error"
            api.lastError = error.localizedDescription
        }
    }

    func disconnect() {
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        session = nil
        streamingStatus = "disconnected"
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
                            self.streamingStatus = json["status"] as? String ?? "degraded"
                        } else if let seq = json["sequence_number"] as? Int {
                            let event = TimelineEvent(
                                id: json["event_id"] as? String ?? UUID().uuidString,
                                eventType: json["event_type"] as? String ?? "event",
                                message: json["message"] as? String ?? "",
                                sequenceNumber: seq,
                                createdAt: nil
                            )
                            self.events.append(event)
                            self.lastSequence = max(self.lastSequence, seq)
                        }
                    }
                    self.receiveLoop()
                case .failure:
                    self.streamingStatus = "reconnecting"
                    let mid = self.missionId
                    try? await Task.sleep(nanoseconds: 2_000_000_000)
                    if !mid.isEmpty { await self.connect(missionId: mid) }
                }
            }
        }
    }
}
