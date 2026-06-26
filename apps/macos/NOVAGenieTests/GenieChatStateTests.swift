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

    func testVoiceDefaultsAreSafe() {
        let state = MacAppState(userDefaults: defaults)
        XCTAssertTrue(state.voiceInputEnabled)
        XCTAssertFalse(state.voiceWakeWordEnabled)
        XCTAssertFalse(state.voiceKillSwitch)
        XCTAssertTrue(state.voiceStopListeningOnClose)
    }

    func testNewChatClearsConversation() {
        let state = MacAppState(userDefaults: defaults)
        state.chatDraft = "hello"
        state.chatMessages = [ChatMessage(role: .assistant, content: "hi")]
        state.pendingToolIntent = "personal_search_scope_confirmation"
        state.startNewChat()
        XCTAssertNil(state.activeChatSessionId)
        XCTAssertTrue(state.chatMessages.isEmpty)
        XCTAssertEqual(state.chatDraft, "")
        XCTAssertNil(state.pendingToolIntent)
    }

    func testProviderBadgeReflectsRuntimeMode() {
        let state = MacAppState(userDefaults: defaults)
        state.runtimeMode = "degraded_rule_based"
        state.fallbackReason = "provider_unreachable"
        state.updateProviderBadge()
        XCTAssertEqual(state.providerBadge, "degraded · local unavailable")
    }

    func testDoneEventCarriesActiveProject() {
        let event = ChatStreamEvent(
            kind: .done(
                response: "hello",
                intent: "set_project",
                blocked: false,
                sessionId: "sess-1",
                activeProject: "nova",
                pendingToolIntent: nil,
                runtimeMode: "local_ollama",
                selectedProvider: "local",
                selectedModel: "qwen2.5:7b",
                fallbackReason: nil,
                localAvailable: true,
                agentOSMission: nil,
                orbitEmailDraft: nil
            )
        )
        if case .done(
            let response,
            let intent,
            _,
            _,
            let activeProject,
            _,
            let runtimeMode,
            _,
            _,
            _,
            let localAvailable,
            _,
            _
        ) = event.kind {
            XCTAssertEqual(response, "hello")
            XCTAssertEqual(intent, "set_project")
            XCTAssertEqual(activeProject, "nova")
            XCTAssertEqual(runtimeMode, "local_ollama")
            XCTAssertTrue(localAvailable ?? false)
        } else {
            XCTFail("expected done event")
        }
    }

    func testCompactWindowDefaultSize() {
        XCTAssertEqual(CompactWindowCoordinator.defaultWidth, 920)
        XCTAssertEqual(CompactWindowCoordinator.defaultHeight, 760)
        XCTAssertEqual(CompactWindowCoordinator.minimumWidth, 720)
        XCTAssertEqual(CompactWindowCoordinator.minimumHeight, 560)
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
