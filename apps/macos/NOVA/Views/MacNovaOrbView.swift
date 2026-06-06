import SwiftUI

struct MacNovaOrbView: View {
    @State private var isPulsing = false
    var size: CGFloat = 48
    var isActive: Bool = false
    var onTap: (() -> Void)?

    var body: some View {
        Button(action: { onTap?() }) {
            ZStack {
            Circle()
                .fill(MacDesignTokens.novaBlue.opacity(0.3))
                .frame(width: size * 1.3, height: size * 1.3)
                .scaleEffect(isPulsing ? 1.08 : 0.95)
                .animation(.easeInOut(duration: 2).repeatForever(autoreverses: true), value: isPulsing)

            Circle()
                .fill(MacDesignTokens.novaBlue)
                .frame(width: size, height: size)

            Text("N")
                .font(.system(size: size * 0.4, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
            }
        }
        .buttonStyle(.plain)
        .onAppear { isPulsing = true }
    }
}

#Preview {
    MacNovaOrbView()
        .padding()
}
