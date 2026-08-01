/* Xong — UI shell: Today / Lists / Recap views + the check-off interaction.
 * Vanilla JS, no framework, no build step. All strings via XongI18n.
 */
(function () {
'use strict';

var client = new window.XongStore.ApiClient();
var t = function (k, v) { return window.XongI18n.t(k, v); };

var state = {
  view: 'today',
  listId: null,
  lists: [],
  today: null,
  focusRaw: null,
  recap: null,
  listTasks: null,
  listDone: null,
  user: null,
  weave: null,
  skillSlug: null
};

var STARRED_KEY = 'xong.starred-ever';
var WEAVE_KEY_PREFIX = 'xong.weave.passes.';
var SPLASH_MIN_MS = 1400;
var SYNC_INTERVAL_MS = 30000;
var syncTimer = null;
var syncRunning = false;
var splashStarted = performance.now();
var splashDismissed = false;

/* ---------- small helpers ---------- */

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function $(sel, root) { return (root || document).querySelector(sel); }

function fmtDate(d) {
  d = d || new Date();
  return new Intl.DateTimeFormat(window.XongI18n.locale(), {
    weekday: 'long', day: 'numeric', month: 'long'
  }).format(d);
}

function fmtWeekday(d, style) {
  return new Intl.DateTimeFormat(window.XongI18n.locale(), {
    weekday: style || 'long'
  }).format(d);
}

function greeting() {
  var h = new Date().getHours();
  if (h < 11) return t('greetMorning');
  if (h < 18) return t('greetAfternoon');
  return t('greetEvening');
}

function localDay(iso) {
  if (!iso) return null;
  return window.XongStore.localDate(new Date(iso));
}

function todayStr() { return window.XongStore.localDate(); }

function daysBetween(a, b) {
  return Math.round((new Date(a + 'T12:00') - new Date(b + 'T12:00')) / 86400000);
}

function timeOf(iso) {
  var d = new Date(iso);
  return String(d.getHours()).padStart(2, '0') + ':' +
         String(d.getMinutes()).padStart(2, '0');
}

function weaveTier(passes) {
  if (passes >= 500) return 5;
  if (passes >= 100) return 4;
  if (passes >= 25) return 3;
  if (passes >= 5) return 2;
  return 1;
}

function renderIdentity() {
  if (!state.user) return;
  var name = state.user.display_name || state.user.username;
  var weave = state.weave;
  document.querySelectorAll('.side-tools, .topbar-tools').forEach(function (el) {
    var identity = el.querySelector('.identity');
    if (!identity) {
      identity = document.createElement('span');
      identity.className = 'identity';
      identity.innerHTML = '<span class="who"></span>';
      el.insertBefore(identity, el.firstChild);
    }
    var who = identity.querySelector('.who');
    who.textContent = name;
    who.title = state.user.username;
    var mark = identity.querySelector('.weave-mark');
    if (!weave || weave.threads < 1) {
      if (mark) mark.remove();
      return;
    }
    var tooltip = t('weaveTooltip', { threads: weave.threads, passes: weave.passes });
    if (!mark) {
      mark = document.createElement('button');
      mark.type = 'button';
      mark.className = 'weave-mark';
      mark.innerHTML = '<svg width="18" height="18" aria-hidden="true"><use></use></svg>';
      identity.appendChild(mark);
    }
    mark.dataset.tooltip = tooltip;
    mark.setAttribute('aria-label', tooltip);
    mark.querySelector('use').setAttribute('href', '#weave-tier-' + weaveTier(weave.passes));
  });
}

async function refreshWeave() {
  if (!state.user || !client.hasCapability('org')) return;
  var profile = await client.getPerson(state.user.username);
  if (!profile || !profile.weave) return;
  var next = profile.weave;
  var key = WEAVE_KEY_PREFIX + state.user.username;
  var previous = null;
  try {
    var stored = localStorage.getItem(key);
    if (stored !== null) previous = Number(stored);
    localStorage.setItem(key, String(next.passes));
  } catch (e) {}
  state.weave = next;
  renderIdentity();
  if (previous !== null && Number.isFinite(previous) && next.passes > previous) {
    document.querySelectorAll('.weave-mark').forEach(function (mark) {
      mark.classList.remove('weave-pass');
      void mark.offsetWidth;
      mark.classList.add('weave-pass');
      setTimeout(function () { mark.classList.remove('weave-pass'); }, 800);
    });
  }
}

async function syncCycle() {
  if (syncRunning || document.hidden) return;
  syncRunning = true;
  try {
    await client.flushQueue();
    await refreshWeave();
  } finally {
    syncRunning = false;
  }
}

function startSyncCycle() {
  if (client.mock || syncTimer !== null) return;
  syncTimer = setInterval(syncCycle, SYNC_INTERVAL_MS);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) syncCycle();
  });
}

