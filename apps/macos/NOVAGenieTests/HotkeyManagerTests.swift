import Carbon
import XCTest
@testable import NOVAGenie

@MainActor
final class HotkeyManagerTests: XCTestCase {
    func testDefaultHotkeyUsesOptionS() {
        let manager = GlobalHotkeyManager()
        XCTAssertEqual(manager.keyCode, GlobalHotkeyManager.defaultKeyCode)
        XCTAssertEqual(manager.keyCode, UInt32(kVK_ANSI_S))
        XCTAssertEqual(manager.modifiers, GlobalHotkeyManager.defaultModifiers)
        XCTAssertEqual(manager.modifiers, UInt32(optionKey))
    }

    func testDisabledSkipsRegistrationError() {
        let manager = GlobalHotkeyManager()
        manager.isEnabled = false
        manager.applyRegistration()
        XCTAssertNil(manager.registrationError)
    }
}
