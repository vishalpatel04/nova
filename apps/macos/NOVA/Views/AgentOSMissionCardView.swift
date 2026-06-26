import AppKit
import SwiftUI

struct AgentOSMissionCardView: View {
    let mission: AgentOSMissionPayload
    let onAction: (AgentOSMissionAction) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            timelineSection
            resultSection
            if !approvalActions.isEmpty {
                approvalSection
            }
            utilityActions
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .strokeBorder(Color.white.opacity(0.14), lineWidth: 1)
                )
        )
        .shadow(color: Color.black.opacity(0.22), radius: 12, y: 4)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("NOVA Agent OS Mission")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(MacDesignTokens.novaBlue)
                Spacer()
                statusPill(mission.status)
            }
            Text(mission.missionTitle)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.primary)
        }
    }

    private var timelineSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Timeline")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            ForEach(mission.agentTimeline) { entry in
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
        }
    }

    private var resultSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Result")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            if let name = mission.result.appName {
                row("App", name)
            }
            if let type = mission.result.appType {
                row("Type", type)
            }
            if let path = mission.result.path {
                row("Path", path)
            }
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
            if let evidence = mission.result.evidenceLog {
                row("Evidence", evidence)
            }
        }
    }

    private var approvalSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let question = mission.result.approvalQuestion, !question.isEmpty {
                Text(question)
                    .font(.caption.weight(.medium))
            }
            HStack(spacing: 8) {
                ForEach(approvalActions) { action in
                    Button(action.label) {
                        onAction(action)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                }
            }
        }
    }

    private var utilityActions: some View {
        HStack(spacing: 8) {
            ForEach(utilityActionButtons) { action in
                Button(action.label) {
                    onAction(action)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
    }

    private var approvalActions: [AgentOSMissionAction] {
        mission.actions.filter { $0.action == "approve_mission" || $0.action == "skip_mission" }
    }

    private var utilityActionButtons: [AgentOSMissionAction] {
        mission.actions.filter { $0.action != "approve_mission" && $0.action != "skip_mission" }
    }

    private func row(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption.monospaced())
                .textSelection(.enabled)
                .lineLimit(3)
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

    @ViewBuilder
    private func statusPill(_ status: String) -> some View {
        let normalized = status.replacingOccurrences(of: "_", with: " ").uppercased()
        Text(normalized)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(pillColor(for: status).opacity(0.18))
            .foregroundStyle(pillColor(for: status))
            .clipShape(Capsule())
    }

    private func pillColor(for status: String) -> Color {
        switch status.lowercased() {
        case "pass", "done", "completed":
            return .green
        case "waiting_approval", "warning":
            return .orange
        case "skipped":
            return .secondary
        case "failed", "fail":
            return .red
        default:
            return MacDesignTokens.novaBlue
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
