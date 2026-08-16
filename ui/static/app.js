let _earnCatalog = [];

const ACTION_SUB_MAP = {
  community_service: [],  // bot always picks the highest tier automatically
  career_training: [
    ["fire","Fire Department"],
    ["customs","Customs"],
    ["police","Police"],
  ],
  university: [
    ["","All"],
    ["Business","Business"],
    ["Science","Science"],
    ["Medicine","Medicine"],
    ["Engineering","Engineering"],
    ["Law","Law"],
  ],
  training_centre: [
    ["Jui Jitsu","Jui Jitsu"],
    ["Muay Thai","Muay Thai"],
    ["Karate","Karate"],
    ["MMA","MMA"],
  ],
  drug_manufacturing: [],
};

function loadAvailableEarns() {
  const earnTypeSel = document.getElementById("earn_type");
  const currentType = earnTypeSel ? earnTypeSel.dataset.current || "" : "";
  fetch("/api/available_earns")
    .then(r => r.json())
    .then(opts => {
      _earnCatalog = opts;
      _populateEarnCategories(currentType);
    })
    .catch(() => {});
}

function _populateEarnCategories(selectedEarnType) {
  const catSel = document.getElementById("earn_category");
  if (!catSel) return;

  // Build ordered unique category list — only include categories with enabled earns
  const seen = new Set();
  const cats = [];
  _earnCatalog.forEach(e => {
    if (e.enabled === false) return;
    const cat = e.category || "Uncategorized";
    if (!seen.has(cat)) { seen.add(cat); cats.push(cat); }
  });

  // Determine which category the saved earn_type belongs to
  const entry = _earnCatalog.find(e => e.schedule_value === selectedEarnType);
  const selectedCat = entry ? (entry.category || "Uncategorized") : (cats[0] || "");

  catSel.innerHTML = cats.map(c =>
    `<option value="${c}"${c === selectedCat ? " selected" : ""}>${c}</option>`
  ).join("");

  _renderEarnSelect(selectedEarnType);
}

function _renderEarnSelect(selectedValue) {
  const catSel = document.getElementById("earn_category");
  const sel = document.getElementById("earn_type");
  if (!sel) return;
  const cat = catSel ? catSel.value : "";
  const items = _earnCatalog.filter(e => e.schedule_value && e.enabled !== false && (e.category || "Uncategorized") === cat);
  if (!items.length) {
    // Preserve current value so a failed/empty catalog load doesn't overwrite config
    const preserved = sel.dataset.current || sel.value || "";
    sel.innerHTML = preserved
      ? `<option value="${preserved}">${preserved}</option>`
      : '<option value="">— no earns in this category —</option>';
    _updateEarnsPills();
    return;
  }
  sel.innerHTML = items.map(e => {
    const style = e.available === false ? ' style="color:red"' : '';
    const selected = e.schedule_value === selectedValue ? " selected" : "";
    return `<option value="${e.schedule_value}"${selected}${style}>${e.label}</option>`;
  }).join("");
  _updateEarnsPills();
}

// ── Earn Planner ─────────────────────────────────────────────────────────────
let _earnPlannerLimits = {};   // {schedule_value: limit} — current save payload
let _earnPlannerData = null;   // last /api/earn_planner response

function loadEarnPlanner() {
  fetch("/api/earn_planner")
    .then(r => r.json())
    .then(d => {
      _earnPlannerData = d;
      _earnPlannerLimits = {};
      (d.earns || []).forEach(e => { _earnPlannerLimits[e.value] = e.limit; });
      const group = document.getElementById("earn-planner-group");
      if (group) group.style.display = d.available ? "" : "none";
      _renderEarnPlanner();
    })
    .catch(() => {});
}

function _renderEarnPlanner() {
  if (!_earnPlannerData) return;
  const d = _earnPlannerData;

  // Populate add-dropdown with mappable earns not already listed
  const addSel = document.getElementById("earn-planner-add-select");
  if (addSel) {
    const mappable = d.mappable || {};
    const listed = new Set(Object.keys(_earnPlannerLimits));
    const opts = Object.keys(mappable)
      .filter(v => !listed.has(v))
      .map(v => `<option value="${v}">${mappable[v]}</option>`)
      .join("");
    addSel.innerHTML = opts || '<option value="">— all earns listed —</option>';
  }

  // Render listed earns. Merge live completed counts from last fetch.
  const completedByValue = {};
  (d.earns || []).forEach(e => { completedByValue[e.value] = e.completed; });

  const listEl = document.getElementById("earn-planner-list");
  if (!listEl) return;

  const values = Object.keys(_earnPlannerLimits);
  if (!values.length) {
    listEl.innerHTML = '<p style="color:var(--muted);font-size:0.82rem">No limits set — every earn is unlimited.</p>';
    return;
  }

  const mappable = d.mappable || {};
  listEl.innerHTML = values.map(value => {
    const name = mappable[value] || value;
    const limit = _earnPlannerLimits[value];
    const completed = completedByValue[value] || 0;
    const isActive = value === d.active;
    const pct = limit > 0 ? Math.min(100, Math.round((completed / limit) * 100)) : 0;
    let barColor = "var(--accent,#89b4fa)";
    let warn = "";
    if (completed >= limit) { barColor = "var(--error,#f87171)"; warn = " ⛔ at cap"; }
    else if (pct >= 90)     { barColor = "var(--warn,#f59e0b)"; warn = " ⚠ near cap"; }
    return `<div class="earn-planner-row" style="padding:8px 0;border-top:1px solid var(--border)">
      <div style="display:flex;align-items:center;gap:8px">
        <span style="flex:1;font-weight:${isActive ? "600" : "400"}">${name}${isActive ? ' <span style="color:var(--accent);font-size:0.75rem">(active)</span>' : ""}</span>
        <span style="font-size:0.8rem;color:var(--muted)">${completed} done</span>
        <span style="color:var(--muted)">/</span>
        <input type="number" min="1" step="1" value="${limit}" style="width:80px"
          onchange="earnPlannerSetLimit('${value}', this.value)">
        <button type="button" class="pl-icon-btn pl-icon-btn-danger" title="Remove limit"
          onclick="earnPlannerRemove('${value}')">✕</button>
      </div>
      <div style="height:6px;background:var(--surface2,#1e2a3a);border-radius:3px;margin-top:5px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:${barColor}"></div>
      </div>
      <div style="font-size:0.75rem;color:var(--muted);margin-top:2px">${pct}%${warn}</div>
    </div>`;
  }).join("");
}

function earnPlannerAdd() {
  const sel = document.getElementById("earn-planner-add-select");
  const limitEl = document.getElementById("earn-planner-add-limit");
  if (!sel || !limitEl) return;
  const value = sel.value;
  const limit = parseInt(limitEl.value, 10);
  if (!value || !limit || limit < 1) return;
  _earnPlannerLimits[value] = limit;
  limitEl.value = "";
  _renderEarnPlanner();
  autoSave();
}

function earnPlannerSetLimit(value, raw) {
  const limit = parseInt(raw, 10);
  if (!limit || limit < 1) return;
  _earnPlannerLimits[value] = limit;
  _renderEarnPlanner();
  autoSave();
}

function earnPlannerRemove(value) {
  delete _earnPlannerLimits[value];
  _renderEarnPlanner();
  autoSave();
}

function populateActionSub(selectedValue) {
  const type = document.getElementById("action_type").value;
  const sel = document.getElementById("action_sub");
  const label = document.getElementById("action_sub_label");
  const opts = ACTION_SUB_MAP[type] || [];

  if (opts.length === 0) {
    label.style.visibility = "hidden";
    sel.innerHTML = "";
  } else {
    label.style.visibility = "visible";
    sel.innerHTML = opts.map(([v, l]) =>
      `<option value="${v}" ${v === selectedValue ? "selected" : ""}>${l}</option>`
    ).join("");
  }

  const ctOpts = document.getElementById("career_training_options");
  if (ctOpts) ctOpts.style.display = type === "career_training" ? "" : "none";

  const fbLabel = document.getElementById("action_fallback_label");
  if (fbLabel) {
    const show = type === "career_training" || type === "university" || type === "training_centre";
    fbLabel.style.display = show ? "" : "none";
  }
  updateActionWarnings();
}

const _CS_AWAY_ALLOWED_RANKS = new Set([
  "loan officer", "bank manager", "mortician", "undertaker", "funeral director",
  "doctor", "surgeon", "hospital director", "technician", "engineer",
  "chief engineer", "supervisor", "superintendent", "commissioner-general",
  "lawyer", "judge", "supreme court judge", "sergeant", "senior sergeant",
  "detective", "commissioner", "fire fighter", "fire chief", "mayor",
]);
const _CAREER_TRAINING_BLOCKED = new Set(["Customs", "Fire", "Police"]);

function updateActionWarnings() {
  const ctWarn = document.getElementById("career-training-warning");
  const csWarn = document.getElementById("cs-away-warning");
  if (ctWarn) {
    const actionType = document.getElementById("action_type")?.value;
    const occ = (_botState.occupation || "").toLowerCase();
    const blocked = actionType === "career_training" && _CAREER_TRAINING_BLOCKED.has(_careerGroup(_botState.occupation));
    ctWarn.style.display = blocked ? "" : "none";
  }
  if (csWarn) {
    const awayType = document.getElementById("away_action_type")?.value;
    const rank = (_botState.rank || "").toLowerCase();
    const occ = (_botState.occupation || "").toLowerCase();
    const eligible = _CS_AWAY_ALLOWED_RANKS.has(rank) || _CS_AWAY_ALLOWED_RANKS.has(occ);
    const blocked = awayType === "community_service" && !eligible;
    csWarn.style.display = blocked ? "" : "none";
  }
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

function _buildPayload() {
  return {
    email: document.getElementById("email").value,
    password: document.getElementById("password").value,
    pin_required: document.getElementById("pin_required").checked,
    ui_pin: document.getElementById("ui_pin").value,
    earns_enabled: document.getElementById("earns_enabled").checked,
    earn_mode: document.getElementById("earn_mode").value,
    earn_type: document.getElementById("earn_type").value,
    earn_planner_limits: {..._earnPlannerLimits},
    crimes_enabled: document.getElementById("crimes_enabled").checked,
    primary_crime: document.getElementById("primary_crime").value,
    primary_threshold: document.getElementById("primary_threshold").value,
    away_crime: document.getElementById("away_crime").value,
    away_threshold: document.getElementById("away_threshold").value,
    armed_agg_private: document.getElementById("armed_agg_private").checked,
    armed_agg_drug_house: document.getElementById("armed_agg_drug_house").checked,
    torch_private: document.getElementById("torch_private").checked,
    torch_payback_public: document.getElementById("torch_payback_public").value,
    torch_payback_private: document.getElementById("torch_payback_private").value,
    action_enabled: document.getElementById("action_enabled").checked,
    action_type: document.getElementById("action_type").value,
    action_sub: document.getElementById("action_sub").value,
    action_fallback: (document.getElementById("action_fallback")||{value:""}).value,
    career_training_stop_at_14: document.getElementById("career_training_stop_at_14")?.checked ?? false,
    away_action_enabled: document.getElementById("action_enabled").checked,
    away_action_type: document.getElementById("away_action_type").value,
    fallback_to_away: document.getElementById("fallback_to_away").checked,
    payback_mode: document.getElementById("payback_mode").value,
    monitor_top_job: document.getElementById("monitor_top_job").checked,
    promo_thread_id: (document.getElementById("promo_thread_id") || {value:""}).value.trim(),
    auto_promo_enabled: document.getElementById("auto_promo_enabled")?.checked ?? false,
    promo_choices: _collectPromoChoices(),
    crossroads_enabled: (document.getElementById("crossroads_enabled")||{checked:false}).checked,
    crossroads_selection: (document.getElementById("crossroads_selection")||{value:"current"}).value,
    war_mode_enabled: (document.getElementById("war_mode_enabled")||{checked:false}).checked,
    war_mode_skip_pin: (document.getElementById("war_mode_skip_pin")||{checked:false}).checked,
    jail_enabled: document.getElementById("jail_enabled").checked,
    jail_duty: document.getElementById("jail_duty").value,
    jail_action: document.getElementById("jail_action").value,
    jail_use_consumables: document.getElementById("jail_use_consumables").checked,
    auto_jail_time: document.getElementById("auto_jail_time")?.value ?? "off",
    use_warrants: document.getElementById("use_warrants")?.value === "true",
    auto_warrant_handling: document.getElementById("auto_warrant_handling")?.value ?? "none",
    auto_jail_partner: document.getElementById("auto_jail_partner")?.value ?? "",
    show_scheduler: (document.getElementById("show_scheduler")||{checked:false}).checked,
    debug_logging: (document.getElementById("debug_logging")||{checked:false}).checked,
    headless: document.getElementById("headless").checked,
    event_boss_enabled: (document.getElementById("event_boss_enabled")||{checked:false}).checked,
    logout_on_stop: document.getElementById("logout_on_stop").checked,
    relog_on_session_expire: document.getElementById("relog_on_session_expire").checked,
    min_cash_on_hand: parseInt(document.getElementById("min_cash_on_hand").value) || 0,
    char_history_enabled: document.getElementById("char_history_enabled").checked,
    char_history_interval: parseInt(document.getElementById("char_history_interval").value) || 30,
    laundering_enabled: (document.getElementById("laundering_enabled")||{checked:false}).checked,
    launder_amount: parseInt((document.getElementById("launder_amount")||{value:"0"}).value)||0,
    laundering_preferred_contacts: _getLaunderContacts(),
    case_work_enabled: document.getElementById("case_work_enabled").checked,
    hospital_poll_interval: parseInt(document.getElementById("hospital_poll_interval").value) || 31,
    fire_poll_interval: parseInt(document.getElementById("fire_poll_interval").value) || 31,
    banking_poll_interval: parseInt(document.getElementById("banking_poll_interval")?.value) || 60,
    hospital_tasks: _serializePriorityTable("hospital-priority-body"),
    engineering_tasks: _serializePriorityTable("engineering-priority-body"),
    player_list_enabled: document.getElementById("player_list_enabled").checked,
    player_refresh_interval: parseInt(document.getElementById("player_refresh_interval").value) || 30,
    player_whitelist_bolds: (document.getElementById("pl-bolds-toggle")||{checked:true}).checked,
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
    bionics_enabled: (document.getElementById("bionics_enabled")||{checked:false}).checked,
    bionics_wanted_items: ["arms","legs","eyes","brain","heart"].filter(i => (document.getElementById("bionics_want_"+i)||{checked:false}).checked),
    bionics_priority_order: _serializePriorityItems("bionics-priority-body"),
    bionics_interval_window: parseInt((document.getElementById("bionics_interval_window")||{value:5}).value)||5,
    bionics_interval_no_window: parseInt((document.getElementById("bionics_interval_no_window")||{value:16}).value)||16,
    bionics_use_time_window: (document.getElementById("bionics_use_time_window")||{checked:false}).checked,
    bionics_window_start: (document.getElementById("bionics_window_start")||{value:"00:00"}).value,
    bionics_window_end:   (document.getElementById("bionics_window_end")||{value:"23:59"}).value,
    bionics_auto_restock: (document.getElementById("bionics_auto_restock")||{checked:false}).checked,
    weapon_store_enabled: (document.getElementById("weapon_store_enabled")||{checked:false}).checked,
    weapon_store_wanted_items: _wsCheckedItems(),
    weapon_store_priority_order: _serializePriorityItems("weapon-store-priority-body"),
    weapon_store_interval_window: parseInt((document.getElementById("weapon_store_interval_window")||{value:5}).value)||5,
    weapon_store_interval_no_window: parseInt((document.getElementById("weapon_store_interval_no_window")||{value:16}).value)||16,
    weapon_store_use_time_window: (document.getElementById("weapon_store_use_time_window")||{checked:false}).checked,
    weapon_store_window_start: (document.getElementById("weapon_store_window_start")||{value:"00:00"}).value,
    weapon_store_window_end:   (document.getElementById("weapon_store_window_end")||{value:"23:59"}).value,
    weapon_store_auto_restock: (document.getElementById("weapon_store_auto_restock")||{checked:false}).checked,
    gym_enabled:    (document.getElementById("gym_enabled")||{checked:false}).checked,
    gym_activity:   (document.getElementById("gym_activity")||{value:"weights"}).value,
    gym_auto_travel:(document.getElementById("gym_auto_travel")||{checked:false}).checked,
    casino_enabled:     (document.getElementById("casino_enabled")||{checked:false}).checked,
    casino_activity:    (document.getElementById("casino_activity")||{value:"slots"}).value,
    casino_bet_amount:  parseInt((document.getElementById("casino_bet_amount")||{value:"100"}).value)||100,
    casino_auto_travel: (document.getElementById("casino_auto_travel")||{checked:false}).checked,
    banking_auto_invest_enabled: (document.getElementById("banking_auto_invest_enabled")||{checked:false}).checked,
    banking_investment_term: (document.getElementById("banking_investment_term")||{value:"3,2.25"}).value,
    banking_invest_amount: (document.getElementById("banking_invest_amount")||{value:0}).value,
    banking_auto_weed: (document.getElementById("banking_auto_weed")||{checked:false}).checked,
    banking_weed_queue_threshold: (document.getElementById("banking_weed_queue_threshold")||{value:5}).value,
    smart_travel_enabled:            (document.getElementById("smart_travel_enabled")||{checked:false}).checked,
    smart_travel_store_priority:     (document.getElementById("smart_travel_store_priority")||{value:"bionics"}).value,
    smart_travel_window_vs_activity: (document.getElementById("smart_travel_window_vs_activity")||{value:"windows"}).value,
    smart_travel_home:               (document.getElementById("smart_travel_home")||{value:"home_city"}).value,
    sync_enabled:       (document.getElementById("sync_enabled")||{checked:false}).checked,
    sync_server_url:    (document.getElementById("sync_server_url")||{value:""}).value.trim(),
    sync_interval:      parseInt((document.getElementById("sync_interval")||{value:"2"}).value)||2,
    sync_online_time:   (document.getElementById("sync_online_time")||{checked:true}).checked,
    sync_lists:         (document.getElementById("sync_lists")||{checked:true}).checked,
    sync_groups:        (document.getElementById("sync_groups")||{checked:true}).checked,
    skill_combat_medic_target: (document.getElementById("skill_combat_medic_target")||{value:""}).value,
    skill_biometric_virus_target: (document.getElementById("skill_biometric_virus_target")||{value:""}).value,
    skill_travel_expert_enabled: (document.getElementById("skill_travel_expert_enabled")||{checked:false}).checked,
    skill_travel_expert_target: (document.getElementById("skill_travel_expert_target")||{value:""}).value,
    skill_travel_expert_threshold: parseInt((document.getElementById("skill_travel_expert_threshold")||{value:"2"}).value)||2,
    skill_all_seeing_eye_enabled: (document.getElementById("skill_all_seeing_eye_enabled")||{checked:false}).checked,
    skill_all_seeing_eye_target: (document.getElementById("skill_all_seeing_eye_target")||{value:""}).value,
    skill_all_seeing_eye_group: (document.getElementById("skill_all_seeing_eye_group")||{value:""}).value,
    skill_news_editor_target: (document.getElementById("skill_news_editor_target")||{value:""}).value,
    skill_news_editor_title: (document.getElementById("skill_news_editor_title")||{value:""}).value,
    skill_news_editor_event: (document.getElementById("skill_news_editor_event")||{value:""}).value,
    ..._collectEventConsume(),
    ..._collectNotifSettings(),
  };
}

const _EVENT_ITEMS = ["Burger","Coffee","Egg","Fries","Lightning","Milk","Popcorn","Watermelon"];
function _collectEventConsume() {
  const o = {};
  _EVENT_ITEMS.forEach(n => {
    const el = document.getElementById("event_consume_" + n);
    o["event_consume_" + n] = el ? el.checked : false;
  });
  return o;
}

function toggleEventConsumeSettings() {
  const on = (document.getElementById("event_boss_enabled") || {checked:false}).checked;
  const el = document.getElementById("event-consume-settings");
  if (el) el.style.display = on ? "" : "none";
}

function toggleWarModeLink() {
  const on = (document.getElementById("war_mode_enabled") || {checked:false}).checked;
  const el = document.getElementById("war-mode-link-row");
  if (el) el.style.display = on ? "" : "none";
}

// Snapshot of the last config this tab synced with the server. Saves send only
// the fields that differ from it, so one tab can't clobber another tab's — or
// the bot's background — changes. `null` until the first baseline capture.
let _savedConfig = null;
let _knownSettingsRev = 0;
let _settingsRevInit = false;
let _foreignChangePending = false;

function _doSave() {
  const data = _buildPayload();
  const body = _savedConfig ? Object.assign({ _base: _savedConfig }, data) : data;
  return fetch("/save", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  }).then(r => r.json()).then(res => {
    _savedConfig = data;
    if (res && res.settings_rev != null) {
      _knownSettingsRev = Math.max(_knownSettingsRev, res.settings_rev);
    }
    return res;
  });
}

