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
        .frame(minWidth: 720, idealWidth: 920, maxWidth: 1200, minHeight: 560, idealHeight: 760, maxHeight: 1000)
    }
}
