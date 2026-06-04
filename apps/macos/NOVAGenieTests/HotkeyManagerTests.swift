import Carbon
import XCTest
@testable import NOVAGenie

@MainActor
final class HotkeyManagerTests: XCTestCase {
    private var defaults: UserDefaults!
    private var events: [String] = []

    override func setUp() {
        super.setUp()
        let suiteName = "NOVAGenieTests.Hotkey.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)
        events = []
        NovaHotkeyTelemetry.eventSink = { [weak self] event in
            self?.events.append(event)
        }
        MenuBarCoordinator.resetForTesting()
    }

    override func tearDown() {
        NovaHotkeyTelemetry.eventSink = nil
        MenuBarCoordinator.resetForTesting()
        super.tearDown()
    }

    func testDefaultKeycodeIsSpaceAndModifiersControlOption() {
        XCTAssertEqual(GlobalHotkeyManager.defaultKeyCode, UInt32(kVK_Space))
        XCTAssertEqual(GlobalHotkeyManager.defaultModifiers, UInt32(optionKey | controlKey))
        XCTAssertEqual(GlobalHotkeyManager.defaultShortcutLabel, "⌃⌥ Space")

        let manager = GlobalHotkeyManager(userDefaults: defaults)
        XCTAssertEqual(manager.keyCode, UInt32(kVK_Space))
        XCTAssertEqual(manager.modifiers, UInt32(optionKey | controlKey))
    }

    func testMigratesLegacyOptionSDefault() {
        defaults.set(UInt32(kVK_ANSI_S), forKey: "nova_hotkey_keycode")
        defaults.set(UInt32(optionKey), forKey: "nova_hotkey_modifiers")

        let manager = GlobalHotkeyManager(userDefaults: defaults)

        XCTAssertEqual(manager.keyCode, UInt32(kVK_Space))
        XCTAssertEqual(manager.modifiers, UInt32(optionKey | controlKey))
        XCTAssertTrue(defaults.bool(forKey: "nova_hotkey_migrated_ctrl_opt_space"))
    }

    func testMigratesLegacyOptionSpaceDefault() {
        defaults.set(UInt32(kVK_Space), forKey: "nova_hotkey_keycode")
        defaults.set(UInt32(optionKey), forKey: "nova_hotkey_modifiers")

        let manager = GlobalHotkeyManager(userDefaults: defaults)

        XCTAssertEqual(manager.keyCode, UInt32(kVK_Space))
        XCTAssertEqual(manager.modifiers, UInt32(optionKey | controlKey))
    }

    func testDoesNotMigrateCustomShortcut() {
        defaults.set(UInt32(kVK_ANSI_A), forKey: "nova_hotkey_keycode")
        defaults.set(UInt32(cmdKey), forKey: "nova_hotkey_modifiers")

        let manager = GlobalHotkeyManager(userDefaults: defaults)

        XCTAssertEqual(manager.keyCode, UInt32(kVK_ANSI_A))
        XCTAssertEqual(manager.modifiers, UInt32(cmdKey))
        XCTAssertFalse(defaults.bool(forKey: "nova_hotkey_migrated_ctrl_opt_space"))
    }

    func testDuplicateRegistrationPrevention() {
        let manager = GlobalHotkeyManager(userDefaults: defaults)
        manager.isEnabled = false
        manager.applyRegistration()
        XCTAssertEqual(manager.registrationAttemptCount, 0)

        manager.isEnabled = true
        manager.applyRegistration()
        let attemptsAfterFirst = manager.registrationAttemptCount
        XCTAssertGreaterThanOrEqual(attemptsAfterFirst, 1)

        manager.applyRegistration()
        XCTAssertEqual(manager.registrationAttemptCount, attemptsAfterFirst)
        XCTAssertTrue(events.contains("nova_hotkey_register_skipped_duplicate"))
    }

    func testDisabledHotkeySkipsRegistration() {
        let manager = GlobalHotkeyManager(userDefaults: defaults)
        manager.isEnabled = false
        manager.applyRegistration()
        XCTAssertNil(manager.registrationError)
        XCTAssertFalse(manager.isHotkeyRegistered)
        XCTAssertFalse(events.contains("nova_hotkey_register_attempt"))
    }

    func testRegisterAtStartupOnlyOnce() {
        let manager = GlobalHotkeyManager(userDefaults: defaults)
        manager.isEnabled = true
        manager.registerAtStartup()
        let count = manager.registrationAttemptCount
        manager.registerAtStartup()
        XCTAssertEqual(manager.registrationAttemptCount, count)
        XCTAssertTrue(manager.hasRegisteredAtStartup)
    }

    func testStartupRegistrationEmitsTelemetry() {
        let manager = GlobalHotkeyManager(userDefaults: defaults)
        manager.isEnabled = true
        let state = testAppState(hotkey: manager)
        MenuBarCoordinator.initialize(appState: state)

        XCTAssertTrue(events.contains("nova_hotkey_register_attempt"))
        XCTAssertTrue(events.contains("nova_menu_bar_ready"))
    }

    func testSummonNotificationDelivery() {
        let expectation = expectation(description: "summon")
        let token = NotificationCenter.default.addObserver(
            forName: .novaHotkeySummon,
            object: nil,
            queue: .main
        ) { _ in expectation.fulfill() }

        NotificationCenter.default.post(name: .novaHotkeySummon, object: nil)
        wait(for: [expectation], timeout: 1.0)
        NotificationCenter.default.removeObserver(token)
    }

    func testCompactChatOpenRequest() {
        let state = testAppState()
        state.handleHotkeySummon()
        XCTAssertTrue(state.isExpanded)
        XCTAssertTrue(state.summonListen)
        XCTAssertTrue(events.contains("nova_hotkey_triggered"))
        XCTAssertTrue(events.contains("nova_compact_chat_opened"))
    }

    func testMenuBarCoordinatorInitializationOnce() {
        let manager = GlobalHotkeyManager(userDefaults: defaults)
        manager.isEnabled = true
        let state = testAppState(hotkey: manager)
        MenuBarCoordinator.initialize(appState: state)
        MenuBarCoordinator.initialize(appState: state)
        XCTAssertEqual(manager.registrationAttemptCount, 1)
    }

    private func testAppState(hotkey: GlobalHotkeyManager? = nil) -> MacAppState {
        let state = MacAppState()
        if let hotkey {
            state.hotkey = hotkey
        }
        return state
    }
}
