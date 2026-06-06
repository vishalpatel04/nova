import Foundation

enum NOVAAPIError: LocalizedError {
    case unauthorized
    case http(Int, String)
    case decoding(Error)
    case network(Error)
    case keychain(OSStatus)
    case noToken
    case streaming(String)

    var errorDescription: String? {
        switch self {
        case .unauthorized: return "Authentication required. Pair this device or enter a token."
        case .http(let code, let body): return "Server error (\(code)): \(body)"
        case .decoding(let err): return "Invalid response: \(err.localizedDescription)"
        case .network(let err): return err.localizedDescription
        case .keychain(let status): return "Keychain error (\(status))"
        case .noToken: return "No device token stored"
        case .streaming(let msg): return msg
        }
    }
}

struct APIErrorBody: Decodable {
    struct Detail: Decodable {
        let code: String?
        let message: String
    }

    let error: Detail?
}
