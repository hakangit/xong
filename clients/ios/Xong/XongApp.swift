import SwiftUI

@main
struct XongApp: App {
    @StateObject private var config = AppConfiguration()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(config)
                .preferredColorScheme(nil)
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var config: AppConfiguration

    var body: some View {
        switch config.mode {
        case .unset:
            OnboardingView()
        case .local, .server:
            // Rebuilt when the tenant or language changes, so the store is
            // never left pointing at the previous tenant's cache.
            MainView(store: TaskStore(configuration: config))
                .id("\(config.namespace)-\(config.revision)")
        }
    }
}

struct MainView: View {
    @EnvironmentObject private var config: AppConfiguration
    @StateObject var store: TaskStore
    @State private var tab = Tab.today
    @State private var showSettings = false
    @State private var skillSlug: String?

    enum Tab: Hashable { case today, lists, recap }

    init(store: TaskStore) {
        _store = StateObject(wrappedValue: store)
    }

    var body: some View {
        ZStack(alignment: .top) {
            Color.xBackground.ignoresSafeArea()

            TabView(selection: $tab) {
                todayTab
                    .tag(Tab.today)
                    .tabItem { Label(Strings.t(.navToday), systemImage: "sun.max") }
                ListsView()
                    .tag(Tab.lists)
                    .tabItem { Label(Strings.t(.navLists), systemImage: "list.bullet") }
                RecapView()
                    .tag(Tab.recap)
                    .tabItem { Label(Strings.t(.navRecap), systemImage: "chart.bar") }
            }
            .tint(Color.xInk)

            headerControls
        }
        .environmentObject(store)
        .task {
            await config.refreshTenant()
            await store.refresh()
        }
        .sheet(isPresented: $showSettings) { SettingsView().environmentObject(store) }
        .sheet(item: Binding(get: { skillSlug.map(SkillRoute.init) },
                             set: { skillSlug = $0?.slug })) { route in
            SkillTracesView(slug: route.slug).environmentObject(store)
        }
        .onOpenURL { url in
            // xong://skill/<slug> — mirrors the web app's #skill/<slug>, which
            // is likewise reachable only by link, not by navigation.
            guard url.scheme == "xong", url.host == "skill" else { return }
            let slug = url.pathComponents.filter { $0 != "/" }.first
            if let slug, !slug.isEmpty { skillSlug = slug }
        }
    }

    /// The assistant sits under Today only — it acts on today's work, and
    /// putting it on every tab would make it furniture.
    private var todayTab: some View {
        VStack(spacing: 0) {
            TodayView()
            if store.api != nil {
                AssistantBar()
            }
        }
    }

    private var headerControls: some View {
        HStack(spacing: 8) {
            Spacer()
            // Weave comes from the org module; a deployment without it would
            // just 404, so don't ask.
            if store.api != nil, store.supports("org") {
                WeaveMark()
            }
            Button { showSettings = true } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 17))
                    .foregroundStyle(Color.xMuted)
                    .frame(width: 44, height: 44)
                    .background(Color.xSurface, in: Circle())
            }
            .buttonStyle(.plain)
        }
        .padding(.trailing, 16)
        .padding(.top, 4)
    }
}

private struct SkillRoute: Identifiable {
    let slug: String
    var id: String { slug }
}
