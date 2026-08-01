import SwiftUI

struct TodayView: View {
    @EnvironmentObject private var store: TaskStore
    @State private var draft = ""
    @State private var notice: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header

                if let today = store.today {
                    focusSection(today)
                    section(Strings.t(.overdueTitle), today.overdue)
                    section(Strings.t(.dueTodayTitle), today.dueToday)
                    defaultList(today)
                }
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 28)
        }
        .background(Color.xBackground)
        .scrollDismissesKeyboard(.interactively)
        .refreshable { await store.refresh() }
    }

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(greeting)
                .font(XFont.display(40))
                .foregroundStyle(Color.xInk)

            HStack(spacing: 8) {
                Text(Date().formatted(.dateTime.weekday(.wide).month(.wide).day()))
                    .font(XFont.body(15))
                    .foregroundStyle(Color.xMuted)

                if let streak = store.today?.streak, streak > 0 {
                    Text("🔥 " + Strings.t(.streakDays, streak))
                        .font(XFont.body(14, weight: .semibold))
                        .foregroundStyle(Color.xAccent)
                        .padding(.horizontal, 9)
                        .padding(.vertical, 4)
                        .background(Color.xAccent.opacity(0.12), in: Capsule())
                }

                if store.isOffline {
                    Text(Strings.t(.offline))
                        .font(XFont.body(13))
                        .foregroundStyle(Color.xMuted)
                }
            }

            if let notice {
                Text(notice)
                    .font(XFont.body(14))
                    .foregroundStyle(Color.xMuted)
                    .padding(.top, 4)
            }
        }
        .padding(.top, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var greeting: String {
        switch Calendar.current.component(.hour, from: Date()) {
        case ..<12: return Strings.t(.greetMorning)
        case 12..<18: return Strings.t(.greetAfternoon)
        default: return Strings.t(.greetEvening)
        }
    }

    // MARK: - Sections

    @ViewBuilder
    private func focusSection(_ today: Today) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionTitle(Strings.t(.focusTitle))

            if today.focus.isEmpty {
                Text(Strings.t(.focusEmpty))
                    .font(XFont.body(15))
                    .foregroundStyle(Color.xMuted)
                Text(Strings.t(.focusHint))
                    .font(XFont.body(14))
                    .foregroundStyle(Color.xFaint)
            } else {
                ForEach(today.focus) { task in
                    TaskRow(task: task, isFocus: true,
                            onToggle: { complete(task) },
                            onStar: { star(task) })
                }
            }
        }
    }

    @ViewBuilder
    private func section(_ title: String, _ tasks: [TaskItem]) -> some View {
        if !tasks.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                sectionTitle(title)
                ForEach(tasks) { task in
                    TaskRow(task: task,
                            isFocus: store.focusIds.contains(task.id),
                            onToggle: { complete(task) },
                            onStar: { star(task) })
                }
            }
        }
    }

    @ViewBuilder
    private func defaultList(_ today: Today) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionTitle(today.defaultList.name)

            AddTaskField(text: $draft) {
                let title = draft
                draft = ""
                Task { await store.add(title: title, to: today.defaultList.id) }
            }

            let rest = today.defaultTasks.filter { task in
                !today.focus.contains(task) && !today.dueToday.contains(task)
                    && !today.overdue.contains(task)
            }

            if rest.isEmpty && today.focus.isEmpty {
                Text(Strings.t(.emptyList))
                    .font(XFont.body(15))
                    .foregroundStyle(Color.xMuted)
                    .padding(.top, 4)
            }

            ForEach(rest) { task in
                TaskRow(task: task,
                        isFocus: store.focusIds.contains(task.id),
                        onToggle: { complete(task) },
                        onStar: { star(task) })
            }
        }
    }

    private func sectionTitle(_ text: String) -> some View {
        Text(text.uppercased())
            .font(XFont.body(12, weight: .semibold))
            .tracking(1.1)
            .foregroundStyle(Color.xFaint)
    }

    // MARK: - Actions

    private func complete(_ task: TaskItem) {
        Feedback.shared.completed()
        Task { await store.complete(task) }
    }

    private func star(_ task: TaskItem) {
        Task {
            let ok = await store.toggleFocus(task)
            if !ok {
                Feedback.shared.blocked()
                notice = Strings.t(.maxThree)
                try? await Task.sleep(for: .seconds(2.5))
                notice = nil
            }
        }
    }
}

struct AddTaskField: View {
    @Binding var text: String
    let onSubmit: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "plus")
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(Color.xFaint)

            TextField(Strings.t(.addPlaceholder), text: $text)
                .font(XFont.body(17))
                .foregroundStyle(Color.xInk)
                .submitLabel(.done)
                .onSubmit(onSubmit)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 13)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .strokeBorder(style: StrokeStyle(lineWidth: 1, dash: [5, 4]))
                .foregroundStyle(Color.xLine)
        )
    }
}
