import Foundation

@MainActor
final class VoiceRuntime: ObservableObject {
    enum Phase: Equatable {
        case idle
        case wakeListening
        case recording
        case transcribing
        case speaking

        var isWakeListening: Bool {
            if case .wakeListening = self { return true }
            return false
        }

        var isRecording: Bool {
            if case .recording = self { return true }
            return false
        }
    }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var liveTranscript = ""
    @Published private(set) var permissionGranted = false

    private let stt: MacSTTProvider
    private let tts: MacTTSProvider
    private var transcriptTask: Task<Void, Never>?
    private var wakeDetected = false
    private var wakeWordEnabled = false

    init(stt: MacSTTProvider? = nil, tts: MacTTSProvider? = nil) {
        let adapter = AVFoundationVoiceAdapter()
        self.stt = stt ?? adapter
        self.tts = tts ?? adapter
    }

    func preparePermissions() async -> Bool {
        if let adapter = stt as? AVFoundationVoiceAdapter {
            permissionGranted = await adapter.requestPermissions()
            return permissionGranted
        }
        permissionGranted = true
        return true
    }

    func startPushToTalk() async throws {
        if phase == .wakeListening {
            wakeDetected = true
            phase = .recording
            return
        }
        guard phase == .idle else { return }
        try await stt.startListening()
        startTranscriptLoop(wakeMode: false)
        phase = .recording
    }

    func startWakeListening() async throws {
        guard phase == .idle else { return }
        guard supportsWakeWord else { return }
        wakeWordEnabled = true
        wakeDetected = false
        try await stt.startListening()
        startTranscriptLoop(wakeMode: true)
        phase = .wakeListening
    }

    func cancelRecording() async {
        transcriptTask?.cancel()
        await stt.stopListening()
        liveTranscript = ""
        phase = .idle
        wakeDetected = false
    }

    func finishPushToTalk() async -> String {
        phase = .transcribing
        await stt.stopListening()
        transcriptTask?.cancel()
        phase = .idle
        let text = liveTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
        liveTranscript = ""
        wakeDetected = false
        return text
    }

    func speak(_ text: String, voiceProfileId: String = "en-US") async {
        guard !text.isEmpty else { return }
        phase = .speaking
        try? await tts.speak(text, voiceProfileId: voiceProfileId)
        phase = .idle
    }

    func interruptPlayback() async {
        await tts.stop()
        if phase == .speaking {
            phase = .idle
        }
    }

    var isRecording: Bool { phase == .recording }
    var isSpeaking: Bool { phase == .speaking }
    var isWakeListening: Bool { phase == .wakeListening }
    var supportsWakeWord: Bool {
        (stt as? AVFoundationVoiceAdapter)?.supportsOnDeviceRecognition == true
    }

    func stopWakeListening() async {
        if phase == .wakeListening {
            await cancelRecording()
        }
    }

    private func startTranscriptLoop(wakeMode: Bool) {
        liveTranscript = ""
        transcriptTask?.cancel()
        transcriptTask = Task {
            for await text in stt.transcript {
                if Task.isCancelled { break }
                if wakeMode, !wakeDetected {
                    let sanitized = Self.stripWakePhrase(from: text)
                    if sanitized.detected {
                        wakeDetected = true
                        phase = .recording
                        liveTranscript = sanitized.remainder
                    } else {
                        phase = .wakeListening
                        liveTranscript = ""
                    }
                } else {
                    liveTranscript = text
                }
                if wakeDetected && wakeMode {
                    phase = .recording
                }
            }
        }
    }

    private static func stripWakePhrase(from text: String) -> (detected: Bool, remainder: String) {
        let normalized = text
            .lowercased()
            .replacingOccurrences(of: "hey nova", with: " ")
            .replacingOccurrences(of: "okay nova", with: " ")
            .replacingOccurrences(of: "nova", with: " ")
            .replacingOccurrences(of: "  ", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let lower = text.lowercased()
        let detected = lower.contains("hey nova") || lower.contains("okay nova") || lower.contains("nova")
        return (detected, detected ? normalized : text)
    }
}
