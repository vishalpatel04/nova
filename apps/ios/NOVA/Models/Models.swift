import Foundation

struct Agent: Identifiable, Codable {
    let id: String
    let displayName: String
    let role: String
    let description: String?
    let colourToken: String
    let iconToken: String
    let voiceProfileId: String
    let modelTier: String
    let status: String

    enum CodingKeys: String, CodingKey {
        case id
        case displayName = "display_name"
        case role, description
        case colourToken = "colour_token"
        case iconToken = "icon_token"
        case voiceProfileId = "voice_profile_id"
        case modelTier = "model_tier"
        case status
    }
}

struct Device: Identifiable, Codable {
    let id: String
    let name: String
    let deviceType: String
    let status: String
    let hostname: String?
    let lastSeenAt: String?
    let capabilities: [String]

    enum CodingKeys: String, CodingKey {
        case id, name, status, hostname, capabilities
        case deviceType = "device_type"
        case lastSeenAt = "last_seen_at"
    }
}

struct Mission: Identifiable, Codable {
    let id: String
    let missionType: String
    let status: String
    let title: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, status, title
        case missionType = "mission_type"
        case createdAt = "created_at"
    }
}

struct ChatMessage: Identifiable {
    let id = UUID()
    let agentId: String
    let content: String
    let isUser: Bool
    let timestamp: Date
}

enum MockData {
    static let agents: [Agent] = [
        Agent(id: "nova", displayName: "NOVA", role: "chief_of_staff",
              description: "Chief of Staff", colourToken: "nova_blue",
              iconToken: "orb", voiceProfileId: "nova_prime",
              modelTier: "flagship", status: "active"),
        Agent(id: "mars", displayName: "MARS", role: "engineering_commander",
              description: "Engineering Commander", colourToken: "mars_red",
              iconToken: "wrench", voiceProfileId: "mars_engineer",
              modelTier: "flagship", status: "active"),
    ]

    static let devices: [Device] = [
        Device(id: "worker-001", name: "M3 Worker", deviceType: "macos_worker",
               status: "online", hostname: "macbook.local", lastSeenAt: nil,
               capabilities: ["filesystem", "ripgrep", "git"]),
    ]

    static let missions: [Mission] = [
        Mission(id: "1", missionType: "system_status", status: "completed",
                title: "System Status Check", createdAt: "2026-06-03T12:00:00Z"),
    ]

    static let chatMessages: [ChatMessage] = [
        ChatMessage(agentId: "nova", content: "Good morning, Arth. All systems operational.", isUser: false, timestamp: Date()),
        ChatMessage(agentId: "user", content: "What's my system status?", isUser: true, timestamp: Date()),
        ChatMessage(agentId: "nova", content: "One worker online. Control plane healthy.", isUser: false, timestamp: Date()),
    ]
}
