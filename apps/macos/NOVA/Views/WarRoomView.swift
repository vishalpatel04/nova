import AppKit
import SwiftUI

struct WarRoomView: View {
    @EnvironmentObject private var appState: MacAppState
    @StateObject private var voice = VoiceRuntime()
    @FocusState private var inputFocused: Bool

    private var latestMission: AgentOSMissionPayload? {
        appState.chatMessages.last(where: { $0.agentOSMission != nil })?.agentOSMission
    }

    private var roster: [WarRoomRosterEntry] {
        latestMission?.warRoomRoster?.isEmpty == false
            ? (latestMission?.warRoomRoster ?? [])
            : WarRoomRosterEntry.defaultRoster()
    }

    var body: some View {
        VStack(spacing: 0) {
            warRoomHeader
            HStack(spacing: 0) {
                AgentRosterPanel(
                    roster: roster,
                    selectedAgentId: appState.selectedWarRoomAgentId
                ) { agentId in
                    appState.selectedWarRoomAgentId = agentId
                }
                .frame(width: 220)

                Divider()

                WarRoomCenterPanel(
                    inspector: selectedInspector,
                    feed: workFeed,
                    messages: warRoomMessages,
                    isSending: appState.isChatSending
                ) { command in
                    appState.chatDraft = command
                }
                .frame(minWidth: 430)

                Divider()

                MissionEvidencePanel(mission: latestMission)
                    .environmentObject(appState)
                    .frame(width: 340)
            }
            if let error = appState.chatError {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.white)
                    .padding(8)
                    .frame(maxWidth: .infinity)
                    .background(Color.red.opacity(0.85))
            }
            warRoomInputBar
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
            if appState.selectedWarRoomAgentId == nil {
                appState.selectedWarRoomAgentId = roster.first?.agentId
            }
        }
        .onDisappear {
            Task { await stopVoiceSession() }
        }
        .onChange(of: voice.liveTranscript) { _, transcript in
            if !voice.isSpeaking {
                appState.chatDraft = transcript
            }
        }
    }

    private var warRoomHeader: some View {
        HStack(spacing: 10) {
            MacNovaOrbView(size: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text("Agent War Room")
                    .font(.subheadline.weight(.semibold))
                Text("Team updates from MissionGraph · Forge · Sentry")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            layoutToggle
            ProviderStatusBadge(healthy: appState.providerHealthy, label: appState.providerBadge)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    private var layoutToggle: some View {
        Picker("Layout", selection: $appState.chatLayoutMode) {
            Text("Chat").tag(MacAppState.ChatLayoutMode.compact)
            Text("War Room").tag(MacAppState.ChatLayoutMode.warRoom)
        }
        .pickerStyle(.segmented)
        .frame(width: 180)
    }

    private var warRoomMessages: [WarRoomMessage] {
        var rows: [WarRoomMessage] = []
        for message in appState.chatMessages {
            if message.role == .user {
                rows.append(
                    WarRoomMessage(
                        id: message.id.uuidString,
                        speaker: "You",
                        agentId: nil,
                        glyph: "person.fill",
                        colorToken: "nova_blue",
                        body: message.content,
                        isUser: true,
                        timestamp: message.timestamp
                    )
                )
                continue
            }
            if let mission = message.agentOSMission, let reports = mission.agentReports, !reports.isEmpty {
                for report in reports {
                    rows.append(
                        WarRoomMessage(
                            id: "\(message.id.uuidString)-\(report.id)",
                            speaker: report.agent,
                            agentId: report.agentId,
                            glyph: glyphForAgent(report.agentId),
                            colorToken: colorForAgent(report.agentId),
                            body: report.report,
                            isUser: false,
                            timestamp: message.timestamp
                        )
                    )
                }
            } else if let email = message.orbitEmailDraft {
                rows.append(
                    WarRoomMessage(
                        id: "\(message.id.uuidString)-orbit",
                        speaker: "Orbit",
                        agentId: "orbit",
                        glyph: "envelope.fill",
                        colorToken: "venus_rose",
                        body: email.text,
                        isUser: false,
                        timestamp: message.timestamp
                    )
                )
            } else if !message.content.isEmpty {
                rows.append(
                    WarRoomMessage(
                        id: message.id.uuidString,
                        speaker: "NOVA",
                        agentId: "prime",
                        glyph: "star.fill",
                        colorToken: "nova_blue",
                        body: message.content,
                        isUser: false,
                        timestamp: message.timestamp
                    )
                )
            }
        }
        return rows
    }

    private var selectedInspector: WarRoomAgentInspector? {
        let selectedId = appState.selectedWarRoomAgentId ?? roster.first?.agentId
        if let selectedId,
           let inspector = latestMission?.agentInspectors?.first(where: { $0.agentId == selectedId }) {
            return inspector
        }
        guard let selectedId,
              let row = roster.first(where: { $0.agentId == selectedId }) else {
            return nil
        }
        return WarRoomAgentInspector(
            agentId: row.agentId,
            displayName: row.displayName,
            role: roleForAgent(row.agentId),
            status: row.status,
            currentTask: row.taskSummary == "Standing by"
                ? "No active task yet. Mention @\(row.displayName) to assign one."
                : row.taskSummary,
            lastReport: latestMission?.agentReports?.last(where: { $0.agentId == row.agentId })?.report ?? "",
            relatedNodeIds: [],
            relatedNodes: [],
            evidencePaths: [],
            files: [],
            commands: [],
            whatDoing: row.taskSummary == "Standing by"
                ? "No active task yet. Mention @\(row.displayName) to assign one."
                : row.taskSummary,
            needsFromUser: "",
            askCommand: askCommandForAgent(row.agentId, displayName: row.displayName),
            metadata: nil
        )
    }

    private var workFeed: [WarRoomWorkFeedItem] {
        if let feed = latestMission?.agentWorkFeed, !feed.isEmpty {
            return feed
        }
        return warRoomMessages.filter { !$0.isUser }.enumerated().map { index, message in
            WarRoomWorkFeedItem(
                id: "message-\(index)",
                agentId: message.agentId ?? "prime",
                agent: message.speaker,
                status: "done",
                message: message.body,
                timestamp: nil,
                evidencePaths: []
            )
        }
    }

    private func glyphForAgent(_ agentId: String) -> String {
        roster.first(where: { $0.agentId == agentId })?.glyph
            ?? AgentParticipant(rawValue: agentId)?.glyph
            ?? "cpu.fill"
    }

    private func colorForAgent(_ agentId: String) -> String {
        roster.first(where: { $0.agentId == agentId })?.colorToken
            ?? AgentParticipant(rawValue: agentId)?.colorToken
            ?? "nova_blue"
    }

    private var warRoomInputBar: some View {
        VStack(spacing: 0) {
            Divider()
            voiceFallbackStrip
            HStack(alignment: .bottom, spacing: 8) {
                Button {
                    Task { await toggleVoice() }
                } label: {
                    Image(systemName: voiceButtonIcon)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(voice.isRecording ? .red : .primary)
                        .frame(width: 32, height: 32)
                }
                .buttonStyle(.bordered)
                .help(latestMission?.voiceStatus?.micHelper ?? "Click mic, speak command, release/auto-send.")

                TextEditor(text: $appState.chatDraft)
                    .font(.body)
                    .frame(minHeight: 44, maxHeight: 100)
                    .scrollContentBackground(.hidden)
                    .background(Color.secondary.opacity(0.08))
                    .cornerRadius(8)
                    .focused($inputFocused)
                    .overlay(alignment: .topLeading) {
                        if appState.chatDraft.isEmpty {
                            Text("Ask NOVA or @mention an agent…")
                                .font(.body)
                                .foregroundStyle(.tertiary)
                                .padding(.horizontal, 5)
                                .padding(.vertical, 8)
                                .allowsHitTesting(false)
                        }
                    }
                    .onKeyPress(.return, phases: .down) { press in
                        if press.modifiers.contains(.shift) { return .ignored }
                        sendMessage()
                        return .handled
                    }

                Button("Send") { sendMessage() }
                    .buttonStyle(.borderedProminent)
                    .disabled(
                        appState.isChatSending
                            || appState.chatDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    )
            }
            .padding(10)
            .background(.ultraThinMaterial)
        }
    }

    private var voiceFallbackStrip: some View {
        HStack(spacing: 8) {
            Image(systemName: voice.isRecording ? "waveform" : "mic.circle")
                .foregroundStyle(voice.isRecording ? .red : MacDesignTokens.novaBlue)
            Text(voiceStatusLabel)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.primary)
            Text(latestMission?.voiceStatus?.fallbackMessage ?? "Wake word is experimental. Use push-to-talk for demo.")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Spacer()
            Text(latestMission?.voiceStatus?.micHelper ?? "Click mic, speak command, release/auto-send.")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color.orange.opacity(appState.voiceWakeWordEnabled ? 0.14 : 0.08))
    }

    private var voiceButtonIcon: String {
        switch voice.phase {
        case .recording, .wakeListening: return "mic.fill"
        case .transcribing: return "waveform"
        case .speaking: return "speaker.wave.2.fill"
        case .idle: return "mic"
        }
    }

    private var voiceStatusLabel: String {
        switch voice.phase {
        case .recording: return "Recording"
        case .transcribing: return "Transcribing"
        case .speaking: return "Speaking"
        case .wakeListening: return "Listening"
        case .idle:
            return appState.voiceInputEnabled ? "Voice idle" : "Voice off"
        }
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
            if transcript.isEmpty {
                appState.chatError = latestMission?.voiceStatus?.missMessage
                    ?? "I didn't catch a wake phrase. Try push-to-talk or type the command."
                return
            }
            appState.chatDraft = transcript
            if appState.voiceAutoSendAfterTranscription {
                await appState.sendChatMessage(transcript)
            }
            return
        }
        await startPushToTalk()
    }

    private func startPushToTalk() async {
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
            try await voice.startPushToTalk()
        } catch {
            appState.chatError = "Voice failed: \(error.localizedDescription)"
        }
    }

    private func stopVoiceSession() async {
        await voice.cancelRecording()
        await voice.interruptPlayback()
    }

    private func roleForAgent(_ agentId: String) -> String {
        switch agentId {
        case "prime": return "Mission commander"
        case "archive": return "Context and memory"
        case "forge": return "Builder / coding execution"
        case "qa", "qa_engineer": return "Validation"
        case "sentry": return "Safety and approvals"
        case "orbit": return "Gmail / communications"
        case "muse": return "Copy, design, and presentation polish"
        case "nexus": return "Planning and strategy"
        default: return "Selected Forge worker"
        }
    }

    private func askCommandForAgent(_ agentId: String, displayName: String) -> String {
        switch agentId {
        case "prime": return "@Prime summarize the mission"
        case "archive": return "@Archive find related files"
        case "forge": return "@Forge improve this app"
        case "qa", "qa_engineer": return "@QA validate the build"
        case "sentry": return "@Sentry what needs approval?"
        case "orbit": return "@Orbit draft investor email"
        case "muse": return "@Muse make this more investor-ready"
        case "nexus": return "@Nexus plan next milestone"
        default: return "@Forge what engine are you using?"
        }
    }
}

