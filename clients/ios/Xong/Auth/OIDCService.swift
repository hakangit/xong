import AuthenticationServices
import CryptoKit
import Foundation
import os.log

private let logger = Logger(subsystem: "app.xong.client", category: "Auth")

struct Identity: Codable, Equatable {
    let username: String
    let displayName: String?

    var name: String { displayName ?? username }
}

enum OIDCError: LocalizedError {
    case notConfigured
    case discoveryFailed
    case cancelled
    case failed(String)

    var errorDescription: String? {
        switch self {
        case .cancelled: return nil
        default: return Strings.t(.errSignIn)
        }
    }
}

/// Authorization Code + PKCE against whatever OIDC provider the tenant names.
///
/// Ported from the Zitadel flow in dhp-ios, with the hardcoded endpoints
/// replaced by runtime `/.well-known/openid-configuration` discovery — that is
/// what makes this work for any provider, not just Example organization's Zitadel.
@MainActor
final class OIDCService: NSObject {
    static let shared = OIDCService()

    static let redirectURI = "xong://oauth-callback"
    static let callbackScheme = "xong"

    private let keychain = KeychainService.shared
    private var webSession: ASWebAuthenticationSession?

    var accessToken: String? { keychain.readString(key: KeychainService.Keys.accessToken) }

    private struct ProviderMetadata: Codable {
        let authorizationEndpoint: URL
        let tokenEndpoint: URL

        enum CodingKeys: String, CodingKey {
            case authorizationEndpoint = "authorization_endpoint"
            case tokenEndpoint = "token_endpoint"
        }
    }

    private struct TokenResponse: Codable {
        let accessToken: String
        let refreshToken: String?
        let idToken: String?

        enum CodingKeys: String, CodingKey {
            case accessToken = "access_token"
            case refreshToken = "refresh_token"
            case idToken = "id_token"
        }
    }

    private func metadata(for issuer: URL) async throws -> ProviderMetadata {
        let url = issuer.appendingPathComponent(".well-known/openid-configuration")
        guard let (data, response) = try? await URLSession.shared.data(from: url),
              let http = response as? HTTPURLResponse, http.statusCode == 200,
              let metadata = try? JSONDecoder().decode(ProviderMetadata.self, from: data) else {
            throw OIDCError.discoveryFailed
        }
        return metadata
    }

    func signIn(tenant: Tenant) async throws -> Identity {
        guard let issuer = tenant.auth.issuer, let clientId = tenant.auth.clientId else {
            throw OIDCError.notConfigured
        }
        let metadata = try await metadata(for: issuer)

        let verifier = Self.randomURLSafe(64)
        let state = Self.randomURLSafe(16)

        var components = URLComponents(url: metadata.authorizationEndpoint,
                                       resolvingAgainstBaseURL: false)!
        components.queryItems = [
            URLQueryItem(name: "client_id", value: clientId),
            URLQueryItem(name: "redirect_uri", value: Self.redirectURI),
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "scope", value: tenant.auth.resolvedScopes),
            URLQueryItem(name: "code_challenge", value: Self.s256(verifier)),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
            URLQueryItem(name: "state", value: state),
        ]

        let callbackURL: URL = try await withCheckedThrowingContinuation { continuation in
            let session = ASWebAuthenticationSession(
                url: components.url!,
                callbackURLScheme: Self.callbackScheme
            ) { url, error in
                if let url {
                    continuation.resume(returning: url)
                } else if let error = error as? ASWebAuthenticationSessionError,
                          error.code == .canceledLogin {
                    continuation.resume(throwing: OIDCError.cancelled)
                } else {
                    continuation.resume(throwing: OIDCError.failed(error?.localizedDescription ?? "unknown"))
                }
            }
            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = false
            self.webSession = session
            session.start()
        }

        let items = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false)?.queryItems
        guard items?.first(where: { $0.name == "state" })?.value == state else {
            throw OIDCError.failed("state mismatch")
        }
        guard let code = items?.first(where: { $0.name == "code" })?.value else {
            throw OIDCError.failed("no authorization code")
        }

        let tokens = try await exchange(at: metadata.tokenEndpoint, body: [
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": Self.redirectURI,
            "client_id": clientId,
            "code_verifier": verifier,
        ])
        store(tokens)

        return Self.identity(fromIDToken: tokens.idToken)
            ?? Identity(username: "sso", displayName: nil)
    }

    /// Refresh the access token. Returns false when refresh is not possible —
    /// the caller then sends the user back through sign-in.
    func refresh(tenant: Tenant) async -> Bool {
        guard let issuer = tenant.auth.issuer, let clientId = tenant.auth.clientId,
              let refreshToken = keychain.readString(key: KeychainService.Keys.refreshToken) else {
            return false
        }
        do {
            let metadata = try await metadata(for: issuer)
            let tokens = try await exchange(at: metadata.tokenEndpoint, body: [
                "grant_type": "refresh_token",
                "refresh_token": refreshToken,
                "client_id": clientId,
            ])
            store(tokens)
            return true
        } catch {
            logger.error("token refresh failed: \(error.localizedDescription)")
            return false
        }
    }

    func signOut() {
        keychain.delete(key: KeychainService.Keys.accessToken)
        keychain.delete(key: KeychainService.Keys.refreshToken)
    }

    private func exchange(at endpoint: URL, body: [String: String]) async throws -> TokenResponse {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")

        var allowed = CharacterSet.alphanumerics
        allowed.insert(charactersIn: "-._~")
        request.httpBody = body
            .map { "\($0.key)=\($0.value.addingPercentEncoding(withAllowedCharacters: allowed) ?? $0.value)" }
            .joined(separator: "&")
            .data(using: .utf8)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            let detail = String(data: data, encoding: .utf8) ?? ""
            throw OIDCError.failed("token exchange: \(detail.prefix(200))")
        }
        return try JSONDecoder().decode(TokenResponse.self, from: data)
    }

    private func store(_ tokens: TokenResponse) {
        keychain.save(key: KeychainService.Keys.accessToken, string: tokens.accessToken)
        if let refresh = tokens.refreshToken {
            keychain.save(key: KeychainService.Keys.refreshToken, string: refresh)
        }
    }

    /// Reads display claims out of the ID token. This is not a security
    /// decision — the server validates the token independently — so an
    /// unverified local decode is fine here.
    private static func identity(fromIDToken idToken: String?) -> Identity? {
        guard let idToken else { return nil }
        let parts = idToken.split(separator: ".")
        guard parts.count == 3 else { return nil }

        var payload = String(parts[1])
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        while payload.count % 4 != 0 { payload += "=" }

        guard let data = Data(base64Encoded: payload),
              let claims = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        let username = claims["preferred_username"] as? String
            ?? claims["email"] as? String
            ?? "sso"
        return Identity(username: username, displayName: claims["name"] as? String)
    }

    private static func randomURLSafe(_ count: Int) -> String {
        var bytes = [UInt8](repeating: 0, count: count)
        _ = SecRandomCopyBytes(kSecRandomDefault, count, &bytes)
        return Data(bytes).base64URLEncoded
    }

    static func s256(_ verifier: String) -> String {
        Data(SHA256.hash(data: Data(verifier.utf8))).base64URLEncoded
    }
}

extension OIDCService: ASWebAuthenticationPresentationContextProviding {
    nonisolated func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        MainActor.assumeIsolated {
            let scene = UIApplication.shared.connectedScenes.first { $0.activationState == .foregroundActive }
            return (scene as? UIWindowScene)?.keyWindow ?? ASPresentationAnchor()
        }
    }
}

private extension Data {
    var base64URLEncoded: String {
        base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}
