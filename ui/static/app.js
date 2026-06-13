const EARN_MAP = {
  Secret:      [["whore","Whore"],["street_fight","Streetfight"],["joy_ride","Joyride"],["pimp","Pimp"]],
  General:     [["shoplift","Shoplift"],["steal_cheques","Steal Cheques"]],
  Hospital:    [["nurse","Nurse"],["doctor","Doctor"],["surgeon","Surgeon"],["hospital_director","Hospital Director"]],
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
  const section = btn.closest(".tabs-card") || btn.closest(".card");
  if (section) {
    section.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    section.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  }
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
    action_enabled: document.getElementById("action_enabled").checked,
    action_type: document.getElementById("action_type").value,
    action_sub: document.getElementById("action_sub").value,
    away_action_enabled: document.getElementById("action_enabled").checked,
    away_action_type: document.getElementById("away_action_type").value,
    fallback_to_away: document.getElementById("fallback_to_away").checked,
    payback_mode: document.getElementById("payback_mode").value,
    monitor_top_job: document.getElementById("monitor_top_job").checked,
    promo_thread_id: (document.getElementById("promo_thread_id") || {value:""}).value.trim(),
    jail_enabled: document.getElementById("jail_enabled").checked,
    jail_duty: document.getElementById("jail_duty").value,
    jail_action: document.getElementById("jail_action").value,
    jail_use_consumables: document.getElementById("jail_use_consumables").checked,
    headless: document.getElementById("headless").checked,
    logout_on_stop: document.getElementById("logout_on_stop").checked,
    relog_on_session_expire: document.getElementById("relog_on_session_expire").checked,
    min_cash_on_hand: parseInt(document.getElementById("min_cash_on_hand").value) || 0,
    char_history_enabled: document.getElementById("char_history_enabled").checked,
    char_history_interval: parseInt(document.getElementById("char_history_interval").value) || 30,
    case_work_enabled: document.getElementById("case_work_enabled").checked,
    hospital_poll_interval: parseInt(document.getElementById("hospital_poll_interval").value) || 31,
    fire_poll_interval: parseInt(document.getElementById("fire_poll_interval").value) || 31,
    hospital_tasks: _serializePriorityTable("hospital-priority-body"),
    player_list_enabled: document.getElementById("player_list_enabled").checked,
    player_refresh_interval: parseInt(document.getElementById("player_refresh_interval").value) || 30,
    consume_timer_limit: document.getElementById("consume_timer_limit").value || "00:00",
    auto_consume: document.getElementById("auto_consume").checked,
    auto_consumable: document.getElementById("auto_consumable").value,
    consumable_limit: parseInt(document.getElementById("consumable_limit").value) || 33,
    consumable_buffer: parseInt(document.getElementById("consumable_buffer").value) || 0,
    smart_consumables: document.getElementById("smart_consumables").checked,
    autobuy_enabled: (document.getElementById("autobuy_enabled") || {checked:false}).checked,
    autobuy_price_marijuana: parseInt((document.getElementById("autobuy_price_marijuana")||{value:0}).value)||0,
    autobuy_qty_marijuana:   parseInt((document.getElementById("autobuy_qty_marijuana")||{value:0}).value)||0,
    autobuy_price_ecstasy:   parseInt((document.getElementById("autobuy_price_ecstasy")||{value:0}).value)||0,
    autobuy_qty_ecstasy:     parseInt((document.getElementById("autobuy_qty_ecstasy")||{value:0}).value)||0,
    autobuy_price_acid:      parseInt((document.getElementById("autobuy_price_acid")||{value:0}).value)||0,
    autobuy_qty_acid:        parseInt((document.getElementById("autobuy_qty_acid")||{value:0}).value)||0,
    autobuy_price_speed:     parseInt((document.getElementById("autobuy_price_speed")||{value:0}).value)||0,
    autobuy_qty_speed:       parseInt((document.getElementById("autobuy_qty_speed")||{value:0}).value)||0,
    autobuy_price_pice:      parseInt((document.getElementById("autobuy_price_pice")||{value:0}).value)||0,
    autobuy_qty_pice:        parseInt((document.getElementById("autobuy_qty_pice")||{value:0}).value)||0,
    autobuy_price_heroin:    parseInt((document.getElementById("autobuy_price_heroin")||{value:0}).value)||0,
    autobuy_qty_heroin:      parseInt((document.getElementById("autobuy_qty_heroin")||{value:0}).value)||0,
    autobuy_price_cocaine:   parseInt((document.getElementById("autobuy_price_cocaine")||{value:0}).value)||0,
    autobuy_qty_cocaine:     parseInt((document.getElementById("autobuy_qty_cocaine")||{value:0}).value)||0,
    gym_enabled:    (document.getElementById("gym_enabled")||{checked:false}).checked,
    gym_activity:   (document.getElementById("gym_activity")||{value:"weights"}).value,
    gym_auto_travel:(document.getElementById("gym_auto_travel")||{checked:false}).checked,
  };

  return fetch("/save", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data),
  }).then(r => r.json());
}

