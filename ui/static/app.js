const EARN_MAP = {
  Secret:      [["whore","Whore"],["street_fight","Streetfight"],["joy_ride","Joyride"],["pimp","Pimp"]],
  General:     [["shoplift","Shoplift"],["steal_cheques","Steal Cheques"]],
  Hospital:    [["nurse","Nurse"],["doctor","Doctor"],["surgeon","Surgeon"]],
  Engineering: [["mechanic","Mechanic"]],
  Bank:        [["bank_teller","Work at Local Bank"]],
  Mortician:   [["mortician_assistant","Mortician Assistant"]],
  Law:         [["legal_secretary","Legal Secretary"]],
  Crime:       [["shoplift","Shoplift"],["steal_cheques","Steal Cheques"],["drag_racing","Compete at illegal drags"],["hack_bank","Hack bank account"],["scamming","Scamming"]],
};

const ACTION_SUB_MAP = {
  community_service: [],  // bot always picks the highest tier automatically
  career_training: [
    ["fire","Fire Department"],
    ["customs","Customs"],
    ["police","Police"],
  ],
  university: [
    ["Business","Business"],
    ["Science","Science"],
    ["Medicine","Medicine"],
    ["Engineering","Engineering"],
    ["Law","Law"],
  ],
  training_centre: [],
  drug_manufacturing: [],
};

function populateEarns(selectedValue) {
  const cat = document.getElementById("earn_category").value;
  const sel = document.getElementById("earn_type");
  const opts = EARN_MAP[cat] || [];
  sel.innerHTML = opts.map(([v, l]) =>
    `<option value="${v}" ${v === selectedValue ? "selected" : ""}>${l}</option>`
  ).join("");
  _updateEarnsPills();
}

function populateActionSub(selectedValue) {
  const type = document.getElementById("action_type").value;
  const sel = document.getElementById("action_sub");
  const label = document.getElementById("action_sub_label");
  const opts = ACTION_SUB_MAP[type] || [];

  if (opts.length === 0) {
    label.style.visibility = "hidden";
    sel.innerHTML = "";
    return;
  }
  label.style.visibility = "visible";
  sel.innerHTML = opts.map(([v, l]) =>
    `<option value="${v}" ${v === selectedValue ? "selected" : ""}>${l}</option>`
  ).join("");
}

function toggleAwayCrime() {
  const primary = document.getElementById("primary_crime").value;
  document.getElementById("away_crime_row").style.display = primary === "hack" ? "" : "none";
}

function showTab(id, btn) {
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  btn.classList.add("active");
}

// ── Save ─────────────────────────────────────────────────────────────────────

function _doSave() {
  const data = {
    email: document.getElementById("email").value,
    password: document.getElementById("password").value,
    earns_enabled: document.getElementById("earns_enabled").checked,
    earn_category: document.getElementById("earn_category").value,
    earn_type: document.getElementById("earn_type").value,
    crimes_enabled: document.getElementById("crimes_enabled").checked,
    primary_crime: document.getElementById("primary_crime").value,
    primary_threshold: document.getElementById("primary_threshold").value,
    away_crime: document.getElementById("away_crime").value,
    away_threshold: document.getElementById("away_threshold").value,
    armed_agg_private: document.getElementById("armed_agg_private").checked,
    armed_agg_drug_house: document.getElementById("armed_agg_drug_house").checked,
    armed_payback_private: document.getElementById("armed_payback_private").checked,
    armed_payback_public: document.getElementById("armed_payback_public").checked,
    action_enabled: document.getElementById("action_enabled").checked,
    action_type: document.getElementById("action_type").value,
    action_sub: document.getElementById("action_sub").value,
    away_action_enabled: document.getElementById("action_enabled").checked,
    away_action_type: document.getElementById("away_action_type").value,
    fallback_to_away: document.getElementById("fallback_to_away").checked,
    payback_enabled: document.getElementById("payback_enabled").checked,
    logout_on_stop: document.getElementById("logout_on_stop").checked,
    relog_on_session_expire: document.getElementById("relog_on_session_expire").checked,
    case_work_enabled: document.getElementById("case_work_enabled").checked,
    hospital_poll_interval: parseInt(document.getElementById("hospital_poll_interval").value) || 31,
    fire_poll_interval: parseInt(document.getElementById("fire_poll_interval").value) || 31,
    hospital_tasks: _serializePriorityTable("hospital-priority-body"),
    player_refresh_interval: parseInt(document.getElementById("player_refresh_interval").value) || 30,
    consume_timer_limit: document.getElementById("consume_timer_limit").value || "00:00",
    auto_consume: document.getElementById("auto_consume").checked,
    auto_consumable: document.getElementById("auto_consumable").value,
    consumable_limit: parseInt(document.getElementById("consumable_limit").value) || 33,
    consumable_buffer: parseInt(document.getElementById("consumable_buffer").value) || 0,
  };

  return fetch("/save", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data),
  }).then(r => r.json());
}

