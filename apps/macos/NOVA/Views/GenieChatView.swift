import AppKit
import SwiftUI

struct GenieChatView: View {
    @EnvironmentObject private var appState: MacAppState
    @StateObject private var voice = VoiceRuntime()
    @FocusState private var inputFocused: Bool
    @State private var expandedMessageIDs: Set<UUID> = []

    private let quickSuggestions = [
        "system status",
        "connected devices",
        "list directory ~/Projects/nova",
        "repo analysis",
        "what can you do?",
    ]

    var compact: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            statusBar
            messageList
            suggestionBar
            if let error = appState.chatError {
                errorBanner(error)
            }
            chatInputBar
        }
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .strokeBorder(MacDesignTokens.glassStroke, lineWidth: 1)
                )
        )
        .preferredColorScheme(.dark)
        .task {
            await appState.refreshRuntimeStatus()
            await appState.refreshRecentChatSessions()
            await syncVoiceOnOpen()
        }
        .onDisappear {
            Task { await stopVoiceSession() }
        }
        .onChange(of: appState.summonListen) { _, listen in
            if listen {
                appState.summonListen = false
                Task { await startVoiceCapture() }
            }
        }
        .onChange(of: appState.voiceKillSwitch) { _, killSwitch in
            Task {
                if killSwitch {
                    await stopVoiceSession()
                } else {
                    await syncVoiceOnOpen()
                }
            }
        }
        .onChange(of: appState.voiceInputEnabled) { _, enabled in
            Task {
                if enabled {
                    await syncVoiceOnOpen()
                } else {
                    await stopVoiceSession()
                }
            }
        }
        .onChange(of: appState.voiceWakeWordEnabled) { _, _ in
            Task {
                if voice.isRecording || voice.isWakeListening {
                    await stopVoiceSession()
                    await syncVoiceOnOpen()
                } else {
                    await syncVoiceOnOpen()
                }
            }
        }
        .onChange(of: appState.voiceStartListeningOnOpen) { _, _ in
            Task {
                if voice.isRecording || voice.isWakeListening {
                    await stopVoiceSession()
                }
                await syncVoiceOnOpen()
            }
        }
        .onChange(of: voice.liveTranscript) { _, transcript in
            if !voice.isSpeaking {
                appState.chatDraft = transcript
            }
        }
        .onChange(of: voice.phase) { oldPhase, newPhase in
            handleVoicePhaseChange(oldPhase: oldPhase, newPhase: newPhase)
        }
        .onChange(of: appState.chatDraft) { _, _ in
            appState.persistChatSnapshot()
        }
    }

    private var statusBar: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(appState.providerHealthy ? Color.green : Color.orange)
                .frame(width: 6, height: 6)
            Text(appState.providerBadge)
                .font(.caption2.weight(.medium))
                .foregroundStyle(.secondary)
                .lineLimit(1)
            if let project = appState.activeProjectName {
                Text("📁 \(project)")
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            if let pending = appState.pendingToolIntent {
                Text(pending.replacingOccurrences(of: "_", with: " "))
                    .font(.caption2)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.accentColor.opacity(0.12))
                    .clipShape(Capsule())
            }
            if !appState.taskTimeline.isEmpty {
                TaskTimelineStrip(entries: appState.taskTimeline)
            }
            if !appState.providerHealthy, let hint = appState.localModelStatusMessage {
                Text(hint)
                    .font(.caption2)
                    .foregroundStyle(.orange)
                    .lineLimit(2)
            }
            Spacer(minLength: 8)
            Menu {
                Button("New Chat") { appState.startNewChat() }
                Button("Clear Current Conversation") { appState.clearCurrentConversationMemory() }
                Divider()
                Button("Refresh Sessions") {
                    Task { await appState.refreshRecentChatSessions() }
                }
                if !appState.recentChatSessions.isEmpty {
                    Divider()
                    ForEach(appState.recentChatSessions.prefix(8)) { session in
                        Button {
                            Task { await appState.restoreSession(sessionId: session.id) }
                        } label: {
                            Text(session.title)
                        }
                    }
                }
            } label: {
                Image(systemName: "clock.arrow.circlepath")
            }
            .menuStyle(.borderlessButton)
            .buttonStyle(.plain)
            .help("Recent chats")
            Button {
                appState.startNewChat()
            } label: {
                Image(systemName: "plus.bubble")
            }
            .buttonStyle(.plain)
            .help("New chat")
            voiceStatusChip
        }
        .padding(.horizontal, 12)
        .padding(.top, 6)
    }

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    if appState.chatMessages.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(appState.providerHealthy ? MacAppState.welcomeText : (appState.localModelStatusMessage ?? "Local model unavailable. Start Ollama."))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 8)
                    }
                    ForEach(appState.chatMessages) { message in
                        ChatBubble(message: message)
                            .environmentObject(appState)
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
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 16)
            }
            .frame(minHeight: compact ? 320 : 420, maxHeight: .infinity)
            .onChange(of: appState.chatMessages.count) { _, _ in
                scrollToBottom(proxy: proxy)
            }
            .onChange(of: appState.chatMessages.last?.content) { _, _ in
                scrollToBottom(proxy: proxy)
            }
        }
    }

    private var suggestionBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(quickSuggestions, id: \.self) { suggestion in
                    Button(suggestion) {
                        appState.chatDraft = suggestion
                        sendMessage()
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .font(.caption2)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, compact ? 4 : 6)
        }
    }

    private func scrollToBottom(proxy: ScrollViewProxy) {
        if let last = appState.chatMessages.last {
            withAnimation(.easeOut(duration: 0.15)) { proxy.scrollTo(last.id, anchor: .bottom) }
        }
    }

    private var chatInputBar: some View {
        VStack(spacing: 0) {
            Divider()
            HStack(alignment: .bottom, spacing: 8) {
                Button {
                    Task { await toggleVoice() }
                } label: {
                    Image(systemName: (voice.isRecording || voice.isWakeListening) ? "mic.fill" : "mic")
                        .foregroundStyle((voice.isRecording || voice.isWakeListening) ? .red : .primary)
                }
                .buttonStyle(.plain)
                .help("Click mic, speak command, release/auto-send.")

                TextEditor(text: $appState.chatDraft)
                    .font(.body)
                    .frame(minHeight: 44, maxHeight: compact ? 72 : 120)
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
                    .buttonStyle(.borderedProminent)
                    .controlSize(.regular)
                    .disabled(
                        appState.isChatSending
                            || appState.chatDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    )
            }
            .padding(10)
            .background(.ultraThinMaterial)
        }
    }

    private func errorBanner(_ text: String) -> some View {
        HStack(spacing: 8) {
            Text(text)
                .font(.caption)
                .foregroundStyle(.white)
                .lineLimit(2)
            Spacer()
            Button {
                appState.chatError = nil
            } label: {
                Image(systemName: "xmark")
                    .font(.caption2)
            }
            .buttonStyle(.plain)
            .foregroundStyle(.white)
        }
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
        if voice.isRecording || voice.isWakeListening {
            let transcript = await voice.finishPushToTalk()
            if !transcript.isEmpty {
                appState.chatDraft = transcript
                if appState.voiceAutoSendAfterTranscription {
                    await appState.sendChatMessage(transcript)
                }
            } else if appState.voiceWakeWordEnabled {
                appState.chatError = "I didn't catch a wake phrase. Try push-to-talk or type the command."
            }
        } else {
            await startVoiceCapture(forcePushToTalk: true)
        }
    }

    private func startVoiceCapture(forcePushToTalk: Bool = false) async {
        if appState.voiceKillSwitch || !appState.voiceInputEnabled {
            appState.chatError = "Voice input is disabled."
            return
        }
        let granted = await voice.preparePermissions()
        guard granted else {
            appState.chatError = "Speech or microphone permission denied."
            return
        }
        do {
            if appState.voiceWakeWordEnabled && !forcePushToTalk {
                if voice.supportsWakeWord {
                    try await voice.startWakeListening()
                } else {
                    appState.chatError = "Wake word is experimental. Use push-to-talk for demo."
                }
            } else {
                try await voice.startPushToTalk()
            }
        } catch {
            appState.chatError = error.localizedDescription
        }
    }

    private func syncVoiceOnOpen() async {
        guard !appState.voiceKillSwitch, appState.voiceInputEnabled else { return }
        guard appState.voiceWakeWordEnabled || appState.voiceStartListeningOnOpen else { return }
        await startVoiceCapture()
    }

    private func stopVoiceSession() async {
        await voice.cancelRecording()
        await voice.interruptPlayback()
    }

    private func handleVoicePhaseChange(oldPhase: VoiceRuntime.Phase, newPhase: VoiceRuntime.Phase) {
        guard oldPhase.isWakeListening else { return }
        guard newPhase.isRecording else { return }
        guard appState.voiceWakeSoundEnabled else { return }
        NSSound.beep()
    }

    private var voiceStatusChip: some View {
        let label: String
        switch true {
        case appState.voiceKillSwitch:
            label = "Voice Off"
        case voice.isSpeaking:
            label = "Speaking"
        case voice.isWakeListening:
            label = "Listening"
        case voice.isRecording:
            label = "Recording"
        case voice.phase == .transcribing:
            label = "Transcribing"
        case appState.voiceInputEnabled && appState.voiceWakeWordEnabled:
            label = voice.supportsWakeWord ? "Wake experimental" : "Push-to-talk"
        case appState.voiceInputEnabled:
            label = "Idle"
        default:
            label = "Voice Off"
        }
        return Text(label)
            .font(.caption2)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Color.secondary.opacity(0.12))
            .clipShape(Capsule())
    }
}

