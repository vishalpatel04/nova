import SwiftUI

struct CompactChatView: View {
    @EnvironmentObject private var appState: MacAppState
    @StateObject private var speech = MacSpeechController()
    @State private var messages: [String] = []

    var body: some View {
        VStack(spacing: 8) {
            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(messages, id: \.self) { msg in
                        Text(msg).font(.caption)
                    }
                    if speech.isListening {
                        Text(speech.transcript).font(.caption2).foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(height: 80)

            HStack {
                MacNovaOrbView(isActive: speech.isListening) {
                    Task { await toggleVoice() }
                }
                .frame(width: 44, height: 44)
                VStack(alignment: .leading) {
                    Text("Worker: \(appState.workerHealth.label)")
                        .font(.caption2)
                    Text(appState.voiceMode.displayName)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Expand") { appState.isExpanded = true }
                    .buttonStyle(.borderless)
            }
            .padding(.horizontal)
            .padding(.bottom, 8)
        }
        .task { await appState.pollWorkerHealth() }
        .onChange(of: appState.summonListen) { _, listen in
            if listen {
                appState.summonListen = false
                Task { await toggleVoice() }
            }
        }
    }

    private func toggleVoice() async {
        if speech.isListening {
            speech.stop()
            await sendTranscript(speech.transcript)
        } else {
            do { try speech.toggleListening() } catch { appState.globalError = error.localizedDescription }
        }
    }

    private func sendTranscript(_ text: String) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, appState.isPaired else { return }
        messages.append("You: \(trimmed)")
        do {
            let mission = try await appState.api.createMission(type: "system_status", title: trimmed)
            let reply: String
            if mission.status == "queued_waiting_for_worker" {
                reply = "Mission queued — worker offline."
            } else {
                reply = "Mission \(mission.status)."
            }
            messages.append("NOVA: \(reply)")
            speech.speak(reply, mode: appState.voiceMode)
        } catch {
            appState.globalError = error.localizedDescription
        }
    }
}
