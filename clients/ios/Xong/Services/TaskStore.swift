import Foundation
import SwiftUI

/// Single source of truth for the UI.
///
/// Local mode is served entirely by LocalEngine. Server mode reads through the
/// API and mirrors into the same engine, so the app stays usable offline and a
/// dropped connection degrades to stale data rather than an empty screen.
/// Merge semantics deliberately live on the server — the client stays dumb, so
/// five frontends cannot each invent a different conflict rule.
@MainActor
final class TaskStore: ObservableObject {
    @Published private(set) var today: Today?
    @Published private(set) var lists: [TaskList] = []
    @Published private(set) var recap: WeeklyRecap?
    @Published private(set) var isOffline = false
    @Published private(set) var statusMessage: String?

    private let engine: LocalEngine
    /// nil in local-only mode. Views that offer server-only features (
    /// attachments, assistant, precedents) hide themselves when this is nil.
    let api: APIClient?
    /// What this deployment actually runs. A v1 server advertises nothing, so
    /// everything is assumed on; a v2 server lists its modules and the client
    /// must not call endpoints it does not have.
    private(set) var capabilities: Tenant?

    func supports(_ capability: String) -> Bool {
        guard let capabilities else { return false }
        return capabilities.has(capability)
    }

    init(configuration: AppConfiguration) {
        let namespace = configuration.namespace
        self.engine = LocalEngine(namespace: namespace)
        self.capabilities = configuration.tenant
        if let tenant = configuration.tenant {
            self.api = APIClient(tenant: tenant)
        } else {
            self.api = nil
        }
    }

    var focusIds: [Int] { engine.focusIds }

    // MARK: - Loading

    func refresh() async {
        guard let api else {
            renderLocal()
            return
        }
        do {
            async let remoteToday = api.today()
            async let remoteLists = api.lists()
            let fetchedToday = try await remoteToday
            let fetchedLists = try await remoteLists
            today = fetchedToday
            lists = fetchedLists
            isOffline = false
            statusMessage = nil
            engine.mirror(lists: fetchedLists, today: fetchedToday)
        } catch {
            isOffline = true
            statusMessage = (error as? APIError)?.diagnostic ?? error.localizedDescription
            renderLocal()
        }
    }

    func loadRecap() async {
        if let api, let remote = try? await api.weeklyRecap() {
            recap = remote
            return
        }
        recap = engine.weeklyRecap()
    }

    func tasks(in list: TaskList) -> [TaskItem] {
        engine.tasks(listId: list.id)
    }

    private func renderLocal() {
        today = engine.today()
        lists = engine.lists
    }

    // MARK: - Mutations (optimistic; the UI must never wait on the network)

    func add(title: String, to listId: Int?) async {
        let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        engine.createTask(NewTask(title: trimmed, listId: listId, nextAction: nil,
                                  dueAt: nil, whenWhere: nil))
        renderLocal()

        if let api {
            _ = try? await api.createTask(NewTask(title: trimmed, listId: listId,
                                                  nextAction: nil, dueAt: nil, whenWhere: nil))
            await refresh()
        }
    }

    func complete(_ task: TaskItem) async {
        engine.complete(task.id)
        renderLocal()

        if let api {
            _ = try? await api.complete(task.id)
            await refresh()
        }
    }

    func uncomplete(_ task: TaskItem) async {
        engine.uncomplete(task.id)
        renderLocal()

        if let api {
            _ = try? await api.uncomplete(task.id)
            await refresh()
        }
    }

    func delete(_ task: TaskItem) async {
        engine.delete(task.id)
        renderLocal()

        if let api {
            try? await api.deleteTask(task.id)
            await refresh()
        }
    }

    /// Toggles a task in today's 3. Capped at three, and the cap is announced
    /// rather than silently ignored.
    @discardableResult
    func toggleFocus(_ task: TaskItem) async -> Bool {
        var ids = engine.focusIds
        if let existing = ids.firstIndex(of: task.id) {
            ids.remove(at: existing)
        } else {
            guard ids.count < 3 else { return false }
            ids.append(task.id)
        }
        engine.setFocus(ids)
        renderLocal()

        if let api {
            _ = try? await api.setFocus(ids)
            await refresh()
        }
        return true
    }

    func update(_ task: TaskItem, patch: TaskPatch) async {
        engine.update(task.id) { stored in
            if let title = patch.title { stored.title = title }
            stored.nextAction = patch.nextAction
            stored.notes = patch.notes
            stored.whenWhere = patch.whenWhere
            stored.dueAt = patch.dueAt
        }
        renderLocal()

        if let api {
            _ = try? await api.updateTask(task.id, patch)
            await refresh()
        }
    }

    func addList(name: String) async {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        engine.createList(name: trimmed)
        renderLocal()

        if let api {
            _ = try? await api.createList(name: trimmed)
            await refresh()
        }
    }
}
