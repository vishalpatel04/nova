import XCTest
@testable import NOVAGenie

@MainActor
final class GenieChatStateTests: XCTestCase {
    private var defaults: UserDefaults!

    override func setUp() {
        super.setUp()
        let suiteName = "NOVAGenieTests.Chat.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)
    }

    func testChatMessageModelRoles() {
        let user = ChatMessage(role: .user, content: "hello")
        let assistant = ChatMessage(role: .assistant, content: "hi")
        let error = ChatMessage(role: .error, content: "blocked", blocked: true)
        XCTAssertEqual(user.role, .user)
        XCTAssertEqual(assistant.role, .assistant)
        XCTAssertTrue(error.blocked)
    }

    func testAuthenticatedLaunchShowsChatNotPairing() throws {
        defaults.set("arth-mac-client", forKey: NovaDeviceIdentity.deviceIdDefaultsKey)
        let service = "com.nova.macos.tests.\(UUID().uuidString)"
        try KeychainStore.save(token: "token", account: "arth-mac-client", service: service)

        let state = MacAppState(userDefaults: defaults, keychainService: service)
        XCTAssertTrue(state.isPaired)
        XCTAssertFalse(state.shouldShowPairing)
        XCTAssertEqual(state.compactWindowMode, .chat)
    }

    func testDoneEventCarriesActiveProject() {
        let event = ChatStreamEvent(
            kind: .done(
                intent: "set_project",
                blocked: false,
                sessionId: "sess-1",
                activeProject: "nova",
                pendingToolIntent: nil
            )
        )
        if case .done(let intent, _, _, let activeProject, _) = event.kind {
            XCTAssertEqual(intent, "set_project")
            XCTAssertEqual(activeProject, "nova")
        } else {
            XCTFail("expected done event")
        }
    }
}

final class NovaProviderKeychainTests: XCTestCase {
    override func tearDown() {
        NovaProviderSettings.deleteAPIKey(provider: .openai)
        super.tearDown()
    }

    func testProviderKeyStoredAndMasked() throws {
        try NovaProviderSettings.saveAPIKey("sk-test-secret", provider: .openai)
        XCTAssertEqual(NovaProviderSettings.maskedKeyStatus(provider: .openai), "••••••••")
        XCTAssertTrue(NovaProviderSettings.isConfigured(provider: .openai))
    }

    func testPreferFreeLocalDefaultsOn() {
        UserDefaults.standard.removeObject(forKey: NovaProviderSettings.preferFreeLocalKey)
        XCTAssertTrue(NovaProviderSettings.preferFreeLocal)
    }
}