// ── Cross-tab settings sync (Option 3) ───────────────────────────────────────

function _onForeignSettingsChange() {
  if (_foreignChangePending) return;
  const ae = document.activeElement;
  const editing = ae && /^(INPUT|SELECT|TEXTAREA)$/.test(ae.tagName || "");
  // If the user isn't mid-edit, just re-sync by reloading; otherwise show a
  // non-destructive banner so we don't wipe an in-progress edit.
  if (!editing) { location.reload(); return; }
  _foreignChangePending = true;
  if (document.getElementById("settings-sync-banner")) return;
  const bar = document.createElement("div");
  bar.id = "settings-sync-banner";
  bar.className = "settings-sync-banner";
  bar.innerHTML =
    "Settings were changed in another window." +
    ' <button type="button" onclick="location.reload()">Reload</button>' +
    ' <button type="button" class="dismiss" onclick="this.parentNode.remove()">✕</button>';
  document.body.appendChild(bar);
}

function autoSave() {
  // Immediate save for checkboxes/selects.
  _doSave();
  _updateIncomePills();
  _updateIncomeTabColors();
}

// ── Debounced save (3s) for free-text/number inputs; also flushed on blur ─────

let _saveTimer = null;

function debouncedSave() {
  clearTimeout(_saveTimer);
  _saveTimer = setTimeout(flushSave, 3000);
}

function flushSave() {
  if (!_saveTimer) return;
  clearTimeout(_saveTimer);
  _saveTimer = null;
  _doSave().then(() => {
    document.querySelectorAll(".input-unsaved").forEach(el => el.classList.remove("input-unsaved"));
  });
  _updateIncomePills();
  _updateIncomeTabColors();
}

// Commit any pending edit as soon as the field loses focus.
document.addEventListener("focusout", () => { if (_saveTimer) flushSave(); });

function markCredsDirty() {
  document.getElementById("email").classList.add("input-unsaved");
  document.getElementById("password").classList.add("input-unsaved");
  debouncedSave();
}

function markNumDirty(el) {
  el.classList.add("input-unsaved");
  debouncedSave();
}

function autobuyMarkDirty() {
  debouncedSave();
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

    // Make the whole section header clickable to expand/collapse.
    const header = section.querySelector("h2");
    const cbtn = header && header.querySelector(".collapse-btn");
    if (header && cbtn) {
      const m = /toggleSection\('([^']+)'\)/.exec(cbtn.getAttribute("onclick") || "");
      const id = m ? m[1] : section.id;
      cbtn.style.pointerEvents = "none";  // clicks pass through to the header
      header.style.cursor = "pointer";
      header.addEventListener("click", (e) => {
        // Ignore clicks on interactive controls inside the header.
        if (e.target.closest("input, select, textarea, a, button:not(.collapse-btn)")) return;
        toggleSection(id);
      });
    }
  });
}

// ── Section pills ─────────────────────────────────────────────────────────────

function _pill(text) {
  return `<span class="pill">${escHtml(text)}</span>`;
}

function _selText(id) {
  const sel = document.getElementById(id);
  if (!sel || sel.selectedIndex < 0) return "";
  const opt = sel.options[sel.selectedIndex];
  return opt ? opt.text : "";
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
  const mode = document.getElementById("earn_mode")?.value || "auto";
  const label = _selText("earn_type");
  const suffix = mode === "manual" ? " (Manual)" : "";
  el.innerHTML = label ? _pill(label + suffix) : "";
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
    ["income-tab-earns",      "earns_enabled"],
    ["income-tab-crimes",     "crimes_enabled"],
    ["income-tab-actions",    "action_enabled"],
    ["income-tab-banking",    "banking_auto_invest_enabled"],
  ];
  tabs.forEach(([tabId, toggleId]) => {
    const tab = document.getElementById(tabId);
    const toggle = document.getElementById(toggleId);
    if (tab && toggle) tab.classList.toggle("tab-disabled", !toggle.checked);
  });
}

let _lastEnergy = null;
let _respectPct = null;

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

function openRespectOverlay() {
  const ov = document.getElementById("respect-overlay");
  if (ov) {
    document.getElementById("respect-overlay-pct").textContent = _respectPct != null ? _respectPct : "—";
    ov.style.display = "flex";
  }
}

function closeRespectOverlay() {
  const ov = document.getElementById("respect-overlay");
  if (ov) ov.style.display = "none";
}

// ---------------------------------------------------------------------------
// Weapon action overlay
// ---------------------------------------------------------------------------

function openWeaponOverlay(el) {
  const name = el.dataset.wname || "";
  const slot = el.dataset.wslot || "";
  const dur = el.dataset.wdur || "";
  const actions = JSON.parse(el.dataset.wactions || "[]");
  document.getElementById("weapon-overlay-title").textContent = name + (slot ? " (" + slot + ")" : "");
  const body = document.getElementById("weapon-overlay-body");
  body.innerHTML = dur ? `<span class="muted">${escHtml(dur)}</span>` : "";
  actions.forEach(a => {
    const btn = document.createElement("button");
    btn.className = "action-btn";
    btn.textContent = a.label;
    btn.onclick = () => { closeWeaponOverlay(); navigateTo(a.url); loadProfile(); };
    body.appendChild(btn);
  });
  document.getElementById("weapon-overlay").classList.add("active");
}
function closeWeaponOverlay() {
  document.getElementById("weapon-overlay").classList.remove("active");
}

function openVehicleOverlay(el) {
  const name = el.dataset.vname || "";
  const actions = JSON.parse(el.dataset.vactions || "[]");
  document.getElementById("vehicle-overlay-title").textContent = name;
  const body = document.getElementById("vehicle-overlay-body");
  body.innerHTML = "";
  actions.forEach(a => {
    const btn = document.createElement("button");
    btn.className = "action-btn";
    btn.textContent = a.label;
    btn.onclick = () => { closeVehicleOverlay(); navigateTo(a.url); loadProfile(); };
    body.appendChild(btn);
  });
  document.getElementById("vehicle-overlay").classList.add("active");
}
function closeVehicleOverlay() {
  document.getElementById("vehicle-overlay").classList.remove("active");
}

function openRepairOverlay(condition) {
  document.getElementById("repair-overlay-condition").textContent = condition || "Unknown";
  document.getElementById("repair-overlay").classList.add("active");
}
function closeRepairOverlay() {
  document.getElementById("repair-overlay").classList.remove("active");
}
function submitRepair() {
  closeRepairOverlay();
  fetch("/repair_vehicle", {method: "POST"})
    .then(r => r.json())
    .then(d => { if (d.error) alert(d.error); else loadProfile(); })
    .catch(e => alert(String(e)));
}

// ---------------------------------------------------------------------------
// Earn catalog overlay
// ---------------------------------------------------------------------------

const _EARN_CATEGORIES = [
  "Crime", "Hospital", "Engineering", "Bank", "Mortician", "Law",
  "Fire", "Police", "Gangster", "General", "Secret", "Uncategorized",
];

async function openEarnCatalog() {
  const ov = document.getElementById("earn-catalog-overlay");
  if (!ov) return;
  try {
    const res = await fetch("/earn_catalog");
    _earnCatalog = await res.json();
  } catch (e) {
    _earnCatalog = [];
  }
  _renderEarnCatalogRows();
  ov.style.display = "flex";
}

function closeEarnCatalog() {
  const ov = document.getElementById("earn-catalog-overlay");
  if (ov) ov.style.display = "none";
}

function showEarnCatalogTab(tab) {
  document.getElementById("earn-cat-panel-assign").style.display = tab === "assign" ? "" : "none";
  document.getElementById("earn-cat-panel-edit").style.display   = tab === "edit"   ? "" : "none";
  document.getElementById("earn-cat-tab-assign").classList.toggle("active", tab === "assign");
  document.getElementById("earn-cat-tab-edit").classList.toggle("active",   tab === "edit");
  if (tab === "edit") _renderEarnCategoryEditor();
}

function _earnCategoryList() {
  const seen = new Set(), cats = [];
  _earnCatalog.forEach(e => { const c = e.category || "Uncategorized"; if (!seen.has(c)) { seen.add(c); cats.push(c); } });
  return cats;
}

function _renderEarnCategoryEditor() {
  const container = document.getElementById("earn-cat-edit-list");
  if (!container) return;
  const cats = _earnCategoryList();
  container.innerHTML = cats.map(cat => `
    <div style="display:flex;gap:8px;align-items:center">
      <input type="text" value="${escHtml(cat)}" data-orig="${escHtml(cat)}" style="flex:1" oninput="this.dataset.dirty='1'">
      <button class="btn-secondary" onclick="applyEarnCategoryRename(this)">Rename</button>
      <button class="btn-danger" onclick="deleteEarnCategory('${escHtml(cat)}')" title="Delete">✕</button>
    </div>`).join("");
}

function applyEarnCategoryRename(btn) {
  const input = btn.parentElement.querySelector("input");
  const orig  = input.dataset.orig;
  const next  = input.value.trim();
  if (!next || next === orig) return;
  _earnCatalog = _earnCatalog.map(e => e.category === orig ? {...e, category: next} : e);
  input.dataset.orig = next;
  input.dataset.dirty = "";
  _renderEarnCategoryEditor();
  _renderEarnCatalogRows();
}

function deleteEarnCategory(cat) {
  if (!confirm(`Delete category "${cat}"? Its earns will move to Uncategorized.`)) return;
  _earnCatalog = _earnCatalog.map(e => e.category === cat ? {...e, category: "Uncategorized"} : e);
  _renderEarnCategoryEditor();
  _renderEarnCatalogRows();
}

function addEarnCategory() {
  const input = document.getElementById("earn-cat-new-name");
  const name  = input.value.trim();
  if (!name) return;
  if (_earnCategoryList().includes(name)) { input.value = ""; return; }
  _earnCatalog = _earnCatalog.map(e => e);
  _earnCatalog.push({ label: "__placeholder__", schedule_value: "", category: name, available: false });
  input.value = "";
  _renderEarnCategoryEditor();
  _renderEarnCatalogRows();
}

function _renderEarnCatalogRows() {
  const tbody = document.getElementById("earn-catalog-rows");
  if (!tbody) return;
  tbody.innerHTML = "";
  const sorted = [..._earnCatalog].sort((a, b) => a.label.localeCompare(b.label));
  for (const entry of sorted) {
    const avail = entry.available === true ? "✓" : entry.available === false ? "✗" : "—";
    const availColor = entry.available === true ? "#a6e3a1" : entry.available === false ? "#f38ba8" : "var(--muted)";
    const allCats = [...new Set([..._EARN_CATEGORIES, ..._earnCategoryList()])];
    const catOptions = allCats.map(c =>
      `<option value="${c}" ${entry.category === c ? "selected" : ""}>${c}</option>`
    ).join("");
    const tr = document.createElement("tr");
    tr.style.borderBottom = "1px solid #2a2a3a";
    tr.dataset.label = entry.label;
    tr.innerHTML = `
      <td style="padding:6px 8px;">${entry.label}</td>
      <td style="padding:6px 8px;color:${availColor};font-weight:600;">${avail}</td>
      <td style="padding:6px 8px;">
        <select class="earn-cat-select" style="background:#2a2a3a;color:#cdd6f4;border:1px solid #444;border-radius:4px;padding:3px 6px;font-size:0.82rem;">
          ${catOptions}
        </select>
      </td>`;
    tbody.appendChild(tr);
  }
}

async function saveEarnCatalog() {
  const rows = document.querySelectorAll("#earn-catalog-rows tr[data-label]");
  const byLabel = Object.fromEntries(_earnCatalog.map(e => [e.label, e]));
  rows.forEach(row => {
    const label = row.dataset.label;
    const sel = row.querySelector(".earn-cat-select");
    if (byLabel[label] && sel) byLabel[label].category = sel.value;
  });
  const updated = Object.values(byLabel);
  try {
    await fetch("/earn_catalog", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(updated),
    });
    _earnCatalog = updated;
    closeEarnCatalog();
    _renderEarnSelect();
  } catch (e) {
    alert("Failed to save earn categories.");
  }
}

function refreshRespect() {
  const btn = document.getElementById("respect-refresh-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Refreshing…"; }
  fetch("/respect/refresh", {method: "POST"})
    .then(r => r.json())
    .then(d => {
      if (btn) { btn.disabled = false; btn.textContent = "Refresh Now"; }
      if (d.error) { alert(d.error); return; }
    })
    .catch(() => { if (btn) { btn.disabled = false; btn.textContent = "Refresh Now"; } });
}

let _botRunning = false;
let _botPaused = false;
let _prevEarnsEnabled = null;

function cancelSnipe() {
  fetch("/cancel-snipe", {method: "POST"}).catch(() => {});
  const btn = document.getElementById("cancel-snipe-btn");
  if (btn) btn.style.display = "none";
}

