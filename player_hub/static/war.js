/* Player Hub — War Mode JS */

function api(url, opts) {
  opts = opts || {};
  opts.headers = opts.headers || {};
  if (opts.body && typeof opts.body === 'object') {
    opts.body = JSON.stringify(opts.body);
    opts.headers['Content-Type'] = 'application/json';
  }
  return fetch(url, opts).then(function(r) {
    return r.json().then(function(d) { d._status = r.status; return d; });
  });
}

function toast(msg, ok) {
  var el = document.createElement('div');
  el.className = 'toast ' + (ok ? 'toast-ok' : 'toast-err');
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(function() { el.remove(); }, 3000);
}

function esc(s) {
  if (s == null) return '';
  var d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function renderWarEntry(e) {
  var statusClass = 'status-open';
  if (e.status === 'Protected') statusClass = 'status-protected';
  else if (e.status === 'In-Window') statusClass = 'status-in-window';

  return '<tr>' +
    '<td>' + esc(e.name) + '</td>' +
    '<td>' + e.ws + '</td>' +
    '<td class="' + statusClass + '">' + esc(e.status) + '</td>' +
    '<td>' + esc(e.whack_type) + '</td>' +
    '<td>' + esc(e.last_whack_time) + '</td>' +
    '<td>' + esc(e.window_open) + '</td>' +
    '<td>' + esc(e.window_close) + '</td>' +
    '<td>' + esc(e.last_checked) + '</td>' +
    '<td>' + esc(e.source_client) + '</td>' +
    '<td>' +
      '<button class="btn-sm btn-secondary" onclick="warEdit(\'' + esc(e.name) + '\',\'' + esc(e.side) + '\')">Edit</button> ' +
      '<button class="btn-sm btn-danger" onclick="warRemove(\'' + esc(e.name) + '\',\'' + esc(e.side) + '\')">Remove</button>' +
    '</td>' +
    '</tr>';
}

function loadWar() {
  api('/api/crud/war/state').then(function(d) {
    var opps = document.getElementById('war-opps');
    var friendlies = document.getElementById('war-friendlies');
    opps.innerHTML = '';
    friendlies.innerHTML = '';

    (d.opps || []).forEach(function(e) { opps.innerHTML += renderWarEntry(e); });
    (d.friendlies || []).forEach(function(e) { friendlies.innerHTML += renderWarEntry(e); });

    var evLog = document.getElementById('war-events');
    evLog.innerHTML = '';
    (d.events || []).forEach(function(ev) {
      var div = document.createElement('div');
      div.className = 'event-line';
      div.innerHTML = '<span class="event-ts">' + esc(ev.ts) + '</span>' +
                      (ev.source_client ? '<span class="event-src">[' + esc(ev.source_client) + ']</span>' : '') +
                      esc(ev.message);
      evLog.appendChild(div);
    });
  });
}

window.warAdd = function(e) {
  e.preventDefault();
  var name = document.getElementById('war-name').value.trim();
  var side = document.getElementById('war-side').value;
  if (!name) return;
  api('/api/crud/war/add', {method:'POST', body:{name:name, side:side}}).then(function(d) {
    if (d.ok) { document.getElementById('war-name').value = ''; loadWar(); }
    else toast(d.error || 'Error', false);
  });
};

window.warRemove = function(name, side) {
  if (!confirm('Remove ' + name + ' from ' + side + '?')) return;
  api('/api/crud/war/remove', {method:'POST', body:{name:name, side:side}}).then(function(d) {
    if (d.ok) loadWar();
    else toast(d.error || 'Error', false);
  });
};

window.warEdit = function(name, side) {
  var wt = prompt('Whack type (Normal / Bodyguard):', 'Normal');
  if (wt === null) return;
  var lwt = prompt('Last whack time (YYYY-MM-DD HH:MM:SS or empty):', '');
  if (lwt === null) return;
  var body = {name: name, side: side};
  if (wt) body.whack_type = wt;
  if (lwt !== '') body.last_whack_time = lwt;
  api('/api/crud/war/update', {method:'POST', body:body}).then(function(d) {
    if (d.ok) loadWar();
    else toast(d.error || 'Error', false);
  });
};

window.warClearEvents = function() {
  if (!confirm('Clear all war events?')) return;
  api('/api/crud/war/clear_events', {method:'POST'}).then(function(d) {
    if (d.ok) loadWar();
  });
};

loadWar();
setInterval(loadWar, 5000);
