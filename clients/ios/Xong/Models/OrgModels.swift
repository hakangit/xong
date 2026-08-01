import Foundation

/// Models for the four surfaces the web app grew: attachments, the assistant,
/// weave (org threads), and skill precedents.

struct Attachment: Codable, Identifiable, Equatable {
    let id: Int
    var taskId: Int
    /// "file" or "url"
    var kind: String
    var url: String?
    var filename: String?
    var contentType: String?
    var sizeBytes: Int?
    var createdBy: String
    var createdAt: Date

    var isLink: Bool { kind == "url" }

    var displayName: String {
        if let filename, !filename.isEmpty { return filename }
        if let url, !url.isEmpty { return url }
        return "#\(id)"
    }

    enum CodingKeys: String, CodingKey {
        case id
        case taskId = "task_id"
        case kind
        case url
        case filename
        case contentType = "content_type"
        case sizeBytes = "size_bytes"
        case createdBy = "created_by"
        case createdAt = "created_at"
    }
}

struct AssistantInfo: Codable, Equatable {
    var hasAssistant: Bool
    var name: String?

    enum CodingKeys: String, CodingKey {
        case hasAssistant = "has_assistant"
        case name
    }
}

struct AssistantReply: Codable, Equatable {
    var name: String
    var reply: String
}

/// Threads woven through other people's work: `passes` is the running count,
/// `threads` how many distinct ones.
struct Weave: Codable, Equatable {
    var threads: Int
    var passes: Int

    /// Mirrors weaveTier() in app.js — same thresholds, so the mark means the
    /// same thing on both clients.
    var tier: Int {
        switch passes {
        case 500...: return 5
        case 100..<500: return 4
        case 25..<100: return 3
        case 5..<25: return 2
        default: return 1
        }
    }
}

struct Person: Codable, Equatable {
    var username: String
    var displayName: String?
    var weave: Weave?

    enum CodingKeys: String, CodingKey {
        case username
        case displayName = "display_name"
        case weave
    }
}

struct Skill: Codable, Equatable {
    var id: Int?
    var slug: String?
    var name: String
}

struct SkillOwner: Codable, Equatable {
    var username: String
    var displayName: String?

    enum CodingKeys: String, CodingKey {
        case username
        case displayName = "display_name"
    }

    var name: String { displayName ?? username }
}

struct DecisionTrace: Codable, Identifiable, Equatable {
    let id: Int
    var kind: String
    var situation: String?
    var decision: String?
    var approver: String?
    var outcome: String?
    var supersededBy: Int?
    var trust: String?
    var tags: [String]
    var createdBy: String?
    var createdAt: Date?

    /// Boundaries read as standing rules; everything else is a past decision.
    var isBoundary: Bool { kind == "boundary" }

    enum CodingKeys: String, CodingKey {
        case id
        case kind
        case situation
        case decision
        case approver
        case outcome
        case supersededBy = "superseded_by"
        case trust
        case tags
        case createdBy = "created_by"
        case createdAt = "created_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        kind = (try? c.decode(String.self, forKey: .kind)) ?? "decision"
        situation = try? c.decode(String.self, forKey: .situation)
        decision = try? c.decode(String.self, forKey: .decision)
        approver = try? c.decode(String.self, forKey: .approver)
        outcome = try? c.decode(String.self, forKey: .outcome)
        supersededBy = try? c.decode(Int.self, forKey: .supersededBy)
        trust = try? c.decode(String.self, forKey: .trust)
        tags = (try? c.decode([String].self, forKey: .tags)) ?? []
        createdBy = try? c.decode(String.self, forKey: .createdBy)
        createdAt = try? c.decode(Date.self, forKey: .createdAt)
    }
}

struct SkillTraces: Codable, Equatable {
    var skill: Skill
    var owner: SkillOwner?
    var traces: [DecisionTrace]

    var boundaries: [DecisionTrace] { traces.filter(\.isBoundary) }
    var decisions: [DecisionTrace] { traces.filter { !$0.isBoundary } }
}
