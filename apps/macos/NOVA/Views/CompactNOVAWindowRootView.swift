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
        .frame(minWidth: 380, idealWidth: 440, minHeight: 460, idealHeight: 560)
    }
}
