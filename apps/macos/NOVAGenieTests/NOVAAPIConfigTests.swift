import XCTest
@testable import NOVAGenie

@MainActor
final class NOVAAPIConfigTests: XCTestCase {
    func testSharedClientBaseURL() {
        XCTAssertFalse(NOVAAPIClient.shared.baseURL.isEmpty)
    }
}
