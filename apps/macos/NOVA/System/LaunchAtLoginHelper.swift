import Foundation
import ServiceManagement

enum LaunchAtLoginHelper {
    static var isEnabled: Bool {
        SMAppService.mainApp.status == .enabled
    }

    static var statusLabel: String {
        switch SMAppService.mainApp.status {
        case .enabled: return "Enabled"
        case .requiresApproval: return "Requires approval in System Settings"
        case .notRegistered: return "Not registered"
        case .notFound: return "App not found"
        @unknown default: return "Unknown"
        }
    }

    static func setEnabled(_ enabled: Bool) throws {
        if enabled {
            try SMAppService.mainApp.register()
        } else {
            try SMAppService.mainApp.unregister()
        }
    }
}
