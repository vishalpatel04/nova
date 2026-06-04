import XCTest
@testable import NOVAGenie

final class StreamStatusTests: XCTestCase {
    func testBadgeLabels() {
        XCTAssertEqual(MissionStreamBadge(streamingStatus: "live"), .live)
        XCTAssertEqual(MissionStreamBadge(streamingStatus: "degraded"), .degraded)
    }
}