function toggleBot() {
  if (_botRunning) {
    // Stop is queued on the bot thread — don't change UI now; let pollStatus
    // reflect the real state once the stop task actually runs.
    fetch("/stop", {method: "POST"}).catch(() => {});
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

function openCloseBotModal() {
  document.getElementById("close-bot-overlay").style.display = "flex";
}
function closeCloseBotModal() {
  document.getElementById("close-bot-overlay").style.display = "none";
}
function closeBot() {
  closeCloseBotModal();
  fetch("/api/shutdown", {method: "POST"}).catch(() => {});
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

      // Cross-tab settings sync: a higher revision than we've seen means a
      // different tab (or the bot) changed the config — re-sync this tab.
      if (d.settings_rev != null) {
        if (!_settingsRevInit) {
          _knownSettingsRev = d.settings_rev;
          _settingsRevInit = true;
        } else if (d.settings_rev > _knownSettingsRev) {
          _knownSettingsRev = d.settings_rev;
          _onForeignSettingsChange();
        }
      }

      const taskEl = document.getElementById("status-task");
      if (taskEl) taskEl.textContent = (d.running && !d.paused && d.current_task) ? d.current_task : "";

      const cancelBtn = document.getElementById("cancel-snipe-btn");
      if (cancelBtn) cancelBtn.style.display = (d.running && !d.paused && d.current_task === "Snipe Top Job") ? "inline-block" : "none";

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

      // Move the jail General controls into the income "Jail" tab while in jail.
      _syncJailTab(!!d.in_jail);

      // Jail badge and status card tint
      const jailBadge = document.getElementById("stat-jail-badge");
      const statusCard = document.getElementById("s-character");
      const clearQueueBtn = document.getElementById("jail-clear-queue-btn");
      if (d.in_jail) {
        if (jailBadge) jailBadge.style.display = "";
        if (statusCard) { statusCard.classList.add("in-jail"); statusCard.classList.remove("in-hospital"); }
        if (clearQueueBtn) clearQueueBtn.disabled = false;
      } else if (d.in_hospital) {
        if (jailBadge) jailBadge.style.display = "none";
        if (statusCard) { statusCard.classList.remove("in-jail"); statusCard.classList.add("in-hospital"); }
        if (clearQueueBtn) clearQueueBtn.disabled = true;
      } else {
        if (jailBadge) jailBadge.style.display = "none";
        if (statusCard) { statusCard.classList.remove("in-jail"); statusCard.classList.remove("in-hospital"); }
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

      // Event-boss collected items (display only; click does nothing).
      const evWrap = document.getElementById("stat-event-consumables-wrap");
      if (evWrap) {
        const evc = d.event_consumables || {};
        const evNames = _EVENT_ITEMS.filter(n => evc[n] && (evc[n].qty ?? 0) > 0);
        if (d.event_boss_enabled && evNames.length) {
          evWrap.style.display = "";
          document.getElementById("stat-event-consumables").innerHTML =
            evNames.map(n =>
              `<div class="consumable-item"><span class="consumable-name">${n}</span><span class="consumable-qty ${_botRunning ? 'consumable-link' : ''}" onclick="${_botRunning ? `consumeEventItem('${n}')` : ''}">${evc[n].qty}</span></div>`
            ).join("");
        } else {
          evWrap.style.display = "none";
        }
      }

      // Timers
      _lastEnergy = d.energy;
      if (d.respect_pct !== undefined) {
        _respectPct = d.respect_pct;
        const respectItem = document.getElementById("stat-respect-item");
        const respectVal  = document.getElementById("stat-respect");
        if (respectItem && respectVal) {
          if (_respectPct != null) {
            respectVal.textContent = _respectPct;
            respectItem.style.display = "";
          } else {
            respectItem.style.display = "none";
          }
        }
      }
      updateTimers(d.timers || {}, d.server_time, d.agg_pro_active, d.in_jail ? d.jail_release_secs : null, d.flight_departs_at || null, d.hospital_release_at || null);
      // On login (transition to logged_in), refresh the auto-jail partner list
      // now that own occupation/home city are known.
      if (d.logged_in && !_botState.logged_in) loadAutoJailPartners();
      _botState = {
        logged_in: !!d.logged_in, in_jail: !!d.in_jail, in_hospital: !!d.in_hospital,
        action_ready: !!d.action_ready, hold_action_timer: !!d.hold_action_timer,
        city: d.city || "", home_city: d.home_city || "",
        occupation: d.occupation || "", rank: d.rank || "",
        cs_sentence: d.cs_sentence || 0, agg_fail_count: d.agg_fail_count || 0,
        online_players: new Set(d.online_players || []),
        local_players: new Set(d.local_players || []),
        jail_players: new Set(d.jail_players || []),
      };
      _updateStatPanel();
      _updateCharPills();
      _updatePlayerPills();
      updateActionWarnings();
      if (!_actMenuEl && document.getElementById("pl-tab-active")?.classList.contains("active")) {
        plRenderActive();
      }

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

      // Casino timer
      const casinoTimerEl = document.getElementById("casino-timer");
      if (casinoTimerEl) {
        const releaseAt = d.casino_release_at || 0;
        const secsLeft = Math.round(releaseAt - Date.now() / 1000);
        if (releaseAt <= 0 || secsLeft <= 0) {
          casinoTimerEl.textContent = "Ready";
        } else {
          const h = Math.floor(secsLeft / 3600);
          const m = Math.floor((secsLeft % 3600) / 60);
          const s = secsLeft % 60;
          casinoTimerEl.textContent = h + "h " + String(m).padStart(2,"0") + "m " + String(s).padStart(2,"0") + "s";
        }
      }

      // Banking mature date
      const matureEl = document.getElementById("banking-mature-date");
      if (matureEl) {
        const matureAt = d.banking_mature_at || 0;
        if (matureAt <= 0) {
          matureEl.textContent = "N/A";
        } else {
          const dt = new Date(matureAt * 1000);
          matureEl.textContent = dt.toLocaleString();
        }
      }

      // Bionics store visits + next check
      const bionicsViewsEl = document.getElementById("bionics-views");
      const bionicsNextEl  = document.getElementById("bionics-next-check");
      if (bionicsViewsEl) {
        bionicsViewsEl.textContent = d.bionics_views ? `${d.bionics_views.current} / ${d.bionics_views.max}` : "--";
      }
      if (bionicsNextEl) {
        if (d.bionics_next_check_at) {
          const secsLeft = Math.max(0, Math.round(d.bionics_next_check_at - Date.now() / 1000));
          if (secsLeft <= 0) {
            bionicsNextEl.textContent = "Ready";
          } else {
            const h = Math.floor(secsLeft / 3600), m = Math.floor((secsLeft % 3600) / 60), s = secsLeft % 60;
            bionicsNextEl.textContent = (h ? h + "h " : "") + String(m).padStart(2, "0") + "m " + String(s).padStart(2, "0") + "s";
          }
        } else {
          bionicsNextEl.textContent = "--";
        }
      }

      // Case work auto-detect
      updateCaseWorkSection(d.occupation || "");

      // Journals live feed — refresh when journals_updated_at advances.
      // Always refresh the underlying data (cjRefreshData only re-renders when no
      // filter is active, and rendering into a hidden panel is harmless), so the
      // viewer is current whether or not its tab is showing.
      if ((d.journals_updated_at || 0) > _cjLastUpdated) {
        _cjLastUpdated = d.journals_updated_at;
        cjRefreshData();
      }

      // Launder cooldown
      const lcdBar = document.getElementById("launder-cooldown-bar");
      if (lcdBar) {
        const lcd = d.launder_cooldown || 0;
        if (lcd > 0) {
          lcdBar.style.display = "flex";
          const m = Math.ceil(lcd / 60);
          document.getElementById("launder-cooldown-text").textContent = `Cooldown: ${m} min remaining`;
        } else {
          lcdBar.style.display = "none";
        }
      }

      // Notifications
      _updateNotifBell(d.notifications || []);

      // Character history live reload — refresh when char_history_updated_at advances
      if ((d.char_history_updated_at || 0) > _chLastUpdated) {
        _chLastUpdated = d.char_history_updated_at;
        loadPlayers();
        if (document.getElementById("pl-bolds-toggle")?.checked) _plRunWhitelistBolds();
        if (document.getElementById("status-history")?.classList.contains("active")) {
          loadCharHistory();
        }
        loadEarnPlanner();
      }

      if (d.earn_mode) {
        const em = document.getElementById("earn_mode");
        if (em && em.value !== d.earn_mode && em !== document.activeElement) {
          em.value = d.earn_mode;
        }
      }

      // Action enabled/type/fallback sync — reflect fallback-driven changes
      if (typeof d.action_enabled === "boolean") {
        const ae = document.getElementById("action_enabled");
        if (ae && ae.checked !== d.action_enabled) {
          ae.checked = d.action_enabled;
          _updateIncomeTabColors();
        }
      }
      if (d.action_type) {
        const at = document.getElementById("action_type");
        if (at && at.value !== d.action_type && at !== document.activeElement) {
          at.value = d.action_type;
          populateActionSub(d.action_sub || "");
        }
      }
      if (typeof d.action_fallback === "string") {
        const af = document.getElementById("action_fallback");
        if (af && af.value !== d.action_fallback && af !== document.activeElement) {
          af.value = d.action_fallback;
        }
      }

      // Active earn sync — reflect planner-driven earn switches in the Earns tab
      if (d.earn_type) {
        const es = document.getElementById("earn_type");
        if (es && es.value !== d.earn_type && es !== document.activeElement) {
          es.dataset.current = d.earn_type;
          _populateEarnCategories(d.earn_type);
        }
      }

      // Bionics window sync — update UI fields when auto-detected window changes
      if (d.bionics_window_start) {
        const ws = document.getElementById("bionics_window_start");
        if (ws && ws !== document.activeElement) ws.value = d.bionics_window_start;
      }
      if (d.bionics_window_end) {
        const we = document.getElementById("bionics_window_end");
        if (we && we !== document.activeElement) we.value = d.bionics_window_end;
      }

      // Weapon store next check
      const wsNextEl = document.getElementById("weapon-store-next-check");
      if (wsNextEl) {
        if (d.weapon_store_next_check_at) {
          const secsLeft = Math.max(0, Math.round(d.weapon_store_next_check_at - Date.now() / 1000));
          if (secsLeft <= 0) {
            wsNextEl.textContent = "Ready";
          } else {
            const h = Math.floor(secsLeft / 3600), m = Math.floor((secsLeft % 3600) / 60), s = secsLeft % 60;
            wsNextEl.textContent = (h ? h + "h " : "") + String(m).padStart(2, "0") + "m " + String(s).padStart(2, "0") + "s";
          }
        } else {
          wsNextEl.textContent = "--";
        }
      }

      // Weapon store window sync
      if (d.weapon_store_window_start) {
        const ws = document.getElementById("weapon_store_window_start");
        if (ws && ws !== document.activeElement) ws.value = d.weapon_store_window_start;
      }
      if (d.weapon_store_window_end) {
        const we = document.getElementById("weapon_store_window_end");
        if (we && we !== document.activeElement) we.value = d.weapon_store_window_end;
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

      // Scheduler visualization
      const schedBody = document.getElementById("scheduler-body");
      if (schedBody) {
        fetch("/api/scheduler").then(r => r.json()).then(s => {
          schedBody.innerHTML = (s.tasks || []).map(t => {
            const dot = t.ready
              ? '<span style="color:var(--accent)">● Ready</span>'
              : '<span style="color:var(--muted-text)">○ Blocked</span>';
            const reasons = (t.reasons || []).map(r => escHtml(r)).join(", ");
            return `<tr><td>${escHtml(t.label)}</td><td>${t.priority}</td><td>${dot}</td><td style="color:var(--muted-text);font-size:0.85em">${reasons}</td></tr>`;
          }).join("");
        }).catch(() => {});
      }
    })
    .catch(() => {})
    .finally(() => { _loadAvailableSkills(); setTimeout(pollStatus, 3000); });
}

loadPlayers();

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

// Bot state flags for status chips and state panel
let _botState = {
  logged_in: false, in_jail: false, in_hospital: false,
  action_ready: false, hold_action_timer: false,
  city: "", home_city: "", cs_sentence: 0, agg_fail_count: 0,
  online_players: new Set(), local_players: new Set(), jail_players: new Set(),
};

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

  // State chips
  const chip = (label, active, warn) => {
    const col = warn ? "var(--danger,#e05252)" : active ? "var(--accent)" : "var(--muted-text)";
    return `<div class="stat-item"><span class="stat-label" style="color:${col}">● ${label}</span></div>`;
  };
  const b = _botState;
  if (b.city && b.home_city && b.city !== b.home_city)
                           tiles.push(chip("Away",          false, false));
  if (b.hold_action_timer) tiles.push(chip("Hold Action",   false, true));
  if (b.cs_sentence > 0)   tiles.push(chip(`CS ×${b.cs_sentence}`, false, true));
  if (b.agg_fail_count > 0) tiles.push(chip(`Agg Fails ${b.agg_fail_count}/3`, b.agg_fail_count < 3, b.agg_fail_count >= 3));

  grid.innerHTML = tiles.join("");
}

function _updateStatPanel() {
  const panel = document.getElementById("state-panel-body");
  if (!panel) return;
  const b = _botState;
  const row = (label, value, warn) => {
    const col = warn ? "var(--danger,#e05252)" : "var(--muted-text)";
    return `<tr>
      <td class="stat-label" style="padding:4px 8px">${escHtml(label)}</td>
      <td class="stat-value" style="color:${col};text-align:right;padding:4px 8px">${escHtml(String(value))}</td>
    </tr>`;
  };
  const outsideHome = !!(b.city && b.home_city && b.city !== b.home_city);
  panel.innerHTML = [
    row("In Jail",            b.in_jail ? "Yes" : "No",           b.in_jail),
    row("In Hospital",        b.in_hospital ? "Yes" : "No",       b.in_hospital),
    row("Outside Home City",  outsideHome ? "Yes" : "No",         outsideHome),
    row("Hold Action Timer",  b.hold_action_timer ? "Yes" : "No", b.hold_action_timer),
    row("CS Sentence",        b.cs_sentence,                       b.cs_sentence > 0),
    row("Agg Fail Count",     `${b.agg_fail_count} / 3`,          b.agg_fail_count >= 3),
  ].join("");
}

function takeScreenshot() {
  window.open("/screenshot", "_blank");
}

function clearEarnQueue() {
  const btn = document.getElementById("clear-earn-btn");
  btn.disabled = true;
  fetch("/clear_earn_queue", { method: "POST" })
    .then(r => r.json())
    .finally(() => { btn.disabled = false; });
}

function togglePinInput() {
  const row = document.getElementById("pin_input_row");
  if (row) row.style.display = document.getElementById("pin_required").checked ? "" : "none";
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

function consumeEventItem(name) {
  fetch("/consume-event", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name}),
  });
}

function clearLaunderCooldown() {
  fetch("/clear-launder-cooldown", {method: "POST"});
}

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/'/g,"&#39;").replace(/"/g,"&quot;");
}

