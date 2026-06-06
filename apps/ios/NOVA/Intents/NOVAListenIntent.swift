import AppIntents

/// App Intent for Shortcuts / Action Button — starts NOVA listening when the app opens.
struct NOVAListenIntent: AppIntent {
    static var title: LocalizedStringResource = "Start NOVA Listening"
    static var description = IntentDescription("Opens NOVA and starts tap-to-listen voice capture.")
    static var openAppWhenRun: Bool = true

    @MainActor
    func perform() async throws -> some IntentResult {
        UserDefaults.standard.set(true, forKey: "nova_pending_listen")
        return .result(dialog: "Opening NOVA for listening.")
    }
}

struct NOVAShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: NOVAListenIntent(),
            phrases: ["Start \(.applicationName) listening", "Listen with \(.applicationName)"],
            shortTitle: "NOVA Listen",
            systemImageName: "waveform.circle"
        )
    }
}
