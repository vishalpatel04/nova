import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            NavigationStack { HomeView() }
                .tabItem { Label("NOVA", systemImage: "circle.hexagongrid.fill") }

            NavigationStack { ChatView() }
                .tabItem { Label("Chat", systemImage: "bubble.left.fill") }

            NavigationStack { MissionRoomView() }
                .tabItem { Label("Missions", systemImage: "list.bullet.rectangle") }

            NavigationStack { AgentsView() }
                .tabItem { Label("Agents", systemImage: "person.3.fill") }

            NavigationStack {
                List {
                    NavigationLink("Devices") { DevicesView() }
                    NavigationLink("Pairing") { PairingView() }
                    NavigationLink("Settings") { SettingsView() }
                }
                .navigationTitle("More")
            }
            .tabItem { Label("More", systemImage: "ellipsis.circle") }
        }
        .tint(DesignTokens.novaBlue)
    }
}

#Preview {
    MainTabView()
        .environmentObject(AppState())
}
