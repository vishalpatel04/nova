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
        .frame(minWidth: 340, idealWidth: 380, minHeight: 380, idealHeight: 460)
    }
}
