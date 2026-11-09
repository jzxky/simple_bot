/* Bot history — the "Database" tab of the Activity Log section.
 *
 * Character picker, then two sub-tabs:
 *   Table              → player-hub DataTable (sort, filter, search) with
 *                        quick category filters
 *   Character history  → a summary laid out like the game's character
 *                        history page, built from the bot's own log
 * "Import logs…" at the bottom opens an overlay to rebuild history from
 * activity log files, with a date range to tick logs quickly.
 */
(function () {
  "use strict";
  const CATEGORY_LABELS = window.ACTION_CATEGORY_LABELS || {};
  let ahCharacters = [];
  let ahCurrent = "";
  let ahTable = null;
  let loaded = false;

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  }
  function catLabel(c) { return CATEGORY_LABELS[c] || c; }
  function money(v) {
    if (v === null || v === undefined || v === "") return "";
    v = Number(v);
    return (v < 0 ? "-$" : "$") + Math.abs(v).toLocaleString();
  }
  function fmtTs(ts) { return (ts || "").replace("T", " ").replace("Z", ""); }
  function character() { return document.getElementById("ah-char").value; }

  // Tabs inside this panel only (the page's showTab() would reset the whole card).
  function ahTab(group, name, btn) {
    const root = document.getElementById("action-history");
    root.querySelectorAll(`[data-ah-group="${group}"]`).forEach(p =>
      p.classList.toggle("ah-panel-hidden", p.dataset.ahPanel !== name));
    btn.parentElement.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b === btn));
    if (name === "summary") loadSummary();
  }

  // Top-level Activity Log tabs: Text Log | Database.
  function logTab(name) {
    const sec = document.getElementById("s-log");
    sec.querySelectorAll("[data-log-panel]").forEach(p =>
      p.classList.toggle("ah-panel-hidden", p.dataset.logPanel !== name));
    sec.querySelectorAll("[data-log-tab]").forEach(b =>
      b.classList.toggle("active", b.dataset.logTab === name));
    try { localStorage.setItem("ob-log-tab", name); } catch (e) { /* private mode */ }
    if (name === "db") init();
  }

  // ── Characters ────────────────────────────────────────────────────────────
  async function loadCharacterList() {
    const r = await fetch("/api/actions/characters");
    const data = await r.json();
    ahCharacters = data.characters;
    ahCurrent = data.current;
    const sel = document.getElementById("ah-char");
    const prev = sel.value;
    sel.innerHTML = ahCharacters.map(c => {
      const span = `${c.first_seen.slice(0, 10)} to ${c.current ? "now" : c.last_seen.slice(0, 10)}`;
      const tag = c.current ? "current" : c.status;
      return `<option value="${esc(c.name)}">${esc(c.name)} (${esc(span)}, ${esc(tag)})</option>`;
    }).join("") + '<option value="">All characters</option>';
    if (prev && ahCharacters.some(c => c.name === prev)) sel.value = prev;
    else if (ahCurrent && ahCharacters.some(c => c.name === ahCurrent)) sel.value = ahCurrent;
  }
  function onCharChange() {
    if (ahTable) { ahTable.state.page = 1; ahTable.reload(); }
    loadSummary();
  }

  // ── Table (player-hub DataTable, server mode) ─────────────────────────────
  function tableFetch(q) {
    const ch = character();
    return fetch("/api/actions/table" + q + (ch ? "&character=" + encodeURIComponent(ch) : "")).then(r => r.json());
  }
  // Agg and case work kinds under the game's own names.
  function kindLabel(kind) {
    return KIND_LABELS[kind] || kind || "";
  }
  function sourceLabel(v) { return v ? "Imported · " + v.replace(/^import:/, "") : "Live"; }
  function buildTable() {
    ahTable = new DataTable("ah-dt", {
      id: "actions",
      columns: [
        {key: "ts", label: "Time (UTC)", filter: false, title: true, render: r => esc(fmtTs(r.ts))},
        {key: "server_time", label: "Game time", filter: false},
        {key: "character", label: "Character", hidden: true},
        {key: "category", label: "Category", filterLabel: catLabel},
        {key: "kind", label: "Type", summary: true, filterLabel: v => kindLabel(v), render: r => esc(kindLabel(r.kind))},
        {key: "result", label: "Result", summary: "head", render: r => `<span class="pill ${esc(r.result)}">${esc(r.result)}</span>`},
        {key: "target", label: "Target"},
        {key: "amount", label: "Amount", type: "number", filter: false, cls: "num", summary: true, render: r => esc(money(r.amount))},
        {key: "paid_back", label: "Paid back", type: "number", filter: false, cls: "num", render: r => esc(money(r.paid_back))},
        {key: "city", label: "City"},
        {key: "message", label: "Message", filter: false, sortable: false, cls: "ah-msg",
         render: r => {
           const d = Object.keys(r.detail || {}).length ? "\n" + JSON.stringify(r.detail, null, 2) : "";
           return `<span title="${esc((r.message || "") + d)}">${esc(r.message)}</span>`;
         }},
        {key: "source", label: "Source", hidden: true, filterLabel: sourceLabel, render: r => esc(sourceLabel(r.source))},
      ],
      noun: "actions", nounOne: "action",
      searchPlaceholder: "Search target, type or message…",
      defaultSort: [{key: "ts", dir: "desc"}],
      columnChooser: true,
      perPage: 25,
      emptyText: "No actions recorded yet.",
      server: {load: tableFetch, facet: tableFetch},
      onStateChange: syncQuick,
    });
    document.querySelectorAll("#ah-quick .ah-chip").forEach(b =>
      b.addEventListener("click", () => quickFilter(b.dataset.cat)));
    syncQuick(ahTable.getState());
  }

  // Quick filters: one tap shows only that category; tap again to clear.
  function quickFilter(cat) {
    const cur = (ahTable.getState().filters || {}).category || [];
    const only = cur.length === 1 && cur[0] === cat;
    ahTable.setFilter("category", only ? [] : [cat]);
  }
  function syncQuick(st) {
    const cur = (st.filters || {}).category || [];
    document.querySelectorAll("#ah-quick .ah-chip").forEach(b =>
      b.classList.toggle("on", cur.length === 1 && cur[0] === b.dataset.cat));
  }

  // ── Character history summary ─────────────────────────────────────────────
  async function loadSummary() {
    const panel = document.querySelector('[data-ah-panel="summary"]');
    if (!panel || panel.classList.contains("ah-panel-hidden")) return;
    const ch = character();
    const r = await fetch("/api/actions/summary" + (ch ? "?character=" + encodeURIComponent(ch) : ""));
    renderSummaryGrid(await r.json());
  }

  // Structured like the game's character history page (same section names and
  // row names), but counted from the bot's own action log, so it works for
  // players who don't have character history. Counts are successful actions;
  // the % beside a row is its success rate. Rows with a ▸ expand.
  const CRIME_ROWS = [  // [action kind, character history row name]
    ["pickpocket", "Pickpocketing"], ["mugging", "Muggings"], ["breaking", "Break & Enters"],
    ["torch", "Torches"], ["armed", "Armed Robberies"], ["hack", "Hacking"],
  ];
  const CAREER_SECTIONS = [  // [case work kind, character history section]
    ["banking", "Banking Work"], ["hospital", "Medical Work"], ["lawyer", "Law Work"],
    ["engineering", "Engineering"], ["fire", "Fire Fighter"],
  ];
  const KIND_LABELS = Object.assign(Object.fromEntries(CRIME_ROWS.concat(CAREER_SECTIONS)), {
    manufacture: "Drug manufacturing", study: "Study", degree: "Degree completed",
  });

  const CASE_TYPE_LABELS = {
    sex_change: "Sex Changes", bionics: "Bionic Surgery", flu: "Flu Treatment", recover: "Recovery",
    dna: "DNA Processing", fire: "Fires", investigation: "Investigations", inspection: "Inspections",
    unknown: "Other", other: "Other",
  };
  function caseTypeLabel(kind, t) {
    if (CASE_TYPE_LABELS[t]) return CASE_TYPE_LABELS[t];
    return t.charAt(0).toUpperCase() + t.slice(1);
  }
  function n(v) { return Number(v || 0).toLocaleString(); }
  function rateCell(success, fail) {
    const done = (success || 0) + (fail || 0);
    if (!done) return '<td class="ah-rate"></td>';
    const pct = Math.round(100 * success / done);
    return `<td class="ah-rate ${pct >= 75 ? "good" : pct < 40 ? "poor" : ""}">${pct}%</td>`;
  }
  function sumOf(kinds, key) { return kinds.reduce((a, k) => a + (k[key] || 0), 0); }

  // One key/value row. opts: rate [success, fail], money (value is $),
  // cls, sub (child rows [{label, value, rate}] shown when tapped).
  let _grp = 0;
  function chRow(label, value, opts) {
    opts = opts || {};
    const rate = opts.rate ? rateCell(opts.rate[0], opts.rate[1]) : '<td class="ah-rate"></td>';
    const val = `<td class="ch-val${opts.money ? " ch-money" : ""}">${opts.money ? esc(money(value) || "$0") : n(value)}</td>`;
    if (!opts.sub || !opts.sub.length) {
      return `<tr${opts.cls ? ` class="${opts.cls}"` : ""}><td class="ch-key">${esc(label)}</td>${val}${rate}</tr>`;
    }
    const g = "g" + (++_grp);
    let html = `<tr class="ah-exp${opts.cls ? " " + opts.cls : ""}" data-group="${g}" onclick="ahToggleSummaryGroup(this)">
      <td class="ch-key"><span class="ah-caret">▸</span> ${esc(label)}</td>${val}${rate}</tr>`;
    for (const x of opts.sub) {
      html += `<tr class="ah-sub" data-parent="${g}" style="display:none"><td class="ch-key">${esc(x.label)}</td>
        <td class="ch-val">${x.units ? n(x.value) + " used" : n(x.value)}</td>
        ${x.rate ? rateCell(x.rate[0], x.rate[1]) : '<td class="ah-rate"></td>'}</tr>`;
    }
    return html;
  }
  // Sections open on desktop and start collapsed on phones; a tap on the
  // title flips one, and the choice survives re-renders.
  const sectionOpen = {};
  function isOpen(title) {
    return title in sectionOpen ? sectionOpen[title] : !window.matchMedia("(max-width: 640px)").matches;
  }
  function chSection(title, rows, note, total) {
    if (!rows) return "";
    // Cards that never show a success rate don't need the % column.
    if (!/class="ah-rate[^"]*">[^<]/.test(rows)) rows = rows.split('<td class="ah-rate"></td>').join("");
    const open = isOpen(title);
    return `<div class="ch-grid-item"><div class="ch-section ah-sec${open ? "" : " ah-collapsed"}" data-title="${esc(title)}">
      <div class="ch-section-head ah-sec-head" onclick="ahToggleSection(this)">
        <span class="ah-caret">▸</span><span class="ch-section-title">${esc(title)}</span>
        ${total !== undefined && total !== "" ? `<span class="ah-sec-total">${esc(total)}</span>` : ""}
      </div>
      <div class="ah-sec-body"><table class="ch-table">${rows}</table>
      ${note ? `<div class="ah-sec-note">${esc(note)}</div>` : ""}</div></div></div>`;
  }
  function toggleSection(head) {
    const sec = head.closest(".ah-sec");
    const open = sec.classList.toggle("ah-collapsed") === false;
    sectionOpen[sec.dataset.title] = open;
  }
  function subRows(kinds, withRate) {
    return kinds.slice().sort((a, b) => (b.success || 0) - (a.success || 0))
      .map(k => ({label: k.kind || "–", value: k.success, rate: withRate ? [k.success, k.fail] : null}));
  }

  function renderSummaryGrid(summary) {
    const byKind = summary.by_kind || [];
    const caseTypes = summary.case_types || [];
    _grp = 0;
    const box = document.getElementById("ah-summary");
    const byCat = {};
    byKind.forEach(k => (byCat[k.category] = byCat[k.category] || []).push(k));
    const cat = c => byCat[c] || [];
    const kindOf = (c, kind) => cat(c).find(k => k.kind === kind);
    let html = "";

    // ── Character Information ──
    let info = "";
    const gym = cat("gym").filter(k => k.kind !== "membership");
    if (gym.length) info += chRow("Gym Trains", sumOf(gym, "success"), {sub: subRows(gym)});
    if (cat("community_service").length) {
      info += chRow("Community Services", sumOf(cat("community_service"), "success"), {sub: subRows(cat("community_service"))});
    }
    if (cat("dog_train").length) {
      info += chRow("Dog Trains", sumOf(cat("dog_train"), "success"), {sub: subRows(cat("dog_train"))});
    }
    if (cat("consume").length) {
      info += chRow("Consumables Used", sumOf(cat("consume"), "units"),
        {sub: cat("consume").slice().sort((a, b) => b.units - a.units).map(k => ({label: k.kind || "–", value: k.units, units: true}))});
    }
    if (cat("fire_duty").length) {
      const f = cat("fire_duty");
      info += chRow("Fire Duties", sumOf(f, "success"), {rate: [sumOf(f, "success"), sumOf(f, "fail")], sub: subRows(f, true)});
    }
    const jailed = kindOf("jail", "jailed");
    if (jailed) info += chRow("Times Jailed", jailed.n);
    const jb = kindOf("jail", "jailbreak");
    if (jb) info += chRow("Jailbreaks", jb.success, {rate: [jb.success, jb.fail]});
    if (cat("jail_duty").length) {
      const d = cat("jail_duty");
      info += chRow("Jail Duties", sumOf(d, "success"), {rate: [sumOf(d, "success"), sumOf(d, "fail")], sub: subRows(d, true)});
    }
    html += chSection("Character Information", info);

    // ── Crimes Committed ──
    const aggs = cat("agg");
    if (aggs.length) {
      let rows = "";
      const known = new Set(CRIME_ROWS.map(r => r[0]));
      for (const [kind, label] of CRIME_ROWS) {
        const k = kindOf("agg", kind);
        if (k) rows += chRow(label, k.success, {rate: [k.success, k.fail]});
      }
      aggs.filter(k => !known.has(k.kind)).forEach(k => { rows += chRow(k.kind || "Other", k.success, {rate: [k.success, k.fail]}); });
      rows += chRow("Total Aggravated", sumOf(aggs, "success"), {rate: [sumOf(aggs, "success"), sumOf(aggs, "fail")], cls: "ah-total"});
      rows += chRow("Money Taken", sumOf(aggs, "amount"), {money: true, cls: "ah-total"});
      html += chSection("Crimes Committed", rows, "", n(sumOf(aggs, "success")));
    }

    // ── Career sections (case work): successful work by type, no fails ──
    const cw = cat("case_work");
    const careerKinds = new Set(CAREER_SECTIONS.map(c => c[0]));
    const careers = CAREER_SECTIONS.concat(cw.filter(k => !careerKinds.has(k.kind)).map(k => [k.kind, k.kind || "Case Work"]));
    for (const [kind, title] of careers) {
      const k = kindOf("case_work", kind);
      if (!k) continue;
      const types = caseTypes.filter(t => t.kind === kind);
      let rows = "";
      if (kind === "banking") {
        const own = types.find(t => t.type === "own");
        const client = types.find(t => t.type === "client");
        rows += chRow("Launders for Clients", client ? client.n : 0);
        rows += chRow("Own Money Laundered", own ? own.n : 0);
        rows += chRow("Total Laundered", k.amount, {money: true, cls: "ah-total"});
      } else {
        for (const t of types) rows += chRow(caseTypeLabel(kind, t.type), t.n);
        if (types.length !== 1) rows += chRow("Total", k.success, {cls: "ah-total"});
        if (kind === "hospital" && k.fail) {
          rows += chRow("Failures", k.fail, {sub: (summary.hospital_fails || []).map(f => ({label: f.message || "(no message)", value: f.n}))});
        }
        if (k.amount) rows += chRow("Earned", k.amount, {money: true, cls: "ah-total"});
      }
      html += chSection(title, rows, "", kind === "banking" ? money(k.amount) : n(k.success));
    }

    // ── Money sent to contacts to be laundered ──
    const sent = cat("launder");
    if (sent.length) {
      let rows = chRow("Launders Sent", sumOf(sent, "success"),
        {rate: [sumOf(sent, "success"), sumOf(sent, "fail")], sub: subRows(sent)});
      rows += chRow("Total Sent", sumOf(sent, "amount"), {money: true, cls: "ah-total"});
      html += chSection("Money Laundering", rows, "Dirty money sent to banker contacts to be laundered.",
        money(sumOf(sent, "amount")));
    }

    // ── Training & Education ──
    const ct = cat("career_training"), tc = cat("training_centre");
    const study = kindOf("university", "study"), degree = kindOf("university", "degree");
    if (ct.length || tc.length || study || degree) {
      let rows = "";
      if (ct.length) rows += chRow("Career Training", sumOf(ct, "success"), {sub: subRows(ct)});
      if (tc.length) rows += chRow("Training Centre", sumOf(tc, "success"), {sub: subRows(tc)});
      if (study) rows += chRow("University Study", study.success, {rate: [study.success, study.fail]});
      if (degree) {
        rows += chRow("Degrees Completed", degree.success,
          {sub: (summary.degrees || []).map(d => ({label: d, value: 1}))});
      }
      html += chSection("Training & Education", rows, "",
        n(sumOf(ct, "success") + sumOf(tc, "success") + (study ? study.success : 0)));
    }

    // ── Earn History ──
    const earns = cat("earn"), queue = cat("earn_queue");
    const drugs = kindOf("drug_manufacture", "manufacture");
    if (earns.length || queue.length || drugs) {
      let rows = "";
      if (earns.length) {
        rows += chRow("Manual Earns", sumOf(earns, "success"), {rate: [sumOf(earns, "success"), sumOf(earns, "fail")], sub: subRows(earns, true)});
        if (sumOf(earns, "amount")) rows += chRow("Earned", sumOf(earns, "amount"), {money: true});
      }
      if (queue.length) rows += chRow("Earn Queue Top-ups", sumOf(queue, "success"), {sub: subRows(queue)});
      if (drugs) rows += chRow("Drug Manufacturing", drugs.success, {rate: [drugs.success, drugs.fail]});
      html += chSection("Earn History", rows,
        "Auto earns can't be tracked: the game runs the auto earn queue on its own servers.",
        n(sumOf(earns, "success")));
    }

    // Anything else the bot records later still shows up.
    const shown = new Set(["gym", "community_service", "dog_train", "consume", "jail", "jail_duty",
                           "agg", "case_work", "earn", "earn_queue", "fire_duty", "career_training",
                           "training_centre", "university", "drug_manufacture", "launder"]);
    Object.keys(byCat).filter(c => !shown.has(c)).forEach(c => {
      html += chSection(catLabel(c), byCat[c].map(k => chRow(k.kind || "–", k.success, {rate: [k.success, k.fail]})).join(""));
    });

    // Headline totals above the cards.
    const caseWork = cat("case_work");
    const made = sumOf(aggs, "amount") + sumOf(caseWork, "amount") + sumOf(earns, "amount");
    const tiles = [
      ["Aggs", n(sumOf(aggs, "success"))],
      ["Case Work", n(sumOf(caseWork, "success"))],
      ["Manual Earns", n(sumOf(earns, "success"))],
      ["Money Made", money(made) || "$0"],
    ];
    document.getElementById("ah-totals").innerHTML = byKind.length ? tiles.map(([l, v]) =>
      `<div class="ah-tile"><div class="v">${esc(v)}</div><div class="l">${esc(l)}</div></div>`).join("") : "";
    box.innerHTML = html || '<div class="ah-empty" style="grid-column:1/-1">No actions recorded yet.</div>';
  }

  function toggleSummaryGroup(tr) {
    const open = !tr.classList.contains("open");
    tr.classList.toggle("open", open);
    tr.closest("table").querySelectorAll(`tr.ah-sub[data-parent="${tr.dataset.group}"]`)
      .forEach(r => r.style.display = open ? "" : "none");
  }

  function table(headers, rows) {
    return `<table class="ah-table"><thead><tr>${headers.map((h, i) =>
      `<th class="${i ? "num" : ""}">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(r =>
      `<tr>${r.map((c, i) => `<td class="${i ? "num" : ""}">${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }

  // ── Import from activity logs ───────────────────────────────────────────────
  async function loadLogs() {
    const r = await fetch("/api/actions/logs");
    const data = await r.json();
    const inp = document.getElementById("imp-char");
    if (!inp.value) inp.value = document.getElementById("ah-char").value || data.current || "";
    document.getElementById("imp-char-list").innerHTML =
      ahCharacters.map(c => `<option value="${esc(c.name)}">`).join("");
    const body = document.getElementById("imp-logs");
    document.getElementById("imp-all").checked = false;
    if (!data.logs.length) {
      body.innerHTML = '<tr><td colspan="4" class="ah-empty">No activity logs found.</td></tr>';
      return;
    }
    const end = document.getElementById("imp-end");
    if (!end.value) end.value = data.game_date || "";
    body.innerHTML = data.logs.map(l => `<tr>
        <td><input type="checkbox" class="imp-file" value="${esc(l.file)}"
                   data-start="${esc(l.start || "")}" data-end="${esc(l.end || l.start || "")}"></td>
        <td>${esc(l.file)}</td>
        <td class="num">${(l.size / 1024).toFixed(0)} KB</td>
        <td>${l.imported.map(i => `${esc(i.character)} (${i.rows})`).join(", ") || "–"}</td>
      </tr>`).join("");
    if (document.getElementById("imp-start").value) selectRange();
  }
  function toggleAllLogs(on) {
    document.querySelectorAll(".imp-file").forEach(c => c.checked = on);
    document.getElementById("imp-range-note").textContent = "";
  }
  // Tick every log that was written to between the start and end dates.
  function selectRange() {
    const start = document.getElementById("imp-start").value;
    const end = document.getElementById("imp-end").value;
    const note = document.getElementById("imp-range-note");
    if (!start && !end) { note.textContent = ""; return; }
    if (start && end && start > end) { note.textContent = "Start date is after the end date."; return; }
    let n = 0;
    document.querySelectorAll(".imp-file").forEach(c => {
      const fs = c.dataset.start, fe = c.dataset.end || fs;
      const on = !!fs && (!end || fs <= end) && (!start || fe >= start);
      c.checked = on;
      if (on) n++;
    });
    document.getElementById("imp-all").checked = false;
    note.textContent = `${n} log${n === 1 ? "" : "s"} selected`;
  }
  function openImport() {
    document.getElementById("ah-import-overlay").classList.add("active");
    document.body.classList.add("ah-modal-open");
    loadLogs();
  }
  function closeImport() {
    document.getElementById("ah-import-overlay").classList.remove("active");
    document.body.classList.remove("ah-modal-open");
  }
  async function runImport(dryRun) {
    const files = [...document.querySelectorAll(".imp-file:checked")].map(c => c.value);
    const character = document.getElementById("imp-char").value.trim();
    const status = document.getElementById("imp-status");
    const out = document.getElementById("imp-result");
    if (!files.length) { status.textContent = "Select at least one log."; return; }
    if (!character) { status.textContent = "Enter the character name."; return; }
    const existing = ahCharacters.some(c => c.name === character);
    if (!dryRun && !existing &&
        !confirm(`"${character}" isn't a character in the database yet. Import as a new character?`)) return;
    status.textContent = dryRun ? "Reading logs…" : "Importing…";
    const r = await fetch("/api/actions/import", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({files, character, dry_run: dryRun}),
    });
    const data = await r.json();
    if (!r.ok) { status.innerHTML = `<span class="imp-err">${esc(data.error || "Import failed")}</span>`; return; }
    status.textContent = (dryRun ? "Preview: " : "Imported ") +
      `${data.total.toLocaleString()} actions for ${data.character}` + (dryRun ? " (nothing saved yet)" : ".");
    out.innerHTML = '<div class="ah-box">' + table(
      ["Log file", "Actions", "Skipped (already live)", "By category"],
      data.files.map(f => f.error ? [f.file, "–", "–", f.error] : [
        f.file, f.rows, f.skipped_live,
        Object.entries(f.by_category).map(([k, v]) => `${catLabel(k)} ${v}`).join(", ") || "none",
      ])) + "</div>";
    if (!dryRun) {
      await loadCharacterList();
      document.getElementById("ah-char").value = character;
      loadLogs();
      onCharChange();
    }
  }

  // The picker sticks just under the main menu, which is itself sticky.
  function setStickyTop() {
    const bar = document.getElementById("main-tab-bar");
    const root = document.getElementById("action-history");
    if (bar && root) root.style.setProperty("--ah-sticky-top", bar.offsetHeight + "px");
  }

  // ── Init: load when the Activity Log section is first opened ─────────────
  async function init() {
    if (loaded || !document.getElementById("action-history")) return;
    loaded = true;
    setStickyTop();
    window.addEventListener("resize", setStickyTop);
    await loadCharacterList();
    buildTable();
  }
  window.ahTab = ahTab;
  window.ahLogTab = logTab;
  window.ahSelectRange = selectRange;
  window.ahOpenImport = openImport;
  window.ahCloseImport = closeImport;
  window.ahOnCharChange = onCharChange;
  window.ahToggleSummaryGroup = toggleSummaryGroup;
  window.ahToggleSection = toggleSection;
  window.ahToggleAllLogs = toggleAllLogs;
  window.ahRunImport = runImport;
  window.ahInit = init;
  // Load the database the first time its tab is shown.
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && document.getElementById("ah-import-overlay")?.classList.contains("active")) closeImport();
  });
  document.addEventListener("DOMContentLoaded", () => {
    let tab = "text";
    try { tab = localStorage.getItem("ob-log-tab") || "text"; } catch (e) { /* private mode */ }
    if (tab === "db") logTab("db");
  });
})();
