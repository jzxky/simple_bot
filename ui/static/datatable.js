/* DataTable — ported from the player-hub repo (static/datatable.js).
 *
 * One table component for every list in the app:
 *  - multi-value filters: a checklist of values (with counts) per column,
 *    OR within a column, AND across columns; active filters show as chips
 *  - tiered sort: click a header to sort by it, Shift+click to add it as the
 *    next tier; the Sort panel adds, reorders, flips and removes tiers
 *  - search, column chooser, drag-to-reorder headers, pagination
 *  - stacked cards instead of a wide table on phones
 *  - sort / filters / columns remembered per table in localStorage
 *
 * Client mode: call table.setRows(rows) and everything happens in the browser.
 * Server mode: pass opts.server = {load(qs) -> Promise<{rows,total,pages}>,
 * facet(qs) -> Promise<{facet:[{value,count}],truncated}>}; qs is a query string
 * in the table_query.py contract (f.<col>, sort=col:dir,..., search, page).
 *
 * Column options: key, label, render(row) -> HTML, value(row) -> raw value,
 * filterLabel(value) -> text, filter (default true), sortable (default true),
 * type ('number' sorts numerically), hidden (hidden by default), cls,
 * title (true: card heading on phones), search (default true).
 */
(function(global) {
  'use strict';

  // player-hub's common.js provides these; this page has no common.js.
  var esc = global.esc || function(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  };
  var isMobile = global.isMobile || function() { return global.matchMedia('(max-width: 640px)').matches; };

  function store(key, val) {
    try {
      if (val === undefined) return JSON.parse(localStorage.getItem(key));
      localStorage.setItem(key, JSON.stringify(val));
    } catch (e) { return null; }
  }

  function isBlank(v) { return v == null || v === ''; }

  function toNum(v) {
    if (typeof v === 'number') return v;
    var n = parseFloat(String(v).replace(/,/g, ''));
    return isNaN(n) ? null : n;
  }

  var collator = (global.Intl && Intl.Collator) ? new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' }) : null;

  function compareValues(a, b, numeric) {
    var ba = isBlank(a), bb = isBlank(b);
    if (ba || bb) return ba === bb ? 0 : (ba ? 1 : -1);  // blanks last (direction-independent; caller skips flipping)
    if (numeric || (typeof a === 'number' && typeof b === 'number')) {
      var na = toNum(a), nb = toNum(b);
      if (na != null && nb != null) return na - nb;
    }
    a = String(a); b = String(b);
    return collator ? collator.compare(a, b) : (a.toLowerCase() < b.toLowerCase() ? -1 : a.toLowerCase() > b.toLowerCase() ? 1 : 0);
  }

  function dirLabel(col, dir) {
    if (col.type === 'number') return dir === 'asc' ? '▲ Low→High' : '▼ High→Low';
    return dir === 'asc' ? '▲ A→Z' : '▼ Z→A';
  }

  var ICON = {
    filter: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h12l-4.5 5.5V13L6.5 14V8.5z"/></svg>',
    sort: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 2v12M1.5 11.5 4 14l2.5-2.5M12 14V2M9.5 4.5 12 2l2.5 2.5"/></svg>',
    cols: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="1.5" y="2.5" width="13" height="11" rx="1"/><path d="M6 2.5v11M10 2.5v11"/></svg>',
    x: '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M2 2l8 8M10 2l-8 8"/></svg>',
    up: '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 7.5 6 4l3.5 3.5"/></svg>',
    down: '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 4.5 6 8l3.5-3.5"/></svg>'
  };

  function DataTable(container, opts) {
    if (typeof container === 'string') container = document.getElementById(container);
    this.el = container;
    this.opts = opts = opts || {};
    this.columns = opts.columns.map(function(c) {
      return Object.assign({ filter: true, sortable: true, search: true }, c);
    });
    this.colMap = {};
    var self = this;
    this.columns.forEach(function(c) { self.colMap[c.key] = c; });
    this.storeKey = opts.id ? 'dt:' + opts.id : null;
    this.perPage = opts.perPage || (opts.server ? 100 : 0);
    this.rows = null;      // client mode: all rows; server mode: current page
    this.total = 0;
    this.pages = 1;
    this.openPanel = null; // 'filters' | 'sort' | 'columns'
    this.openFacet = null; // column key expanded in the filter panel
    this.facetQuery = {};
    this.loadSeq = 0;

    var saved = (this.storeKey && store(this.storeKey)) || {};
    var keys = this.columns.map(function(c) { return c.key; });
    this.state = {
      sort: this._validSort(saved.sort || opts.defaultSort || []),
      filters: this._validFilters(saved.filters || opts.defaultFilters || {}),
      search: '',
      page: 1,
      visible: Array.isArray(saved.visible) ? saved.visible.filter(function(k) { return self.colMap[k]; })
        : this.columns.filter(function(c) { return !c.hidden; }).map(function(c) { return c.key; }),
      order: Array.isArray(saved.order) && saved.order.length === keys.length &&
        saved.order.every(function(k) { return self.colMap[k]; }) ? saved.order : keys
    };
    if (opts.initialVisible && !saved.visible) this.state.visible = opts.initialVisible.filter(function(k) { return self.colMap[k]; });
    if (opts.initialOrder && !saved.order) {
      var io = opts.initialOrder.filter(function(k) { return self.colMap[k]; });
      keys.forEach(function(k) { if (io.indexOf(k) === -1) io.push(k); });
      this.state.order = io;
    }
    // Columns added after the user saved their choice still show up in the chooser,
    // and are shown (unless hidden by default) rather than staying hidden by an old save.
    keys.forEach(function(k, i) {
      if (self.state.order.indexOf(k) !== -1) return;
      // Put it where it sits by default: before the next column that is already placed.
      var at = -1;
      for (var j = i + 1; j < keys.length && at === -1; j++) at = self.state.order.indexOf(keys[j]);
      if (at === -1) self.state.order.push(k); else self.state.order.splice(at, 0, k);
    });
    if (Array.isArray(saved.visible) && Array.isArray(saved.order)) {
      this.columns.forEach(function(c) {
        if (saved.order.indexOf(c.key) === -1 && !c.hidden && self.state.visible.indexOf(c.key) === -1) self.state.visible.push(c.key);
      });
    }

    // A link like /?f.homecity=Detroit&sort=rank:asc wins over the saved state.
    if (opts.urlState) this._readUrl();
    this.selected = {};   // selection key -> row (opts.selectable)
    this.compact = this.columns.some(function(c) { return c.summary; });

    this._build();
    if (opts.server) this.reload();
    else this.render();
  }

  DataTable.prototype._validSort = function(sort) {
    var self = this, seen = {};
    return (sort || []).filter(function(s) {
      if (!s || !self.colMap[s.key] || !self.colMap[s.key].sortable || seen[s.key]) return false;
      seen[s.key] = true; return true;
    }).map(function(s) { return { key: s.key, dir: s.dir === 'desc' ? 'desc' : 'asc' }; });
  };

  DataTable.prototype._validFilters = function(f) {
    var out = {}, self = this;
    Object.keys(f || {}).forEach(function(k) {
      if (self.colMap[k] && self.colMap[k].filter && Array.isArray(f[k]) && f[k].length) out[k] = f[k].map(String);
    });
    return out;
  };

  DataTable.prototype._readUrl = function() {
    var params = new URLSearchParams(window.location.search), self = this;
    var filters = {}, any = false;
    params.forEach(function(v, k) {
      if (k.indexOf('f.') === 0) {
        var col = k.slice(2);
        if (self.colMap[col] && self.colMap[col].filter) { (filters[col] = filters[col] || []).push(v); any = true; }
      }
    });
    if (params.has('sort')) {
      var sort = params.get('sort').split(',').map(function(p) { var x = p.split(':'); return { key: x[0], dir: x[1] }; });
      var vs = this._validSort(sort);
      if (vs.length) { this.state.sort = vs; any = true; }
    }
    if (params.has('search')) { this.state.search = params.get('search').trim(); any = true; }
    if (any) this.state.filters = filters;
  };

  DataTable.prototype._writeUrl = function() {
    if (!this.opts.urlState || !window.history.replaceState) return;
    var qs = this.queryString(false);
    window.history.replaceState(null, '', window.location.pathname + (qs === '?' ? '' : qs) + window.location.hash);
  };

  DataTable.prototype._save = function() {
    this._writeUrl();
    if (!this.storeKey) return;
    store(this.storeKey, { sort: this.state.sort, filters: this.state.filters,
                           visible: this.state.visible, order: this.state.order });
  };

  // ---- DOM scaffold ----
  DataTable.prototype._build = function() {
    var o = this.opts, self = this;
    this.el.classList.add('dt');
    var hasFilters = this.columns.some(function(c) { return c.filter; });
    var hasSort = this.columns.some(function(c) { return c.sortable; });
    var tb = '<div class="dt-toolbar">';
    if (o.search !== false) {
      tb += '<input type="search" class="dt-search" placeholder="' + esc(o.searchPlaceholder || 'Search…') +
            '" aria-label="Search" autocomplete="off" enterkeyhint="search">';
    }
    tb += '<div class="dt-tools">';
    (o.quickFilters || []).forEach(function(k) {
      var c = self.colMap[k];
      if (c) tb += '<button type="button" class="btn-secondary dt-tool dt-quick" data-panel="quick:' + esc(k) + '" aria-expanded="false"><span>' + esc(c.label) + '</span><span class="dt-badge" hidden></span><span class="dt-caret-sm">▾</span></button>';
    });
    if (hasFilters) tb += '<button type="button" class="btn-secondary dt-tool" data-panel="filters" aria-expanded="false">' + ICON.filter + '<span>Filter</span><span class="dt-badge" hidden></span></button>';
    if (hasSort) tb += '<button type="button" class="btn-secondary dt-tool" data-panel="sort" aria-expanded="false">' + ICON.sort + '<span>Sort</span><span class="dt-badge" hidden></span></button>';
    if (o.columnChooser) tb += '<button type="button" class="btn-secondary dt-tool" data-panel="columns" aria-expanded="false">' + ICON.cols + '<span>Columns</span></button>';
    tb += '</div><span class="dt-count"></span></div>';
    this.el.innerHTML = (o.views ? '<div class="dt-views"></div>' : '') + tb +
      '<div class="dt-chips" hidden></div>' +
      (o.selectable ? '<div class="dt-bulk" hidden></div>' : '') +
      '<div class="dt-panel" hidden></div>' +
      '<div class="dt-scroll' + (o.scrollY ? ' dt-scroll-y' : '') + '">' +
        '<table class="data-table dt-table' + (o.cards === false ? '' : ' dt-cards') + (this.compact ? ' dt-compact' : '') + '">' +
        '<thead><tr></tr></thead><tbody></tbody></table></div>' +
      '<div class="pagination dt-pages"></div>';

    this.$search = this.el.querySelector('.dt-search');
    this.$count = this.el.querySelector('.dt-count');
    this.$chips = this.el.querySelector('.dt-chips');
    this.$panel = this.el.querySelector('.dt-panel');
    this.$headRow = this.el.querySelector('thead tr');
    this.$body = this.el.querySelector('tbody');
    this.$pages = this.el.querySelector('.dt-pages');
    this.$views = this.el.querySelector('.dt-views');
    this.$bulk = this.el.querySelector('.dt-bulk');
    if (this.$search && this.state.search) this.$search.value = this.state.search;
    this.$body.innerHTML = '<tr class="dt-msg"><td colspan="99">Loading…</td></tr>';

    if (this.$search) {
      var timer;
      this.$search.addEventListener('input', function() {
        clearTimeout(timer);
        timer = setTimeout(function() {
          self.state.search = self.$search.value.trim();
          self.state.page = 1;
          self._changed(false);
        }, o.server ? 300 : 120);
      });
    }

    this.el.querySelectorAll('.dt-tool').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var p = btn.getAttribute('data-panel');
        self.togglePanel(self.openPanel === p ? null : p);
      });
    });

    // Click-away and Esc close the panel.
    this._docClick = function(e) {
      if (!self.openPanel) return;
      if (self.$panel.contains(e.target) || e.target.closest('.dt-tool') && self.el.contains(e.target)) return;
      if (!document.body.contains(e.target)) return; // element re-rendered away
      self.togglePanel(null);
    };
    document.addEventListener('click', this._docClick);
    this.el.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && self.openPanel) { e.stopPropagation(); self.togglePanel(null); }
    });

    this.$body.addEventListener('click', function(e) {
      var tr = e.target.closest('tr[data-i]');
      if (!tr || !self._pageRows) return;
      var row = self._pageRows[+tr.getAttribute('data-i')];
      var cb = e.target.closest('.dt-sel');
      if (cb) { self._toggleSelect(row, cb.checked); return; }
      if (e.target.closest('a, button, select, input, label, textarea')) return;
      // Phones: a tap opens a compact card to show every field.
      if (self.compact && isMobile() && !o.onRowClick) { tr.classList.toggle('dt-open'); return; }
      if (o.onRowClick) o.onRowClick(row, e);
    });
    this.$headRow.addEventListener('click', function(e) {
      var all = e.target.closest('.dt-sel-all');
      if (!all) return;
      e.stopPropagation();
      (self._pageRows || []).forEach(function(r) { self._toggleSelect(r, all.checked, true); });
      self.render();
    });
  };

  // ---- Selection (opts.selectable = {key, actions:[{label, danger, run(rows)}]}) ----
  DataTable.prototype._selKey = function(row) { return String(row[this.opts.selectable.key]); };

  DataTable.prototype._toggleSelect = function(row, on, quiet) {
    var k = this._selKey(row);
    if (on) this.selected[k] = row; else delete this.selected[k];
    if (!quiet) { this._renderBulk(); this._syncSelAll(); }
  };

  DataTable.prototype.clearSelection = function() {
    this.selected = {};
    this.render();
  };

  DataTable.prototype._syncSelAll = function() {
    var all = this.$headRow.querySelector('.dt-sel-all'), self = this;
    if (!all) return;
    var rows = this._pageRows || [];
    var n = rows.filter(function(r) { return self.selected[self._selKey(r)]; }).length;
    all.checked = rows.length > 0 && n === rows.length;
    all.indeterminate = n > 0 && n < rows.length;
  };

  DataTable.prototype._renderBulk = function() {
    if (!this.$bulk) return;
    var self = this, keys = Object.keys(this.selected);
    if (!keys.length) { this.$bulk.hidden = true; this.$bulk.innerHTML = ''; return; }
    var h = '<span class="dt-bulk-n">' + keys.length + ' selected</span><span class="dt-bulk-actions">';
    this.opts.selectable.actions.forEach(function(a, i) {
      h += '<button type="button" class="btn-sm ' + (a.danger ? 'btn-danger' : 'btn-primary') + '" data-a="' + i + '">' + esc(a.label) + '</button>';
    });
    h += '</span><button type="button" class="dt-link dt-bulk-clear">Clear</button>';
    this.$bulk.innerHTML = h;
    this.$bulk.hidden = false;
    this.$bulk.querySelectorAll('[data-a]').forEach(function(b) {
      b.onclick = function() {
        var rows = Object.keys(self.selected).map(function(k) { return self.selected[k]; });
        self.opts.selectable.actions[+b.getAttribute('data-a')].run(rows);
      };
    });
    this.$bulk.querySelector('.dt-bulk-clear').onclick = function() { self.clearSelection(); };
  };

  // ---- Saved views (opts.views): named sort + filter + search sets, per browser ----
  DataTable.prototype._viewsKey = function() { return 'dt-views:' + (this.opts.id || ''); };
  DataTable.prototype._getViews = function() { return store(this._viewsKey()) || []; };
  DataTable.prototype._viewSig = function(v) {
    var f = {};
    Object.keys(v.filters || {}).sort().forEach(function(k) { f[k] = (v.filters[k] || []).slice().sort(); });
    return JSON.stringify([v.sort || [], f, v.search || '']);
  };

  DataTable.prototype._renderViews = function() {
    if (!this.$views) return;
    var self = this, views = this._getViews(), cur = this._viewSig(this.state);
    var def = { name: this.opts.defaultViewName || 'Default', sort: this.opts.defaultSort || [], filters: this.opts.defaultFilters || {}, search: '' };
    var h = '<span class="dt-views-label">Views</span>';
    [def].concat(views).forEach(function(v, i) {
      var on = self._viewSig(v) === cur;
      h += '<span class="dt-view' + (on ? ' active' : '') + '"><button type="button" class="dt-view-btn" data-v="' + i + '">' + esc(v.name) + '</button>' +
        (i ? '<button type="button" class="dt-view-x" data-x="' + (i - 1) + '" aria-label="Delete view ' + esc(v.name) + '">' + ICON.x + '</button>' : '') + '</span>';
    });
    h += '<button type="button" class="dt-link dt-view-save">+ Save this view</button>';
    this.$views.innerHTML = h;
    this.$views.querySelectorAll('.dt-view-btn').forEach(function(b) {
      b.onclick = function() {
        var i = +b.getAttribute('data-v'), v = i ? views[i - 1] : def;
        self.state.sort = self._validSort(v.sort);
        self.state.filters = self._validFilters(v.filters);
        self.state.search = v.search || '';
        if (self.$search) self.$search.value = self.state.search;
        self.state.page = 1;
        self._changed(true);
      };
    });
    this.$views.querySelectorAll('.dt-view-x').forEach(function(b) {
      b.onclick = function() {
        var i = +b.getAttribute('data-x');
        if (!confirm('Delete the view "' + views[i].name + '"?')) return;
        views.splice(i, 1);
        store(self._viewsKey(), views);
        self._renderViews();
      };
    });
    this.$views.querySelector('.dt-view-save').onclick = function() {
      var ov = showOverlay('Save view', '<div class="form-group"><label>Name</label><input type="text" id="dt-view-name" maxlength="40" placeholder="e.g. Enemy bolds"></div>' +
        '<p class="muted">Saves the current filters, sort and search. Views are kept in this browser.</p>', {
        confirmLabel: 'Save',
        onConfirm: function(panel, close) {
          var name = panel.querySelector('#dt-view-name').value.trim();
          if (!name) { toast('Give the view a name', false); return; }
          var list = self._getViews().filter(function(v) { return v.name !== name; });
          list.push({ name: name, sort: self.state.sort, filters: self.state.filters, search: self.state.search });
          store(self._viewsKey(), list);
          close();
          self._renderViews();
        }
      });
    };
  };

  // ---- Public API ----
  DataTable.prototype.setRows = function(rows) {
    this.rows = rows || [];
    this.render();
    if (this._isFilterPanel() && this.openFacet) this._refreshFacetCounts();
  };

  DataTable.prototype.reload = function() {
    if (!this.opts.server) { this.render(); return; }
    var self = this, seq = ++this.loadSeq;
    this.el.classList.add('dt-loading');
    return this.opts.server.load(this.queryString(true)).then(function(d) {
      if (seq !== self.loadSeq) return;
      self.el.classList.remove('dt-loading');
      self.rows = d.rows || [];
      self.total = d.total || 0;
      self.pages = d.pages || 1;
      if (self.state.page > self.pages && self.pages > 0) { self.state.page = self.pages; return self.reload(); }
      self.render();
    });
  };

  DataTable.prototype.getState = function() { return JSON.parse(JSON.stringify(this.state)); };

  DataTable.prototype.setFilter = function(key, values) {
    if (values && values.length) this.state.filters[key] = values.map(String);
    else delete this.state.filters[key];
    this.state.page = 1;
    this._changed(true);
  };

  DataTable.prototype.clearFilters = function() {
    this.state.filters = {};
    this.state.search = '';
    if (this.$search) this.$search.value = '';
    this.state.page = 1;
    this._changed(true);
  };

  DataTable.prototype.queryString = function(withPage) {
    var s = this.state, parts = [];
    if (withPage) {
      parts.push('page=' + s.page);
      parts.push('per_page=' + this.perPage);
    }
    if (s.sort.length) parts.push('sort=' + encodeURIComponent(s.sort.map(function(t) { return t.key + ':' + t.dir; }).join(',')));
    Object.keys(s.filters).forEach(function(k) {
      s.filters[k].forEach(function(v) { parts.push('f.' + encodeURIComponent(k) + '=' + encodeURIComponent(v)); });
    });
    if (s.search) parts.push('search=' + encodeURIComponent(s.search));
    return '?' + parts.join('&');
  };

  DataTable.prototype._changed = function(rerenderPanel) {
    this._save();
    if (this.opts.server) this.reload(); else this.render();
    if (rerenderPanel && this.openPanel) this._renderPanel();
    else if (this._isFilterPanel()) this._refreshFacetCounts();
    if (this.opts.onStateChange) this.opts.onStateChange(this.getState());
  };

  // ---- Sorting ----
  DataTable.prototype.sortBy = function(key, additive) {
    var sort = this.state.sort, idx = -1;
    for (var i = 0; i < sort.length; i++) if (sort[i].key === key) idx = i;
    var first = this.colMap[key].type === 'number' || this.colMap[key].firstDir === 'desc' ? 'desc' : 'asc';
    if (additive) {
      if (idx === -1) sort.push({ key: key, dir: first });
      else sort[idx].dir = sort[idx].dir === 'asc' ? 'desc' : 'asc';
    } else if (idx === 0 && sort.length === 1) {
      sort[0].dir = sort[0].dir === 'asc' ? 'desc' : 'asc';
    } else {
      this.state.sort = [{ key: key, dir: idx === -1 ? first : sort[idx].dir }];
    }
    this.state.page = 1;
    this._changed(this.openPanel === 'sort');
  };

  DataTable.prototype._value = function(col, row) {
    return col.value ? col.value(row) : row[col.key];
  };

  DataTable.prototype._filterKey = function(col, row) {
    var v = this._value(col, row);
    return v == null ? '' : String(v);
  };

  DataTable.prototype._matches = function(row, skipKey) {
    var f = this.state.filters, self = this;
    for (var k in f) {
      if (k === skipKey || !f.hasOwnProperty(k)) continue;
      if (f[k].indexOf(self._filterKey(self.colMap[k], row)) === -1) return false;
    }
    var q = this.state.search.toLowerCase();
    if (q) {
      var hit = this.columns.some(function(c) {
        if (!c.search) return false;
        var v = self._value(c, row);
        if (v == null) return false;
        if (String(v).toLowerCase().indexOf(q) !== -1) return true;
        return c.filterLabel ? String(c.filterLabel(String(v))).toLowerCase().indexOf(q) !== -1 : false;
      });
      if (!hit) return false;
    }
    return true;
  };

  DataTable.prototype._clientRows = function() {
    var self = this, rows = (this.rows || []).filter(function(r) { return self._matches(r); });
    var tiers = this.state.sort;
    if (tiers.length) {
      rows = rows.map(function(r, i) { return { r: r, i: i }; });
      rows.sort(function(a, b) {
        for (var t = 0; t < tiers.length; t++) {
          var col = self.colMap[tiers[t].key];
          var va = col.sortValue ? col.sortValue(a.r) : self._value(col, a.r);
          var vb = col.sortValue ? col.sortValue(b.r) : self._value(col, b.r);
          var c;
          if (isBlank(va) || isBlank(vb)) c = compareValues(va, vb);
          else { c = compareValues(va, vb, col.type === 'number'); if (tiers[t].dir === 'desc') c = -c; }
          if (c) return c;
        }
        return a.i - b.i;
      }).forEach(function(x, i) { rows[i] = x.r; });
    }
    return rows;
  };

  // ---- Render ----
  DataTable.prototype._orderedCols = function() {
    var self = this;
    return this.state.order.map(function(k) { return self.colMap[k]; })
      .filter(function(c) { return c && self.state.visible.indexOf(c.key) !== -1; });
  };

  DataTable.prototype.render = function() {
    if (this.rows === null) return;
    var self = this, o = this.opts, s = this.state;
    var cols = this._orderedCols();
    var rows, total, pages;

    if (o.server) {
      rows = this.rows; total = this.total; pages = this.pages;
    } else {
      var all = this._clientRows();
      total = all.length;
      if (this.perPage) {
        pages = Math.max(1, Math.ceil(total / this.perPage));
        if (s.page > pages) s.page = pages;
        rows = all.slice((s.page - 1) * this.perPage, s.page * this.perPage);
      } else { pages = 1; rows = all; }
    }
    this._pageRows = rows;

    // Header
    var multi = s.sort.length > 1;
    var hh = '';
    cols.forEach(function(c) {
      var tier = -1;
      for (var i = 0; i < s.sort.length; i++) if (s.sort[i].key === c.key) tier = i;
      var cls = [c.cls || ''];
      if (c.sortable) cls.push('dt-sortable');
      if (tier !== -1) cls.push('dt-sorted');
      var aria = tier === 0 ? ' aria-sort="' + (s.sort[0].dir === 'asc' ? 'ascending' : 'descending') + '"' : '';
      hh += '<th data-key="' + esc(c.key) + '" class="' + cls.join(' ') + '"' + aria +
        (c.sortable ? ' tabindex="0" title="Click to sort · Shift+click to add as another sort level"' : '') +
        (o.reorder ? ' draggable="true"' : '') + '>' +
        '<span class="dt-th">' + esc(c.label) +
        (tier !== -1 ? '<span class="dt-arrow">' + (s.sort[tier].dir === 'asc' ? '▲' : '▼') +
          (multi ? '<sup>' + (tier + 1) + '</sup>' : '') + '</span>' : '') +
        (s.filters[c.key] ? '<span class="dt-th-filter" title="Filtered">' + ICON.filter + '</span>' : '') +
        '</span></th>';
    });
    if (o.selectable) hh = '<th class="dt-selcell"><input type="checkbox" class="dt-sel-all" aria-label="Select all on this page"></th>' + hh;
    this.$headRow.innerHTML = hh;
    this._bindHeader();

    // Body
    if (!rows.length) {
      var filtered = Object.keys(s.filters).length || s.search;
      this.$body.innerHTML = '<tr class="dt-msg"><td colspan="' + Math.max(cols.length, 1) + '">' +
        (filtered ? 'Nothing matches these filters. <button type="button" class="btn-sm btn-secondary dt-clear">Clear filters</button>'
                  : esc(o.emptyText || 'Nothing here yet.')) + '</td></tr>';
      var clr = this.$body.querySelector('.dt-clear');
      if (clr) clr.onclick = function() { self.clearFilters(); };
    } else {
      var html = '', lastGroup = null, span = cols.length + (o.selectable ? 1 : 0);
      rows.forEach(function(r, i) {
        if (o.groupBy) {
          var g = o.groupBy(r);
          if (g !== lastGroup) { html += '<tr class="dt-group"><td colspan="' + span + '">' + esc(g) + '</td></tr>'; lastGroup = g; }
        }
        var rc = o.rowClass ? o.rowClass(r) : '';
        var sel = o.selectable && self.selected[self._selKey(r)];
        html += '<tr data-i="' + i + '"' + ((rc || sel) ? ' class="' + esc((rc || '') + (sel ? ' dt-selected' : '')) + '"' : '') + (o.onRowClick ? ' style="cursor:pointer"' : '') + '>';
        if (o.selectable) html += '<td class="dt-selcell"><input type="checkbox" class="dt-sel" aria-label="Select"' + (sel ? ' checked' : '') + '></td>';
        cols.forEach(function(c) {
          var v = self._value(c, r);
          var content = c.render ? c.render(r) : esc(c.filterLabel && !isBlank(v) ? c.filterLabel(String(v)) : v);
          var tdc = (c.cls || '') + (c.title ? ' dt-card-title' : '') + (c.key === '_actions' ? ' dt-actions' : '') +
            (c.summary === 'head' ? ' dt-head' : c.summary ? ' dt-sum' : '') +
            (content === '' || content == null ? ' dt-empty' : '');
          html += '<td data-label="' + esc(c.label) + '"' + (tdc.trim() ? ' class="' + tdc.trim() + '"' : '') + '>' +
            (content == null ? '' : content) + '</td>';
        });
        html += '</tr>';
      });
      this.$body.innerHTML = html;
    }

    // Count
    var noun = o.noun || 'rows';
    var unfiltered = o.server ? null : (this.rows || []).length;
    this.$count.textContent = (unfiltered != null && unfiltered !== total)
      ? total.toLocaleString() + ' of ' + unfiltered.toLocaleString() + ' ' + noun
      : total.toLocaleString() + ' ' + (total === 1 && o.nounOne ? o.nounOne : noun);

    this._renderPagination(pages, total);
    this._updatePanelFoot();
    this._renderChips();
    this._renderBadges();
    this._renderBulk();
    this._syncSelAll();
    this._renderViews();
    if (o.afterRender) o.afterRender(rows);
  };

  DataTable.prototype._bindHeader = function() {
    var self = this;
    this.$headRow.querySelectorAll('th').forEach(function(th) {
      var key = th.getAttribute('data-key');
      var col = self.colMap[key];
      if (!col) return;
      if (col.sortable) {
        th.addEventListener('click', function(e) { self.sortBy(key, e.shiftKey || e.ctrlKey || e.metaKey); });
        th.addEventListener('keydown', function(e) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); self.sortBy(key, e.shiftKey); }
        });
      }
      if (self.opts.reorder) {
        th.addEventListener('dragstart', function(e) { self._drag = key; e.dataTransfer.effectAllowed = 'move'; try { e.dataTransfer.setData('text/plain', key); } catch (x) {} });
        th.addEventListener('dragover', function(e) { if (!self._drag) return; e.preventDefault(); th.classList.add('drag-over'); });
        th.addEventListener('dragleave', function() { th.classList.remove('drag-over'); });
        th.addEventListener('drop', function(e) {
          e.preventDefault();
          th.classList.remove('drag-over');
          var from = self._drag; self._drag = null;
          if (!from || from === key) return;
          var order = self.state.order;
          order.splice(order.indexOf(from), 1);
          order.splice(order.indexOf(key), 0, from);
          self._save();
          self.render();
        });
        th.addEventListener('dragend', function() { self._drag = null; });
      }
    });
  };

  DataTable.prototype._renderPagination = function(pages, total) {
    var self = this, p = this.state.page, w = this.$pages;
    w.innerHTML = '';
    if (pages <= 1) return;
    function btn(label, page, disabled, aria) {
      var b = document.createElement('button');
      b.type = 'button';
      b.innerHTML = label;
      if (aria) b.setAttribute('aria-label', aria);
      b.disabled = disabled;
      b.onclick = function() {
        self.state.page = page;
        if (self.opts.server) self.reload(); else self.render();
        var top = self.el.getBoundingClientRect().top;
        if (top < 0) window.scrollBy(0, top - 60);
      };
      w.appendChild(b);
    }
    btn('«', 1, p <= 1, 'First page');
    btn('‹ Prev', p - 1, p <= 1);
    var span = document.createElement('span');
    span.className = 'dt-page-info';
    span.textContent = 'Page ' + p + ' of ' + pages;
    w.appendChild(span);
    btn('Next ›', p + 1, p >= pages);
    btn('»', pages, p >= pages, 'Last page');
  };

  DataTable.prototype._valueLabel = function(col, v) {
    if (v === '') return '(blank)';
    return col.filterLabel ? col.filterLabel(v) : v;
  };

  DataTable.prototype._renderChips = function() {
    var self = this, f = this.state.filters, keys = Object.keys(f);
    if (!keys.length) { this.$chips.hidden = true; this.$chips.innerHTML = ''; return; }
    var h = '';
    keys.forEach(function(k) {
      var col = self.colMap[k];
      var vals = f[k].map(function(v) { return self._valueLabel(col, v); });
      var shown = vals.length > 2 ? vals.slice(0, 2).join(', ') + ' +' + (vals.length - 2) : vals.join(', ');
      h += '<span class="dt-chip"><button type="button" class="dt-chip-body" data-k="' + esc(k) + '" title="' + esc(vals.join(', ')) + '">' +
        '<b>' + esc(col.label) + ':</b> ' + esc(shown) + '</button>' +
        '<button type="button" class="dt-chip-x" data-k="' + esc(k) + '" aria-label="Remove ' + esc(col.label) + ' filter">' + ICON.x + '</button></span>';
    });
    if (keys.length > 1) h += '<button type="button" class="dt-link dt-chips-clear">Clear all</button>';
    this.$chips.innerHTML = h;
    this.$chips.hidden = false;
    this.$chips.querySelectorAll('.dt-chip-x').forEach(function(b) {
      b.onclick = function(e) { e.stopPropagation(); self.setFilter(b.getAttribute('data-k'), null); };
    });
    this.$chips.querySelectorAll('.dt-chip-body').forEach(function(b) {
      b.onclick = function(e) { e.stopPropagation(); self.openFacet = b.getAttribute('data-k'); self.togglePanel('filters'); };
    });
    var ca = this.$chips.querySelector('.dt-chips-clear');
    if (ca) ca.onclick = function() { self.state.filters = {}; self.state.page = 1; self._changed(true); };
  };

  DataTable.prototype._renderBadges = function() {
    var fb = this.el.querySelector('[data-panel="filters"] .dt-badge');
    var sb = this.el.querySelector('[data-panel="sort"] .dt-badge');
    var nf = Object.keys(this.state.filters).length, ns = this.state.sort.length;
    if (fb) { fb.hidden = !nf; fb.textContent = nf; }
    var self = this;
    this.el.querySelectorAll('.dt-quick').forEach(function(b) {
      var k = b.getAttribute('data-panel').slice(6), n = (self.state.filters[k] || []).length;
      var badge = b.querySelector('.dt-badge');
      badge.hidden = !n; badge.textContent = n;
      b.classList.toggle('dt-quick-on', !!n);
    });
    if (sb) { sb.hidden = ns < 2; sb.textContent = ns; }
  };

  // ---- Panels ----
  DataTable.prototype.togglePanel = function(name) {
    this.openPanel = name;
    var self = this;
    this.el.querySelectorAll('.dt-tool').forEach(function(b) {
      var on = b.getAttribute('data-panel') === name;
      b.classList.toggle('active', on);
      b.setAttribute('aria-expanded', on ? 'true' : 'false');
    });
    if (!name) {
      this.$panel.hidden = true;
      this.$panel.innerHTML = '';
      this.el.classList.remove('dt-panel-open');
      document.body.classList.remove('dt-sheet-open');
      return;
    }
    this.el.classList.add('dt-panel-open');
    if (isMobile()) document.body.classList.add('dt-sheet-open');
    this.$panel.hidden = false;
    this._renderPanel();
    setTimeout(function() {
      var first = self.$panel.querySelector('.dt-facet-search, select, button');
      if (first && !isMobile() && name === 'filters' && self.openFacet) {
        var fs = self.$panel.querySelector('.dt-facet-search'); if (fs) fs.focus();
      }
    }, 0);
  };

  DataTable.prototype._isFilterPanel = function() {
    return this.openPanel === 'filters' || (this.openPanel || '').indexOf('quick:') === 0;
  };

  DataTable.prototype._panelHead = function(title, extra) {
    return '<div class="dt-panel-head"><span class="dt-panel-title">' + esc(title) + '</span>' + (extra || '') +
      '<button type="button" class="dt-panel-x" aria-label="Close">' + ICON.x + '</button></div>';
  };

  DataTable.prototype._renderPanel = function() {
    var p = this.openPanel, self = this;
    if (p && p.indexOf('quick:') === 0) { this.openFacet = p.slice(6); this._renderFilterPanel(p.slice(6)); }
    else if (p === 'filters') this._renderFilterPanel();
    else if (p === 'sort') this._renderSortPanel();
    else if (p === 'columns') this._renderColumnsPanel();
    var x = this.$panel.querySelector('.dt-panel-x');
    if (x) x.onclick = function() { self.togglePanel(null); };
    this._addPanelFoot();
  };

  // Phones: a sticky "Show N rows" button closes the bottom sheet.
  DataTable.prototype._addPanelFoot = function() {
    var self = this;
    if (this.$panel.querySelector('.dt-panel-foot')) return;
    var foot = document.createElement('div');
    foot.className = 'dt-panel-foot';
    foot.innerHTML = '<button type="button" class="btn-primary dt-done"></button>';
    this.$panel.appendChild(foot);
    foot.querySelector('button').onclick = function() { self.togglePanel(null); };
    this._updatePanelFoot();
  };

  DataTable.prototype._updatePanelFoot = function() {
    var b = this.$panel.querySelector('.dt-done');
    if (b) b.textContent = 'Show ' + this.$count.textContent;
  };

  DataTable.prototype._renderFilterPanel = function(only) {
    var self = this, f = this.state.filters;
    var cols = this.columns.filter(function(c) { return c.filter && (!only || c.key === only); });
    var h = this._panelHead(only ? this.colMap[only].label : 'Filter', Object.keys(f).length && !only ? '<button type="button" class="dt-link dt-fclear">Clear all</button>' : '');
    if (!only) h += '<p class="dt-hint">Tick any number of values. Rows must match one of the ticked values in every filtered column.</p>';
    h += '<div class="dt-facets">';
    cols.forEach(function(c) {
      var n = f[c.key] ? f[c.key].length : 0;
      var open = self.openFacet === c.key;
      h += '<div class="dt-facet' + (open ? ' open' : '') + '" data-k="' + esc(c.key) + '">' +
        '<button type="button" class="dt-facet-head" aria-expanded="' + open + '">' +
        '<span>' + esc(c.label) + '</span>' +
        (n ? '<span class="dt-facet-n">' + n + ' selected</span>' : '<span class="dt-facet-any">Any</span>') +
        '<span class="dt-caret">' + ICON.down + '</span></button>';
      if (open) h += '<div class="dt-facet-body"><div class="muted dt-facet-loading">Loading…</div></div>';
      h += '</div>';
    });
    h += '</div>';
    this.$panel.innerHTML = h;
    var fc = this.$panel.querySelector('.dt-fclear');
    if (fc) fc.onclick = function() { self.state.filters = {}; self.state.page = 1; self._changed(true); };
    this.$panel.querySelectorAll('.dt-facet-head').forEach(function(b) {
      b.onclick = function() {
        var k = b.parentElement.getAttribute('data-k');
        self.openFacet = self.openFacet === k ? null : k;
        self._renderPanel();
      };
    });
    if (this.openFacet && this.colMap[this.openFacet]) this._loadFacet(this.openFacet);
  };

  // Values of one column with counts, under every other active filter.
  DataTable.prototype._facetValues = function(key) {
    var self = this, col = this.colMap[key], q = (this.facetQuery[key] || '').toLowerCase();
    if (this.opts.server) {
      var qs = this.queryString(false) + '&facet=' + encodeURIComponent(key) + (q ? '&facet_q=' + encodeURIComponent(q) : '');
      return this.opts.server.facet(qs).then(function(d) { return { values: d.facet || [], truncated: d.truncated }; });
    }
    var counts = {};
    (this.rows || []).forEach(function(r) {
      if (!self._matches(r, key)) return;
      var v = self._filterKey(col, r);
      counts[v] = (counts[v] || 0) + 1;
    });
    var values = Object.keys(counts).map(function(v) { return { value: v, count: counts[v] }; });
    if (q) values = values.filter(function(x) { return String(self._valueLabel(col, x.value)).toLowerCase().indexOf(q) !== -1; });
    values.sort(function(a, b) { return compareValues(a.value, b.value, col.type === 'number'); });
    return Promise.resolve({ values: values, truncated: false });
  };

  DataTable.prototype._loadFacet = function(key) {
    var self = this, seq = (this._facetSeq = (this._facetSeq || 0) + 1);
    this._facetValues(key).then(function(res) {
      if (seq !== self._facetSeq || !self._isFilterPanel() || self.openFacet !== key) return;
      self._renderFacetBody(key, res);
    });
  };

  DataTable.prototype._refreshFacetCounts = function() {
    if (!this._isFilterPanel()) return;
    var self = this;
    // Update the "n selected" labels, then the open checklist's counts.
    this.$panel.querySelectorAll('.dt-facet').forEach(function(el) {
      var k = el.getAttribute('data-k'), n = self.state.filters[k] ? self.state.filters[k].length : 0;
      var head = el.querySelector('.dt-facet-head');
      var tag = head.querySelector('.dt-facet-n, .dt-facet-any');
      if (tag) { tag.className = n ? 'dt-facet-n' : 'dt-facet-any'; tag.textContent = n ? n + ' selected' : 'Any'; }
    });
    var fc = this.$panel.querySelector('.dt-panel-head');
    if (fc) {
      var has = Object.keys(this.state.filters).length, btn = fc.querySelector('.dt-fclear');
      if (has && !btn && this.openPanel === 'filters') { this._renderPanel(); return; }
      if (!has && btn) btn.remove();
    }
    if (this.openFacet) this._loadFacet(this.openFacet);
  };

  DataTable.prototype._renderFacetBody = function(key, res) {
    var self = this, col = this.colMap[key];
    var wrap = this.$panel.querySelector('.dt-facet[data-k="' + key.replace(/"/g, '\\"') + '"] .dt-facet-body');
    if (!wrap) return;
    var selected = this.state.filters[key] || [];
    var values = res.values.slice();
    // Ticked values stay listed even when other filters leave no rows for them.
    selected.forEach(function(v) {
      if (!values.some(function(x) { return x.value === v; })) values.push({ value: v, count: 0 });
    });
    var q = this.facetQuery[key] || '';
    var existing = wrap.querySelector('.dt-facet-search');
    var hadFocus = existing && document.activeElement === existing;
    var caret = hadFocus ? existing.selectionStart : null;

    var h = '';
    if (values.length > 8 || q || res.truncated) {
      h += '<input type="search" class="dt-facet-search" placeholder="Find a value…" value="' + esc(q) + '" autocomplete="off">';
    }
    h += '<div class="dt-facet-actions">' +
      '<button type="button" class="dt-link" data-act="all">Select shown</button>' +
      '<button type="button" class="dt-link" data-act="none">Clear</button>' +
      (selected.length && values.length > 1 ? '<button type="button" class="dt-link" data-act="invert">Invert</button>' : '') +
      '</div>';
    h += '<div class="dt-facet-list">';
    if (!values.length) h += '<div class="muted dt-facet-loading">No values</div>';
    values.forEach(function(x) {
      var on = selected.indexOf(x.value) !== -1;
      var label = self._valueLabel(col, x.value);
      h += '<label class="dt-check' + (x.count === 0 ? ' dt-zero' : '') + '"><input type="checkbox" value="' + esc(x.value) + '"' + (on ? ' checked' : '') + '>' +
        '<span class="dt-check-label' + (x.value === '' ? ' muted' : '') + '">' + esc(label) + '</span>' +
        '<span class="dt-check-n">' + x.count.toLocaleString() + '</span></label>';
    });
    if (res.truncated) h += '<div class="muted dt-facet-loading">Showing the most common values. Type to find others.</div>';
    h += '</div>';
    wrap.innerHTML = h;

    var search = wrap.querySelector('.dt-facet-search');
    if (search) {
      if (hadFocus) { search.focus(); try { search.setSelectionRange(caret, caret); } catch (e) {} }
      var t;
      search.addEventListener('input', function() {
        clearTimeout(t);
        t = setTimeout(function() { self.facetQuery[key] = search.value; self._loadFacet(key); }, self.opts.server ? 250 : 60);
      });
    }
    wrap.querySelectorAll('input[type=checkbox]').forEach(function(cb) {
      cb.addEventListener('change', function() {
        var cur = (self.state.filters[key] || []).slice();
        if (cb.checked) { if (cur.indexOf(cb.value) === -1) cur.push(cb.value); }
        else cur = cur.filter(function(v) { return v !== cb.value; });
        self.setFilterQuiet(key, cur);
      });
    });
    wrap.querySelectorAll('[data-act]').forEach(function(b) {
      b.onclick = function() {
        var act = b.getAttribute('data-act');
        var shown = values.map(function(x) { return x.value; });
        var cur = (self.state.filters[key] || []).slice();
        if (act === 'all') shown.forEach(function(v) { if (cur.indexOf(v) === -1) cur.push(v); });
        else if (act === 'none') cur = [];
        else if (act === 'invert') cur = shown.filter(function(v) { return cur.indexOf(v) === -1; });
        self.setFilterQuiet(key, cur);
      };
    });
  };

  // Apply a filter change from inside the open panel without rebuilding it.
  DataTable.prototype.setFilterQuiet = function(key, values) {
    if (values && values.length) this.state.filters[key] = values;
    else delete this.state.filters[key];
    this.state.page = 1;
    this._changed(false);
  };

  DataTable.prototype._renderSortPanel = function() {
    var self = this, s = this.state.sort;
    var sortable = this.columns.filter(function(c) { return c.sortable; });
    var h = this._panelHead('Sort', s.length ? '<button type="button" class="dt-link dt-sreset">Reset</button>' : '');
    h += '<p class="dt-hint">Rows are ordered by the first level, then ties are broken by the next. ' +
         '<span class="dt-desktop-only">Shift+click a column header to add a level.</span></p>';
    h += '<ol class="dt-tiers">';
    s.forEach(function(t, i) {
      var opts = sortable.filter(function(c) { return c.key === t.key || !s.some(function(x) { return x.key === c.key; }); })
        .map(function(c) { return '<option value="' + esc(c.key) + '"' + (c.key === t.key ? ' selected' : '') + '>' + esc(c.label) + '</option>'; }).join('');
      h += '<li class="dt-tier" data-i="' + i + '">' +
        '<span class="dt-tier-n">' + (i === 0 ? 'Sort by' : 'then by') + '</span>' +
        '<select class="dt-tier-col" aria-label="Sort column">' + opts + '</select>' +
        '<button type="button" class="btn-secondary btn-sm dt-tier-dir" title="Flip direction">' + dirLabel(self.colMap[t.key], t.dir) + '</button>' +
        '<span class="dt-tier-btns">' +
        '<button type="button" class="dt-icon" data-act="up" aria-label="Move up"' + (i === 0 ? ' disabled' : '') + '>' + ICON.up + '</button>' +
        '<button type="button" class="dt-icon" data-act="down" aria-label="Move down"' + (i === s.length - 1 ? ' disabled' : '') + '>' + ICON.down + '</button>' +
        '<button type="button" class="dt-icon dt-icon-x" data-act="rm" aria-label="Remove level">' + ICON.x + '</button>' +
        '</span></li>';
    });
    h += '</ol>';
    var unused = sortable.filter(function(c) { return !s.some(function(x) { return x.key === c.key; }); });
    if (unused.length) {
      h += '<select class="dt-tier-add" aria-label="Add sort level"><option value="">+ Add ' + (s.length ? 'another level' : 'a sort column') + '…</option>' +
        unused.map(function(c) { return '<option value="' + esc(c.key) + '">' + esc(c.label) + '</option>'; }).join('') + '</select>';
    }
    this.$panel.innerHTML = h;

    var reset = this.$panel.querySelector('.dt-sreset');
    if (reset) reset.onclick = function() { self.state.sort = self._validSort(self.opts.defaultSort || []); self.state.page = 1; self._changed(true); };
    this.$panel.querySelectorAll('.dt-tier').forEach(function(li) {
      var i = +li.getAttribute('data-i');
      li.querySelector('.dt-tier-col').onchange = function() { s[i].key = this.value; self._changed(true); };
      li.querySelector('.dt-tier-dir').onclick = function() { s[i].dir = s[i].dir === 'asc' ? 'desc' : 'asc'; self._changed(true); };
      li.querySelectorAll('[data-act]').forEach(function(b) {
        b.onclick = function() {
          var act = b.getAttribute('data-act');
          if (act === 'rm') s.splice(i, 1);
          else {
            var j = act === 'up' ? i - 1 : i + 1;
            var tmp = s[i]; s[i] = s[j]; s[j] = tmp;
          }
          self.state.page = 1;
          self._changed(true);
        };
      });
    });
    var add = this.$panel.querySelector('.dt-tier-add');
    if (add) add.onchange = function() {
      if (!this.value) return;
      var c = self.colMap[this.value];
      s.push({ key: this.value, dir: c.type === 'number' || c.firstDir === 'desc' ? 'desc' : 'asc' });
      self.state.page = 1;
      self._changed(true);
    };
  };

  DataTable.prototype._renderColumnsPanel = function() {
    var self = this, st = this.state;
    var h = this._panelHead('Columns', '<button type="button" class="dt-link dt-creset">Reset</button>');
    h += '<p class="dt-hint">Show or hide columns. <span class="dt-desktop-only">Drag headers to reorder them.</span></p><div class="dt-col-list">';
    st.order.forEach(function(k, i) {
      var c = self.colMap[k];
      h += '<div class="dt-col-row"><label class="dt-check"><input type="checkbox" value="' + esc(k) + '"' +
        (st.visible.indexOf(k) !== -1 ? ' checked' : '') + '><span class="dt-check-label">' + esc(c.label) + '</span></label>' +
        '<span class="dt-tier-btns">' +
        '<button type="button" class="dt-icon" data-act="up" data-k="' + esc(k) + '" aria-label="Move ' + esc(c.label) + ' left"' + (i === 0 ? ' disabled' : '') + '>' + ICON.up + '</button>' +
        '<button type="button" class="dt-icon" data-act="down" data-k="' + esc(k) + '" aria-label="Move ' + esc(c.label) + ' right"' + (i === st.order.length - 1 ? ' disabled' : '') + '>' + ICON.down + '</button>' +
        '</span></div>';
    });
    h += '</div>';
    this.$panel.innerHTML = h;
    this.$panel.querySelectorAll('input[type=checkbox]').forEach(function(cb) {
      cb.onchange = function() {
        if (cb.checked) { if (st.visible.indexOf(cb.value) === -1) st.visible.push(cb.value); }
        else st.visible = st.visible.filter(function(k) { return k !== cb.value; });
        self._save(); self.render();
      };
    });
    this.$panel.querySelectorAll('.dt-icon[data-act]').forEach(function(b) {
      b.onclick = function() {
        var k = b.getAttribute('data-k'), i = st.order.indexOf(k), j = b.getAttribute('data-act') === 'up' ? i - 1 : i + 1;
        if (j < 0 || j >= st.order.length) return;
        st.order[i] = st.order[j]; st.order[j] = k;
        self._save(); self.render(); self._renderPanel();
      };
    });
    this.$panel.querySelector('.dt-creset').onclick = function() {
      st.visible = (self.opts.initialVisible || self.columns.filter(function(c) { return !c.hidden; }).map(function(c) { return c.key; })).slice();
      st.order = self.columns.map(function(c) { return c.key; });
      self._save(); self.render(); self._renderPanel();
    };
  };

  global.DataTable = DataTable;
})(window);
