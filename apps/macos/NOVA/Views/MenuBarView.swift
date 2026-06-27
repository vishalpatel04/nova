import SwiftUI

struct MenuBarView: View {
    @EnvironmentObject var appState: MacAppState

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if appState.shouldShowPairing {
                CompactPairingView()
            } else if appState.chatLayoutMode == .warRoom && appState.isExpanded {
                WarRoomView()
            } else {
                GenieChatView(compact: !appState.isExpanded)
            }
            Divider()
            footer
        }
        .frame(minWidth: 720, idealWidth: 920, maxWidth: 1200)
        .task {
            await appState.pollWorkerHealth()
            await appState.refreshRuntimeStatus()
        }
    }

    private var header: some View {
        HStack(spacing: 12) {
            MacNovaOrbView(size: 36)
            VStack(alignment: .leading, spacing: 2) {
                Text("NOVA")
                    .font(.headline.weight(.semibold))
                HStack(spacing: 6) {
                    modePill("Agent OS")
                    Text(appState.voiceMode.displayName)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 8)
            if !appState.shouldShowPairing {
                Picker("Layout", selection: $appState.chatLayoutMode) {
                    Text("Chat").tag(MacAppState.ChatLayoutMode.compact)
                    Text("War Room").tag(MacAppState.ChatLayoutMode.warRoom)
                }
                .pickerStyle(.segmented)
                .frame(width: 160)
            }
            ProviderStatusBadge(
                healthy: appState.providerHealthy,
                label: appState.providerBadge
            )
            WorkerHealthBadge(health: appState.workerHealth)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    private func modePill(_ label: String) -> some View {
        Text(label)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(MacDesignTokens.novaBlue.opacity(0.16))
            .foregroundStyle(MacDesignTokens.novaBlue)
            .clipShape(Capsule())
    }

    private var footer: some View {
        HStack {
            Button(action: { appState.isExpanded.toggle() }) {
                Image(systemName: appState.isExpanded ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
            }
            .buttonStyle(.plain)
            Spacer()
            Picker("Voice", selection: $appState.voiceMode) {
                ForEach(MacAppState.VoiceMode.allCases, id: \.self) { mode in
                    Text(mode.displayName).tag(mode)
                }
            }
            .pickerStyle(.menu)
            .frame(width: 120)
        }
        .padding(8)
    }
}

struct ProviderStatusBadge: View {
    let healthy: Bool
    let label: String

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(healthy ? Color.green : Color.orange)
                .frame(width: 8, height: 8)
            Text(label)
                .font(.caption2)
                .lineLimit(1)
        }
    }
}

struct WorkerHealthBadge: View {
    let health: MacAppState.WorkerHealth

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(color)
                .frame(width: 8, height: 8)
            Text(health.label)
                .font(.caption2)
                .lineLimit(1)
        }
    }

    private var color: Color {
        switch health {
        case .healthy: return .green
        case .degraded: return .orange
        case .offline: return .red
        case .unknown: return .gray
        }
    }
}
