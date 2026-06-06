import XCTest
@testable import NOVA

final class NovaOrbStateMachineTests: XCTestCase {
    func testListeningActivatesOrb() {
        var machine = NovaOrbStateMachine()
        machine.beginListening()
        XCTAssertTrue(machine.isListening)
        XCTAssertTrue(machine.isActive)
        machine.endListening()
        XCTAssertFalse(machine.isActive)
    }
}
