import SwiftUI

struct ApprovalQueueView: View {
    @EnvironmentObject private var appState: MacAppState
    @State private var pendingItems: [MacApprovalRequest] = []
    @State private var approvedItems: [MacApprovalRequest] = []
    @State private var loadError: String?
    @State private var actionMessage: String?
    @State private var lastExecution: MacShellExecutionResult?
    @State private var lastPatch: MacPatchExecutionResult?

    var body: some View {
        VStack(spacing: 0) {
            header
            if let loadError {
                Text(loadError).font(.caption).foregroundStyle(.red).padding(.horizontal)
            }
            if let actionMessage {
                Text(actionMessage).font(.caption).foregroundStyle(.secondary).padding(.horizontal)
            }
            if let lastPatch {
                patchPanel(lastPatch)
            }
            if let lastExecution {
                executionPanel(lastExecution)
            }
            List {
                if !pendingItems.isEmpty {
                    Section("Pending") {
                        ForEach(pendingItems) { item in
                            approvalRow(item, showApprove: true)
                        }
                    }
                }
                if !approvedItems.isEmpty {
                    Section("Approved — ready to execute") {
                        ForEach(approvedItems) { item in
                            approvalRow(
                                item,
                                showExecute: item.capability == "shell.execute",
                                showApplyPatch: item.capability == "code.patch" || item.capability == "file.write"
                            )
                        }
                    }
                }
                if pendingItems.isEmpty && approvedItems.isEmpty {
                    Text("No actionable approvals.")
                        .foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle("Approvals")
        .task { await refresh() }
        .refreshable { await refresh() }
    }

    private var header: some View {
        HStack {
            Text("Approvals")
                .font(.headline)
            Spacer()
            Button("Refresh") { Task { await refresh() } }
        }
        .padding(.horizontal)
        .padding(.top, 8)
    }

    @ViewBuilder
    private func approvalRow(
        _ item: MacApprovalRequest,
        showApprove: Bool = false,
        showExecute: Bool = false,
        showApplyPatch: Bool = false
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(item.actionSummary)
                    .font(.subheadline.weight(.medium))
                Spacer()
                RiskBadge(level: item.riskLevel)
            }
            Text(item.capability)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(item.commandOrPayloadPreview)
                .font(.caption.monospaced())
                .foregroundStyle(.primary)
                .lineLimit(4)
            HStack {
                StatusBadge(status: item.status)
                Text("Expires \(item.expiresAt.formatted(date: .abbreviated, time: .shortened))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            HStack {
                if showApprove {
                    Button("Approve") { Task { await approve(item.id) } }
                        .buttonStyle(.borderedProminent)
                    Button("Reject") { Task { await reject(item.id) } }
                        .buttonStyle(.bordered)
                }
                if showExecute {
                    Button("Execute Approved Action") { Task { await execute(item.id) } }
                        .buttonStyle(.borderedProminent)
                }
                if showApplyPatch {
                    Button("Apply Approved Patch") { Task { await applyPatch(item.id) } }
                        .buttonStyle(.borderedProminent)
                }
            }
            .font(.caption)
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func patchPanel(_ result: MacPatchExecutionResult) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("Patch result")
                    .font(.caption.weight(.semibold))
                StatusBadge(status: result.status)
            }
            Text(result.patchPreview)
                .font(.caption.monospaced())
                .lineLimit(8)
            if let files = result.appliedFiles, !files.isEmpty {
                Text("Applied: \(files.joined(separator: ", "))")
                    .font(.caption2)
            }
            if let err = result.errorMessage, !err.isEmpty {
                Text(err)
                    .font(.caption.monospaced())
                    .foregroundStyle(.orange)
            }
        }
        .padding(8)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .padding(.horizontal)
    }

    private func applyPatch(_ id: String) async {
        do {
            let result = try await appState.api.applyApprovedPatch(approvalId: id)
            lastPatch = result
            actionMessage = "Patch apply finished: \(result.status)"
            await refresh()
        } catch {
            loadError = error.localizedDescription
        }
    }

    @ViewBuilder
    private func executionPanel(_ result: MacShellExecutionResult) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("Execution result")
                    .font(.caption.weight(.semibold))
                StatusBadge(status: result.status)
            }
            if let stdout = result.stdoutExcerpt, !stdout.isEmpty {
                Text(stdout)
                    .font(.caption.monospaced())
                    .lineLimit(8)
            }
            if let stderr = result.stderrExcerpt, !stderr.isEmpty {
                Text(stderr)
                    .font(.caption.monospaced())
                    .foregroundStyle(.orange)
                    .lineLimit(4)
            }
            if let code = result.exitCode {
                Text("Exit code: \(code)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(8)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .padding(.horizontal)
    }

    private func refresh() async {
        guard appState.isPaired else { return }
        do {
            let actionable = try await appState.api.fetchActionableApprovals()
            pendingItems = actionable.pending
            approvedItems = actionable.approved
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func approve(_ id: String) async {
        do {
            _ = try await appState.api.approveRequest(id: id)
            actionMessage = "Approved. Click Execute Approved Action when ready."
            await refresh()
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func reject(_ id: String) async {
        do {
            _ = try await appState.api.rejectRequest(id: id)
            actionMessage = "Rejected."
            await refresh()
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func execute(_ id: String) async {
        do {
            let result = try await appState.api.runApprovedExecution(approvalId: id)
            lastExecution = result
            actionMessage = "Execution finished: \(result.status)"
            await refresh()
        } catch {
            loadError = error.localizedDescription
        }
    }
}

private struct RiskBadge: View {
    let level: String

    var body: some View {
        Text(level.uppercased())
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }

    private var color: Color {
        switch level.lowercased() {
        case "critical": return .red
        case "high": return .orange
        case "medium": return .yellow
        default: return .green
        }
    }
}

private struct StatusBadge: View {
    let status: String

    var body: some View {
        Text(status)
            .font(.caption2.weight(.medium))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Color.secondary.opacity(0.12))
            .clipShape(Capsule())
    }
}
