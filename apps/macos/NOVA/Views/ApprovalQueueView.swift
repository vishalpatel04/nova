import SwiftUI

struct ApprovalQueueView: View {
    @EnvironmentObject private var appState: MacAppState
    @State private var items: [MacApprovalRequest] = []
    @State private var loadError: String?
    @State private var actionMessage: String?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Pending approvals")
                    .font(.headline)
                Spacer()
                Button("Refresh") { Task { await refresh() } }
            }
            .padding(.horizontal)
            .padding(.top, 8)

            if let loadError {
                Text(loadError)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .padding(.horizontal)
            }
            if let actionMessage {
                Text(actionMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal)
            }

            List {
                if items.isEmpty {
                    Text("No pending approvals.")
                        .foregroundStyle(.secondary)
                }
                ForEach(items) { item in
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
                            .font(.caption)
                            .foregroundStyle(.primary)
                            .lineLimit(4)
                        HStack {
                            Button("Approve") { Task { await approve(item.id) } }
                                .buttonStyle(.borderedProminent)
                            Button("Reject") { Task { await reject(item.id) } }
                                .buttonStyle(.bordered)
                        }
                        .font(.caption)
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .navigationTitle("Approvals")
        .task { await refresh() }
        .refreshable { await refresh() }
    }

    private func refresh() async {
        guard appState.isPaired else { return }
        do {
            items = try await appState.api.fetchPendingApprovals()
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func approve(_ id: String) async {
        do {
            _ = try await appState.api.approveRequest(id: id)
            actionMessage = "Approved (execution not yet wired)."
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
