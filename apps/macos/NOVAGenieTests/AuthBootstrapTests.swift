import XCTest
@testable import NOVAGenie

@MainActor
final class AuthBootstrapTests: XCTestCase {
    private var defaults: UserDefaults!
    private var keychainService: String!
    private var events: [String] = []

    override func setUp() {
        super.setUp()
        let suiteName = "NOVAGenieTests.Auth.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)
        keychainService = "com.nova.macos.tests.\(UUID().uuidString)"
        events = []
        NovaHotkeyTelemetry.eventSink = { [weak self] event in
            self?.events.append(event)
        }
    }

    override func tearDown() {
        NovaHotkeyTelemetry.eventSink = nil
        if let deviceId = defaults.string(forKey: NovaDeviceIdentity.deviceIdDefaultsKey) {
            KeychainStore.delete(account: deviceId, service: keychainService)
        }
        KeychainStore.delete(
            account: NovaDeviceIdentity.legacyAccount,
            service: NovaDeviceIdentity.legacyService
        )
        super.tearDown()
    }

    func testLookupUsesProductionServiceAndDeviceAccount() {
        defaults.set("arth-mac-client", forKey: NovaDeviceIdentity.deviceIdDefaultsKey)
        try? KeychainStore.save(token: "nova-test-token", account: "arth-mac-client", service: keychainService)

        let lookup = NovaAuthBootstrap.lookupToken(
            userDefaults: defaults,
            keychainService: keychainService
        )

        XCTAssertEqual(lookup.token, "nova-test-token")
        XCTAssertEqual(lookup.keychainAccount, "arth-mac-client")
        XCTAssertEqual(lookup.source, "primary")
        XCTAssertTrue(events.contains("nova_token_lookup_started"))
        XCTAssertTrue(events.contains("nova_token_lookup_success"))
    }

    func testDiscoversManualKeychainEntryWithoutPersistedDeviceId() throws {
        try KeychainStore.save(token: "manual-token", account: "arth-mac-client", service: keychainService)

        let lookup = NovaAuthBootstrap.lookupToken(
            userDefaults: defaults,
            keychainService: keychainService
        )

        XCTAssertEqual(lookup.token, "manual-token")
        XCTAssertEqual(lookup.source, "discovered")
        XCTAssertEqual(defaults.string(forKey: NovaDeviceIdentity.deviceIdDefaultsKey), "arth-mac-client")
    }

    func testMigratesLegacyGenieCredentials() throws {
        try KeychainStore.save(
            token: "legacy-token",
            account: NovaDeviceIdentity.legacyAccount,
            service: NovaDeviceIdentity.legacyService
        )

        let lookup = NovaAuthBootstrap.lookupToken(userDefaults: defaults, keychainService: keychainService)

        XCTAssertEqual(lookup.token, "legacy-token")
        XCTAssertEqual(lookup.source, "legacy")
    }

    func testAppLaunchesAuthenticatedWhenTokenPresent() throws {
        defaults.set("arth-mac-client", forKey: NovaDeviceIdentity.deviceIdDefaultsKey)
        try KeychainStore.save(token: "boot-token", account: "arth-mac-client", service: keychainService)

        let window = FakeAuthCompactWindowCoordinator()
        let state = MacAppState(
            compactWindowCoordinator: window,
            userDefaults: defaults,
            keychainService: keychainService
        )

        XCTAssertTrue(state.isPaired)
        XCTAssertEqual(state.compactWindowMode, .chat)
        XCTAssertFalse(state.shouldShowPairing)
        XCTAssertTrue(events.contains("nova_auth_state_authenticated"))

        state.requestInitialWindowOpen()
        XCTAssertEqual(window.lastMode, .chat)
    }

    func testFailedLookupLeavesAppUnpaired() {
        let lookup = NovaAuthBootstrap.lookupToken(
            userDefaults: defaults,
            keychainService: keychainService
        )

        XCTAssertNil(lookup.token)
        XCTAssertTrue(events.contains("nova_token_lookup_failed"))
        XCTAssertTrue(
            events.contains {
                $0.contains("nova_auth_diagnostic") && $0.contains("token_exists=false")
            }
        )
    }
}

@MainActor
private final class FakeAuthCompactWindowCoordinator: CompactWindowCoordinating {
    let stableWindowIdentifier = "com.nova.macos.genie.compact.auth.test"
    private(set) var createCount = 0
    private(set) var openCount = 0
    private(set) var focusCount = 0
    private(set) var lastMode: MacAppState.CompactWindowMode?

    func open(appState: MacAppState, mode: MacAppState.CompactWindowMode) {
        appState.compactWindowMode = mode
        lastMode = mode
        createCount += 1
        openCount += 1
    }
}