private struct AgentRosterPanel: View {
    let roster: [WarRoomRosterEntry]
    let selectedAgentId: String?
    let onSelect: (String) -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text("Agent roster")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 12)
                    .padding(.top, 12)
                ForEach(roster) { agent in
                    Button {
                        onSelect(agent.agentId)
                    } label: {
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: agent.glyph)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(MacDesignTokens.agentColor(for: agent.colorToken))
                                .frame(width: 28, height: 28)
                                .background(
                                    Circle()
                                        .fill(MacDesignTokens.agentColor(for: agent.colorToken).opacity(0.15))
                                )
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(agent.displayName)
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(.primary)
                                    Spacer(minLength: 4)
                                    statusPill(agent.status)
                                }
                                Text(agent.taskSummary)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(3)
                                    .multilineTextAlignment(.leading)
                            }
                        }
                        .padding(10)
                        .background(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .fill(
                                    selectedAgentId == agent.agentId
                                        ? MacDesignTokens.novaBlue.opacity(0.12)
                                        : Color.black.opacity(0.12)
                                )
                        )
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal, 8)
                }
            }
            .padding(.bottom, 12)
        }
        .background(MacDesignTokens.chatPanel.opacity(0.35))
    }

    private func statusPill(_ status: String) -> some View {
        Text(AgentStatus(rawValue: status)?.label ?? status.capitalized)
            .font(.system(size: 9, weight: .semibold))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(statusColor(status).opacity(0.18))
            .foregroundStyle(statusColor(status))
            .clipShape(Capsule())
    }

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "working", "thinking": return MacDesignTokens.novaBlue
        case "done": return .green
        case "blocked", "failed": return .red
        case "needs_approval": return .orange
        default: return .secondary
        }
    }
}