function autoSave() {
  _doSave();
  _updateIncomePills();
  _updateIncomeTabColors();
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

function autobuyMarkDirty() {
  const btn = document.getElementById("save-autobuy");
  if (btn) btn.classList.add("needed");
}

function autobuyS() {
  _doSave().then(() => {
    const btn = document.getElementById("save-autobuy");
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
  const el = document.getElementById("pills-income-crimes");
  if (!el) return;
  const enabled = document.getElementById("crimes_enabled")?.checked;
  if (!enabled) { el.innerHTML = _pill("Aggravated Crimes: Disabled"); return; }
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
  const el = document.getElementById("pills-income-earns");
  if (!el) return;
  const enabled = document.getElementById("earns_enabled")?.checked;
  if (!enabled) { el.innerHTML = _pill("Earns: Disabled"); return; }
  const label = _selText("earn_type");
  el.innerHTML = label ? _pill(label) : "";
}

function _updateActionsPills() {
  const el = document.getElementById("pills-income-actions");
  if (!el) return;
  const enabled = document.getElementById("action_enabled")?.checked;
  if (!enabled) { el.innerHTML = _pill("Actions: Disabled"); return; }
  el.innerHTML = _pill(_selText("action_type")) + _pill(_selText("away_action_type"));
}

function _updateIncomePills() {
  _updateEarnsPills();
  _updateCrimePills();
  _updateActionsPills();
}

function _updateIncomeTabColors() {
  const tabs = [
    ["income-tab-earns",   "earns_enabled"],
    ["income-tab-crimes",  "crimes_enabled"],
    ["income-tab-actions", "action_enabled"],
  ];
  tabs.forEach(([tabId, toggleId]) => {
    const tab = document.getElementById(tabId);
    const toggle = document.getElementById(toggleId);
    if (tab && toggle) tab.classList.toggle("tab-disabled", !toggle.checked);
  });
}

let _lastEnergy = null;

function _updateCharPills() {
  const el = document.getElementById("pills-s-character");
  if (!el) return;
  const pills = [];
  if (_lastEnergy != null) pills.push(_pill(`⚡ ${_lastEnergy}%`));
  const now = Date.now();
  if (_jailReleaseEndMs != null) {
    const secs = Math.max(0, Math.floor((_jailReleaseEndMs - now) / 1000));
    if (secs > 0) pills.push(_pill(`Release: ${_fmtCountdown(secs)}`));
  }
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
      document.getElementById("stat-next-rank").textContent = d.next_rank || "--";
      document.getElementById("stat-rank-progress").textContent = d.rank_progress != null ? d.rank_progress + "%" : "--";
      document.getElementById("stat-city").textContent = d.city || "--";
      document.getElementById("stat-home-city").textContent = d.home_city || "--";

      // Jail: show jail_rank in rank pill, hide occupation pill
      const rankLabel = document.getElementById("stat-rank-label");
      const occupationItem = document.getElementById("stat-occupation-item");
      if (d.in_jail) {
        document.getElementById("stat-rank").textContent = d.jail_rank || "--";
        if (rankLabel) rankLabel.textContent = "Jail Rank";
        if (occupationItem) occupationItem.style.display = "none";
      } else {
        document.getElementById("stat-rank").textContent = d.rank || "--";
        document.getElementById("stat-occupation").textContent = d.occupation || "--";
        if (rankLabel) rankLabel.textContent = "Rank";
        if (occupationItem) occupationItem.style.display = "";
      }
      document.getElementById("stat-health").textContent = d.health != null ? d.health + "%" : "--";
      document.getElementById("stat-energy").textContent = d.energy != null ? d.energy + "%" : "--";
      document.getElementById("stat-earns").textContent = d.earns_24h != null ? d.earns_24h : "--";
      document.getElementById("stat-cons-24h").textContent = d.consumables_24h != null ? d.consumables_24h : "--";

      const fmt = n => "$" + (n ?? 0).toLocaleString();
      document.getElementById("stat-clean").textContent = d.clean_money != null ? fmt(d.clean_money) : "--";
      document.getElementById("stat-dirty").textContent = d.dirty_money != null ? fmt(d.dirty_money) : "--";
      document.getElementById("stat-bank").textContent = d.bank_balance ? fmt(d.bank_balance) : "--";

      // Jail badge and status card tint
      const jailBadge = document.getElementById("stat-jail-badge");
      const statusCard = document.getElementById("s-character");
      const clearQueueBtn = document.getElementById("jail-clear-queue-btn");
      if (d.in_jail) {
        if (jailBadge) jailBadge.style.display = "";
        if (statusCard) statusCard.classList.add("in-jail");
        if (clearQueueBtn) clearQueueBtn.disabled = false;
      } else {
        if (jailBadge) jailBadge.style.display = "none";
        if (statusCard) statusCard.classList.remove("in-jail");
        if (clearQueueBtn) clearQueueBtn.disabled = true;
      }

      // Consumables — show jail consumables if in jail, normal consumables otherwise
      if (d.in_jail) {
        const jcons = d.jail_consumables || {};
        const JAIL_CONS_LABELS = { cigarettes: "Cigarettes", booze: "Booze", porn: "Porn", shanks: "Shanks" };
        document.getElementById("stat-consumables").innerHTML =
          Object.entries(JAIL_CONS_LABELS).filter(([k]) => (jcons[k] ?? 0) > 0).map(([k, label]) =>
            `<div class="consumable-item"><span class="consumable-name">${label}</span><span class="consumable-qty">${jcons[k]}</span></div>`
          ).join("") || '<span class="placeholder">No jail consumables</span>';
      } else {
        const cons = d.consumables || {};
        document.getElementById("stat-consumables").innerHTML =
          Object.entries(CONSUMABLE_LABELS).filter(([k]) => (cons[k] ?? 0) > 0).map(([k, label]) =>
            `<div class="consumable-item"><span class="consumable-name">${label}</span><span class="consumable-qty ${_botRunning ? 'consumable-link' : ''}" onclick="${_botRunning ? `consumeItem('${k}')` : ''}">${cons[k]}</span></div>`
          ).join("") || '<span class="placeholder">No consumables</span>';
      }

      // Timers
      _lastEnergy = d.energy;
      updateTimers(d.timers || {}, d.server_time, d.agg_pro_active, d.in_jail ? d.jail_release_secs : null, d.flight_departs_at || null, d.hospital_release_at || null);
      _updateCharPills();

      // Show check-for-updates row only when running inside a git repo
      const updateRow = document.getElementById("update-row");
      if (updateRow) updateRow.style.display = d.is_git_repo ? "" : "none";

      // Gym timer
      const gymTimerEl = document.getElementById("gym-timer");
      if (gymTimerEl) {
        if (d.last_gym_use && d.last_gym_use > 0) {
          const nextGym = d.last_gym_use + 12 * 3600;
          const secsLeft = Math.round(nextGym - Date.now() / 1000);
          if (secsLeft <= 0) {
            gymTimerEl.textContent = "Ready";
          } else {
            const h = Math.floor(secsLeft / 3600);
            const m = Math.floor((secsLeft % 3600) / 60);
            const s = secsLeft % 60;
            gymTimerEl.textContent = h + "h " + String(m).padStart(2,"0") + "m " + String(s).padStart(2,"0") + "s";
          }
        } else {
          gymTimerEl.textContent = "Ready";
        }
      }

      // Case work auto-detect
      updateCaseWorkSection(d.occupation || "");

      // Journals live feed — refresh when journals_updated_at advances.
      // Avoids the race where has_new_journals clears before the next poll.
      if ((d.journals_updated_at || 0) > _cjLastUpdated) {
        _cjLastUpdated = d.journals_updated_at;
        const journalsTab = document.getElementById("cj-journals");
        if (journalsTab && journalsTab.classList.contains("active")) {
          cjRefreshData();
        }
      }

      // Character history live reload — refresh when char_history_updated_at advances
      if ((d.char_history_updated_at || 0) > _chLastUpdated) {
        _chLastUpdated = d.char_history_updated_at;
        if (document.getElementById("s-char-history") &&
            document.getElementById("s-char-history").style.display !== "none") {
          loadCharHistory();
        }
      }

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
let _jailReleaseEndMs = null;
let _flightDepartsAtMs = null;
let _hospitalReleaseAtMs = null;

function updateTimers(timers, serverTimeStr, aggProActive, jailReleaseSecs, flightDepartsAt, hospitalReleaseAt) {
  _aggProActive = aggProActive;

  // Jail release timer — re-anchor on every poll since it's a raw seconds value
  if (jailReleaseSecs != null && jailReleaseSecs > 0) {
    _jailReleaseEndMs = Date.now() + jailReleaseSecs * 1000;
  } else if (jailReleaseSecs == null) {
    _jailReleaseEndMs = null;
  }

  // Flight timer — flightDepartsAt is a Unix timestamp from the server
  if (flightDepartsAt != null) {
    const msLeft = flightDepartsAt * 1000 - Date.now();
    if (msLeft > 0) {
      _flightDepartsAtMs = flightDepartsAt * 1000;
    } else {
      _flightDepartsAtMs = null;
    }
  } else {
    _flightDepartsAtMs = null;
  }

  // Hospital release timer — hospitalReleaseAt is a Unix timestamp from the server
  if (hospitalReleaseAt != null) {
    const msLeft = hospitalReleaseAt * 1000 - Date.now();
    if (msLeft > 0) {
      _hospitalReleaseAtMs = hospitalReleaseAt * 1000;
    } else {
      _hospitalReleaseAtMs = null;
    }
  } else {
    _hospitalReleaseAtMs = null;
  }

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
  if ((Object.keys(_activeTimers).length > 0 || _jailReleaseEndMs != null || _flightDepartsAtMs != null || _hospitalReleaseAtMs != null) && !_timerInterval) {
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
  // Clear flight timer once it passes
  if (_flightDepartsAtMs != null && Date.now() >= _flightDepartsAtMs) {
    _flightDepartsAtMs = null;
  }
  // Clear hospital timer once it passes
  if (_hospitalReleaseAtMs != null && Date.now() >= _hospitalReleaseAtMs) {
    _hospitalReleaseAtMs = null;
  }
  _renderTimers();
  _updateCharPills();
  // Keep interval running as long as there are countdown timers, AggPro, jail release, flight, or hospital
  const countdownKeys = Object.keys(_activeTimers).filter(k => k !== "aggpro");
  if (countdownKeys.length === 0 && !_aggProActive && _jailReleaseEndMs == null && _flightDepartsAtMs == null && _hospitalReleaseAtMs == null) {
    clearInterval(_timerInterval);
    _timerInterval = null;
  }
}

function _renderTimers() {
  const grid = document.getElementById("stat-timers-grid");
  const now = Date.now();
  const tiles = [];

  // Jail release countdown — shown first while in jail
  if (_jailReleaseEndMs != null) {
    const secs = Math.max(0, Math.floor((_jailReleaseEndMs - now) / 1000));
    tiles.push(`<div class="stat-item stat-item-timer"><span class="stat-label">Release</span><span class="stat-value stat-timer-value">${_fmtCountdown(secs)}</span></div>`);
  }

  // Flight departure countdown
  if (_flightDepartsAtMs != null) {
    const secs = Math.max(0, Math.floor((_flightDepartsAtMs - now) / 1000));
    tiles.push(`<div class="stat-item stat-item-timer"><span class="stat-label">Flight</span><span class="stat-value stat-timer-value">${_fmtCountdown(secs)}</span></div>`);
  }

  // Hospital release countdown
  if (_hospitalReleaseAtMs != null) {
    const secs = Math.max(0, Math.floor((_hospitalReleaseAtMs - now) / 1000));
    tiles.push(`<div class="stat-item stat-item-timer"><span class="stat-label">Hospital</span><span class="stat-value stat-timer-value">${_fmtCountdown(secs)}</span></div>`);
  }

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
  window.open("/page_snapshot", "_blank");
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

function checkForUpdates() {
  const btn = document.getElementById("check-update-btn");
  btn.disabled = true;
  btn.textContent = "Checking…";
  fetch("/check_update")
    .then(r => r.json())
    .then(d => {
      if (d.error) { alert("Update check failed: " + d.error); return; }
      if (d.up_to_date) { alert("You are up to date."); return; }
      const modal = document.getElementById("update-modal");
      document.getElementById("update-modal-title").textContent =
        `Update Available (${d.commits_behind} commit${d.commits_behind !== 1 ? "s" : ""} behind)`;
      document.getElementById("update-modal-body").textContent = d.log || "";
      modal.style.display = "flex";
    })
    .catch(() => alert("Could not reach server."))
    .finally(() => { btn.disabled = false; btn.textContent = "Check for Updates"; });
}

function applyUpdate() {
  const applyBtn = document.getElementById("apply-update-btn");
  applyBtn.disabled = true;
  applyBtn.textContent = "Installing…";
  fetch("/apply_update", {method: "POST"})
    .then(r => r.json())
    .then(d => {
      document.getElementById("update-modal").style.display = "none";
      if (d.error) { alert("Update failed: " + d.error); return; }
      if (confirm("Update applied. Restart now?\n\n" + (d.output || ""))) {
        restartBot();
      }
    })
    .catch(() => alert("Could not reach server."))
    .finally(() => { applyBtn.disabled = false; applyBtn.textContent = "Install Update"; });
}

function restartBot() {
  const btn = document.getElementById("restart-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Restarting…"; }
  fetch("/restart", {method: "POST"})
    .then(() => _pollUntilBack())
    .catch(() => _pollUntilBack());
}

function _pollUntilBack() {
  const MAX = 60;
  let attempts = 0;
  const interval = setInterval(() => {
    attempts++;
    fetch("/status")
      .then(r => { if (r.ok) { clearInterval(interval); location.reload(); } })
      .catch(() => {});
    if (attempts >= MAX) {
      clearInterval(interval);
      const btn = document.getElementById("restart-btn");
      if (btn) { btn.disabled = false; btn.textContent = "Restart"; }
      alert("Server did not come back after 60 seconds.");
    }
  }, 1000);
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

function findThreadId() {
  const overlay = document.getElementById("thread-overlay");
  const content = document.getElementById("thread-overlay-content");
  overlay.style.display = "flex";
  content.innerHTML = "<p style='color:#888;'>Loading…</p>";
  fetch("/promo/bar_threads")
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        content.innerHTML = `<p style='color:#f38ba8;'>${data.error}</p>`;
        return;
      }
      const threads = data.threads || [];
      if (!threads.length) {
        content.innerHTML = "<p style='color:#888;'>No threads found.</p>";
        return;
      }
      content.innerHTML = threads.map(t =>
        `<div class="thread-option" onclick="selectThread('${t.id}')" style="padding:8px 10px;cursor:pointer;border-radius:5px;margin-bottom:4px;background:#313244;color:#cdd6f4;">${t.title} <span style='color:#888;font-size:.85em'>#${t.id}</span></div>`
      ).join("");
    })
    .catch(() => {
      content.innerHTML = "<p style='color:#f38ba8;'>Failed to fetch threads.</p>";
    });
}

function selectThread(id) {
  const input = document.getElementById("promo_thread_id");
  if (input) { input.value = id; autoSave(); }
  closeThreadOverlay();
}

function closeThreadOverlay(event) {
  if (event && event.target !== document.getElementById("thread-overlay")) return;
  const overlay = document.getElementById("thread-overlay");
  overlay.style.opacity = "1";
  let op = 1;
  const fade = setInterval(() => {
    op -= 0.1;
    overlay.style.opacity = op;
    if (op <= 0) { clearInterval(fade); overlay.style.display = "none"; overlay.style.opacity = "1"; }
  }, 20);
}

// ── Cash overlay ──────────────────────────────────────────────────────────────

let _cashOpenedAt = 0;

function openCashOverlay() {
  _cashOpenedAt = Date.now();
  document.getElementById("cash-step-action").style.display = "";
  document.getElementById("cash-step-withdraw").style.display = "none";
  document.getElementById("cash-custom-input").style.display = "none";
  document.getElementById("cash-custom-input").value = "";
  document.querySelectorAll("input[name='wamt']").forEach(r => r.checked = false);
  const ov = document.getElementById("cash-overlay");
  ov.style.display = "flex";
}

function closeCashOverlay(event) {
  if (event && event.target !== document.getElementById("cash-overlay")) return;
  if (Date.now() - _cashOpenedAt < 300) return; // ignore tap-delay ghost click on iOS
  document.getElementById("cash-overlay").style.display = "none";
}

function cashDoDeposit() {
  document.getElementById("cash-overlay").style.display = "none";
  fetch("/deposit", { method: "POST" })
    .then(r => r.json())
    .then(d => { if (d.error) alert(d.error); });
}

function cashShowWithdraw() {
  document.getElementById("cash-step-action").style.display = "none";
  document.getElementById("cash-step-withdraw").style.display = "";
}

function cashToggleCustom(radio) {
  const inp = document.getElementById("cash-custom-input");
  inp.style.display = radio.checked && radio.value === "x" ? "" : "none";
  if (inp.style.display !== "none") inp.focus();
}

function cashSubmitWithdraw() {
  const selected = document.querySelector("input[name='wamt']:checked");
  if (!selected) return;
  let amount;
  if (selected.value === "x") {
    amount = parseInt(document.getElementById("cash-custom-input").value, 10);
    if (!amount || amount <= 0) return;
  } else {
    amount = parseInt(selected.value, 10);
  }
  document.getElementById("cash-overlay").style.display = "none";
  fetch("/withdraw", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({amount}),
  }).then(r => r.json()).then(d => { if (d.error) alert(d.error); });
}

function requestWithdraw() {
  const raw = prompt("Withdraw amount ($):");
  if (!raw) return;
  const amount = parseInt(raw.replace(/[^0-9]/g, ""), 10);
  if (!amount || amount <= 0) return;
  fetch("/withdraw", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({amount}),
  }).then(r => r.json()).then(d => { if (d.error) alert(d.error); });
}

// ── Tasks ─────────────────────────────────────────────────────────────────────

function onTaskChange() {
  const val = document.getElementById("task-selector").value;
  document.querySelectorAll(".task-panel").forEach(p => p.style.display = "none");
  if (val === "travel") {
    document.getElementById("task-travel").style.display = "";
    onTravelMethodChange();
  }
  if (val === "jailbreak") {
    document.getElementById("task-jailbreak").style.display = "";
    loadJbPopulation();
  }
  if (val === "archive-journals") {
    document.getElementById("task-archive-journals").style.display = "";
  }
  if (val === "warrants") {
    document.getElementById("task-warrants").style.display = "";
  }
}

// ── Travel ────────────────────────────────────────────────────────────────────

let _travelDests = [];

function onTravelMethodChange() {
  const method = document.getElementById("travel-method").value;
  const destSel = document.getElementById("travel-destination");
  destSel.innerHTML = '<option value="">— Loading... —</option>';
  document.getElementById("travel-dest-meta").textContent = "";
  document.getElementById("travel-error").style.display = "none";
  fetch("/tasks/travel_destinations?method=" + method)
    .then(r => r.json())
    .then(d => {
      if (d.error) {
        document.getElementById("travel-error").textContent = d.error;
        document.getElementById("travel-error").style.display = "";
        destSel.innerHTML = '<option value="">— Unavailable —</option>';
        return;
      }
      _travelDests = d.destinations || [];
      destSel.innerHTML = '<option value="">— Select destination —</option>' +
        _travelDests.map(o => `<option value="${escHtml(o.value)}">${escHtml(o.label)}</option>`).join("");
      destSel.onchange = _onTravelDestChange;
      _onTravelDestChange();
    })
    .catch(() => {
      destSel.innerHTML = '<option value="">— Error —</option>';
    });
}

function _onTravelDestChange() {
  const val = document.getElementById("travel-destination").value;
  const dest = _travelDests.find(o => o.value === val);
  const meta = document.getElementById("travel-dest-meta");
  if (dest && dest.costs) {
    meta.textContent = dest.costs + (dest.minutes ? "  ·  " + dest.minutes + " min" : "");
  } else {
    meta.textContent = "";
  }
}

function submitTravel() {
  const method = document.getElementById("travel-method").value;
  const target = document.getElementById("travel-destination").value;
  const errEl = document.getElementById("travel-error");
  errEl.style.display = "none";
  if (!target) { errEl.textContent = "Select a destination."; errEl.style.display = ""; return; }
  const btn = event.target;
  btn.disabled = true;
  fetch("/tasks/travel", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({target_city: target, method}),
  })
    .then(r => r.json())
    .then(d => {
      if (d.error) { errEl.textContent = d.error; errEl.style.display = ""; }
    })
    .catch(() => { errEl.textContent = "Request failed."; errEl.style.display = ""; })
    .finally(() => { btn.disabled = false; });
}

function checkWarrants() {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = "Checking...";
  const out = document.getElementById("warrants-result");
  out.innerHTML = "";
  fetch("/tasks/check_warrants", { method: "POST" })
    .then(r => r.json())
    .then(d => {
      if (d.error) { out.innerHTML = `<p class="task-hint-block" style="color:var(--red)">${escHtml(d.error)}</p>`; return; }
      const ws = d.warrants;
      if (!ws.length) { out.innerHTML = `<p class="task-hint-block">No active warrants.</p>`; return; }
      let html = `<div style="overflow-x:auto"><table class="warrant-table">
        <thead><tr>
          <th>Case #</th><th>Crime</th><th>Victim</th><th>Fine</th>
          <th>Jail Time</th><th>CS's</th><th>Defense</th><th></th>
        </tr></thead><tbody>`;
      for (const w of ws) {
        html += `<tr>
          <td>${escHtml(w.case_id)}</td>
          <td>${escHtml(w.crime)}</td>
          <td>${escHtml(w.victim)}</td>
          <td>${escHtml(w.fine)}</td>
          <td>${escHtml(w.jail_time)}</td>
          <td>${escHtml(w.css)}</td>
          <td>${escHtml(w.defense)}</td>
          <td><button class="btn-secondary" style="white-space:nowrap;padding:4px 10px" onclick="turnInWarrant(this,'${escHtml(w.turn_in_url)}','${escHtml(w.case_id)}')">Turn In</button></td>
        </tr>`;
      }
      html += `</tbody></table></div>`;
      out.innerHTML = html;
    })
    .catch(e => { out.innerHTML = `<p class="task-hint-block" style="color:var(--red)">${escHtml(String(e))}</p>`; })
    .finally(() => { btn.disabled = false; btn.textContent = "Check Warrants"; });
}

function turnInWarrant(btn, url, caseId) {
  btn.disabled = true;
  btn.textContent = "...";
  fetch("/tasks/turn_in_warrant", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, case_id: caseId }),
  })
    .then(r => r.json())
    .then(d => {
      if (d.error) { alert("Turn in failed: " + d.error); btn.disabled = false; btn.textContent = "Turn In"; return; }
      btn.textContent = "Queued";
    })
    .catch(e => { alert("Error: " + e); btn.disabled = false; btn.textContent = "Turn In"; });
}

