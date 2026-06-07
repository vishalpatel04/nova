import Foundation

struct ChatStreamEvent: Equatable {
    enum Kind: Equatable {
        case session(sessionId: String, streamId: String?)
        case token(String)
        case done(
            response: String,
            intent: String,
            blocked: Bool,
            sessionId: String?,
            activeProject: String?,
            pendingToolIntent: String?,
            runtimeMode: String?,
            selectedProvider: String?,
            selectedModel: String?,
            fallbackReason: String?,
            localAvailable: Bool?
        )
        case cancelled
        case error(String)
    }

    let kind: Kind
}

@MainActor
final class ChatStreamClient: ObservableObject {
    @Published private(set) var isStreaming = false
    @Published private(set) var streamId: String?

    private var streamTask: Task<Void, Never>?
    private var cancelURLSession: URLSession?

    func streamChat(
        api: NOVAAPIClient,
        message: String,
        sessionId: String?,
        onEvent: @escaping (ChatStreamEvent) -> Void
    ) {
        cancel()
        isStreaming = true
        streamTask = Task {
            do {
                try await runStream(api: api, message: message, sessionId: sessionId, onEvent: onEvent)
            } catch {
                if !Task.isCancelled {
                    onEvent(ChatStreamEvent(kind: .error(error.localizedDescription)))
                }
            }
            isStreaming = false
        }
    }

    func cancel() {
        streamTask?.cancel()
        streamTask = nil
        if let streamId {
            Task { try? await NOVAAPIClient.shared.cancelChatStream(streamId: streamId) }
        }
        isStreaming = false
    }

    private func runStream(
        api: NOVAAPIClient,
        message: String,
        sessionId: String?,
        onEvent: @escaping (ChatStreamEvent) -> Void
    ) async throws {
        let result = try await api.openChatStream(message: message, sessionId: sessionId)
        streamId = result.streamId
        defer {
            streamId = nil
            cancelURLSession = nil
        }

        var currentEvent = ""
        for try await line in result.lines {
            if Task.isCancelled { break }
            if line.hasPrefix("event: ") {
                currentEvent = String(line.dropFirst(7))
            } else if line.hasPrefix("data: "), !currentEvent.isEmpty {
                let payload = String(line.dropFirst(6))
                emit(event: currentEvent, payload: payload, onEvent: onEvent)
                currentEvent = ""
            }
        }
    }

    private func emit(event: String, payload: String, onEvent: @escaping (ChatStreamEvent) -> Void) {
        guard let data = payload.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        switch event {
        case "session":
            let sessionId = json["session_id"] as? String ?? ""
            let streamId = json["stream_id"] as? String
            self.streamId = streamId
            onEvent(ChatStreamEvent(kind: .session(sessionId: sessionId, streamId: streamId)))
        case "token":
            if let delta = json["delta"] as? String {
                onEvent(ChatStreamEvent(kind: .token(delta)))
            }
        case "done":
            onEvent(
                ChatStreamEvent(
                    kind: .done(
                        response: json["response"] as? String ?? "",
                        intent: json["intent"] as? String ?? "general",
                        blocked: json["blocked"] as? Bool ?? false,
                        sessionId: json["session_id"] as? String,
                        activeProject: json["active_project"] as? String,
                        pendingToolIntent: json["pending_tool_intent"] as? String,
                        runtimeMode: json["runtime_mode"] as? String,
                        selectedProvider: json["selected_provider"] as? String,
                        selectedModel: json["selected_model"] as? String,
                        fallbackReason: json["fallback_reason"] as? String,
                        localAvailable: json["local_available"] as? Bool
                    )
                )
            )
        case "cancelled":
            onEvent(ChatStreamEvent(kind: .cancelled))
        case "error":
            onEvent(ChatStreamEvent(kind: .error(json["message"] as? String ?? "Stream error")))
        default:
            break
        }
    }
}
