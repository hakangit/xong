/* Xong — data layer.
 *
 * ApiClient targets /api/v1 (endpoints per SPEC.md) with an offline-first
 * design: localStorage cache + outbound op queue. Mock mode
 * (window.XONG_MOCK === true, or any file:// preview) serves seeded demo
 * data from a local engine; otherwise the real API is used.
 */
(function () {
'use strict';

var DB_KEY = 'xong.db.v1';
var QUEUE_KEY = 'xong.queue.v1';
var SEED_VERSION = 3;

/* ---------- date helpers (local time) ---------- */

function pad(n) { return String(n).padStart(2, '0'); }

function localDate(d) {
  d = d || new Date();
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
}

function dateOf(iso) {
  if (!iso) return null;
  return localDate(new Date(iso));
}

function daysAgo(n, hour) {
  var d = new Date();
  d.setDate(d.getDate() - n);
  d.setHours(hour == null ? 12 : hour, 0, 0, 0);
  return d;
}

function looksVague(title) {
  // SPEC heuristic: no verb / >10 words → nudge for a tiny next action.
  // Verb detection is unreliable for Vietnamese; word count is the safe half.
  return title.trim().split(/\s+/).length > 10;
}

/* ---------- LocalEngine: full API semantics against localStorage ---------- */

function LocalEngine() {
  this.db = this._load();
}

LocalEngine.prototype._load = function () {
  var isMock = window.XONG_MOCK === true || location.protocol === 'file:';
  var raw = null;
  try { raw = localStorage.getItem(DB_KEY); } catch (e) { /* file:// quirks */ }
  if (raw) {
    try {
      var db = JSON.parse(raw);
      var isDemo = db && db.meta && db.meta.seedVersion === SEED_VERSION;
      var isLive = db && db.meta && db.meta.seedVersion === 'live';
      // Real mode must never surface demo data: purge any cache left over
      // from a mock-mode visit (the "Vietnamese tasks" incident).
      if (isDemo && !isMock) {
        try { localStorage.removeItem(DB_KEY); localStorage.removeItem(QUEUE_KEY); } catch (e2) {}
      } else if ((isMock && isDemo) || (!isMock && isLive)) {
        return db;
      }
    } catch (e) { /* fall through */ }
  }
  if (!isMock) {
    var empty = { meta: { seedVersion: 'live' }, users: [], lists: [], tasks: [],
                  focus: { date: localDate(new Date()), task_ids: [] }, events: [] };
    this._save(empty);
    return empty;
  }
  var seeded = this._seed();
  this._save(seeded);
  return seeded;
};

LocalEngine.prototype._save = function (db) {
  this.db = db || this.db;
  try { localStorage.setItem(DB_KEY, JSON.stringify(this.db)); } catch (e) {}
};

LocalEngine.prototype._seed = function () {
  var now = new Date();
  function t(daysBack, hour) { return daysAgo(daysBack, hour).toISOString(); }
  var todayStr = localDate(now);

  var lists = [
    { id: 1, owner_id: 1, name: 'Việc của tôi', position: 0, archived: false },
    { id: 2, owner_id: 1, name: 'Công việc', position: 1, archived: false },
    { id: 3, owner_id: 1, name: 'Nhà', position: 2, archived: false }
  ];

  function task(id, listId, title, opts) {
    opts = opts || {};
    return {
      id: id,
      list_id: listId,
      title: title,
      next_action: opts.next_action || null,
      notes: opts.notes || null,
      due_at: opts.due_at || null,
      when_where: opts.when_where || null,
      position: opts.position != null ? opts.position : id,
      created_by: 'bạn',
      completed_at: opts.completed_at || null,
      created_at: t(opts.created_days_back != null ? opts.created_days_back : 1, 9),
      looks_vague: looksVague(title)
    };
  }

  var tasks = [
    task(1, 1, 'Gửi báo giá vải cho anh Hùng', {
      due_at: t(0, 17), next_action: 'Mở file báo giá mới nhất', position: 1 }),
    task(2, 1, 'Gọi xác nhận lịch giao hàng tuần này', {
      due_at: t(0, 12), next_action: 'Tra số điện thoại tài xế', position: 2 }),
    task(3, 1, 'Đọc 10 trang sách trước khi ngủ', {
      due_at: t(0, 22), when_where: '21:30, trên giường', position: 3 }),
    task(4, 2, 'Chuẩn bị slide họp sáng mai', {
      due_at: t(0, 18), when_where: '16:00, tại bàn làm việc', position: 4 }),
    task(5, 2, 'Trả lời email đối tác Nhật', {
      due_at: t(1, 17), next_action: 'Mở hộp thư, tìm thư mới nhất', position: 5 }),
    task(6, 1, 'Dọn lại góc bàn làm việc cho gọn', {
      due_at: t(2, 18), position: 6 }),
    task(7, 3, 'Mua sữa và trứng', { position: 7 }),
    task(8, 3, 'Tưới cây ban công', { when_where: '7:00, ban công', position: 8 }),
    task(9, 1, 'Sắp xếp lại toàn bộ tài liệu dự án cũ trong tủ hồ sơ tầng hai cho gọn gàng hơn', {
      position: 9 }),
    task(10, 2, 'Hỏi chị Lan về đợt nghỉ phép', { position: 10 }),
    // Past wins — these feed the streak and the weekly recap.
    task(11, 1, 'Nộp báo cáo tuần', { completed_at: t(1, 10) }),
    task(12, 1, 'Tập thể dục 20 phút', { completed_at: t(1, 7) }),
    task(13, 1, 'Đặt lịch khám răng', { completed_at: t(2, 15) }),
    task(14, 3, 'Gọi cho mẹ', { completed_at: t(2, 20) }),
    task(15, 1, 'Đọc xong chương 3', { completed_at: t(4, 21) }),
    task(16, 1, 'Viết nhật ký', { completed_at: t(4, 22) })
  ];

  var events = [];
  var eid = 1;
  tasks.forEach(function (tk) {
    if (tk.completed_at) {
      events.push({
        id: eid++, user_id: 1, event_type: 'task_completed',
        payload: JSON.stringify({ task_id: tk.id, title: tk.title }),
        created_at: tk.completed_at, actor: 'bạn'
      });
    }
  });

  return {
    meta: { seedVersion: SEED_VERSION, nextListId: 4, nextTaskId: 17, nextEventId: eid },
    users: [{ id: 1, username: 'ban', display_name: 'Bạn', tz: 'UTC' }],
    lists: lists,
    tasks: tasks,
    focus: { date: todayStr, task_ids: [1, 2, 3] },
    events: events
  };
};

LocalEngine.prototype._log = function (type, payload) {
  this.db.events.push({
    id: this.db.meta.nextEventId++, user_id: 1, event_type: type,
    payload: payload ? JSON.stringify(payload) : null,
    created_at: new Date().toISOString(), actor: 'bạn'
  });
};

LocalEngine.prototype._task = function (id) {
  return this.db.tasks.find(function (t) { return t.id === id; }) || null;
};

LocalEngine.prototype.me = function () { return this.db.users[0]; };

LocalEngine.prototype.getLists = function () {
  return this.db.lists
    .filter(function (l) { return !l.archived; })
    .sort(function (a, b) { return a.position - b.position; });
};

LocalEngine.prototype.createList = function (body) {
  var l = {
    id: this.db.meta.nextListId++, owner_id: 1,
    name: body.name, position: this.db.lists.length, archived: false
  };
  this.db.lists.push(l);
  this._log('list_created', { list_id: l.id, name: l.name });
  this._save();
  return l;
};

LocalEngine.prototype.getTasks = function (listId, includeCompleted) {
  return this.db.tasks
    .filter(function (t) {
      return (listId == null || t.list_id === listId) &&
             (includeCompleted || !t.completed_at);
    })
    .sort(function (a, b) { return a.position - b.position; });
};

LocalEngine.prototype.createTask = function (body) {
  var listId = body.list_id != null ? body.list_id : this.getLists()[0].id;
  var minPos = this.db.tasks.reduce(function (m, t) {
    return t.list_id === listId ? Math.min(m, t.position) : m;
  }, 0);
  var tk = {
    id: this.db.meta.nextTaskId++,
    list_id: listId,
    title: body.title,
    next_action: body.next_action || null,
    notes: body.notes || null,
    due_at: body.due_at || null,
    when_where: body.when_where || null,
    position: minPos - 1,
    created_by: 'bạn',
    completed_at: null,
    created_at: new Date().toISOString(),
    looks_vague: looksVague(body.title)
  };
  this.db.tasks.push(tk);
  this._log('task_created', { task_id: tk.id, title: tk.title });
  this._save();
  return tk;
};

LocalEngine.prototype.updateTask = function (id, body) {
  var tk = this._task(id);
  if (!tk) return null;
  ['title', 'next_action', 'notes', 'due_at', 'when_where', 'position', 'list_id']
    .forEach(function (k) { if (k in body) tk[k] = body[k]; });
  if ('title' in body) tk.looks_vague = looksVague(tk.title);
  this._save();
  return tk;
};

LocalEngine.prototype.deleteTask = function (id) {
  this.db.tasks = this.db.tasks.filter(function (t) { return t.id !== id; });
  this.db.focus.task_ids = this.db.focus.task_ids.filter(function (x) { return x !== id; });
  this._save();
};

LocalEngine.prototype.completeTask = function (id) {
  var tk = this._task(id);
  if (!tk) return null;
  if (!tk.completed_at) {
    tk.completed_at = new Date().toISOString();
    this._log('task_completed', { task_id: tk.id, title: tk.title });
  }
  this._save();
  return tk;
};

LocalEngine.prototype.uncompleteTask = function (id) {
  var tk = this._task(id);
  if (!tk) return null;
  tk.completed_at = null;
  this._log('task_uncompleted', { task_id: tk.id, title: tk.title });
  this._save();
  return tk;
};

LocalEngine.prototype._streak = function () {
  var days = {};
  this.db.tasks.forEach(function (t) {
    if (t.completed_at) days[dateOf(t.completed_at)] = true;
  });
  var cursor = new Date();
  if (!days[localDate(cursor)]) cursor.setDate(cursor.getDate() - 1);
  var n = 0;
  while (days[localDate(cursor)]) { n++; cursor.setDate(cursor.getDate() - 1); }
  return n;
};

LocalEngine.prototype.getToday = function () {
  var todayStr = localDate();
  if (this.db.focus.date !== todayStr) {
    this.db.focus = { date: todayStr, task_ids: [] };
    this._save();
  }
  var self = this;
  var open = this.db.tasks.filter(function (t) { return !t.completed_at; });
  var focusIds = this.db.focus.task_ids.filter(function (id) {
    var tk = self._task(id);
    return tk && !tk.completed_at;
  });
  function inFocus(t) { return focusIds.indexOf(t.id) !== -1; }
  var focus = focusIds.map(function (id) { return self._task(id); });
  var dueToday = open.filter(function (t) {
    return !inFocus(t) && dateOf(t.due_at) === todayStr;
  });
  var overdue = open.filter(function (t) {
    var d = dateOf(t.due_at);
    return !inFocus(t) && d && d < todayStr;
  }).sort(function (a, b) { return a.due_at < b.due_at ? 1 : -1; });
  var defList = this.getLists()[0];
  var shown = {};
  focus.concat(dueToday, overdue).forEach(function (t) { shown[t.id] = true; });
  var defTasks = open.filter(function (t) {
    return t.list_id === defList.id && !shown[t.id];
  }).sort(function (a, b) { return a.position - b.position; });
  return {
    date: todayStr,
    streak: this._streak(),
    focus: focus,
    due_today: dueToday,
    overdue: overdue,
    default_list: defList,
    default_tasks: defTasks
  };
};

LocalEngine.prototype.getFocus = function () {
  var self = this;
  var todayStr = localDate();
  if (this.db.focus.date !== todayStr) this.db.focus = { date: todayStr, task_ids: [] };
  return {
    date: this.db.focus.date,
    task_ids: this.db.focus.task_ids,
    tasks: this.db.focus.task_ids.map(function (id) { return self._task(id); })
      .filter(Boolean)
  };
};

LocalEngine.prototype.setFocus = function (taskIds) {
  this.db.focus = { date: localDate(), task_ids: taskIds.slice(0, 3) };
  this._log('focus_set', { task_ids: this.db.focus.task_ids });
  this._save();
  return this.getFocus();
};

LocalEngine.prototype.getWeeklyRecap = function () {
  var days = [];
  var total = 0;
  var bestDay = null;
  var bestCount = 0;
  for (var i = 6; i >= 0; i--) {
    var d = daysAgo(i, 12);
    var key = localDate(d);
    var wins = this.db.tasks.filter(function (t) {
      return t.completed_at && dateOf(t.completed_at) === key;
    });
    days.push({
      date: key,
      count: wins.length,
      titles: wins.map(function (t) { return t.title; })
    });
    total += wins.length;
    if (wins.length > bestCount) { bestCount = wins.length; bestDay = key; }
  }
  return {
    streak: this._streak(),
    total: total,
    best_day: bestDay,
    best_day_count: bestCount,
    days: days,
    teaching_sessions: []
  };
};

/* ---------- ApiClient: /api/v1 with offline-first cache + op queue ---------- */

function ApiClient(opts) {
  opts = opts || {};
  this.baseUrl = opts.baseUrl || '/api/v1';
  this.capabilities = [];
  // Real API when served by the app (http/https, same-origin proxy
  // session provides identity). Mock only for file:// (local file preview)
  // or an explicit window.XONG_MOCK = true.
  this.mock = window.XONG_MOCK === true || location.protocol === 'file:';
  this.engine = new LocalEngine();
  if (!this.mock) {
    var self = this;
    this.flushQueue();
    window.addEventListener('online', function () { self.flushQueue(); });
  }
}

ApiClient.prototype.loadCapabilities = async function () {
  if (this.mock) return this.capabilities;
  try {
    var configUrl = new URL(this.baseUrl, location.href);
    configUrl.pathname = '/.well-known/xong-config';
    configUrl.search = '';
    var res = await fetch(configUrl.toString());
    if (res.ok) {
      var config = await res.json();
      this.capabilities = Array.isArray(config.capabilities) ? config.capabilities : [];
    }
  } catch (e) {}
  return this.capabilities;
};

ApiClient.prototype.hasCapability = function (name) {
  return this.capabilities.indexOf(name) !== -1;
};

ApiClient.prototype._queue = function (op) {
  var q = [];
  try { q = JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'); } catch (e) {}
  q.push(op);
  try { localStorage.setItem(QUEUE_KEY, JSON.stringify(q)); } catch (e) {}
};

ApiClient.prototype.flushQueue = async function () {
  var q = [];
  try { q = JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'); } catch (e) {}
  if (!q.length) return;
  var remaining = [];
  for (var i = 0; i < q.length; i++) {
    try {
      var res = await fetch(this.baseUrl + q[i].path, {
        method: q[i].method,
        headers: { 'Content-Type': 'application/json' },
        body: q[i].body ? JSON.stringify(q[i].body) : undefined
      });
      if (!res.ok) remaining.push(q[i]);
    } catch (e) {
      remaining.push.apply(remaining, q.slice(i));
      break;
    }
  }
  try { localStorage.setItem(QUEUE_KEY, JSON.stringify(remaining)); } catch (e) {}
};

// Live mode: fetch first, local engine as optimistic mirror + offline fallback.
ApiClient.prototype._call = async function (method, path, body, localFn) {
  if (this.mock) return localFn();
  try {
    var res = await fetch(this.baseUrl + path, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.status === 204 ? null : await res.json();
  } catch (e) {
    if (method !== 'GET') {
      this._queue({ method: method, path: path, body: body, ts: Date.now() });
    }
    return localFn();
  }
};

ApiClient.prototype.me = function () {
  var e = this.engine;
  return this._call('GET', '/me', null, function () { return e.me(); });
};
ApiClient.prototype.getPerson = async function (username) {
  if (this.mock) return { username: username, weave: { threads: 0, passes: 0 } };
  try {
    var res = await fetch(this.baseUrl + '/org/people/' + encodeURIComponent(username));
    if (!res.ok) return null;
    return await res.json();
  } catch (e) { return null; }
};
ApiClient.prototype.getLists = function () {
  var e = this.engine;
  return this._call('GET', '/lists', null, function () { return e.getLists(); });
};
ApiClient.prototype.createList = function (name) {
  var e = this.engine;
  return this._call('POST', '/lists', { name: name }, function () {
    return e.createList({ name: name });
  });
};
ApiClient.prototype.getTasks = function (listId, includeCompleted) {
  var e = this.engine;
  var q = '?list_id=' + listId + (includeCompleted ? '&include_completed=true' : '');
  return this._call('GET', '/tasks' + q, null, function () {
    return e.getTasks(listId, includeCompleted);
  });
};
ApiClient.prototype.createTask = function (body) {
  var e = this.engine;
  return this._call('POST', '/tasks', body, function () { return e.createTask(body); });
};
ApiClient.prototype.updateTask = function (id, body) {
  var e = this.engine;
  return this._call('PATCH', '/tasks/' + id, body, function () {
    return e.updateTask(id, body);
  });
};
ApiClient.prototype.deleteTask = function (id) {
  var e = this.engine;
  return this._call('DELETE', '/tasks/' + id, null, function () {
    e.deleteTask(id); return null;
  });
};
ApiClient.prototype.completeTask = function (id) {
  var e = this.engine;
  return this._call('POST', '/tasks/' + id + '/complete', null, function () {
    return e.completeTask(id);
  });
};
ApiClient.prototype.uncompleteTask = function (id) {
  var e = this.engine;
  return this._call('POST', '/tasks/' + id + '/uncomplete', null, function () {
    return e.uncompleteTask(id);
  });
};
ApiClient.prototype.getToday = function () {
  var e = this.engine;
  return this._call('GET', '/today', null, function () { return e.getToday(); });
};
ApiClient.prototype.getFocus = function () {
  var e = this.engine;
  return this._call('GET', '/focus', null, function () { return e.getFocus(); });
};
ApiClient.prototype.setFocus = function (taskIds) {
  var e = this.engine;
  return this._call('POST', '/focus', { task_ids: taskIds }, function () {
    return e.setFocus(taskIds);
  });
};
ApiClient.prototype.getWeeklyRecap = function () {
  var e = this.engine;
  return this._call('GET', '/recap/weekly', null, function () {
    return e.getWeeklyRecap();
  });
};
// ---- attachments + assistant: real mode only (no-op offline) ----

ApiClient.prototype.getAttachments = async function (taskId) {
  if (this.mock) return [];
  try {
    var res = await fetch(this.baseUrl + '/tasks/' + taskId + '/attachments');
    if (!res.ok) return [];
    return await res.json();
  } catch (e) { return []; }
};

ApiClient.prototype.addAttachmentLink = async function (taskId, url, filename) {
  if (this.mock) return null;
  var res = await fetch(this.baseUrl + '/tasks/' + taskId + '/attachments/link', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: url, filename: filename || null })
  });
  if (!res.ok) throw { status: res.status };
  return await res.json();
};

// XHR for upload progress; returns a promise resolving to the attachment.
ApiClient.prototype.uploadAttachmentFile = function (taskId, file, onProgress) {
  if (this.mock) return Promise.resolve(null);
  var base = this.baseUrl;
  return new Promise(function (resolve, reject) {
    var fd = new FormData();
    fd.append('file', file);
    var xhr = new XMLHttpRequest();
    xhr.open('POST', base + '/tasks/' + taskId + '/attachments/file');
    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = function (ev) {
        if (ev.lengthComputable) onProgress(ev.loaded / ev.total);
      };
    }
    xhr.onload = function () {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText)); } catch (e) { resolve(null); }
      } else {
        reject({ status: xhr.status });
      }
    };
    xhr.onerror = function () { reject({ status: 0 }); };
    xhr.send(fd);
  });
};

