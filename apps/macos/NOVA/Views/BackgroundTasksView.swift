import SwiftUI

struct BackgroundTasksView: View {
    @EnvironmentObject private var appState: MacAppState
    @State private var tasks: [MacBackgroundTask] = []
    @State private var loadError: String?
    @State private var expandedTaskId: String?

    var body: some View {
        VStack(spacing: 0) {
            List {
                if let loadError {
                    Text(loadError).font(.caption).foregroundStyle(.red)
                }
                if tasks.isEmpty {
                    Text("No background tasks yet.")
                        .foregroundStyle(.secondary)
                }
                ForEach(tasks) { task in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(task.title).font(.headline)
                            Spacer()
                            Text(task.status).font(.caption).foregroundStyle(.secondary)
                        }
                        Text(task.taskType).font(.caption)
                        if let project = task.projectRoot {
                            Text(project).font(.caption2).lineLimit(1).foregroundStyle(.secondary)
                        }
                        Text("Schedule: \(task.scheduleKind) \(task.scheduleExpression)")
                            .font(.caption2)
                        if let next = task.nextRunAt {
                            Text("Next: \(next.formatted())").font(.caption2)
                        }
                        if let summary = task.lastResultSummary {
                            Text(summary).font(.caption).lineLimit(2)
                        }
                        HStack {
                            Button("Run now") { Task { await runNow(task.id) } }
                                .disabled(task.status == "paused" || task.status == "cancelled")
                            if task.status == "active" {
                                Button("Pause") { Task { await pause(task.id) } }
                            }
                            if task.status == "paused" {
                                Button("Resume") { Task { await resume(task.id) } }
                            }
                            if task.status != "cancelled" {
                                Button("Cancel") { Task { await cancel(task.id) } }
                            }
                            Button("History") { expandedTaskId = expandedTaskId == task.id ? nil : task.id }
                        }
                        .font(.caption)
                        if expandedTaskId == task.id {
                            TaskRunHistoryView(taskId: task.id)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
            HStack {
                Button("Refresh") { Task { await refresh() } }
                Spacer()
                Text("Active: \(appState.activeTasksCount)  Failed: \(appState.failedTasksCount)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(8)
        }
        .navigationTitle("Background Tasks")
        .task { await refresh() }
        .refreshable { await refresh() }
    }

    private func refresh() async {
        guard appState.isPaired else { return }
        do {
            tasks = try await appState.api.fetchBackgroundTasks()
            await appState.refreshBackgroundStatus()
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func runNow(_ id: String) async {
        do {
            _ = try await appState.api.runBackgroundTaskNow(taskId: id)
            await refresh()
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func pause(_ id: String) async {
        do {
            _ = try await appState.api.pauseBackgroundTask(taskId: id)
            await refresh()
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func resume(_ id: String) async {
        do {
            _ = try await appState.api.resumeBackgroundTask(taskId: id)
            await refresh()
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func cancel(_ id: String) async {
        do {
            _ = try await appState.api.cancelBackgroundTask(taskId: id)
            await refresh()
        } catch {
            loadError = error.localizedDescription
        }
    }
}

private struct TaskRunHistoryView: View {
    @EnvironmentObject private var appState: MacAppState
    let taskId: String
    @State private var runs: [MacBackgroundTaskRun] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(runs) { run in
                Text("\(run.status) — \(run.summary ?? "—")")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .task {
            runs = (try? await appState.api.fetchBackgroundTaskRuns(taskId: taskId)) ?? []
        }
    }
}