// Calm overdue phrasing — never red, never scolding (SPEC principle 4).
function overdueLabel(dueIso) {
  var n = daysBetween(todayStr(), localDay(dueIso));
  if (n <= 1) return t('sinceYesterday');
  return t('sinceDaysAgo', { n: n });
}

// "9:30, tại bàn làm việc" -> "tại bàn làm việc" (drop the time half).
function wherePart(whenWhere) {
  var parts = String(whenWhere).split(/[,，]/);
  return (parts.length > 1 ? parts.slice(1).join(', ') : parts[0]).trim();
}

var toastTimer = null;
function toast(msg) {
  var el = $('#toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function () { el.classList.remove('show'); }, 2200);
}

function dismissSplash() {
  if (splashDismissed) return;
  splashDismissed = true;
  var splash = $('#splash');
  if (!splash || document.documentElement.classList.contains('splash-seen')) return;
  var remaining = Math.max(0, SPLASH_MIN_MS - (performance.now() - splashStarted));
  setTimeout(function () {
    splash.classList.add('leaving');
    try { localStorage.setItem('xong.splash.seen.v1', '1'); } catch (e) {}
    var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    setTimeout(function () {
      document.documentElement.classList.add('splash-seen');
      splash.remove();
    }, reduced ? 160 : 560);
  }, remaining);
}

/* ---------- task row: title + at most ONE metadata line ---------- */

function metaHtml(task) {
  if (task.next_action) {
    return '<div class="next-action">' + esc(t('firstStep')) + ' ' +
      esc(task.next_action) + '</div>';
  }
  var day = task.due_at ? localDay(task.due_at) : null;
  if (day === todayStr()) {
    var txt = esc(t('chipToday', { time: timeOf(task.due_at) }));
    if (task.when_where) txt += ' · ' + esc(wherePart(task.when_where));
    return '<div class="chips"><span class="chip due">' + txt + '</span></div>';
  }
  if (day && day < todayStr()) {
    return '<div class="chips"><span class="chip calm">' +
      esc(overdueLabel(task.due_at)) + '</span></div>';
  }
  if (task.when_where) {
    return '<div class="chips"><span class="chip plan">' +
      esc(task.when_where) + '</span></div>';
  }
  return '';
}

function taskRow(task, opts) {
  opts = opts || {};
  var row = document.createElement('div');
  row.className = 'task' + (opts.hero ? ' hero' : '');
  row.dataset.id = task.id;

  var starBtn = '';
  if (opts.star) {
    starBtn = '<button class="star' + (opts.starred ? ' on' : '') + '" ' +
      'data-star="' + task.id + '" aria-label="' + esc(t('ariaStar')) + '">' +
      (opts.starred ? '★' : '☆') + '</button>';
  }

  row.innerHTML =
    '<button class="check" data-check="' + task.id + '" aria-label="' + esc(t('ariaCheck')) + '">' +
      '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7"/></svg>' +
    '</button>' +
    '<div class="task-body">' +
      '<div class="task-title" data-edit="' + task.id + '">' + esc(task.title) + '</div>' +
      metaHtml(task) +
    '</div>' + starBtn;
  return row;
}

// THE core interaction: strike + confetti + ding, then the row gracefully
// leaves after ~800ms.
function completeWithJoy(row, taskId) {
  if (row.classList.contains('done')) return;
  row.classList.add('done');
  var check = row.querySelector('.check');
  var r = check.getBoundingClientRect();
  window.XongConfetti.burst(r.left + r.width / 2, r.top + r.height / 2);
  window.XongAudio.ding();
  client.completeTask(taskId);
  setTimeout(function () {
    row.style.maxHeight = row.scrollHeight + 'px';
    row.classList.add('leaving');
  }, 750);
  setTimeout(function () { refresh(); }, 1100);
}

function restoreTask(row, taskId) {
  if (row.classList.contains('busy')) return;
  row.classList.add('busy');
  window.XongAudio.undo();
  client.uncompleteTask(taskId).then(function () {
    row.style.maxHeight = row.scrollHeight + 'px';
    row.classList.add('leaving');
    setTimeout(function () { refresh(); }, 380);
  });
}

/* ---------- task editor (expand on title click) ---------- */

function openEditor(row, task, focusField) {
  if (row.querySelector('.editor')) {
    closeEditor(row);
    return;
  }
  var ed = document.createElement('form');
  ed.className = 'editor';
  var dueVal = task.due_at ? localDay(task.due_at) : '';
  ed.innerHTML =
    (task.looks_vague && !task.next_action
      ? '<div class="ed-nudge">' + esc(t('edNudge')) + '</div>' : '') +
    '<label>' + esc(t('edNext')) +
      '<input name="next_action" type="text" value="' + esc(task.next_action || '') + '" ' +
        'placeholder="' + esc(t('edNextPh')) + '"></label>' +
    '<label>' + esc(t('edWhen')) +
      '<input name="when_where" type="text" value="' + esc(task.when_where || '') + '" ' +
        'placeholder="' + esc(t('edWhenPh')) + '"></label>' +
    '<label>' + esc(t('edDue')) +
      '<input name="due_date" type="date" value="' + dueVal + '"></label>' +
    '<label>' + esc(t('edNotes')) +
      '<textarea name="notes" rows="2">' + esc(task.notes || '') + '</textarea></label>' +
    '<div class="editor-actions">' +
      '<button type="submit" class="btn primary">' + esc(t('edSave')) + '</button>' +
      '<button type="button" class="btn" data-close>' + esc(t('edClose')) + '</button>' +
      '<button type="button" class="btn danger" data-delete>' + esc(t('edDelete')) + '</button>' +
    '</div>';
  row.appendChild(ed);
  if (!client.mock && client.hasCapability('files')) buildAttachments(ed, task.id);
  if (focusField && ed.elements[focusField]) ed.elements[focusField].focus();

  ed.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var dueDate = ed.elements.due_date.value;
    client.updateTask(task.id, {
      next_action: ed.elements.next_action.value.trim() || null,
      when_where: ed.elements.when_where.value.trim() || null,
      notes: ed.elements.notes.value.trim() || null,
      due_at: dueDate ? new Date(dueDate + 'T09:00:00').toISOString() : null
    }).then(function () { refresh(); });
  });
  ed.querySelector('[data-close]').addEventListener('click', function () {
    closeEditor(row);
  });
  ed.querySelector('[data-delete]').addEventListener('click', function () {
    client.deleteTask(task.id).then(function () {
      row.style.maxHeight = row.scrollHeight + 'px';
      row.classList.add('leaving');
      setTimeout(function () { refresh(); }, 380);
    });
  });
}

