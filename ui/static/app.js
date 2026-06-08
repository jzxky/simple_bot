const EARN_MAP = {
  Secret:      [["whore","Whore"],["street_fight","Streetfight"],["joyride","Joyride"],["pimp","Pimp"]],
  General:     [["shoplift","Shoplift"],["steal_cheques","Steal Cheques"]],
  Hospital:    [["nurse","Nurse"],["doctor","Doctor"],["surgeon","Surgeon"]],
  Engineering: [["mechanic","Mechanic"]],
  Bank:        [["bank_teller","Work at Local Bank"]],
  Mortician:   [["mortician_assistant","Mortician Assistant"]],
  Law:         [["legal_secretary","Legal Secretary"]],
  Crime:       [["5","Shoplift"],["6","Steal cheques"],["8","Compete at illegal drags"],["9","Hack bank account"],["11","Scamming"]],
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

function saveConfig() {
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
    away_action_enabled: document.getElementById("away_action_enabled").checked,
    away_action_type: document.getElementById("away_action_type").value,
    fallback_to_away: document.getElementById("fallback_to_away").checked,
    payback_enabled: document.getElementById("payback_enabled").checked,
    logout_on_stop: document.getElementById("logout_on_stop").checked,
    relog_on_session_expire: document.getElementById("relog_on_session_expire").checked,
  };

  return fetch("/save", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data),
  }).then(r => r.json()).then(() => {
    const btn = document.getElementById("save-btn");
    btn.textContent = "Saved!";
    setTimeout(() => btn.textContent = "Save", 1500);
  });
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
    saveConfig().then(() =>
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
      document.getElementById("stat-aggpro").textContent = d.agg_pro_active ? "Active" : "Inactive";

      const fmt = n => "$" + (n ?? 0).toLocaleString();
      document.getElementById("stat-clean").textContent = d.clean_money != null ? fmt(d.clean_money) : "--";
      document.getElementById("stat-dirty").textContent = d.dirty_money != null ? fmt(d.dirty_money) : "--";

      // Consumables
      const cons = d.consumables || {};
      document.getElementById("stat-consumables").innerHTML =
        Object.entries(CONSUMABLE_LABELS).map(([k, label]) =>
          `<div class="consumable-item"><span class="consumable-name">${label}</span><span class="consumable-qty ${_botRunning ? 'consumable-link' : ''}" onclick="${_botRunning ? `consumeItem('${k}')` : ''}">${cons[k] ?? 0}</span></div>`
        ).join("");

      // Log
      const box = document.getElementById("log-box");
      box.innerHTML = [...d.log].reverse()
        .map(l => `<div class="log-line">${escHtml(l)}</div>`)
        .join("");
    })
    .catch(() => {})
    .finally(() => setTimeout(pollStatus, 3000));
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

function toggleFieldVisibility(id, btn) {
  const el = document.getElementById(id);
  if (el.type === "password") {
    el.type = "text";
    btn.textContent = "Hide";
  } else {
    el.type = "password";
    btn.textContent = "Show";
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
      const link = document.getElementById("log-open-link");
      const files = d.files || [];
      sel.innerHTML = files.length
        ? files.map(f => `<option value="${escHtml(f)}">${escHtml(f)}</option>`).join("")
        : `<option value="">No logs</option>`;
      sel.onchange = () => {
        const f = sel.value;
        if (f) link.href = "/logs/" + encodeURIComponent(f);
      };
      if (files.length) link.href = "/logs/" + encodeURIComponent(files[0]);
    })
    .catch(() => {});
}

loadLogFiles();