function autoSave() {
  _doSave();
  _updateCrimePills();
  _updateEarnsPills();
  _updateActionsPills();
}

// ── Credentials save ──────────────────────────────────────────────────────────

function markCredsDirty() {
  document.getElementById("email").classList.add("input-unsaved");
  document.getElementById("password").classList.add("input-unsaved");
  document.getElementById("creds-save-btn").classList.add("needed");
}

function saveCredentials() {
  _doSave().then(() => {
    document.getElementById("email").classList.remove("input-unsaved");
    document.getElementById("password").classList.remove("input-unsaved");
    document.getElementById("creds-save-btn").classList.remove("needed");
  });
}

// ── Number input save ─────────────────────────────────────────────────────────

function markNumDirty(el) {
  el.classList.add("input-unsaved");
  const btn = document.getElementById("save-" + el.id);
  if (btn) btn.classList.add("needed");
}

function saveNum(id) {
  _doSave().then(() => {
    const el = document.getElementById(id);
    if (el) el.classList.remove("input-unsaved");
    const btn = document.getElementById("save-" + id);
    if (btn) btn.classList.remove("needed");
  });
}

// ── Collapse ──────────────────────────────────────────────────────────────────

function _collapseState() {
  try { return JSON.parse(localStorage.getItem("mm_collapse") || "{}"); } catch { return {}; }
}

function toggleSection(id) {
  const section = document.getElementById(id);
  const body = section.querySelector(".card-body");
  const btn = section.querySelector(".collapse-btn");
  const collapsed = body.classList.toggle("collapsed");
  btn.classList.toggle("collapsed", collapsed);
  section.classList.toggle("is-collapsed", collapsed);
  const state = _collapseState();
  state[id] = collapsed;
  localStorage.setItem("mm_collapse", JSON.stringify(state));
}

function initCollapse() {
  const state = _collapseState();
  document.querySelectorAll(".card[id]").forEach(section => {
    if (state[section.id]) {
      const body = section.querySelector(".card-body");
      const btn = section.querySelector(".collapse-btn");
      if (body) body.classList.add("collapsed");
      if (btn) btn.classList.add("collapsed");
      section.classList.add("is-collapsed");
    }
  });
}

// ── Section pills ─────────────────────────────────────────────────────────────

function _pill(text) {
  return `<span class="pill">${escHtml(text)}</span>`;
}

function _selText(id) {
  const sel = document.getElementById(id);
  return sel ? sel.options[sel.selectedIndex].text : "";
}

function _updateCrimePills() {
  const el = document.getElementById("pills-s-crimes");
  if (!el) return;
  const crime = document.getElementById("primary_crime").value;
  const thresh = parseFloat(document.getElementById("primary_threshold").value);
  const pills = [_pill(`${_selText("primary_crime")} // ${thresh}%`)];
  if (crime === "hack") {
    const at = parseFloat(document.getElementById("away_threshold").value);
    pills.push(_pill(`${_selText("away_crime")} // ${at}%`));
  }
  el.innerHTML = pills.join("");
}

function _updateEarnsPills() {
  const el = document.getElementById("pills-s-earns");
  if (!el) return;
  const label = _selText("earn_type");
  el.innerHTML = label ? _pill(label) : "";
}

