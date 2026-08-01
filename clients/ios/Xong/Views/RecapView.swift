import SwiftUI

/// Weekly wins. Positive copy only — a quiet week is stated as fine, never as
/// a failure (SPEC principle 4).
struct RecapView: View {
    @EnvironmentObject private var store: TaskStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text(Strings.t(.recapTitle))
                    .font(XFont.display(34))
                    .foregroundStyle(Color.xInk)
                    .padding(.top, 10)

                if let recap = store.recap {
                    summary(recap)
                    chart(recap)
                    wins(recap)
                }
            }
            .padding(.horizontal, 18)
            .padding(.bottom, 28)
        }
        .background(Color.xBackground)
        .task { await store.loadRecap() }
        .refreshable { await store.loadRecap() }
    }

    private func summary(_ recap: WeeklyRecap) -> some View {
        HStack(spacing: 10) {
            stat(Strings.t(.recapTotal, recap.total), primary: true)
            if recap.streak > 0 {
                stat("🔥 " + Strings.t(.streakDays, recap.streak), primary: false)
            }
        }
    }

    private func stat(_ text: String, primary: Bool) -> some View {
        Text(text)
            .font(XFont.body(primary ? 17 : 15, weight: primary ? .semibold : .regular))
            .foregroundStyle(primary ? Color.xInk : Color.xAccent)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(primary ? Color.xSurface : Color.xAccent.opacity(0.12),
                        in: RoundedRectangle(cornerRadius: 12))
    }

    /// Seven quiet bars. No gridlines, no axis furniture — the shape is the
    /// whole message.
    private func chart(_ recap: WeeklyRecap) -> some View {
        let peak = max(recap.days.map(\.count).max() ?? 0, 1)

        return HStack(alignment: .bottom, spacing: 8) {
            ForEach(recap.days) { day in
                VStack(spacing: 6) {
                    RoundedRectangle(cornerRadius: 5)
                        .fill(day.count > 0 ? Color.xAccent : Color.xSurface2)
                        .frame(height: max(6, 92 * CGFloat(day.count) / CGFloat(peak)))
                    Text(weekdayInitial(day.date))
                        .font(XFont.body(11))
                        .foregroundStyle(Color.xFaint)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .frame(height: 120)
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func wins(_ recap: WeeklyRecap) -> some View {
        let titles = recap.days.flatMap(\.titles)
        if titles.isEmpty {
            Text(Strings.t(.recapEmpty))
                .font(XFont.body(15))
                .foregroundStyle(Color.xMuted)
        } else {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(titles.enumerated()), id: \.offset) { _, title in
                    HStack(spacing: 10) {
                        Image(systemName: "checkmark")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundStyle(Color.xAccent)
                        Text(title)
                            .font(XFont.body(16))
                            .foregroundStyle(Color.xMuted)
                    }
                }
            }
        }
    }

    private func weekdayInitial(_ key: String) -> String {
        let parser = DateFormatter()
        parser.dateFormat = "yyyy-MM-dd"
        guard let date = parser.date(from: key) else { return "" }

        let out = DateFormatter()
        out.locale = Locale(identifier: Strings.localeIdentifier)
        out.dateFormat = "EEEEE"
        return out.string(from: date)
    }
}