ApiClient.prototype.deleteAttachment = async function (id) {
  if (this.mock) return null;
  await fetch(this.baseUrl + '/attachments/' + id, { method: 'DELETE' });
  return null;
};

ApiClient.prototype.downloadUrl = function (id) {
  return this.baseUrl + '/attachments/' + id + '/download';
};

// ---- precedents (decision traces): real mode only ----

ApiClient.prototype.getSkillTraces = async function (slug) {
  if (this.mock) return null;
  var res = await fetch(this.baseUrl + '/skills/' + encodeURIComponent(slug) + '/traces');
  if (!res.ok) throw { status: res.status };
  return await res.json();
};

ApiClient.prototype.setTraceOutcome = async function (id, outcome) {
  if (this.mock) return null;
  var res = await fetch(this.baseUrl + '/traces/' + id, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ outcome: outcome })
  });
  if (!res.ok) throw { status: res.status };
  return await res.json();
};

ApiClient.prototype.getAssistant = async function () {
  if (this.mock) return { has_assistant: false, name: null };
  try {
    var res = await fetch(this.baseUrl + '/assistant');
    if (!res.ok) return { has_assistant: false, name: null };
    return await res.json();
  } catch (e) { return { has_assistant: false, name: null }; }
};

ApiClient.prototype.commandAssistant = async function (text) {
  if (this.mock) return null;
  var res = await fetch(this.baseUrl + '/assistant/command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: text })
  });
  if (!res.ok) throw { status: res.status };
  return await res.json();
};

window.XongStore = { ApiClient: ApiClient, localDate: localDate };
})();
