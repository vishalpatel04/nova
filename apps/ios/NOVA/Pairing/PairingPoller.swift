import Foundation

@MainActor
final class PairingPoller: ObservableObject {
    @Published private(set) var stateMachine = PairingPollStateMachine()
    @Published var statusMessage = ""

    private let api: NOVAAPIClient
    private var pollTask: Task<Void, Never>?

    init(api: NOVAAPIClient = .shared) {
        self.api = api
    }

    func stop() {
        pollTask?.cancel()
        pollTask = nil
        stateMachine.reset()
    }

    func start(pairingId: String, deviceId: String, onToken: @escaping (String) -> Void) {
        stop()
        stateMachine.beginWaiting()
        statusMessage = "Waiting for operator approval…"
        pollTask = Task {
            while !Task.isCancelled {
                stateMachine.registerPollAttempt()
                do {
                    let status = try await api.fetchPairingStatus(pairingId: pairingId)
                    stateMachine.applyStatus(status.status, tokenReady: status.tokenReady)
                    statusMessage = status.message
                    switch stateMachine.phase {
                    case .retrievingToken:
                        let token = try await api.retrievePairingToken(pairingId: pairingId, deviceId: deviceId)
                        try api.saveToken(token, deviceId: deviceId)
                        stateMachine.applyStatus("claimed", tokenReady: false)
                        statusMessage = "Paired successfully"
                        onToken(token)
                        return
                    case .success:
                        return
                    case .expired, .rejected:
                        return
                    default:
                        break
                    }
                } catch {
                    var machine = stateMachine
                    machine.setFailed(error.localizedDescription)
                    stateMachine = machine
                    statusMessage = error.localizedDescription
                    return
                }
                try? await Task.sleep(nanoseconds: stateMachine.backoffNanoseconds())
            }
        }
    }
}
