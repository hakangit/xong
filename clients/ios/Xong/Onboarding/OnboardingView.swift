import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject private var config: AppConfiguration

    private enum Step { case welcome, connect, confirm }

    @State private var step: Step = .welcome
    @State private var input = ""
    @State private var discovered: Tenant?
    @State private var busy = false
    @State private var errorMessage: String?

    var body: some View {
        ZStack {
            Color.xBackground.ignoresSafeArea()

            VStack(alignment: .leading, spacing: 0) {
                Spacer(minLength: 0)

                Text(Strings.t(.welcomeTitle))
                    .font(.system(size: 52, weight: .heavy))
                    .foregroundStyle(Color.xInk)
                Text(subtitle)
                    .font(.system(size: 18))
                    .foregroundStyle(Color.xMuted)
                    .padding(.top, 6)

                Spacer(minLength: 28)

                content
                    .animation(.easeInOut(duration: 0.2), value: step)

                if let errorMessage {
                    Text(errorMessage)
                        .font(.system(size: 14))
                        .foregroundStyle(Color.xAccent)
                        .padding(.top, 14)
                }

                Spacer(minLength: 0)
            }
            .padding(.horizontal, 28)
            .frame(maxWidth: 520)
        }
    }

    private var subtitle: String {
        switch step {
        case .welcome: return Strings.t(.welcomeBody)
        case .connect: return Strings.t(.connectHint)
        case .confirm: return Strings.t(.confirmBody)
        }
    }

    @ViewBuilder
    private var content: some View {
        switch step {
        case .welcome: welcomeStep
        case .connect: connectStep
        case .confirm: confirmStep
        }
    }

    private var welcomeStep: some View {
        VStack(spacing: 12) {
            choiceCard(
                title: Strings.t(.useLocal),
                hint: Strings.t(.useLocalHint),
                action: { config.chooseLocal() }
            )
            choiceCard(
                title: Strings.t(.connectServer),
                hint: Strings.t(.connectServerHint),
                action: { step = .connect }
            )
        }
    }

    private var connectStep: some View {
        VStack(alignment: .leading, spacing: 14) {
            TextField(Strings.t(.connectPlaceholder), text: $input)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(.emailAddress)
                .font(.system(size: 17))
                .padding(14)
                .background(Color.xSurface, in: RoundedRectangle(cornerRadius: 14))
                .overlay(
                    RoundedRectangle(cornerRadius: 14).stroke(Color.xLine, lineWidth: 1)
                )
                .onSubmit(discover)

            primaryButton(busy ? Strings.t(.connectSearching) : Strings.t(.connectAction),
                          action: discover)
                .disabled(busy || input.trimmingCharacters(in: .whitespaces).isEmpty)

            textButton(Strings.t(.back)) {
                errorMessage = nil
                step = .welcome
            }
        }
    }

    @ViewBuilder
    private var confirmStep: some View {
        if let tenant = discovered {
            VStack(alignment: .leading, spacing: 14) {
                // Naming the org and host before any credential flow keeps a
                // config document from quietly redirecting a sign-in elsewhere.
                VStack(alignment: .leading, spacing: 4) {
                    Text(tenant.name)
                        .font(.system(size: 22, weight: .bold))
                        .foregroundStyle(Color.xInk)
                    Text(tenant.apiBase.host ?? "")
                        .font(.system(size: 15))
                        .foregroundStyle(Color.xMuted)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(18)
                .background(Color.xSurface, in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.xLine, lineWidth: 1))

                primaryButton(busy ? Strings.t(.signingIn) : Strings.t(.confirmSignIn),
                              action: signIn)
                    .disabled(busy)

                textButton(Strings.t(.confirmSwitch)) {
                    errorMessage = nil
                    step = .connect
                }
            }
        }
    }

    private func choiceCard(title: String, hint: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(Color.xInk)
                Text(hint)
                    .font(.system(size: 14))
                    .foregroundStyle(Color.xMuted)
                    .multilineTextAlignment(.leading)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
            .background(Color.xSurface, in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.xLine, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private func primaryButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Color.xBackground)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 15)
                .background(Color.xInk, in: RoundedRectangle(cornerRadius: 14))
        }
        .buttonStyle(.plain)
    }

    private func textButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 15))
                .foregroundStyle(Color.xMuted)
        }
        .buttonStyle(.plain)
    }

    private func discover() {
        guard !busy else { return }
        busy = true
        errorMessage = nil

        Task {
            defer { busy = false }
            do {
                discovered = try await TenantDiscovery.discover(input: input)
                step = .confirm
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    private func signIn() {
        guard let tenant = discovered, !busy else { return }
        busy = true
        errorMessage = nil

        Task {
            defer { busy = false }
            // auth.type "none" means a reverse proxy owns identity; there is
            // no token for the client to fetch.
            guard tenant.auth.type == .oidc else {
                config.connect(to: tenant, as: nil)
                return
            }
            do {
                let identity = try await OIDCService.shared.signIn(tenant: tenant)
                config.connect(to: tenant, as: identity)
            } catch OIDCError.cancelled {
                // User backed out of the web sheet; stay put, say nothing.
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }
}
