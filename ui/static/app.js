const EARN_MAP = {
  Secret:      [["whore","Whore"],["street_fight","Streetfight"],["joyride","Joyride"],["pimp","Pimp"]],
  General:     [["shoplift","Shoplift"],["steal_cheques","Steal Cheques"]],
  Hospital:    [["nurse","Nurse"],["doctor","Doctor"],["surgeon","Surgeon"]],
  Engineering: [["mechanic","Mechanic"]],
  Bank:        [["bank_teller","Work at Local Bank"]],
  Mortician:   [["mortician_assistant","Mortician Assistant"]],
  Law:         [["legal_secretary","Legal Secretary"]],
};

const ACTION_SUB_MAP = {
  community_service: [
    ["gum","Scraping gum off pavements"],
    ["tags","Cleaning up tags"],
    ["weeding","Gardening in the local park"],
    ["kids","Pedestrian controller at local school"],
    ["pamphlets","Delivering pamphlets for mayor"],
    ["delivery","Delivering groceries to elderly"],
    ["football","Coaching little league football"],
    ["suspect","Helping police in line-up"],
    ["reading","Reading to elderly"],
  ],
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
  dog_trains: [],
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
    secondary_crime: document.getElementById("secondary_crime").value,
    secondary_threshold: document.getElementById("secondary_threshold").value,
    action_enabled: document.getElementById("action_enabled").checked,
    action_type: document.getElementById("action_type").value,
    action_sub: document.getElementById("action_sub").value,
    payback_enabled: document.getElementById("payback_enabled").checked,
  };

  fetch("/save", {
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

function toggleBot() {
  const endpoint = _botRunning ? "/stop" : "/start";
  fetch(endpoint, {method: "POST"})
    .then(r => r.json())
    .then(d => updateBotState(d.running, d.paused));
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

function pollStatus() {
  fetch("/status")
    .then(r => r.json())
    .then(d => {
      updateBotState(d.running, d.paused);
      document.getElementById("energy-val").textContent = d.energy;
      document.getElementById("city-val").textContent = d.city || "--";
      document.getElementById("action-val").textContent = d.action_ready ? "Ready" : "Waiting";

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

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
