import Foundation

/// A Xong server's self-description, fetched from `/.well-known/xong-config`.
///
/// This is the autoconfig document: one small file per organization that tells
/// the client where the API is and how to authenticate. Everything else is
/// standard OIDC discovery against `issuer`.
struct Tenant: Codable, Equatable {
    let version: Int
    let name: String
    let apiBase: URL
    let auth: Auth
    /// Config v2. Absent on a v1 server, which predates the concept — treat
    /// that as "everything on", matching how the web client behaves.
    var capabilities: [String]?

    func has(_ capability: String) -> Bool {
        guard let capabilities else { return true }
        return capabilities.contains(capability)
    }

    struct Auth: Codable, Equatable {
        enum Kind: String, Codable {
            /// Standard OIDC Authorization Code + PKCE.
            case oidc
            /// Identity is injected by a reverse proxy (Authelia, oauth2-proxy).
            /// The client sends no token; the proxy handles the browser session.
            case none
        }

        let type: Kind
        let issuer: URL?
        let clientId: String?
        let scopes: String?

        var resolvedScopes: String {
            scopes ?? "openid profile email offline_access"
        }

        enum CodingKeys: String, CodingKey {
            case type
            case issuer
            case clientId = "client_id"
            case scopes
        }
    }

    enum CodingKeys: String, CodingKey {
        case version
        case name
        case apiBase = "api_base"
        case auth
        case capabilities
    }
}
/// HTTPS is required everywhere except loopback, so a developer can point the
/// app at a local server. An attacker who controls loopback already owns the
/// device, so this costs nothing.
func isTransportAcceptable(_ url: URL) -> Bool {
    switch url.scheme?.lowercased() {
    case "https":
        return true
    case "http":
        return ["localhost", "127.0.0.1", "::1"].contains(url.host ?? "")
    default:
        return false
    }
}

enum TenantError: LocalizedError {
    case notHTTPS
    case noConfigFound([URL])
    case malformed(String)

    var errorDescription: String? {
        switch self {
        case .notHTTPS:
            return Strings.t(.errNotHTTPS)
        case .noConfigFound:
            return Strings.t(.errNoConfig)
        case .malformed(let detail):
            return Strings.t(.errMalformed) + " (\(detail))"
        }
    }
}

/// Finds a server's config document from an email address or a URL, in the
/// spirit of email autoconfig — the user types what they already know.
enum TenantDiscovery {
    static let wellKnownPath = "/.well-known/xong-config"

    /// Probe order for `user-two@example.com`:
    ///   1. https://xong.example.com/.well-known/xong-config
    ///   2. https://example.com/.well-known/xong-config
    /// A URL is used directly (with the well-known path appended if it has none).
    static func candidates(for input: String) throws -> [URL] {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw TenantError.malformed("empty") }

        if trimmed.contains("@") {
            let domain = String(trimmed[trimmed.index(after: trimmed.lastIndex(of: "@")!)...])
                .trimmingCharacters(in: .whitespaces)
                .lowercased()
            guard !domain.isEmpty, domain.contains(".") else {
                throw TenantError.malformed("domain")
            }
            return [
                URL(string: "https://xong.\(domain)\(wellKnownPath)"),
                URL(string: "https://\(domain)\(wellKnownPath)"),
            ].compactMap { $0 }
        }

        // A bare host defaults to https, except loopback — a dev server on
        // 127.0.0.1 is plain http, and defaulting it to https just fails.
        let host = trimmed.split(separator: "/").first.map {
            $0.split(separator: ":").first.map(String.init) ?? String($0)
        } ?? trimmed
        let defaultScheme = ["localhost", "127.0.0.1"].contains(host) ? "http" : "https"
        let withScheme = trimmed.contains("://") ? trimmed : "\(defaultScheme)://\(trimmed)"

        guard let url = URL(string: withScheme) else { throw TenantError.malformed("url") }
        guard isTransportAcceptable(url) else { throw TenantError.notHTTPS }

        if url.path.isEmpty || url.path == "/" {
            guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
                throw TenantError.malformed("url")
            }
            components.path = wellKnownPath
            guard let wellKnown = components.url else { throw TenantError.malformed("url") }
            return [wellKnown]
        }
        return [url]
    }

    /// TXT record name and value prefix, e.g.
    ///   _xong.example.com  TXT  "xong=https://xong.example.com"
    static let txtPrefix = "_xong."
    static let txtValuePrefix = "xong="

    static func discover(input: String, session: URLSession = .shared) async throws -> Tenant {
        // An email-only domain has no A record and cannot serve a file, so the
        // DNS record is the only thing such an org can publish. It is tried
        // first, and it is also the only probe that can point at a different
        // domain than the one the user typed.
        if let domain = emailDomain(in: input),
           let url = try? await txtCandidate(for: domain),
           let tenant = try? await fetch(url, session: session) {
            return tenant
        }

        let urls = try candidates(for: input)
        for url in urls {
            guard let tenant = try? await fetch(url, session: session) else { continue }
            return tenant
        }
        throw TenantError.noConfigFound(urls)
    }

    static func emailDomain(in input: String) -> String? {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let at = trimmed.lastIndex(of: "@") else { return nil }
        let domain = String(trimmed[trimmed.index(after: at)...])
            .trimmingCharacters(in: .whitespaces)
            .lowercased()
        return domain.contains(".") ? domain : nil
    }

    static func txtCandidate(for domain: String) async throws -> URL {
        let records = await DNSTextLookup.txt(txtPrefix + domain)

        for record in records {
            let value = record.trimmingCharacters(in: .whitespaces)
            guard value.lowercased().hasPrefix(txtValuePrefix) else { continue }

            let target = String(value.dropFirst(txtValuePrefix.count))
                .trimmingCharacters(in: .whitespaces)
            guard var components = URLComponents(string: target) else { continue }
            // The record names a host; the well-known path is ours to append.
            if components.path.isEmpty || components.path == "/" {
                components.path = wellKnownPath
            }
            guard let url = components.url, isTransportAcceptable(url) else { continue }
            return url
        }
        throw TenantError.noConfigFound([])
    }

    static func fetch(_ url: URL, session: URLSession = .shared) async throws -> Tenant {
        guard isTransportAcceptable(url) else { throw TenantError.notHTTPS }

        var request = URLRequest(url: url)
        request.timeoutInterval = 10
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw TenantError.malformed("http")
        }

        let tenant = try JSONDecoder().decode(Tenant.self, from: data)
        try validate(tenant)
        return tenant
    }

    static func validate(_ tenant: Tenant) throws {
        guard tenant.version >= 1 else { throw TenantError.malformed("version") }
        guard isTransportAcceptable(tenant.apiBase) else { throw TenantError.notHTTPS }

        if tenant.auth.type == .oidc {
            // The issuer receives credentials, so it is held to HTTPS strictly.
            guard let issuer = tenant.auth.issuer, issuer.scheme?.lowercased() == "https" else {
                throw TenantError.notHTTPS
            }
            guard let clientId = tenant.auth.clientId, !clientId.isEmpty else {
                throw TenantError.malformed("client_id")
            }
        }
    }
}
