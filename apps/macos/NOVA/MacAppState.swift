import Foundation
import Combine

final class MacAppState: ObservableObject {
    @Published var voiceMode: VoiceMode = .primeOnly
    @Published var isExpanded = false
    @Published var workerHealth: WorkerHealth = .unknown
    @Published var apiBaseURL = "http://localhost:8000"

    enum VoiceMode: String, CaseIterable {
        case primeOnly = "prime_only"
        case warRoom = "war_room"
        case silentOperations = "silent_operations"
        case briefing = "briefing"

        var displayName: String {
            switch self {
            case .primeOnly: return "Prime Only"
            case .warRoom: return "War Room"
            case .silentOperations: return "Silent Ops"
            case .briefing: return "Briefing"
            }
        }
    }

    enum WorkerHealth {
        case unknown, healthy, degraded, offline

        var label: String {
            switch self {
            case .unknown: return "Unknown"
            case .healthy: return "Healthy"
            case .degraded: return "Degraded"
            case .offline: return "Offline"
            }
        }

        var color: String {
            switch self {
            case .unknown: return "gray"
            case .healthy: return "green"
            case .degraded: return "orange"
            case .offline: return "red"
            }
        }
    }
}
