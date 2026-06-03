import SwiftUI

struct CompactChatView: View {
    @State private var inputText = ""

    var body: some View {
        VStack(spacing: 8) {
            Text("Ask NOVA anything...")
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal)

            HStack {
                TextField("Message...", text: $inputText)
                    .textFieldStyle(.roundedBorder)
                Button(action: {}) {
                    Image(systemName: "arrow.up.circle.fill")
                        .foregroundStyle(MacDesignTokens.novaBlue)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal)
            .padding(.bottom, 8)
        }
    }
}

#Preview {
    CompactChatView()
        .frame(width: 360)
}
