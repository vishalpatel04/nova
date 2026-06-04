import Foundation

/// Resolves the NOVA macOS client device id used as the Keychain account (mirrors worker `DEVICE_ID`).
enum NovaDeviceIdentity {
    static let deviceIdDefaultsKey = "nova_device_id"
    static let deviceIdEnvironmentKey = "DEVICE_ID"

    static let productionService = "com.nova.macos"
    static let legacyService = "com.nova.macos.genie.credentials"
    static let legacyAccount = "device_token"

    static func resolvedDeviceId(userDefaults: UserDefaults = .standard) -> String? {
        if let stored = userDefaults.string(forKey: deviceIdDefaultsKey)?.trimmingCharacters(in: .whitespacesAndNewlines),
           !stored.isEmpty {
            return stored
        }
        if let env = ProcessInfo.processInfo.environment[deviceIdEnvironmentKey]?.trimmingCharacters(in: .whitespacesAndNewlines),
           !env.isEmpty {
            return env
        }
        return nil
    }

    static func persistDeviceId(_ deviceId: String, userDefaults: UserDefaults = .standard) {
        let trimmed = deviceId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        userDefaults.set(trimmed, forKey: deviceIdDefaultsKey)
    }
}