function _updateActionsPills() {
  const el = document.getElementById("pills-s-actions");
  if (!el) return;
  el.innerHTML = _pill(_selText("action_type")) + _pill(_selText("away_action_type"));
}

let _lastEnergy = null;

function _updateCharPills() {
  const el = document.getElementById("pills-s-character");
  if (!el) return;
  const pills = [];
  if (_lastEnergy != null) pills.push(_pill(`⚡ ${_lastEnergy}%`));
  const now = Date.now();
  for (const [key, t] of Object.entries(_activeTimers)) {
    const secs = Math.max(0, Math.floor((t.endMs - now) / 1000));
    if (secs > 0) pills.push(_pill(`${t.label}: ${_fmtCountdown(secs)}`));
  }
  if (_aggProActive && !_activeTimers["aggpro"]) pills.push(_pill("AggPro: Active"));
  el.innerHTML = pills.join("");
}

let _botRunning = false;
let _botPaused = false;
let _prevEarnsEnabled = null;

function toggleBot() {
  if (_botRunning) {
    fetch("/stop", {method: "POST"})
      .then(r => r.json())
      .then(d => updateBotState(d.running, d.paused));
  } else {
    _doSave().then(() =>
      fetch("/start", {method: "POST"})
        .then(r => r.json())
        .then(d => updateBotState(d.running, d.paused))
    );
  }
}

function togglePause() {
  const endpoint = _botPaused ? "/resume" : "/pause";
  fetch(endpoint, {method: "POST"})
    .then(r => r.json())
    .then(d => updateBotState(d.running, d.paused));
}

function updateBotState(running, paused) {
  _botRunning = running;
  _botPaused = paused;

  const toggleBtn = document.getElementById("toggle-btn");
  const pauseBtn = document.getElementById("pause-btn");
  const dot = document.getElementById("status-dot");
  const txt = document.getElementById("status-text");

  toggleBtn.textContent = running ? "Stop Bot" : "Start Bot";
  toggleBtn.className = running ? "running" : "";

  pauseBtn.disabled = !running;
  pauseBtn.textContent = paused ? "Resume" : "Pause";
  pauseBtn.className = paused ? "paused" : "";

  dot.className = "dot " + (running ? (paused ? "paused" : "running") : "stopped");
  txt.textContent = running ? (paused ? "Paused" : "Running") : "Stopped";
}

const CONSUMABLE_LABELS = {
  marijuana: "Weed", cocaine: "Cocaine", ecstasy: "Ecstasy",
  acid: "Acid", speed: "Speed", heroin: "Heroin", pice: "P/Ice",
};