function fmtSize(n) {
  if (n == null) return '';
  if (n < 1024) return n + ' B';
  if (n < 1024 * 1024) return Math.round(n / 1024) + ' KB';
  return (n / (1024 * 1024)).toFixed(1) + ' MB';
}

function buildAttachments(ed, taskId) {
  var sec = document.createElement('div');
  sec.className = 'attachments';
  sec.innerHTML =
    '<div class="att-head">' + esc(t('attHead')) + '</div>' +
    '<div class="att-list"></div>' +
    '<div class="att-actions">' +
      '<button type="button" class="att-btn" data-att-file>' + esc(t('attAddFile')) + '</button>' +
      '<button type="button" class="att-btn" data-att-link>' + esc(t('attAddLink')) + '</button>' +
      '<input type="file" class="att-input" hidden>' +
    '</div>' +
    '<div class="att-msg" hidden></div>';
  ed.appendChild(sec);
  var listEl = sec.querySelector('.att-list');
  var msgEl = sec.querySelector('.att-msg');
  var fileInput = sec.querySelector('.att-input');

  function showMsg(text) {
    msgEl.textContent = text;
    msgEl.hidden = !text;
  }

  function render(items) {
    listEl.innerHTML = '';
    (items || []).forEach(function (a) {
      var rowEl = document.createElement('div');
      rowEl.className = 'att-row';
      if (a.kind === 'file') {
        rowEl.innerHTML =
          '<a class="att-name" href="' + esc(client.downloadUrl(a.id)) + '">' +
            esc(a.filename || 'file') + '</a>' +
          '<span class="att-size">' + esc(fmtSize(a.size_bytes)) + '</span>';
      } else {
        rowEl.innerHTML =
          '<a class="att-name" href="' + esc(a.url) + '" target="_blank" rel="noopener">' +
            esc(a.filename || a.url) + '</a>';
      }
      var del = document.createElement('button');
      del.type = 'button';
      del.className = 'att-del';
      del.textContent = '✕';
      del.title = t('attDelete');
      del.addEventListener('click', function () {
        client.deleteAttachment(a.id).then(reload);
      });
      rowEl.appendChild(del);
      listEl.appendChild(rowEl);
    });
  }

  function reload() {
    return client.getAttachments(taskId).then(render);
  }

  sec.querySelector('[data-att-file]').addEventListener('click', function () {
    showMsg('');
    fileInput.click();
  });
  fileInput.addEventListener('change', function () {
    var f = fileInput.files && fileInput.files[0];
    if (!f) return;
    showMsg(t('attUploading'));
    client.uploadAttachmentFile(taskId, f, function (p) {
      showMsg(t('attUploading') + ' ' + Math.round(p * 100) + '%');
    }).then(function () {
      showMsg('');
      fileInput.value = '';
      reload();
    }).catch(function (e) {
      var key = e && e.status === 413 ? 'attTooLarge'
        : e && e.status === 415 ? 'attBadType' : 'attFailed';
      showMsg(t(key));
      fileInput.value = '';
    });
  });
  sec.querySelector('[data-att-link]').addEventListener('click', function () {
    var url = window.prompt(t('attLinkPrompt'));
    if (!url) return;
    showMsg('');
    client.addAttachmentLink(taskId, url.trim(), null).then(function () {
      reload();
    }).catch(function () { showMsg(t('attFailed')); });
  });

  reload();
}

