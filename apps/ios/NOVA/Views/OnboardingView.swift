import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject var appState: AppState
    @State private var page = 0

    var body: some View {
        TabView(selection: $page) {
            onboardingPage(
                title: "Meet NOVA",
                subtitle: "Your personal AI operating system",
                page: 0
            )
            onboardingPage(
                title: "Seven Commanders",
                subtitle: "Specialized agents for every domain",
                page: 1
            )
            onboardingPage(
                title: "Mission Room",
                subtitle: "Track missions across all your devices",
                page: 2
            )
        }
        .tabViewStyle(.page)
        .indexViewStyle(.page(backgroundDisplayMode: .always))
    }

    private func onboardingPage(title: String, subtitle: String, page: Int) -> some View {
        VStack(spacing: 32) {
            Spacer()
            NovaOrbView(size: 100)
            Text(title)
                .font(.largeTitle.bold())
            Text(subtitle)
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Spacer()
            if page == 2 {
                Button("Get Started") {
                    appState.completeOnboarding()
                }
                .buttonStyle(.borderedProminent)
                .tint(DesignTokens.novaBlue)
                .padding(.bottom, 40)
            } else {
                Button("Continue") { self.page = page + 1 }
                    .buttonStyle(.borderedProminent)
                    .tint(DesignTokens.novaBlue)
                    .padding(.bottom, 40)
            }
        }
        .padding()
        .tag(page)
    }
}

#Preview {
    OnboardingView()
        .environmentObject(AppState())
}
