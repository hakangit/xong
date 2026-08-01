/* Xong — i18n. Vietnamese / English / 简体中文.
 * Tone rule (SPEC principle 4) holds in all three languages: calm, no guilt,
 * no alarm words (no 逾期/警告, no "overdue!" scolding).
 */
(function () {
'use strict';

var KEY = 'xong.lang';
var LOCALES = { vi: 'vi-VN', en: 'en', zh: 'zh-CN' };

var dict = {
  vi: {
    appTitle: 'Xong — việc hôm nay',
    navToday: 'Hôm nay',
    navLists: 'Danh sách',
    navRecap: 'Tuần này',
    muteOff: 'Tắt tiếng',
    muteOn: 'Bật tiếng',
    greetMorning: 'Chào buổi sáng',
    greetAfternoon: 'Chào buổi chiều',
    greetEvening: 'Chào buổi tối',
    streakDays: '🔥 {n} ngày liên tiếp',
    streakQuiet: 'Hôm nay là ngày đẹp để bắt đầu',
    focusTitle: '3 việc hôm nay',
    focusHint: 'Đánh dấu ★ để chọn tối đa 3 việc quan trọng nhất hôm nay.',
    focusEmpty: 'Chưa chọn việc nào — một khởi đầu nhẹ nhàng cũng tuyệt lắm.',
    allDone: 'Xong cả {n}. Hôm nay đủ rồi.',
    maxThree: 'Tối đa 3 việc thôi — bỏ bớt một việc nhé.',
    overdueTitle: 'Lặng lẽ chờ bạn',
    dueTodayTitle: 'Đến hạn hôm nay',
    emptyList: 'Trống trơn — thoải mái nhé.',
    addPlaceholder: 'Thêm việc, Enter là xong',
    newListPlaceholder: '+ Danh sách mới',
    createListEmpty: 'Tạo một danh sách để bắt đầu nhé.',
    doneToday: 'Đã xong hôm nay · {n}',
    chipToday: 'hôm nay {time}',
    sinceYesterday: 'từ hôm qua',
    sinceDaysAgo: 'từ {n} ngày trước',
    firstStep: 'Bước đầu:',
    edNext: 'Bước đầu tiên',
    edNextPh: 'Hành động nhỏ nhất, ví dụ: mở file lên',
    edWhen: 'Khi nào / ở đâu',
    edWhenPh: '9:30, tại bàn làm việc',
    edDue: 'Đến hạn',
    edNotes: 'Ghi chú',
    edSave: 'Lưu',
    edClose: 'Đóng',
    edDelete: 'Xoá',
    edNudge: 'Việc này hơi lớn — bước đầu tiên là gì?',
    attHead: 'Tệp & liên kết',
    attAddFile: '＋ Tệp',
    attAddLink: '＋ Liên kết',
    attDelete: 'Gỡ bỏ',
    attUploading: 'Đang tải lên…',
    attTooLarge: 'Tệp quá lớn (tối đa 20MB).',
    attBadType: 'Loại tệp không hỗ trợ.',
    attFailed: 'Không thêm được, thử lại nhé.',
    attLinkPrompt: 'Dán liên kết (http/https):',
    askAssistant: 'Nhờ {name}…',
    askSend: 'Gửi',
    asstWorking: '{name} đang làm…',
    asstDone: 'Xong rồi.',
    asstNone: 'Bạn chưa có trợ lý.',
    asstUnavailable: 'Trợ lý tạm thời không sẵn sàng.',
    asstFailed: '{name} chưa trả lời được, thử lại nhé.',
    listsTitle: 'Danh sách',
    recapTitle: 'Tuần này',
    recapHeadline: 'Tuần này bạn đã xong <strong>{n}</strong> việc. Tuyệt vỡi!',
    recapHeadlineEmpty: 'Tuần mới đang mở ra — việc đầu tiên hôm nay sẽ là khởi đầu đẹp.',
    recapBestDay: 'Ngày rực rỡ nhất: {day} — {n} việc.',
    recapWeek: '7 ngày qua',
    recapWins: 'Những việc đã xong',
    recapTeaching: 'Tuần này chị đã dạy {agent} một kỹ năng. {skill} — {agentAgain} đã tự làm đúng lần đầu vào {weekday}. Kiến thức này ở lại với công ty là nhờ chị.',
    precedentsTitle: 'Tiền lệ',
    precedentsRulesOf: 'Quy tắc của {name}',
    precedentsRules: 'Quy tắc đã thống nhất',
    precedentsRecent: 'Quyết định gần đây',
    precedentsEmpty: 'Chưa có tiền lệ nào.',
    precedentPending: 'chờ xác nhận',
    precedentSuperseded: 'đã thay bằng #{id}',
    precedentMarkCorrected: 'Đánh dấu đã sửa',
    precedentApproved: '{name} duyệt',
    precedentBack: '← Hôm nay',
    precedentFailed: 'Chưa tải được tiền lệ.',
    weaveTooltip: '{threads} kỹ năng đã dạy · {passes} lần được dùng',
    todayShort: 'nay',
    todayName: 'Hôm nay',
    countItems: '{n} việc',
    ariaStar: 'Chọn vào 3 việc hôm nay',
    ariaCheck: 'Xong việc này'
  },

  en: {
    appTitle: 'Xong — today',
    navToday: 'Today',
    navLists: 'Lists',
    navRecap: 'This week',
    muteOff: 'Mute',
    muteOn: 'Unmute',
    greetMorning: 'Good morning',
    greetAfternoon: 'Good afternoon',
    greetEvening: 'Good evening',
    streakDays: '🔥 {n}-day streak',
    streakQuiet: 'Today is a good day to begin',
    focusTitle: "Today's 3",
    focusHint: 'Tap ★ to choose up to 3 things that matter most today.',
    focusEmpty: 'Nothing chosen yet — a gentle start still counts.',
    allDone: 'All {n} done. Today is enough.',
    maxThree: 'Three is plenty — let one go first.',
    overdueTitle: 'Quietly waiting',
    dueTodayTitle: 'Due today',
    emptyList: 'All clear — breathe easy.',
    addPlaceholder: 'Add a task, Enter to save',
    newListPlaceholder: '+ New list',
    createListEmpty: 'Create a list to get started.',
    doneToday: 'Done today · {n}',
    chipToday: 'today {time}',
    sinceYesterday: 'since yesterday',
    sinceDaysAgo: 'since {n} days ago',
    firstStep: 'First step:',
    edNext: 'First step',
    edNextPh: 'Smallest action, e.g. open the file',
    edWhen: 'When / where',
    edWhenPh: '9:30, at my desk',
    edDue: 'Due',
    edNotes: 'Notes',
    edSave: 'Save',
    edClose: 'Close',
    edDelete: 'Delete',
    edNudge: "This looks big — what's the very first step?",
    attHead: 'Files & links',
    attAddFile: '＋ File',
    attAddLink: '＋ Link',
    attDelete: 'Remove',
    attUploading: 'Uploading…',
    attTooLarge: 'File too large (20MB max).',
    attBadType: 'File type not supported.',
    attFailed: "Couldn't add that — try again.",
    attLinkPrompt: 'Paste a link (http/https):',
    askAssistant: 'Ask {name}…',
    askSend: 'Send',
    asstWorking: '{name} is on it…',
    asstDone: 'Done.',
    asstNone: "You don't have an assistant.",
    asstUnavailable: 'Assistant is unavailable right now.',
    asstFailed: "{name} couldn't respond — try again.",
    listsTitle: 'Lists',
    recapTitle: 'This week',
    recapHeadline: "You've finished <strong>{n}</strong> things this week. Lovely!",
    recapHeadlineEmpty: "A fresh week is opening — today's first task is a beautiful start.",
    recapBestDay: 'Brightest day: {day} — {n} done.',
    recapWeek: 'Last 7 days',
    recapWins: 'Finished this week',
    recapTeaching: 'This week you taught {agent} a skill. {skill} — {agentAgain} did it correctly on their own for the first time on {weekday}. This knowledge stays with the company because of you.',
    precedentsTitle: 'Precedents',
    precedentsRulesOf: "{name}'s rules",
    precedentsRules: 'Agreed rules',
    precedentsRecent: 'Recent decisions',
    precedentsEmpty: 'No precedents yet.',
    precedentPending: 'awaiting confirmation',
    precedentSuperseded: 'replaced by #{id}',
    precedentMarkCorrected: 'Mark corrected',
    precedentApproved: 'approved by {name}',
    precedentBack: '← Today',
    precedentFailed: 'Could not load precedents.',
    weaveTooltip: '{threads} skills taught · {passes} uses',
    todayShort: 'today',
    todayName: 'Today',
    countItems: '{n} done',
    ariaStar: "Pick for today's 3",
    ariaCheck: 'Mark this done'
  },

  zh: {
    appTitle: 'Xong — 今天',
    navToday: '今天',
    navLists: '列表',
    navRecap: '本周',
    muteOff: '静音',
    muteOn: '取消静音',
    greetMorning: '早上好',
    greetAfternoon: '下午好',
    greetEvening: '晚上好',
    streakDays: '🔥 连续 {n} 天',
    streakQuiet: '今天是开始的好日子',
    focusTitle: '今日三件事',
    focusHint: '点 ★ 选出今天最重要的 3 件事。',
    focusEmpty: '还没有选择 — 轻轻开始也很好。',
    allDone: '{n} 件全部完成。今天这样就很好。',
    maxThree: '三件就好 — 先放下一件吧。',
    overdueTitle: '静静等你',
    dueTodayTitle: '今天到期',
    emptyList: '空空的 — 放轻松。',
    addPlaceholder: '添加任务，回车即可',
    newListPlaceholder: '+ 新列表',
    createListEmpty: '创建一个列表，轻轻开始吧。',
    doneToday: '今天已完成 · {n}',
    chipToday: '今天 {time}',
    sinceYesterday: '从昨天',
    sinceDaysAgo: '从 {n} 天前',
    firstStep: '第一步：',
    edNext: '第一步',
    edNextPh: '最小的动作，比如：打开文件',
    edWhen: '何时 / 何地',
    edWhenPh: '9:30，在书桌前',
    edDue: '截止',
    edNotes: '备注',
    edSave: '保存',
    edClose: '关闭',
    edDelete: '删除',
    edNudge: '这件事有点大 — 第一步是什么？',
    attHead: '文件与链接',
    attAddFile: '＋ 文件',
    attAddLink: '＋ 链接',
    attDelete: '移除',
    attUploading: '上传中…',
    attTooLarge: '文件太大（最多 20MB）。',
    attBadType: '不支持的文件类型。',
    attFailed: '添加失败，请再试一次。',
    attLinkPrompt: '粘贴链接（http/https）：',
    askAssistant: '让 {name}…',
    askSend: '发送',
    asstWorking: '{name} 正在处理…',
    asstDone: '完成了。',
    asstNone: '你还没有助理。',
    asstUnavailable: '助理暂时不可用。',
    asstFailed: '{name} 暂时无法回复，请再试一次。',
    listsTitle: '列表',
    recapTitle: '本周',
    recapHeadline: '本周你完成了 <strong>{n}</strong> 件事，真棒！',
    recapHeadlineEmpty: '新的一周刚刚开始 — 今天完成第一件事，就是美好的开始。',
    recapBestDay: '最闪耀的一天：{day} — {n} 件。',
    recapWeek: '过去 7 天',
    recapWins: '已完成的事',
    recapTeaching: '这周你教会了 {agent} 一项技能。{skill} — {agentAgain} 在{weekday}第一次独立做对了。因为有你，这份知识留在了公司。',
    precedentsTitle: '先例',
    precedentsRulesOf: '{name} 的规则',
    precedentsRules: '已定的规则',
    precedentsRecent: '最近的决定',
    precedentsEmpty: '还没有先例。',
    precedentPending: '待确认',
    precedentSuperseded: '已由 #{id} 取代',
    precedentMarkCorrected: '标记为已更正',
    precedentApproved: '由 {name} 批准',
    precedentBack: '← 今天',
    precedentFailed: '暂时无法加载先例。',
    weaveTooltip: '已教 {threads} 项技能 · 被使用 {passes} 次',
    todayShort: '今天',
    todayName: '今天',
    countItems: '{n} 件',
    ariaStar: '选入今日三件事',
    ariaCheck: '完成这件事'
  }
};

var lang = null;

function detect() {
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  if (saved && dict[saved]) return saved;
  var n = (navigator.language || 'en').toLowerCase();
  if (n.indexOf('vi') === 0) return 'vi';
  if (n.indexOf('zh') === 0) return 'zh';
  return 'en';
}

function get() {
  if (!lang) lang = detect();
  return lang;
}

function set(l) {
  if (!dict[l]) return;
  lang = l;
  try { localStorage.setItem(KEY, l); } catch (e) {}
}

function t(key, vars) {
  var s = (dict[get()] && dict[get()][key]) || dict.en[key] || key;
  if (vars) {
    Object.keys(vars).forEach(function (k) {
      s = s.replace('{' + k + '}', vars[k]);
    });
  }
  return s;
}

function locale() { return LOCALES[get()]; }

window.XongI18n = { t: t, get: get, set: set, locale: locale, langs: ['vi', 'en', 'zh'] };
})();
