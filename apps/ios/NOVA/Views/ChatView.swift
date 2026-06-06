import SwiftUI

struct ChatView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var speech = AppleSpeechAdapter()
    private let speaker = NOVASpeechSynthesizer()
    @State private var messages: [ChatMessage] = []
    @State private var missionStatus: String?

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    if messages.isEmpty {
                        Text("Tap the orb to speak with NOVA.")
                            .foregroundStyle(.secondary)
                            .padding()
                    }
                    ForEach(messages) { msg in
                        HStack {
                            if msg.isUser { Spacer() }
                            Text(msg.content)
                                .padding(12)
                                .background(msg.isUser ? DesignTokens.novaBlue.opacity(0.2) : Color.gray.opacity(0.15))
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                            if !msg.isUser { Spacer() }
                        }
                    }
                    if speech.isListening {
                        Text(speech.transcript)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal)
                    }
                    if let missionStatus {
                        Text("Mission: \(missionStatus)")
                            .font(.caption)
                            .foregroundStyle(.orange)
                            .padding(.horizontal)
                    }
                }
                .padding()
            }
            NovaOrbView(isActive: speech.isListening) {
                Task { await toggleListen() }
            }
            .padding()
        }
        .navigationTitle("NOVA")
        .onAppear {
            if UserDefaults.standard.bool(forKey: "nova_pending_listen") {
                UserDefaults.standard.set(false, forKey: "nova_pending_listen")
                Task { await toggleListen() }
            }
        }
    }

    private func toggleListen() async {
        if speech.isListening {
            speech.stopListening()
            await submitTranscript(speech.transcript)
        } else {
            await appState.requestMicrophonePermission()
            await appState.requestSpeechPermission()
            guard appState.microphonePermission == .authorized,
                  appState.speechPermission == .authorized else { return }
            do { try speech.startListening() } catch {
                appState.globalError = error.localizedDescription
            }
        }
    }

    private func submitTranscript(_ text: String) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        messages.append(ChatMessage(agentId: "user", content: trimmed, isUser: true, timestamp: Date()))
        guard appState.isPaired else {
            messages.append(ChatMessage(agentId: "nova", content: "Pair this device first.", isUser: false, timestamp: Date()))
            return
        }
        do {
            let mission = try await appState.api.createMission(
                type: "system_status",
                title: trimmed,
                idempotencyKey: "ios-voice-\(UUID().uuidString)"
            )
            missionStatus = mission.status
            let reply: String
            switch mission.status {
            case "queued_waiting_for_worker":
                reply = "Your mission is queued. No worker is online yet."
            case "completed":
                reply = "System status mission completed."
            default:
                reply = "Mission \(mission.status)."
            }
            messages.append(ChatMessage(agentId: "nova", content: reply, isUser: false, timestamp: Date()))
            speaker.speak(reply)
        } catch {
            appState.globalError = error.localizedDescription
        }
    }
}
