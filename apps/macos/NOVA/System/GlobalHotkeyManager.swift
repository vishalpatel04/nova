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
        didSet {
            userDefaults.set(isEnabled, forKey: Keys.enabled)
            if !isEnabled {
                unregister()
            }
        }
    }
    @Published var registrationError: String?
    @Published var keyCode: UInt32 {
        didSet { userDefaults.set(keyCode, forKey: Keys.keyCode) }
    }
    @Published var modifiers: UInt32 {
        didSet { userDefaults.set(modifiers, forKey: Keys.modifiers) }
    }

    private(set) var registrationAttemptCount = 0
    private(set) var isHotkeyRegistered = false
    private(set) var hasRegisteredAtStartup = false

    private var hotKeyRef: EventHotKeyRef?
    private var eventHandlerRef: EventHandlerRef?
    private let hotKeyID = EventHotKeyID(signature: OSType(0x4E4F5641), id: 1)
    private let userDefaults: UserDefaults
    private let forcedRegistrationStatus: OSStatus?

    private enum Keys {
        static let enabled = "nova_hotkey_enabled"
        static let keyCode = "nova_hotkey_keycode"
        static let modifiers = "nova_hotkey_modifiers"
        static let migratedCtrlOptSpace = "nova_hotkey_migrated_ctrl_opt_space"
    }

    static let defaultKeyCode: UInt32 = UInt32(kVK_Space)
    static let defaultModifiers: UInt32 = UInt32(optionKey | controlKey)
    static let defaultShortcutLabel = "⌃⌥ Space"

    /// Previous shipped defaults — migrated to Control+Option+Space.
    static let legacyOptionSKeyCode: UInt32 = UInt32(kVK_ANSI_S)
    static let legacyOptionSpaceKeyCode: UInt32 = UInt32(kVK_Space)
    static let legacyOptionOnlyModifiers: UInt32 = UInt32(optionKey)

    init(userDefaults: UserDefaults = .standard, forcedRegistrationStatus: OSStatus? = nil) {
        self.userDefaults = userDefaults
        self.forcedRegistrationStatus = forcedRegistrationStatus
        isEnabled = userDefaults.object(forKey: Keys.enabled) as? Bool ?? true
        Self.migrateLegacyShortcutIfNeeded(userDefaults: userDefaults)
        let storedCode = userDefaults.object(forKey: Keys.keyCode) as? UInt32
        keyCode = storedCode ?? Self.defaultKeyCode
        let storedMods = userDefaults.object(forKey: Keys.modifiers) as? UInt32
        modifiers = storedMods ?? Self.defaultModifiers
    }

    static func isLegacyDefaultShortcut(keyCode: UInt32, modifiers: UInt32) -> Bool {
        let optionS = keyCode == legacyOptionSKeyCode && modifiers == legacyOptionOnlyModifiers
        let optionSpace = keyCode == legacyOptionSpaceKeyCode && modifiers == legacyOptionOnlyModifiers
        return optionS || optionSpace
    }

    static func migrateLegacyShortcutIfNeeded(userDefaults: UserDefaults) {
        guard userDefaults.bool(forKey: Keys.migratedCtrlOptSpace) == false else { return }
        guard let storedCode = userDefaults.object(forKey: Keys.keyCode) as? UInt32,
              let storedMods = userDefaults.object(forKey: Keys.modifiers) as? UInt32
        else { return }
        guard isLegacyDefaultShortcut(keyCode: storedCode, modifiers: storedMods) else { return }
        userDefaults.set(defaultKeyCode, forKey: Keys.keyCode)
        userDefaults.set(defaultModifiers, forKey: Keys.modifiers)
        userDefaults.set(true, forKey: Keys.migratedCtrlOptSpace)
    }

    /// Registers the global hotkey once during app startup.
    func registerAtStartup() {
        guard !hasRegisteredAtStartup else { return }
        hasRegisteredAtStartup = true
        applyRegistration()
    }

    func applyRegistration() {
        if isHotkeyRegistered {
            NovaHotkeyTelemetry.emit("nova_hotkey_register_skipped_duplicate")
            return
        }
        unregister()
        guard isEnabled else { return }

        registrationAttemptCount += 1
        NovaHotkeyTelemetry.emit("nova_hotkey_register_attempt")

        if let forcedRegistrationStatus {
            applyRegistrationStatus(forcedRegistrationStatus)
            return
        }

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
            NovaHotkeyTelemetry.emit("nova_hotkey_registration_failed")
            return
        }
        status = RegisterEventHotKey(keyCode, modifiers, hotKeyID, GetApplicationEventTarget(), 0, &hotKeyRef)
        applyRegistrationStatus(status)
    }

    private func applyRegistrationStatus(_ status: OSStatus) {
        if status == noErr {
            registrationError = nil
            isHotkeyRegistered = true
            NovaHotkeyTelemetry.emit("nova_hotkey_registered")
        } else if status == Int32(eventHotKeyExistsErr) {
            registrationError = "Hotkey already registered by another app"
            removeEventHandler()
            NovaHotkeyTelemetry.emit("nova_hotkey_registration_failed")
        } else {
            registrationError = "Failed to register hotkey (\(status))"
            removeEventHandler()
            NovaHotkeyTelemetry.emit("nova_hotkey_registration_failed")
        }
    }

    func unregister() {
        if let hotKeyRef {
            UnregisterEventHotKey(hotKeyRef)
            self.hotKeyRef = nil
        }
        removeEventHandler()
        isHotkeyRegistered = false
    }

    private func removeEventHandler() {
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
