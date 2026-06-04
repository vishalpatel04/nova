import Foundation

struct ChatMessage: Identifiable, Equatable, Codable {
    enum Role: String, Equatable, Codable {
        case user
        case assistant
        case error
    }

    let id: UUID
    var role: Role
    var content: String
    let timestamp: Date
    var blocked: Bool
    var isStreaming: Bool

    init(
        id: UUID = UUID(),
        role: Role,
        content: String,
        timestamp: Date = Date(),
        blocked: Bool = false,
        isStreaming: Bool = false
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.blocked = blocked
        self.isStreaming = isStreaming
    }
}
