import XCTest
@testable import NOVAGenie

final class KeychainStoreTests: XCTestCase {
    override func tearDown() {
        KeychainStore.delete(service: "com.nova.macos.test")
        super.tearDown()
    }

    func testRoundTrip() throws {
        try KeychainStore.save(token: "nova_cli_test", service: "com.nova.macos.test")
        XCTAssertEqual(KeychainStore.load(service: "com.nova.macos.test"), "nova_cli_test")
    }
}
