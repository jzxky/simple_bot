/* Player Hub — Admin JS (tables + users) */

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

// ---- Table viewer ----
(function() {
  var sel = document.getElementById('tb-select');
  if (!sel) return;

  var tbPage = 1;

  api('/api/admin/tables').then(function(d) {
    (d.tables || []).forEach(function(t) {
      var o = document.createElement('option');
      o.value = t.name;
      o.textContent = t.name + ' (' + t.row_count + ')';
      sel.appendChild(o);
    });
  });

  window.loadTable = function() {
    var name = sel.value;
    if (!name) {
      document.getElementById('tb-info').style.display = 'none';
      return;
    }
    tbPage = 1;
    fetchTable(name);
  };

  function fetchTable(name) {
    api('/api/admin/tables/' + encodeURIComponent(name) + '?page=' + tbPage + '&per_page=50').then(function(d) {
      document.getElementById('tb-info').style.display = 'block';
      document.getElementById('tb-title').textContent = d.table;
      document.getElementById('tb-count').textContent = '(' + d.total + ' rows)';

      var thead = document.getElementById('tb-thead');
      thead.innerHTML = '';
      (d.columns || []).forEach(function(c) {
        var th = document.createElement('th');
        th.textContent = c;
        thead.appendChild(th);
      });
      var thAct = document.createElement('th');
      thAct.textContent = 'Actions';
      thead.appendChild(thAct);

      var tbody = document.getElementById('tb-tbody');
      tbody.innerHTML = '';
      (d.rows || []).forEach(function(r) {
        var tr = document.createElement('tr');
        (d.columns || []).forEach(function(c) {
          var td = document.createElement('td');
          var val = r[c];
          td.textContent = val != null ? String(val) : '';
          td.style.maxWidth = '300px';
          td.style.overflow = 'hidden';
          td.style.textOverflow = 'ellipsis';
          tr.appendChild(td);
        });
        var tdAct = document.createElement('td');
        var pkVal = r[d.pk];
        tdAct.innerHTML = '<button class="btn-sm btn-danger" onclick="deleteRow(\'' +
          esc(d.table) + '\',\'' + esc(pkVal) + '\')">Delete</button>';
        tr.appendChild(tdAct);
        tbody.appendChild(tr);
      });

      var pag = document.getElementById('tb-pagination');
      pag.innerHTML = '';
      if (d.pages > 1) {
        var prev = document.createElement('button');
        prev.textContent = 'Prev'; prev.disabled = tbPage <= 1;
        prev.onclick = function() { tbPage--; fetchTable(name); };
        pag.appendChild(prev);
        pag.appendChild(document.createTextNode(' Page ' + d.page + ' of ' + d.pages + ' '));
        var next = document.createElement('button');
        next.textContent = 'Next'; next.disabled = tbPage >= d.pages;
        next.onclick = function() { tbPage++; fetchTable(name); };
        pag.appendChild(next);
      }
    });
  }

  window.deleteRow = function(table, pk) {
    if (!confirm('Delete row ' + pk + ' from ' + table + '?')) return;
    api('/api/admin/tables/' + encodeURIComponent(table) + '/' + encodeURIComponent(pk), {method:'DELETE'}).then(function(d) {
      if (d.ok) { toast('Deleted', true); fetchTable(table); }
      else toast(d.error || 'Error', false);
    });
  };
})();

// ---- User management ----
(function() {
  var tbody = document.getElementById('usr-tbody');
  if (!tbody) return;

  function loadUsers() {
    api('/api/admin/users').then(function(d) {
      tbody.innerHTML = '';
      (d.users || []).forEach(function(u) {
        var tr = document.createElement('tr');
        tr.innerHTML =
          '<td>' + u.id + '</td>' +
          '<td>' + esc(u.username) + '</td>' +
          '<td><span class="role-badge role-' + esc(u.role) + '">' + esc(u.role) + '</span></td>' +
          '<td>' + esc(u.created_at) + '</td>' +
          '<td>' + esc(u.last_login_at) + '</td>' +
          '<td>' +
            '<button class="btn-sm btn-secondary" onclick="editUserRole(' + u.id + ')">Role</button> ' +
            '<button class="btn-sm btn-secondary" onclick="resetUserPw(' + u.id + ')">Password</button> ' +
            '<button class="btn-sm btn-danger" onclick="deleteUser(' + u.id + ',\'' + esc(u.username) + '\')">Delete</button>' +
          '</td>';
        tbody.appendChild(tr);
      });
    });
  }

  window.showCreateUser = function() {
    document.getElementById('user-form').style.display = 'block';
  };
  window.hideCreateUser = function() {
    document.getElementById('user-form').style.display = 'none';
  };

  window.createUser = function(e) {
    e.preventDefault();
    var username = document.getElementById('cu-username').value.trim();
    var password = document.getElementById('cu-password').value;
    var role = document.getElementById('cu-role').value;
    if (!username || !password) return;
    api('/api/admin/users', {method:'POST', body:{username:username, password:password, role:role}}).then(function(d) {
      if (d._status === 201 || d.id) {
        toast('Created', true);
        document.getElementById('cu-username').value = '';
        document.getElementById('cu-password').value = '';
        hideCreateUser();
        loadUsers();
      } else toast(d.error || 'Error', false);
    });
  };

  window.editUserRole = function(id) {
    var role = prompt('New role (admin / user):', '');
    if (!role || (role !== 'admin' && role !== 'user')) return;
    api('/api/admin/users/' + id, {method:'PUT', body:{role:role}}).then(function(d) {
      if (d.ok) { toast('Updated', true); loadUsers(); }
      else toast(d.error || 'Error', false);
    });
  };

  window.resetUserPw = function(id) {
    var pw = prompt('New password:', '');
    if (!pw) return;
    api('/api/admin/users/' + id, {method:'PUT', body:{password:pw}}).then(function(d) {
      if (d.ok) toast('Password reset', true);
      else toast(d.error || 'Error', false);
    });
  };

  window.deleteUser = function(id, name) {
    if (!confirm('Delete user ' + name + '?')) return;
    api('/api/admin/users/' + id, {method:'DELETE'}).then(function(d) {
      if (d.ok) { toast('Deleted', true); loadUsers(); }
      else toast(d.error || 'Error', false);
    });
  };

  loadUsers();
})();
