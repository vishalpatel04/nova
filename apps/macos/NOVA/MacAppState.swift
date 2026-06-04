import AppKit
import Foundation
import Combine
import AVFoundation
import Speech
import SQLite3

@MainActor
final class MacAppState: ObservableObject {
    enum CompactWindowMode: Equatable {
        case chat
        case pairing
    }

    @Published var voiceMode: VoiceMode = .primeOnly
    @Published var isExpanded = false
    @Published var workerHealth: WorkerHealth = .unknown
    @Published var apiBaseURL: String
    @Published var isPaired: Bool
    @Published var globalError: String?
    @Published var compactWindowMode: CompactWindowMode = .chat
    @Published var chatMessages: [ChatMessage] = []
    @Published var chatDraft = ""
    @Published var isChatSending = false
    @Published var chatError: String?
    @Published var activeChatSessionId: String?

    let api = NOVAAPIClient.shared
    @Published var hotkey = GlobalHotkeyManager()
    @Published var summonListen = false
    @Published private(set) var pairedDeviceId: String?
    let compactWindowCoordinator: CompactWindowCoordinating
    let menuBarCoordinator: MenuBarCoordinator
    private let userDefaults: UserDefaults
    private let keychainService: String
    private let legacyKeychainService: String
    private let chatStore = LocalChatStore()

    enum VoiceMode: String, CaseIterable {
        case primeOnly = "prime_only"
        case warRoom = "war_room"
        case silentOperations = "silent_operations"
        case briefing = "briefing"

        var displayName: String {
            switch self {
            case .primeOnly: return "Prime Only"
            case .warRoom: return "War Room"
            case .silentOperations: return "Silent Ops"
            case .briefing: return "Briefing"
            }
        }
    }

    enum WorkerHealth {
        case unknown, healthy, degraded, offline

        var label: String {
            switch self {
            case .unknown: return "Unknown"
            case .healthy: return "Online"
            case .degraded: return "Stale"
            case .offline: return "Offline"
            }
        }
    }

    var shouldShowPairing: Bool {
        compactWindowMode == .pairing || !isPaired
    }

    init(
        compactWindowCoordinator: CompactWindowCoordinating? = nil,
        menuBarCoordinator: MenuBarCoordinator? = nil,
        userDefaults: UserDefaults = .standard,
        keychainService: String = NovaDeviceIdentity.productionService,
        legacyKeychainService: String = NovaDeviceIdentity.legacyService
    ) {
        self.compactWindowCoordinator = compactWindowCoordinator ?? CompactWindowCoordinator()
        self.menuBarCoordinator = menuBarCoordinator ?? MenuBarCoordinator()
        self.userDefaults = userDefaults
        self.keychainService = keychainService
        self.legacyKeychainService = legacyKeychainService
        apiBaseURL = userDefaults.string(forKey: "api_base_url") ?? "http://localhost:8000"
        isPaired = false
        api.baseURL = apiBaseURL
        bootstrapAuthFromKeychain()
        restoreLocalChat()
        NotificationCenter.default.addObserver(
            forName: .novaHotkeySummon,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.handleHotkeySummon()
            }
        }
    }

    func handleHotkeySummon() {
        NovaHotkeyTelemetry.emit("nova_hotkey_triggered")
        openCompactChat(listenAfterOpen: true)
    }

    func startApplication() {
        NovaHotkeyTelemetry.emit("nova_app_started")
        bootstrapAuthFromKeychain()
        menuBarCoordinator.initialize(appState: self)
    }

    func bootstrapAuthFromKeychain() {
        let lookup = NovaAuthBootstrap.lookupToken(
            userDefaults: userDefaults,
            keychainService: keychainService,
            legacyService: legacyKeychainService
        )
        applyAuthLookup(lookup)
    }

    private func applyAuthLookup(_ lookup: KeychainTokenLookup) {
        if lookup.token != nil {
            pairedDeviceId = lookup.deviceId ?? lookup.keychainAccount
            isPaired = true
            compactWindowMode = .chat
            NovaHotkeyTelemetry.emit("nova_auth_state_authenticated")
        } else {
            pairedDeviceId = lookup.deviceId
            isPaired = false
        }
    }

    func requestInitialWindowOpen() {
        NovaHotkeyTelemetry.emit("nova_initial_window_open_requested")
        openCompactChat(mode: isPaired ? .chat : .pairing)
    }

    func openCompactChat(
        listenAfterOpen: Bool = false,
        mode: CompactWindowMode? = nil
    ) {
        isExpanded = true
        let targetMode = mode ?? (isPaired ? .chat : .pairing)
        compactWindowCoordinator.open(appState: self, mode: targetMode)
        if listenAfterOpen {
            summonListen = true
        }
    }

    func openPairingWindow() {
        openCompactChat(mode: .pairing)
    }

    func updateBaseURL(_ url: String) {
        apiBaseURL = url
        api.baseURL = url
        UserDefaults.standard.set(url, forKey: "api_base_url")
    }

    func refreshPairing() {
        bootstrapAuthFromKeychain()
    }

    func sendChatMessage(_ text: String) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        guard isPaired else {
            chatError = "Pair this device before chatting with NOVA."
            return
        }
        chatError = nil
        let userMessage = ChatMessage(role: .user, content: trimmed)
        chatMessages.append(userMessage)
        chatStore.save(messages: chatMessages, sessionId: activeChatSessionId)
        isChatSending = true
        defer { isChatSending = false }
        do {
            let response = try await api.sendChat(message: trimmed, sessionId: activeChatSessionId)
            activeChatSessionId = response.sessionId ?? activeChatSessionId
            let role: ChatMessage.Role = response.blocked ? .error : .assistant
            chatMessages.append(
                ChatMessage(role: role, content: response.response, blocked: response.blocked)
            )
            chatStore.save(messages: chatMessages, sessionId: activeChatSessionId)
            if response.blocked {
                chatError = response.response
            }
        } catch {
            chatError = error.localizedDescription
            chatMessages.append(ChatMessage(role: .error, content: error.localizedDescription))
            chatStore.save(messages: chatMessages, sessionId: activeChatSessionId)
        }
    }

    func restoreLocalChat() {
        let snapshot = chatStore.load()
        activeChatSessionId = snapshot.sessionId
        chatMessages = snapshot.messages
    }

    func pollWorkerHealth() async {
        guard isPaired else { workerHealth = .unknown; return }
        do {
            let status = try await api.fetchSystemStatus()
            if status.workersOnline > 0 && status.hasEligibleOnlineWorker {
                workerHealth = .healthy
            } else if status.workersStale > 0 {
                workerHealth = .degraded
            } else {
                workerHealth = .offline
            }
        } catch {
            workerHealth = .unknown
            globalError = error.localizedDescription
        }
    }
}

