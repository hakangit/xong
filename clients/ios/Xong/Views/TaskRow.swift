import SwiftUI

/// The check control. Everything else in the app stays almost still, so this
/// is where the motion budget goes: a springy fill, then the row leaves.
struct CheckCircle: View {
    let isDone: Bool
    let action: () -> Void

    @State private var pressed = false

    var body: some View {
        Button(action: action) {
            ZStack {
                Circle()
                    .strokeBorder(isDone ? Color.xAccent : Color.xFaint, lineWidth: 1.5)
                    .frame(width: 26, height: 26)

                Circle()
                    .fill(Color.xAccent)
                    .frame(width: 26, height: 26)
                    .scaleEffect(isDone ? 1 : 0.01)
                    .opacity(isDone ? 1 : 0)

                Image(systemName: "checkmark")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(Color.xBackground)
                    .scaleEffect(isDone ? 1 : 0.3)
                    .opacity(isDone ? 1 : 0)
            }
            .scaleEffect(pressed ? 0.86 : 1)
            .animation(.spring(response: 0.32, dampingFraction: 0.55), value: isDone)
            .animation(.spring(response: 0.2, dampingFraction: 0.6), value: pressed)
            .contentShape(Rectangle())
            .frame(width: 44, height: 44)
        }
        .buttonStyle(.plain)
        .simultaneousGesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in
                    guard !pressed else { return }
                    pressed = true
                    Feedback.shared.prepare()
                }
                .onEnded { _ in pressed = false }
        )
    }
}

struct TaskRow: View {
    let task: TaskItem
    var isFocus = false
    var showsStar = true
    let onToggle: () -> Void
    var onStar: (() -> Void)?

    @State private var editing = false

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            CheckCircle(isDone: task.isDone, action: onToggle)

            VStack(alignment: .leading, spacing: 3) {
                Text(task.title)
                    .font(XFont.body(isFocus ? 19 : 17, weight: isFocus ? .semibold : .regular))
                    .foregroundStyle(Color.xInk)
                    .strikethrough(task.isDone, color: Color.xMuted)
                    .fixedSize(horizontal: false, vertical: true)
                    .contentShape(Rectangle())
                    .onTapGesture { editing = true }

                if let next = task.nextAction, !next.isEmpty {
                    Text("\(Strings.t(.firstStep)) \(next)")
                        .font(XFont.body(14))
                        .foregroundStyle(Color.xMuted)
                } else if let label = calmDueLabel {
                    // Calm phrasing, never red, never scolding (SPEC principle 4).
                    Text(label)
                        .font(XFont.body(13))
                        .foregroundStyle(Color.xMuted)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(Color.xSurface2, in: Capsule())
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            if showsStar, let onStar {
                Button(action: onStar) {
                    Image(systemName: isFocus ? "star.fill" : "star")
                        .font(.system(size: 16))
                        .foregroundStyle(isFocus ? Color.xInk : Color.xFaint)
                        .frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(Color.xSurface, in: RoundedRectangle(cornerRadius: 14))
        .sheet(isPresented: $editing) {
            TaskDetailView(task: task)
        }
    }

    private var calmDueLabel: String? {
        guard let due = task.dueAt else { return nil }
        let today = DayKey.today()
        let dueKey = DayKey.of(due)

        if dueKey == today {
            let time = due.formatted(date: .omitted, time: .shortened)
            return "\(Strings.t(.dueAtTime)) \(time)"
        }
        guard dueKey < today else { return nil }

        let days = Calendar.current.dateComponents(
            [.day], from: Calendar.current.startOfDay(for: due),
            to: Calendar.current.startOfDay(for: Date())
        ).day ?? 0
        return days <= 1 ? Strings.t(.sinceYesterday) : Strings.t(.sinceDaysAgo, days)
    }
}
