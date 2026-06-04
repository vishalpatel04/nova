import XCTest
@testable import NOVA

final class KeychainStoreTests: XCTestCase {
    private var service: String!

    override func setUp() {
        super.setUp()
        service = "com.nova.ios.test.\(UUID().uuidString)"
    }

    override func tearDown() {
        KeychainStore.delete(account: "iphone-test", service: service)
        super.tearDown()
    }

    func testRoundTripWithDeviceAccount() throws {
        try KeychainStore.save(token: "nova_cli_test_token", account: "iphone-test", service: service)
        XCTAssertEqual(KeychainStore.load(account: "iphone-test", service: service), "nova_cli_test_token")
    }

    func testLoadResolvedUsesPersistedDeviceId() throws {
        let defaults = UserDefaults(suiteName: "NOVATests.Keychain.\(UUID().uuidString)")!
        defaults.set("iphone-test", forKey: NovaDeviceIdentity.deviceIdDefaultsKey)
        try KeychainStore.save(token: "resolved", account: "iphone-test", service: service)
        XCTAssertEqual(KeychainStore.loadResolved(userDefaults: defaults), "resolved")
    }
}
