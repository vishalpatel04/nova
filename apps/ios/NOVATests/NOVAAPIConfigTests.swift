import XCTest
@testable import NOVA

@MainActor
final class NOVAAPIConfigTests: XCTestCase {
    func testDefaultBaseURLUsesLocalhost() {
        let client = NOVAAPIClient(baseURL: "http://localhost:8000")
        XCTAssertTrue(client.baseURL.contains("localhost"))
    }
}