private struct WarRoomCenterPanel: View {
    let inspector: WarRoomAgentInspector?
    let feed: [WarRoomWorkFeedItem]
    let messages: [WarRoomMessage]
    let isSending: Bool
    let onAskCommand: (String) -> Void

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    AgentInspectorPanel(inspector: inspector, onAskCommand: onAskCommand)
                    WorkFeedPanel(feed: feed)
                    WarRoomChatTranscript(messages: messages, isSending: isSending)
                }
                .padding(14)
            }
        }
        .background(Color.black.opacity(0.08))
    }
}

private struct AgentInspectorPanel: View {
    let inspector: WarRoomAgentInspector?
    let onAskCommand: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: glyph)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(MacDesignTokens.agentColor(for: colorToken))
                    .frame(width: 34, height: 34)
                    .background(Circle().fill(MacDesignTokens.agentColor(for: colorToken).opacity(0.16)))
                VStack(alignment: .leading, spacing: 3) {
                    Text(inspector?.displayName ?? "Agent Inspector")
                        .font(.headline.weight(.semibold))
                    Text(inspector?.role ?? "Select an agent to inspect current work.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if let status = inspector?.status {
                    statusPill(status)
                }
            }

            if let inspector {
                InfoBlock(label: "Current task", value: inspector.currentTask)
                if !inspector.lastReport.isEmpty {
                    InfoBlock(label: "Last report", value: inspector.lastReport)
                }
                InfoBlock(label: "What I'm doing", value: inspector.whatDoing)
                if !inspector.needsFromUser.isEmpty {
                    InfoBlock(label: "What I need from you", value: inspector.needsFromUser, accent: .orange)
                }

                if !inspector.relatedNodes.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Related MissionGraph nodes")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.secondary)
                        FlowLine(items: inspector.relatedNodes.map { $0.displayName })
                    }
                }

                if let engine = inspector.metadata?["forge_engine"], !engine.isEmpty {
                    InfoBlock(label: "Selected engine", value: engine.replacingOccurrences(of: "_", with: " "))
                }
                if let build = inspector.metadata?["build_status"], !build.isEmpty {
                    InfoBlock(label: "Validation status", value: build)
                }
                if !inspector.files.isEmpty {
                    CompactList(label: "Files", items: inspector.files)
                }
                if !inspector.commands.isEmpty {
                    CompactList(label: "Commands", items: inspector.commands)
                }
                if !inspector.evidencePaths.isEmpty {
                    CompactList(label: "Evidence paths", items: inspector.evidencePaths)
                }

                Button {
                    onAskCommand(inspector.askCommand)
                } label: {
                    Label(inspector.askCommand, systemImage: "arrow.turn.down.right")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .help("Insert suggested agent command")
            } else {
                Text("No active task yet. Mention @Agent to assign one.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(Color.black.opacity(0.18))
                .overlay(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .strokeBorder(MacDesignTokens.glassStroke.opacity(0.7), lineWidth: 1)
                )
        )
    }

    private var glyph: String {
        AgentParticipant(rawValue: normalizedAgentId)?.glyph ?? (normalizedAgentId.contains("codex") ? "terminal.fill" : "cpu.fill")
    }

    private var colorToken: String {
        AgentParticipant(rawValue: normalizedAgentId)?.colorToken ?? "mars_red"
    }

    private var normalizedAgentId: String {
        let id = inspector?.agentId ?? "prime"
        return id == "qa_engineer" ? "qa" : id
    }

    private func statusPill(_ status: String) -> some View {
        Text(AgentStatus(rawValue: status)?.label ?? status.replacingOccurrences(of: "_", with: " ").capitalized)
            .font(.system(size: 10, weight: .semibold))
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(warRoomStatusColor(status).opacity(0.18))
            .foregroundStyle(warRoomStatusColor(status))
            .clipShape(Capsule())
    }
}

