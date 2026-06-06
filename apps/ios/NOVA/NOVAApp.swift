import SwiftUI

@main
struct NOVAApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            if !appState.isPaired {
                NavigationStack { PairingView() }
                    .environmentObject(appState)
            } else if appState.hasCompletedOnboarding {
                MainTabView()
                    .environmentObject(appState)
            } else {
                OnboardingView()
                    .environmentObject(appState)
            }
        }
    }
}