function pollStatus() {
  fetch("/status")
    .then(r => r.json())
    .then(d => {
      updateBotState(d.running, d.paused);

      const taskEl = document.getElementById("status-task");
      if (taskEl) taskEl.textContent = (d.running && !d.paused && d.current_task) ? d.current_task : "";

      // Only uncheck earns if the bot just disabled it (true→false transition)
      if (d.earns_enabled != null) {
        if (_prevEarnsEnabled === true && d.earns_enabled === false) {
          document.getElementById("earns_enabled").checked = false;
        }
        _prevEarnsEnabled = d.earns_enabled;
      }

      // Character stats
      document.getElementById("stat-name").textContent = d.own_name || "--";
      document.getElementById("stat-rank").textContent = d.rank || "--";
      document.getElementById("stat-next-rank").textContent = d.next_rank || "--";
      document.getElementById("stat-rank-progress").textContent = d.rank_progress != null ? d.rank_progress + "%" : "--";
      document.getElementById("stat-occupation").textContent = d.occupation || "--";
      document.getElementById("stat-city").textContent = d.city || "--";
      document.getElementById("stat-home-city").textContent = d.home_city || "--";
      document.getElementById("stat-health").textContent = d.health != null ? d.health + "%" : "--";
      document.getElementById("stat-energy").textContent = d.energy != null ? d.energy + "%" : "--";
      document.getElementById("stat-earns").textContent = d.earns_24h != null ? d.earns_24h : "--";
      document.getElementById("stat-cons-24h").textContent = d.consumables_24h != null ? d.consumables_24h : "--";

      const fmt = n => "$" + (n ?? 0).toLocaleString();
      document.getElementById("stat-clean").textContent = d.clean_money != null ? fmt(d.clean_money) : "--";
      document.getElementById("stat-dirty").textContent = d.dirty_money != null ? fmt(d.dirty_money) : "--";

      // Consumables
      const cons = d.consumables || {};
      document.getElementById("stat-consumables").innerHTML =
        Object.entries(CONSUMABLE_LABELS).filter(([k]) => (cons[k] ?? 0) > 0).map(([k, label]) =>
          `<div class="consumable-item"><span class="consumable-name">${label}</span><span class="consumable-qty ${_botRunning ? 'consumable-link' : ''}" onclick="${_botRunning ? `consumeItem('${k}')` : ''}">${cons[k]}</span></div>`
        ).join("") || '<span class="placeholder">No consumables</span>';

      // Timers
      _lastEnergy = d.energy;
      updateTimers(d.timers || {}, d.server_time, d.agg_pro_active);
      _updateCharPills();

      // Case work auto-detect
      updateCaseWorkSection(d.occupation || "");

      // Log — only update live view; switch back to live if first log file matches
      const logSel = document.getElementById("log-file-select");
      if (logSel && logSel.options.length && logSel.options[0].value === _logCurrentFile) {
        _logLiveMode = true;
      }
      if (_logLiveMode) {
        const box = document.getElementById("log-box");
        box.innerHTML = [...d.log].reverse()
          .map(l => `<div class="log-line">${escHtml(l)}</div>`)
          .join("");
      }
    })
    .catch(() => {})
    .finally(() => setTimeout(pollStatus, 3000));
}

const TIMER_LABELS = {
  action:   "Action",
  aggpro:   "AggPro",
  crime:    "Crime",
  earn:     "Earn",
  business: "Business",
  training: "Training",
  jail:     "Jail",
  case:     "Case",
  whack:    "Whack",
  travel:   "Travel",
  skill:    "Skill",
  launder:  "Launder",
  traffick: "Trafficking",
  event:    "Event",
};


// Each entry: { label, endMs (absolute wall-clock ms) }
let _activeTimers = {};
let _timerInterval = null;
let _lastServerTime = null;  // only recalculate anchors when server_time changes

function _parseServerTime(str) {
  if (!str) return null;
  return new Date(str);
}

