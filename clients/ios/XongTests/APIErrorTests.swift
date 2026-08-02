import XCTest
@testable import Xong

final class APIErrorTests: XCTestCase {
    func testHTTPDiagnosticPreservesServerDetail() {
        XCTAssertEqual(
            APIError.http(503, "assistant unavailable").diagnostic,
            "HTTP 503 · assistant unavailable"
        )
    }

    func testUnauthorizedDiagnosticDoesNotInventDetail() {
        XCTAssertEqual(APIError.unauthorized("").diagnostic, "401")
    }
}
