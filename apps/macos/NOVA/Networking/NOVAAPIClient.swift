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

    func fetchPendingApprovals() async throws -> [MacApprovalRequest] {
        let data = try await request(path: "/api/v1/approvals/pending")
        struct Response: Decodable { let items: [MacApprovalRequest] }
        return try decoder.decode(Response.self, from: data).items
    }

    func fetchActionableApprovals() async throws -> MacActionableApprovals {
        let data = try await request(path: "/api/v1/approvals/actionable")
        return try decoder.decode(MacActionableApprovals.self, from: data)
    }

    func runApprovedExecution(approvalId: String) async throws -> MacShellExecutionResult {
        struct Body: Encodable { let approvalId: String }
        let data = try await request(
            path: "/api/v1/executions/run-approved",
            method: "POST",
            body: Body(approvalId: approvalId)
        )
        return try decoder.decode(MacShellExecutionResult.self, from: data)
    }

    func applyApprovedPatch(approvalId: String) async throws -> MacPatchExecutionResult {
        struct Body: Encodable { let approvalId: String }
        let data = try await request(
            path: "/api/v1/executions/apply-approved-patch",
            method: "POST",
            body: Body(approvalId: approvalId)
        )
        return try decoder.decode(MacPatchExecutionResult.self, from: data)
    }

    func setActiveProject(path: String) async throws -> MacActiveProject {
        struct Body: Encodable { let projectRoot: String }
        let data = try await request(
            path: "/api/v1/projects/active",
            method: "POST",
            body: Body(projectRoot: path)
        )
        return try decoder.decode(MacActiveProject.self, from: data)
    }

    func fetchActiveProject() async throws -> MacActiveProject {
        let data = try await request(path: "/api/v1/projects/active")
        return try decoder.decode(MacActiveProject.self, from: data)
    }

    func approveRequest(id: String) async throws -> MacApprovalRequest {
        let data = try await request(path: "/api/v1/approvals/\(id)/approve", method: "POST")
        return try decoder.decode(MacApprovalRequest.self, from: data)
    }

    func rejectRequest(id: String) async throws -> MacApprovalRequest {
        let data = try await request(path: "/api/v1/approvals/\(id)/reject", method: "POST")
        return try decoder.decode(MacApprovalRequest.self, from: data)
    }

    func fetchSchedulerStatus() async throws -> MacSchedulerStatus {
        let data = try await request(path: "/api/v1/scheduler/status")
        return try decoder.decode(MacSchedulerStatus.self, from: data)
    }

    func fetchBackgroundTasks() async throws -> [MacBackgroundTask] {
        let data = try await request(path: "/api/v1/background-tasks")
        return try decoder.decode(MacBackgroundTaskList.self, from: data).tasks
    }

    func fetchBackgroundTask(taskId: String) async throws -> MacBackgroundTask {
        let data = try await request(path: "/api/v1/background-tasks/\(taskId)")
        return try decoder.decode(MacBackgroundTask.self, from: data)
    }

    func createBackgroundTask(body: MacBackgroundTaskCreate) async throws -> MacBackgroundTask {
        let data = try await request(path: "/api/v1/background-tasks", method: "POST", body: body)
        return try decoder.decode(MacBackgroundTask.self, from: data)
    }

    func pauseBackgroundTask(taskId: String) async throws -> MacBackgroundTask {
        let data = try await request(path: "/api/v1/background-tasks/\(taskId)/pause", method: "POST")
        return try decoder.decode(MacBackgroundTask.self, from: data)
    }

    func resumeBackgroundTask(taskId: String) async throws -> MacBackgroundTask {
        let data = try await request(path: "/api/v1/background-tasks/\(taskId)/resume", method: "POST")
        return try decoder.decode(MacBackgroundTask.self, from: data)
    }

    func cancelBackgroundTask(taskId: String) async throws -> MacBackgroundTask {
        let data = try await request(path: "/api/v1/background-tasks/\(taskId)/cancel", method: "POST")
        return try decoder.decode(MacBackgroundTask.self, from: data)
    }

    func runBackgroundTaskNow(taskId: String) async throws -> MacBackgroundTaskRun {
        let data = try await request(path: "/api/v1/background-tasks/\(taskId)/run-now", method: "POST")
        return try decoder.decode(MacBackgroundTaskRun.self, from: data)
    }

    func fetchBackgroundTaskRuns(taskId: String) async throws -> [MacBackgroundTaskRun] {
        let data = try await request(path: "/api/v1/background-tasks/\(taskId)/runs")
        return try decoder.decode(MacBackgroundTaskRunList.self, from: data).runs
    }

    func fetchBackgroundSchedulerStatus() async throws -> MacBackgroundSchedulerStatus {
        let data = try await request(path: "/api/v1/background-tasks/scheduler-status")
        return try decoder.decode(MacBackgroundSchedulerStatus.self, from: data)
    }

    func fetchNotifications() async throws -> MacNotificationList {
        let data = try await request(path: "/api/v1/notifications")
        return try decoder.decode(MacNotificationList.self, from: data)
    }

    func markNotificationRead(notificationId: String) async throws -> MacNotificationItem {
        let data = try await request(
            path: "/api/v1/notifications/\(notificationId)/read",
            method: "POST"
        )
        return try decoder.decode(MacNotificationItem.self, from: data)
    }

    func markAllNotificationsRead() async throws -> Int {
        struct Response: Decodable { let markedRead: Int }
        let data = try await request(path: "/api/v1/notifications/read-all", method: "POST")
        return try decoder.decode(Response.self, from: data).markedRead
    }

    func fetchRuntimeStatus() async throws -> MacRuntimeStatus {
        let data = try await request(path: "/api/v1/runtime/status")
        return try decoder.decode(MacRuntimeStatus.self, from: data)
    }

    func fetchActiveAgentPlan() async throws -> MacAgentPlanDetail? {
        struct Wrapper: Decodable { let plan: MacAgentPlanDetail? }
        let data = try await request(path: "/api/v1/agent-plans/active")
        return try decoder.decode(Wrapper.self, from: data).plan
    }

    func createAgentPlan(objective: String, title: String? = nil) async throws -> MacAgentPlanDetail {
        struct Body: Encodable {
            let objective: String
            let title: String?
        }
        struct Direct: Decodable {
            let planId: String
            let status: String
            let objective: String
            let providerLane: String
            let currentStepIndex: Int
            let steps: [MacAgentPlanStep]
            let waitingApproval: Bool?
            let approvalId: String?
            let patchPreview: String?
            let reviewerVerdict: String?
            let commitProposal: MacCommitProposal?
        }
        let data = try await request(
            path: "/api/v1/agent-plans",
            method: "POST",
            body: Body(objective: objective, title: title)
        )
        let direct = try decoder.decode(Direct.self, from: data)
        return MacAgentPlanDetail(
            planId: direct.planId,
            status: direct.status,
            objective: direct.objective,
            providerLane: direct.providerLane,
            currentStepIndex: direct.currentStepIndex,
            steps: direct.steps,
            waitingApproval: direct.waitingApproval,
            approvalId: direct.approvalId,
            patchPreview: direct.patchPreview,
            reviewerVerdict: direct.reviewerVerdict,
            commitProposal: direct.commitProposal
        )
    }

    func cancelAgentPlan(planId: String) async throws {
        _ = try await request(path: "/api/v1/agent-plans/\(planId)/cancel", method: "POST")
    }

    func fetchProviderTrust() async throws -> MacProviderTrust {
        let data = try await request(path: "/api/v1/provider-trust")
        return try decoder.decode(MacProviderTrust.self, from: data)
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
    let approvalRequired: Bool?
    let approvalId: String?
    let riskLevel: String?
    let taskId: String?
    let timeline: [MacTaskTimelineEntry]?
    let activeProject: String?
    let unifiedDiff: String?
}

