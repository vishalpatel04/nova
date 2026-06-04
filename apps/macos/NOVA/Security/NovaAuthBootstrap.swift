import Foundation

struct KeychainTokenLookup: Equatable {
    let token: String?
    let deviceId: String?
    let keychainAccount: String?
    let keychainService: String
    let source: String

    var tokenExists: Bool { token != nil }
}

/// Startup Keychain token resolution with structured telemetry.
enum NovaAuthBootstrap {
    static func lookupToken(
        userDefaults: UserDefaults = .standard,
        keychainService: String = NovaDeviceIdentity.productionService,
        legacyService: String = NovaDeviceIdentity.legacyService,
        legacyAccount: String = NovaDeviceIdentity.legacyAccount
    ) -> KeychainTokenLookup {
        NovaHotkeyTelemetry.emit("nova_token_lookup_started")

        let resolvedDeviceId = NovaDeviceIdentity.resolvedDeviceId(userDefaults: userDefaults)

        if let deviceId = resolvedDeviceId,
           let token = KeychainStore.load(account: deviceId, service: keychainService) {
            emitDiagnostics(deviceId: deviceId, keychainAccount: deviceId, tokenExists: true)
            NovaHotkeyTelemetry.emit("nova_token_lookup_success")
            return KeychainTokenLookup(
                token: token,
                deviceId: deviceId,
                keychainAccount: deviceId,
                keychainService: keychainService,
                source: "primary"
            )
        }

        if let token = KeychainStore.load(account: legacyAccount, service: legacyService) {
            let account = legacyAccount
            emitDiagnostics(deviceId: resolvedDeviceId, keychainAccount: account, tokenExists: true)
            NovaHotkeyTelemetry.emit("nova_token_lookup_success")
            return KeychainTokenLookup(
                token: token,
                deviceId: resolvedDeviceId,
                keychainAccount: account,
                keychainService: legacyService,
                source: "legacy"
            )
        }

        if let discovered = KeychainStore.discoverToken(service: keychainService) {
            NovaDeviceIdentity.persistDeviceId(discovered.account, userDefaults: userDefaults)
            emitDiagnostics(deviceId: discovered.account, keychainAccount: discovered.account, tokenExists: true)
            NovaHotkeyTelemetry.emit("nova_token_lookup_success")
            return KeychainTokenLookup(
                token: discovered.token,
                deviceId: discovered.account,
                keychainAccount: discovered.account,
                keychainService: keychainService,
                source: "discovered"
            )
        }

        emitDiagnostics(deviceId: resolvedDeviceId, keychainAccount: resolvedDeviceId, tokenExists: false)
        NovaHotkeyTelemetry.emit("nova_token_lookup_failed")
        return KeychainTokenLookup(
            token: nil,
            deviceId: resolvedDeviceId,
            keychainAccount: resolvedDeviceId,
            keychainService: keychainService,
            source: "none"
        )
    }

    static func emitDiagnostics(deviceId: String?, keychainAccount: String?, tokenExists: Bool) {
        let deviceLabel = deviceId ?? "nil"
        let accountLabel = keychainAccount ?? "nil"
        NovaHotkeyTelemetry.emit(
            "nova_auth_diagnostic device_id=\(deviceLabel) keychain_account=\(accountLabel) token_exists=\(tokenExists)"
        )
    }
}
