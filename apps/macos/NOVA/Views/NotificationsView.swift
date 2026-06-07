import SwiftUI
import UserNotifications

struct NotificationsView: View {
    @EnvironmentObject private var appState: MacAppState
    @State private var notifications: [MacNotificationItem] = []
    @State private var unreadCount = 0
    @State private var loadError: String?

    var body: some View {
        VStack(spacing: 0) {
            List {
                if let loadError {
                    Text(loadError).font(.caption).foregroundStyle(.red)
                }
                if notifications.isEmpty {
                    Text("No notifications.")
                        .foregroundStyle(.secondary)
                }
                ForEach(notifications) { item in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(item.title).font(.headline)
                            Spacer()
                            if !item.read {
                                Text("unread").font(.caption2).foregroundStyle(.orange)
                            }
                        }
                        Text(item.summary).font(.caption)
                        Text(item.createdAt.formatted()).font(.caption2).foregroundStyle(.secondary)
                        HStack {
                            if !item.read {
                                Button("Mark read") { Task { await markRead(item.id) } }
                                    .font(.caption)
                            }
                            if let taskId = item.taskId {
                                NavigationLink("Task") {
                                    BackgroundTaskDetailLoader(taskId: taskId)
                                }
                                .font(.caption)
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
            HStack {
                Button("Refresh") { Task { await refresh() } }
                Button("Mark all read") { Task { await markAllRead() } }
                Spacer()
                Text("\(unreadCount) unread")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(8)
        }
        .navigationTitle("Notifications")
        .task { await refresh() }
        .refreshable { await refresh() }
    }

    private func refresh() async {
        guard appState.isPaired else { return }
        do {
            let payload = try await appState.api.fetchNotifications()
            notifications = payload.notifications
            unreadCount = payload.unreadCount
            appState.unreadNotificationsCount = unreadCount
            loadError = nil
            await maybeShowLocalAlert(for: payload.notifications.first)
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func markRead(_ id: String) async {
        do {
            _ = try await appState.api.markNotificationRead(notificationId: id)
            await refresh()
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func markAllRead() async {
        do {
            _ = try await appState.api.markAllNotificationsRead()
            await refresh()
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func maybeShowLocalAlert(for item: MacNotificationItem?) async {
        guard let item, !item.read else { return }
        guard item.notificationType.contains("failed") || item.notificationType.contains("reminder") else { return }
        let center = UNUserNotificationCenter.current()
        let granted = try? await center.requestAuthorization(options: [.alert, .sound])
        guard granted == true else { return }
        let content = UNMutableNotificationContent()
        content.title = item.title
        content.body = String(item.summary.prefix(200))
        let request = UNNotificationRequest(
            identifier: item.id,
            content: content,
            trigger: nil
        )
        try? await center.add(request)
    }
}

private struct BackgroundTaskDetailLoader: View {
    @EnvironmentObject private var appState: MacAppState
    let taskId: String
    @State private var task: MacBackgroundTask?

    var body: some View {
        Group {
            if let task {
                VStack(alignment: .leading, spacing: 8) {
                    Text(task.title).font(.headline)
                    Text(task.taskType)
                    Text("Status: \(task.status)")
                    if let summary = task.lastResultSummary {
                        Text(summary)
                    }
                }
                .padding()
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Task")
        .task {
            task = try? await appState.api.fetchBackgroundTask(taskId: taskId)
        }
    }
}
