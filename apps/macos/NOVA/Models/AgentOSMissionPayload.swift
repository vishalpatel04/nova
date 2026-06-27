import Foundation

struct AgentOSMissionPayload: Codable, Equatable {
    let type: String
    let missionId: String
    let status: String
    let missionTitle: String
    let agentTimeline: [AgentOSTimelineEntry]
    let agentReports: [WarRoomAgentReport]?
    let warRoomRoster: [WarRoomRosterEntry]?
    let graphNodes: [MissionGraphNodeViewModel]?
    let result: AgentOSMissionResult
    let actions: [AgentOSMissionAction]
    let text: String

    enum CodingKeys: String, CodingKey {
        case type
        case missionId = "mission_id"
        case status
        case missionTitle = "mission_title"
        case agentTimeline = "agent_timeline"
        case agentReports = "agent_reports"
        case warRoomRoster = "war_room_roster"
        case graphNodes = "graph_nodes"
        case result
        case actions
        case text
    }
}

struct AgentOSTimelineEntry: Codable, Equatable, Identifiable {
    var id: String { "\(agent)-\(summary)" }
    let agent: String
    let agentId: String?
    let status: String
    let summary: String
    let timestamp: String?

    enum CodingKeys: String, CodingKey {
        case agent
        case agentId = "agent_id"
        case status
        case summary
        case timestamp
    }
}

struct AgentOSMissionResult: Codable, Equatable {
    let appName: String?
    let appType: String?
    let path: String?
    let buildStatus: String?
    let previewUrl: String?
    let runCommand: String?
    let evidenceLog: String?
    let approvalKind: String?
    let approvalQuestion: String?
    let runtime: String?
    let deploymentStatus: String?
    let forgeEngine: String?
    let engineDisplayName: String?
    let engineStatus: String?
    let forgeEvidencePaths: [String]?

    enum CodingKeys: String, CodingKey {
        case appName = "app_name"
        case appType = "app_type"
        case path
        case buildStatus = "build_status"
        case previewUrl = "preview_url"
        case runCommand = "run_command"
        case evidenceLog = "evidence_log"
        case approvalKind = "approval_kind"
        case approvalQuestion = "approval_question"
        case runtime
        case deploymentStatus = "deployment_status"
        case forgeEngine = "forge_engine"
        case engineDisplayName = "engine_display_name"
        case engineStatus = "engine_status"
        case forgeEvidencePaths = "forge_evidence_paths"
    }
}

struct AgentOSMissionAction: Codable, Equatable, Identifiable {
    var id: String { "\(action)-\(label)-\(missionId ?? url ?? text ?? "")" }
    let label: String
    let action: String
    let missionId: String?
    let url: String?
    let text: String?

    enum CodingKeys: String, CodingKey {
        case label
        case action
        case missionId = "mission_id"
        case url
        case text
    }
}