function closeEditor(row) {
  var ed = row.querySelector('.editor');
  if (ed) ed.remove();
}

function findTask(id) {
  var pools = [];
  if (state.today) {
    pools = pools.concat(state.today.focus, state.today.due_today,
      state.today.overdue, state.today.default_tasks);
  }
  pools = pools.concat(state.listTasks || [], state.listDone || []);
  for (var i = 0; i < pools.length; i++) if (pools[i] && pools[i].id === id) return pools[i];
  return null;
}

/* ---------- shared delegation for task lists ---------- */

function bindTaskEvents(container) {
  if (container.dataset.taskBound) return; // #view persists across renders
  container.dataset.taskBound = '1';
  container.addEventListener('click', function (ev) {
    var target = ev.target;
    var btn;

    if ((btn = target.closest('[data-check]'))) {
      var row = btn.closest('.task');
      if (row.classList.contains('completed')) {
        restoreTask(row, Number(btn.dataset.check));
      } else {
        completeWithJoy(row, Number(btn.dataset.check));
      }
      return;
    }
    if ((btn = target.closest('[data-star]'))) {
      toggleFocus(Number(btn.dataset.star));
      return;
    }
    if ((btn = target.closest('[data-edit]'))) {
      if (target.closest('.editor')) return;
      var erow = btn.closest('.task');
      var etask = findTask(Number(btn.dataset.edit));
      if (etask && !erow.classList.contains('done')) openEditor(erow, etask);
    }
  });
}

/* ---------- Today view ---------- */

function streakChip(streak) {
  if (streak > 0) {
    return '<span class="streak">' + esc(t('streakDays', { n: streak })) + '</span>';
  }
  return '<span class="streak quiet">' + esc(t('streakQuiet')) + '</span>';
}

function hasStarred() {
  try { return localStorage.getItem(STARRED_KEY) === '1'; } catch (e) { return false; }
}