function submitArchiveJournals(all) {
  const pages = all ? null : parseInt(document.getElementById("aj-pages").value, 10);
  if (!all && (!pages || pages < 1)) { alert("Enter a valid page count."); return; }
  fetch("/tasks/archive_journals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pages: all ? null : pages }),
  }).then(r => r.json()).then(d => {
    if (d.error) alert("Error: " + d.error);
    else alert("Archive task queued.");
  });
}

function onJbActionChange() {
  const val = document.getElementById("jb-action").value;
  ["jb-plan-form", "jb-execute-form", "jb-calloff-form"].forEach(id => {
    document.getElementById(id).style.display = "none";
  });
  if (val === "plan") document.getElementById("jb-plan-form").style.display = "";
  if (val === "execute") document.getElementById("jb-execute-form").style.display = "";
  if (val === "calloff") document.getElementById("jb-calloff-form").style.display = "";
}

function clearJailDutyQueue(e) {
  if (e) e.preventDefault();
  fetch("/clear_jail_duty_queue", { method: "POST" })
    .then(r => r.json())
    .then(d => { if (d.error) alert(d.error); });
}

function loadJbPopulation() {
  fetch("/tasks/online_population")
    .then(r => r.json())
    .then(d => {
      _populateSelect("jb-target", d.jail_inmates, "— Select target —");
      const partnerRow = document.getElementById("jb-partner-row");
      const partnerSel = document.getElementById("jb-partner");
      if (partnerSel) {
        partnerSel.innerHTML = `<option value="">— Select partner —</option>` +
          (d.partners || []).map(n => `<option value="${n}">${n}</option>`).join("") +
          `<option value="__other__">Other…</option>`;
      }
      partnerRow.style.display = "";
    });
}