// Use escJsStr (not escHtml) when embedding a value as a string argument inside an
// inline onclick/onchange attribute.  JSON.stringify produces a valid JS double-quoted
// string literal; replacing the outer " with &quot; keeps it safe in the HTML context.
// The browser decodes &quot; → " before the JS engine parses it, so the result is a
// properly-escaped JS string regardless of apostrophes or other special characters.
function escJsStr(s) {
  return JSON.stringify(s == null ? "" : String(s)).replace(/&/g,"&amp;").replace(/"/g,"&quot;");
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
const CW_ENGINEERING_OCCUPATIONS = new Set(["Mechanic", "Technician", "Engineer", "Chief Engineer"]);
const CW_BANKING_OCCUPATIONS = new Set(["Bank Teller", "Loan Officer", "Bank Manager"]);

function updateCaseWorkSection(occupation) {
  const isHospital = CW_HOSPITAL_OCCUPATIONS.has(occupation);
  const isFire = CW_FIRE_OCCUPATIONS.has(occupation);
  const isEngineering = CW_ENGINEERING_OCCUPATIONS.has(occupation);
  const isBanking = CW_BANKING_OCCUPATIONS.has(occupation);
  const hasWork = isHospital || isFire || isEngineering || isBanking;

  document.getElementById("cw-none").style.display = hasWork ? "none" : "";
  document.getElementById("cw-hospital").style.display = isHospital ? "" : "none";
  document.getElementById("cw-fire").style.display = isFire ? "" : "none";
  document.getElementById("cw-engineering").style.display = isEngineering ? "" : "none";
  document.getElementById("cw-banking").style.display = isBanking ? "" : "none";
  if (isHospital)    renderCwHospitalHistory();
  if (isEngineering) renderCwEngineeringHistory();
}

function bulkAddLaunderContacts() {
  const btn = document.getElementById("bulk-launder-btn");
  const status = document.getElementById("bulk-launder-status");
  if (btn) btn.disabled = true;
  if (status) status.textContent = "Starting…";
  fetch("/banklaunder/bulk_add", {method: "POST"})
    .then(r => r.json())
    .then(d => {
      if (status) status.textContent = d.ok ? "Started — see activity log." : (d.error || "Failed.");
    })
    .catch(() => { if (status) status.textContent = "Request failed."; })
    .finally(() => { setTimeout(() => { if (btn) btn.disabled = false; }, 2000); });
}

// ── Laundering preferred contacts ─────────────────────────────────────────────

const _LAUNDER_OCCUPATIONS = ["Bank Teller", "Loan Officer", "Bank Manager"];

function populateLaunderContactSelect() {
  const sel = document.getElementById("launder_contact_select");
  if (!sel || !_plData) return;
  const existing = _getLaunderContacts();
  const existingLower = new Set(existing.map(n => n.toLowerCase()));
  const candidates = _plData
    .filter(p => _LAUNDER_OCCUPATIONS.includes(p.occupation) && p.active && !existingLower.has(p.username.toLowerCase()))
    .sort((a, b) => a.username.localeCompare(b.username));
  sel.innerHTML = '<option value="">-- select --</option>';
  candidates.forEach(p => {
    const opt = document.createElement("option");
    opt.value = p.username;
    opt.textContent = p.username;
    sel.appendChild(opt);
  });
}

function addLaunderContact() {
  const sel = document.getElementById("launder_contact_select");
  if (!sel || !sel.value) return;
  const name = sel.value;
  _appendLaunderContactItem(name);
  populateLaunderContactSelect();
  autoSave();
}

function fastAddLaunderContacts() {
  const sel = document.getElementById("launder_contact_select");
  if (!sel) return;
  const friendlyGroups = new Set(_plGroups.filter(g => g.type === "friendly").map(g => g.name));
  const opts = Array.from(sel.options).filter(o => {
    if (!o.value) return false;
    const p = _plData.find(pl => pl.username === o.value);
    return p && p.group && friendlyGroups.has(p.group);
  }).map(o => o.value);
  opts.forEach(name => _appendLaunderContactItem(name));
  populateLaunderContactSelect();
  autoSave();
}

function removeLaunderContact(btn) {
  const item = btn.closest(".launder-contact-item");
  if (item) item.remove();
  populateLaunderContactSelect();
  autoSave();
}

function _appendLaunderContactItem(name) {
  const list = document.getElementById("launder_contacts_list");
  if (!list) return;
  const existing = _getLaunderContacts();
  if (existing.some(n => n.toLowerCase() === name.toLowerCase())) return;
  const tr = document.createElement("tr");
  tr.className = "launder-contact-item";
  tr.dataset.name = name;
  tr.innerHTML = `<td style="padding:3px 12px 3px 0">${name}</td><td style="padding:3px 0"><button type="button" class="btn-danger-sm" onclick="removeLaunderContact(this)" style="font-size:0.75rem;padding:1px 6px">✕</button></td>`;
  list.appendChild(tr);
}

function _getLaunderContacts() {
  const list = document.getElementById("launder_contacts_list");
  if (!list) return [];
  return Array.from(list.querySelectorAll(".launder-contact-item")).map(el => el.dataset.name);
}

function _collectPromoChoices() {
  const choices = {};
  document.querySelectorAll('input[type="radio"][name^="promo_"]').forEach(radio => {
    if (radio.checked) choices[radio.name.replace(/^promo_/, "")] = radio.value;
  });
  return choices;
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

// ── Priority list helpers for bionics + weapon store ──────────────────────────

const WS_ITEMS = [
  "Baseball Bat","Pistol","Hand Grenade","Assault Rifle","Katana","Shotgun",
  "Lightsaber","Sniper Rifle","FlameThrower","Omega Death Laser","Plasma Rifle",
  "Rail Gun","Protection Vest","Kevlar Bullet Proof Vest","Riot Shield"
];

const BIONIC_ITEMS = ["arms","legs","eyes","brain","heart"];

function _serializePriorityItems(tbodyId) {
  return [...document.querySelectorAll(`#${tbodyId} tr`)].map(r => r.dataset.item).filter(Boolean);
}

function _wsCheckedItems() {
  return WS_ITEMS.filter(item => {
    const el = document.getElementById("ws_want_" + item.replace(/ /g, "_"));
    return el && el.checked;
  });
}

function _syncPriorityList(tbodyId, checkedItems) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  // Remove rows for unchecked items
  [...tbody.querySelectorAll("tr")].forEach(row => {
    if (!checkedItems.includes(row.dataset.item)) row.remove();
  });
  // Append newly checked items not already present
  const existing = [...tbody.querySelectorAll("tr")].map(r => r.dataset.item);
  checkedItems.forEach(item => {
    if (!existing.includes(item)) {
      const tr = document.createElement("tr");
      tr.dataset.item = item;
      tr.setAttribute("draggable", "true");
      tr.innerHTML =
        `<td class="priority-num"></td>` +
        `<td>${escHtml(item)}</td>` +
        `<td><div class="priority-move">` +
        `<button type="button" onclick="_moveRow(this,-1)">▲</button>` +
        `<button type="button" onclick="_moveRow(this,1)">▼</button>` +
        `</div></td>`;
      tbody.appendChild(tr);
    }
  });
  _renumberTable(tbodyId);
}

function bionicsOnBuyListChange() {
  const checked = BIONIC_ITEMS.filter(item => {
    const el = document.getElementById("bionics_want_" + item);
    return el && el.checked;
  });
  _syncPriorityList("bionics-priority-body", checked);
  _renderBuyListSummary("bionics-priority-body", "bionics-buylist-summary");
  autoSave();
}

function wsOnBuyListChange() {
  _syncPriorityList("weapon-store-priority-body", _wsCheckedItems());
  _renderBuyListSummary("weapon-store-priority-body", "weapon-store-buylist-summary");
  autoSave();
}

// Comma-delimited summary of the priority list (wanted items in priority order).
function _renderBuyListSummary(tbodyId, spanId) {
  const span = document.getElementById(spanId);
  if (!span) return;
  const tbody = document.getElementById(tbodyId);
  const items = tbody ? [...tbody.querySelectorAll("tr[data-item]")].map(r => r.dataset.item) : [];
  span.textContent = items.length ? items.join(", ") : "None";
}

function openBionicsBuyList() {
  const ov = document.getElementById("bionics-buylist-overlay");
  if (ov) ov.style.display = "flex";
}
function closeBionicsBuyList() {
  const ov = document.getElementById("bionics-buylist-overlay");
  if (ov) ov.style.display = "none";
  _renderBuyListSummary("bionics-priority-body", "bionics-buylist-summary");
}
function openWeaponBuyList() {
  const ov = document.getElementById("weapon-buylist-overlay");
  if (ov) ov.style.display = "flex";
}
function closeWeaponBuyList() {
  const ov = document.getElementById("weapon-buylist-overlay");
  if (ov) ov.style.display = "none";
  _renderBuyListSummary("weapon-store-priority-body", "weapon-store-buylist-summary");
}

function _initPriorityDrag(tbodyId) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  let dragSrc = null;

  tbody.addEventListener("dragstart", e => {
    const row = e.target.closest("tr[draggable]");
    if (!row) return;
    dragSrc = row;
    row.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
  });
  function _clearDropIndicators() {
    tbody.querySelectorAll(".drop-before,.drop-after").forEach(r => {
      r.classList.remove("drop-before", "drop-after");
    });
  }
  function _getDropTarget(e) {
    const row = e.target.closest("tr[draggable]");
    if (!row || row === dragSrc) return null;
    const rect = row.getBoundingClientRect();
    const after = e.clientY > rect.top + rect.height / 2;
    return { row, after };
  }
  tbody.addEventListener("dragend", () => {
    if (dragSrc) dragSrc.classList.remove("dragging");
    _clearDropIndicators();
    dragSrc = null;
  });
  tbody.addEventListener("dragover", e => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    _clearDropIndicators();
    const dt = _getDropTarget(e);
    if (dt) dt.row.classList.add(dt.after ? "drop-after" : "drop-before");
  });
  tbody.addEventListener("dragleave", e => {
    if (!tbody.contains(e.relatedTarget)) _clearDropIndicators();
  });
  tbody.addEventListener("drop", e => {
    e.preventDefault();
    _clearDropIndicators();
    const dt = _getDropTarget(e);
    if (!dt || !dragSrc) return;
    const { row: target, after } = dt;
    tbody.insertBefore(dragSrc, after ? target.nextSibling : target);
    _renumberTable(tbodyId);
    autoSave();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  _initPriorityDrag("bionics-priority-body");
  _initPriorityDrag("weapon-store-priority-body");
  _renderBuyListSummary("bionics-priority-body", "bionics-buylist-summary");
  _renderBuyListSummary("weapon-store-priority-body", "weapon-store-buylist-summary");
  toggleEventConsumeSettings();
  toggleWarModeLink();
  loadEarnPlanner();
  _loadSkillsGroupDropdown();
  _loadAvailableSkills();
  // Capture the baseline the diff-based save compares against, once dynamic
  // tables/summaries have populated from the server-rendered values.
  // Delay must be long enough for loadEarnPlanner fetch to complete.
  setTimeout(() => { _savedConfig = _buildPayload(); }, 2500);
});

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

const _BUYLIST_SUMMARY = {
  "bionics-priority-body": "bionics-buylist-summary",
  "weapon-store-priority-body": "weapon-store-buylist-summary",
};

function _renumberTable(tbodyId) {
  document.querySelectorAll(`#${tbodyId} tr`).forEach((row, i) => {
    const num = row.querySelector(".priority-num");
    if (num) num.textContent = i + 1;
  });
  if (_BUYLIST_SUMMARY[tbodyId]) _renderBuyListSummary(tbodyId, _BUYLIST_SUMMARY[tbodyId]);
}

function _loadSkillsGroupDropdown() {
  const sel = document.getElementById("skill_all_seeing_eye_group");
  if (!sel) return;
  const cur = sel.dataset.current || sel.value;
  fetch("/api/player_groups").then(r => r.json()).then(groups => {
    sel.innerHTML = '<option value="">-- select --</option>';
    groups.forEach(g => {
      const opt = document.createElement("option");
      opt.value = g;
      opt.textContent = g;
      if (g === cur) opt.selected = true;
      sel.appendChild(opt);
    });
  }).catch(() => {});
}

function _loadAvailableSkills() {
  fetch("/api/available_skills").then(r => r.json()).then(skills => {
    const msg = document.getElementById("skills-none-msg");
    let anyVisible = false;
    document.querySelectorAll(".skill-group").forEach(el => {
      if (skills.includes(el.dataset.skill)) {
        el.style.display = "";
        anyVisible = true;
      } else {
        el.style.display = "none";
      }
    });
    if (msg) msg.style.display = anyVisible ? "none" : "";
  }).catch(() => {});
}

function useSkillNow(skill, skillName) {
  const targetEl = document.getElementById("skill_" + skill + "_target");
  const target = (targetEl ? targetEl.value : "").trim();
  if (!target) { alert("Enter a target player first."); return; }
  fetch("/api/use_skill", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({skill: skill, target: target, skill_name: skillName})
  }).then(r => r.json()).then(d => {
    if (d.error) alert(d.error);
  }).catch(e => alert("Error: " + e));
}

function useNewsEditor() {
  const target = (document.getElementById("skill_news_editor_target")||{}).value||"";
  const title = (document.getElementById("skill_news_editor_title")||{}).value||"";
  const event = (document.getElementById("skill_news_editor_event")||{}).value||"";
  if (!target.trim() || !title.trim() || !event.trim()) {
    alert("All three fields (target, title, event) are required.");
    return;
  }
  fetch("/api/use_skill", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({skill: "news_editor", target: target.trim(), title: title.trim(), event: event.trim()})
  }).then(r => r.json()).then(d => {
    if (d.error) alert(d.error);
  }).catch(e => alert("Error: " + e));
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

// ── Quick Travel Overlay ──────────────────────────────────────────────────────

const _TRAVEL_CITIES = ["Auckland", "Beirut", "Chicago"];

function openTravelOverlay() {
  const current = _botState.city || "";
  const container = document.getElementById("travel-overlay-buttons");
  const status = document.getElementById("travel-overlay-status");
  status.textContent = "";
  container.innerHTML = _TRAVEL_CITIES
    .filter(c => c !== current)
    .map(c => `<button class="btn-primary" onclick="doQuickTravel('${c}')">${c}</button>`)
    .join("");
  document.getElementById("travel-overlay").style.display = "flex";
}

function closeTravelOverlay() {
  document.getElementById("travel-overlay").style.display = "none";
}

function doQuickTravel(city) {
  const status = document.getElementById("travel-overlay-status");
  status.textContent = "Travelling...";
  document.querySelectorAll("#travel-overlay-buttons button").forEach(b => b.disabled = true);
  fetch("/tasks/travel", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({target_city: city, method: "own_vehicle"}),
  })
    .then(r => r.json())
    .then(d => {
      if (d.error) { status.textContent = d.error; }
      else { status.textContent = "Travel to " + city + " initiated."; }
    })
    .catch(() => { status.textContent = "Request failed."; })
    .finally(() => {
      document.querySelectorAll("#travel-overlay-buttons button").forEach(b => b.disabled = false);
    });
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
          <td><button class="btn-secondary" style="white-space:nowrap;padding:4px 10px" onclick="turnInWarrant(this,${escJsStr(w.turn_in_url)},${escJsStr(w.case_id)})">Turn In</button></td>
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
  const btn = document.getElementById("status-tab-history-btn");
  if (btn) btn.style.display = enabled ? "" : "none";
  const panel = document.getElementById("status-history");
  if (enabled) {
    loadCharHistory();
  } else if (panel && panel.classList.contains("active")) {
    // History tab was open but is now disabled → fall back to Stats
    const statsBtn = document.querySelector("#s-character .tab-bar .tab-btn");
    if (statsBtn) statsBtn.click();
  }
}

function refreshCharHistory() {
  fetch("/character_history/refresh", {method: "POST"})
    .then(r => r.json())
    .then(d => {
      if (d.error) { alert(d.error); return; }
      setTimeout(loadCharHistory, 3000);
    });
}

let _chViewing = "";  // "" = current character

function loadCharHistory(name) {
  if (name === undefined) name = _chViewing;
  _chViewing = name || "";
  const q = _chViewing ? "?char=" + encodeURIComponent(_chViewing) : "";
  _populateCharHistorySelect();
  Promise.all([
    fetch("/character_history" + q).then(r => r.json()),
    fetch("/trait_requirements" + q).then(r => r.json()),
  ]).then(([data, reqs]) => {
    _chData = data;
    _chReqs = reqs;
    renderCharHistory(data, reqs);
  });
}

function _populateCharHistorySelect() {
  const sel = document.getElementById("char-history-select");
  if (!sel) return;
  fetch("/character_history/list").then(r => r.json()).then(d => {
    const names = d.characters || [];
    const current = d.current || "";
    const opts = [];
    if (current) opts.push(`<option value="">${escHtml(current)} (current)</option>`);
    names.filter(n => n !== current).forEach(n => opts.push(`<option value="${escHtml(n)}">${escHtml(n)}</option>`));
    sel.innerHTML = opts.join("") || '<option value="">(none saved)</option>';
    sel.value = _chViewing;
  }).catch(() => {});
}

function onCharHistorySelect() {
  const sel = document.getElementById("char-history-select");
  if (sel) loadCharHistory(sel.value);
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

// Global toggle: hide entire subsections whose values are all zero.
function _isChHideEmpty() {
  return localStorage.getItem("ch-hide-empty") === "true";
}

function toggleChHideEmpty() {
  localStorage.setItem("ch-hide-empty", _isChHideEmpty() ? "false" : "true");
  reRenderCharHistory();
}

function _isSectionAllZero(sec) {
  const rows = sec && sec.rows ? sec.rows : [];
  return rows.length > 0 && rows.every(r => _isZero(r.value));
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

// Collect same-origin stylesheet rules so the exported image is fully styled.
function _collectAppCss() {
  let css = "";
  for (const sheet of document.styleSheets) {
    let rules;
    try { rules = sheet.cssRules; } catch (e) { continue; }
    if (!rules) continue;
    for (const rule of rules) css += rule.cssText + "\n";
  }
  return css;
}

// Render the character-history content to a downloadable PNG (no external libs).
function saveCharHistoryImage() {
  const src = document.getElementById("char-history-body");
  if (!src || !_chData) { alert("No character history to save yet."); return; }

  const pad = 20, scale = 2;
  const w = Math.max(src.scrollWidth, src.getBoundingClientRect().width);
  const h = Math.max(src.scrollHeight, src.getBoundingClientRect().height);
  const totalW = Math.ceil(w + pad * 2);
  const totalH = Math.ceil(h + pad * 2);

  const bgRaw = getComputedStyle(document.body).getPropertyValue("--surface").trim();
  const bg = bgRaw || "#232f42";

  const wrapper = document.createElement("div");
  wrapper.setAttribute("xmlns", "http://www.w3.org/1999/xhtml");
  wrapper.style.cssText =
    `width:${Math.ceil(w)}px;padding:${pad}px;background:${bg};box-sizing:content-box;`;
  const styleEl = document.createElement("style");
  styleEl.textContent = _collectAppCss();
  wrapper.appendChild(styleEl);
  wrapper.appendChild(src.cloneNode(true));

  let xhtml;
  try { xhtml = new XMLSerializer().serializeToString(wrapper); }
  catch (e) { alert("Could not serialize content for image export."); return; }

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${totalW}" height="${totalH}">` +
    `<foreignObject x="0" y="0" width="${totalW}" height="${totalH}">${xhtml}</foreignObject></svg>`;
  const url = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);

  const img = new Image();
  img.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = totalW * scale;
    canvas.height = totalH * scale;
    const ctx = canvas.getContext("2d");
    ctx.scale(scale, scale);
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, totalW, totalH);
    ctx.drawImage(img, 0, 0);
    try {
      canvas.toBlob(blob => {
        if (!blob) { alert("Could not generate image."); return; }
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        const name = String(_chViewing || "character").replace(/[^a-zA-Z0-9_-]/g, "_");
        a.download = `char_history_${name}.png`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      }, "image/png");
    } catch (e) {
      alert("Could not export image: " + e.message);
    }
  };
  img.onerror = () => alert("Could not render image (browser limitation).");
  img.src = url;
}

function renderCwEngineeringHistory() {
  const container = document.getElementById("cw-eng-history");
  if (!container) return;
  const enabled = document.getElementById("char_history_enabled")?.checked;
  if (!enabled) { container.innerHTML = ""; return; }

  if (!_chData || !_chData.stat_sections) {
    container.innerHTML = `<p style="color:var(--muted);font-size:0.9rem">No character history data yet.</p>`;
    return;
  }
  const sec = (_chData.stat_sections || []).find(s => s.title === "Engineering");
  if (!sec) { container.innerHTML = ""; return; }

  const REFRESH_BTN = `<button class="btn-secondary icon-btn" onclick="refreshCharHistory()" title="Refresh character history" style="margin-left:4px;padding:2px 5px">
    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
  </button>`;

  const hideZeros = _isHideZeros(sec.title);
  const rows = hideZeros ? sec.rows.filter(r => !_isZero(r.value)) : sec.rows;
  const toggle = _hzToggle(sec.title, hideZeros);

  let html = `<div class="ch-section">
    <div class="ch-section-head"><span class="ch-section-title">${sec.title}</span>${toggle}${REFRESH_BTN}</div>`;
  if (!rows.length && hideZeros) {
    html += `<p class="ch-empty-note">All values zero</p>`;
  } else {
    html += `<table class="ch-table">`;
    for (const row of rows) {
      html += `<tr><td class="ch-key">${row.key}</td><td class="ch-val">${_fmtVal(row.value)}</td></tr>`;
    }
    html += `</table>`;
  }
  html += `</div>`;
  container.innerHTML = html;
}