function renderToday() {
  var v = $('#view');
  var d = state.today;
  var focusIds = d.focus.map(function (task) { return task.id; });

  var html =
    '<header class="view-head">' +
      '<h1 class="display">' + esc(greeting()) + '</h1>' +
      '<div class="date-line">' + esc(fmtDate()) + ' · ' + streakChip(d.streak) + '</div>' +
    '</header>';

  // Today's 3 as ritual — and when every focus task is done, the section
  // folds into one quiet celebratory line.
  var rawFocus = state.focusRaw;
  var allDone = rawFocus && rawFocus.task_ids.length > 0 &&
    rawFocus.tasks.length > 0 &&
    rawFocus.tasks.every(function (task) { return task && task.completed_at; });

  if (allDone) {
    html += '<section class="focus-section">' +
      '<div class="focus-done-line">' + esc(t('allDone', { n: rawFocus.task_ids.length })) +
      '</div></section>';
  } else {
    html += '<section class="focus-section"><h2>' + esc(t('focusTitle')) +
      '</h2><div class="focus-list" id="focus-list"></div>';
    if (d.focus.length < 3 && !hasStarred()) {
      html += '<p class="hint">' + esc(t('focusHint')) + '</p>';
    }
    html += '</section>';
  }

  if (d.overdue.length) {
    html += '<section class="calm-section"><h2 class="quiet-h">' + esc(t('overdueTitle')) +
      '</h2><div id="overdue-list"></div></section>';
  }
  if (d.due_today.length) {
    html += '<section><h2>' + esc(t('dueTodayTitle')) +
      '</h2><div id="due-list"></div></section>';
  }

  html += '<section><h2>' + esc(d.default_list.name) + '</h2>' +
    addBoxHtml(d.default_list.id) +
    '<div id="default-list"></div></section>';

  v.innerHTML = html;

  var focusWrap = $('#focus-list');
  if (focusWrap) {
    if (!d.focus.length) {
      focusWrap.innerHTML = '<div class="empty">' + esc(t('focusEmpty')) + '</div>';
    }
    d.focus.forEach(function (task) {
      focusWrap.appendChild(taskRow(task, { hero: true, star: true, starred: true }));
    });
  }

  fill('#overdue-list', d.overdue, { star: true, starredFn: inFocusFn(focusIds) });
  fill('#due-list', d.due_today, { star: true, starredFn: inFocusFn(focusIds) });
  fill('#default-list', d.default_tasks, { star: true, starredFn: inFocusFn(focusIds) });

  bindTaskEvents(v);
  bindAddBox(v);
}

function inFocusFn(focusIds) {
  return function (task) { return focusIds.indexOf(task.id) !== -1; };
}

function fill(sel, tasks, opts) {
  var wrap = $(sel);
  if (!wrap) return;
  if (!tasks.length) {
    wrap.innerHTML = '<div class="empty">' + esc(t('emptyList')) + '</div>';
    return;
  }
  tasks.forEach(function (task) {
    wrap.appendChild(taskRow(task, {
      star: opts.star,
      starred: opts.starredFn ? opts.starredFn(task) : false
    }));
  });
}

async function toggleFocus(taskId) {
  var focusIds = state.today.focus.map(function (task) { return task.id; });
  var idx = focusIds.indexOf(taskId);
  if (idx !== -1) {
    focusIds.splice(idx, 1);
  } else {
    if (focusIds.length >= 3) {
      toast(t('maxThree'));
      return;
    }
    focusIds.push(taskId);
    try { localStorage.setItem(STARRED_KEY, '1'); } catch (e) {}
  }
  await client.setFocus(focusIds);
  refresh();
}

/* ---------- add box ---------- */

function addBoxHtml(listId) {
  return '<form class="add-box" data-list="' + listId + '">' +
    '<span class="plus">+</span>' +
    '<input type="text" placeholder="' + esc(t('addPlaceholder')) + '" autocomplete="off">' +
    '</form>';
}

function bindAddBox(root) {
  root.querySelectorAll('.add-box').forEach(function (form) {
    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      var input = form.querySelector('input');
      var title = input.value.trim();
      if (!title) return;
      var listId = Number(form.dataset.list);
      input.value = '';
      await client.createTask({ title: title, list_id: listId });
      await refresh();
      // Keep typing flow: focus the add box again.
      var again = document.querySelector('.add-box[data-list="' + listId + '"] input');
      if (again) again.focus();
    });
  });
}

/* ---------- Lists view ---------- */

