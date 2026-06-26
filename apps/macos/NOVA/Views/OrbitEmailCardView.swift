import AppKit
import SwiftUI

struct OrbitEmailCardView: View {
    let email: OrbitEmailPayload
    let onAction: (AgentOSMissionAction) -> Void
    @State private var evidenceExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Orbit Email Draft")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(MacDesignTokens.novaBlue)
                Spacer()
                statusPill(email.status)
            }
            if let to = email.result.to { row("To", to) }
            if let subject = email.result.subject { row("Subject", subject) }
            if let body = email.result.bodyPreview {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Body preview")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(body)
                        .font(.caption)
                        .textSelection(.enabled)
                        .lineLimit(evidenceExpanded ? nil : 6)
                }
            }
            if let source = email.result.draftSource {
                row("Draft source", source)
            }
            if let evidence = email.result.evidenceLog {
                DisclosureGroup(isExpanded: $evidenceExpanded) {
                    Text(evidence)
                        .font(.caption2.monospaced())
                        .textSelection(.enabled)
                } label: {
                    Text("Evidence")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
            }
            if !approvalActions.isEmpty {
                if let question = email.result.approvalQuestion, !question.isEmpty {
                    Text(question)
                        .font(.caption.weight(.medium))
                }
                HStack(spacing: 8) {
                    ForEach(approvalActions) { action in
                        Button(action.label) { onAction(action) }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.small)
                    }
                }
            }
            HStack(spacing: 8) {
                ForEach(utilityActions) { action in
                    Button(action.label) { onAction(action) }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                }
            }
        }
        .padding(14)
        .background(cardBackground)
    }

    private var approvalActions: [AgentOSMissionAction] {
        email.actions.filter { $0.action == "approve_email_send" || $0.action == "skip_email_send" }
    }

    private var utilityActions: [AgentOSMissionAction] {
        email.actions.filter { $0.action != "approve_email_send" && $0.action != "skip_email_send" }
    }

    private var cardBackground: some View {
        RoundedRectangle(cornerRadius: 16, style: .continuous)
            .fill(.ultraThinMaterial)
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(Color.white.opacity(0.14), lineWidth: 1)
            )
            .shadow(color: Color.black.opacity(0.18), radius: 10, y: 3)
    }

    private func row(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption)
                .textSelection(.enabled)
        }
    }

    private func statusPill(_ status: String) -> some View {
        Text(status.replacingOccurrences(of: "_", with: " ").uppercased())
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Color.orange.opacity(0.18))
            .foregroundStyle(.orange)
            .clipShape(Capsule())
    }
}

enum OrbitEmailActionHandler {
    static func perform(_ action: AgentOSMissionAction, appState: MacAppState) {
        switch action.action {
        case "approve_email_send":
            Task { await appState.sendChatMessage("yes") }
        case "skip_email_send":
            Task { await appState.sendChatMessage("no") }
        case "copy_text":
            if let text = action.text {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(text, forType: .string)
            }
        default:
            AgentOSMissionActionHandler.perform(action, appState: appState)
        }
    }
}
