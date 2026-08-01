import SwiftUI
import UniformTypeIdentifiers

struct TaskDetailView: View {
    let task: TaskItem
    @EnvironmentObject private var store: TaskStore
    @Environment(\.dismiss) private var dismiss

    @State private var nextAction: String
    @State private var whenWhere: String
    @State private var notes: String
    @State private var dueAt: Date
    @State private var hasDue: Bool
    @State private var confirmingDelete = false

    init(task: TaskItem) {
        self.task = task
        _nextAction = State(initialValue: task.nextAction ?? "")
        _whenWhere = State(initialValue: task.whenWhere ?? "")
        _notes = State(initialValue: task.notes ?? "")
        _dueAt = State(initialValue: task.dueAt ?? Date())
        _hasDue = State(initialValue: task.dueAt != nil)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text(task.title)
                        .font(XFont.body(20, weight: .semibold))
                        .foregroundStyle(Color.xInk)

                    // The nudge from SPEC principle 1: a vague-looking task is
                    // asked for its first concrete step, never scolded.
                    if task.looksVague && nextAction.isEmpty {
                        Text(Strings.t(.edNudge))
                            .font(XFont.body(14))
                            .foregroundStyle(Color.xMuted)
                            .padding(12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.xAccent.opacity(0.10),
                                        in: RoundedRectangle(cornerRadius: 12))
                    }

                    field(Strings.t(.edNext), text: $nextAction,
                          placeholder: Strings.t(.edNextPh))
                    field(Strings.t(.edWhen), text: $whenWhere,
                          placeholder: Strings.t(.edWhenPh))

                    VStack(alignment: .leading, spacing: 6) {
                        Toggle(isOn: $hasDue) {
                            Text(Strings.t(.edDue))
                                .font(XFont.body(13, weight: .semibold))
                                .foregroundStyle(Color.xFaint)
                        }
                        .tint(Color.xAccent)

                        if hasDue {
                            DatePicker("", selection: $dueAt)
                                .labelsHidden()
                                .datePickerStyle(.compact)
                        }
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        label(Strings.t(.edNotes))
                        TextEditor(text: $notes)
                            .font(XFont.body(16))
                            .frame(minHeight: 80)
                            .scrollContentBackground(.hidden)
                            .padding(8)
                            .background(Color.xSurface, in: RoundedRectangle(cornerRadius: 12))
                    }

                    // Attachments are server-backed; local-only mode has none.
                    if store.api != nil {
                        AttachmentsSection(taskId: task.id)
                    }

                    Button(role: .destructive) {
                        confirmingDelete = true
                    } label: {
                        Text(Strings.t(.edDelete))
                            .font(XFont.body(16))
                            .foregroundStyle(Color.xAccent)
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 4)
                }
                .padding(18)
            }
            .background(Color.xBackground)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(Strings.t(.edClose)) { dismiss() }
                        .foregroundStyle(Color.xMuted)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(Strings.t(.edSave)) { save() }
                        .foregroundStyle(Color.xInk)
                        .fontWeight(.semibold)
                }
            }
            .confirmationDialog(Strings.t(.edDelete), isPresented: $confirmingDelete,
                                titleVisibility: .visible) {
                Button(Strings.t(.edDelete), role: .destructive) {
                    Task {
                        await store.delete(task)
                        dismiss()
                    }
                }
                Button(Strings.t(.cancel), role: .cancel) {}
            }
        }
    }

    private func label(_ text: String) -> some View {
        Text(text)
            .font(XFont.body(13, weight: .semibold))
            .foregroundStyle(Color.xFaint)
    }

    private func field(_ title: String, text: Binding<String>, placeholder: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            label(title)
            TextField(placeholder, text: text)
                .font(XFont.body(16))
                .padding(12)
                .background(Color.xSurface, in: RoundedRectangle(cornerRadius: 12))
        }
    }

    private func save() {
        let patch = TaskPatch(
            title: nil,
            nextAction: nextAction.isEmpty ? nil : nextAction,
            notes: notes.isEmpty ? nil : notes,
            dueAt: hasDue ? dueAt : nil,
            whenWhere: whenWhere.isEmpty ? nil : whenWhere
        )
        Task {
            await store.update(task, patch: patch)
            dismiss()
        }
    }
}

