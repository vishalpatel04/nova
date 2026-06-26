import Foundation

struct OrbitEmailPayload: Codable, Equatable {
    let type: String
    let draftId: String
    let status: String
    let result: OrbitEmailResult
    let actions: [AgentOSMissionAction]
    let text: String

    enum CodingKeys: String, CodingKey {
        case type
        case draftId = "draft_id"
        case status
        case result
        case actions
        case text
    }
}

struct OrbitEmailResult: Codable, Equatable {
    let to: String?
    let subject: String?
    let bodyPreview: String?
    let draftSource: String?
    let evidenceLog: String?
    let approvalQuestion: String?

    enum CodingKeys: String, CodingKey {
        case to
        case subject
        case bodyPreview = "body_preview"
        case draftSource = "draft_source"
        case evidenceLog = "evidence_log"
        case approvalQuestion = "approval_question"
    }
}
