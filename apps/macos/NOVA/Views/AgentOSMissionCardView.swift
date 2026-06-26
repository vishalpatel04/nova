import AppKit
import SwiftUI

struct AgentOSMissionCardView: View {
    let mission: AgentOSMissionPayload
    let onAction: (AgentOSMissionAction) -> Void
    @State private var evidenceExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            timelineSection
            resultSection
            approvalFooter
            utilityActions
        }
        .padding(16)
        .background(cardBackground)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("NOVA Agent OS Mission")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(MacDesignTokens.novaBlue)
                Spacer()
                statusPill(mission.status)
            }
            Text(mission.missionTitle)
                .font(.body.weight(.medium))
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var timelineSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Timeline")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if let first = mission.agentTimeline.first {
                        timelineRow(first)
                    }
                    if mission.agentTimeline.count > 2 {
                        ForEach(mission.agentTimeline.dropFirst().dropLast()) { entry in
                            timelineRow(entry)
                        }
                    }
                    if mission.agentTimeline.count > 1, let last = mission.agentTimeline.last {
                        timelineRow(last)
                    }
                }
            }
            .frame(maxHeight: 220)
            .padding(10)
            .background(RoundedRectangle(cornerRadius: 12).fill(Color.black.opacity(0.12)))
        }
    }

    private var resultSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Result")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            if let name = mission.result.appName { row("App", name) }
            if let type = mission.result.appType { row("Type", type) }
            if let path = mission.result.path { row("Path", path) }
            if let build = mission.result.buildStatus {
                HStack(spacing: 6) {
                    Text("Build")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    statusPill(build.lowercased() == "pass" ? "pass" : build.lowercased())
                }
            }
            if let run = mission.result.runCommand, !run.isEmpty {
                row("Run", run)
            }
            if let preview = mission.result.previewUrl, !preview.isEmpty {
                Button("Open Preview") {
                    if let action = mission.actions.first(where: { $0.action == "open_url" }) {
                        onAction(action)
                    } else if let url = URL(string: preview) {
                        NSWorkspace.shared.open(url)
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.regular)
            }
            if let evidence = mission.result.evidenceLog {
                DisclosureGroup(isExpanded: $evidenceExpanded) {
                    Text(evidence)
                        .font(.caption2.monospaced())
                        .textSelection(.enabled)
                } label: {
                    Text("Evidence log")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color.black.opacity(0.08)))
    }

    @ViewBuilder
    private var approvalFooter: some View {
        if !approvalActions.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                if let question = mission.result.approvalQuestion, !question.isEmpty {
                    Text(question)
                        .font(.callout.weight(.medium))
                }
                HStack(spacing: 10) {
                    ForEach(approvalActions) { action in
                        Button(action.label) { onAction(action) }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.regular)
                    }
                }
            }
            .padding(.top, 4)
        }
    }

    private var utilityActions: some View {
        HStack(spacing: 8) {
            ForEach(utilityActionButtons) { action in
                Button(action.label) { onAction(action) }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
        }
    }

    private var cardBackground: some View {
        RoundedRectangle(cornerRadius: 18, style: .continuous)
            .fill(.ultraThinMaterial)
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .strokeBorder(MacDesignTokens.glassStroke, lineWidth: 1)
            )
            .shadow(color: Color.black.opacity(0.24), radius: 14, y: 5)
    }

    private var approvalActions: [AgentOSMissionAction] {
        mission.actions.filter { $0.action == "approve_mission" || $0.action == "skip_mission" }
    }

    private var utilityActionButtons: [AgentOSMissionAction] {
        mission.actions.filter {
            $0.action != "approve_mission"
                && $0.action != "skip_mission"
                && $0.action != "open_url"
        }
    }

    private func timelineRow(_ entry: AgentOSTimelineEntry) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Text(timelineGlyph(for: entry.status))
                .font(.caption.monospaced())
                .frame(width: 14)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(entry.agent)
                        .font(.caption.weight(.semibold))
                    if entry.status != "done" {
                        statusPill(entry.status)
                    }
                }
                Text(entry.summary)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func row(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption.monospaced())
                .textSelection(.enabled)
                .lineLimit(4)
        }
    }

    private func timelineGlyph(for status: String) -> String {
        switch status {
        case "done", "pass": return "✓"
        case "warning", "waiting_approval": return "⚠"
        case "failed": return "✕"
        case "skipped": return "–"
        default: return "•"
        }
    }

    private func statusPill(_ status: String) -> some View {
        Text(status.replacingOccurrences(of: "_", with: " ").uppercased())
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(pillColor(for: status).opacity(0.18))
            .foregroundStyle(pillColor(for: status))
            .clipShape(Capsule())
    }

    private func pillColor(for status: String) -> Color {
        switch status.lowercased() {
        case "pass", "done", "completed": return .green
        case "waiting_approval", "warning": return .orange
        case "skipped": return .secondary
        case "failed", "fail": return .red
        default: return MacDesignTokens.novaBlue
        }
    }
}

enum AgentOSMissionActionHandler {
    static func perform(_ action: AgentOSMissionAction, appState: MacAppState) {
        switch action.action {
        case "approve_mission":
            Task { await appState.sendChatMessage("yes") }
        case "skip_mission":
            Task { await appState.sendChatMessage("no") }
        case "open_url":
            if let urlString = action.url, let url = URL(string: urlString) {
                NSWorkspace.shared.open(url)
            }
        case "copy_text":
            if let text = action.text {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(text, forType: .string)
            }
        default:
            break
        }
    }
}