struct LocalChatSnapshot {
    let sessionId: String?
    let messages: [ChatMessage]
}

final class LocalChatStore {
    private let dbPath: String

    init(filename: String = "NOVAChat.sqlite") {
        let base = FileManager.default.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first ?? URL(fileURLWithPath: NSTemporaryDirectory())
        let dir = base.appendingPathComponent("NOVA", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        dbPath = dir.appendingPathComponent(filename).path
        initialize()
    }

    func save(messages: [ChatMessage], sessionId: String?) {
        guard let db = open() else { return }
        defer { sqlite3_close(db) }
        let data = (try? JSONEncoder().encode(messages)) ?? Data()
        let sql = """
        INSERT OR REPLACE INTO chat_snapshots (id, session_id, payload, updated_at)
        VALUES ('active', ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
        """
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(statement) }
        if let sessionId {
            sqlite3_bind_text(statement, 1, sessionId, -1, SQLITE_TRANSIENT)
        } else {
            sqlite3_bind_null(statement, 1)
        }
        data.withUnsafeBytes { buffer in
            _ = sqlite3_bind_blob(statement, 2, buffer.baseAddress, Int32(data.count), SQLITE_TRANSIENT)
        }
        sqlite3_step(statement)
    }

    func load() -> LocalChatSnapshot {
        guard let db = open() else { return LocalChatSnapshot(sessionId: nil, messages: []) }
        defer { sqlite3_close(db) }
        let sql = "SELECT session_id, payload FROM chat_snapshots WHERE id = 'active' LIMIT 1;"
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else {
            return LocalChatSnapshot(sessionId: nil, messages: [])
        }
        defer { sqlite3_finalize(statement) }
        guard sqlite3_step(statement) == SQLITE_ROW else {
            return LocalChatSnapshot(sessionId: nil, messages: [])
        }
        let sessionId = sqlite3_column_text(statement, 0).map { String(cString: $0) }
        let bytes = sqlite3_column_blob(statement, 1)
        let count = Int(sqlite3_column_bytes(statement, 1))
        guard let bytes, count > 0 else {
            return LocalChatSnapshot(sessionId: sessionId, messages: [])
        }
        let data = Data(bytes: bytes, count: count)
        let messages = (try? JSONDecoder().decode([ChatMessage].self, from: data)) ?? []
        return LocalChatSnapshot(sessionId: sessionId, messages: messages)
    }

    private func initialize() {
        guard let db = open() else { return }
        defer { sqlite3_close(db) }
        sqlite3_exec(
            db,
            """
            CREATE TABLE IF NOT EXISTS chat_snapshots (
              id TEXT PRIMARY KEY,
              session_id TEXT,
              payload BLOB NOT NULL,
              updated_at TEXT NOT NULL
            );
            """,
            nil,
            nil,
            nil
        )
    }

    private func open() -> OpaquePointer? {
        var db: OpaquePointer?
        guard sqlite3_open(dbPath, &db) == SQLITE_OK else { return nil }
        return db
    }
}

private let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

@MainActor
final class MacSpeechController: ObservableObject {
    @Published var transcript = ""
    @Published var isListening = false
    @Published var permissionGranted = false
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private let engine = AVAudioEngine()
    private let synthesizer = AVSpeechSynthesizer()

    func requestPermissions() async -> Bool {
        let speechStatus = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { status in
                continuation.resume(returning: status == .authorized)
            }
        }
        let micStatus = await AVCaptureDevice.requestAccess(for: .audio)
        permissionGranted = speechStatus && micStatus
        return permissionGranted
    }

    func speak(_ text: String, mode: MacAppState.VoiceMode) {
        guard mode != .silentOperations else { return }
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
        synthesizer.speak(utterance)
    }

    func toggleListening() throws {
        if isListening { stop(); return }
        request = SFSpeechAudioBufferRecognitionRequest()
        guard let request, let recognizer, recognizer.isAvailable else { return }
        let input = engine.inputNode
        input.installTap(onBus: 0, bufferSize: 1024, format: input.outputFormat(forBus: 0)) { buffer, _ in
            request.append(buffer)
        }
        engine.prepare()
        try engine.start()
        isListening = true
        task = recognizer.recognitionTask(with: request) { [weak self] result, _ in
            Task { @MainActor in
                if let result { self?.transcript = result.bestTranscription.formattedString }
                if result?.isFinal == true { self?.stop() }
            }
        }
    }

    func stop() {
        task?.cancel()
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        isListening = false
    }
}
