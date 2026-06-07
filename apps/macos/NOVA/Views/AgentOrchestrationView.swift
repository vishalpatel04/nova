import SwiftUI

struct AgentOrchestrationView: View {
    @EnvironmentObject private var appState: MacAppState
    @State private var plan: MacAgentPlanDetail?
    @State private var trustInfo: MacProviderTrust?
    @State private var loadError: String?
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            AgentPlanTabView(plan: $plan, loadError: $loadError)
                .tabItem { Label("Plan", systemImage: "list.bullet.clipboard") }
                .tag(0)
            PatchReviewTabView(plan: plan)
                .tabItem { Label("Patch", systemImage: "doc.text.magnifyingglass") }
                .tag(1)
            CommitProposalTabView(plan: plan)
                .tabItem { Label("Commit", systemImage: "arrow.triangle.branch") }
                .tag(2)
            ProviderTrustTabView(trustInfo: trustInfo)
                .tabItem { Label("Trust", systemImage: "lock.shield") }
                .tag(3)
        }
        .navigationTitle("Agent Orchestration")
        .task { await refreshAll() }
    }

    private func refreshAll() async {
        guard appState.isPaired else { return }
        do {
            plan = try await appState.api.fetchActiveAgentPlan()
            trustInfo = try await appState.api.fetchProviderTrust()
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }
}

private struct AgentPlanTabView: View {
    @EnvironmentObject private var appState: MacAppState
    @Binding var plan: MacAgentPlanDetail?
    @Binding var loadError: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let loadError {
                Text(loadError).font(.caption).foregroundStyle(.red)
            }
            if let plan {
                Text(plan.objective).font(.subheadline)
                HStack {
                    StatusBadge(text: plan.status)
                    StatusBadge(text: plan.providerLane, color: .blue)
                    if plan.waitingApproval == true {
                        StatusBadge(text: "Awaiting approval", color: .orange)
                    }
                }
                Text("Step \(plan.currentStepIndex)/\(plan.steps.count)")
                    .font(.caption)
                List(plan.steps) { step in
                    HStack {
                        Text(step.agentRole).font(.caption.bold())
                        Text(step.actionType).font(.caption2)
                        Spacer()
                        Text(step.status).font(.caption2).foregroundStyle(.secondary)
                    }
                }
                HStack {
                    Button("Refresh") { Task { await refresh() } }
                    Button("Cancel plan") { Task { await cancel() } }
                        .disabled(plan.planId.isEmpty)
                }
                .font(.caption)
            } else {
                Text("No active agent plan.").foregroundStyle(.secondary)
                Button("Create repair plan") {
                    Task { await createPlan() }
                }
            }
        }
        .padding(8)
    }

    private func refresh() async {
        do {
            plan = try await appState.api.fetchActiveAgentPlan()
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func createPlan() async {
        do {
            plan = try await appState.api.createAgentPlan(objective: "Fix failing tests")
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func cancel() async {
        guard let id = plan?.planId else { return }
        do {
            try await appState.api.cancelAgentPlan(planId: id)
            plan = try await appState.api.fetchActiveAgentPlan()
        } catch {
            loadError = error.localizedDescription
        }
    }
}

private struct PatchReviewTabView: View {
    let plan: MacAgentPlanDetail?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                if let plan {
                    if let verdict = plan.reviewerVerdict {
                        StatusBadge(text: verdict, color: verdict.contains("blocked") ? .red : .green)
                    }
                    if let preview = plan.patchPreview, !preview.isEmpty {
                        Text("Diff preview").font(.caption.bold())
                        Text(preview).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                    } else {
                        Text("No patch proposed yet.").foregroundStyle(.secondary)
                    }
                    if plan.approvalId != nil {
                        Text("Approve in Approvals queue, then Apply Approved Patch.")
                            .font(.caption)
                            .foregroundStyle(.orange)
                    }
                } else {
                    Text("No active plan.").foregroundStyle(.secondary)
                }
            }
            .padding(8)
        }
    }
}

private struct CommitProposalTabView: View {
    let plan: MacAgentPlanDetail?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Push Disabled").font(.caption.bold()).foregroundStyle(.red)
            if let proposal = plan?.commitProposal {
                LabeledContent("Branch", value: proposal.branchName)
                LabeledContent("Message", value: proposal.commitMessage)
                if !proposal.stagedPaths.isEmpty {
                    Text("Staged files:").font(.caption.bold())
                    ForEach(proposal.stagedPaths, id: \.self) { path in
                        Text(path).font(.caption2)
                    }
                }
            } else {
                Text("No commit proposal yet.").foregroundStyle(.secondary)
            }
            Text("Branch creation and commit require separate approvals.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(8)
    }
}

private struct ProviderTrustTabView: View {
    let trustInfo: MacProviderTrust?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let trustInfo {
                StatusBadge(text: trustInfo.activeLane, color: trustInfo.localActive ? .green : .orange)
                Text("External enabled: \(trustInfo.externalProvidersEnabled ? "yes" : "no")")
                    .font(.caption)
                ForEach(trustInfo.providers, id: \.kind) { provider in
                    HStack {
                        Text(provider.kind)
                        Spacer()
                        Text("cfg:\(provider.configured ? "✓" : "–") en:\(provider.enabled ? "✓" : "–")")
                            .font(.caption2)
                    }
                }
                Text("API keys never shown — macOS Keychain / NOVA_VAULT only.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            } else {
                Text("Loading trust lane…").foregroundStyle(.secondary)
            }
        }
        .padding(8)
    }
}

private struct StatusBadge: View {
    let text: String
    var color: Color = .secondary

    var body: some View {
        Text(text)
            .font(.caption2)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .clipShape(RoundedRectangle(cornerRadius: 4))
    }
}