private struct WorkFeedPanel: View {
    let feed: [WarRoomWorkFeedItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Work Feed")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                Text("\(feed.count) updates")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if feed.isEmpty {
                Text("No agent activity yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(feed.prefix(8)) { item in
                    WorkFeedRow(item: item)
                }
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Color.black.opacity(0.14)))
    }
}

private struct WorkFeedRow: View {
    let item: WarRoomWorkFeedItem

    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            Image(systemName: glyph)
                .font(.caption.weight(.bold))
                .foregroundStyle(MacDesignTokens.agentColor(for: colorToken))
                .frame(width: 24, height: 24)
                .background(Circle().fill(MacDesignTokens.agentColor(for: colorToken).opacity(0.14)))
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(item.agent)
                        .font(.caption.weight(.semibold))
                    Text(item.status.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.system(size: 9, weight: .semibold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(warRoomStatusColor(item.status).opacity(0.16))
                        .foregroundStyle(warRoomStatusColor(item.status))
                        .clipShape(Capsule())
                    Spacer()
                    if let timestamp = item.timestamp, !timestamp.isEmpty {
                        Text(timestamp)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                            .lineLimit(1)
                    }
                }
                Text(item.message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                if let evidence = item.evidencePaths.first {
                    Button {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(evidence, forType: .string)
                    } label: {
                        Label("Copy evidence", systemImage: "doc.on.doc")
                    }
                    .buttonStyle(.borderless)
                    .controlSize(.small)
                    .font(.caption2)
                    .help(evidence)
                }
            }
        }
    }

    private var glyph: String {
        AgentParticipant(rawValue: normalizedAgentId)?.glyph ?? "cpu.fill"
    }

    private var colorToken: String {
        AgentParticipant(rawValue: normalizedAgentId)?.colorToken ?? "nova_blue"
    }

    private var normalizedAgentId: String {
        item.agentId == "qa_engineer" ? "qa" : item.agentId
    }
}

