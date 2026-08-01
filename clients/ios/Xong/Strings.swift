import Foundation

/// Onboarding lives in native SwiftUI, so it cannot draw on js/i18n.js. The
/// tone rule from SPEC principle 4 still applies in all three languages: calm,
/// no guilt, no alarm words.
enum Strings {
    enum Key {
        case welcomeTitle, welcomeBody
        case useLocal, useLocalHint
        case connectServer, connectServerHint
        case connectTitle, connectHint, connectPlaceholder, connectAction, connectSearching
        case confirmTitle, confirmBody, confirmSignIn, confirmSwitch
        case signingIn, back, cancel, retry
        case errNotHTTPS, errNoConfig, errMalformed, errSignIn, errOffline
        // Main UI
        case navToday, navLists, navRecap
        case greetMorning, greetAfternoon, greetEvening
        case streakDays, streakQuiet
        case focusTitle, focusHint, focusEmpty, maxThree
        case overdueTitle, dueTodayTitle, emptyList, addPlaceholder
        case newListPlaceholder, defaultListName, firstStep
        case sinceYesterday, sinceDaysAgo, dueAtTime
        case recapTitle, recapTotal, recapBestDay, recapEmpty
        case offline, done, delete
        // Settings
        case settings, settingsLanguage, settingsLanguageSystem, settingsConnection
        case settingsLocalMode, settingsSignOut, settingsSwitchServer, settingsConnected
        case settingsSwitchKeepsData, settingsSound
        // Task editor
        case edNudge, edNext, edNextPh, edWhen, edWhenPh, edDue, edNotes
        case edSave, edClose, edDelete
        // Attachments
        case attachments, attachLinkPh, attachFailed
        // Assistant
        case askAssistant, asstWorking, asstNone, asstUnavailable, asstFailed
        // Weave + precedents
        case weaveTooltip
        case precedentsTitle, precedentsRules, precedentsRulesOf, precedentsRecent
        case precedentsEmpty, precedentFailed, precedentBack, precedentCorrect
        case precedentSuperseded
    }

    /// Explicit choice from Settings; nil follows the device.
    static var override: String?

    static var language: String {
        if let override, ["vi", "en", "zh"].contains(override) { return override }
        let preferred = Locale.preferredLanguages.first ?? "en"
        if preferred.hasPrefix("vi") { return "vi" }
        if preferred.hasPrefix("zh") { return "zh" }
        return "en"
    }

    static var localeIdentifier: String {
        ["vi": "vi_VN", "zh": "zh_Hans", "en": "en"][language] ?? "en"
    }

    /// Substitutes {n} the way i18n.js does, so copy stays portable between
    /// the web app and here.
    static func t(_ key: Key, _ n: Int) -> String {
        t(key).replacingOccurrences(of: "{n}", with: String(n))
    }

    static func t(_ key: Key) -> String {
        let table = dictionary[language] ?? dictionary["en"]!
        return table[key] ?? dictionary["en"]![key] ?? ""
    }