function renderCwHospitalHistory() {
  const container = document.getElementById("cw-hosp-history");
  if (!container) return;
  const enabled = document.getElementById("char_history_enabled")?.checked;
  if (!enabled) { container.innerHTML = ""; return; }

  if (!_chData || !_chData.stat_sections) {
    container.innerHTML = `<p style="color:var(--muted);font-size:0.9rem">No character history data yet.</p>`;
    return;
  }
  const sec = (_chData.stat_sections || []).find(s => s.title === "Medical Work");
  if (!sec) { container.innerHTML = ""; return; }

  const REFRESH_BTN = `<button class="btn-secondary icon-btn" onclick="refreshCharHistory()" title="Refresh character history" style="margin-left:4px;padding:2px 5px">
    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
  </button>`;

  const hideZeros = _isHideZeros(sec.title);
  const rows = hideZeros ? sec.rows.filter(r => !_isZero(r.value)) : sec.rows;
  const toggle = _hzToggle(sec.title, hideZeros);

  let html = `<div class="ch-section">
    <div class="ch-section-head"><span class="ch-section-title">${sec.title}</span>${toggle}${REFRESH_BTN}</div>`;
  if (!rows.length && hideZeros) {
    html += `<p class="ch-empty-note">All values zero</p>`;
  } else {
    html += `<table class="ch-table">`;
    for (const row of rows) {
      html += `<tr><td class="ch-key">${row.key}</td><td class="ch-val">${_fmtVal(row.value)}</td></tr>`;
    }
    html += `</table>`;
  }
  html += `</div>`;
  container.innerHTML = html;
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

  const hideEmptyToggle = document.getElementById("ch-hide-empty-toggle");
  if (hideEmptyToggle) hideEmptyToggle.checked = _isChHideEmpty();

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
  const hideEmpty = _isChHideEmpty();
  const secs = SECTION_ORDER.map(t => byTitle[t]).filter(Boolean)
    .filter(sec => !(hideEmpty && sec.title !== "Character Information" && _isSectionAllZero(sec)));
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
  renderCwHospitalHistory();
  renderCwEngineeringHistory();
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
let _cjSubTab = "events"; // "events" or "requests"
let _cjShowInactive = false;
let _cjLastUpdated = 0;   // last journals_updated_at seen from /status
let _chLastUpdated = 0;   // last char_history_updated_at seen from /status
const CJ_PAGE_SIZE = 10;

function cjSwitchSub(tab, btn) {
  _cjSubTab = tab;
  document.querySelectorAll(".cj-journal-subtabs .tab-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  const toggle = document.getElementById("cj-inactive-toggle");
  if (toggle) toggle.style.display = tab === "requests" ? "flex" : "none";
  cjSearch();
}

function _cjFilterByTab(entries) {
  return entries.filter(e => {
    if ((e.type || "events") !== _cjSubTab) return false;
    if (_cjSubTab === "requests" && !_cjShowInactive && e.status === "inactive") return false;
    return true;
  });
}

function cjToggleInactive() {
  _cjShowInactive = !_cjShowInactive;
  cjSearch();
}

function cjRefresh() {
  fetch("/refresh-journals", {method: "POST"})
    .then(r => r.json())
    .catch(() => {});
}

function cjInit() {
  fetch("/journals")
    .then(r => r.json())
    .then(data => {
      _cjData = Object.values(data).sort((a, b) => new Date(b.time) - new Date(a.time));
      _cjFiltered = _cjFilterByTab(_cjData);
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
      const q = (document.getElementById("cj-search")?.value || "").toLowerCase().trim();
      if (!q) {
        _cjFiltered = _cjFilterByTab(_cjData);
        cjRender();
      }
      // Filter active — _cjData is updated silently.
      // cjSearch() will pick it up the moment the user clears the box.
    })
    .catch(() => {});
}

function cjSearch() {
  const q = (document.getElementById("cj-search").value || "").toLowerCase().trim();
  let base = _cjFilterByTab(_cjData);
  if (!q) {
    _cjFiltered = base;
  } else {
    const words = q.split(/\s+/).filter(Boolean);
    _cjFiltered = base.filter(e => {
      const haystack = [(e.title || ""), (e.text || ""), (e.time || "")].join(" ").toLowerCase();
      return words.every(w => haystack.includes(w));
    });
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

  list.innerHTML = slice.map(e => {
    const inactive = e.status === "inactive";
    let actions = "";
    if (_cjSubTab === "requests" && !inactive) {
      if (e.accept_url) actions += `<button class="action-btn" onclick="cjDoAction('${escHtml(e.id)}','${escHtml(e.accept_url)}','accept')">Accept</button>`;
      if (e.decline_url) actions += `<button class="btn-secondary" onclick="cjDoAction('${escHtml(e.id)}','${escHtml(e.decline_url)}','decline')">Decline</button>`;
    }
    return `<div class="cj-entry${inactive ? ' cj-inactive' : ''}" id="cje-${escHtml(e.id || '')}">
      <span class="cj-entry-title">${escHtml(e.title || "")}${inactive ? ' <em style="font-size:0.8em;opacity:0.6">(inactive)</em>' : ''}</span>
      <span class="cj-entry-time">${escHtml(e.time || "")}</span>
      <div class="cj-entry-text">${escHtml(e.text || "")}</div>
      ${actions ? `<div class="cj-entry-actions" style="margin-top:4px;display:flex;gap:6px">${actions}</div>` : ""}
    </div>`;
  }).join("");

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

function cjDoAction(entryId, url, actionType) {
  const row = document.getElementById("cje-" + entryId);
  const btns = row ? row.querySelectorAll(".cj-entry-actions button") : [];
  btns.forEach(b => b.disabled = true);
  fetch("/journal-action", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({entry_id: entryId, action_url: url, action_type: actionType}),
  })
    .then(r => r.json())
    .then(d => {
      if (row) {
        const act = row.querySelector(".cj-entry-actions");
        if (act) act.innerHTML = `<span style="color:var(--muted);font-size:0.8rem">${escHtml(actionType)} sent</span>`;
      }
    })
    .catch(() => { btns.forEach(b => b.disabled = false); });
}

// =============================================================================
// Player Section
// =============================================================================

const PL_SWATCH_COLORS = ["#e74c3c","#e67e22","#f1c40f","#2ecc71","#3498db","#9b59b6","#e91e8c","#1abc9c","#aaaaaa","#555555"];

let _plData     = [];
let _plFiltered = [];
let _plExpanded = {};
let _plGroups   = [];
let _plSortCol  = "username";
let _plSortAsc  = true;
const _plColVisible = {rank:true, occupation:true, career_group:true, homecity:true, group:true, tags:true, character_age:true, jail_age:true, agg_crimes:true, case_work:true};
const _PL_COL_INDEX = {rank:2, occupation:3, career_group:4, homecity:5, group:6, tags:7, character_age:8, jail_age:9, agg_crimes:10, case_work:11};

// ── Helpers ──────────────────────────────────────────────────────────────────

function _plGroupColorMap() {
  const m = {};
  _plGroups.forEach(g => { m[g.name] = g.color; });
  return m;
}

function _fmtAge(mins) {
  if (!mins) return "—";
  const h = Math.floor(mins / 60), m = mins % 60;
  return h ? `${h}h ${m}m` : `${m}m`;
}

const _CAREER_GROUPS = {
  "Gangster":   ["gangster"],
  "Law":        ["legal secretary", "lawyer", "judge", "supreme court judge"],
  "Police":     ["police officer"],
  "Customs":    ["customs"],
  "Hospital":   ["nurse", "doctor", "surgeon", "hospital director"],
  "Engineering":["mechanic", "technician", "engineer", "chief engineer"],
  "Fire":       ["volunteer fire fighter", "fire fighter", "fire chief"],
  "Bank":       ["bank teller", "bank manager", "loan officer"],
  "Funeral":    ["mortician assistant", "mortician", "undertaker", "funeral director"],
  "Mayor":      ["mayor"],
  "Unemployed": ["unemployed"],
};
const _OCC_TO_CAREER = {};
Object.entries(_CAREER_GROUPS).forEach(([grp, occs]) => {
  occs.forEach(o => { _OCC_TO_CAREER[o] = grp; });
});

function _careerGroup(occupation) {
  return _OCC_TO_CAREER[(occupation || "").toLowerCase()] || "Other";
}

// Collapsed-header pills for the Player Lists section: active count (👥) plus
// live totals for online / local-online / jail populations.
function _updatePlayerPills() {
  const pill = document.getElementById("pills-s-players");
  if (!pill) return;
  const active = (_plData || []).filter(p => p.active).length;
  const online = _botState.online_players ? _botState.online_players.size : 0;
  const local  = _botState.local_players  ? _botState.local_players.size  : 0;
  const jail   = _botState.jail_players   ? _botState.jail_players.size   : 0;
  const spec = [
    { n: active, color: "",        label: "Total players" },
    { n: online, color: "#ffffff", label: "Total online" },
    { n: local,  color: "#eab308", label: "Total local online" },
    { n: jail,   color: "#3fae5a", label: "In jail" },
  ];
  pill.innerHTML = spec.map(s => _peoplePill(s.n, s.color, s.label)).join("");
}

// A count pill styled like the default section pill, with a "people" glyph
// tinted to encode its category. `label` is exposed as tooltip + accessible text.
function _peoplePill(count, color, label) {
  const fill = color || "currentColor";
  const icon = `<svg viewBox="0 0 640 512" width="14" height="12" style="vertical-align:-1px" fill="${fill}" aria-hidden="true"><path d="M144 0a80 80 0 1 1 0 160A80 80 0 1 1 144 0zM512 0a80 80 0 1 1 0 160A80 80 0 1 1 512 0zM0 298.7C0 239.8 47.8 192 106.7 192l42.7 0c15.9 0 31 3.5 44.6 9.7c-1.3 7.2-1.9 14.7-1.9 22.3c0 38.2 16.8 72.5 43.3 96c-.2 0-.4 0-.7 0L21.3 320C9.6 320 0 310.4 0 298.7zM405.3 320c-.2 0-.4 0-.7 0c26.6-23.5 43.3-57.8 43.3-96c0-7.6-.7-15-1.9-22.3c13.6-6.3 28.7-9.7 44.6-9.7l42.7 0C592.2 192 640 239.8 640 298.7c0 11.8-9.6 21.3-21.3 21.3l-213.3 0zM224 224a96 96 0 1 1 192 0 96 96 0 1 1 -192 0zM128 485.3C128 411.7 187.7 352 261.3 352l117.3 0C452.3 352 512 411.7 512 485.3c0 14.7-11.9 26.7-26.7 26.7l-330.7 0c-14.7 0-26.7-11.9-26.7-26.7z"/></svg>`;
  return `<span class="pill" title="${escHtml(label)}" aria-label="${escHtml(label)}: ${count}">${icon} ${count}</span>`;
}

// ── Active players tab (live online / local / jail + quick interactions) ──────
// Career colours taken verbatim from the game's own `.colored .*` CSS classes.
// (Gangster = the game's "Crime", Mayor = "Politics".)
const _CAREER_COLORS = {
  "Gangster":    "#E8E68F",              // .crime
  "Police":      "#33C4ff",              // .police
  "Law":         "#D256FF",              // .law
  "Customs":     "#05D5A4",              // .customs
  "Hospital":    "#FFA4A4",              // .hospital
  "Engineering": "#FFA455",              // .engineering
  "Fire":        "#FF7745",              // .fire
  "Bank":        "#1cfb3d",              // .bank
  "Funeral":     "rgba(255,255,255,0.58)", // .funeral
  "Mayor":       "#FFFFFF",              // .politics / .mayor
  "Unemployed":  "#C0C0C0",              // .colored .none
  "Other":       "#C0C0C0",
};

function _careerColor(occupation) {
  return _CAREER_COLORS[_careerGroup(occupation)] || _CAREER_COLORS["Other"];
}

function _plOccByName() {
  const m = {};
  (_plData || []).forEach(p => { if (p.username) m[p.username.toLowerCase()] = p; });
  return m;
}

let _activeCareerFilter = "All";

function plFilterCareer(career) {
  _activeCareerFilter = career;
  document.querySelectorAll(".pl-career-tab").forEach(b => {
    b.classList.toggle("active", b.textContent.trim() === career);
  });
  plRenderActive();
}

function plRenderActive() {
  const content  = document.getElementById("pl-active-content");
  const legendEl = document.getElementById("pl-active-legend");
  if (!content) return;

  if (legendEl) {
    legendEl.innerHTML = Object.entries(_CAREER_COLORS)
      .filter(([g]) => g !== "Other")
      .map(([g, c]) => `<span class="pl-legend-item"><span class="pl-legend-dot" style="background:${c}"></span>${g}</span>`)
      .join("");
  }

  const occ      = _plOccByName();
  const online   = _botState.online_players ? [..._botState.online_players] : [];
  const local    = _botState.local_players  ? [..._botState.local_players]  : [];
  const jail     = _botState.jail_players   ? [..._botState.jail_players]   : [];
  const localSet = new Set(local);

  const groups = [
    { key: "online", title: "Online (other cities)", names: online.filter(n => !localSet.has(n)) },
    { key: "local",  title: "Local City",            names: local },
    { key: "jail",   title: "In Jail",               names: jail },
  ];

  content.innerHTML = groups.map(g => {
    let names = g.names.slice().sort((a, b) => a.localeCompare(b));
    if (_activeCareerFilter !== "All") {
      names = names.filter(n => {
        const p = occ[n.toLowerCase()];
        return p && _careerGroup(p.occupation) === _activeCareerFilter;
      });
    }
    const chips = names.length
      ? names.map(n => {
          const p     = occ[n.toLowerCase()];
          const color = p ? _careerColor(p.occupation) : _CAREER_COLORS["Other"];
          const title = p ? `${p.occupation || "?"} · ${p.homecity || "?"}` : "not in player DB";
          const mayorCls = p && _careerGroup(p.occupation) === "Mayor" ? " pl-active-mayor" : "";
          return `<button class="pl-active-name${mayorCls}" style="color:${color}" title="${escHtml(title)}"
                    onclick="plOpenActMenu(event, ${escJsStr(n)}, '${g.key}')">${escHtml(n)}</button>`;
        }).join("")
      : `<span class="pl-active-empty">None</span>`;
    return `<div class="pl-active-group">
      <div class="pl-active-group-head">${escHtml(g.title)} <span class="pl-active-count">${names.length}</span></div>
      <div class="pl-active-names">${chips}</div>
    </div>`;
  }).join("");
}

let _actMenuEl = null;

function plOpenActMenu(ev, username, groupKey) {
  ev.stopPropagation();
  plCloseActMenu();

  const actions = [];
  if (groupKey === "local") {
    // Hack / B&E require residency confirmation from the player DB:
    //   B&E  → target's home city matches the bot's CURRENT city
    //   Hack → the above AND target's home city matches the bot's HOME city
    const p       = _plOccByName()[username.toLowerCase()];
    const homeCity = p ? (p.homecity || "") : "";
    const eq = (a, b) => !!a && !!b && a.toLowerCase() === b.toLowerCase();
    const canBreak = eq(homeCity, _botState.city || "");
    const canHack  = canBreak && eq(homeCity, _botState.home_city || "");

    actions.push(["pickpocket", "Pickpocket"], ["mugging", "Mug"]);
    if (canHack)  actions.push(["hack", "Hack"]);
    if (canBreak) actions.push(["breaking", "Break & Enter"]);
  }
  actions.push(["transfer", "Transfer Money"]);

  const p       = _plOccByName()[username.toLowerCase()];
  const nameCol = p ? _careerColor(p.occupation) : _CAREER_COLORS["Other"];
  const rowsHtml = p
    ? `<div class="pl-act-row"><span>City</span><b>${escHtml(p.homecity || "?")}</b></div>` +
      `<div class="pl-act-row"><span>Job</span><b>${escHtml(p.occupation || "?")}</b></div>` +
      `<div class="pl-act-row"><span>Rank</span><b>${escHtml(p.rank || "?")}</b></div>`
    : `<div class="pl-act-row pl-act-unknown">Not in player DB</div>`;
  const avatarHtml = (p && p.pic_url)
    ? `<img class="pl-act-avatar" src="/api/player_image/${encodeURIComponent(username)}" alt=""
            onerror="this.style.display='none'">`
    : "";

  const el = document.createElement("div");
  el.className = "pl-act-menu";
  el.innerHTML =
    `<div class="pl-act-menu-top">${avatarHtml}<div class="pl-act-menu-head" style="color:${nameCol}">${escHtml(username)}</div></div>` +
    `<div class="pl-act-details">${rowsHtml}</div>` +
    actions.map(([kind, label]) =>
      `<button class="pl-act-btn" onclick="plDoInteract('${kind}', ${escJsStr(username)})">${escHtml(label)}</button>`
    ).join("") +
    `<div class="pl-act-result" style="display:none"></div>`;
  document.body.appendChild(el);
  _actMenuEl = el;

  const pad  = 8;
  const rect = el.getBoundingClientRect();
  let x = ev.clientX, y = ev.clientY + 6;
  if (x + rect.width  + pad > window.innerWidth)  x = window.innerWidth  - rect.width  - pad;
  if (y + rect.height + pad > window.innerHeight) y = ev.clientY - rect.height - 6;
  el.style.left = Math.max(pad, x) + "px";
  el.style.top  = Math.max(pad, y) + "px";
}

function plCloseActMenu() {
  if (_actMenuEl) { _actMenuEl.remove(); _actMenuEl = null; }
}

document.addEventListener("click", e => {
  if (_actMenuEl && !_actMenuEl.contains(e.target)) plCloseActMenu();
});

function plDoInteract(crime, username) {
  if (!_actMenuEl) return;
  let amount = 0;
  if (crime === "transfer") {
    const val = prompt(`Transfer how much to ${username}?`, "1");
    if (val === null) return;
    amount = parseInt(String(val).replace(/[^0-9]/g, ""), 10) || 0;
    if (amount <= 0) return;
  }
  const resultEl = _actMenuEl.querySelector(".pl-act-result");
  const buttons  = _actMenuEl.querySelectorAll(".pl-act-btn");
  buttons.forEach(b => b.disabled = true);
  if (resultEl) {
    resultEl.style.display = "block";
    resultEl.className = "pl-act-result";
    resultEl.textContent = "Working…";
  }

  fetch("/api/interact", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ crime, target: username, amount }),
  })
    .then(r => r.json())
    .then(d => {
      if (resultEl) {
        resultEl.textContent = d.message || (d.ok ? "Done." : "Failed.");
        resultEl.classList.add(d.ok ? "pl-act-ok" : "pl-act-fail");
      }
      buttons.forEach(b => b.disabled = false);
    })
    .catch(() => {
      if (resultEl) { resultEl.textContent = "Request failed."; resultEl.classList.add("pl-act-fail"); }
      buttons.forEach(b => b.disabled = false);
    });
}

function _onlineStatus(username) {
  if (_botState.local_players.has(username)) return "local";
  if (_botState.online_players.has(username)) return "online";
  return "offline";
}

// ── Load & rebuild filters ────────────────────────────────────────────────────

function loadPlayers() {
  fetch("/api/players")
    .then(r => r.json())
    .then(data => {
      _plData   = (data.players || []).map(p => ({ ...p, group: p.group_name ?? p.group ?? "" }));
      _plGroups = data.groups || [];
      _plRebuildFilters();
      plFilter();
      _plRenderGroupsTab(_plGroups);
      _updatePlayerPills();
      // Keep the auto-jail partner list current with the player DB.
      loadAutoJailPartners();
      populateLaunderContactSelect();
    })
    .catch(() => {});
}

function _plRebuildFilters() {
  const uniq = col => [...new Set(_plData.map(p => p[col] || "").filter(Boolean))].sort((a,b) => a.localeCompare(b));
  const uniqTags = [...new Set(_plData.flatMap(p => p.tags || []))].sort();
  const uniqCareer = [...new Set(_plData.map(p => _careerGroup(p.occupation)).filter(Boolean))].sort((a,b) => a.localeCompare(b));

  const specs = [
    { id: "pl-filter-rank",         vals: uniq("rank") },
    { id: "pl-filter-occupation",   vals: uniq("occupation") },
    { id: "pl-filter-career-group", vals: uniqCareer },
    { id: "pl-filter-homecity",     vals: uniq("homecity") },
    { id: "pl-filter-group",        vals: uniq("group") },
    { id: "pl-filter-tag",          vals: uniqTags },
  ];
  specs.forEach(({ id, vals }) => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = `<option value="">All</option>` +
      vals.map(v => `<option value="${escHtml(v)}">${escHtml(v)}</option>`).join("");
    if (cur && [...sel.options].some(o => o.value === cur)) sel.value = cur;
  });
}

// ── Filter & sort ─────────────────────────────────────────────────────────────

