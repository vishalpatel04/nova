import Foundation
import Security

enum NovaProviderName: String, CaseIterable, Identifiable {
    case openai
    case anthropic
    case qwen
    case deepseek
    case local

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .openai: return "OpenAI"
        case .anthropic: return "Anthropic"
        case .qwen: return "Qwen"
        case .deepseek: return "DeepSeek"
        case .local: return "Local / Ollama"
        }
    }

    var keychainAccount: String { "provider_key_\(rawValue)" }
}

enum NovaProviderSettings {
    private static let service = "com.nova.macos.providers"
    private static let defaults = UserDefaults.standard

    static let defaultProviderKey = "nova_default_provider"
    static let modelNameKey = "nova_model_name"
    static let localEndpointKey = "nova_local_endpoint"
    static let preferFreeLocalKey = "nova_prefer_free_local"

    static var defaultProvider: NovaProviderName {
        get {
            NovaProviderName(rawValue: defaults.string(forKey: defaultProviderKey) ?? "") ?? .local
        }
        set { defaults.set(newValue.rawValue, forKey: defaultProviderKey) }
    }

    static var modelName: String {
        get { defaults.string(forKey: modelNameKey) ?? "llama3.2" }
        set { defaults.set(newValue, forKey: modelNameKey) }
    }

    static var localEndpointURL: String {
        get { defaults.string(forKey: localEndpointKey) ?? "http://localhost:11434" }
        set { defaults.set(newValue, forKey: localEndpointKey) }
    }

    static var preferFreeLocal: Bool {
        get {
            if defaults.object(forKey: preferFreeLocalKey) == nil { return true }
            return defaults.bool(forKey: preferFreeLocalKey)
        }
        set { defaults.set(newValue, forKey: preferFreeLocalKey) }
    }

    static func saveAPIKey(_ key: String, provider: NovaProviderName) throws {
        let data = Data(key.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: provider.keychainAccount,
        ]
        SecItemDelete(query as CFDictionary)
        var add = query
        add[kSecValueData as String] = data
        let status = SecItemAdd(add as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw NSError(domain: "Keychain", code: Int(status))
        }
    }

    static func loadAPIKey(provider: NovaProviderName) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: provider.keychainAccount,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func deleteAPIKey(provider: NovaProviderName) {
        SecItemDelete([
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: provider.keychainAccount,
        ] as CFDictionary)
    }

    static func maskedKeyStatus(provider: NovaProviderName) -> String {
        loadAPIKey(provider: provider) == nil ? "Not set" : "••••••••"
    }

    static func isConfigured(provider: NovaProviderName) -> Bool {
        switch provider {
        case .local:
            return !localEndpointURL.isEmpty
        default:
            return loadAPIKey(provider: provider) != nil
        }
    }
}
