import Foundation

protocol STTProvider {
    func startListening() async throws
    func stopListening() async
    var transcript: AsyncStream<String> { get }
}

protocol TTSProvider {
    func speak(_ text: String, voiceProfileId: String) async throws
    func stop() async
}

/// Placeholder STT — Slice 2 will integrate Speech framework
final class PlaceholderSTTProvider: STTProvider {
    var transcript: AsyncStream<String> {
        AsyncStream { continuation in
            continuation.finish()
        }
    }

    func startListening() async throws {}
    func stopListening() async {}
}

/// Placeholder TTS — Slice 2 will integrate AVSpeechSynthesizer
final class PlaceholderTTSProvider: TTSProvider {
    func speak(_ text: String, voiceProfileId: String) async throws {}
    func stop() async {}
}

struct VoiceProfileMetadata {
    let id: String
    let displayName: String
    let description: String
}

enum VoiceProfiles {
    static let all: [VoiceProfileMetadata] = [
        VoiceProfileMetadata(id: "nova_prime", displayName: "NOVA Prime", description: "Warm chief-of-staff voice"),
        VoiceProfileMetadata(id: "mars_engineer", displayName: "MARS Engineer", description: "Direct technical voice"),
    ]
}
