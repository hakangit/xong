import Foundation

/// What the app is pointed at. Local-only is a first-class mode, not a
/// fallback: it is the whole app for someone with no company server, and it is
/// what a reviewer sees without credentials.
@MainActor
final class AppConfiguration: ObservableObject {
    enum Mode: Equatable {
        case unset
        case local
        case server(Tenant)
    }

    @Published private(set) var mode: Mode = .unset
    @Published private(set) var identity: Identity?

    private let defaults = UserDefaults.standard
    private enum StorageKey {
        static let mode = "xong.mode"
        static let tenant = "xong.tenant"
        static let identity = "xong.identity"
        static let language = "xong.language"
    }

    init() {
        language = defaults.string(forKey: StorageKey.language)
        Strings.override = language
        load()
    }

    var tenant: Tenant? {
        if case .server(let tenant) = mode { return tenant }
        return nil
    }

    /// Cache key. Each server, and local-only, keeps its own store so one
    /// organization's tasks never surface in another's session.
    var namespace: String {
        guard let host = tenant?.apiBase.host else { return "local" }
        return host.replacingOccurrences(of: ":", with: "-")
    }

    /// Bumped whenever something the UI is built from changes, so views that
    /// cache state get rebuilt.
    @Published private(set) var revision = 0

    /// Explicit language choice; nil follows the device.
    @Published private(set) var language: String? {
        didSet { Strings.override = language }
    }

    func setLanguage(_ code: String?) {
        language = code
        if let code {
            defaults.set(code, forKey: StorageKey.language)
        } else {
            defaults.removeObject(forKey: StorageKey.language)
        }
        revision += 1
    }

    func chooseLocal() {
        mode = .local
        identity = nil
        defaults.set("local", forKey: StorageKey.mode)
        defaults.removeObject(forKey: StorageKey.tenant)
        defaults.removeObject(forKey: StorageKey.identity)
    }

    func connect(to tenant: Tenant, as identity: Identity?) {
        mode = .server(tenant)
        self.identity = identity
        defaults.set("server", forKey: StorageKey.mode)
        defaults.set(try? JSONEncoder().encode(tenant), forKey: StorageKey.tenant)
        defaults.set(try? JSONEncoder().encode(identity), forKey: StorageKey.identity)
    }

    /// Returns to onboarding and drops any tokens.
    func reset() {
        OIDCService.shared.signOut()
        mode = .unset
        identity = nil
        defaults.removeObject(forKey: StorageKey.mode)
        defaults.removeObject(forKey: StorageKey.tenant)
        defaults.removeObject(forKey: StorageKey.identity)
    }

    private func load() {
        switch defaults.string(forKey: StorageKey.mode) {
        case "local":
            mode = .local
        case "server":
            guard let data = defaults.data(forKey: StorageKey.tenant),
                  let tenant = try? JSONDecoder().decode(Tenant.self, from: data) else {
                mode = .unset
                return
            }
            mode = .server(tenant)
            if let data = defaults.data(forKey: StorageKey.identity) {
                identity = try? JSONDecoder().decode(Identity.self, from: data)
            }
        default:
            mode = .unset
        }
    }
}
