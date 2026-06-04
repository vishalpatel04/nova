import Foundation

@MainActor
final class NOVAAPIClient: ObservableObject {
    static let shared = NOVAAPIClient()

    @Published var baseURL: String
    @Published var lastError: String?

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .iso8601
        return d
    }()

    private let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        return e
    }()

    init(baseURL: String = UserDefaults.standard.string(forKey: "api_base_url") ?? "http://localhost:8000") {
        self.baseURL = baseURL
    }

    var deviceToken: String? {
        NovaAuthBootstrap.lookupToken().token
    }

    func saveToken(_ token: String, deviceId: String) throws {
        NovaDeviceIdentity.persistDeviceId(deviceId)
        try KeychainStore.save(
            token: token,
            account: deviceId,
            service: NovaDeviceIdentity.productionService
        )
        KeychainStore.delete(
            account: NovaDeviceIdentity.legacyAccount,
            service: NovaDeviceIdentity.legacyService
        )
    }

    func clearToken() {
        if let deviceId = NovaDeviceIdentity.resolvedDeviceId() {
            KeychainStore.delete(account: deviceId, service: NovaDeviceIdentity.productionService)
        }
        KeychainStore.delete(
            account: NovaDeviceIdentity.legacyAccount,
            service: NovaDeviceIdentity.legacyService
        )
    }

    private func request(
        path: String,
        method: String = "GET",
        body: Encodable? = nil,
        requiresAuth: Bool = true,
        extraHeaders: [String: String] = [:]
    ) async throws -> Data {
        guard let url = URL(string: "\(baseURL)\(path)") else { throw URLError(.badURL) }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        for (key, value) in extraHeaders {
            req.setValue(value, forHTTPHeaderField: key)
        }
        if requiresAuth {
            guard let token = deviceToken else { throw URLError(.userAuthenticationRequired) }
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body { req.httpBody = try encoder.encode(AnyEncodable(body)) }
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse, http.statusCode < 400 else {
            throw URLError(.badServerResponse)
        }
        return data
    }

    func fetchAgents() async throws -> [MacAgent] {
        let data = try await request(path: "/api/v1/agents")
        return try decoder.decode([MacAgent].self, from: data)
    }

    func fetchDevices() async throws -> [MacDevice] {
        let data = try await request(path: "/api/v1/devices")
        return try decoder.decode([MacDevice].self, from: data)
    }

    func fetchSystemStatus() async throws -> MacSystemStatus {
        let data = try await request(path: "/api/v1/system/status")
        return try decoder.decode(MacSystemStatus.self, from: data)
    }

    func createMission(type: String, title: String, idempotencyKey: String? = nil) async throws -> MacMissionDetail {
        struct Body: Encodable { let missionType: String; let title: String }
        var headers: [String: String] = [:]
        if let idempotencyKey { headers["Idempotency-Key"] = idempotencyKey }
        let data = try await request(
            path: "/api/v1/missions",
            method: "POST",
            body: Body(missionType: type, title: title),
            extraHeaders: headers
        )
        return try decoder.decode(MacMissionDetail.self, from: data)
    }

    func sendChat(message: String, sessionId: String? = nil) async throws -> MacChatResponse {
        struct Body: Encodable { let message: String; let sessionId: String? }
        let data = try await request(
            path: "/api/v1/chat",
            method: "POST",
            body: Body(message: message, sessionId: sessionId)
        )
        return try decoder.decode(MacChatResponse.self, from: data)
    }

    struct ChatStreamHandle {
        let streamId: String?
        let lines: AsyncThrowingStream<String, Error>
    }

    func openChatStream(message: String, sessionId: String? = nil) async throws -> ChatStreamHandle {
        guard let url = URL(string: "\(baseURL)/api/v1/chat/stream") else { throw URLError(.badURL) }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        guard let token = deviceToken else { throw URLError(.userAuthenticationRequired) }
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        struct Body: Encodable { let message: String; let sessionId: String? }
        req.httpBody = try encoder.encode(Body(message: message, sessionId: sessionId))

        let (bytes, response) = try await URLSession.shared.bytes(for: req)
        guard let http = response as? HTTPURLResponse, http.statusCode < 400 else {
            throw URLError(.badServerResponse)
        }
        let streamId = http.value(forHTTPHeaderField: "X-NOVA-Stream-Id")
        let lines = AsyncThrowingStream<String, Error> { continuation in
            Task {
                do {
                    for try await line in bytes.lines {
                        continuation.yield(line)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
        return ChatStreamHandle(streamId: streamId, lines: lines)
    }

    func cancelChatStream(streamId: String) async throws {
        _ = try await request(path: "/api/v1/chat/stream/\(streamId)/cancel", method: "POST")
    }

    func fetchLatestChatSession() async throws -> MacChatSessionDetail {
        let data = try await request(path: "/api/v1/chat/sessions/latest")
        return try decoder.decode(MacChatSessionDetail.self, from: data)
    }

    func fetchChatSession(id: String) async throws -> MacChatSessionDetail {
        let data = try await request(path: "/api/v1/chat/sessions/\(id)")
        return try decoder.decode(MacChatSessionDetail.self, from: data)
    }

    func fetchChatSessionSummaries() async throws -> [MacChatSessionSummary] {
        let data = try await request(path: "/api/v1/chat/sessions")
        return try decoder.decode([MacChatSessionSummary].self, from: data)
    }

    func fetchCompanionInbox(deviceId: String?) async throws -> [MacCompanionInboxItem] {
        var path = "/api/v1/companion/inbox"
        if let deviceId { path += "?device_id=\(deviceId)" }
        let data = try await request(path: path)
        return try decoder.decode([MacCompanionInboxItem].self, from: data)
    }

    func sendCompanionPrompt(message: String, targetDeviceId: String) async throws -> MacCompanionPromptResponse {
        struct Body: Encodable { let message: String; let targetDeviceId: String }
        let data = try await request(
            path: "/api/v1/companion/prompts",
            method: "POST",
            body: Body(message: message, targetDeviceId: targetDeviceId)
        )
        return try decoder.decode(MacCompanionPromptResponse.self, from: data)
    }

    func markCompanionInboxRead(itemId: String) async throws -> MacCompanionInboxItem {
        let data = try await request(path: "/api/v1/companion/inbox/\(itemId)/read", method: "POST")
        return try decoder.decode(MacCompanionInboxItem.self, from: data)
    }

    func fetchSchedulerStatus() async throws -> MacSchedulerStatus {
        let data = try await request(path: "/api/v1/scheduler/status")
        return try decoder.decode(MacSchedulerStatus.self, from: data)
    }

    func fetchRuntimeStatus() async throws -> MacRuntimeStatus {
        let data = try await request(path: "/api/v1/runtime/status")
        return try decoder.decode(MacRuntimeStatus.self, from: data)
    }

    func fetchChatSessions() async throws -> [MacChatSession] {
        let data = try await request(path: "/api/v1/chat/sessions")
        return try decoder.decode([MacChatSession].self, from: data)
    }

    func fetchTimeline(missionId: String, afterSequence: Int = 0) async throws -> MacTimelineResponse {
        var path = "/api/v1/missions/\(missionId)/timeline"
        if afterSequence > 0 { path += "?after_sequence=\(afterSequence)" }
        let data = try await request(path: path)
        return try decoder.decode(MacTimelineResponse.self, from: data)
    }

    func issueWebSocketTicket(scope: String, missionId: String?) async throws -> MacWSTicket {
        struct Body: Encodable { let scope: String; let missionId: String? }
        let data = try await request(
            path: "/api/v1/pairing/ws-tickets",
            method: "POST",
            body: Body(scope: scope, missionId: missionId)
        )
        return try decoder.decode(MacWSTicket.self, from: data)
    }

    func claimPairing(code: String, deviceId: String, name: String, deviceType: String) async throws -> MacPairingClaim {
        struct Body: Encodable { let code, deviceId, name, deviceType: String }
        let data = try await request(
            path: "/api/v1/pairing/claim",
            method: "POST",
            body: Body(code: code, deviceId: deviceId, name: name, deviceType: deviceType),
            requiresAuth: false
        )
        return try decoder.decode(MacPairingClaim.self, from: data)
    }

    func fetchPairingStatus(pairingId: String) async throws -> MacPairingStatus {
        let data = try await request(path: "/api/v1/pairing/\(pairingId)/status", requiresAuth: false)
        return try decoder.decode(MacPairingStatus.self, from: data)
    }

    func retrievePairingToken(pairingId: String, deviceId: String) async throws -> String {
        struct Body: Encodable { let deviceId: String }
        let data = try await request(
            path: "/api/v1/pairing/\(pairingId)/token",
            method: "POST",
            body: Body(deviceId: deviceId),
            requiresAuth: false
        )
        return try decoder.decode(MacPairingTokenResponse.self, from: data).token
    }
}

private struct AnyEncodable: Encodable {
    private let encode: (Encoder) throws -> Void
    init(_ value: Encodable) { encode = value.encode }
    func encode(to encoder: Encoder) throws { try encode(encoder) }
}

struct MacAgent: Decodable, Identifiable { let id, displayName, role, status: String }
struct MacDevice: Decodable, Identifiable {
    let id, name, deviceType, status: String
    let capabilities: [String]
}
struct MacSystemStatus: Decodable {
    let workersOnline, workersTotal, workersStale, workersOffline: Int
    let hasEligibleOnlineWorker: Bool
    let streaming: String
}
struct MacMissionDetail: Decodable, Identifiable { let id, missionType, status, title: String }
struct MacTimelineEvent: Decodable, Identifiable {
    let id, eventType, message: String
    let sequenceNumber: Int?
}
struct MacTimelineResponse: Decodable { let events: [MacTimelineEvent]; let streaming: String }
struct MacWSTicket: Decodable { let ticket: String }
struct MacPairingClaim: Decodable { let pairingId, status, message: String; let deviceId: String; let token: String? }
struct MacPairingStatus: Decodable {
    let pairingId, status, message: String
    let deviceId: String?
    let expiresAt: String
    let tokenReady: Bool
}
struct MacPairingTokenResponse: Decodable { let deviceId, token, status: String }
struct MacChatResponse: Decodable {
    let response: String
    let intent: String
    let blocked: Bool
    let sessionId: String?
    let tokenUsage: [String: StringValue]?
}

struct MacRuntimeStatus: Decodable {
    let localFirst: Bool
    let paidProvidersEnabled: Bool
    let providers: [MacProviderHealth]
}

struct MacProviderHealth: Decodable {
    let provider: String
    let configured: Bool
    let paid: Bool
    let healthy: Bool
    let mode: String
    let detail: String?
}

struct MacChatSession: Decodable, Identifiable {
    let id: String
    let title: String
    let providerMode: String
    let updatedAt: Date?
}

struct MacChatSessionSummary: Identifiable, Decodable {
    let id: String
    let title: String
    let updatedAt: Date
}

struct MacChatSessionDetail: Decodable, Identifiable {
    let id: String
    let title: String
    let messages: [MacChatSessionMessage]
}

struct MacChatSessionMessage: Decodable {
    let role: String
    let content: String
    let blocked: Bool
}

struct MacCompanionPromptResponse: Decodable {
    let status: String
    let sessionId: String
    let messageId: String
    let inboxItemId: String?
}

struct MacCompanionInboxItem: Identifiable, Decodable {
    let id: String
    let sourceDeviceId: String?
    let targetDeviceId: String
    let message: String
    let status: String
    let createdAt: Date
}

struct MacSchedulerStatus: Decodable {
    let paused: Bool
    let taskCount: Int
}

enum StringValue: Decodable {
    case string(String)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode(Int.self) {
            self = .string(String(value))
        } else if let value = try? container.decode(Bool.self) {
            self = .string(String(value))
        } else {
            self = .string("")
        }
    }
}
