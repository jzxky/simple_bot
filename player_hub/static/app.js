/* Player Hub — main JS (players, detail, groups, clients) */

// ---- Helpers ----
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

function toggleDropdown(id) {
  var el = document.getElementById(id);
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

document.addEventListener('click', function(e) {
  document.querySelectorAll('.dropdown-menu').forEach(function(m) {
    if (!m.parentElement.contains(e.target)) m.style.display = 'none';
  });
});

// ---- Players list ----
(function() {
  var plTbody = document.getElementById('pl-tbody');
  if (!plTbody) return;

  var ALL_COLS = [
    {key:'username',label:'Username'},
    {key:'homecity',label:'City'},
    {key:'occupation',label:'Occupation'},
    {key:'rank',label:'Rank'},
    {key:'group_name',label:'Group'},
    {key:'active',label:'Active'},
    {key:'character_age',label:'Char Age'},
    {key:'jail_age',label:'Jail Age'},
    {key:'agg_crimes',label:'Agg Crimes'},
    {key:'case_work',label:'Case Work'},
    {key:'alias',label:'Alias'},
    {key:'sex',label:'Sex'},
    {key:'wealth',label:'Wealth'},
    {key:'respect',label:'Respect'},
    {key:'godfather',label:'Godfather'},
    {key:'crew_name',label:'Crew'},
    {key:'capos',label:'Capos'},
    {key:'scripting',label:'Scripting'},
    {key:'monitoring',label:'Monitoring'},
    {key:'notes',label:'Notes'},
    {key:'born_at',label:'Born'},
    {key:'died_at',label:'Died'},
    {key:'scraped_at',label:'Scraped'},
    {key:'assignments_updated_at',label:'Assignments Updated'},
    {key:'source_client',label:'Source'},
  ];

  var DEFAULT_VISIBLE = ['username','homecity','occupation','rank','group_name','active','character_age','agg_crimes','case_work','alias','source_client'];

  var visible;
  try { visible = JSON.parse(localStorage.getItem('ph_cols')); } catch(e) {}
  if (!visible || !Array.isArray(visible)) visible = DEFAULT_VISIBLE.slice();

  var sortCol = 'username', sortOrder = 'asc', page = 1, perPage = 100;
  var groups = {};

  function saveVisible() {
    try { localStorage.setItem('ph_cols', JSON.stringify(visible)); } catch(e) {}
  }

  function buildColCheckboxes() {
    var wrap = document.getElementById('col-checkboxes');
    if (!wrap) return;
    wrap.innerHTML = '';
    ALL_COLS.forEach(function(c) {
      var lbl = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = visible.indexOf(c.key) !== -1;
      cb.onchange = function() {
        if (cb.checked) { if (visible.indexOf(c.key) === -1) visible.push(c.key); }
        else { visible = visible.filter(function(k){return k!==c.key;}); }
        saveVisible();
        renderTable();
      };
      lbl.appendChild(cb);
      lbl.appendChild(document.createTextNode(' ' + c.label));
      wrap.appendChild(lbl);
    });
  }

  function buildHeader() {
    var thead = document.getElementById('pl-thead');
    thead.innerHTML = '';
    ALL_COLS.forEach(function(c) {
      var th = document.createElement('th');
      th.textContent = c.label;
      th.dataset.col = c.key;
      if (visible.indexOf(c.key) === -1) th.classList.add('col-hidden');
      if (sortCol === c.key) th.classList.add(sortOrder === 'asc' ? 'sorted-asc' : 'sorted-desc');
      th.onclick = function() {
        if (sortCol === c.key) sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
        else { sortCol = c.key; sortOrder = 'asc'; }
        page = 1;
        loadPlayers();
      };
      thead.appendChild(th);
    });
  }

  var playersData = [];

  function renderTable() {
    buildHeader();
    plTbody.innerHTML = '';
    playersData.forEach(function(p) {
      var tr = document.createElement('tr');
      ALL_COLS.forEach(function(c) {
        var td = document.createElement('td');
        if (visible.indexOf(c.key) === -1) td.classList.add('col-hidden');
        var val = p[c.key];
        if (c.key === 'username') {
          td.innerHTML = '<a href="/player/' + encodeURIComponent(val) + '">' + esc(val) + '</a>';
        } else if (c.key === 'group_name' && val) {
          var g = groups[val];
          var bg = g ? g.color : '#3498db';
          td.innerHTML = '<span class="group-badge" style="background:' + esc(bg) + ';color:#111">' + esc(val) + '</span>';
        } else if (c.key === 'active') {
          td.textContent = val ? 'Active' : 'Dead';
          if (!val) td.classList.add('text-danger');
        } else if (c.key === 'monitoring') {
          td.textContent = val ? 'Yes' : 'No';
        } else {
          td.textContent = val != null ? val : '';
        }
        tr.appendChild(td);
      });
      plTbody.appendChild(tr);
    });
  }

  function renderPagination(data) {
    var wrap = document.getElementById('pl-pagination');
    wrap.innerHTML = '';
    if (data.pages <= 1) return;
    var prev = document.createElement('button');
    prev.textContent = 'Prev';
    prev.disabled = page <= 1;
    prev.onclick = function() { page--; loadPlayers(); };
    wrap.appendChild(prev);
    wrap.appendChild(document.createTextNode(' Page ' + data.page + ' of ' + data.pages + ' (' + data.total + ' players) '));
    var next = document.createElement('button');
    next.textContent = 'Next';
    next.disabled = page >= data.pages;
    next.onclick = function() { page++; loadPlayers(); };
    wrap.appendChild(next);
  }

  function getFilters() {
    var q = '?page=' + page + '&per_page=' + perPage + '&sort=' + sortCol + '&order=' + sortOrder;
    var search = document.getElementById('pl-search');
    if (search && search.value.trim()) q += '&search=' + encodeURIComponent(search.value.trim());
    var fc = document.getElementById('f-city');
    if (fc && fc.value) q += '&city=' + encodeURIComponent(fc.value);
    var fo = document.getElementById('f-occupation');
    if (fo && fo.value) q += '&occupation=' + encodeURIComponent(fo.value);
    var fr = document.getElementById('f-rank');
    if (fr && fr.value) q += '&rank=' + encodeURIComponent(fr.value);
    var fg = document.getElementById('f-group');
    if (fg && fg.value) q += '&group=' + encodeURIComponent(fg.value);
    var fa = document.getElementById('f-active');
    if (fa && fa.value !== '') q += '&active=' + fa.value;
    return q;
  }

  function loadPlayers() {
    api('/api/crud/players' + getFilters()).then(function(d) {
      playersData = d.players || [];
      renderTable();
      renderPagination(d);
    });
  }

  function loadFilterOptions() {
    api('/api/crud/filter_options').then(function(d) {
      fillSelect('f-city', d.cities || []);
      fillSelect('f-occupation', d.occupations || []);
      fillSelect('f-rank', d.ranks || []);
      fillSelect('f-group', d.groups || []);
    });
  }

  function fillSelect(id, items) {
    var sel = document.getElementById(id);
    if (!sel) return;
    var val = sel.value;
    while (sel.options.length > 1) sel.remove(1);
    items.forEach(function(it) {
      var o = document.createElement('option');
      o.value = it; o.textContent = it;
      sel.appendChild(o);
    });
    sel.value = val;
  }

  function loadGroups() {
    api('/api/crud/groups').then(function(d) {
      groups = {};
      (d.groups || []).forEach(function(g) { groups[g.name] = g; });
      loadPlayers();
    });
  }

  var searchInput = document.getElementById('pl-search');
  var searchTimer;
  if (searchInput) {
    searchInput.addEventListener('input', function() {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function() { page = 1; loadPlayers(); }, 300);
    });
  }

  document.querySelectorAll('.filter-panel select').forEach(function(sel) {
    sel.addEventListener('change', function() { page = 1; loadPlayers(); });
  });

  buildColCheckboxes();
  loadFilterOptions();
  loadGroups();
})();

