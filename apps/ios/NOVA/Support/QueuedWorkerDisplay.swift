import Foundation

enum QueuedWorkerDisplay {
    static func message(for status: String) -> String {
        switch status {
        case "queued_waiting_for_worker":
            return "Mission queued — no worker is online yet."
        default:
            return "Mission status: \(status)"
        }
    }
}
