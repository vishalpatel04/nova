import SwiftUI

struct ExpandedChatView: View {
    private let messages: [(String, Bool)] = [
        ("Good morning, Arth.", false),
        ("What's the system status?", true),
        ("All workers online. Control plane healthy.", false),
    ]

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 8) {
                ForEach(Array(messages.enumerated()), id: \.offset) { _, msg in
                    HStack {
                        if msg.1 { Spacer() }
                        Text(msg.0)
                            .padding(8)
                            .background(msg.1 ? MacDesignTokens.novaBlue : Color.secondary.opacity(0.15))
                            .foregroundStyle(msg.1 ? .white : .primary)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                        if !msg.1 { Spacer() }
                    }
                }
            }
            .padding()
        }
        .frame(height: 240)
    }
}

#Preview {
    ExpandedChatView()
        .frame(width: 360)
}
