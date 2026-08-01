import SwiftUI

struct ListsView: View {
    @EnvironmentObject private var store: TaskStore
    @State private var selected: TaskList?
    @State private var newListName = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text(Strings.t(.navLists))
                    .font(XFont.display(34))
                    .foregroundStyle(Color.xInk)
                    .padding(.top, 10)

                ForEach(store.lists) { list in
                    listCard(list)
                }

                AddTaskField(text: $newListName) {
                    let name = newListName
                    newListName = ""
                    Task { await store.addList(name: name) }
                }
                .overlay(alignment: .leading) {
                    // Placeholder differs from the task field; the shared field
                    // renders its own, so nothing to draw here.
                    EmptyView()
                }
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 28)
        }
        .background(Color.xBackground)
        .refreshable { await store.refresh() }
        .sheet(item: $selected) { list in
            ListDetailView(list: list)
                .environmentObject(store)
        }
    }

    private func listCard(_ list: TaskList) -> some View {
        Button {
            selected = list
        } label: {
            HStack {
                Text(list.name)
                    .font(XFont.body(18, weight: .medium))
                    .foregroundStyle(Color.xInk)
                Spacer()
                Text("\(store.tasks(in: list).count)")
                    .font(XFont.body(15))
                    .foregroundStyle(Color.xFaint)
                Image(systemName: "chevron.right")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Color.xFaint)
            }
            .padding(16)
            .background(Color.xSurface, in: RoundedRectangle(cornerRadius: 14))
        }
        .buttonStyle(.plain)
    }
}

struct ListDetailView: View {
    let list: TaskList
    @EnvironmentObject private var store: TaskStore
    @Environment(\.dismiss) private var dismiss
    @State private var draft = ""

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    AddTaskField(text: $draft) {
                        let title = draft
                        draft = ""
                        Task { await store.add(title: title, to: list.id) }
                    }

                    let tasks = store.tasks(in: list)
                    if tasks.isEmpty {
                        Text(Strings.t(.emptyList))
                            .font(XFont.body(15))
                            .foregroundStyle(Color.xMuted)
                            .padding(.top, 6)
                    }

                    ForEach(tasks) { task in
                        TaskRow(task: task,
                                isFocus: store.focusIds.contains(task.id),
                                onToggle: {
                                    Feedback.shared.completed()
                                    Task { await store.complete(task) }
                                },
                                onStar: { Task { await store.toggleFocus(task) } })
                    }
                }
                .padding(.horizontal, 18)
                .padding(.vertical, 12)
            }
            .background(Color.xBackground)
            .navigationTitle(list.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(Strings.t(.done)) { dismiss() }
                        .foregroundStyle(Color.xInk)
                }
            }
        }
    }
}