function _fmtCountdown(secs) {
  if (secs <= 0) return "Ready";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2,"0")}m ${String(s).padStart(2,"0")}s`;
  if (m > 0) return `${m}m ${String(s).padStart(2,"0")}s`;
  return `${s}s`;
}

// _aggProActive tracks latest agg_pro_active from status for always-visible tile
let _aggProActive = false;

function updateTimers(timers, serverTimeStr, aggProActive) {
  _aggProActive = aggProActive;

  // Only re-anchor countdowns when server_time changes (fresh state refresh).
  // Between polls the wall-clock countdowns keep ticking uninterrupted.
  if (serverTimeStr !== _lastServerTime) {
    _lastServerTime = serverTimeStr;
    const serverTime = _parseServerTime(serverTimeStr);
    if (serverTime) {
      const now = Date.now();
      const newActive = {};
      for (const [key, t] of Object.entries(timers)) {
        if (key === "aggpro") continue; // handled separately as always-visible
        if (t.ready || !t.end) continue;
        const endTime = _parseServerTime(t.end);
        if (!endTime) continue;
        const remainingSecs = Math.floor((endTime - serverTime) / 1000);
        if (remainingSecs <= 0) continue;
        newActive[key] = { label: TIMER_LABELS[key] || key, endMs: now + remainingSecs * 1000 };
      }
      // AggPro countdown
      const ap = timers["aggpro"];
      if (ap && !ap.ready && ap.end) {
        const endTime = _parseServerTime(ap.end);
        if (endTime) {
          const remainingSecs = Math.floor((endTime - serverTime) / 1000);
          if (remainingSecs > 0) {
            newActive["aggpro"] = { label: "AggPro", endMs: now + remainingSecs * 1000 };
          }
        }
      }
      _activeTimers = newActive;
    }
  }

  _renderTimers();
  if (Object.keys(_activeTimers).length > 0 && !_timerInterval) {
    _timerInterval = setInterval(_tickTimers, 1000);
  }
}

function _tickTimers() {
  const now = Date.now();
  for (const key of Object.keys(_activeTimers)) {
    if (key === "aggpro") continue; // never auto-remove aggpro tile
    if (Math.floor((_activeTimers[key].endMs - now) / 1000) <= 0) {
      delete _activeTimers[key];
    }
  }
  // If aggpro countdown expired, keep tile but it will show as inactive
  if (_activeTimers["aggpro"] && Math.floor((_activeTimers["aggpro"].endMs - now) / 1000) <= 0) {
    delete _activeTimers["aggpro"];
  }
  _renderTimers();
  _updateCharPills();
  // Keep interval running as long as there are countdown timers or AggPro is shown
  const countdownKeys = Object.keys(_activeTimers).filter(k => k !== "aggpro");
  if (countdownKeys.length === 0 && !_aggProActive) {
    clearInterval(_timerInterval);
    _timerInterval = null;
  }
}

function _renderTimers() {
  const grid = document.getElementById("stat-timers-grid");
  const now = Date.now();
  const tiles = [];

  // AggPro always shown
  if (_activeTimers["aggpro"]) {
    const secs = Math.max(0, Math.floor((_activeTimers["aggpro"].endMs - now) / 1000));
    tiles.push(`<div class="stat-item stat-item-timer"><span class="stat-label">AggPro</span><span class="stat-value stat-timer-value">${_fmtCountdown(secs)}</span></div>`);
  } else {
    const val = _aggProActive ? "Active" : "None";
    const cls = _aggProActive ? "stat-timer-value" : "";
    tiles.push(`<div class="stat-item"><span class="stat-label">AggPro</span><span class="stat-value ${cls}">${val}</span></div>`);
  }

  // Other active countdown timers
  for (const [key, t] of Object.entries(_activeTimers)) {
    if (key === "aggpro") continue;
    const secs = Math.max(0, Math.floor((t.endMs - now) / 1000));
    tiles.push(`<div class="stat-item stat-item-timer"><span class="stat-label">${escHtml(t.label)}</span><span class="stat-value stat-timer-value">${_fmtCountdown(secs)}</span></div>`);
  }

  grid.innerHTML = tiles.join("");
}

function takeScreenshot() {
  const btn = document.getElementById("screenshot-btn");
  btn.textContent = "Loading...";
  btn.disabled = true;
  fetch("/screenshot")
    .then(r => r.json())
    .then(d => {
      if (d.error) {
        alert("Screenshot failed: " + d.error);
        return;
      }
      const win = window.open("", "_blank");
      win.document.write(
        `<html><head><title>Bot Screenshot</title>
        <style>body{margin:0;background:#111;display:flex;justify-content:center;}
        img{max-width:100%;height:auto;}</style></head>
        <body><img src="${d.image}"></body></html>`
      );
      win.document.close();
    })
    .catch(e => alert("Screenshot error: " + e))
    .finally(() => {
      btn.textContent = "Screenshot";
      btn.disabled = false;
    });
}

function clearEarnQueue() {
  const btn = document.getElementById("clear-earn-btn");
  btn.disabled = true;
  fetch("/clear_earn_queue", { method: "POST" })
    .then(r => r.json())
    .finally(() => { btn.disabled = false; });
}

function toggleFieldVisibility(id, btn) {
  const el = document.getElementById(id);
  const slash = btn.querySelector(".eye-slash");
  if (el.type === "password") {
    el.type = "text";
    if (slash) slash.style.display = "none";
  } else {
    el.type = "password";
    if (slash) slash.style.display = "";
  }
}

function consumeItem(type) {
  fetch("/consume", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({type}),
  });
}

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function loadLogFiles() {
  fetch("/logs/list")
    .then(r => r.json())
    .then(d => {
      const sel = document.getElementById("log-file-select");
      const files = d.files || [];
      sel.innerHTML = files.length
        ? files.map(f => `<option value="${escHtml(f)}">${escHtml(f)}</option>`).join("")
        : `<option value="">No logs</option>`;
      _logCurrentFile = files.length ? files[0] : "";
    })
    .catch(() => {});
}

let _logLiveMode = true;
let _logCurrentFile = "";

function onLogFileChange() {
  const sel = document.getElementById("log-file-select");
  _logCurrentFile = sel.value;
  if (!_logCurrentFile) return;
  // If the user picks the first (latest) file, restore live mode
  const isLatest = sel.selectedIndex === 0;
  _logLiveMode = isLatest;
  if (!isLatest) _loadLogFile(_logCurrentFile);
}

function openFullLog() {
  if (_logCurrentFile) {
    window.open("/logs/" + encodeURIComponent(_logCurrentFile), "_blank");
  } else {
    window.open("/logs", "_blank");
  }
}

function _loadLogFile(filename) {
  fetch("/logs/lines/" + encodeURIComponent(filename))
    .then(r => r.json())
    .then(d => {
      const box = document.getElementById("log-box");
      box.innerHTML = [...(d.lines || [])].reverse()
        .map(l => `<div class="log-line">${escHtml(l)}</div>`)
        .join("");
    })
    .catch(() => {});
}

loadLogFiles();

// ---------------------------------------------------------------------------
// Case Work
// ---------------------------------------------------------------------------

const CW_HOSPITAL_OCCUPATIONS = new Set(["Nurse", "Doctor", "Surgeon", "Hospital Director"]);
const CW_FIRE_OCCUPATIONS = new Set(["Volunteer Fire Fighter", "Fire Fighter", "Fire Chief"]);

function updateCaseWorkSection(occupation) {
  const isHospital = CW_HOSPITAL_OCCUPATIONS.has(occupation);
  const isFire = CW_FIRE_OCCUPATIONS.has(occupation);
  const hasWork = isHospital || isFire;

  document.getElementById("cw-none").style.display = hasWork ? "none" : "";
  document.getElementById("cw-hospital").style.display = isHospital ? "" : "none";
  document.getElementById("cw-fire").style.display = isFire ? "" : "none";

  const pills = document.getElementById("pills-s-casework");
  if (pills) {
    if (isHospital) {
      const interval = document.getElementById("hospital_poll_interval").value;
      pills.innerHTML = _pill("Hospital") + _pill(`${interval}s`);
    } else if (isFire) {
      const interval = document.getElementById("fire_poll_interval").value;
      pills.innerHTML = _pill("Fire") + _pill(`${interval}s`);
    } else {
      pills.innerHTML = "";
    }
  }
}

function _serializePriorityTable(tbodyId) {
  const rows = document.querySelectorAll(`#${tbodyId} tr`);
  const tasks = [];
  rows.forEach(row => {
    const type = row.dataset.type;
    if (!type) return;
    const targetSel = row.querySelector(".cw-select");
    const toggle = row.querySelector('input[type="checkbox"]');
    const task = { type };
    if (targetSel) task.target = targetSel.value;
    if (toggle) task.enabled = toggle.checked;
    tasks.push(task);
  });
  return tasks;
}

// Up/down reorder for priority tables
function _moveRow(btn, dir) {
  const row = btn.closest("tr");
  const tbody = row.parentElement;
  if (dir === -1) {
    const prev = row.previousElementSibling;
    if (prev) tbody.insertBefore(row, prev);
  } else {
    const next = row.nextElementSibling;
    if (next) tbody.insertBefore(next, row);
  }
  _renumberTable(tbody.id);
  autoSave();
}

function _renumberTable(tbodyId) {
  document.querySelectorAll(`#${tbodyId} tr`).forEach((row, i) => {
    const num = row.querySelector(".priority-num");
    if (num) num.textContent = i + 1;
  });
}
