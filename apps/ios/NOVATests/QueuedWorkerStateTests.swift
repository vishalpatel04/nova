import XCTest
@testable import NOVA

final class QueuedWorkerStateTests: XCTestCase {
    func testQueuedMissionMessage() {
        let message = QueuedWorkerDisplay.message(for: "queued_waiting_for_worker")
        XCTAssertTrue(message.contains("queued"))
    }
}