function plFilter() {
  const search    = (document.getElementById("pl-search")?.value || "").toLowerCase();
  const aliasFlt  = (document.getElementById("pl-filter-alias")?.value || "").toLowerCase();
  const onlineFlt = document.getElementById("pl-filter-online")?.value || "";
  const rank      = document.getElementById("pl-filter-rank")?.value || "";
  const occ       = document.getElementById("pl-filter-occupation")?.value || "";
  const careerGrp = document.getElementById("pl-filter-career-group")?.value || "";
  const city      = document.getElementById("pl-filter-homecity")?.value || "";
  const group     = document.getElementById("pl-filter-group")?.value || "";
  const tag       = document.getElementById("pl-filter-tag")?.value || "";
  const agg       = document.getElementById("pl-filter-agg")?.value || "";
  const cw        = document.getElementById("pl-filter-casework")?.value || "";
  const activeOnly = document.getElementById("pl-filter-active")?.checked ?? true;

  _plFiltered = _plData.filter(p => {
    if (activeOnly && !p.active) return false;
    if (search && !p.username.toLowerCase().includes(search)) return false;
    if (aliasFlt && !(p.alias||"").toLowerCase().includes(aliasFlt)) return false;
    if (onlineFlt && _onlineStatus(p.username) !== onlineFlt) return false;
    if (rank  && p.rank !== rank) return false;
    if (occ   && p.occupation !== occ) return false;
    if (careerGrp && _careerGroup(p.occupation) !== careerGrp) return false;
    if (city  && p.homecity !== city) return false;
    if (group && p.group !== group) return false;
    if (tag   && !(p.tags||[]).includes(tag)) return false;
    if (agg === "__none__" && p.agg_crimes) return false;
    if (agg && agg !== "__none__" && p.agg_crimes !== agg) return false;
    if (cw === "__none__" && p.case_work) return false;
    if (cw && cw !== "__none__" && p.case_work !== cw) return false;
    return true;
  });
  _plApplySort();
  _plRenderTable();
}

function plSort(col) {
  if (_plSortCol === col) _plSortAsc = !_plSortAsc;
  else { _plSortCol = col; _plSortAsc = true; }
  _plApplySort();
  _plRenderTable();
}

const _STATUS_ORDER = { local: 0, online: 1, offline: 2 };

function _plSortVal(p, col) {
  if (col === "career_group") return _careerGroup(p.occupation).toLowerCase();
  if (col === "online_status") return String(_STATUS_ORDER[_onlineStatus(p.username)] ?? 2);
  if (col === "character_age") return String(p.character_age || 0).padStart(10, "0");
  if (col === "jail_age") return String(p.jail_age || 0).padStart(10, "0");
  return (p[col] || "").toLowerCase();
}

function _plApplySort() {
  const col = _plSortCol, asc = _plSortAsc ? 1 : -1;
  _plFiltered = [..._plFiltered].sort((a, b) =>
    asc * _plSortVal(a, col).localeCompare(_plSortVal(b, col))
  );
  document.querySelectorAll(".pl-th[data-col]").forEach(th => {
    const icon = th.querySelector(".pl-sort-icon");
    if (!icon) return;
    if (th.dataset.col === col) {
      icon.textContent = _plSortAsc ? "▲" : "▼";
      th.classList.add("pl-th-sorted");
    } else {
      icon.textContent = "↕";
      th.classList.remove("pl-th-sorted");
    }
  });
}

// ── Column visibility ─────────────────────────────────────────────────────────

function togglePlColMenu() {
  const m = document.getElementById("pl-col-menu");
  if (m) m.style.display = m.style.display === "none" ? "block" : "none";
}

function plToggleColSection(hdr) {
  const body = hdr.nextElementSibling;
  const chevron = hdr.querySelector(".pl-col-chevron");
  if (!body) return;
  const collapsed = body.style.display === "none";
  body.style.display = collapsed ? "" : "none";
  if (chevron) chevron.textContent = collapsed ? "▾" : "▸";
}
document.addEventListener("click", e => {
  const menu = document.getElementById("pl-col-menu");
  const btn  = document.getElementById("pl-col-menu-btn");
  if (menu && !menu.contains(e.target) && e.target !== btn) menu.style.display = "none";
});

function plToggleCol(col, visible) {
  _plColVisible[col] = visible;
  const idx = _PL_COL_INDEX[col];
  if (idx == null) return;
  document.querySelectorAll(`#pl-table th:nth-child(${idx + 1}), #pl-table td:nth-child(${idx + 1})`).forEach(cell => {
    cell.style.display = visible ? "" : "none";
  });
}

// ── Render player table ───────────────────────────────────────────────────────

function _plRenderTable() {
  const tbody = document.getElementById("pl-tbody");
  if (!tbody) return;
  const colorMap = _plGroupColorMap();

  if (_plFiltered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="13" style="padding:12px;color:var(--muted);text-align:center">No players found.</td></tr>`;
    return;
  }

  const rows = [];
  _plFiltered.forEach(p => {
    const color = colorMap[p.group] || null;
    const groupCell = p.group
      ? `<span class="pl-group-badge" style="background:${color||'#888'}">${escHtml(p.group)}</span>`
      : `<span style="color:var(--muted)">—</span>`;
    const tags    = (p.tags||[]).map(t => `<span class="pl-tag">${escHtml(t)}</span>`).join(" ");
    const aggCell = p.agg_crimes ? `<span class="pl-assign-badge pl-assign-${p.agg_crimes}">${p.agg_crimes}</span>` : "—";
    const cwCell  = p.case_work  ? `<span class="pl-assign-badge pl-assign-${p.case_work}">${p.case_work}</span>`   : "—";
    const expanded = _plExpanded[p.username];
    const isLocal  = _botState.local_players.has(p.username);
    const isOnline = isLocal || _botState.online_players.has(p.username);
    const dot = isLocal  ? `<span title="Online — local" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#32cd32"></span>`
              : isOnline ? `<span title="Online" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#f0c040"></span>`
              : "";

    const careerGrp = _careerGroup(p.occupation);
    const ageCell   = p.character_age ? _fmtAge(p.character_age) : "—";
    const jailAgeCell = p.jail_age ? _fmtAge(p.jail_age) : "—";
    rows.push(`<tr class="pl-data-row${expanded?' pl-row-expanded':''}" onclick="plToggleRow(${escJsStr(p.username)})" style="cursor:pointer">
      <td style="text-align:center">${dot}</td>
      <td><span class="pl-chevron">${expanded?'▾':'▸'}</span> ${escHtml(p.username)}</td>
      <td>${escHtml(p.alias||"")}</td>
      <td>${escHtml(p.rank||"—")}</td>
      <td>${escHtml(p.occupation||"—")}</td>
      <td>${escHtml(careerGrp)}</td>
      <td>${escHtml(p.homecity||"—")}</td>
      <td>${groupCell}</td>
      <td>${tags||"—"}</td>
      <td style="white-space:nowrap">${ageCell}</td>
      <td style="white-space:nowrap">${jailAgeCell}</td>
      <td>${aggCell}</td>
      <td>${cwCell}</td>
      <td style="text-align:center"><input type="checkbox" ${p.monitoring ? 'checked' : ''} onclick="event.stopPropagation();plToggleMonitoring(${escJsStr(p.username)}, this.checked)"></td>
    </tr>`);

    if (expanded) {
      rows.push(`<tr class="pl-detail-row"><td colspan="14"><div class="pl-detail" id="pldetail-${escHtml(p.username)}">${_plDetailHtml(p)}</div></td></tr>`);
    }
  });
  tbody.innerHTML = rows.join("");
}

function plToggleRow(username) {
  _plExpanded[username] = !_plExpanded[username];
  _plRenderTable();
}

function _plDetailHtml(p) {
  const histId    = `plhist-${p.username}`;
  const groupOpts = _plGroups.map(g =>
    `<option value="${escHtml(g.name)}" ${p.group===g.name?'selected':''}>${escHtml(g.name)}</option>`
  ).join("");
  return `
<div class="pl-detail-grid">
  <div class="pl-detail-item"><span class="pl-detail-label">Status</span>${p.active?"Active":"Inactive"}</div>
  <div class="pl-detail-item">
    <span class="pl-detail-label">Alias</span>
    <input type="text" value="${escHtml(p.alias||'')}" onchange="plSetField(${escJsStr(p.username)}, 'alias', this.value)" onclick="event.stopPropagation()" style="width:120px" class="pl-filter-input">
  </div>
  <div class="pl-detail-item"><span class="pl-detail-label">Character Age</span>${_fmtAge(p.character_age||0)}</div>
  <div class="pl-detail-item"><span class="pl-detail-label">Jail Age</span>${_fmtAge(p.jail_age||0)}</div>
  <div class="pl-detail-item">
    <span class="pl-detail-label">Group</span>
    <select onchange="plSetGroup(${escJsStr(p.username)}, this.value, this)" onclick="event.stopPropagation()">
      <option value="">— none —</option>${groupOpts}
    </select>
  </div>
  <div class="pl-detail-item">
    <span class="pl-detail-label">Agg Crimes</span>
    <select onchange="plSetAssignment(${escJsStr(p.username)}, 'agg_crimes', this.value)" onclick="event.stopPropagation()">
      <option value="" ${!p.agg_crimes?'selected':''}>— none —</option>
      <option value="whitelist" ${p.agg_crimes==='whitelist'?'selected':''}>Whitelist</option>
      <option value="blacklist" ${p.agg_crimes==='blacklist'?'selected':''}>Blacklist</option>
    </select>
  </div>
  <div class="pl-detail-item">
    <span class="pl-detail-label">Case Work</span>
    <select onchange="plSetAssignment(${escJsStr(p.username)}, 'case_work', this.value)" onclick="event.stopPropagation()">
      <option value="" ${!p.case_work?'selected':''}>— none —</option>
      <option value="whitelist" ${p.case_work==='whitelist'?'selected':''}>Whitelist</option>
      <option value="blacklist" ${p.case_work==='blacklist'?'selected':''}>Blacklist</option>
    </select>
  </div>
</div>
${p.scraped_at ? `<div class="pl-detail-grid" style="margin-top:6px">
  <div class="pl-detail-item"><span class="pl-detail-label">Sex</span>${escHtml(p.sex||"—")}</div>
  <div class="pl-detail-item"><span class="pl-detail-label">Wealth</span>${escHtml(p.wealth||"—")}</div>
  <div class="pl-detail-item"><span class="pl-detail-label">Scripting</span>${escHtml(p.scripting||"—")}</div>
</div>` : ''}
<button class="btn-secondary" id="plupdate-${escHtml(p.username)}" style="margin-top:6px"
        onclick="plUpdatePlayer(${escJsStr(p.username)}, this); event.stopPropagation()">Update</button>
<div class="pl-detail-item" style="margin-top:6px">
  <span class="pl-detail-label">Notes</span>
  <textarea rows="3" style="max-width:400px;width:100%;resize:vertical;font-size:0.85rem" class="pl-filter-input"
    onclick="event.stopPropagation()"
    onchange="plSetField(${escJsStr(p.username)}, 'notes', this.value)">${escHtml(p.notes||'')}</textarea>
</div>
<div class="pl-history-toggle" onclick="plLoadHistory(${escJsStr(p.username)}, '${histId}', this); event.stopPropagation()">
  ▸ Show Career History
</div>
<div id="${histId}" style="display:none"></div>`;
}

function plUpdatePlayer(username, btn) {
  if (!_botRunning) { alert("Bot is not running."); return; }
  const prevScrapedAt = (_plData.find(p => p.username === username) || {}).scraped_at;
  if (btn) { btn.disabled = true; btn.textContent = "Updating…"; }
  fetch(`/players/${encodeURIComponent(username)}/scrape`, {method: "POST"})
    .then(r => r.json())
    .then(d => {
      if (d.error) {
        alert(d.error);
        if (btn) { btn.disabled = false; btn.textContent = "Update"; }
        return;
      }
      _plPollForScrapeUpdate(username, prevScrapedAt, btn, 0);
    })
    .catch(() => { if (btn) { btn.disabled = false; btn.textContent = "Update"; } });
}

function _plPollForScrapeUpdate(username, prevScrapedAt, btn, attempt) {
  fetch("/api/players").then(r => r.json()).then(d => {
    const players = d.players || [];
    const p = players.find(pl => pl.username === username);
    const updated = p && p.scraped_at && p.scraped_at !== prevScrapedAt;
    if (updated || attempt >= 15) {
      loadPlayers();
      return;
    }
    setTimeout(() => _plPollForScrapeUpdate(username, prevScrapedAt, btn, attempt + 1), 2000);
  }).catch(() => {
    if (btn) { btn.disabled = false; btn.textContent = "Update"; }
  });
}

function plLoadHistory(username, containerId, toggleEl) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (container.style.display !== "none") {
    container.style.display = "none";
    if (toggleEl) toggleEl.textContent = "▸ Show Career History";
    return;
  }
  if (container.dataset.loaded) {
    container.style.display = "block";
    if (toggleEl) toggleEl.textContent = "▾ Hide Career History";
    return;
  }
  container.innerHTML = '<p style="color:var(--muted);padding:8px">Loading…</p>';
  container.style.display = "block";
  if (toggleEl) toggleEl.textContent = "▾ Hide Career History";
  fetch(`/api/players/${encodeURIComponent(username)}/history`)
    .then(r => r.json())
    .then(resp => {
      const rows = resp.history ?? resp;
      if (!rows.length) {
        container.innerHTML = '<p style="color:var(--muted);padding:8px">No history.</p>';
        return;
      }
      container.innerHTML = `
<table class="pl-history-table">
  <thead><tr><th>Occupation</th><th>Rank</th><th>City</th><th>Date</th></tr></thead>
  <tbody>${rows.map(r => `<tr>
    <td>${escHtml(r.occupation||"")}</td><td>${escHtml(r.rank||"")}</td>
    <td>${escHtml(r.homecity||"")}</td><td>${escHtml((r.ts||"").replace(/^\d{4}-/,"").replace(/T/," ").replace(/:\d{2}Z$/,""))}</td>
  </tr>`).join("")}</tbody>
</table>`;
      container.dataset.loaded = "1";
    })
    .catch(() => { container.innerHTML = '<p style="color:var(--muted);padding:8px">Failed to load.</p>'; });
}

// ── Obituaries ────────────────────────────────────────────────────────────────

let _plDeadSort = { col: "died_at", asc: false };
let _plDeadExpanded = {};

function plDeadSort(col) {
  if (_plDeadSort.col === col) _plDeadSort.asc = !_plDeadSort.asc;
  else { _plDeadSort.col = col; _plDeadSort.asc = true; }
  plRenderRecentDead();
}

