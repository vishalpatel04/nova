import Foundation
import Combine

final class AppState: ObservableObject {
    @Published var hasCompletedOnboarding: Bool
    @Published var apiBaseURL: String
    @Published var microphonePermission: MicrophonePermission = .notDetermined

    init() {
        hasCompletedOnboarding = UserDefaults.standard.bool(forKey: "onboarding_complete")
        apiBaseURL = UserDefaults.standard.string(forKey: "api_base_url") ?? "http://localhost:8000"
    }

    func completeOnboarding() {
        hasCompletedOnboarding = true
        UserDefaults.standard.set(true, forKey: "onboarding_complete")
    }
}

enum MicrophonePermission {
    case notDetermined
    case denied
    case authorized
}