struct AttachmentsSection: View {
    let taskId: Int
    @EnvironmentObject private var store: TaskStore

    @State private var attachments: [Attachment] = []
    @State private var linkDraft = ""
    @State private var showingPicker = false
    @State private var busy = false
    @State private var shareURL: URL?
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(Strings.t(.attachments))
                .font(XFont.body(13, weight: .semibold))
                .foregroundStyle(Color.xFaint)

            ForEach(attachments) { attachment in
                row(attachment)
            }

            HStack(spacing: 8) {
                TextField(Strings.t(.attachLinkPh), text: $linkDraft)
                    .font(XFont.body(15))
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .padding(10)
                    .background(Color.xSurface, in: RoundedRectangle(cornerRadius: 10))
                    .onSubmit(addLink)

                Button(action: { showingPicker = true }) {
                    Image(systemName: "paperclip")
                        .font(.system(size: 16))
                        .foregroundStyle(Color.xInk)
                        .frame(width: 40, height: 40)
                        .background(Color.xSurface2, in: RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
                .disabled(busy)
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(XFont.body(13))
                    .foregroundStyle(Color.xMuted)
            }
        }
        .task { await load() }
        .fileImporter(isPresented: $showingPicker, allowedContentTypes: [.item]) { result in
            if case .success(let url) = result { upload(url) }
        }
        .sheet(item: Binding(get: { shareURL.map(ShareTarget.init) },
                             set: { shareURL = $0?.url })) { target in
            ShareSheet(url: target.url)
        }
    }

    private func row(_ attachment: Attachment) -> some View {
        HStack(spacing: 10) {
            Image(systemName: attachment.isLink ? "link" : "doc")
                .font(.system(size: 14))
                .foregroundStyle(Color.xFaint)

            Text(attachment.displayName)
                .font(XFont.body(15))
                .foregroundStyle(Color.xInk)
                .lineLimit(1)
                .truncationMode(.middle)

            Spacer()

            Button {
                open(attachment)
            } label: {
                Image(systemName: attachment.isLink ? "arrow.up.right" : "square.and.arrow.down")
                    .font(.system(size: 14))
                    .foregroundStyle(Color.xMuted)
            }
            .buttonStyle(.plain)

            Button {
                remove(attachment)
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color.xFaint)
            }
            .buttonStyle(.plain)
        }
        .padding(12)
        .background(Color.xSurface, in: RoundedRectangle(cornerRadius: 12))
    }

    private func load() async {
        guard let api = store.api else { return }
        attachments = (try? await api.attachments(taskId: taskId)) ?? []
    }

    private func addLink() {
        let url = linkDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !url.isEmpty, let api = store.api else { return }
        linkDraft = ""

        Task {
            _ = try? await api.addAttachmentLink(taskId: taskId, url: url, filename: nil)
            await load()
        }
    }

    private func upload(_ url: URL) {
        guard let api = store.api else { return }
        busy = true
        errorMessage = nil

        Task {
            defer { busy = false }
            // Security-scoped: a file picked outside the sandbox is unreadable
            // without this, and the failure is silent otherwise.
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }

            guard let data = try? Data(contentsOf: url) else {
                errorMessage = Strings.t(.attachFailed)
                return
            }
            let mime = UTType(filenameExtension: url.pathExtension)?.preferredMIMEType
                ?? "application/octet-stream"
            do {
                _ = try await api.uploadAttachment(taskId: taskId, filename: url.lastPathComponent,
                                                   mimeType: mime, data: data)
                await load()
            } catch {
                errorMessage = Strings.t(.attachFailed)
            }
        }
    }

    private func open(_ attachment: Attachment) {
        if attachment.isLink, let raw = attachment.url, let url = URL(string: raw) {
            UIApplication.shared.open(url)
            return
        }
        guard let api = store.api else { return }
        Task {
            shareURL = try? await api.downloadAttachment(attachment)
        }
    }

    private func remove(_ attachment: Attachment) {
        guard let api = store.api else { return }
        Task {
            try? await api.deleteAttachment(attachment.id)
            await load()
        }
    }
}

private struct ShareTarget: Identifiable {
    let url: URL
    var id: String { url.absoluteString }
}

private struct ShareSheet: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: [url], applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
