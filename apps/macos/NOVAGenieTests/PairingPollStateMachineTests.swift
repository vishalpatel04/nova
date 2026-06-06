import XCTest
@testable import NOVAGenie

final class PairingPollStateMachineTests: XCTestCase {
    func testRejectedStatus() {
        var machine = PairingPollStateMachine()
        machine.applyStatus("rejected", tokenReady: false)
        XCTAssertEqual(machine.phase, .rejected)
    }
}
