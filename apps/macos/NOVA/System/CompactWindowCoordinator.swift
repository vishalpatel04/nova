import AppKit
import SwiftUI

@MainActor
protocol CompactWindowCoordinating: AnyObject {
    var stableWindowIdentifier: String { get }
    var createCount: Int { get }
    var openCount: Int { get }
    var focusCount: Int { get }

    func open(appState: MacAppState, mode: MacAppState.CompactWindowMode)
}

@MainActor
final class CompactWindowCoordinator: NSObject, CompactWindowCoordinating, NSWindowDelegate {
    static let defaultWidth: CGFloat = 920
    static let defaultHeight: CGFloat = 760
    static let minimumWidth: CGFloat = 720
    static let minimumHeight: CGFloat = 560

    let stableWindowIdentifier = "com.nova.macos.genie.compact"
    private(set) var createCount = 0
    private(set) var openCount = 0
    private(set) var focusCount = 0

    private var windowController: NSWindowController?

    func open(appState: MacAppState, mode: MacAppState.CompactWindowMode) {
        appState.compactWindowMode = mode

        if let window = windowController?.window {
            openCount += 1
            focusCount += 1
            focus(window)
            NovaHotkeyTelemetry.emit("nova_compact_chat_focused")
            return
        }

        createCount += 1
        openCount += 1
        let root = CompactNOVAWindowRootView()
            .environmentObject(appState)
        let hosting = NSHostingController(rootView: root)
        let window = NSWindow(contentViewController: hosting)
        window.identifier = NSUserInterfaceItemIdentifier(stableWindowIdentifier)
        window.title = "NOVA"
        window.setContentSize(NSSize(width: Self.defaultWidth, height: Self.defaultHeight))
        window.minSize = NSSize(width: Self.minimumWidth, height: Self.minimumHeight)
        window.styleMask = [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView]
        window.titlebarAppearsTransparent = true
        window.isReleasedWhenClosed = false
        window.center()
        window.delegate = self

        let controller = NSWindowController(window: window)
        windowController = controller
        NovaHotkeyTelemetry.emit("nova_compact_chat_created")
        focus(window)
        NovaHotkeyTelemetry.emit("nova_compact_chat_opened")
    }

    func windowWillClose(_ notification: Notification) {
        windowController = nil
    }

    private func focus(_ window: NSWindow) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
        window.orderFrontRegardless()
    }
}
