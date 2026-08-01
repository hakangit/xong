import Foundation

extension Data {
    mutating func append(_ string: String) {
        append(Data(string.utf8))
    }
}

struct UserAccount: Codable, Equatable {
    let id: Int
    var username: String
    var displayName: String
    var tz: String

    enum CodingKeys: String, CodingKey {
        case id
        case username
        case displayName = "display_name"
        case tz
    }
}

struct TaskPatch: Codable {
    var title: String?
    var nextAction: String?
    var notes: String?
    var dueAt: Date?
    var whenWhere: String?

    enum CodingKeys: String, CodingKey {
        case title
        case nextAction = "next_action"
        case notes
        case dueAt = "due_at"
        case whenWhere = "when_where"
    }
}

enum APIError: LocalizedError {
    case unauthorized
    case http(Int)
    case transport(String)

    var errorDescription: String? {
        switch self {
        case .unauthorized: return Strings.t(.errSignIn)
        default: return Strings.t(.errOffline)
        }
    }
}

/// Talks to /api/v1 on whichever tenant the app is pointed at.
///
/// Auth depends on what the tenant's config document declared: an OIDC bearer
/// token, or nothing at all when a reverse proxy owns identity.
actor APIClient {
    private let tenant: Tenant
    private let session: URLSession

    init(tenant: Tenant, session: URLSession = .shared) {
        self.tenant = tenant
        self.session = session
    }

    // MARK: - Endpoints

    func today() async throws -> Today { try await get("/today") }
    func lists() async throws -> [TaskList] { try await get("/lists") }
    func weeklyRecap() async throws -> WeeklyRecap { try await get("/recap/weekly") }

    func createTask(_ task: NewTask) async throws -> TaskItem {
        try await send("POST", "/tasks", body: task)
    }

    func complete(_ id: Int) async throws -> TaskItem {
        try await send("POST", "/tasks/\(id)/complete", body: Empty())
    }

    func uncomplete(_ id: Int) async throws -> TaskItem {
        try await send("POST", "/tasks/\(id)/uncomplete", body: Empty())
    }

    func deleteTask(_ id: Int) async throws {
        _ = try await raw("DELETE", "/tasks/\(id)", body: nil)
    }

    func setFocus(_ ids: [Int]) async throws -> Focus {
        try await send("POST", "/focus", body: FocusBody(taskIds: ids))
    }

    func createList(name: String) async throws -> TaskList {
        try await send("POST", "/lists", body: ListBody(name: name))
    }

    func updateTask(_ id: Int, _ patch: TaskPatch) async throws -> TaskItem {
        try await send("PATCH", "/tasks/\(id)", body: patch)
    }

    // MARK: - Attachments

    func attachments(taskId: Int) async throws -> [Attachment] {
        try await get("/tasks/\(taskId)/attachments")
    }

    func addAttachmentLink(taskId: Int, url: String, filename: String?) async throws -> Attachment {
        try await send("POST", "/tasks/\(taskId)/attachments/link",
                       body: LinkBody(url: url, filename: filename))
    }

    func deleteAttachment(_ id: Int) async throws {
        _ = try await raw("DELETE", "/attachments/\(id)", body: nil)
    }

    /// Multipart upload. Field name is `file`, matching the web client.
    func uploadAttachment(taskId: Int, filename: String, mimeType: String,
                          data fileData: Data) async throws -> Attachment {
        let boundary = "xong-\(UUID().uuidString)"
        var body = Data()
        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n")
        body.append("Content-Type: \(mimeType)\r\n\r\n")
        body.append(fileData)
        body.append("\r\n--\(boundary)--\r\n")

        var request = try await request("POST", "/tasks/\(taskId)/attachments/file", body: body)
        request.setValue("multipart/form-data; boundary=\(boundary)",
                         forHTTPHeaderField: "Content-Type")

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw APIError.http((response as? HTTPURLResponse)?.statusCode ?? -1)
        }
        return try JSONCoding.decoder.decode(Attachment.self, from: data)
    }

    /// Downloads to a temp file. Deliberately not handed to Safari: the bearer
    /// token would not travel with it, so an authenticated file would 401.
    func downloadAttachment(_ attachment: Attachment) async throws -> URL {
        let data = try await raw("GET", "/attachments/\(attachment.id)/download", body: nil)
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("xong-downloads", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let target = directory.appendingPathComponent(attachment.displayName)
        try data.write(to: target, options: .atomic)
        return target
    }

    // MARK: - Assistant, weave, precedents

    func assistantInfo() async throws -> AssistantInfo { try await get("/assistant") }

    func commandAssistant(_ text: String) async throws -> AssistantReply {
        try await send("POST", "/assistant/command", body: CommandBody(text: text))
    }

    func person(_ username: String) async throws -> Person {
        try await get("/org/people/\(username.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? username)")
    }

    func me() async throws -> UserAccount { try await get("/me") }

    func skillTraces(slug: String) async throws -> SkillTraces {
        try await get("/skills/\(slug.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? slug)/traces")
    }

    func setTraceOutcome(_ id: Int, outcome: String) async throws {
        _ = try await raw("PATCH", "/traces/\(id)",
                          body: try JSONCoding.encoder.encode(OutcomeBody(outcome: outcome)))
    }

    private struct LinkBody: Codable {
        let url: String
        let filename: String?
    }

    private struct CommandBody: Codable {
        let text: String
    }

    private struct OutcomeBody: Codable {
        let outcome: String
    }

    // MARK: - Transport

    private struct Empty: Codable {}

    private struct FocusBody: Codable {
        let taskIds: [Int]
        enum CodingKeys: String, CodingKey { case taskIds = "task_ids" }
    }

    private struct ListBody: Codable {
        let name: String
    }

    private func url(_ path: String) -> URL {
        URL(string: tenant.apiBase.absoluteString + path) ?? tenant.apiBase
    }

    private func request(_ method: String, _ path: String, body: Data?) async throws -> URLRequest {
        var request = URLRequest(url: url(path))
        request.httpMethod = method
        request.timeoutInterval = 15
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if body != nil {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        request.httpBody = body

        if tenant.auth.type == .oidc, let token = await OIDCService.shared.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func raw(_ method: String, _ path: String, body: Data?) async throws -> Data {
        let request = try await request(method, path, body: body)

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.transport(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else { throw APIError.transport("no response") }

        if http.statusCode == 401 {
            // Access tokens expire; refresh once and retry before giving up,
            // otherwise the app silently degrades to cache and looks healthy
            // while syncing nothing.
            if await OIDCService.shared.refresh(tenant: tenant) {
                let retry = try await self.request(method, path, body: body)
                let (retryData, retryResponse) = try await session.data(for: retry)
                if let retryHTTP = retryResponse as? HTTPURLResponse,
                   (200..<300).contains(retryHTTP.statusCode) {
                    return retryData
                }
            }
            throw APIError.unauthorized
        }

        guard (200..<300).contains(http.statusCode) else {
            throw APIError.http(http.statusCode)
        }
        return data
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        let data = try await raw("GET", path, body: nil)
        return try JSONCoding.decoder.decode(T.self, from: data)
    }

    private func send<Body: Encodable, T: Decodable>(
        _ method: String, _ path: String, body: Body
    ) async throws -> T {
        let encoded = try JSONCoding.encoder.encode(body)
        let data = try await raw(method, path, body: encoded)
        return try JSONCoding.decoder.decode(T.self, from: data)
    }
}
