import SwiftUI

struct MacMemoryOverview: Decodable {
    let accessProfile: String
    let indexingPaused: Bool
    let localOnly: Bool
    let documentsDiscovered: Int
    let documentsIndexed: Int
    let chunks: Int
    let entities: Int
    let relationships: Int
    let pendingJobs: Int
    let embeddingHealth: String
    let embeddingAvailable: Bool
    let vaultPath: String
    let vaultInvisible: Bool
}

struct MacMemoryFact: Decodable, Identifiable {
    let id: String
    let subject: String
    let predicate: String
    let objectSummary: String
    let confidence: Double
    let userConfirmed: Bool
}

struct MacMemoryRelationship: Decodable, Identifiable {
    let id: String
    let relationType: String
    let confidence: Double
    let sourceEntityId: String
    let targetEntityId: String
    let userConfirmed: Bool
}

struct MacMemorySearchHit: Decodable, Identifiable {
    var id: String { memoryId }
    let kind: String
    let memoryId: String
    let summary: String
    let score: Double
    let provenance: String
}

struct MacMemorySearchResult: Decodable {
    let query: String
    let hits: [MacMemorySearchHit]
    let semanticAvailable: Bool
    let searchedSources: [String]
}

struct MemoryCenterView: View {
    @EnvironmentObject private var appState: MacAppState
    @State private var tab = 0
    @State private var overview: MacMemoryOverview?
    @State private var facts: [MacMemoryFact] = []
    @State private var relationships: [MacMemoryRelationship] = []
    @State private var searchQuery = ""
    @State private var searchResult: MacMemorySearchResult?
    @State private var loadError: String?
    @State private var exportPreview = ""

    var body: some View {
        VStack(spacing: 0) {
            Picker("Section", selection: $tab) {
                Text("Overview").tag(0)
                Text("Indexed").tag(1)
                Text("Facts").tag(2)
                Text("Relationships").tag(3)
                Text("Search").tag(4)
                Text("Privacy").tag(5)
            }
            .pickerStyle(.segmented)
            .padding()

            if let loadError {
                Text(loadError).font(.caption).foregroundStyle(.red).padding(.horizontal)
            }

            ScrollView {
                switch tab {
                case 0: overviewTab
                case 1: indexedTab
                case 2: factsTab
                case 3: relationshipsTab
                case 4: searchTab
                default: privacyTab
                }
            }
        }
        .navigationTitle("Memory Center")
        .task { await refreshAll() }
        .refreshable { await refreshAll() }
    }

    @ViewBuilder
    private var overviewTab: some View {
        if let overview {
            VStack(alignment: .leading, spacing: 8) {
                Label("Local-only memory", systemImage: "lock.shield")
                    .font(.headline)
                LabeledContent("Access profile", value: overview.accessProfile)
                LabeledContent("Indexing", value: overview.indexingPaused ? "Paused" : "Active")
                LabeledContent("Documents", value: "\(overview.documentsDiscovered) discovered / \(overview.documentsIndexed) indexed")
                LabeledContent("Chunks", value: "\(overview.chunks)")
                LabeledContent("Graph", value: "\(overview.entities) entities, \(overview.relationships) relationships")
                LabeledContent("Queue", value: "\(overview.pendingJobs) pending jobs")
                Text(overview.embeddingHealth).font(.caption).foregroundStyle(.secondary)
            }
            .padding()
        } else {
            ProgressView().padding()
        }
    }

    @ViewBuilder
    private var indexedTab: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Indexed folders").font(.headline)
            Button("Enable broad local knowledge") {
                Task { await setProfile("broad_local") }
            }
            Button("Use minimal profile") {
                Task { await setProfile("minimal") }
            }
            Button("Rescan (bounded)") {
                Task { await scan() }
            }
            Button(overview?.indexingPaused == true ? "Resume indexing" : "Pause indexing") {
                Task { await togglePause() }
            }
        }
        .padding()
    }

    @ViewBuilder
    private var factsTab: some View {
        if facts.isEmpty {
            Text("No personal facts yet.").foregroundStyle(.secondary).padding()
        } else {
            ForEach(facts) { fact in
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(fact.subject) → \(fact.objectSummary)").font(.body)
                    Text("\(fact.predicate) · confidence \(fact.confidence, specifier: "%.2f")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal)
                .padding(.vertical, 4)
            }
        }
    }

    @ViewBuilder
    private var relationshipsTab: some View {
        if relationships.isEmpty {
            Text("No relationships yet.").foregroundStyle(.secondary).padding()
        } else {
            ForEach(relationships) { rel in
                Text("\(rel.relationType) (\(rel.confidence, specifier: "%.2f"))")
                    .padding(.horizontal)
            }
        }
    }

    @ViewBuilder
    private var searchTab: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                TextField("Search local memory", text: $searchQuery)
                Button("Search") { Task { await search() } }
            }
            if let searchResult {
                Text("Semantic: \(searchResult.semanticAvailable ? "available" : "unavailable")")
                    .font(.caption)
                ForEach(searchResult.hits) { hit in
                    VStack(alignment: .leading) {
                        Text(hit.summary).font(.body)
                        Text("[\(hit.kind)] \(hit.provenance) · \(hit.score, specifier: "%.2f")")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding()
    }

    @ViewBuilder
    private var privacyTab: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Privacy").font(.headline)
            if let overview {
                Text("Vault path: \(overview.vaultPath)")
                    .font(.caption)
                Text("NOVA_VAULT is permanently invisible — no reads, search, metadata, or indexing.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Button("Export memory locally") { Task { await exportMemory() } }
            Button("Verify audit chain") { Task { await verifyAudit() } }
            if !exportPreview.isEmpty {
                Text(exportPreview).font(.caption2).textSelection(.enabled)
            }
        }
        .padding()
    }

    private func refreshAll() async {
        guard appState.isPaired else { return }
        do {
            overview = try await appState.api.fetchMemoryOverview()
            facts = try await appState.api.fetchMemoryFacts()
            relationships = try await appState.api.fetchMemoryRelationships()
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func setProfile(_ profile: String) async {
        do {
            overview = try await appState.api.setMemoryProfile(profile)
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func scan() async {
        do {
            _ = try await appState.api.scanMemorySources()
            await refreshAll()
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func togglePause() async {
        do {
            if overview?.indexingPaused == true {
                try await appState.api.resumeMemoryIndexing()
            } else {
                try await appState.api.pauseMemoryIndexing()
            }
            await refreshAll()
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func search() async {
        guard !searchQuery.isEmpty else { return }
        do {
            searchResult = try await appState.api.searchMemory(query: searchQuery)
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func exportMemory() async {
        do {
            let data = try await appState.api.exportMemory()
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            if let json = try? encoder.encode(data),
               let text = String(data: json, encoding: .utf8) {
                exportPreview = String(text.prefix(2000))
            }
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func verifyAudit() async {
        do {
            let valid = try await appState.api.verifyMemoryAuditIntegrity()
            exportPreview = "Audit chain integrity: \(valid ? "VALID" : "INVALID")"
        } catch {
            loadError = error.localizedDescription
        }
    }
}