// ---- Player detail ----
(function() {
  if (typeof PLAYER_NAME === 'undefined') return;
  var content = document.getElementById('pd-content');

  function loadDetail() {
    api('/api/crud/players/' + encodeURIComponent(PLAYER_NAME)).then(function(p) {
      if (p.error) { content.textContent = p.error; return; }
      renderDetail(p);
    });
  }

  function renderDetail(p) {
    var html = '<div class="detail-grid">';

    html += '<div class="detail-card">';
    html += '<h3>Identity</h3>';
    if (p.pic_url) html += '<img src="' + esc(p.pic_url) + '" class="player-pic" onerror="this.style.display=\'none\'">';
    html += field('Username', p.username);
    html += field('Alias', p.alias, 'alias');
    html += field('Sex', p.sex);
    html += field('City', p.homecity);
    html += field('Active', p.active ? 'Active' : 'Dead');
    html += field('Born', p.born_at);
    html += field('Died', p.died_at);
    html += '</div>';

    html += '<div class="detail-card">';
    html += '<h3>Career</h3>';
    html += field('Rank', p.rank);
    html += field('Occupation', p.occupation);
    html += field('Character Age', p.character_age);
    html += field('Jail Age', p.jail_age);
    html += field('Wealth', p.wealth);
    html += field('Respect', p.respect);
    html += field('Godfather', p.godfather);
    html += field('Crew', p.crew_name);
    html += field('Capos', p.capos);
    html += field('Scripting', p.scripting);
    html += '</div>';

    html += '<div class="detail-card">';
    html += '<h3>Assignments</h3>';
    html += field('Group', p.group_name, 'group_name');
    html += field('Agg Crimes', p.agg_crimes, 'agg_crimes');
    html += field('Case Work', p.case_work, 'case_work');
    html += field('Monitoring', p.monitoring ? 'Yes' : 'No', 'monitoring');
    html += field('Notes', p.notes, 'notes');
    html += '</div>';

    html += '<div class="detail-card">';
    html += '<h3>Sync Info</h3>';
    html += field('Source Client', p.source_client);
    html += field('Scraped At', p.scraped_at);
    html += field('Assignments Updated', p.assignments_updated_at);
    html += field('Respect Checked', p.respect_last_checked ? new Date(p.respect_last_checked * 1000).toISOString().slice(0,19) : '');
    html += '</div>';

    html += '</div>';

    if (p.career_history && p.career_history.length) {
      html += '<div class="card" style="margin-top:14px"><h2>Career History</h2>';
      html += '<div class="table-wrap"><table class="data-table"><thead><tr>';
      html += '<th>Time</th><th>Rank</th><th>Occupation</th><th>City</th><th>Duration</th>';
      html += '</tr></thead><tbody>';
      for (var i = 0; i < p.career_history.length; i++) {
        var ch = p.career_history[i];
        var dur = '';
        if (i > 0) {
          var prev = new Date(p.career_history[i-1].ts);
          var cur = new Date(ch.ts);
          if (!isNaN(prev) && !isNaN(cur)) {
            var diff = prev - cur;
            dur = formatDuration(diff);
          }
        }
        html += '<tr><td>' + esc(ch.ts) + '</td><td>' + esc(ch.rank) + '</td>';
        html += '<td>' + esc(ch.occupation) + '</td><td>' + esc(ch.homecity) + '</td>';
        html += '<td>' + esc(dur) + '</td></tr>';
      }
      html += '</tbody></table></div></div>';
    }

    content.innerHTML = html;

    content.querySelectorAll('.editable').forEach(function(el) {
      el.addEventListener('click', function() {
        var fld = el.dataset.field;
        var curVal = el.textContent;
        if (fld === 'monitoring') {
          saveField(fld, curVal === 'Yes' ? 0 : 1);
          return;
        }
        var input = document.createElement('input');
        input.type = 'text';
        input.value = curVal;
        input.style.width = Math.max(100, el.offsetWidth) + 'px';
        el.textContent = '';
        el.appendChild(input);
        input.focus();
        function save() {
          var nv = input.value;
          if (nv !== curVal) saveField(fld, nv);
          else { el.textContent = curVal; }
        }
        input.addEventListener('blur', save);
        input.addEventListener('keydown', function(e) {
          if (e.key === 'Enter') input.blur();
          if (e.key === 'Escape') { el.textContent = curVal; }
        });
      });
    });
  }

  function field(label, value, editKey) {
    var cls = editKey ? ' editable' : '';
    var data = editKey ? ' data-field="' + editKey + '"' : '';
    return '<div class="field-row"><span class="field-label">' + esc(label) + '</span>' +
           '<span class="field-value' + cls + '"' + data + '>' + esc(value != null ? value : '') + '</span></div>';
  }

  function formatDuration(ms) {
    var s = Math.floor(ms / 1000);
    var d = Math.floor(s / 86400);
    var h = Math.floor((s % 86400) / 3600);
    var m = Math.floor((s % 3600) / 60);
    var parts = [];
    if (d) parts.push(d + 'd');
    if (h) parts.push(h + 'h');
    if (m) parts.push(m + 'm');
    return parts.join(' ') || '< 1m';
  }

  function saveField(fld, val) {
    var body = {};
    body[fld] = val;
    api('/api/crud/players/' + encodeURIComponent(PLAYER_NAME), {method: 'PUT', body: body}).then(function(d) {
      if (d.ok) { toast('Saved', true); loadDetail(); }
      else toast(d.error || 'Error', false);
    });
  }

  window.deletePlayer = function(name) {
    if (!confirm('Delete player ' + name + '? This also removes their career history.')) return;
    api('/api/crud/players/' + encodeURIComponent(name), {method: 'DELETE'}).then(function(d) {
      if (d.ok) { toast('Deleted', true); window.location.href = '/'; }
      else toast(d.error || 'Error', false);
    });
  };

  loadDetail();
})();