function plRenderRecentDead() {
  const tbody = document.getElementById("pl-dead-tbody");
  if (!tbody) return;
  const cutoff = Date.now() - 3 * 24 * 3600 * 1000;

  const search = (document.getElementById("pl-dead-search")?.value || "").toLowerCase();
  const rankF  = document.getElementById("pl-dead-filter-rank")?.value || "";
  const occF   = document.getElementById("pl-dead-filter-occupation")?.value || "";
  const cityF  = document.getElementById("pl-dead-filter-homecity")?.value || "";

  let rows = (_plData || []).filter(p => {
    if (p.active) return false;
    if (!p.died_at) return false;
    if (new Date(p.died_at).getTime() < cutoff) return false;
    if (search && !p.username.toLowerCase().includes(search)) return false;
    if (rankF && p.rank !== rankF) return false;
    if (occF  && p.occupation !== occF) return false;
    if (cityF && p.homecity !== cityF) return false;
    return true;
  });

  // Populate filter dropdowns on first call
  _plPopulateDeadFilters((_plData || []).filter(p => !p.active && p.died_at && new Date(p.died_at).getTime() >= cutoff));

  const { col, asc } = _plDeadSort;
  rows.sort((a, b) => {
    const av = col === "died_at" ? (new Date(a.died_at).getTime()) : col === "character_age" ? (a.character_age || 0) : (a[col] || "").toLowerCase();
    const bv = col === "died_at" ? (new Date(b.died_at).getTime()) : col === "character_age" ? (b.character_age || 0) : (b[col] || "").toLowerCase();
    if (typeof av === "number") return asc ? av - bv : bv - av;
    return asc ? av.localeCompare(bv) : bv.localeCompare(av);
  });

  document.querySelectorAll("#pl-dead-table .pl-sort-icon").forEach(el => { el.textContent = "↕"; el.classList.remove("pl-th-sorted"); });
  const icon = document.getElementById(`pl-dead-icon-${col}`);
  if (icon) { icon.textContent = asc ? "▲" : "▼"; icon.classList.add("pl-th-sorted"); }

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="padding:12px;color:var(--text-muted);text-align:center">No deaths in the last 3 days.</td></tr>`;
    return;
  }

  const colorMap = _plGroupColorMap();
  tbody.innerHTML = rows.map(p => {
    const diedDate = new Date(p.died_at).toLocaleString();
    const expanded = _plDeadExpanded[p.username];
    const groupCell = p.group
      ? `<span class="pl-group-badge" style="background:${colorMap[p.group]||'#888'}">${escHtml(p.group)}</span>`
      : "";
    const rows2 = [`<tr class="pl-data-row${expanded?' pl-row-expanded':''}" onclick="_plDeadToggle(${escJsStr(p.username)})" style="cursor:pointer">
      <td><span class="pl-chevron">${expanded?'▾':'▸'}</span> ${escHtml(p.username)} ${groupCell}</td>
      <td>${escHtml(p.rank||"—")}</td>
      <td>${escHtml(p.occupation||"—")}</td>
      <td>${escHtml(p.homecity||"—")}</td>
      <td style="white-space:nowrap;font-size:11px;color:var(--text-muted)">${p.character_age ? _fmtAge(p.character_age) : "—"}</td>
      <td style="white-space:nowrap">${escHtml(diedDate)}</td>
    </tr>`];
    if (expanded) rows2.push(`<tr class="pl-detail-row"><td colspan="6"><div class="pl-detail">${_plDetailHtml(p)}</div></td></tr>`);
    return rows2.join("");
  }).join("");
}

function _plDeadToggle(username) {
  _plDeadExpanded[username] = !_plDeadExpanded[username];
  plRenderRecentDead();
}

function _plPopulateDeadFilters(source) {
  const uniq = col => [...new Set(source.map(p => p[col] || "").filter(Boolean))].sort();
  [
    { id: "pl-dead-filter-rank",       col: "rank" },
    { id: "pl-dead-filter-occupation", col: "occupation" },
    { id: "pl-dead-filter-homecity",   col: "homecity" },
  ].forEach(({ id, col }) => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = `<option value="">All</option>` + uniq(col).map(v => `<option value="${escHtml(v)}">${escHtml(v)}</option>`).join("");
    if (cur && [...sel.options].some(o => o.value === cur)) sel.value = cur;
  });
}

// ── Births ────────────────────────────────────────────────────────────────────

let _plBornSort = { col: "born_at", asc: false };
let _plBornExpanded = {};

function plBornSort(col) {
  if (_plBornSort.col === col) _plBornSort.asc = !_plBornSort.asc;
  else { _plBornSort.col = col; _plBornSort.asc = true; }
  plRenderRecentBorn();
}

function plRenderRecentBorn() {
  const tbody = document.getElementById("pl-born-tbody");
  if (!tbody) return;
  const cutoff = Date.now() - 3 * 24 * 3600 * 1000;

  const search = (document.getElementById("pl-born-search")?.value || "").toLowerCase();
  const rankF  = document.getElementById("pl-born-filter-rank")?.value || "";
  const occF   = document.getElementById("pl-born-filter-occupation")?.value || "";
  const cityF  = document.getElementById("pl-born-filter-homecity")?.value || "";

  let rows = (_plData || []).filter(p => {
    if (!p.born_at) return false;
    if (new Date(p.born_at).getTime() < cutoff) return false;
    if (search && !p.username.toLowerCase().includes(search)) return false;
    if (rankF && p.rank !== rankF) return false;
    if (occF  && p.occupation !== occF) return false;
    if (cityF && p.homecity !== cityF) return false;
    return true;
  });

  _plPopulateBornFilters((_plData || []).filter(p => p.born_at && new Date(p.born_at).getTime() >= cutoff));

  const { col, asc } = _plBornSort;
  rows.sort((a, b) => {
    const av = col === "born_at" ? (new Date(a.born_at).getTime()) : col === "character_age" ? (a.character_age || 0) : (a[col] || "").toLowerCase();
    const bv = col === "born_at" ? (new Date(b.born_at).getTime()) : col === "character_age" ? (b.character_age || 0) : (b[col] || "").toLowerCase();
    if (typeof av === "number") return asc ? av - bv : bv - av;
    return asc ? av.localeCompare(bv) : bv.localeCompare(av);
  });

  document.querySelectorAll("#pl-born-table .pl-sort-icon").forEach(el => { el.textContent = "↕"; el.classList.remove("pl-th-sorted"); });
  const icon = document.getElementById(`pl-born-icon-${col}`);
  if (icon) { icon.textContent = asc ? "▲" : "▼"; icon.classList.add("pl-th-sorted"); }

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="padding:12px;color:var(--text-muted);text-align:center">No new players in the last 3 days.</td></tr>`;
    return;
  }

  const colorMap = _plGroupColorMap();
  tbody.innerHTML = rows.map(p => {
    const bornDate = new Date(p.born_at).toLocaleString();
    const expanded = _plBornExpanded[p.username];
    const groupCell = p.group
      ? `<span class="pl-group-badge" style="background:${colorMap[p.group]||'#888'}">${escHtml(p.group)}</span>`
      : "";
    const rows2 = [`<tr class="pl-data-row${expanded?' pl-row-expanded':''}" onclick="_plBornToggle(${escJsStr(p.username)})" style="cursor:pointer">
      <td><span class="pl-chevron">${expanded?'▾':'▸'}</span> ${escHtml(p.username)} ${groupCell}</td>
      <td>${escHtml(p.rank||"—")}</td>
      <td>${escHtml(p.occupation||"—")}</td>
      <td>${escHtml(p.homecity||"—")}</td>
      <td style="white-space:nowrap;font-size:11px;color:var(--text-muted)">${p.character_age ? _fmtAge(p.character_age) : "—"}</td>
      <td style="white-space:nowrap">${escHtml(bornDate)}</td>
    </tr>`];
    if (expanded) rows2.push(`<tr class="pl-detail-row"><td colspan="6"><div class="pl-detail">${_plDetailHtml(p)}</div></td></tr>`);
    return rows2.join("");
  }).join("");
}

function _plBornToggle(username) {
  _plBornExpanded[username] = !_plBornExpanded[username];
  plRenderRecentBorn();
}

function _plPopulateBornFilters(source) {
  const uniq = col => [...new Set(source.map(p => p[col] || "").filter(Boolean))].sort();
  [
    { id: "pl-born-filter-rank",       col: "rank" },
    { id: "pl-born-filter-occupation", col: "occupation" },
    { id: "pl-born-filter-homecity",   col: "homecity" },
  ].forEach(({ id, col }) => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = `<option value="">All</option>` + uniq(col).map(v => `<option value="${escHtml(v)}">${escHtml(v)}</option>`).join("");
    if (cur && [...sel.options].some(o => o.value === cur)) sel.value = cur;
  });
}

// ── Top Jobs tab ─────────────────────────────────────────────────────────────

function plLoadTopJobs() {
  const container = document.getElementById("pl-topjobs-content");
  if (!container) return;
  container.innerHTML = '<p style="padding:12px;color:var(--text-muted);text-align:center">Loading…</p>';
  fetch("/api/players/top_jobs")
    .then(r => r.json())
    .then(data => {
      const holders = data.holders || [];
      const jobs = data.jobs || [];
      // Group by city
      const cities = {};
      holders.forEach(h => {
        const city = h.homecity || "Unknown";
        if (!cities[city]) cities[city] = {};
        cities[city][h.occupation] = h;
      });
      const cityNames = Object.keys(cities).sort();
      if (!cityNames.length) {
        container.innerHTML = '<p style="padding:12px;color:var(--text-muted);text-align:center">No top job holders found in player database.</p>';
        return;
      }
      let html = '<div style="display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(340px,1fr))">';
      cityNames.forEach(city => {
        html += `<div style="background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px 16px">
          <h3 style="margin:0 0 10px;font-size:1rem;color:var(--accent)">${escHtml(city)}</h3>
          <table style="width:100%;font-size:0.85rem;border-collapse:collapse">
            <thead><tr style="border-bottom:1px solid var(--border)">
              <th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-weight:500">Job</th>
              <th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-weight:500">Holder</th>
              <th style="text-align:left;padding:4px 6px;color:var(--text-muted);font-weight:500">Duration</th>
            </tr></thead><tbody>`;
        jobs.forEach(job => {
          const h = cities[city][job];
          const expandId = `tjexp-${escHtml(city)}-${escHtml(job)}`.replace(/\s+/g, '_');
          if (h) {
            const since = h.duration_secs != null ? _topJobDuration(h.duration_secs) : "—";
            html += `<tr style="border-bottom:1px solid var(--border);cursor:pointer" onclick="_tjToggleCareer('${expandId}', ${escJsStr(job)}, ${escJsStr(city)})">
              <td style="padding:4px 6px">${escHtml(job)}</td>
              <td style="padding:4px 6px;font-weight:500">${escHtml(h.username)}</td>
              <td style="padding:4px 6px;color:var(--text-muted);white-space:nowrap">${since}</td>
            </tr>
            <tr id="${expandId}" style="display:none"><td colspan="3" style="padding:0"></td></tr>`;
          } else {
            html += `<tr style="border-bottom:1px solid var(--border)">
              <td style="padding:4px 6px">${escHtml(job)}</td>
              <td style="padding:4px 6px;color:var(--text-muted)">Vacant</td>
              <td style="padding:4px 6px"></td>
            </tr>`;
          }
        });
        html += '</tbody></table></div>';
      });
      html += '</div>';
      container.innerHTML = html;
    })
    .catch(() => {
      container.innerHTML = '<p style="padding:12px;color:var(--error);text-align:center">Failed to load top jobs.</p>';
    });
}

function _topJobDuration(secs) {
  if (secs == null || secs < 0) return "—";
  const days = Math.floor(secs / 86400);
  const hours = Math.floor((secs % 86400) / 3600);
  if (days < 1) return hours + "h";
  return days + "d " + hours + "h";
}

function _tjToggleCareer(expandId, occupation, city) {
  const row = document.getElementById(expandId);
  if (!row) return;
  if (row.style.display !== 'none') { row.style.display = 'none'; return; }
  const cell = row.querySelector('td');
  cell.innerHTML = '<div style="padding:4px 6px 8px;color:var(--text-muted);font-size:0.8rem">Loading…</div>';
  row.style.display = '';
  fetch(`/api/players/career_group?occupation=${encodeURIComponent(occupation)}&city=${encodeURIComponent(city)}`)
    .then(r => r.json())
    .then(data => {
      const players = data.players || [];
      if (!players.length) {
        cell.innerHTML = '<div style="padding:4px 6px 8px 20px;color:var(--text-muted);font-size:0.8rem">No other players in this career path.</div>';
        return;
      }
      let html = '<div style="padding:2px 6px 8px 20px;font-size:0.8rem">';
      players.forEach(p => {
        html += `<div style="padding:2px 0"><span style="color:var(--text-muted)">${escHtml(p.occupation)}</span> — <span style="font-weight:500">${escHtml(p.username)}</span></div>`;
      });
      html += '</div>';
      cell.innerHTML = html;
    })
    .catch(() => { cell.innerHTML = '<div style="padding:4px 6px 8px 20px;color:var(--error);font-size:0.8rem">Failed to load.</div>'; });
}

// ── Assignments & groups ──────────────────────────────────────────────────────

function plSetAssignment(username, context, value) {
  fetch("/players/assign", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({username, context, value}),
  }).then(() => {
    const p = _plData.find(x => x.username === username);
    if (p) p[context] = value;
    _plRenderTable();
  }).catch(() => {});
}

function plSetField(username, field, value) {
  fetch("/players/set_field", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({username, field, value}),
  }).then(() => {
    const p = _plData.find(x => x.username === username);
    if (p) p[field] = value;
    _plRenderTable();
  }).catch(() => {});
}

function plSetGroup(username, group, el) {
  fetch("/players/set_group", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({username, group}),
  }).then(() => {
    const p = _plData.find(x => x.username === username);
    if (p) p.group = group;
    _plRenderTable();
  }).catch(() => {});
}

function plBoldsToggleChanged() {
  const on = document.getElementById("pl-bolds-toggle")?.checked;
  if (on) _plRunWhitelistBolds();
}

function _plRunWhitelistBolds() {
  fetch("/players/whitelist_bolds", {method: "POST"})
    .then(r => r.json())
    .then(d => { if (d.newly > 0) loadPlayers(); })
    .catch(() => {});
}

function plToggleMonitoring(username, on) {
  fetch("/toggle-monitoring", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({username, on}),
  }).then(() => {
    const p = _plData.find(x => x.username === username);
    if (p) p.monitoring = on ? 1 : 0;
  }).catch(() => {});
}

function plScrapePlayers() {
  if (!_botRunning) { alert("Bot is not running."); return; }
  const overlay = document.getElementById("pl-scrape-overlay");
  if (overlay) overlay.style.display = "flex";
}

function plScrapeConfirm() {
  const overlay = document.getElementById("pl-scrape-overlay");
  if (overlay) overlay.style.display = "none";
  fetch("/scrape-players", {method: "POST"}).catch(() => {});
}

function plScrapeCancel() {
  const overlay = document.getElementById("pl-scrape-overlay");
  if (overlay) overlay.style.display = "none";
}

// ── Refresh & import ──────────────────────────────────────────────────────────

// Relocate the jail General controls between the Settings→Jail tab and the
// Income→Jail tab depending on whether the character is in jail.
function _syncJailTab(inJail) {
  // Jail tab is always available under Income; the jail General controls live there.
  const btn = document.getElementById("income-tab-jail-btn");
  const group = document.getElementById("jail-general-group");
  const mount = document.getElementById("income-jail-mount");
  if (!btn || !group || !mount) return;
  if (group.parentElement !== mount) mount.appendChild(group);
  btn.style.display = "";
}

function loadAutoJailPartners() {
  const sel = document.getElementById("auto_jail_partner");
  if (!sel) return;
  const current = sel.dataset.current || sel.value || "";
  fetch("/jail/partner_candidates")
    .then(r => r.json())
    .then(d => {
      const names = d.partners || [];
      // Keep the saved partner selectable even if not in the current candidate list.
      if (current && !names.includes(current)) names.unshift(current);
      const opts = ['<option value="">— none —</option>']
        .concat(names.map(n => `<option value="${escHtml(n)}"${n === current ? " selected" : ""}>${escHtml(n)}</option>`));
      sel.innerHTML = opts.join("");
      sel.value = current;
    })
    .catch(() => {});
}

function triggerAutoJailCheck() {
  const btn = document.getElementById("auto-jail-check-btn");
  const status = document.getElementById("auto-jail-check-status");
  if (btn) btn.disabled = true;
  if (status) status.textContent = "Checking…";
  fetch("/jail/auto_jail_check", {method: "POST"})
    .then(r => r.json())
    .then(d => {
      if (status) status.textContent = d.ok ? "Triggered — see activity log." : (d.error || "Failed.");
    })
    .catch(() => { if (status) status.textContent = "Request failed."; })
    .finally(() => { setTimeout(() => { if (btn) btn.disabled = false; }, 2000); });
}

function plRefresh() {
  const btn    = document.getElementById("pl-refresh-btn");
  const status = document.getElementById("pl-refresh-status");
  if (btn) { btn.disabled = true; btn.textContent = "Refreshing…"; }
  if (status) status.textContent = "";
  fetch("/players/refresh", {method: "POST"})
    .then(r => r.json())
    .then(d => {
      if (btn) { btn.disabled = false; btn.textContent = "Refresh"; }
      if (d.error) { if (status) status.textContent = d.error; return; }
      loadPlayers();
      if (document.getElementById("pl-bolds-toggle")?.checked) _plRunWhitelistBolds();
    })
    .catch(() => {
      if (btn) { btn.disabled = false; btn.textContent = "Refresh"; }
      if (status) status.textContent = "Refresh failed.";
    });
}

function plRunImport() {
  const textarea = document.getElementById("pl-import-text");
  const context  = document.getElementById("pl-import-context")?.value;
  const assign   = document.getElementById("pl-import-assignment")?.value;
  const btn      = document.querySelector("#pl-tab-import .action-btn");
  if (!textarea || !context || !assign) return;
  const names = textarea.value.split("\n").map(s => s.trim()).filter(Boolean);
  if (!names.length) return;
  if (btn) { btn.disabled = true; btn.textContent = "Importing…"; }
  fetch("/players/import", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({names, context, assignment: assign}),
  }).then(r => r.json())
    .then(d => {
      loadPlayers();
      if (btn) { btn.disabled = false; btn.textContent = "Import"; }
      textarea.value = "";
      const report = document.getElementById("pl-import-report");
      if (report) {
        report.style.display = "block";
        report.textContent = `Assigned ${d.assigned} player(s). Unmatched: ${(d.unmatched||[]).join(", ")||"none"}`;
      }
    })
    .catch(() => { if (btn) { btn.disabled = false; btn.textContent = "Import"; } });
}

// ── Groups tab ────────────────────────────────────────────────────────────────

let _plGroupExpanded = {};

function _plColorSelect(selected, onchange) {
  const opts = [
    ["#e74c3c","Red"],["#e67e22","Orange"],["#f1c40f","Yellow"],
    ["#2ecc71","Green"],["#3498db","Blue"],["#9b59b6","Purple"],
    ["#e91e8c","Pink"],["#1abc9c","Teal"],["#aaaaaa","Light Grey"],["#555555","Dark Grey"],
  ].map(([v,l]) => `<option value="${v}" ${selected===v?'selected':''}>&#9679; ${l}</option>`).join("");
  return `<select class="pl-filter-input pl-color-select" style="--pl-sel-color:${selected||'#3498db'}"
    onchange="${onchange};this.style.setProperty('--pl-sel-color',this.value)">${opts}</select>`;
}