function checkJailOffline() {
  const btn = document.getElementById("jb-check-btn");
  btn.textContent = "Checking…";
  btn.disabled = true;
  fetch("/tasks/jail_inmates_check")
    .then(r => r.json())
    .then(d => {
      btn.textContent = "Check Offline";
      btn.disabled = false;
      if (d.error) { alert(d.error); return; }
      _populateSelect("jb-target", d.inmates, "— Select target —");
    })
    .catch(() => { btn.textContent = "Check Offline"; btn.disabled = false; });
}

function _populateSelect(id, items, placeholder) {
  const sel = document.getElementById(id);
  if (!sel) return;
  sel.innerHTML = `<option value="">${placeholder}</option>` +
    items.map(n => `<option value="${n}">${n}</option>`).join("");
}

function _taskFeedback(feedbackId, msg, isError) {
  const el = document.getElementById(feedbackId);
  if (!el) return;
  el.textContent = msg;
  el.style.display = msg ? "" : "none";
  el.className = "task-feedback " + (isError ? "task-feedback-error" : "task-feedback-ok");
}

function onJbPartnerChange() {
  const sel = document.getElementById("jb-partner");
  const other = document.getElementById("jb-partner-other");
  if (!sel || !other) return;
  other.style.display = sel.value === "__other__" ? "" : "none";
}

