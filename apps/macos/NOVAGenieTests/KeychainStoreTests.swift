import XCTest
@testable import NOVAGenie

final class KeychainStoreTests: XCTestCase {
    private var service: String!

    override func setUp() {
        super.setUp()
        service = "com.nova.macos.test.\(UUID().uuidString)"
    }

    override func tearDown() {
        KeychainStore.delete(account: "arth-mac-client", service: service)
        super.tearDown()
    }

    func testRoundTripWithDeviceAccount() throws {
        try KeychainStore.save(token: "nova_cli_test", account: "arth-mac-client", service: service)
        XCTAssertEqual(KeychainStore.load(account: "arth-mac-client", service: service), "nova_cli_test")
    }

    func testDiscoverTokenOnService() throws {
        try KeychainStore.save(token: "discovered", account: "arth-mac-client", service: service)
        let discovered = KeychainStore.discoverToken(service: service)
        XCTAssertEqual(discovered?.account, "arth-mac-client")
        XCTAssertEqual(discovered?.token, "discovered")
    }
}
