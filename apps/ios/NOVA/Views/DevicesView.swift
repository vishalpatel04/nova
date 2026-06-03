import SwiftUI

struct DevicesView: View {
    @State private var devices = MockData.devices

    var body: some View {
        List(devices) { device in
            VStack(alignment: .leading, spacing: 4) {
                Text(device.name)
                    .font(.headline)
                Text(device.deviceType.replacingOccurrences(of: "_", with: " ").capitalized)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                HStack {
                    Circle()
                        .fill(device.status == "online" ? .green : .orange)
                        .frame(width: 8, height: 8)
                    Text(device.status.capitalized)
                        .font(.caption)
                    Spacer()
                    Text("\(device.capabilities.count) capabilities")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle("Devices")
    }
}

#Preview {
    NavigationStack { DevicesView() }
}