private struct InfoBlock: View {
    let label: String
    let value: String
    var accent: Color = .secondary

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(accent)
            Text(value)
                .font(.caption)
                .foregroundStyle(.primary)
                .textSelection(.enabled)
        }
    }
}

private struct CompactList: View {
    let label: String
    let items: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            ForEach(items.prefix(5), id: \.self) { item in
                Text(item)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .textSelection(.enabled)
            }
        }
    }
}

private struct FlowLine: View {
    let items: [String]

    var body: some View {
        HStack(spacing: 6) {
            ForEach(items.prefix(4), id: \.self) { item in
                Text(item)
                    .font(.caption2.weight(.medium))
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(Color.secondary.opacity(0.12))
                    .clipShape(Capsule())
            }
        }
    }
}

private struct WarRoomChatTranscript: View {
    let messages: [WarRoomMessage]
    let isSending: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Conversation")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            WarRoomChatPanel(messages: messages, isSending: isSending)
                .frame(minHeight: 180, maxHeight: 320)
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
    }
}

private struct WarRoomChatPanel: View {
    let messages: [WarRoomMessage]
    let isSending: Bool

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    if messages.isEmpty {
                        Text("Agents stand by for your mission. Try: build a landing page for SusCo")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding()
                    }
                    ForEach(messages) { message in
                        WarRoomMessageBubble(message: message)
                            .id(message.id)
                    }
                    if isSending {
                        HStack(spacing: 8) {
                            ProgressView().controlSize(.small)
                            Text("Team is working…")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(14)
            }
            .onChange(of: messages.count) { _, _ in
                scrollToBottom(proxy: proxy)
            }
            .onChange(of: messages.last?.body) { _, _ in
                scrollToBottom(proxy: proxy)
            }
        }
    }

    private func scrollToBottom(proxy: ScrollViewProxy) {
        if let last = messages.last {
            withAnimation(.easeOut(duration: 0.15)) {
                proxy.scrollTo(last.id, anchor: .bottom)
            }
        }
    }
}

