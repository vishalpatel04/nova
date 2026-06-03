import SwiftUI

struct DesignTokens {
    static let novaBlue = Color(red: 0.2, green: 0.5, blue: 0.95)
    static let marsRed = Color(red: 0.9, green: 0.3, blue: 0.25)
    static let mercurySilver = Color(red: 0.7, green: 0.75, blue: 0.8)
    static let jupiterAmber = Color(red: 0.95, green: 0.7, blue: 0.2)
    static let venusRose = Color(red: 0.95, green: 0.5, blue: 0.65)
    static let saturnGold = Color(red: 0.85, green: 0.75, blue: 0.4)
    static let neptuneTeal = Color(red: 0.2, green: 0.7, blue: 0.7)

    static let background = Color(.systemBackground)
    static let secondaryBackground = Color(.secondarySystemBackground)
    static let orbGlow = novaBlue.opacity(0.4)

    static func agentColor(for token: String) -> Color {
        switch token {
        case "nova_blue": return novaBlue
        case "mars_red": return marsRed
        case "mercury_silver": return mercurySilver
        case "jupiter_amber": return jupiterAmber
        case "venus_rose": return venusRose
        case "saturn_gold": return saturnGold
        case "neptune_teal": return neptuneTeal
        default: return novaBlue
        }
    }
}
