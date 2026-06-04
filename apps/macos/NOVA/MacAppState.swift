import Foundation
import Combine
import AVFoundation
import Speech

@MainActor
final class MacAppState: ObservableObject {
    @Published var voiceMode: VoiceMode = .primeOnly
    @Published var isExpanded = false
    @Published var workerHealth: WorkerHealth = .unknown
    @Published var apiBaseURL: String
    @Published var isPaired: Bool
    @Published var globalError: String?

    let api = NOVAAPIClient.shared

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

    init() {
        apiBaseURL = UserDefaults.standard.string(forKey: "api_base_url") ?? "http://localhost:8000"
        isPaired = KeychainStore.load() != nil
        api.baseURL = apiBaseURL
    }

    func updateBaseURL(_ url: String) {
        apiBaseURL = url
        api.baseURL = url
        UserDefaults.standard.set(url, forKey: "api_base_url")
    }

    func refreshPairing() { isPaired = KeychainStore.load() != nil }

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

@MainActor
final class MacSpeechController: ObservableObject {
    @Published var transcript = ""
    @Published var isListening = false
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private let engine = AVAudioEngine()
    private let synthesizer = AVSpeechSynthesizer()

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
