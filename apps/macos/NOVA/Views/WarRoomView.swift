import AppKit
import SwiftUI

struct WarRoomView: View {
    @EnvironmentObject private var appState: MacAppState
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

                WarRoomChatPanel(messages: warRoomMessages, isSending: appState.isChatSending)
                    .frame(minWidth: 360)

                Divider()

                MissionEvidencePanel(mission: latestMission)
                    .environmentObject(appState)
                    .frame(width: 280)
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
            HStack(alignment: .bottom, spacing: 8) {
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

    private func sendMessage() {
        let text = appState.chatDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        appState.chatDraft = ""
        Task { await appState.sendChatMessage(text) }
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
                    ForEach(nodes) { node in
                        HStack(alignment: .top, spacing: 8) {
                            Circle()
                                .fill(nodeColor(node.status))
                                .frame(width: 8, height: 8)
                                .padding(.top, 4)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(node.displayName)
                                    .font(.caption.weight(.medium))
                                if !node.outputSummary.isEmpty {
                                    Text(node.outputSummary)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(2)
                                }
                            }
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
        case "running": return MacDesignTokens.novaBlue
        case "failed": return .red
        default: return .secondary.opacity(0.5)
        }
    }
}
