import Foundation

/// Full task semantics on-device, so local-only mode is a real product and not
/// a degraded one — and so a reviewer with no server can use the whole app.
///
/// Cache is keyed by namespace: each server, and local-only, keeps its own
/// store, so one organization's tasks never surface in another's session.
final class LocalEngine {
    private struct Database: Codable {
        var lists: [TaskList]
        var tasks: [TaskItem]
        var focusDate: String
        var focusTaskIds: [Int]
        var nextListId: Int
        var nextTaskId: Int
    }

    private let namespace: String
    private var db: Database

    init(namespace: String) {
        self.namespace = namespace
        self.db = Self.load(namespace: namespace) ?? Self.empty()
        save()
    }

    // MARK: - Persistence

    private static func url(namespace: String) -> URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        return base.appendingPathComponent("xong-\(namespace).json")
    }

    private static func load(namespace: String) -> Database? {
        guard let data = try? Data(contentsOf: url(namespace: namespace)) else { return nil }
        return try? JSONCoding.decoder.decode(Database.self, from: data)
    }

    private static func empty() -> Database {
        Database(
            lists: [TaskList(id: 1, ownerId: 1, name: Strings.t(.defaultListName),
                             position: 0, archived: false)],
            tasks: [],
            focusDate: DayKey.today(),
            focusTaskIds: [],
            nextListId: 2,
            nextTaskId: 1
        )
    }

    private func save() {
        guard let data = try? JSONCoding.encoder.encode(db) else { return }
        try? data.write(to: Self.url(namespace: namespace), options: .atomic)
    }

    static func clear(namespace: String) {
        try? FileManager.default.removeItem(at: url(namespace: namespace))
    }

    // MARK: - Reads

    var lists: [TaskList] {
        db.lists.filter { !$0.archived }.sorted { $0.position < $1.position }
    }

    func tasks(listId: Int?, includeCompleted: Bool = false) -> [TaskItem] {
        db.tasks
            .filter { listId == nil || $0.listId == listId }
            .filter { includeCompleted || !$0.isDone }
            .sorted { $0.position < $1.position }
    }

    func today() -> Today {
        let todayKey = DayKey.today()
        let open = db.tasks.filter { !$0.isDone }
        let focusIds = db.focusDate == todayKey ? db.focusTaskIds : []

        let focus = focusIds.compactMap { id in open.first { $0.id == id } }
        let dueToday = open.filter { task in
            guard let due = task.dueAt else { return false }
            return DayKey.of(due) == todayKey && !focusIds.contains(task.id)
        }
        let overdue = open.filter { task in
            guard let due = task.dueAt else { return false }
            return DayKey.of(due) < todayKey && !focusIds.contains(task.id)
        }
        let defaultList = lists.first ?? Self.empty().lists[0]

        return Today(
            date: todayKey,
            streak: streak(),
            focus: focus,
            dueToday: dueToday.sorted { $0.position < $1.position },
            overdue: overdue.sorted { $0.position < $1.position },
            defaultList: defaultList,
            defaultTasks: tasks(listId: defaultList.id)
        )
    }

    /// Consecutive days with at least one completion. A day with nothing done
    /// yet does not break the streak until it is over — SPEC principle 4 says
    /// the app never shames, and resetting at midnight would.
    func streak() -> Int {
        let completedDays = Set(db.tasks.compactMap { $0.completedAt.map(DayKey.of) })
        guard !completedDays.isEmpty else { return 0 }

        var count = 0
        var cursor = Date()
        if !completedDays.contains(DayKey.of(cursor)) {
            cursor = Calendar.current.date(byAdding: .day, value: -1, to: cursor)!
        }
        while completedDays.contains(DayKey.of(cursor)) {
            count += 1
            cursor = Calendar.current.date(byAdding: .day, value: -1, to: cursor)!
        }
        return count
    }

    func weeklyRecap() -> WeeklyRecap {
        let calendar = Calendar.current
        var days: [DayWins] = []

        for offset in stride(from: 6, through: 0, by: -1) {
            let date = calendar.date(byAdding: .day, value: -offset, to: Date())!
            let key = DayKey.of(date)
            let titles = db.tasks
                .filter { $0.completedAt.map(DayKey.of) == key }
                .map(\.title)
            days.append(DayWins(date: key, count: titles.count, titles: titles))
        }

        let best = days.max { $0.count < $1.count }
        return WeeklyRecap(
            streak: streak(),
            total: days.reduce(0) { $0 + $1.count },
            bestDay: (best?.count ?? 0) > 0 ? best?.date : nil,
            bestDayCount: best?.count ?? 0,
            days: days
        )
    }

    var focusIds: [Int] {
        db.focusDate == DayKey.today() ? db.focusTaskIds : []
    }

    func mirror(lists: [TaskList], today: Today) {
        if !lists.isEmpty { db.lists = lists }

        var seen = Set<Int>()
        var merged: [TaskItem] = []
        for task in today.focus + today.dueToday + today.overdue + today.defaultTasks
        where seen.insert(task.id).inserted {
            merged.append(task)
        }
        for task in db.tasks where task.isDone && seen.insert(task.id).inserted {
            merged.append(task)
        }

        db.tasks = merged
        db.nextTaskId = max(db.nextTaskId, (merged.map(\.id).max() ?? 0) + 1)
        db.focusDate = today.date
        db.focusTaskIds = today.focus.map(\.id)
        save()
    }

    // MARK: - Writes

    @discardableResult
    func createTask(_ new: NewTask) -> TaskItem {
        let listId = new.listId ?? lists.first?.id ?? 1
        // Wunderlist behaviour: a new task lands at the TOP of its list.
        let minPosition = db.tasks.filter { $0.listId == listId }.map(\.position).min() ?? 0

        let task = TaskItem(
            id: db.nextTaskId,
            listId: listId,
            title: new.title,
            nextAction: new.nextAction,
            notes: nil,
            dueAt: new.dueAt,
            whenWhere: new.whenWhere,
            position: minPosition - 1,
            createdBy: "me",
            completedAt: nil,
            createdAt: Date(),
            looksVague: new.title.split(separator: " ").count > 10
        )
        db.nextTaskId += 1
        db.tasks.append(task)
        save()
        return task
    }

    func complete(_ id: Int, at date: Date = Date()) {
        guard let index = db.tasks.firstIndex(where: { $0.id == id }) else { return }
        db.tasks[index].completedAt = date
        db.focusTaskIds.removeAll { $0 == id }
        save()
    }

    func uncomplete(_ id: Int) {
        guard let index = db.tasks.firstIndex(where: { $0.id == id }) else { return }
        db.tasks[index].completedAt = nil
        save()
    }

    func update(_ id: Int, _ mutate: (inout TaskItem) -> Void) {
        guard let index = db.tasks.firstIndex(where: { $0.id == id }) else { return }
        mutate(&db.tasks[index])
        save()
    }

    func delete(_ id: Int) {
        db.tasks.removeAll { $0.id == id }
        db.focusTaskIds.removeAll { $0 == id }
        save()
    }

    /// Max three, enforced here as the API does.
    func setFocus(_ ids: [Int]) {
        db.focusDate = DayKey.today()
        db.focusTaskIds = Array(ids.prefix(3))
        save()
    }

    @discardableResult
    func createList(name: String) -> TaskList {
        let list = TaskList(id: db.nextListId, ownerId: 1, name: name,
                            position: db.lists.count, archived: false)
        db.nextListId += 1
        db.lists.append(list)
        save()
        return list
    }

    func deleteList(_ id: Int) {
        db.lists.removeAll { $0.id == id }
        db.tasks.removeAll { $0.listId == id }
        save()
    }
}

enum DayKey {
    private static let formatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.calendar = Calendar.current
        return f
    }()

    static func of(_ date: Date) -> String { formatter.string(from: date) }
    static func today() -> String { of(Date()) }
}

enum JSONCoding {
    static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        // FastAPI emits ISO8601, sometimes with fractional seconds and
        // sometimes without; .iso8601 alone rejects the fractional form.
        let withFraction = ISO8601DateFormatter()
        withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]

        d.dateDecodingStrategy = .custom { decoder in
            let raw = try decoder.singleValueContainer().decode(String.self)
            if let date = withFraction.date(from: raw) ?? plain.date(from: raw) {
                return date
            }
            throw DecodingError.dataCorrupted(
                .init(codingPath: decoder.codingPath, debugDescription: "Bad date: \(raw)")
            )
        }
        return d
    }()

    static let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .iso8601
        return e
    }()
}