function submitJbPlan() {
  const target = document.getElementById("jb-target").value;
  const partnerSel = document.getElementById("jb-partner");
  let partner = partnerSel ? partnerSel.value : "";
  if (partner === "__other__") {
    partner = (document.getElementById("jb-partner-other") || {}).value || "";
  }
  const hold = document.getElementById("jb-hold-timer").checked;
  if (!target) { alert("Please select a target."); return; }
  if (document.getElementById("jb-partner-row").style.display !== "none" && !partner) {
    alert("Please select or enter a partner."); return;
  }
  fetch("/tasks/jailbreak_plan", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({target, partner, hold_action_timer: hold}),
  }).then(r => r.json()).then(d => {
    if (d.error) alert(d.error);
  });
}

function submitJbExecute() {
  fetch("/tasks/jailbreak_execute", {method: "POST"})
    .then(r => r.json())
    .then(d => { if (d.error) alert(d.error); });
}

function submitJbCalloff() {
  fetch("/tasks/jailbreak_calloff", {method: "POST"})
    .then(r => r.json())
    .then(d => { if (d.error) alert(d.error); });
}

// ── Character History ────────────────────────────────────────────────────────

let _chData = null;
let _chReqs = null;

function toggleCharHistoryTab() {
  const enabled = document.getElementById("char_history_enabled").checked;
  const sec = document.getElementById("s-char-history");
  if (sec) sec.style.display = enabled ? "" : "none";
  if (enabled) loadCharHistory();
}

