import Foundation

/// Mirrors src/xong/schemas.py. Snake_case is mapped explicitly rather than via
/// a global key strategy so a rename on either side fails loudly at decode.

struct TaskItem: Codable, Identifiable, Equatable {
    let id: Int
    var listId: Int
    var title: String
    var nextAction: String?
    var notes: String?
    var dueAt: Date?
    var whenWhere: String?
    var position: Int
    var createdBy: String
    var completedAt: Date?
    var createdAt: Date
    var looksVague: Bool

    var isDone: Bool { completedAt != nil }

    enum CodingKeys: String, CodingKey {
        case id
        case listId = "list_id"
        case title
        case nextAction = "next_action"
        case notes
        case dueAt = "due_at"
        case whenWhere = "when_where"
        case position
        case createdBy = "created_by"
        case completedAt = "completed_at"
        case createdAt = "created_at"
        case looksVague = "looks_vague"
    }
}

struct TaskList: Codable, Identifiable, Equatable {
    let id: Int
    var ownerId: Int
    var name: String
    var position: Int
    var archived: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case ownerId = "owner_id"
        case name
        case position
        case archived
    }
}

struct Today: Codable, Equatable {
    var date: String
    var streak: Int
    var focus: [TaskItem]
    var dueToday: [TaskItem]
    var overdue: [TaskItem]
    var defaultList: TaskList
    var defaultTasks: [TaskItem]

    enum CodingKeys: String, CodingKey {
        case date
        case streak
        case focus
        case dueToday = "due_today"
        case overdue
        case defaultList = "default_list"
        case defaultTasks = "default_tasks"
    }
}

struct DayWins: Codable, Equatable, Identifiable {
    var date: String
    var count: Int
    var titles: [String]

    var id: String { date }
}

struct WeeklyRecap: Codable, Equatable {
    var streak: Int
    var total: Int
    var bestDay: String?
    var bestDayCount: Int
    var days: [DayWins]

    enum CodingKeys: String, CodingKey {
        case streak
        case total
        case bestDay = "best_day"
        case bestDayCount = "best_day_count"
        case days
    }
}

struct Focus: Codable, Equatable {
    var date: String
    var taskIds: [Int]
    var tasks: [TaskItem]

    enum CodingKeys: String, CodingKey {
        case date
        case taskIds = "task_ids"
        case tasks
    }
}

struct NewTask: Codable {
    var title: String
    var listId: Int?
    var nextAction: String?
    var dueAt: Date?
    var whenWhere: String?

    enum CodingKeys: String, CodingKey {
        case title
        case listId = "list_id"
        case nextAction = "next_action"
        case dueAt = "due_at"
        case whenWhere = "when_where"
    }
}
