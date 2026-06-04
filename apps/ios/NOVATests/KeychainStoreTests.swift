import XCTest
@testable import NOVA

final class KeychainStoreTests: XCTestCase {
    override func tearDown() {
        KeychainStore.delete(service: "com.nova.ios.test")
        super.tearDown()
    }

    func testSaveLoadDelete() throws {
        try KeychainStore.save(token: "nova_cli_test_token", service: "com.nova.ios.test")
        XCTAssertEqual(KeychainStore.load(service: "com.nova.ios.test"), "nova_cli_test_token")
        KeychainStore.delete(service: "com.nova.ios.test")
        XCTAssertNil(KeychainStore.load(service: "com.nova.ios.test"))
    }
}
