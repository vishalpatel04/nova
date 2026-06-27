import Foundation

struct WarRoomAgentReport: Codable, Equatable, Identifiable {
    var id: String { "\(agentId)-\(report)" }
    let agent: String
    let agentId: String
    let status: String
    let report: String
    let timestamp: String?

    enum CodingKeys: String, CodingKey {
        case agent
        case agentId = "agent_id"
        case status
        case report
        case timestamp
    }
}

struct WarRoomRosterEntry: Codable, Equatable, Identifiable {
    var id: String { agentId }
    let agentId: String
    let displayName: String
    let glyph: String
    let colorToken: String
    let status: String
    let taskSummary: String

    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case displayName = "display_name"
        case glyph
        case colorToken = "color_token"
        case status
        case taskSummary = "task_summary"
    }
}

struct MissionGraphNodeViewModel: Codable, Equatable, Identifiable {
    var id: String { nodeId }
    let nodeId: String
    let displayName: String
    let status: String
    let outputSummary: String

    enum CodingKeys: String, CodingKey {
        case nodeId = "node_id"
        case displayName = "display_name"
        case status
        case outputSummary = "output_summary"
    }
}

enum AgentParticipant: String, CaseIterable, Identifiable {
    case prime
    case archive
    case forge
    case qa
    case sentry
    case orbit
    case muse
    case nexus

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .prime: return "Prime"
        case .archive: return "Archive"
        case .forge: return "Forge"
        case .qa: return "QA"
        case .sentry: return "Sentry"
        case .orbit: return "Orbit"
        case .muse: return "Muse"
        case .nexus: return "Nexus"
        }
    }

    var glyph: String {
        switch self {
        case .prime: return "star.fill"
        case .archive: return "books.vertical.fill"
        case .forge: return "hammer.fill"
        case .qa: return "checkmark.seal.fill"
        case .sentry: return "shield.fill"
        case .orbit: return "envelope.fill"
        case .muse: return "paintbrush.fill"
        case .nexus: return "point.3.connected.trianglepath.dotted"
        }
    }

    var colorToken: String {
        switch self {
        case .prime, .nexus: return "nova_blue"
        case .archive: return "mercury_silver"
        case .forge: return "mars_red"
        case .qa: return "neptune_teal"
        case .sentry: return "saturn_gold"
        case .orbit: return "venus_rose"
        case .muse: return "jupiter_amber"
        }
    }
}

enum AgentStatus: String {
    case idle
    case thinking
    case working
    case done
    case blocked
    case needsApproval = "needs_approval"

    var label: String {
        switch self {
        case .idle: return "Idle"
        case .thinking: return "Thinking"
        case .working: return "Working"
        case .done: return "Done"
        case .blocked: return "Blocked"
        case .needsApproval: return "Needs approval"
        }
    }
}

struct WarRoomMessage: Identifiable, Equatable {
    let id: String
    let speaker: String
    let agentId: String?
    let glyph: String
    let colorToken: String
    let body: String
    let isUser: Bool
    let timestamp: Date?
}

extension WarRoomRosterEntry {
    static func defaultRoster() -> [WarRoomRosterEntry] {
        AgentParticipant.allCases.map { agent in
            WarRoomRosterEntry(
                agentId: agent.rawValue,
                displayName: agent.displayName,
                glyph: agent.glyph,
                colorToken: agent.colorToken,
                status: AgentStatus.idle.rawValue,
                taskSummary: "Standing by"
            )
        }
    }
}
