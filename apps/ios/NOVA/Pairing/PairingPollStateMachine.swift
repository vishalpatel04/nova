import Foundation

enum PairingPollPhase: Equatable {
    case idle
    case waitingApproval
    case polling
    case retrievingToken
    case success
    case expired
    case rejected
    case failed(String)
}

struct PairingPollStateMachine {
    private(set) var phase: PairingPollPhase = .idle
    private(set) var attempt: Int = 0

    mutating func reset() {
        phase = .idle
        attempt = 0
    }

    mutating func beginWaiting() {
        phase = .waitingApproval
        attempt = 0
    }

    mutating func registerPollAttempt() {
        attempt += 1
        phase = .polling
    }

    mutating func applyStatus(_ status: String, tokenReady: Bool) {
        switch status {
        case "pending":
            phase = .waitingApproval
        case "approved":
            phase = tokenReady ? .retrievingToken : .polling
        case "claimed":
            phase = .success
        case "expired":
            phase = .expired
        case "rejected":
            phase = .rejected
        default:
            phase = .polling
        }
    }

    mutating func setFailed(_ message: String) {
        phase = .failed(message)
    }

    func backoffNanoseconds(maxAttempt: Int = 8) -> UInt64 {
        let capped = min(attempt, maxAttempt)
        let seconds = min(pow(2.0, Double(capped)) * 0.5, 30.0)
        return UInt64(seconds * 1_000_000_000)
    }
}
