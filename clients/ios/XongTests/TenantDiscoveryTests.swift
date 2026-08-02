import XCTest
@testable import Xong

final class TenantDiscoveryTests: XCTestCase {
    func testEmailDiscoveryPrefersXongHostThenRootDomain() throws {
        let candidates = try TenantDiscovery.candidates(for: "person@example.com")

        XCTAssertEqual(candidates.map(\.absoluteString), [
            "https://xong.example.com/.well-known/xong-config",
            "https://example.com/.well-known/xong-config",
        ])
    }

    func testRemotePlainHTTPIsRejectedBeforeCredentialsCanBeSent() {
        XCTAssertThrowsError(try TenantDiscovery.candidates(for: "http://tasks.example.com")) {
            guard case TenantError.notHTTPS = $0 else {
                return XCTFail("expected notHTTPS, received \($0)")
            }
        }
    }

    func testLoopbackPlainHTTPRemainsAvailableForDevelopment() throws {
        let candidates = try TenantDiscovery.candidates(for: "127.0.0.1:8000")

        XCTAssertEqual(
            candidates.map(\.absoluteString),
            ["http://127.0.0.1:8000/.well-known/xong-config"]
        )
    }

    func testOIDCTenantRequiresHTTPSIssuerAndClientID() {
        let tenant = Tenant(
            version: 2,
            name: "Example",
            apiBase: URL(string: "https://tasks.example.com/api/v1")!,
            auth: Tenant.Auth(
                type: .oidc,
                issuer: URL(string: "http://id.example.com"),
                clientId: "xong-ios",
                scopes: nil
            ),
            capabilities: []
        )

        XCTAssertThrowsError(try TenantDiscovery.validate(tenant)) {
            guard case TenantError.notHTTPS = $0 else {
                return XCTFail("expected notHTTPS, received \($0)")
            }
        }
    }

    func testMissingCapabilitiesRetainsVersionOneCompatibility() {
        let tenant = Tenant(
            version: 1,
            name: "Example",
            apiBase: URL(string: "https://tasks.example.com/api/v1")!,
            auth: Tenant.Auth(type: .none, issuer: nil, clientId: nil, scopes: nil),
            capabilities: nil
        )

        XCTAssertTrue(tenant.has("org"))
    }
}
