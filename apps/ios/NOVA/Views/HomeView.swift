import SwiftUI

struct HomeView: View {
    var body: some View {
        VStack(spacing: 24) {
            Spacer()
            NovaOrbView(size: 140)
            Text("NOVA")
                .font(.title.bold())
            Text("Tap to speak")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Spacer()
            HStack(spacing: 16) {
                Image(systemName: "mic.fill")
                    .font(.title2)
                    .foregroundStyle(DesignTokens.novaBlue)
                Text("Voice input coming in Slice 2")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.bottom, 32)
        }
        .navigationTitle("NOVA")
    }
}