async function renderLists() {
  if (state.listId == null && state.lists.length) state.listId = state.lists[0].id;
  var list = state.lists.find(function (l) { return l.id === state.listId; });
  var v = $('#view');

  var tabs = state.lists.map(function (l) {
    return '<button class="list-tab' + (l.id === state.listId ? ' on' : '') + '" ' +
      'data-list-tab="' + l.id + '">' + esc(l.name) + '</button>';
  }).join('');

  v.innerHTML =
    '<header class="view-head"><h1>' + esc(t('listsTitle')) + '</h1></header>' +
    '<div class="list-tabs">' + tabs +
      '<form class="new-list"><input type="text" placeholder="' +
        esc(t('newListPlaceholder')) + '"></form>' +
    '</div>' +
    (list
      ? '<section><h2>' + esc(list.name) + '</h2>' + addBoxHtml(list.id) +
        '<div id="list-tasks"></div>' +
        '<div id="list-done-wrap"></div></section>'
      : '<div class="empty">' + esc(t('createListEmpty')) + '</div>');

  v.querySelectorAll('[data-list-tab]').forEach(function (b) {
    b.addEventListener('click', async function () {
      state.listId = Number(b.dataset.listTab);
      await refresh();
    });
  });

  var nl = v.querySelector('.new-list');
  nl.addEventListener('submit', async function (ev) {
    ev.preventDefault();
    var input = nl.querySelector('input');
    var name = input.value.trim();
    if (!name) return;
    var created = await client.createList(name);
    state.listId = created.id;
    await refresh();
  });

  if (!list) return;

  state.listTasks = await client.getTasks(list.id, false);
  state.listDone = (await client.getTasks(list.id, true)).filter(function (task) {
    return task.completed_at && localDay(task.completed_at) === todayStr();
  });

  var wrap = $('#list-tasks');
  if (!state.listTasks.length) {
    wrap.innerHTML = '<div class="empty">' + esc(t('emptyList')) + '</div>';
  }
  state.listTasks.forEach(function (task) { wrap.appendChild(taskRow(task)); });

  var doneWrap = $('#list-done-wrap');
  if (state.listDone.length) {
    doneWrap.innerHTML = '<h3 class="quiet-h">' + esc(t('doneToday', { n: state.listDone.length })) +
      '</h3><div id="list-done"></div>';
    var dw = $('#list-done');
    state.listDone.forEach(function (task) {
      var row = taskRow(task);
      row.classList.add('completed');
      dw.appendChild(row);
    });
  }

  bindTaskEvents(v);
  bindAddBox(v);
}

/* ---------- Recap view ---------- */

async function renderRecap() {
  state.recap = await client.getWeeklyRecap();
  var r = state.recap;
  var v = $('#view');
  var max = Math.max(1, Math.max.apply(null, r.days.map(function (d) { return d.count; })));

  var headline = r.total > 0
    ? t('recapHeadline', { n: r.total })
    : t('recapHeadlineEmpty');

  var best = '';
  if (r.best_day) {
    var bd = new Date(r.best_day + 'T12:00');
    best = '<p class="best-day">' + esc(t('recapBestDay', {
      day: fmtWeekday(bd), n: r.best_day_count
    })) + '</p>';
  }

  var bars = r.days.map(function (d) {
    var dt = new Date(d.date + 'T12:00');
    var h = Math.round((d.count / max) * 100);
    var label = d.date === todayStr() ? t('todayShort') : fmtWeekday(dt, 'short');
    return '<div class="bar-col">' +
      '<div class="bar-num">' + (d.count || '') + '</div>' +
      '<div class="bar" style="height:' + Math.max(h, d.count ? 12 : 3) + '%"></div>' +
      '<div class="bar-label">' + esc(label) + '</div></div>';
  }).join('');

  var wins = r.days.slice().reverse().map(function (d) {
    if (!d.count) return '';
    var dt = new Date(d.date + 'T12:00');
    var name = d.date === todayStr() ? t('todayName') : fmtWeekday(dt);
    return '<div class="win-day"><h3>' + esc(name) + ' · ' +
      esc(t('countItems', { n: d.count })) + '</h3><ul>' +
      d.titles.map(function (title) { return '<li>' + esc(title) + '</li>'; }).join('') +
      '</ul></div>';
  }).join('');

  var teaching = (r.teaching_sessions || []).map(function (session) {
    return '<p>' + esc(t('recapTeaching', {
      agent: session.agent_display,
      agentAgain: session.agent_display,
      skill: session.skill_name,
      weekday: fmtWeekday(new Date(session.first_clean_run_at))
    })) + '</p>';
  }).join('');

  v.innerHTML =
    '<header class="view-head"><h1>' + esc(t('recapTitle')) + '</h1>' +
      '<div class="date-line">' + streakChip(r.streak) + '</div></header>' +
    '<section class="recap-hero"><p class="headline">' + headline + '</p>' + best + '</section>' +
    (teaching ? '<section class="teaching-recap">' + teaching + '</section>' : '') +
    '<section><h2>' + esc(t('recapWeek')) + '</h2><div class="bars">' + bars + '</div></section>' +
    (wins ? '<section><h2>' + esc(t('recapWins')) + '</h2>' + wins + '</section>' : '');
}

/* ---------- Skill precedents view (#skill/<slug>) ---------- */

