import XCTest
@testable import NOVA

final class TimelineMergerTests: XCTestCase {
    func testDeduplicatesByEventId() {
        let a = TimelineEvent(id: "e1", eventType: "a", message: "one", sequenceNumber: 1, createdAt: nil)
        let b = TimelineEvent(id: "e1", eventType: "a", message: "two", sequenceNumber: 1, createdAt: nil)
        let merged = TimelineMerger.merge(existing: [a], incoming: [b])
        XCTAssertEqual(merged.count, 1)
        XCTAssertEqual(merged.first?.message, "two")
    }

    func testMaxSequence() {
        let events = [
            TimelineEvent(id: "1", eventType: "x", message: "", sequenceNumber: 3, createdAt: nil),
            TimelineEvent(id: "2", eventType: "x", message: "", sequenceNumber: 7, createdAt: nil),
        ]
        XCTAssertEqual(TimelineMerger.maxSequence(in: events, current: 2), 7)
    }
}
