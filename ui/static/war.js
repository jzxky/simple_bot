const WHACK_TYPES = ["Normal", "Bodyguard"];
const WAR_COLS = [
  ["name","Name"],["ws","WS"],["status","Status"],["whack_type","Whack Type"],
  ["last_whack","Last Whack"],["window_open","Window Open"],["window_close","Window Close"],
  ["last_checked","Last Checked"],
];
const warSort = { opps: {col:null, dir:1}, friendlies: {col:null, dir:1} };

function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function fmtTime(s) { return s || "—"; }

function warSortBy(side, col) {
  const st = warSort[side];
  if (st.col === col) st.dir = -st.dir; else { st.col = col; st.dir = 1; }
  warLoad();
}
function warSortRows(side, rows) {
  const st = warSort[side];
  if (!st.col) return rows;
  const c = st.col, dir = st.dir;
  return rows.slice().sort((a, b) => {
    let x = a[c], y = b[c];
    if (c === "ws") { x = x == null ? -1 : x; y = y == null ? -1 : y; return (x - y) * dir; }
    x = (x ?? "").toString().toLowerCase(); y = (y ?? "").toString().toLowerCase();
    return (x < y ? -1 : x > y ? 1 : 0) * dir;
  });
}

function warTable(side, rows) {
  if (!rows.length) return '<p class="war-empty">No names tracked.</p>';
  rows = warSortRows(side, rows);
  const st = warSort[side];
  const head = "<tr>" + WAR_COLS.map(([c, l]) => {
    const ind = st.col === c ? (st.dir > 0 ? " ▲" : " ▼") : "";
    return `<th class="war-th" onclick="warSortBy('${side}','${c}')">${l}${ind}</th>`;
  }).join("") + "<th>Actions</th></tr>";
  const body = rows.map(r => `
    <tr>
      <td data-label="Name">${esc(r.name)}</td>
      <td data-label="WS">${r.ws == null ? "—" : r.ws}</td>
      <td data-label="Status" class="war-status ${r.status}">${r.status}</td>
      <td data-label="Whack Type">
        <select onchange="warSetType('${side}','${esc(r.name)}',this.value)">
          ${WHACK_TYPES.map(t => `<option value="${t}" ${r.whack_type===t?'selected':''}>${t}</option>`).join("")}
        </select>
      </td>
      <td data-label="Last Whack" class="war-whack-cell">
        <input type="time" class="war-time-input" value="${esc(r.last_whack)}"
               onchange="warSetTime('${side}','${esc(r.name)}',this.value)">
        <button class="war-clear" title="Clear whack time" onclick="warSetTime('${side}','${esc(r.name)}','')">✕</button>
      </td>
      <td data-label="Window Open">${fmtTime(r.window_open)}</td>
      <td data-label="Window Close">${fmtTime(r.window_close)}</td>
      <td data-label="Last Checked">${fmtTime(r.last_checked)}</td>
      <td data-label="" class="war-actions">
        <button class="btn-secondary war-btn" title="Check now" onclick="warCheck('${esc(r.name)}')">Check</button>
        <button class="btn-secondary war-btn war-del" title="Delete" onclick="warRemove('${side}','${esc(r.name)}')">Delete</button>
      </td>
    </tr>`).join("");
  return `<div class="war-table-wrap"><table class="war-table">${head}${body}</table></div>`;
}

function warRender(d) {
  document.getElementById("war-disabled").style.display = d.enabled ? "none" : "";
  document.getElementById("war-content").style.display = d.enabled ? "" : "none";
  if (!d.enabled) return;
  document.getElementById("war-opps").innerHTML = warTable("opps", d.opps || []);
  document.getElementById("war-friendlies").innerHTML = warTable("friendlies", d.friendlies || []);
  const iv = document.getElementById("war-interval");
  if (iv && !iv.matches(":focus")) iv.value = String(d.interval || 5);
  const log = document.getElementById("war-log");
  const events = d.events || [];
  log.innerHTML = events.length
    ? events.map(e => `<div class="war-log-line">[${esc(e.ts)}] ${esc(e.message)}</div>`).join("")
    : '<span class="war-empty">No war events yet.</span>';
}

let _warLastJson = "";
function warApply(d, force) {
  const json = JSON.stringify(d);
  if (!force) {
    if (json === _warLastJson) return;                          // nothing changed
    const ae = document.activeElement;
    if (ae && ae.closest && ae.closest(".war-table")) return;   // don't clobber an in-progress edit
  }
  _warLastJson = json;
  warRender(d);
}
function warLoad(force = true) {
  // When embedded inside the main SPA, only poll while the War Mode tab is
  // actually the active tab — otherwise this stacks a redundant 5s poll on
  // top of pollStatus() even when the tab isn't visible. On the standalone
  // /war page #s-war-mode doesn't exist, so this is a no-op there.
  const embedded = document.getElementById("s-war-mode");
  if (embedded && !embedded.classList.contains("main-active")) return;
  fetch("/api/war/lists").then(r => r.json()).then(d => warApply(d, force)).catch(()=>{});
}

function warAdd() {
  const name = document.getElementById("war-add-name").value.trim();
  const side = document.getElementById("war-add-side").value;
  const msg = document.getElementById("war-add-msg");
  if (!name) return;
  fetch("/api/war/add", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({name, side})}).then(r => r.json()).then(d => {
      msg.textContent = d.message || "";
      msg.style.color = d.ok ? "var(--success)" : "var(--red)";
      if (d.ok) document.getElementById("war-add-name").value = "";
      warLoad();
    });
}
function warRemove(side, name) {
  if (!confirm(`Delete ${name} from ${side}?`)) return;
  fetch("/api/war/remove", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({name, side})}).then(() => warLoad());
}
function warCheck(name) {
  const msg = document.getElementById("war-add-msg");
  fetch("/api/war/check", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({name})}).then(r => r.json()).then(d => {
      msg.textContent = d.ok ? `Check queued for ${name}.` : (d.message || "Check failed.");
      msg.style.color = d.ok ? "var(--muted)" : "var(--red)";
    });
}
function warSetType(side, name, whack_type) {
  fetch("/api/war/set_whack_type", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({name, side, whack_type})}).then(() => warLoad());
}
function warSetTime(side, name, time) {
  fetch("/api/war/set_whack_time", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({name, side, time})}).then(() => warLoad());
}
function warSetInterval() {
  const minutes = parseInt(document.getElementById("war-interval").value) || 5;
  fetch("/api/war/set_interval", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({minutes})});
}
function warCheckNow() {
  fetch("/api/war/check", {method:"POST"}).then(r => r.json()).then(d => {
    const msg = document.getElementById("war-add-msg");
    if (!d.ok) { msg.textContent = d.message || "Check failed."; msg.style.color = "var(--red)"; }
    else { msg.textContent = "Check queued."; msg.style.color = "var(--muted)"; }
  });
}
function warClearEvents() {
  fetch("/api/war/clear_events", {method:"POST"}).then(() => warLoad());
}

// Enter on the name box or side selector adds the player.
["war-add-name", "war-add-side"].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); warAdd(); } });
});

warLoad();
setInterval(() => warLoad(false), 5000);   // re-render only when the data actually changes
