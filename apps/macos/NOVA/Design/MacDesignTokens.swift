import SwiftUI

struct MacDesignTokens {
    static let novaBlue = Color(red: 0.2, green: 0.5, blue: 0.95)
    static let background = Color(nsColor: .windowBackgroundColor)
    static let glassFill = Color.black.opacity(0.28)
    static let glassStroke = Color.white.opacity(0.12)
    static let chatPanel = Color(nsColor: .windowBackgroundColor).opacity(0.55)

    static func agentColor(for token: String) -> Color {
        switch token {
        case "nova_blue": return novaBlue
        case "mars_red": return Color(red: 0.9, green: 0.3, blue: 0.25)
        case "mercury_silver": return Color(red: 0.7, green: 0.75, blue: 0.8)
        case "jupiter_amber": return Color(red: 0.95, green: 0.7, blue: 0.2)
        case "venus_rose": return Color(red: 0.95, green: 0.5, blue: 0.65)
        case "saturn_gold": return Color(red: 0.85, green: 0.75, blue: 0.4)
        case "neptune_teal": return Color(red: 0.2, green: 0.7, blue: 0.7)
        default: return novaBlue
        }
    }
}
