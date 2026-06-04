import SwiftUI

struct GenieChatView: View {
    @EnvironmentObject private var appState: MacAppState
    @StateObject private var voice = VoiceRuntime()
    @FocusState private var inputFocused: Bool

    var compact: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            statusBar
            messageList
            if let error = appState.chatError {
                errorBanner(error)
            }
            chatInputBar
        }
        .background(Color(nsColor: .windowBackgroundColor).opacity(0.95))
        .onChange(of: appState.summonListen) { _, listen in
            if listen {
                appState.summonListen = false
                Task { await startVoiceCapture() }
            }
        }
        .onChange(of: voice.liveTranscript) { _, transcript in
            if !voice.isRecording, !transcript.isEmpty {
                appState.chatDraft = transcript
            }
        }
        .onChange(of: appState.chatDraft) { _, draft in
            appState.persistChatSnapshot()
        }
    }

    private var statusBar: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(appState.providerHealthy ? Color.green : Color.orange)
                .frame(width: 6, height: 6)
            Text(appState.providerModeLabel)
                .font(.caption2)
                .foregroundStyle(.secondary)
            if appState.isChatStreaming {
                ProgressView().controlSize(.mini)
                Text("Streaming…")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Button("Stop") { appState.cancelActiveChatStream() }
                    .font(.caption2)
                    .buttonStyle(.plain)
            } else if voice.isRecording {
                Image(systemName: "mic.fill")
                    .foregroundStyle(.red)
                    .font(.caption2)
                Text("Recording…")
                    .font(.caption2)
                Button("Cancel") { Task { await voice.cancelRecording() } }
                    .font(.caption2)
                    .buttonStyle(.plain)
            } else if voice.isSpeaking {
                Text("Speaking…")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.top, 6)
    }

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    if appState.chatMessages.isEmpty {
                        Text("Ask about system status, devices, missions, or safe read-only files.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(.vertical, 8)
                    }
                    ForEach(appState.chatMessages) { message in
                        ChatBubble(message: message)
                            .id(message.id)
                    }
                    if appState.isChatSending && !appState.isChatStreaming {
                        HStack(spacing: 8) {
                            ProgressView().controlSize(.small)
                            Text("NOVA is thinking…")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.leading, 4)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
            }
            .frame(minHeight: compact ? 120 : 260, maxHeight: compact ? 180 : .infinity)
            .onChange(of: appState.chatMessages.count) { _, _ in
                scrollToBottom(proxy: proxy)
            }
            .onChange(of: appState.chatMessages.last?.content) { _, _ in
                scrollToBottom(proxy: proxy)
            }
        }
    }

    private func scrollToBottom(proxy: ScrollViewProxy) {
        if let last = appState.chatMessages.last {
            withAnimation(.easeOut(duration: 0.15)) { proxy.scrollTo(last.id, anchor: .bottom) }
        }
    }

    private var chatInputBar: some View {
        HStack(alignment: .bottom, spacing: 8) {
            Button {
                Task { await toggleVoice() }
            } label: {
                Image(systemName: voice.isRecording ? "mic.fill" : "mic")
                    .foregroundStyle(voice.isRecording ? .red : .primary)
            }
            .buttonStyle(.plain)
            .help("Push-to-talk")

            TextEditor(text: $appState.chatDraft)
                .font(.body)
                .frame(minHeight: 36, maxHeight: compact ? 56 : 88)
                .scrollContentBackground(.hidden)
                .background(Color.secondary.opacity(0.08))
                .cornerRadius(8)
                .focused($inputFocused)
                .onKeyPress(.return, phases: .down) { press in
                    if press.modifiers.contains(.shift) { return .ignored }
                    sendMessage()
                    return .handled
                }

            Button("Send") { sendMessage() }
                .keyboardShortcut(.return, modifiers: [])
                .disabled(
                    appState.isChatSending
                        || appState.chatDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                )
        }
        .padding(10)
        .background(Color.black.opacity(0.15))
    }

    private func errorBanner(_ text: String) -> some View {
        Text(text)
            .font(.caption)
            .foregroundStyle(.white)
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.red.opacity(0.75))
    }

    private func sendMessage() {
        let text = appState.chatDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        appState.chatDraft = ""
        Task { await appState.sendChatMessage(text) }
    }

    private func toggleVoice() async {
        if voice.isRecording {
            let transcript = await voice.finishPushToTalk()
            if !transcript.isEmpty {
                appState.chatDraft = transcript
                await appState.sendChatMessage(transcript)
            }
        } else {
            await startVoiceCapture()
        }
    }

    private func startVoiceCapture() async {
        let granted = await voice.preparePermissions()
        guard granted else {
            appState.chatError = "Speech or microphone permission denied."
            return
        }
        do {
            try await voice.startPushToTalk()
        } catch {
            appState.chatError = error.localizedDescription
        }
    }
}

private struct ChatBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 24) }
            Text(message.content.isEmpty && message.isStreaming ? "…" : message.content)
                .font(.caption)
                .padding(10)
                .foregroundStyle(foreground)
                .background(background)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .opacity(message.isStreaming ? 0.92 : 1)
            if message.role != .user { Spacer(minLength: 24) }
        }
    }

    private var background: Color {
        switch message.role {
        case .user: return MacDesignTokens.novaBlue
        case .assistant: return Color.secondary.opacity(0.18)
        case .error: return Color.red.opacity(0.25)
        }
    }

    private var foreground: Color {
        message.role == .user ? .white : .primary
    }
}
