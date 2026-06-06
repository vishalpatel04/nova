import XCTest
@testable import NOVA

final class AppIntentMetadataTests: XCTestCase {
    func testListenIntentOpensApp() {
        XCTAssertTrue(NOVAListenIntent.openAppWhenRun)
    }
}