// ---- Groups ----
(function() {
  var tbody = document.getElementById('grp-tbody');
  if (!tbody) return;

  function loadGroups() {
    api('/api/crud/groups').then(function(d) {
      tbody.innerHTML = '';
      (d.groups || []).forEach(function(g) {
        var tr = document.createElement('tr');
        tr.innerHTML =
          '<td>' + esc(g.name) + '</td>' +
          '<td>' + esc(g.type) + '</td>' +
          '<td><span class="color-swatch" style="background:' + esc(g.color) + '"></span> ' + esc(g.color) + '</td>' +
          '<td>' + esc(g.agg_crimes) + '</td>' +
          '<td>' + esc(g.case_work) + '</td>' +
          '<td>' + g.member_count + '</td>' +
          '<td>' + groupActions(g) + '</td>';
        tbody.appendChild(tr);
      });
    });
  }

  function groupActions(g) {
    var html = '<button class="btn-sm btn-secondary" onclick="editGroup(\'' + esc(g.name) + '\')">Edit</button> ';
    html += '<button class="btn-sm btn-secondary" onclick="renameGroup(\'' + esc(g.name) + '\')">Rename</button> ';
    if (USER_ROLE === 'admin') {
      html += '<button class="btn-sm btn-danger" onclick="deleteGroup(\'' + esc(g.name) + '\')">Delete</button>';
    }
    return html;
  }

  window.createGroup = function(e) {
    e.preventDefault();
    var name = document.getElementById('grp-name').value.trim();
    var type = document.getElementById('grp-type').value;
    var color = document.getElementById('grp-color').value;
    if (!name) return;
    api('/api/crud/groups', {method:'POST', body:{name:name, type:type, color:color}}).then(function(d) {
      if (d.ok || d._status === 201) { toast('Created', true); document.getElementById('grp-name').value = ''; loadGroups(); }
      else toast(d.error || 'Error', false);
    });
  };

  window.editGroup = function(name) {
    var type = prompt('Type (neutral/friendly/enemy):', '');
    if (type === null) return;
    var color = prompt('Color hex:', '');
    if (color === null) return;
    var body = {};
    if (type) body.type = type;
    if (color) body.color = color;
    if (Object.keys(body).length === 0) return;
    api('/api/crud/groups/' + encodeURIComponent(name), {method:'PUT', body:body}).then(function(d) {
      if (d.ok) { toast('Updated', true); loadGroups(); }
      else toast(d.error || 'Error', false);
    });
  };

  window.renameGroup = function(name) {
    var newName = prompt('New name for ' + name + ':', name);
    if (!newName || newName === name) return;
    api('/api/crud/groups/' + encodeURIComponent(name) + '/rename', {method:'POST', body:{new_name:newName}}).then(function(d) {
      if (d.ok) { toast('Renamed', true); loadGroups(); }
      else toast(d.error || 'Error', false);
    });
  };

  window.deleteGroup = function(name) {
    if (!confirm('Delete group ' + name + '? Members will be unassigned.')) return;
    api('/api/crud/groups/' + encodeURIComponent(name), {method:'DELETE'}).then(function(d) {
      if (d.ok) { toast('Deleted', true); loadGroups(); }
      else toast(d.error || 'Error', false);
    });
  };

  loadGroups();
})();

