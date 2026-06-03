import SwiftUI

struct MacDevicesView: View {
    private let devices = [
        ("M3 Worker", "online", "macos_worker"),
        ("iPhone", "online", "iphone_client"),
    ]

    var body: some View {
        List(devices, id: \.0) { device in
            HStack {
                VStack(alignment: .leading) {
                    Text(device.0).font(.headline)
                    Text(device.2.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Circle().fill(device.1 == "online" ? .green : .orange).frame(width: 8, height: 8)
            }
        }
        .navigationTitle("Devices")
    }
}

#Preview {
    MacDevicesView()
}
