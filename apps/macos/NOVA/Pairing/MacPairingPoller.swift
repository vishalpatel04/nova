import Foundation

@MainActor
final class MacPairingPoller: ObservableObject {
    @Published private(set) var stateMachine = PairingPollStateMachine()
    @Published var statusMessage = ""

    private let api: NOVAAPIClient
    private var pollTask: Task<Void, Never>?

    init(api: NOVAAPIClient? = nil) {
        self.api = api ?? .shared
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
                    if stateMachine.phase == .retrievingToken {
                        let token = try await api.retrievePairingToken(pairingId: pairingId, deviceId: deviceId)
                        try api.saveToken(token)
                        stateMachine.applyStatus("claimed", tokenReady: false)
                        statusMessage = "Paired successfully"
                        onToken(token)
                        return
                    }
                    if stateMachine.phase == .success || stateMachine.phase == .expired || stateMachine.phase == .rejected {
                        return
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