    private static let dictionary: [String: [Key: String]] = [
        "vi": [
            .welcomeTitle: "Xong.",
            .welcomeBody: "Việc hôm nay, gọn gàng.",
            .useLocal: "Dùng riêng trên máy này",
            .useLocalHint: "Mọi thứ ở lại trong điện thoại. Không cần tài khoản.",
            .connectServer: "Kết nối với công ty",
            .connectServerHint: "Đồng bộ với máy chủ Xong của tổ chức bạn.",
            .connectTitle: "Kết nối",
            .connectHint: "Nhập email công việc, hoặc địa chỉ máy chủ.",
            .connectPlaceholder: "ban@example.com",
            .connectAction: "Tiếp tục",
            .connectSearching: "Đang tìm máy chủ…",
            .confirmTitle: "Đã tìm thấy",
            .confirmBody: "Bạn sẽ đăng nhập và đồng bộ việc với máy chủ này.",
            .confirmSignIn: "Đăng nhập",
            .confirmSwitch: "Đổi địa chỉ khác",
            .signingIn: "Đang đăng nhập…",
            .back: "Quay lại",
            .cancel: "Bỏ qua",
            .retry: "Thử lại",
            .errNotHTTPS: "Địa chỉ cần dùng HTTPS.",
            .errNoConfig: "Chưa tìm thấy máy chủ Xong ở địa chỉ này.",
            .errMalformed: "Máy chủ trả về cấu hình không đọc được.",
            .errSignIn: "Chưa đăng nhập được. Thử lại nhé.",
            .errOffline: "Đang dùng dữ liệu ngoại tuyến.",
            .navToday: "Hôm nay",
            .navLists: "Danh sách",
            .navRecap: "Tuần này",
            .greetMorning: "Chào buổi sáng",
            .greetAfternoon: "Chào buổi chiều",
            .greetEvening: "Chào buổi tối",
            .streakDays: "{n} ngày liên tiếp",
            .streakQuiet: "Hôm nay là ngày đẹp để bắt đầu",
            .focusTitle: "3 việc hôm nay",
            .focusHint: "Đánh dấu ★ để chọn tối đa 3 việc quan trọng nhất hôm nay.",
            .focusEmpty: "Chưa chọn việc nào — một khởi đầu nhẹ nhàng cũng tuyệt lắm.",
            .maxThree: "Tối đa 3 việc thôi — bỏ bớt một việc nhé.",
            .overdueTitle: "Lặng lẽ chờ bạn",
            .dueTodayTitle: "Đến hạn hôm nay",
            .emptyList: "Trống trơn — thoải mái nhé.",
            .addPlaceholder: "Thêm việc, Enter là xong",
            .newListPlaceholder: "Danh sách mới",
            .defaultListName: "Việc của tôi",
            .firstStep: "Bước đầu:",
            .sinceYesterday: "từ hôm qua",
            .sinceDaysAgo: "từ {n} ngày trước",
            .dueAtTime: "hôm nay",
            .recapTitle: "Tuần này",
            .recapTotal: "Đã xong {n} việc",
            .recapBestDay: "Ngày nhiều nhất",
            .recapEmpty: "Tuần này còn nhẹ nhàng — vẫn ổn mà.",
            .offline: "Ngoại tuyến",
            .done: "Xong",
            .delete: "Xoá",
            .settings: "Cài đặt",
            .settingsLanguage: "Ngôn ngữ",
            .settingsLanguageSystem: "Theo máy",
            .settingsConnection: "Kết nối",
            .settingsLocalMode: "Chỉ trên máy này",
            .settingsSignOut: "Đăng xuất",
            .settingsSwitchServer: "Đổi máy chủ",
            .settingsConnected: "Đang kết nối",
            .settingsSwitchKeepsData: "Việc đã lưu trên máy này vẫn được giữ lại.",
            .settingsSound: "Âm thanh khi xong",
            .edNudge: "Việc này hơi rộng — bước đầu tiên là gì nhỉ?",
            .edNext: "Bước đầu tiên",
            .edNextPh: "Hành động nhỏ nhất, ví dụ: mở file lên",
            .edWhen: "Khi nào / ở đâu",
            .edWhenPh: "9:30, tại bàn làm việc",
            .edDue: "Đến hạn",
            .edNotes: "Ghi chú",
            .edSave: "Lưu",
            .edClose: "Đóng",
            .edDelete: "Xoá việc này",
            .attachments: "Tệp đính kèm",
            .attachLinkPh: "Dán một đường dẫn",
            .attachFailed: "Chưa gửi được tệp. Thử lại nhé.",
            .askAssistant: "Hỏi {name}…",
            .asstWorking: "{name} đang làm…",
            .asstNone: "Bạn chưa có trợ lý.",
            .asstUnavailable: "{name} đang bận. Thử lại sau nhé.",
            .asstFailed: "Chưa gửi được. Thử lại nhé.",
            .weaveTooltip: "{threads} mạch · {passes} lượt",
            .precedentsTitle: "Tiền lệ",
            .precedentsRules: "Nguyên tắc",
            .precedentsRulesOf: "Nguyên tắc của {name}",
            .precedentsRecent: "Quyết định gần đây",
            .precedentsEmpty: "Chưa có tiền lệ nào.",
            .precedentFailed: "Chưa tải được tiền lệ.",
            .precedentBack: "Quay lại",
            .precedentCorrect: "Cần chỉnh",
            .precedentSuperseded: "đã thay thế",
        ],
        "en": [
            .welcomeTitle: "Xong.",
            .welcomeBody: "Today's work, quietly.",
            .useLocal: "Use on this phone only",
            .useLocalHint: "Everything stays on your device. No account needed.",
            .connectServer: "Connect to my company",
            .connectServerHint: "Sync with your organization's Xong server.",
            .connectTitle: "Connect",
            .connectHint: "Enter your work email, or a server address.",
            .connectPlaceholder: "you@example.com",
            .connectAction: "Continue",
            .connectSearching: "Looking for your server…",
            .confirmTitle: "Found it",
            .confirmBody: "You'll sign in and sync your tasks with this server.",
            .confirmSignIn: "Sign in",
            .confirmSwitch: "Use a different address",
            .signingIn: "Signing in…",
            .back: "Back",
            .cancel: "Not now",
            .retry: "Try again",
            .errNotHTTPS: "The address needs to use HTTPS.",
            .errNoConfig: "No Xong server found at that address.",
            .errMalformed: "That server returned a config we couldn't read.",
            .errSignIn: "Couldn't sign in. Let's try again.",
            .errOffline: "Showing offline data.",
            .navToday: "Today",
            .navLists: "Lists",
            .navRecap: "This week",
            .greetMorning: "Good morning",
            .greetAfternoon: "Good afternoon",
            .greetEvening: "Good evening",
            .streakDays: "{n}-day streak",
            .streakQuiet: "Today is a good day to begin",
            .focusTitle: "Today's 3",
            .focusHint: "Tap ★ to choose up to 3 things that matter most today.",
            .focusEmpty: "Nothing chosen yet — a gentle start still counts.",
            .maxThree: "Three is the most — let one go first.",
            .overdueTitle: "Quietly waiting",
            .dueTodayTitle: "Due today",
            .emptyList: "All clear — breathe easy.",
            .addPlaceholder: "Add a task, Enter to save",
            .newListPlaceholder: "New list",
            .defaultListName: "My tasks",
            .firstStep: "First step:",
            .sinceYesterday: "since yesterday",
            .sinceDaysAgo: "since {n} days ago",
            .dueAtTime: "today",
            .recapTitle: "This week",
            .recapTotal: "{n} done",
            .recapBestDay: "Best day",
            .recapEmpty: "A light week — that's fine too.",
            .offline: "Offline",
            .done: "Done",
            .delete: "Delete",
            .settings: "Settings",
            .settingsLanguage: "Language",
            .settingsLanguageSystem: "System",
            .settingsConnection: "Connection",
            .settingsLocalMode: "This phone only",
            .settingsSignOut: "Sign out",
            .settingsSwitchServer: "Switch server",
            .settingsConnected: "Connected to",
            .settingsSwitchKeepsData: "Tasks saved on this phone are kept.",
            .settingsSound: "Sound on completion",
            .edNudge: "This one is a bit broad — what is the first step?",
            .edNext: "First step",
            .edNextPh: "The smallest action, e.g. open the file",
            .edWhen: "When / where",
            .edWhenPh: "9:30, at my desk",
            .edDue: "Due",
            .edNotes: "Notes",
            .edSave: "Save",
            .edClose: "Close",
            .edDelete: "Delete this task",
            .attachments: "Attachments",
            .attachLinkPh: "Paste a link",
            .attachFailed: "Couldn't send that file. Try again.",
            .askAssistant: "Ask {name}…",
            .asstWorking: "{name} is working…",
            .asstNone: "You don't have an assistant yet.",
            .asstUnavailable: "{name} is busy. Try again shortly.",
            .asstFailed: "Couldn't send that. Try again.",
            .weaveTooltip: "{threads} threads · {passes} passes",
            .precedentsTitle: "Precedents",
            .precedentsRules: "Standing rules",
            .precedentsRulesOf: "{name}'s standing rules",
            .precedentsRecent: "Recent decisions",
            .precedentsEmpty: "No precedents yet.",
            .precedentFailed: "Couldn't load precedents.",
            .precedentBack: "Back",
            .precedentCorrect: "Needs correcting",
            .precedentSuperseded: "superseded",
        ],
        "zh": [
            .welcomeTitle: "Xong.",
            .welcomeBody: "今天的事，安安静静。",
            .useLocal: "仅在这台手机上使用",
            .useLocalHint: "所有内容都留在手机里，无需账号。",
            .connectServer: "连接到公司",
            .connectServerHint: "与所在组织的 Xong 服务器同步。",
            .connectTitle: "连接",
            .connectHint: "输入工作邮箱，或服务器地址。",
            .connectPlaceholder: "you@example.com",
            .connectAction: "继续",
            .connectSearching: "正在查找服务器…",
            .confirmTitle: "已找到",
            .confirmBody: "你将登录并与该服务器同步事项。",
            .confirmSignIn: "登录",
            .confirmSwitch: "换一个地址",
            .signingIn: "正在登录…",
            .back: "返回",
            .cancel: "暂不",
            .retry: "再试一次",
            .errNotHTTPS: "地址需要使用 HTTPS。",
            .errNoConfig: "在该地址没有找到 Xong 服务器。",
            .errMalformed: "该服务器返回的配置无法读取。",
            .errSignIn: "暂时无法登录，再试一次。",
            .errOffline: "正在显示离线数据。",
            .navToday: "今天",
            .navLists: "清单",
            .navRecap: "本周",
            .greetMorning: "早上好",
            .greetAfternoon: "下午好",
            .greetEvening: "晚上好",
            .streakDays: "连续 {n} 天",
            .streakQuiet: "今天很适合开始",
            .focusTitle: "今天的三件事",
            .focusEmpty: "还没有选 — 轻轻开始也很好。",
            .focusHint: "点 ★ 选出今天最重要的三件事。",
            .maxThree: "最多三件 — 先放下一件吧。",
            .overdueTitle: "静静等着你",
            .dueTodayTitle: "今天到期",
            .emptyList: "空空的 — 放轻松。",
            .addPlaceholder: "添加事项，回车保存",
            .newListPlaceholder: "新清单",
            .defaultListName: "我的事项",
            .firstStep: "第一步：",
            .sinceYesterday: "从昨天起",
            .sinceDaysAgo: "从 {n} 天前起",
            .dueAtTime: "今天",
            .recapTitle: "本周",
            .recapTotal: "完成 {n} 件",
            .recapBestDay: "最多的一天",
            .recapEmpty: "这周比较轻 — 也很好。",
            .offline: "离线",
            .done: "完成",
            .delete: "删除",
            .settings: "设置",
            .settingsLanguage: "语言",
            .settingsLanguageSystem: "跟随系统",
            .settingsConnection: "连接",
            .settingsLocalMode: "仅本机",
            .settingsSignOut: "退出登录",
            .settingsSwitchServer: "更换服务器",
            .settingsConnected: "已连接",
            .settingsSwitchKeepsData: "本机已保存的事项会保留。",
            .settingsSound: "完成提示音",
            .edNudge: "这件事有点宽 — 第一步是什么？",
            .edNext: "第一步",
            .edNextPh: "最小的动作，例如：打开文件",
            .edWhen: "何时 / 何地",
            .edWhenPh: "9:30，在工位",
            .edDue: "到期",
            .edNotes: "备注",
            .edSave: "保存",
            .edClose: "关闭",
            .edDelete: "删除这件事",
            .attachments: "附件",
            .attachLinkPh: "粘贴一个链接",
            .attachFailed: "文件没能发送，再试一次。",
            .askAssistant: "问 {name}…",
            .asstWorking: "{name} 正在处理…",
            .asstNone: "你还没有助理。",
            .asstUnavailable: "{name} 正忙，稍后再试。",
            .asstFailed: "没能发送，再试一次。",
            .weaveTooltip: "{threads} 条脉络 · {passes} 次",
            .precedentsTitle: "先例",
            .precedentsRules: "既定原则",
            .precedentsRulesOf: "{name} 的既定原则",
            .precedentsRecent: "近期决定",
            .precedentsEmpty: "还没有先例。",
            .precedentFailed: "先例加载失败。",
            .precedentBack: "返回",
            .precedentCorrect: "需要修正",
            .precedentSuperseded: "已被取代",
        ],
    ]
}
