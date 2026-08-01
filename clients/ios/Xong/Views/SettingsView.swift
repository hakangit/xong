import SwiftUI

/// Language and connection live here — native owns both, so there is exactly
/// one place to change either.
struct SettingsView: View {
    @EnvironmentObject private var config: AppConfiguration
    @Environment(\.dismiss) private var dismiss
    @State private var confirmingSwitch = false

    private let languages: [(code: String?, label: String)] = [
        (nil, Strings.t(.settingsLanguageSystem)),
        ("vi", "Tiếng Việt"),
        ("en", "English"),
        ("zh", "中文"),
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    languageSection
                    connectionSection
                    soundSection
                }
                .padding(.horizontal, 18)
                .padding(.vertical, 16)
            }
            .background(Color.xBackground)
            .navigationTitle(Strings.t(.settings))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(Strings.t(.done)) { dismiss() }
                        .foregroundStyle(Color.xInk)
                }
            }
        }
    }

    private var languageSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            title(Strings.t(.settingsLanguage))
            ForEach(languages, id: \.label) { option in
                row(option.label, selected: config.language == option.code) {
                    config.setLanguage(option.code)
                }
            }
        }
    }

    private var connectionSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            title(Strings.t(.settingsConnection))

            if let tenant = config.tenant {
                VStack(alignment: .leading, spacing: 3) {
                    Text(Strings.t(.settingsConnected))
                        .font(XFont.body(13))
                        .foregroundStyle(Color.xFaint)
                    Text(tenant.name)
                        .font(XFont.body(17, weight: .semibold))
                        .foregroundStyle(Color.xInk)
                    Text(tenant.apiBase.host ?? "")
                        .font(XFont.body(14))
                        .foregroundStyle(Color.xMuted)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(16)
                .background(Color.xSurface, in: RoundedRectangle(cornerRadius: 14))

                action(Strings.t(.settingsSignOut)) { confirmingSwitch = true }
            } else {
                Text(Strings.t(.settingsLocalMode))
                    .font(XFont.body(16))
                    .foregroundStyle(Color.xInk)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
                    .background(Color.xSurface, in: RoundedRectangle(cornerRadius: 14))

                action(Strings.t(.connectServer)) { confirmingSwitch = true }
            }
        }
        .confirmationDialog(Strings.t(.settingsSwitchServer),
                            isPresented: $confirmingSwitch, titleVisibility: .visible) {
            Button(Strings.t(.settingsSwitchServer)) { config.reset() }
            Button(Strings.t(.cancel), role: .cancel) {}
        } message: {
            // Per-tenant caches mean nothing is destroyed by switching — say so,
            // because "sign out" usually implies loss.
            Text(Strings.t(.settingsSwitchKeepsData))
        }
    }

    private var soundSection: some View {
        row(Strings.t(.settingsSound), selected: !Feedback.shared.isMuted) {
            Feedback.shared.toggleMute()
        }
    }

    private func title(_ text: String) -> some View {
        Text(text.uppercased())
            .font(XFont.body(12, weight: .semibold))
            .tracking(1.1)
            .foregroundStyle(Color.xFaint)
    }

    private func row(_ label: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack {
                Text(label)
                    .font(XFont.body(16))
                    .foregroundStyle(Color.xInk)
                Spacer()
                if selected {
                    Image(systemName: "checkmark")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(Color.xAccent)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(Color.xSurface, in: RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
    }

    private func action(_ label: String, perform: @escaping () -> Void) -> some View {
        Button(action: perform) {
            Text(label)
                .font(XFont.body(16, weight: .medium))
                .foregroundStyle(Color.xAccent)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
        }
        .buttonStyle(.plain)
    }
}