private struct WarRoomMessageBubble: View {
    let message: WarRoomMessage

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            if message.isUser { Spacer(minLength: 40) }
            if !message.isUser {
                Image(systemName: message.glyph)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(MacDesignTokens.agentColor(for: message.colorToken))
                    .frame(width: 26, height: 26)
                    .background(
                        Circle()
                            .fill(MacDesignTokens.agentColor(for: message.colorToken).opacity(0.14))
                    )
            }
            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 4) {
                if !message.isUser {
                    Text(message.speaker)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(MacDesignTokens.agentColor(for: message.colorToken))
                }
                Text(message.body)
                    .font(.callout)
                    .textSelection(.enabled)
                    .padding(12)
                    .background(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(message.isUser ? MacDesignTokens.novaBlue.opacity(0.22) : Color.black.opacity(0.18))
                    )
            }
            if !message.isUser { Spacer(minLength: 40) }
        }
    }
}

private func warRoomStatusColor(_ status: String) -> Color {
    switch status {
    case "working", "thinking", "running": return MacDesignTokens.novaBlue
    case "done", "passed": return .green
    case "blocked", "failed": return .red
    case "needs_approval", "warning", "waiting_approval": return .orange
    default: return .secondary
    }
}

private struct MissionEvidencePanel: View {
    @EnvironmentObject private var appState: MacAppState
    let mission: AgentOSMissionPayload?
    @State private var logsExpanded = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Mission graph")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)

