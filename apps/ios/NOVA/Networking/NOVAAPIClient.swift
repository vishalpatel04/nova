import Foundation

@MainActor
final class NOVAAPIClient: ObservableObject {
    static let shared = NOVAAPIClient()

    @Published var baseURL: String
    @Published var isLoading = false
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

    var deviceToken: String? { KeychainStore.loadResolved() }

    func saveToken(_ token: String, deviceId: String) throws {
        NovaDeviceIdentity.persistDeviceId(deviceId)
        try KeychainStore.save(token: token, account: deviceId)
        KeychainStore.delete(
            account: NovaDeviceIdentity.legacyAccount,
            service: NovaDeviceIdentity.legacyService
        )
    }

    func clearToken() {
        if let deviceId = NovaDeviceIdentity.resolvedDeviceId() {
            KeychainStore.delete(account: deviceId)
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
        idempotencyKey: String? = nil,
        requiresAuth: Bool = true
    ) async throws -> (Data, HTTPURLResponse) {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw NOVAAPIError.network(URLError(.badURL))
        }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if requiresAuth {
            guard let token = deviceToken else { throw NOVAAPIError.noToken }
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let idempotencyKey {
            req.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key")
        }
        if let body {
            req.httpBody = try encoder.encode(AnyEncodable(body))
        }
        do {
            let (data, response) = try await URLSession.shared.data(for: req)
            guard let http = response as? HTTPURLResponse else {
                throw NOVAAPIError.network(URLError(.badServerResponse))
            }
            if http.statusCode == 401 { throw NOVAAPIError.unauthorized }
            if http.statusCode >= 400 {
                let message = String(data: data, encoding: .utf8) ?? "unknown"
                throw NOVAAPIError.http(http.statusCode, message)
            }
            return (data, http)
        } catch let err as NOVAAPIError {
            throw err
        } catch {
            throw NOVAAPIError.network(error)
        }
    }

    func fetchAgents() async throws -> [Agent] {
        let (data, _) = try await request(path: "/api/v1/agents")
        return try decoder.decode([Agent].self, from: data)
    }

    func fetchDevices() async throws -> [Device] {
        let (data, _) = try await request(path: "/api/v1/devices")
        return try decoder.decode([Device].self, from: data)
    }

    func fetchSystemStatus() async throws -> SystemStatus {
        let (data, _) = try await request(path: "/api/v1/system/status")
        return try decoder.decode(SystemStatus.self, from: data)
    }

    func createMission(type: String, title: String, idempotencyKey: String? = nil) async throws -> MissionDetail {
        struct Body: Encodable { let missionType: String; let title: String }
        let (data, _) = try await request(
            path: "/api/v1/missions",
            method: "POST",
            body: Body(missionType: type, title: title),
            idempotencyKey: idempotencyKey
        )
        return try decoder.decode(MissionDetail.self, from: data)
    }

    func fetchMission(id: String) async throws -> MissionDetail {
        let (data, _) = try await request(path: "/api/v1/missions/\(id)")
        return try decoder.decode(MissionDetail.self, from: data)
    }

    func fetchTimeline(missionId: String, afterSequence: Int = 0) async throws -> TimelineResponse {
        var path = "/api/v1/missions/\(missionId)/timeline"
        if afterSequence > 0 { path += "?after_sequence=\(afterSequence)" }
        let (data, _) = try await request(path: path)
        return try decoder.decode(TimelineResponse.self, from: data)
    }

    func issueWebSocketTicket(scope: String, missionId: String?) async throws -> WebSocketTicketResponse {
        struct Body: Encodable {
            let scope: String
            let missionId: String?
        }
        let (data, _) = try await request(
            path: "/api/v1/pairing/ws-tickets",
            method: "POST",
            body: Body(scope: scope, missionId: missionId)
        )
        return try decoder.decode(WebSocketTicketResponse.self, from: data)
    }

    func claimPairing(
        code: String,
        deviceId: String,
        name: String,
        deviceType: String
    ) async throws -> PairingClaimResponse {
        struct Body: Encodable {
            let code: String
            let deviceId: String
            let name: String
            let deviceType: String
        }
        let (data, _) = try await request(
            path: "/api/v1/pairing/claim",
            method: "POST",
            body: Body(code: code, deviceId: deviceId, name: name, deviceType: deviceType),
            requiresAuth: false
        )
        return try decoder.decode(PairingClaimResponse.self, from: data)
    }

    func fetchPairingStatus(pairingId: String) async throws -> PairingStatusResponse {
        let (data, _) = try await request(
            path: "/api/v1/pairing/\(pairingId)/status",
            requiresAuth: false
        )
        return try decoder.decode(PairingStatusResponse.self, from: data)
    }

    func retrievePairingToken(pairingId: String, deviceId: String) async throws -> String {
        struct Body: Encodable { let deviceId: String }
        let (data, _) = try await request(
            path: "/api/v1/pairing/\(pairingId)/token",
            method: "POST",
            body: Body(deviceId: deviceId),
            requiresAuth: false
        )
        return try decoder.decode(PairingTokenResponse.self, from: data).token
    }
}

private struct AnyEncodable: Encodable {
    private let encode: (Encoder) throws -> Void
    init(_ value: Encodable) {
        encode = value.encode
    }
    func encode(to encoder: Encoder) throws { try encode(encoder) }
}

struct SystemStatus: Decodable {
    let controlPlane: String
    let streaming: String
    let workersOnline: Int
    let workersTotal: Int
    let workersStale: Int
    let workersOffline: Int
    let hasEligibleOnlineWorker: Bool
}

struct MissionDetail: Decodable, Identifiable {
    let id: String
    let missionType: String
    let status: String
    let title: String
    let createdAt: Date?
    let timelineEvents: [TimelineEvent]?
}

struct TimelineEvent: Decodable, Identifiable {
    let id: String
    let eventType: String
    let message: String
    let sequenceNumber: Int?
    let createdAt: Date?
}

struct TimelineResponse: Decodable {
    let missionId: String
    let events: [TimelineEvent]
    let streaming: String
    let afterSequence: Int
}

struct WebSocketTicketResponse: Decodable {
    let ticket: String
    let expiresInSeconds: Int
}

struct PairingClaimResponse: Decodable {
    let pairingId: String
    let status: String
    let deviceId: String
    let token: String?
    let message: String
}

struct PairingStatusResponse: Decodable {
    let pairingId: String
    let status: String
    let deviceId: String?
    let expiresAt: String
    let tokenReady: Bool
    let message: String
}

struct PairingTokenResponse: Decodable {
    let deviceId: String
    let token: String
    let status: String
}
