import Foundation
import AVFoundation
import Speech

@MainActor
final class AVFoundationVoiceAdapter: MacSTTProvider, MacTTSProvider {
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private let engine = AVAudioEngine()
    private let synthesizer = AVSpeechSynthesizer()
    private var transcriptContinuation: AsyncStream<String>.Continuation?
    private(set) var isListening = false

    var transcript: AsyncStream<String> {
        AsyncStream { continuation in
            transcriptContinuation = continuation
        }
    }

    func requestPermissions() async -> Bool {
        let speechStatus = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { status in
                continuation.resume(returning: status == .authorized)
            }
        }
        let micStatus = await AVCaptureDevice.requestAccess(for: .audio)
        return speechStatus && micStatus
    }

    func startListening() async throws {
        guard !isListening else { return }
        request = SFSpeechAudioBufferRecognitionRequest()
        guard let request, let recognizer, recognizer.isAvailable else {
            throw VoiceRuntimeError.recognizerUnavailable
        }
        let input = engine.inputNode
        input.installTap(onBus: 0, bufferSize: 1024, format: input.outputFormat(forBus: 0)) { buffer, _ in
            request.append(buffer)
        }
        engine.prepare()
        try engine.start()
        isListening = true
        task = recognizer.recognitionTask(with: request) { [weak self] result, _ in
            Task { @MainActor in
                guard let self else { return }
                if let result {
                    self.transcriptContinuation?.yield(result.bestTranscription.formattedString)
                }
                if result?.isFinal == true {
                    await self.stopListening()
                }
            }
        }
    }

    func stopListening() async {
        task?.cancel()
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        isListening = false
        request = nil
        task = nil
    }

    func speak(_ text: String, voiceProfileId: String) async throws {
        stopSpeaking()
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: voiceProfileId.isEmpty ? "en-US" : voiceProfileId)
        synthesizer.speak(utterance)
    }

    func stop() async {
        await stopListening()
        stopSpeaking()
    }

    private func stopSpeaking() {
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }
    }
}

enum VoiceRuntimeError: LocalizedError {
    case recognizerUnavailable
    case permissionDenied

    var errorDescription: String? {
        switch self {
        case .recognizerUnavailable: return "Speech recognizer unavailable."
        case .permissionDenied: return "Microphone or speech permission denied."
        }
    }
}
