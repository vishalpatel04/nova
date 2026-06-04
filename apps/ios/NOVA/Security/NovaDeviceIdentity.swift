import Foundation

/// Resolves the NOVA iOS client device id used as the Keychain account.
enum NovaDeviceIdentity {
    static let deviceIdDefaultsKey = "nova_device_id"
    static let deviceIdEnvironmentKey = "DEVICE_ID"
    static let productionService = "com.nova.ios"
    static let legacyService = "com.nova.ios.credentials"
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