// ---- Clients ----
(function() {
  var tbody = document.getElementById('cl-tbody');
  if (!tbody) return;

  function loadClients() {
    api('/api/crud/clients').then(function(d) {
      tbody.innerHTML = '';
      (d.clients || []).forEach(function(c) {
        var statusText = 'Active';
        var statusClass = 'text-success';
        if (!c.active) { statusText = 'Revoked'; statusClass = 'text-danger'; }
        var tr = document.createElement('tr');
        tr.innerHTML =
          '<td>' + esc(c.client_id) + '</td>' +
          '<td>' + esc(c.label) + '</td>' +
          '<td class="' + statusClass + '">' + statusText + '</td>' +
          '<td>' + esc(c.last_push_at) + '</td>' +
          '<td>' + esc(c.last_pull_at) + '</td>' +
          '<td>' + (c.player_count || 0) + '</td>' +
          '<td>' + clientActions(c) + '</td>';
        tbody.appendChild(tr);
      });
    });
  }

  function clientActions(c) {
    var html = '<button class="btn-sm btn-secondary" onclick="editClientLabel(\'' + esc(c.client_id) + '\')">Label</button> ';
    if (USER_ROLE === 'admin' && c.active) {
      html += '<button class="btn-sm btn-danger" onclick="revokeClient(\'' + esc(c.client_id) + '\')">Revoke</button>';
    }
    return html;
  }

  window.editClientLabel = function(id) {
    var label = prompt('Label for ' + id + ':', '');
    if (label === null) return;
    api('/api/crud/clients/' + encodeURIComponent(id), {method:'PUT', body:{label:label}}).then(function(d) {
      if (d.ok) { toast('Updated', true); loadClients(); }
      else toast(d.error || 'Error', false);
    });
  };

  window.revokeClient = function(id) {
    if (!confirm('Revoke client ' + id + '?')) return;
    api('/api/admin/clients/' + encodeURIComponent(id), {method:'DELETE'}).then(function(d) {
      if (d.ok) { toast('Revoked', true); loadClients(); }
      else toast(d.error || 'Error', false);
    });
  };

  window.showRegisterClient = function() {
    document.getElementById('register-form').style.display = 'block';
  };
  window.hideRegisterClient = function() {
    document.getElementById('register-form').style.display = 'none';
    document.getElementById('rc-result').style.display = 'none';
  };

  window.registerClient = function(e) {
    e.preventDefault();
    var id = document.getElementById('rc-id').value.trim();
    var label = document.getElementById('rc-label').value.trim();
    if (!id) return;
    api('/api/admin/clients', {method:'POST', body:{client_id:id, label:label}}).then(function(d) {
      if (d.api_key) {
        var res = document.getElementById('rc-result');
        res.style.display = 'block';
        res.innerHTML = '<strong>API Key (shown once):</strong><br>' + esc(d.api_key) +
                        '<br><br><small>Client ID: ' + esc(d.client_id) + '</small>';
        loadClients();
      } else toast(d.error || 'Error', false);
    });
  };

  loadClients();

  // Sync log
  var slTbody = document.getElementById('sl-tbody');
  if (!slTbody) return;
  var slPage = 1;

  function loadSyncLog() {
    api('/api/crud/sync_log?page=' + slPage + '&per_page=20').then(function(d) {
      slTbody.innerHTML = '';
      (d.log || []).forEach(function(r) {
        var tr = document.createElement('tr');
        tr.innerHTML =
          '<td>' + esc(r.ts) + '</td>' +
          '<td>' + esc(r.client_id) + '</td>' +
          '<td>' + esc(r.action) + '</td>' +
          '<td>' + r.player_count + '</td>' +
          '<td>' + r.group_count + '</td>' +
          '<td>' + r.career_count + '</td>';
        slTbody.appendChild(tr);
      });

      var pag = document.getElementById('sl-pagination');
      if (!pag) return;
      var pages = Math.ceil(d.total / 20);
      pag.innerHTML = '';
      if (pages <= 1) return;
      var prev = document.createElement('button');
      prev.textContent = 'Prev'; prev.disabled = slPage <= 1;
      prev.onclick = function() { slPage--; loadSyncLog(); };
      pag.appendChild(prev);
      pag.appendChild(document.createTextNode(' Page ' + slPage + ' of ' + pages + ' '));
      var next = document.createElement('button');
      next.textContent = 'Next'; next.disabled = slPage >= pages;
      next.onclick = function() { slPage++; loadSyncLog(); };
      pag.appendChild(next);
    });
  }

  loadSyncLog();
})();
