import XCTest
@testable import NOVAGenie

@MainActor
final class HotkeyManagerTests: XCTestCase {
    func testDefaultHotkeyUsesOptionSpace() {
        let manager = GlobalHotkeyManager()
        XCTAssertEqual(manager.keyCode, GlobalHotkeyManager.defaultKeyCode)
        XCTAssertEqual(manager.modifiers, GlobalHotkeyManager.defaultModifiers)
    }

    func testDisabledSkipsRegistrationError() {
        let manager = GlobalHotkeyManager()
        manager.isEnabled = false
        manager.applyRegistration()
        XCTAssertNil(manager.registrationError)
    }
}
