import Foundation

enum MissionStreamBadge: String, Equatable {
    case live
    case reconnecting
    case degraded
    case offline
    case disconnected

    init(streamingStatus: String) {
        switch streamingStatus.lowercased() {
        case "live": self = .live
        case "reconnecting": self = .reconnecting
        case "degraded": self = .degraded
        case "offline", "error": self = .offline
        default: self = .disconnected
        }
    }
}

struct TimelineMerger {
    static func merge(existing: [TimelineEvent], incoming: [TimelineEvent]) -> [TimelineEvent] {
        var byId: [String: TimelineEvent] = [:]
        for event in existing + incoming {
            byId[event.id] = event
        }
        return byId.values.sorted {
            ($0.sequenceNumber ?? 0) < ($1.sequenceNumber ?? 0)
        }
    }

    static func maxSequence(in events: [TimelineEvent], current: Int) -> Int {
        let maxSeq = events.compactMap(\.sequenceNumber).max() ?? current
        return max(current, maxSeq)
    }
}
