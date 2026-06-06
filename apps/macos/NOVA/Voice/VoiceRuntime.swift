import Foundation

@MainActor
final class VoiceRuntime: ObservableObject {
    enum Phase: Equatable {
        case idle
        case recording
        case transcribing
        case speaking
    }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var liveTranscript = ""
    @Published private(set) var permissionGranted = false

    private let stt: MacSTTProvider
    private let tts: MacTTSProvider
    private var transcriptTask: Task<Void, Never>?

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
        guard phase == .idle else { return }
        liveTranscript = ""
        phase = .recording
        transcriptTask?.cancel()
        transcriptTask = Task {
            for await text in stt.transcript {
                liveTranscript = text
            }
        }
        try await stt.startListening()
    }

    func cancelRecording() async {
        transcriptTask?.cancel()
        await stt.stopListening()
        liveTranscript = ""
        phase = .idle
    }

    func finishPushToTalk() async -> String {
        await stt.stopListening()
        transcriptTask?.cancel()
        phase = .idle
        let text = liveTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
        liveTranscript = ""
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
}
