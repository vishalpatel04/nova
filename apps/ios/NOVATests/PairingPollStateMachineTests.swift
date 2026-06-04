import XCTest
@testable import NOVA

final class PairingPollStateMachineTests: XCTestCase {
    func testApprovedWithTokenReadyMovesToRetrieving() {
        var machine = PairingPollStateMachine()
        machine.beginWaiting()
        machine.applyStatus("approved", tokenReady: true)
        XCTAssertEqual(machine.phase, .retrievingToken)
    }

    func testBackoffCapsAtThirtySeconds() {
        var machine = PairingPollStateMachine()
        for _ in 0..<20 { machine.registerPollAttempt() }
        XCTAssertLessThanOrEqual(Double(machine.backoffNanoseconds()) / 1e9, 30.0)
    }
}
