import XCTest
@testable import NOVAGenie

final class MacTimelineMergerTests: XCTestCase {
    func testDeduplicatesEvents() {
        let a = MacTimelineEvent(id: "e1", eventType: "a", message: "one", sequenceNumber: 1)
        let b = MacTimelineEvent(id: "e1", eventType: "a", message: "two", sequenceNumber: 2)
        let merged = MacTimelineMerger.merge(existing: [a], incoming: [b])
        XCTAssertEqual(merged.count, 1)
    }
}
