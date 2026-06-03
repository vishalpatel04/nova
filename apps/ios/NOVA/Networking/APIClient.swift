import Foundation

actor APIClient {
    static let shared = APIClient()
    var baseURL: String = "http://localhost:8000"

    func fetchAgents() async throws -> [Agent] {
        let url = URL(string: "\(baseURL)/api/v1/agents")!
        let (data, response) = try await URLSession.shared.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            return MockData.agents
        }
        return try JSONDecoder().decode([Agent].self, from: data)
    }

    func fetchDevices() async throws -> [Device] {
        let url = URL(string: "\(baseURL)/api/v1/devices")!
        let (data, response) = try await URLSession.shared.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            return MockData.devices
        }
        return try JSONDecoder().decode([Device].self, from: data)
    }

    func createMission(type: String, title: String) async throws -> Mission {
        var request = URLRequest(url: URL(string: "\(baseURL)/api/v1/missions")!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body = ["mission_type": type, "title": title]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, _) = try await URLSession.shared.data(for: request)
        return try JSONDecoder().decode(Mission.self, from: data)
    }
}
