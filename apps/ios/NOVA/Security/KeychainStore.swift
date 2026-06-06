import Foundation
import Security

enum KeychainStore {
    static func save(token: String, account: String, service: String = NovaDeviceIdentity.productionService) throws {
        let data = Data(token.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
        var add = query
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(add as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw NOVAAPIError.keychain(status)
        }
    }

    static func load(account: String, service: String = NovaDeviceIdentity.productionService) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func loadResolved(userDefaults: UserDefaults = .standard) -> String? {
        if let deviceId = NovaDeviceIdentity.resolvedDeviceId(userDefaults: userDefaults),
           let token = load(account: deviceId) {
            return token
        }
        return load(account: NovaDeviceIdentity.legacyAccount, service: NovaDeviceIdentity.legacyService)
    }

    static func delete(account: String, service: String = NovaDeviceIdentity.productionService) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
    }
}
