import XCTest
@testable import NOVAGenie

final class NovaOrbStateMachineTests: XCTestCase {
    func testToggleListening() {
        var machine = NovaOrbStateMachine()
        machine.beginListening()
        XCTAssertTrue(machine.isActive)
    }
}