struct MacTaskTimelineEntry: Decodable, Identifiable {
    var id: String { stage + (at ?? "") }
    let stage: String
    let message: String
    let at: String?
}

struct MacActiveProject: Decodable {
    let projectRoot: String
    let projectName: String
    let currentBranch: String?
    let detectedTooling: [String: Bool]?
    let lastOpenedAt: Date
    let userId: String
    let deviceId: String
}

struct MacRuntimeStatus: Decodable {
    let localFirst: Bool
    let paidProvidersEnabled: Bool
    let providers: [MacProviderHealth]
    let localModel: String?
    let ollamaReachable: Bool
    let ollamaModelReady: Bool
    let providerBadge: String?
    let statusMessage: String?
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

struct MacBackgroundTask: Identifiable, Decodable {
    let id: String
    let taskType: String
    let title: String
    let projectRoot: String?
    let scheduleKind: String
    let scheduleExpression: String
    let status: String
    let nextRunAt: Date?
    let lastResultSummary: String?
    let lastError: String?
    let runCount: Int
    let failureCount: Int
}

struct MacBackgroundTaskList: Decodable {
    let tasks: [MacBackgroundTask]
}

struct MacBackgroundTaskCreate: Encodable {
    let taskType: String
    let title: String
    let projectRoot: String?
    let scheduleKind: String
    let scheduleExpression: String
}

struct MacBackgroundTaskRun: Identifiable, Decodable {
    let id: String
    let taskId: String
    let status: String
    let summary: String?
    let error: String?
    let attempt: Int
    let startedAt: Date?
    let finishedAt: Date?
}

struct MacBackgroundTaskRunList: Decodable {
    let runs: [MacBackgroundTaskRun]
}

struct MacBackgroundSchedulerStatus: Decodable {
    let active: Bool
    let activeTasks: Int
    let failedTasks: Int
    let dueTasks: Int
    let unreadNotifications: Int
}

struct MacNotificationItem: Identifiable, Decodable {
    let id: String
    let notificationType: String
    let title: String
    let summary: String
    let taskId: String?
    let read: Bool
    let createdAt: Date
}

struct MacNotificationList: Decodable {
    let notifications: [MacNotificationItem]
    let unreadCount: Int
}

struct MacApprovalRequest: Identifiable, Decodable {
    let id: String
    let capability: String
    let actionSummary: String
    let commandOrPayloadPreview: String
    let riskLevel: String
    let status: String
    let createdAt: Date
    let expiresAt: Date
}

struct MacActionableApprovals: Decodable {
    let pending: [MacApprovalRequest]
    let approved: [MacApprovalRequest]
}

struct MacShellExecutionResult: Decodable {
    let executionId: String
    let approvalId: String
    let capability: String
    let commandPreview: String
    let status: String
    let stdoutExcerpt: String?
    let stderrExcerpt: String?
    let exitCode: Int?
    let startedAt: Date?
    let finishedAt: Date?
}

struct MacPatchExecutionResult: Decodable {
    let executionId: String
    let approvalId: String
    let capability: String
    let projectRoot: String
    let patchPreview: String
    let status: String
    let appliedFiles: [String]?
    let errorMessage: String?
    let startedAt: Date?
    let finishedAt: Date?
}

struct MacAgentPlanStep: Decodable, Identifiable {
    var id: Int { stepIndex }
    let stepIndex: Int
    let agentRole: String
    let actionType: String
    let status: String
    let inputSummary: String?
    let outputSummary: String?
    let retryCount: Int?
}

struct MacCommitProposal: Decodable {
    let branchName: String
    let commitMessage: String
    let stagedPaths: [String]
    let pushDisabled: Bool?
}

struct MacAgentPlanDetail: Decodable {
    let planId: String
    let status: String
    let objective: String
    let providerLane: String
    let currentStepIndex: Int
    let steps: [MacAgentPlanStep]
    let waitingApproval: Bool?
    let approvalId: String?
    let patchPreview: String?
    let reviewerVerdict: String?
    let commitProposal: MacCommitProposal?

    enum CodingKeys: String, CodingKey {
        case planId = "plan_id"
        case status, objective, providerLane, currentStepIndex, steps
        case waitingApproval, approvalId, patchPreview, reviewerVerdict, commitProposal
    }
}

struct MacProviderTrustEntry: Decodable {
    let kind: String
    let configured: Bool
    let enabled: Bool
}

struct MacProviderTrust: Decodable {
    let activeLane: String
    let localActive: Bool
    let externalProvidersEnabled: Bool
    let providers: [MacProviderTrustEntry]
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
