import AppKit
import Carbon
import Foundation

extension Notification.Name {
    static let novaHotkeySummon = Notification.Name("novaHotkeySummon")
}

/// System-wide hotkey via Carbon `RegisterEventHotKey` (no Accessibility permission).
@MainActor
final class GlobalHotkeyManager: ObservableObject {
    @Published var isEnabled: Bool {
        didSet { UserDefaults.standard.set(isEnabled, forKey: "nova_hotkey_enabled") }
    }
    @Published var registrationError: String?
    @Published var keyCode: UInt32 {
        didSet { UserDefaults.standard.set(keyCode, forKey: "nova_hotkey_keycode") }
    }
    @Published var modifiers: UInt32 {
        didSet { UserDefaults.standard.set(modifiers, forKey: "nova_hotkey_modifiers") }
    }

    private var hotKeyRef: EventHotKeyRef?
    private var eventHandlerRef: EventHandlerRef?
    private let hotKeyID = EventHotKeyID(signature: OSType(0x4E4F5641), id: 1)

    static let defaultKeyCode: UInt32 = UInt32(kVK_Space)
    static let defaultModifiers: UInt32 = UInt32(optionKey)

    init() {
        isEnabled = UserDefaults.standard.object(forKey: "nova_hotkey_enabled") as? Bool ?? true
        let storedCode = UserDefaults.standard.object(forKey: "nova_hotkey_keycode") as? UInt32
        keyCode = storedCode ?? Self.defaultKeyCode
        let storedMods = UserDefaults.standard.object(forKey: "nova_hotkey_modifiers") as? UInt32
        modifiers = storedMods ?? Self.defaultModifiers
    }

    func applyRegistration() {
        unregister()
        guard isEnabled else { return }
        var status = InstallEventHandler(
            GetApplicationEventTarget(),
            { _, event, _ -> OSStatus in
                var hotID = EventHotKeyID()
                GetEventParameter(
                    event,
                    EventParamName(kEventParamDirectObject),
                    EventParamType(typeEventHotKeyID),
                    nil,
                    MemoryLayout<EventHotKeyID>.size,
                    nil,
                    &hotID
                )
                if hotID.id == 1 {
                    DispatchQueue.main.async {
                        NotificationCenter.default.post(name: .novaHotkeySummon, object: nil)
                    }
                }
                return noErr
            },
            1,
            [EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))],
            nil,
            &eventHandlerRef
        )
        guard status == noErr else {
            registrationError = "Failed to install hotkey handler (\(status))"
            return
        }
        status = RegisterEventHotKey(keyCode, modifiers, hotKeyID, GetApplicationEventTarget(), 0, &hotKeyRef)
        if status == noErr {
            registrationError = nil
        } else if status == Int32(eventHotKeyExistsErr) {
            registrationError = "Hotkey already registered by another app"
        } else {
            registrationError = "Failed to register hotkey (\(status))"
        }
    }

    func unregister() {
        if let hotKeyRef {
            UnregisterEventHotKey(hotKeyRef)
            self.hotKeyRef = nil
        }
        if let eventHandlerRef {
            RemoveEventHandler(eventHandlerRef)
            self.eventHandlerRef = nil
        }
    }

    deinit {
        if let hotKeyRef { UnregisterEventHotKey(hotKeyRef) }
        if let eventHandlerRef { RemoveEventHandler(eventHandlerRef) }
    }
}
