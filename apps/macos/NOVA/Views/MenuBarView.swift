import SwiftUI

struct MenuBarView: View {
    @EnvironmentObject var appState: MacAppState

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if appState.shouldShowPairing {
                CompactPairingView()
            } else {
                GenieChatView(compact: !appState.isExpanded)
            }
            Divider()
            footer
        }
        .frame(width: 360)
        .task {
            await appState.pollWorkerHealth()
            await appState.refreshRuntimeStatus()
        }
    }

    private var header: some View {
        HStack {
            MacNovaOrbView(size: 32)
            VStack(alignment: .leading) {
                Text("NOVA")
                    .font(.headline)
                Text(appState.voiceMode.displayName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            ProviderStatusBadge(
                healthy: appState.providerHealthy,
                label: appState.providerBadge
            )
            WorkerHealthBadge(health: appState.workerHealth)
        }
        .padding()
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

#Preview {
    MenuBarView()
        .environmentObject(MacAppState())
}