// A precedent is one line of the owner's judgement — same quiet weight as a
// task row, no badges, no counters.
function traceRow(trace, owner, isOwner) {
  var approver = trace.approver;
  if (owner && approver === owner.username) approver = owner.display_name;

  var meta = [];
  if (approver) meta.push(t('precedentApproved', { name: approver }));
  if (trace.outcome === 'pending') meta.push(t('precedentPending'));
  if (trace.superseded_by) {
    meta.push(t('precedentSuperseded', { id: trace.superseded_by }));
  }

  var control = '';
  if (isOwner && trace.outcome !== 'corrected') {
    control = '<button type="button" class="trace-fix" data-trace="' + trace.id + '">' +
      esc(t('precedentMarkCorrected')) + '</button>';
  }

  return '<div class="trace' + (trace.kind === 'boundary' ? ' boundary' : '') + '">' +
    '<div class="trace-body">' +
      '<div class="trace-situation">' + esc(trace.situation) + '</div>' +
      '<div class="trace-decision">' + esc(trace.decision) + '</div>' +
      (meta.length
        ? '<div class="trace-meta">' + esc(meta.join(' · ')) + '</div>' : '') +
    '</div>' + control + '</div>';
}

async function renderSkill() {
  var v = $('#view');
  if (!client.hasCapability('org')) {
    location.hash = 'today';
    return;
  }
  var data = null;
  try {
    data = await client.getSkillTraces(state.skillSlug);
  } catch (e) { data = null; }
  if (!data) {
    v.innerHTML = '<header class="view-head"><h1>' + esc(t('precedentsTitle')) +
      '</h1></header><div class="empty">' + esc(t('precedentFailed')) + '</div>';
    return;
  }

  var owner = data.owner;
  var isOwner = !!(owner && state.user && owner.username === state.user.username);
  var traces = data.traces || [];
  var boundaries = traces.filter(function (tr) { return tr.kind === 'boundary'; });
  var decisions = traces.filter(function (tr) { return tr.kind !== 'boundary'; });

  var rulesHead = owner
    ? t('precedentsRulesOf', { name: owner.display_name })
    : t('precedentsRules');

  var html =
    '<header class="view-head">' +
      '<button type="button" class="trace-back">' +
        esc(t('precedentBack')) + '</button>' +
      '<h1>' + esc(data.skill.name) + '</h1>' +
      '<div class="date-line">' + esc(t('precedentsTitle')) + '</div>' +
    '</header>';

  if (boundaries.length) {
    html += '<section class="precedents rules"><h2>' + esc(rulesHead) + '</h2>' +
      boundaries.map(function (tr) { return traceRow(tr, owner, isOwner); }).join('') +
      '</section>';
  }
  if (decisions.length) {
    html += '<section class="precedents"><h2 class="quiet-h">' +
      esc(t('precedentsRecent')) + '</h2>' +
      decisions.map(function (tr) { return traceRow(tr, owner, isOwner); }).join('') +
      '</section>';
  }
  if (!traces.length) {
    html += '<div class="empty">' + esc(t('precedentsEmpty')) + '</div>';
  }
  v.innerHTML = html;

  v.querySelector('.trace-back').addEventListener('click', function () {
    location.hash = 'today';
  });
  v.querySelectorAll('[data-trace]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      btn.disabled = true;
      client.setTraceOutcome(Number(btn.dataset.trace), 'corrected')
        .then(function () { renderSkill(); })
        .catch(function () { btn.disabled = false; });
    });
  });
}

/* ---------- shell ---------- */

async function refresh() {
  if (state.view === 'skill') {
    await renderSkill();
    await refreshWeave();
    return;
  }
  state.lists = await client.getLists();
  if (state.view === 'today') {
    state.today = await client.getToday();
    state.focusRaw = await client.getFocus();
    renderToday();
  } else if (state.view === 'lists') {
    await renderLists();
  } else {
    await renderRecap();
  }
  await refreshWeave();
}

function switchView(view) {
  state.view = view;
  document.querySelectorAll('.nav-btn').forEach(function (b) {
    b.classList.toggle('on', b.dataset.view === view);
  });
  return refresh();
}

function updateMuteBtn() {
  var muted = window.XongAudio.isMuted();
  document.querySelectorAll('.mute-btn').forEach(function (b) {
    b.textContent = muted ? '🔇' : '🔊';
    b.setAttribute('aria-label', muted ? t('muteOn') : t('muteOff'));
    b.classList.toggle('muted', muted);
  });
}

