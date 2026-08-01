import SwiftUI

/// Precedents for a skill: standing boundaries first, then past decisions.
///
/// The web app reaches this only through the URL hash, never through a link —
/// it is a deep-link surface for agents. The iOS equivalent is the xong://
/// scheme, so xong://skill/<slug> lands here.
struct SkillTracesView: View {
    let slug: String
    @EnvironmentObject private var store: TaskStore
    @Environment(\.dismiss) private var dismiss

    @State private var data: SkillTraces?
    @State private var failed = false
    @State private var me: String?

    private var isOwner: Bool {
        guard let owner = data?.owner?.username, let me else { return false }
        return owner == me
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if failed {
                        Text(Strings.t(.precedentFailed))
                            .font(XFont.body(15))
                            .foregroundStyle(Color.xMuted)
                    } else if let data {
                        header(data)

                        if !data.boundaries.isEmpty {
                            section(rulesHeading(data), data.boundaries)
                        }
                        if !data.decisions.isEmpty {
                            section(Strings.t(.precedentsRecent), data.decisions)
                        }
                        if data.traces.isEmpty {
                            Text(Strings.t(.precedentsEmpty))
                                .font(XFont.body(15))
                                .foregroundStyle(Color.xMuted)
                        }
                    } else {
                        ProgressView().tint(Color.xMuted)
                    }
                }
                .padding(18)
            }
            .background(Color.xBackground)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(Strings.t(.precedentBack)) { dismiss() }
                        .foregroundStyle(Color.xMuted)
                }
            }
        }
        .task { await load() }
    }

    private func rulesHeading(_ data: SkillTraces) -> String {
        guard let owner = data.owner else { return Strings.t(.precedentsRules) }
        return Strings.t(.precedentsRulesOf).replacingOccurrences(of: "{name}", with: owner.name)
    }

    private func header(_ data: SkillTraces) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(data.skill.name)
                .font(XFont.display(30))
                .foregroundStyle(Color.xInk)
            Text(Strings.t(.precedentsTitle))
                .font(XFont.body(13))
                .tracking(0.6)
                .foregroundStyle(Color.xMuted)
        }
    }

    private func section(_ title: String, _ traces: [DecisionTrace]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title.uppercased())
                .font(XFont.body(12, weight: .semibold))
                .tracking(1.1)
                .foregroundStyle(Color.xFaint)

            ForEach(traces) { trace in
                traceRow(trace)
            }
        }
    }

    private func traceRow(_ trace: DecisionTrace) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if let situation = trace.situation, !situation.isEmpty {
                Text(situation)
                    .font(XFont.body(14))
                    .foregroundStyle(Color.xMuted)
            }
            if let decision = trace.decision, !decision.isEmpty {
                Text(decision)
                    .font(XFont.body(16, weight: .medium))
                    .foregroundStyle(Color.xInk)
            }

            HStack(spacing: 8) {
                if let approver = trace.approver, !approver.isEmpty {
                    tag(approver)
                }
                if let outcome = trace.outcome, !outcome.isEmpty {
                    tag(outcome)
                }
                if trace.supersededBy != nil {
                    tag(Strings.t(.precedentSuperseded))
                }

                Spacer()

                // Only humans may grade a precedent, and only the owner is
                // offered it — the API enforces both; this just matches.
                if isOwner && trace.outcome != "corrected" && trace.supersededBy == nil {
                    Button(Strings.t(.precedentCorrect)) { correct(trace) }
                        .font(XFont.body(13, weight: .medium))
                        .foregroundStyle(Color.xAccent)
                        .buttonStyle(.plain)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(Color.xSurface, in: RoundedRectangle(cornerRadius: 14))
    }

    private func tag(_ text: String) -> some View {
        Text(text)
            .font(XFont.body(12))
            .foregroundStyle(Color.xFaint)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Color.xSurface2, in: Capsule())
    }

    private func load() async {
        guard let api = store.api else {
            failed = true
            return
        }
        me = try? await api.me().username
        do {
            data = try await api.skillTraces(slug: slug)
        } catch {
            failed = true
        }
    }

    private func correct(_ trace: DecisionTrace) {
        guard let api = store.api else { return }
        Task {
            try? await api.setTraceOutcome(trace.id, outcome: "corrected")
            await load()
        }
    }
}
