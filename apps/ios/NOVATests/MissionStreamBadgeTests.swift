import XCTest
@testable import NOVA

final class MissionStreamBadgeTests: XCTestCase {
    func testStreamingStatusMapping() {
        XCTAssertEqual(MissionStreamBadge(streamingStatus: "live"), .live)
        XCTAssertEqual(MissionStreamBadge(streamingStatus: "reconnecting"), .reconnecting)
        XCTAssertEqual(MissionStreamBadge(streamingStatus: "offline"), .offline)
    }
}
