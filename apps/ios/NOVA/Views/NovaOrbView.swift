import SwiftUI

struct NovaOrbView: View {
    @State private var isPulsing = false
    var size: CGFloat = 120
    var isActive: Bool = false
    var onTap: (() -> Void)?

    var body: some View {
        Button(action: { onTap?() }) {
            ZStack {
            Circle()
                .fill(DesignTokens.orbGlow)
                .frame(width: size * 1.4, height: size * 1.4)
                .scaleEffect(isPulsing ? 1.1 : 0.95)
                .animation(.easeInOut(duration: 2).repeatForever(autoreverses: true), value: isPulsing)

            Circle()
                .fill(
                    RadialGradient(
                        colors: [DesignTokens.novaBlue, DesignTokens.novaBlue.opacity(0.6)],
                        center: .center,
                        startRadius: 0,
                        endRadius: size / 2
                    )
                )
                .frame(width: size, height: size)
                .shadow(color: DesignTokens.novaBlue.opacity(0.5), radius: 20)

            Text("N")
                .font(.system(size: size * 0.35, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
            }
        }
        .buttonStyle(.plain)
        .onAppear { isPulsing = true }
    }
}

#Preview {
    NovaOrbView()
        .padding()
        .background(Color.black)
}
