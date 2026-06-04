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
    }

    override func tearDown() {
        NovaHotkeyTelemetry.eventSink = nil
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
        let manager = GlobalHotkeyManager(userDefaults: defaults, forcedRegistrationStatus: noErr)
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
        state.menuBarCoordinator.initialize(appState: state)

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
        XCTAssertTrue(events.contains("nova_compact_chat_created"))
    }

    func testMenuBarCoordinatorInitializationOnce() {
        let manager = GlobalHotkeyManager(userDefaults: defaults)
        manager.isEnabled = true
        let state = testAppState(hotkey: manager)
        state.menuBarCoordinator.initialize(appState: state)
        state.menuBarCoordinator.initialize(appState: state)
        XCTAssertEqual(manager.registrationAttemptCount, 1)
    }

    func testStartupRequestsOneCompactWindow() {
        let window = FakeCompactWindowCoordinator()
        let state = testAppState(compactWindowCoordinator: window)
        state.startApplication()

        XCTAssertEqual(state.menuBarCoordinator.startupWindowRequestCount, 1)
        XCTAssertEqual(window.openCount, 1)
        XCTAssertTrue(events.contains("nova_app_started"))
        XCTAssertTrue(events.contains("nova_initial_window_open_requested"))
    }

    func testRepeatedOpenRequestsFocusExistingWindow() {
        let window = FakeCompactWindowCoordinator()
        let state = testAppState(compactWindowCoordinator: window)

        state.openCompactChat()
        state.openCompactChat()
        state.openCompactChat()

        XCTAssertEqual(window.createCount, 1)
        XCTAssertEqual(window.openCount, 3)
        XCTAssertEqual(window.focusCount, 2)
        XCTAssertTrue(events.contains("nova_compact_chat_focused"))
    }

    func testNoDuplicateCompactWindows() {
        let window = FakeCompactWindowCoordinator()
        let state = testAppState(compactWindowCoordinator: window)

        state.startApplication()
        state.openCompactChat()
        state.handleHotkeySummon()

        XCTAssertEqual(window.createCount, 1)
    }

    func testMenuBarCoordinatorRetained() {
        let state = testAppState()
        state.menuBarCoordinator.initialize(appState: state)

        XCTAssertEqual(state.menuBarCoordinator.readinessCount, 1)
        XCTAssertEqual(state.menuBarCoordinator.startupWindowRequestCount, 1)
    }

    func testMenuBarMenuIncludesRequiredCommands() {
        XCTAssertEqual(MenuBarRootView.commandTitles, ["Open NOVA", "Pair Device", "Settings", "Quit NOVA"])
    }

    func testUnpairedStateOpensPairingView() {
        let window = FakeCompactWindowCoordinator()
        let state = testAppState(compactWindowCoordinator: window)
        state.isPaired = false

        state.requestInitialWindowOpen()

        XCTAssertEqual(window.lastMode, .pairing)
        XCTAssertTrue(state.shouldShowPairing)
    }

    func testHotkeyRegistrationFailureDoesNotBlockStartupWindow() {
        let manager = GlobalHotkeyManager(userDefaults: defaults, forcedRegistrationStatus: Int32(eventHotKeyExistsErr))
        let window = FakeCompactWindowCoordinator()
        let state = testAppState(hotkey: manager, compactWindowCoordinator: window)

        state.startApplication()

        XCTAssertEqual(window.openCount, 1)
        XCTAssertTrue(events.contains("nova_hotkey_registration_failed"))
        XCTAssertTrue(events.contains("nova_initial_window_open_requested"))
    }

    func testHotkeyRegistrationFailureDoesNotBlockMenuBarReadiness() {
        let manager = GlobalHotkeyManager(userDefaults: defaults, forcedRegistrationStatus: Int32(eventHotKeyExistsErr))
        let state = testAppState(hotkey: manager)

        state.startApplication()

        XCTAssertEqual(state.menuBarCoordinator.readinessCount, 1)
        XCTAssertTrue(events.contains("nova_menu_bar_ready"))
        XCTAssertNotNil(manager.registrationError)
    }

    func testHotkeyTriggerRequestsCompactWindowFocus() {
        let window = FakeCompactWindowCoordinator()
        let state = testAppState(compactWindowCoordinator: window)

        state.openCompactChat()
        state.handleHotkeySummon()

        XCTAssertEqual(window.focusCount, 1)
        XCTAssertTrue(state.summonListen)
        XCTAssertTrue(events.contains("nova_hotkey_triggered"))
    }

    func testTelemetryCallsOccurForStartupOpenFocusAndFailurePaths() {
        let manager = GlobalHotkeyManager(userDefaults: defaults, forcedRegistrationStatus: Int32(eventHotKeyExistsErr))
        let window = FakeCompactWindowCoordinator()
        let state = testAppState(hotkey: manager, compactWindowCoordinator: window)

        state.startApplication()
        state.openCompactChat()

        XCTAssertTrue(events.contains("nova_app_started"))
        XCTAssertTrue(events.contains("nova_menu_bar_ready"))
        XCTAssertTrue(events.contains("nova_initial_window_open_requested"))
        XCTAssertTrue(events.contains("nova_compact_chat_created"))
        XCTAssertTrue(events.contains("nova_compact_chat_focused"))
        XCTAssertTrue(events.contains("nova_hotkey_register_attempt"))
        XCTAssertTrue(events.contains("nova_hotkey_registration_failed"))
    }

    private func isolatedUserDefaults() -> UserDefaults {
        let suiteName = "NOVAGenieTests.State.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)
        return defaults
    }

    private func testAppState(
        hotkey: GlobalHotkeyManager? = nil,
        compactWindowCoordinator: CompactWindowCoordinating? = nil
    ) -> MacAppState {
        let defaults = isolatedUserDefaults()
        let state = MacAppState(
            compactWindowCoordinator: compactWindowCoordinator ?? FakeCompactWindowCoordinator(),
            userDefaults: defaults,
            keychainService: "com.nova.macos.tests.\(UUID().uuidString)"
        )
        if let hotkey {
            state.hotkey = hotkey
        }
        return state
    }
}

@MainActor
private final class FakeCompactWindowCoordinator: CompactWindowCoordinating {
    let stableWindowIdentifier = "com.nova.macos.genie.compact.test"
    private(set) var createCount = 0
    private(set) var openCount = 0
    private(set) var focusCount = 0
    private(set) var lastMode: MacAppState.CompactWindowMode?

    func open(appState: MacAppState, mode: MacAppState.CompactWindowMode) {
        appState.compactWindowMode = mode
        lastMode = mode
        if createCount == 0 {
            createCount = 1
            NovaHotkeyTelemetry.emit("nova_compact_chat_created")
            NovaHotkeyTelemetry.emit("nova_compact_chat_opened")
        } else {
            focusCount += 1
            NovaHotkeyTelemetry.emit("nova_compact_chat_focused")
        }
        openCount += 1
    }
}