private struct TaskTimelineStrip: View {
    let entries: [MacTaskTimelineEntry]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 4) {
                ForEach(entries) { entry in
                    Text(entry.stage.replacingOccurrences(of: "_", with: " "))
                        .font(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.12))
                        .clipShape(Capsule())
                }
            }
        }
        .frame(maxWidth: 180)
    }
}

private struct ChatBubble: View {
    @EnvironmentObject private var appState: MacAppState
    let message: ChatMessage
    @State private var expanded = false

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 24) }
            VStack(alignment: .leading, spacing: 8) {
                if let mission = message.agentOSMission {
                    AgentOSMissionCardView(mission: mission) { action in
                        AgentOSMissionActionHandler.perform(action, appState: appState)
                    }
                    if shouldShowFollowupText(for: mission) {
                        Text(message.content)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                } else if let email = message.orbitEmailDraft {
                    OrbitEmailCardView(email: email) { action in
                        OrbitEmailActionHandler.perform(action, appState: appState)
                    }
                } else if shouldCollapse {
                    Text(expanded ? contentText : collapsedText)
                        .font(.caption)
                        .textSelection(.enabled)
                    Button(expanded ? "Show less" : "Show more") {
                        expanded.toggle()
                    }
                    .font(.caption2)
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                } else {
                    Text(contentText)
                        .font(.caption)
                        .textSelection(.enabled)
                }
            }
            .padding(message.agentOSMission == nil && message.orbitEmailDraft == nil ? 10 : 0)
            .foregroundStyle(foreground)
            .background { bubbleBackground }
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .opacity(message.isStreaming ? 0.92 : 1)
            if message.role != .user { Spacer(minLength: 24) }
        }
    }

    private func shouldShowFollowupText(for mission: AgentOSMissionPayload) -> Bool {
        let trimmed = message.content.trimmingCharacters(in: .whitespacesAndNewlines)
        return !trimmed.isEmpty && trimmed != mission.text
    }

    @ViewBuilder
    private var bubbleBackground: some View {
        if message.agentOSMission == nil && message.orbitEmailDraft == nil {
            background
        }
    }

    private var contentText: String {
        if message.content.isEmpty && message.isStreaming {
            return "Running mission…"
        }
        return message.content
    }

    private var shouldCollapse: Bool {
        message.agentOSMission == nil && message.orbitEmailDraft == nil && contentText.count > 700
    }

    private var collapsedText: String {
        String(contentText.prefix(700)) + "…"
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