function refreshCharHistory() {
  fetch("/character_history/refresh", {method: "POST"})
    .then(r => r.json())
    .then(d => {
      if (d.error) { alert(d.error); return; }
      setTimeout(loadCharHistory, 3000);
    });
}

function loadCharHistory() {
  Promise.all([
    fetch("/character_history").then(r => r.json()),
    fetch("/trait_requirements").then(r => r.json()),
  ]).then(([data, reqs]) => {
    _chData = data;
    _chReqs = reqs;
    renderCharHistory(data, reqs);
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _isZero(val) {
  if (val === null || val === undefined) return true;
  const s = String(val).trim();
  // "0", "$0", "0/0", "0 successful out of 0" all count as zero
  return /^[\$\s]*0[\s,]*$/.test(s) || /^0\s+successful\s+out\s+of\s+0$/.test(s);
}

function _hzKey(title) {
  return "ch-hz-" + title.replace(/[^a-zA-Z0-9]/g, "_");
}

function _isHideZeros(title) {
  const stored = localStorage.getItem(_hzKey(title));
  return stored === null ? true : stored === "true";
}

function _setHideZeros(title, val) {
  localStorage.setItem(_hzKey(title), val ? "true" : "false");
}

function toggleHideZeros(title) {
  _setHideZeros(title, !_isHideZeros(title));
  reRenderCharHistory();
}

function _fmtVal(val) {
  if (typeof val === "string" && val.startsWith("$")) {
    return `<span class="ch-money">${val}</span>`;
  }
  return val;
}

// ── Section builders ──────────────────────────────────────────────────────────

function _buildStatSection(sec) {
  const hideZeros = _isHideZeros(sec.title);
  const rows = hideZeros ? sec.rows.filter(r => !_isZero(r.value)) : sec.rows;
  const toggle = _hzToggle(sec.title, hideZeros);
  if (!rows.length && hideZeros) return `<div class="ch-section ch-section-empty">
    <div class="ch-section-head"><span class="ch-section-title">${sec.title}</span>${toggle}</div>
    <p class="ch-empty-note">All values zero</p></div>`;

  let html = `<div class="ch-section">
    <div class="ch-section-head"><span class="ch-section-title">${sec.title}</span>${toggle}</div>
    <table class="ch-table">`;
  for (const row of rows) {
    html += `<tr><td class="ch-key">${row.key}</td><td class="ch-val">${_fmtVal(row.value)}</td></tr>`;
  }
  return html + "</table></div>";
}

function _hzToggle(title, hideZeros) {
  const checked = hideZeros ? "checked" : "";
  const escaped = title.replace(/'/g, "\\'");
  return `<label class="toggle-label ch-hz-toggle" title="Hide zero values">
    <input type="checkbox" ${checked} onchange="toggleHideZeros('${escaped}')">
    <span class="toggle"></span>
  </label>`;
}

function reRenderCharHistory() {
  if (_chData) renderCharHistory(_chData, _chReqs);
}

const _AGG_CRIME_KEYS = new Set([
  "Pickpocketing", "Muggings", "GTAs", "Break & Enters",
  "Torches", "Armed Robberies", "Bank Robberies", "Hacking",
]);

function _buildCrimesSection(sec) {
  const hideZeros = _isHideZeros(sec.title);
  const toggle = _hzToggle(sec.title, hideZeros);
  const rows = hideZeros ? sec.rows.filter(r => !_isZero(r.value)) : sec.rows;

  let aggTotal = 0;
  for (const r of sec.rows) {
    if (_AGG_CRIME_KEYS.has(r.key)) {
      const n = parseInt(String(r.value).replace(/,/g, ""), 10);
      if (!isNaN(n)) aggTotal += n;
    }
  }

  if (!rows.length && hideZeros) return `<div class="ch-section ch-section-empty">
    <div class="ch-section-head"><span class="ch-section-title">${sec.title}</span>${toggle}</div>
    <p class="ch-empty-note">All values zero</p></div>`;

  let html = `<div class="ch-section">
    <div class="ch-section-head"><span class="ch-section-title">${sec.title}</span>${toggle}</div>
    <table class="ch-table">`;
  for (const row of rows) {
    html += `<tr><td class="ch-key">${row.key}</td><td class="ch-val">${_fmtVal(row.value)}</td></tr>`;
  }
  html += `<tr style="border-top:1px solid var(--border)"><td class="ch-key" style="font-weight:600">Total Aggravated</td><td class="ch-val" style="font-weight:600">${aggTotal.toLocaleString()}</td></tr>`;
  return html + "</table></div>";
}

// ── Main render ───────────────────────────────────────────────────────────────

function renderCharHistory(data, reqs) {
  const body = document.getElementById("char-history-body");
  const updEl = document.getElementById("char-history-updated");
  if (!data || !data.stat_sections) {
    body.innerHTML = "<p style='color:#888;font-size:0.9rem;'>No data yet. Enable Character History and start the bot to fetch stats.</p>";
    return;
  }

  updEl.textContent = data.last_updated ? "Updated: " + data.last_updated : "";

  const byTitle = {};
  for (const sec of (data.stat_sections || [])) byTitle[sec.title] = sec;

  let html = "";

  // ── Stat sections ─────────────────────────────────────────────────────────
  const SECTION_ORDER = [
    "Character Information",
    "Crimes Committed", "Gambling",
    "Whacking Info",
    // Career sections — show all, each gets hide-zeros
    "Mayor", "Funeral Work", "Banking Work", "Customs Work",
    "Medical Work", "Law Work", "Police Work", "Engineering", "Fire Fighter",
  ];

  // Two-column grid for sections
  const secs = SECTION_ORDER.map(t => byTitle[t]).filter(Boolean);
  html += `<div class="ch-grid">`;
  for (const sec of secs) {
    const built = sec.title === "Crimes Committed" ? _buildCrimesSection(sec) : _buildStatSection(sec);
    html += `<div class="ch-grid-item">${built}</div>`;
  }
  html += `</div>`;

  // ── Earn History ──────────────────────────────────────────────────────────
  if (data.earn_history && data.earn_history.length) {
    const hideZeros = _isHideZeros("earn_history");

    // Find max formatted count length across all entries for uniform pill width
    let maxCountLen = 1;
    for (const cat of data.earn_history) {
      for (const e of cat.entries) {
        maxCountLen = Math.max(maxCountLen, e.count.toLocaleString().length);
      }
    }
    const pillW = `${maxCountLen + 0.4}ch`;

    html += `<div class="ch-section ch-section-full">
      <div class="ch-section-head">
        <span class="ch-section-title">Earn History</span>
        ${_hzToggle("earn_history", hideZeros)}
      </div>
      <table class="ch-table ch-earn-table">`;
    for (const cat of data.earn_history) {
      const entries = hideZeros ? cat.entries.filter(e => e.count > 0) : cat.entries;
      if (!entries.length) continue;
      html += `<tr>
        <td class="ch-earn-cat">${cat.category}</td>
        <td class="ch-earn-entries">`;
      for (const e of entries) {
        html += `<span class="ch-earn-item"><span class="ch-earn-label">${e.type}</span><span class="ch-earn-count" style="min-width:${pillW}">${e.count.toLocaleString()}</span></span>`;
      }
      html += `</td></tr>`;
    }
    html += `</table></div>`;
  }

  // ── Promotion History ─────────────────────────────────────────────────────
  if (data.promotion_history && data.promotion_history.length) {
    html += `<div class="ch-section ch-section-full">
      <div class="ch-section-head"><span class="ch-section-title">Promotion History</span></div>
      <div class="ch-table-scroll"><table class="ch-table ch-promo-table">
        <thead><tr><th>City</th><th>Rank</th><th>Occupation</th><th>Date</th></tr></thead><tbody>`;
    for (const p of data.promotion_history) {
      html += `<tr><td>${p.city}</td><td>${p.rank}</td><td>${p.occupation}</td><td class="ch-date">${p.date}</td></tr>`;
    }
    html += `</tbody></table></div></div>`;
  }

  // ── Skills & Traits (unlocked only, single column) ────────────────────────
  const _HIDDEN_SKILLS = new Set(["Throw Snowball", "Diligent Worker", "Bloodlust"]);
  const allUnlocked = (data.skills_traits || []).filter(s =>
    !_HIDDEN_SKILLS.has(s.name) && (s.status === "Unlocked" || s.status === "Active")
  );
  const lockedTraits = (data.skills_traits || []).filter(s =>
    !_HIDDEN_SKILLS.has(s.name) &&
    s.status !== "Unlocked" && s.status !== "Active" &&
    s.type === "Trait"
  );
  const lockedSkills = (data.skills_traits || []).filter(s =>
    !_HIDDEN_SKILLS.has(s.name) &&
    s.status !== "Unlocked" && s.status !== "Active" &&
    s.type === "Skill"
  );

  if (allUnlocked.length || lockedTraits.length || lockedSkills.length) {
    html += `<div class="ch-section ch-section-full">
      <div class="ch-section-head"><span class="ch-section-title">Skills &amp; Traits</span>`;
    if (lockedTraits.length || lockedSkills.length) {
      html += `<button class="ch-locked-btn" onclick="toggleLockedTraits()">Show Locked</button>`;
    }
    html += `</div>`;

    // Unlocked — single column list
    if (allUnlocked.length) {
      html += `<ul class="ch-unlocked-list">`;
      for (const s of allUnlocked) {
        const rankStr = s.max_rank > 1 ? ` <span class="ch-rank-badge">${s.rank}/${s.max_rank}</span>` : "";
        html += `<li class="ch-unlocked-item">
          <span class="ch-st-type">${s.type}</span>
          <span class="ch-st-name">${s.name}</span>${rankStr}
        </li>`;
      }
      html += `</ul>`;
    } else {
      html += `<p class="ch-empty-note">No unlocked skills or traits yet.</p>`;
    }

    // Locked panel (hidden by default)
    html += `<div id="ch-locked-panel" style="display:none">`;
    html += `<div class="ch-locked-divider">Locked — not yet unlocked</div>`;
    const allLocked = [...lockedTraits, ...lockedSkills];
    for (const s of allLocked) {
      const reqData = reqs && reqs[s.name];
      const progress = reqData && reqData.progress && reqData.progress.length
        ? reqData.progress
        : null;
      const desc = reqData ? reqData.description : "";
      html += `<div class="ch-locked-item">
        <div class="ch-locked-row">
          <span class="ch-st-type">${s.type}</span>
          <span class="ch-locked-name">${s.name}</span>
          <span class="ch-rank-badge">${s.rank}/${s.max_rank}</span>
        </div>`;
      if (desc) html += `<div class="ch-locked-desc">${desc}</div>`;
      if (progress) {
        for (const p of progress) {
          const pct = p.pct;
          html += `<div class="ch-req">
            <div class="ch-req-label">${p.label} <span class="ch-req-counts">${p.current.toLocaleString()} / ${p.target.toLocaleString()}</span></div>
            <div class="ch-req-bar"><div class="ch-req-fill" style="width:${pct}%"></div></div>
          </div>`;
        }
      } else if (reqData && reqData.progress !== undefined) {
        html += `<div class="ch-locked-desc ch-req-unknown">Requirements not yet configured.</div>`;
      }
      html += `</div>`;
    }
    html += `</div>`; // #ch-locked-panel
    html += `</div>`; // .ch-section
  }

  body.innerHTML = html;
}

function toggleLockedTraits() {
  const panel = document.getElementById("ch-locked-panel");
  if (!panel) return;
  const btn = document.querySelector(".ch-locked-btn");
  const hidden = panel.style.display === "none";
  panel.style.display = hidden ? "" : "none";
  if (btn) btn.textContent = hidden ? "Hide Locked" : "Show Locked";
}

// ── Communications & Journals ────────────────────────────────────────────────

let _cjData = [];         // full sorted journal list
let _cjFiltered = [];     // after search filter
let _cjPage = 1;
let _cjLastUpdated = 0;   // last journals_updated_at seen from /status
let _chLastUpdated = 0;   // last char_history_updated_at seen from /status
const CJ_PAGE_SIZE = 10;

function cjInit() {
  fetch("/journals")
    .then(r => r.json())
    .then(data => {
      _cjData = Object.values(data).sort((a, b) => new Date(b.time) - new Date(a.time));
      _cjFiltered = _cjData;
      _cjPage = 1;
      cjRender();
    })
    .catch(() => {});
}

// Refresh underlying data without disturbing an active filter/view.
// Called when has_new_journals fires while the tab is open.
function cjRefreshData() {
  fetch("/journals")
    .then(r => r.json())
    .then(data => {
      _cjData = Object.values(data).sort((a, b) => new Date(b.time) - new Date(a.time));
      const q = (document.getElementById("cj-search").value || "").toLowerCase().trim();
      if (!q) {
        // No filter — update the visible list too
        _cjFiltered = _cjData;
        cjRender();
      }
      // Filter active — _cjData is updated silently.
      // cjSearch() will pick it up the moment the user clears the box.
    })
    .catch(() => {});
}

function cjSearch() {
  const q = (document.getElementById("cj-search").value || "").toLowerCase().trim();
  if (!q) {
    _cjFiltered = _cjData;
  } else {
    _cjFiltered = _cjData.filter(e =>
      (e.title || "").toLowerCase().includes(q) ||
      (e.text  || "").toLowerCase().includes(q) ||
      (e.time  || "").toLowerCase().includes(q)
    );
  }
  _cjPage = 1;
  cjRender();
}

function cjRender() {
  const list = document.getElementById("cj-list");
  const pager = document.getElementById("cj-pagination");
  const pagerTop = document.getElementById("cj-pagination-top");
  if (!list || !pager) return;

  if (_cjFiltered.length === 0) {
    list.innerHTML = '<p class="cj-empty">No journals found.</p>';
    pager.innerHTML = "";
    if (pagerTop) pagerTop.innerHTML = "";
    return;
  }

  const totalPages = Math.ceil(_cjFiltered.length / CJ_PAGE_SIZE);
  if (_cjPage > totalPages) _cjPage = totalPages;
  const start = (_cjPage - 1) * CJ_PAGE_SIZE;
  const slice = _cjFiltered.slice(start, start + CJ_PAGE_SIZE);

  list.innerHTML = slice.map(e => `
    <div class="cj-entry">
      <span class="cj-entry-title">${escHtml(e.title || "")}</span>
      <span class="cj-entry-time">${escHtml(e.time || "")}</span>
      <div class="cj-entry-text">${escHtml(e.text || "")}</div>
    </div>
  `).join("");

  // Pagination buttons
  let btns = "";
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) {
      btns += `<button onclick="cjGoPage(${i})" class="${i === _cjPage ? 'active' : ''}">${i}</button>`;
    }
  } else {
    const pages = new Set([1, totalPages, _cjPage, _cjPage - 1, _cjPage + 1].filter(p => p >= 1 && p <= totalPages));
    let prev = 0;
    [...pages].sort((a,b) => a-b).forEach(p => {
      if (prev && p - prev > 1) btns += `<button disabled>…</button>`;
      btns += `<button onclick="cjGoPage(${p})" class="${p === _cjPage ? 'active' : ''}">${p}</button>`;
      prev = p;
    });
  }
  pager.innerHTML = btns;
  if (pagerTop) pagerTop.innerHTML = btns;
}

function cjGoPage(n) {
  _cjPage = n;
  cjRender();
}