function _plRenderGroupsTab(groups) {
  const tbody = document.getElementById("pl-groups-tbody");
  if (!tbody) return;
  if (!groups || !groups.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="padding:12px;color:var(--muted);text-align:center">No groups yet.</td></tr>`;
    return;
  }

  const TRASH = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>`;
  const EDIT  = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`;

  const rows = [];
  groups.forEach(g => {
    const aggSel = ["","whitelist","blacklist"].map(v =>
      `<option value="${v}" ${g.agg_crimes===v?'selected':''}>${v||"—"}</option>`).join("");
    const cwSel = ["","whitelist","blacklist"].map(v =>
      `<option value="${v}" ${g.case_work===v?'selected':''}>${v||"—"}</option>`).join("");
    const typeSel = ["neutral","friendly","enemy"].map(v =>
      `<option value="${v}" ${g.type===v?'selected':''}>${v.charAt(0).toUpperCase()+v.slice(1)}</option>`).join("");
    const colorSel = _plColorSelect(g.color, `plUpdateGroupColor(${escJsStr(g.name)}, this.value)`);
    const expanded = _plGroupExpanded[g.name];

    rows.push(`<tr class="pl-data-row${expanded?' pl-row-expanded':''}" onclick="plToggleGroup(${escJsStr(g.name)})" style="cursor:pointer">
      <td><span class="pl-chevron">${expanded?'▾':'▸'}</span> ${escHtml(g.name)}</td>
      <td onclick="event.stopPropagation()">
        <select class="pl-filter-input" onchange="plUpdateGroupType(${escJsStr(g.name)}, this.value)">${typeSel}</select>
      </td>
      <td onclick="event.stopPropagation()">${colorSel}</td>
      <td onclick="event.stopPropagation()">
        <select class="pl-filter-input" onchange="plUpdateGroupAssignment(${escJsStr(g.name)}, 'agg_crimes', this.value)">${aggSel}</select>
      </td>
      <td onclick="event.stopPropagation()">
        <select class="pl-filter-input" onchange="plUpdateGroupAssignment(${escJsStr(g.name)}, 'case_work', this.value)">${cwSel}</select>
      </td>
      <td>${g.member_count||0}</td>
      <td style="white-space:nowrap">
        <button class="pl-icon-btn" title="Edit group" onclick="event.stopPropagation();plOpenEditGroupModal(${escJsStr(g.name)})">${EDIT}</button>
        <button class="pl-icon-btn pl-icon-btn-danger" title="Delete group" onclick="event.stopPropagation();plOpenDeleteModal(${escJsStr(g.name)})">${TRASH}</button>
      </td>
    </tr>`);

    if (expanded) {
      rows.push(`<tr class="pl-detail-row"><td colspan="7">
        <div class="pl-detail" id="plgdetail-${escHtml(g.name)}">
          <div id="plgmembers-${escHtml(g.name)}" style="color:var(--muted);font-size:0.83rem">Loading…</div>
        </div>
      </td></tr>`);
    }
  });
  tbody.innerHTML = rows.join("");
  groups.forEach(g => { if (_plGroupExpanded[g.name]) _plLoadGroupMembers(g.name); });
}



function plToggleGroup(name) {
  _plGroupExpanded[name] = !_plGroupExpanded[name];
  _plRenderGroupsTab(_plGroups);
}

function _plLoadGroupMembers(groupName) {
  const container = document.getElementById(`plgmembers-${groupName}`);
  if (!container) return;
  fetch(`/api/players/group/${encodeURIComponent(groupName)}`)
    .then(r => r.json())
    .then(data => {
      // Re-query — table may have been re-rendered while fetch was in flight
      const el = document.getElementById(`plgmembers-${groupName}`);
      if (!el) return;
      const members = (data.players || []).map(p => ({ ...p, group: p.group_name ?? "" }));
      if (!members.length) {
        el.innerHTML = '<p style="color:var(--muted);padding:4px 0">No members.</p>';
        return;
      }
      const colorMap = _plGroupColorMap();
      el.innerHTML = `<table class="pl-history-table" style="width:100%">
        <thead><tr>
          <th>Name</th><th>Rank</th><th>Occupation</th><th>City</th>
          <th>Agg (individual)</th><th>Case Work (individual)</th>
        </tr></thead>
        <tbody>${members.map(p => {
          const aggBadge = p.agg_crimes ? `<span class="pl-assign-badge pl-assign-${p.agg_crimes}">${p.agg_crimes}</span>` : "—";
          const cwBadge  = p.case_work  ? `<span class="pl-assign-badge pl-assign-${p.case_work}">${p.case_work}</span>`   : "—";
          return `<tr>
            <td>${escHtml(p.username)}</td>
            <td>${escHtml(p.rank||"—")}</td>
            <td>${escHtml(p.occupation||"—")}</td>
            <td>${escHtml(p.homecity||"—")}</td>
            <td>${aggBadge}</td><td>${cwBadge}</td>
          </tr>`;
        }).join("")}</tbody>
      </table>`;
    })
    .catch(() => {
      const el = document.getElementById(`plgmembers-${groupName}`);
      if (el) el.innerHTML = '<p style="color:var(--muted)">Failed to load.</p>';
    });
}

function plCreateGroup() {
  const nameEl  = document.getElementById("pl-new-group-name");
  const typeEl  = document.getElementById("pl-new-group-type");
  const colorEl = document.getElementById("pl-new-group-color");
  const errEl   = document.getElementById("pl-group-create-error");
  const name    = nameEl?.value.trim();
  const color   = colorEl?.value || "#3498db";
  const type    = typeEl?.value || "neutral";
  if (!name) return;
  fetch("/players/groups/create", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name, color, group_type: type}),
  }).then(r => r.json())
    .then(d => {
      if (!d.ok) { if (errEl) errEl.textContent = d.error || "Error"; return; }
      if (errEl) errEl.textContent = "";
      if (nameEl) nameEl.value = "";
      loadPlayers();
    })
    .catch(() => {});
}

// ── Delete modal ──────────────────────────────────────────────────────────────
function plOpenDeleteModal(name) {
  const modal = document.getElementById("pl-delete-modal");
  const msg   = document.getElementById("pl-delete-modal-msg");
  const btn   = document.getElementById("pl-delete-modal-confirm");
  if (!modal) return;
  msg.textContent = `Are you sure you want to delete "${name}"? This cannot be undone.`;
  btn.onclick = () => {
    fetch("/players/groups/delete", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name}),
    }).then(() => { plCloseDeleteModal(); loadPlayers(); }).catch(() => {});
  };
  modal.style.display = "flex";
}
function plCloseDeleteModal() {
  const m = document.getElementById("pl-delete-modal");
  if (m) m.style.display = "none";
}

// ── Edit group modal ──────────────────────────────────────────────────────────
let _plEditGroupOriginalName = "";

function plOpenEditGroupModal(groupName) {
  const modal   = document.getElementById("pl-editgroup-modal");
  const nameEl  = document.getElementById("pl-editgroup-name");
  const colorEl = document.getElementById("pl-editgroup-color");
  const membersEl = document.getElementById("pl-editgroup-members");
  const resultEl  = document.getElementById("pl-editgroup-result");
  const btn     = document.getElementById("pl-editgroup-confirm");
  if (!modal) return;

  _plEditGroupOriginalName = groupName;
  const g = _plGroups.find(x => x.name === groupName);
  if (nameEl) nameEl.value = groupName;
  if (colorEl && g) {
    colorEl.value = g.color || "#3498db";
    colorEl.style.setProperty("--pl-sel-color", colorEl.value);
  }
  if (membersEl) membersEl.value = "Loading…";
  if (resultEl) resultEl.textContent = "";
  if (btn) btn.onclick = () => _plDoEditGroup(_plEditGroupOriginalName);

  modal.style.display = "flex";

  // Pre-fill members
  fetch(`/api/players/group/${encodeURIComponent(groupName)}`)
    .then(r => r.json())
    .then(data => {
      const names = (data.players || []).map(p => p.username);
      if (membersEl) membersEl.value = names.join("\n");
      setTimeout(() => nameEl?.select(), 50);
    })
    .catch(() => { if (membersEl) membersEl.value = ""; });
}

function plCloseEditGroupModal() {
  const m = document.getElementById("pl-editgroup-modal");
  if (m) m.style.display = "none";
}

function _plDoEditGroup(originalName) {
  const nameEl    = document.getElementById("pl-editgroup-name");
  const colorEl   = document.getElementById("pl-editgroup-color");
  const membersEl = document.getElementById("pl-editgroup-members");
  const resultEl  = document.getElementById("pl-editgroup-result");
  const btn       = document.getElementById("pl-editgroup-confirm");

  const newName = (nameEl?.value || "").trim();
  const newColor = colorEl?.value || "#3498db";
  const names = (membersEl?.value || "").split("\n").map(s => s.trim()).filter(Boolean);

  if (!newName) { if (resultEl) resultEl.textContent = "Name cannot be empty."; return; }
  if (btn) { btn.disabled = true; btn.textContent = "Saving…"; }

  const steps = [];

  // Rename if changed
  if (newName !== originalName) {
    steps.push(fetch("/players/groups/rename", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({old_name: originalName, new_name: newName}),
    }).then(r => r.json()).then(d => {
      if (!d.ok) throw new Error(d.error || "Rename failed");
    }));
  }

  // Colour update
  const g = _plGroups.find(x => x.name === originalName);
  if (!g || newColor !== g.color) {
    steps.push(fetch("/players/groups/update_color", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name: newName !== originalName ? newName : originalName, color: newColor}),
    }));
  }

  Promise.all(steps)
    .then(() => {
      // Set members — set everyone in textarea to this group; remove anyone currently in group but not in textarea
      const targetGroupName = newName !== originalName ? newName : originalName;
      const knownLower = new Map(_plData.map(p => [p.username.toLowerCase(), p.username]));
      const wantedLower = new Set(names.map(n => n.toLowerCase()));

      const g2 = _plGroups.find(x => x.name === originalName);
      // Current members come from _plData
      const currentMembers = _plData.filter(p => p.group === originalName).map(p => p.username);

      const toAdd    = names.map(n => knownLower.get(n.toLowerCase())).filter(Boolean);
      const toRemove = currentMembers.filter(u => !wantedLower.has(u.toLowerCase()));

      const memberOps = [
        ...toAdd.map(username => fetch("/players/set_group", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({username, group: targetGroupName}),
        })),
        ...toRemove.map(username => fetch("/players/set_group", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({username, group: ""}),
        })),
      ];
      return Promise.all(memberOps);
    })
    .then(() => {
      if (btn) { btn.disabled = false; btn.textContent = "Save"; }
      plCloseEditGroupModal();
      loadPlayers();
    })
    .catch(e => {
      if (btn) { btn.disabled = false; btn.textContent = "Save"; }
      if (resultEl) resultEl.textContent = String(e);
    });
}



function plUpdateGroupColor(name, color) {
  fetch("/players/groups/update_color", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name, color}),
  }).then(() => {
    const g = _plGroups.find(x => x.name === name);
    if (g) g.color = color;
    _plRenderGroupsTab(_plGroups);
  }).catch(() => {});
}

function plUpdateGroupType(name, group_type) {
  fetch("/players/groups/update_type", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name, group_type}),
  }).then(() => {
    const g = _plGroups.find(x => x.name === name);
    if (g) g.type = group_type;
  }).catch(() => {});
}

function plUpdateGroupAssignment(name, context, value) {
  fetch("/players/groups/update_assignment", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name, context, value}),
  }).then(() => {
    const g = _plGroups.find(x => x.name === name);
    if (g) g[context] = value;
  }).catch(() => {});
}

// ── Notifications ─────────────────────────────────────────────────────────────

let _notifPanelOpen = false;

function _updateNotifBell(notifs) {
  const bell = document.getElementById("notif-bell");
  const badge = document.getElementById("notif-badge");
  const panel = document.getElementById("notif-panel");
  if (!bell) return;
  if (notifs.length > 0) {
    badge.textContent = notifs.length;
    // Bell is visible only when collapsed; when expanded the panel replaces it.
    bell.style.display = _notifPanelOpen ? "none" : "";
  } else {
    bell.style.display = "none";
    _notifPanelOpen = false;
    if (panel) panel.style.display = "none";
  }
  if (_notifPanelOpen) _renderNotifList(notifs);
}

function toggleNotifPanel() {
  const panel = document.getElementById("notif-panel");
  const bell = document.getElementById("notif-bell");
  if (!panel) return;
  _notifPanelOpen = !_notifPanelOpen;
  panel.style.display = _notifPanelOpen ? "" : "none";   // expand into full section
  if (bell) bell.style.display = _notifPanelOpen ? "none" : "";  // collapse back to bell
}

function _renderNotifList(notifs) {
  const list = document.getElementById("notif-list");
  if (!list) return;
  if (!notifs.length) { list.innerHTML = ""; return; }
  list.innerHTML = notifs.map(n => {
    const extra = n.event_type === "warrants_outstanding"
      ? `<button class="btn-secondary" style="font-size:11px;padding:2px 8px;margin-top:4px" onclick="clearWarrantCooldown('${escHtml(n.id)}')">Clear Cooldown</button>`
      : "";
    return `
    <div class="notif-item">
      <div class="notif-item-body">
        <span class="notif-ts">${escHtml(n.ts)}</span>
        <span class="notif-msg">${escHtml(n.message)}</span>
        ${extra}
      </div>
      <button class="notif-dismiss-btn" onclick="dismissNotif('${escHtml(n.id)}')" title="Dismiss">✕</button>
    </div>`;
  }).join("");
}

function dismissNotif(id) {
  fetch("/notifications/dismiss", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({id}),
  }).catch(() => {});
}

function clearAllNotifs() {
  fetch("/notifications/clear", {method: "POST"}).catch(() => {});
}

function clearWarrantCooldown(notifId) {
  fetch("/travel/clear-warrant-cooldown", {method: "POST"}).catch(() => {});
  dismissNotif(notifId);
}

function _collectNotifSettings() {
  const out = {};
  document.querySelectorAll('input[id^="notif_"]').forEach(el => {
    out[el.id] = el.checked;
  });
  return out;
}

function navigateTo(url) {
  fetch("/navigate", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({url}),
  })
    .then(r => r.json())
    .then(d => { if (d.error) alert(d.error); })
    .catch(e => alert(String(e)));
}

let _profileLoading = false;
function loadProfile() {
  const el = document.getElementById("profile-content");
  if (!el || _profileLoading) return;
  _profileLoading = true;
  el.classList.add("profile-refreshing");
  fetch("/profile")
    .then(r => r.json())
    .then(d => {
      _profileLoading = false;
      el.classList.remove("profile-refreshing");
      if (d.error) { el.innerHTML = `<span class="error">${escHtml(d.error)}</span>`; return; }
      el.innerHTML = _renderProfile(d);
    })
    .catch(e => {
      _profileLoading = false;
      el.classList.remove("profile-refreshing");
      el.innerHTML = `<span class="error">${escHtml(String(e))}</span>`;
    });
}

function _renderProfile(d) {
  const h = [];
  const row = (label, val) => `<div class="stat-item"><span class="stat-label">${escHtml(label)}</span><span class="stat-value">${escHtml(val || "—")}</span></div>`;

  // Basic info
  h.push('<div class="stats-grid">');
  for (const k of ["Username","Occupation","Status","Current rank","Age","Creation time"]) {
    if (d[k] != null) h.push(row(k, d[k]));
  }
  h.push('</div>');

  // Bionics
  if (d.bionics && d.bionics.length) {
    h.push('<hr class="stat-divider"><div class="profile-section-title">Bionics</div>');
    h.push('<div class="profile-tags">');
    d.bionics.forEach(b => h.push(`<span class="profile-tag">${escHtml(b)}</span>`));
    h.push('</div>');
  }

  // Weapons — grouped by slot type, pill badges per group
  if (d.weapons && d.weapons.length) {
    h.push('<hr class="stat-divider"><div class="profile-section-title">Weapons</div>');
    const wgroups = {"On Hand": [], "Stash": [], "Vault": []};
    d.weapons.forEach(w => {
      const s = (w.slot || "").toLowerCase();
      if (s.includes("hand"))       wgroups["On Hand"].push(w);
      else if (s.includes("stash")) wgroups["Stash"].push(w);
      else                          wgroups["Vault"].push(w);
    });
    ["On Hand", "Stash", "Vault"].forEach(group => {
      if (!wgroups[group].length) return;
      h.push(`<div class="profile-weapon-group">${escHtml(group)}</div>`);
      h.push('<div class="profile-tags">');
      wgroups[group].forEach(w => {
        const hasActions = group !== "Vault" && w.actions && w.actions.length;
        if (hasActions) {
          const actionsAttr = JSON.stringify(w.actions).replace(/'/g, "&#39;");
          h.push(`<span class="profile-weapon-pill profile-item-clickable" data-wname="${escHtml(w.item||"")}" data-wslot="${escHtml(w.slot||"")}" data-wdur="${escHtml(w.durability||"")}" data-wactions='${actionsAttr}' onclick="openWeaponOverlay(this)">`);
        } else {
          h.push('<span class="profile-weapon-pill">');
        }
        h.push(`<span class="profile-slot">${escHtml(w.slot||"")}</span>`);
        if (w.item) h.push(` <span class="profile-item-name">${escHtml(w.item)}</span>`);
        if (w.durability) h.push(` <span class="muted">${escHtml(w.durability)}</span>`);
        h.push('</span>');
      });
      h.push('</div>');
    });
  }

  // Vehicles
  if (d.vehicles && d.vehicles.length) {
    h.push('<hr class="stat-divider"><div class="profile-section-title">Vehicles</div>');
    d.vehicles.forEach(v => {
      const hasActions = v.actions && v.actions.length;
      const actionsAttr = hasActions ? JSON.stringify(v.actions).replace(/'/g, "&#39;") : "[]";
      h.push('<div class="stats-grid">');
      if (v.Type) {
        if (hasActions) {
          h.push(`<div class="stat-item profile-item-clickable" data-vname="${escHtml(v.Type)}" data-vactions='${actionsAttr}' onclick="openVehicleOverlay(this)"><span class="stat-label">Type</span><span class="stat-value">${escHtml(v.Type)}</span></div>`);
        } else {
          h.push(row("Type", v.Type));
        }
      }
      if (v.Condition) {
        h.push(`<div class="stat-item profile-item-clickable" onclick="openRepairOverlay('${escHtml(v.Condition)}')"><span class="stat-label">Condition</span><span class="stat-value">${escHtml(v.Condition)}</span></div>`);
      }
      for (const k of ["Location", "Parking/security"]) {
        if (v[k]) h.push(row(k, v[k]));
      }
      h.push('</div>');
    });
  }

  // Apartment
  if (d.apartment && Object.keys(d.apartment).length) {
    h.push('<hr class="stat-divider"><div class="profile-section-title">Apartment</div>');
    h.push('<div class="stats-grid">');
    for (const k of ["Apartment","Status","Storage"]) {
      if (d.apartment[k]) h.push(row(k, d.apartment[k]));
    }
    h.push('</div>');
    if (d.apartment.action_url) {
      h.push(`<div class="profile-nav-bar" style="margin-top:6px"><button class="action-btn" onclick="navigateTo('${escHtml(d.apartment.action_url)}')">${escHtml(d.apartment.action_label||"Enter/Manage")}</button></div>`);
    }
  }

  // Pets
  if (d.pets && d.pets.length) {
    h.push('<hr class="stat-divider"><div class="profile-section-title">Pets</div>');
    d.pets.forEach(p => {
      h.push('<div class="stats-grid">');
      for (const k of ["slot","Name","Breed","Age","Fights won","Fights lost"]) {
        if (p[k]) h.push(row(k === "slot" ? "Status" : k, p[k]));
      }
      h.push('</div>');
    });
  }

  // Businesses
  if (d.businesses && d.businesses.length) {
    h.push('<hr class="stat-divider"><div class="profile-section-title">Businesses</div>');
    d.businesses.forEach(b => {
      h.push(`<div class="profile-item"><span class="profile-item-name">${escHtml(b.name)}</span>`);
      if (b.next_restock && b.next_restock !== "N/A") h.push(` <span class="muted">restock: ${escHtml(b.next_restock)}</span>`);
      h.push('</div>');
    });
  }

  // Misc
  if (d.misc && d.misc.length) {
    h.push('<hr class="stat-divider"><div class="profile-section-title">Misc Items</div>');
    h.push('<div class="profile-tags">');
    d.misc.forEach(m => h.push(`<span class="profile-tag">${escHtml(m)}</span>`));
    h.push('</div>');
  }

  return h.join("");
}

