import Foundation

struct NovaOrbStateMachine {
    private(set) var isListening = false
    private(set) var isActive = false

    mutating func beginListening() {
        isListening = true
        isActive = true
    }

    mutating func endListening() {
        isListening = false
        isActive = false
    }
}