var NAV_KEYS = { today: 'navToday', lists: 'navLists', recap: 'navRecap' };

function applyStatic() {
  document.documentElement.lang = window.XongI18n.locale();
  document.title = t('appTitle');
  document.querySelectorAll('.nav-btn').forEach(function (b) {
    b.textContent = t(NAV_KEYS[b.dataset.view]);
  });
  document.querySelectorAll('.lang-switch button').forEach(function (b) {
    b.classList.toggle('on', b.dataset.lang === window.XongI18n.get());
  });
  updateMuteBtn();
}

function currentHash() {
  return (location.hash || '').replace(/^#/, '');
}

// One router: the hash is the truth. #skill/<slug> opens the precedents page.
function applyHash() {
  var hash = currentHash();
  var skill = /^skill\/(.+)$/.exec(hash);
  if (skill) {
    state.skillSlug = decodeURIComponent(skill[1]);
    return switchView('skill');
  }
  return switchView(['today', 'lists', 'recap'].indexOf(hash) !== -1 ? hash : 'today');
}

async function init() {
  var splashFailsafe = setTimeout(dismissSplash, 4500);
  await client.loadCapabilities();
  document.querySelectorAll('.nav-btn').forEach(function (b) {
    b.addEventListener('click', function () {
      if (currentHash() === b.dataset.view) {
        switchView(b.dataset.view);
        return;
      }
      location.hash = b.dataset.view;
    });
  });
  window.addEventListener('hashchange', applyHash);
  document.querySelectorAll('.mute-btn').forEach(function (b) {
    b.addEventListener('click', function () {
      window.XongAudio.setMuted(!window.XongAudio.isMuted());
      updateMuteBtn();
    });
  });
  document.querySelectorAll('.lang-switch button').forEach(function (b) {
    b.addEventListener('click', function () {
      window.XongI18n.set(b.dataset.lang);
      applyStatic();
      refresh();
    });
  });
  applyStatic();
  try {
    await applyHash();
  } finally {
    clearTimeout(splashFailsafe);
    dismissSplash();
  }
  startSyncCycle();
  // Proxy identity: show who this list belongs to (real mode only).
  client.me().then(function (u) {
    if (!u || !u.username) return;
    state.user = u;
    renderIdentity();
    refreshWeave();
    // Ownership decides whether the mark-corrected control exists at all.
    if (state.view === 'skill') renderSkill();
  }).catch(function () {});
  // "Ask <Assistant>" — only rendered if this user actually has an agent.
  if (client.hasCapability('assistant')) {
    client.getAssistant().then(function (info) {
      if (info && info.has_assistant && info.name) {
        var display = info.name.charAt(0).toUpperCase() + info.name.slice(1);
        buildAssistantBar(display);
      }
    }).catch(function () {});
  }
}

function buildAssistantBar(name) {
  if (document.querySelector('.assistant-bar')) return;
  var bar = document.createElement('div');
  bar.className = 'assistant-bar';
  bar.innerHTML =
    '<form class="asst-form">' +
      '<input class="asst-input" type="text" ' +
        'placeholder="' + esc(t('askAssistant', { name: name })) + '">' +
      '<button class="asst-send" type="submit">' + esc(t('askSend')) + '</button>' +
    '</form>' +
    '<div class="asst-reply" hidden></div>';
  document.querySelector('main').appendChild(bar);
  var form = bar.querySelector('.asst-form');
  var input = bar.querySelector('.asst-input');
  var send = bar.querySelector('.asst-send');
  var reply = bar.querySelector('.asst-reply');

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    input.disabled = true;
    send.disabled = true;
    reply.hidden = false;
    reply.className = 'asst-reply working';
    reply.textContent = t('asstWorking', { name: name });
    client.commandAssistant(text).then(function (res) {
      reply.className = 'asst-reply';
      reply.textContent = (res && res.reply) || t('asstDone');
      input.value = '';
      input.disabled = false;
      send.disabled = false;
      refresh();  // the agent may have changed the list
    }).catch(function (e) {
      reply.className = 'asst-reply err';
      var key = e && e.status === 404 ? 'asstNone'
        : e && e.status === 503 ? 'asstUnavailable' : 'asstFailed';
      reply.textContent = t(key, { name: name });
      input.disabled = false;
      send.disabled = false;
    });
  });
}

document.addEventListener('DOMContentLoaded', init);
})();