                if let nodes = mission?.graphNodes, !nodes.isEmpty {
                    Text("11-node MissionGraph")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(Array(nodes.prefix(11).enumerated()), id: \.element.id) { index, node in
                            graphStep(index: index + 1, node: node)
                        }
                    }
                } else {
                    Text("Run a mission to populate the 11-node graph.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                if let engine = mission?.result.forgeEngine, !engine.isEmpty {
                    row("Forge engine", engine.replacingOccurrences(of: "_", with: " "))
                }
                if let build = mission?.result.buildStatus {
                    row("Validation", build)
                }
                if let preview = mission?.result.previewUrl, !preview.isEmpty {
                    Button("Open Preview") {
                        if let action = mission?.actions.first(where: { $0.action == "open_url" }) {
                            AgentOSMissionActionHandler.perform(action, appState: appState)
                        } else if let url = URL(string: preview) {
                            NSWorkspace.shared.open(url)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.regular)
                }

                if let mission {
                    stickyApprovals(for: mission)
                    evidenceSection(for: mission)
                }
            }
            .padding(14)
        }
        .background(MacDesignTokens.chatPanel.opacity(0.35))
    }

    private func row(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption)
                .textSelection(.enabled)
        }
    }

    private func graphStep(index: Int, node: MissionGraphNodeViewModel) -> some View {
        HStack(alignment: .top, spacing: 9) {
            Image(systemName: nodeIcon(node.status))
                .font(.caption.weight(.bold))
                .foregroundStyle(nodeColor(node.status))
                .frame(width: 18, height: 18)
                .background(Circle().fill(nodeColor(node.status).opacity(0.14)))
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text("\(index). \(node.displayName)")
                        .font(.caption.weight(.medium))
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    if let duration = node.durationMs {
                        Text(durationLabel(duration))
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.tertiary)
                    }
                }
                HStack(spacing: 6) {
                    Text((node.selectedAgent ?? "").replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(node.status.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.system(size: 9, weight: .semibold))
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(nodeColor(node.status).opacity(0.15))
                        .foregroundStyle(nodeColor(node.status))
                        .clipShape(Capsule())
                }
                if !node.outputSummary.isEmpty {
                    Text(node.outputSummary)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                if let error = node.error, !error.isEmpty {
                    Text(error)
                        .font(.caption2)
                        .foregroundStyle(.red)
                        .lineLimit(2)
                }
            }
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Color.black.opacity(0.12)))
        .help(node.evidence?.first ?? node.outputSummary)
    }

    private func nodeIcon(_ status: String) -> String {
        switch status {
        case "done": return "checkmark"
        case "running", "working": return "ellipsis"
        case "failed": return "xmark"
        case "skipped": return "minus"
        default: return "circle"
        }
    }

    private func durationLabel(_ durationMs: Int) -> String {
        if durationMs >= 1000 {
            return String(format: "%.1fs", Double(durationMs) / 1000.0)
        }
        return "\(durationMs)ms"
    }

    @ViewBuilder
    private func stickyApprovals(for mission: AgentOSMissionPayload) -> some View {
        let approvals = mission.actions.filter { $0.action == "approve_mission" || $0.action == "skip_mission" }
        if !approvals.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Approval gates")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                if let question = mission.result.approvalQuestion {
                    Text(question)
                        .font(.caption)
                }
                HStack {
                    ForEach(approvals) { action in
                        approvalButton(action)
                    }
                }
            }
            .padding(10)
            .background(RoundedRectangle(cornerRadius: 12).fill(Color.orange.opacity(0.12)))
        }
    }

    private func approvalButton(_ action: AgentOSMissionAction) -> some View {
        Group {
            if action.label == "Yes" {
                Button(action.label) {
                    AgentOSMissionActionHandler.perform(action, appState: appState)
                }
                .buttonStyle(.borderedProminent)
            } else {
                Button(action.label) {
                    AgentOSMissionActionHandler.perform(action, appState: appState)
                }
                .buttonStyle(.bordered)
            }
        }
    }

    @ViewBuilder
    private func evidenceSection(for mission: AgentOSMissionPayload) -> some View {
        DisclosureGroup(isExpanded: $logsExpanded) {
            if let evidence = mission.result.evidenceLog {
                Text(evidence)
                    .font(.caption2.monospaced())
                    .textSelection(.enabled)
            }
            if let path = mission.result.path {
                Text(path)
                    .font(.caption2)
                    .textSelection(.enabled)
            }
        } label: {
            Text("Evidence & logs")
                .font(.caption.weight(.semibold))
        }
    }

    private func nodeColor(_ status: String) -> Color {
        switch status {
        case "done": return .green
        case "running", "working": return MacDesignTokens.novaBlue
        case "failed": return .red
        case "warning", "needs_approval": return .orange
        default: return .secondary.opacity(0.7)
        }
    }
}
