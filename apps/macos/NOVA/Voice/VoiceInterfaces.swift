import Foundation

protocol WakeWordProvider {
    var isListening: Bool { get }
    func start() async throws
    func stop() async
    var onWakeWord: AsyncStream<Void> { get }
}

protocol MacSTTProvider {
    func startListening() async throws
    func stopListening() async
    var transcript: AsyncStream<String> { get }
}

protocol MacTTSProvider {
    func speak(_ text: String, voiceProfileId: String) async throws
    func stop() async
}

final class MockWakeWordProvider: WakeWordProvider {
    var isListening = false
    var onWakeWord: AsyncStream<Void> {
        AsyncStream { $0.finish() }
    }
    func start() async throws { isListening = true }
    func stop() async { isListening = false }
}

final class MockSTTProvider: MacSTTProvider {
    var transcript: AsyncStream<String> {
        AsyncStream { $0.finish() }
    }
    func startListening() async throws {}
    func stopListening() async {}
}

final class MockTTSProvider: MacTTSProvider {
    func speak(_ text: String, voiceProfileId: String) async throws {}
    func stop() async {}
}
