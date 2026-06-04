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

    var deviceToken: String? { KeychainStore.load() }

    func saveToken(_ token: String) throws { try KeychainStore.save(token: token) }
    func clearToken() { KeychainStore.delete() }

    private func request(path: String, method: String = "GET", body: Encodable? = nil, requiresAuth: Bool = true) async throws -> Data {
        guard let url = URL(string: "\(baseURL)\(path)") else { throw URLError(.badURL) }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
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

    func createMission(type: String, title: String) async throws -> MacMissionDetail {
        struct Body: Encodable { let missionType: String; let title: String }
        let data = try await request(
            path: "/api/v1/missions",
            method: "POST",
            body: Body(missionType: type, title: title)
        )
        return try decoder.decode(MacMissionDetail.self, from: data)
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
