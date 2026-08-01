import SwiftUI

/// "Ask <Assistant>" — only shown when this user actually has an agent, so
/// nobody is offered a helper that will not answer.
struct AssistantBar: View {
    @EnvironmentObject private var store: TaskStore

    @State private var info: AssistantInfo?
    @State private var text = ""
    @State private var reply: String?
    @State private var isError = false
    @State private var busy = false

    var body: some View {
        Group {
            if let info, info.hasAssistant, let name = info.name {
                content(name: name)
            } else {
                // Not decoration: a Group that resolves to EmptyView is not in
                // the render tree, so .task never fires and the bar could never
                // load itself. The zero-height placeholder keeps it alive.
                Color.clear.frame(height: 0)
            }
        }
        .task { await load() }
    }

    private func content(name: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let reply {
                Text(reply)
                    .font(XFont.body(14))
                    .foregroundStyle(isError ? Color.xAccent : Color.xMuted)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .transition(.opacity)
            }

            HStack(spacing: 8) {
                TextField(Strings.t(.askAssistant).replacingOccurrences(of: "{name}", with: name),
                          text: $text)
                    .font(XFont.body(15))
                    .disabled(busy)
                    .submitLabel(.send)
                    .onSubmit { send(name: name) }

                Button { send(name: name) } label: {
                    Image(systemName: "arrow.up")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(Color.xBackground)
                        .frame(width: 30, height: 30)
                        .background(Color.xInk, in: Circle())
                }
                .buttonStyle(.plain)
                .disabled(busy || text.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color.xSurface, in: Capsule())
            .overlay(Capsule().stroke(Color.xLine, lineWidth: 1))
        }
        .padding(.horizontal, 14)
        .padding(.bottom, 8)
        .animation(.easeInOut(duration: 0.2), value: reply)
    }

    private func load() async {
        guard let api = store.api else { return }
        info = try? await api.assistantInfo()
    }

    private func send(name: String) {
        let command = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !command.isEmpty, let api = store.api else { return }

        busy = true
        isError = false
        reply = Strings.t(.asstWorking).replacingOccurrences(of: "{name}", with: name)

        Task {
            defer { busy = false }
            do {
                let response = try await api.commandAssistant(command)
                reply = response.reply
                text = ""
                // The agent may have changed the list underneath us.
                await store.refresh()
            } catch APIError.http(404, _) {
                isError = true
                reply = Strings.t(.asstNone).replacingOccurrences(of: "{name}", with: name)
            } catch APIError.http(503, _) {
                isError = true
                reply = Strings.t(.asstUnavailable).replacingOccurrences(of: "{name}", with: name)
            } catch {
                isError = true
                reply = Strings.t(.asstFailed).replacingOccurrences(of: "{name}", with: name)
            }
        }
    }
}

/// The weave mark: threads woven through other people's work. It pulses when
/// the pass count goes up since last seen — the only place the app celebrates
/// something other than a completion.
struct WeaveMark: View {
    @EnvironmentObject private var store: TaskStore

    @State private var weave: Weave?
    @State private var pulsing = false

    var body: some View {
        Group {
            if let weave, weave.threads >= 1 {
                HStack(spacing: 5) {
                    ForEach(0..<min(weave.tier, 5), id: \.self) { index in
                        Capsule()
                            .fill(Color.xAccent.opacity(0.35 + 0.15 * Double(index)))
                            .frame(width: 3, height: 13)
                    }
                }
                .scaleEffect(pulsing ? 1.35 : 1)
                .animation(.spring(response: 0.4, dampingFraction: 0.5), value: pulsing)
                .accessibilityLabel(
                    Strings.t(.weaveTooltip)
                        .replacingOccurrences(of: "{threads}", with: String(weave.threads))
                        .replacingOccurrences(of: "{passes}", with: String(weave.passes))
                )
            } else {
                // Same EmptyView trap as the assistant bar above.
                Color.clear.frame(width: 0, height: 0)
            }
        }
        .task { await load() }
    }

    private func load() async {
        guard let api = store.api,
              let account = try? await api.me(),
              let person = try? await api.person(account.username),
              let next = person.weave else { return }

        let key = "xong.weave.passes.\(account.username)"
        let defaults = UserDefaults.standard
        let previous = defaults.object(forKey: key) as? Int
        defaults.set(next.passes, forKey: key)
        weave = next

        if let previous, next.passes > previous {
            pulsing = true
            try? await Task.sleep(for: .milliseconds(700))
            pulsing = false
        }
    }
}
