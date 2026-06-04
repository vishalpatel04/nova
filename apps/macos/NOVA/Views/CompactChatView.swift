import SwiftUI

struct CompactChatView: View {
    var body: some View {
        GenieChatView(compact: true)
    }
}

struct ExpandedChatView: View {
    var body: some View {
        GenieChatView(compact: false)
    }
}
