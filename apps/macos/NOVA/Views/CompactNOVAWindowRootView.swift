import SwiftUI

struct CompactNOVAWindowRootView: View {
    @EnvironmentObject private var appState: MacAppState

    var body: some View {
        Group {
            if appState.shouldShowPairing {
                CompactPairingView()
            } else {
                MenuBarView()
            }
        }
        .frame(
            minWidth: appState.chatLayoutMode == .warRoom ? 1000 : 720,
            idealWidth: appState.chatLayoutMode == .warRoom ? 1100 : 920,
            maxWidth: 1400,
            minHeight: appState.chatLayoutMode == .warRoom ? 760 : 560,
            idealHeight: 760,
            maxHeight: 1000
        )
    }
}
