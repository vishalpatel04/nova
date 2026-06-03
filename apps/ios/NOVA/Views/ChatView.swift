import SwiftUI

struct ChatView: View {
    @State private var messages = MockData.chatMessages
    @State private var inputText = ""

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(messages) { message in
                        ChatBubble(message: message)
                    }
                }
                .padding()
            }
            HStack {
                TextField("Message NOVA...", text: $inputText)
                    .textFieldStyle(.roundedBorder)
                Button(action: sendMessage) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                        .foregroundStyle(DesignTokens.novaBlue)
                }
            }
            .padding()
        }
        .navigationTitle("Chat")
    }

    private func sendMessage() {
        guard !inputText.isEmpty else { return }
        messages.append(ChatMessage(agentId: "user", content: inputText, isUser: true, timestamp: Date()))
        inputText = ""
    }
}

struct ChatBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.isUser { Spacer() }
            Text(message.content)
                .padding(12)
                .background(message.isUser ? DesignTokens.novaBlue : DesignTokens.secondaryBackground)
                .foregroundStyle(message.isUser ? .white : .primary)
                .clipShape(RoundedRectangle(cornerRadius: 16))
            if !message.isUser { Spacer() }
        }
    }
}

#Preview {
    NavigationStack { ChatView() }
}
