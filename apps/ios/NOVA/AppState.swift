import Foundation
import Combine
import AVFoundation
import Speech

@MainActor
final class AppState: ObservableObject {
    @Published var hasCompletedOnboarding: Bool
    @Published var apiBaseURL: String
    @Published var microphonePermission: MicrophonePermission = .notDetermined
    @Published var speechPermission: SpeechPermission = .notDetermined
    @Published var isPaired: Bool
    @Published var isLoading = false
    @Published var globalError: String?
    @Published var activeChatSessionId: String?
    @Published var companionTargetDeviceId: String?

    let api = NOVAAPIClient.shared

    var pairedDeviceId: String? { NovaDeviceIdentity.resolvedDeviceId() }

    init() {
        hasCompletedOnboarding = UserDefaults.standard.bool(forKey: "onboarding_complete")
        apiBaseURL = UserDefaults.standard.string(forKey: "api_base_url") ?? "http://localhost:8000"
        isPaired = KeychainStore.loadResolved() != nil
        companionTargetDeviceId = UserDefaults.standard.string(forKey: "companion_target_device_id")
        api.baseURL = apiBaseURL
    }

    func completeOnboarding() {
        hasCompletedOnboarding = true
        UserDefaults.standard.set(true, forKey: "onboarding_complete")
    }

    func updateBaseURL(_ url: String) {
        apiBaseURL = url
        api.baseURL = url
        UserDefaults.standard.set(url, forKey: "api_base_url")
    }

    func refreshPairingState() {
        isPaired = KeychainStore.loadResolved() != nil
        if isPaired {
            Task { await restoreLatestSession() }
        }
    }

    func setCompanionTargetDeviceId(_ deviceId: String) {
        companionTargetDeviceId = deviceId
        UserDefaults.standard.set(deviceId, forKey: "companion_target_device_id")
    }

    func restoreLatestSession() async {
        guard isPaired else { return }
        do {
            let session = try await api.fetchLatestChatSession()
            activeChatSessionId = session.id
        } catch {
            // No backend session yet.
        }
    }

    func requestMicrophonePermission() async {
        let session = AVAudioSession.sharedInstance()
        let granted = await withCheckedContinuation { cont in
            session.requestRecordPermission { cont.resume(returning: $0) }
        }
        microphonePermission = granted ? .authorized : .denied
    }

    func requestSpeechPermission() async {
        let status = await withCheckedContinuation { cont in
            SFSpeechRecognizer.requestAuthorization { cont.resume(returning: $0) }
        }
        switch status {
        case .authorized: speechPermission = .authorized
        case .denied, .restricted: speechPermission = .denied
        default: speechPermission = .notDetermined
        }
    }
}

enum MicrophonePermission {
    case notDetermined, denied, authorized
}

enum SpeechPermission {
    case notDetermined, denied, authorized
}
