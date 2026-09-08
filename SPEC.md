# MafiaMatrix Bot — Master Spec

## Overview

A browser automation bot for the game MafiaMatrix (mafiamatrix.com). The bot automates repetitive game actions including aggravated crimes, earns, and action-timer-based activities. It is controlled via a locally-served web UI.

---

## Stack

- **Language:** Python
- **Browser automation:** Playwright (synchronous)
- **User-agent:** Mobile (required for player dropdown lists)
- **UI:** Flask backend, plain HTML/CSS/JS frontend
- **Concurrency:** Single-threaded, polling loop (no async)
- **State:** In-memory only

---

## Architecture

The bot uses a priority-based task scheduler. Each automatable action is implemented as a self-contained Task class. New actions can be added in the future by creating a new Task subclass — no changes to the scheduler or executor are required.

### Task Base Class

```
Task:
  priority: int
  is_complete: bool

  run(state) → Action or None
  can_run(state) → bool
```

- Tasks maintain internal state and are resumable after interruption
- Tasks return structured Action objects — they do not call Playwright directly
- Actions are executed by a central ActionExecutor

### Scheduler

- Maintains a list of active tasks sorted by priority
- Each tick: selects the highest-priority task where `can_run(state)` is True
- If a higher-priority task becomes runnable, it preempts the current task
- Preempted tasks resume from their last saved position on next selection
- Supports dynamic task addition and removal at runtime

### Task Types

**TimerTask** — fires at a fixed interval (e.g. earns check every 30 minutes)
- Tracks last execution time
- `can_run` returns True when interval has elapsed

**IterativeTask** — iterates over a list one item per tick (e.g. player list for crimes)
- Stores current index
- Resumes from last index after interruption

**EventDrivenTask** — triggered by a change in game state (e.g. action timer becoming Ready)
- `can_run` checks a condition against current state

---

## Shared State

Read on every page load. Used by all tasks.

| Value | Source HTML |
|---|---|
| Player's own name | `<div id="display"><a href="/userprofile.asp?username=X">X</a></div>` |
| Current city | First `<div id="display">` after the "Location" `display_top` label |
| Home city | `<div id="display_end">` after the "Home City" `display_top` label |
| Energy | `aria-valuenow` attribute on `<div class="progress-bar bg-energy">` |
| Action timer state | `<span class="donation_timer">` — see Action Timer section |
| Server time | Text content of `<div class="serverTime">` |

**City match check** (used by hack and community service):
- Current city == Home city when `<div id="display">` text matches `<div id="display_end">` text

**Time comparisons:**
- Always use server time from `div.serverTime`
- Never use system clock

---

## Login

**URL:** `https://mafiamatrix.com/default.asp`

**Flow:**
1. Navigate to `https://mafiamatrix.com/default.asp`
2. Fill `input#email` with configured email
3. Fill `input#pass` with configured password
4. Submit the login form
5. Check result:
   - **Success:** URL is `https://mafiamatrix.com/loggedin.asp` → navigate to `https://mafiamatrix.com/loggedin.asp?display=play`
   - **Failure:** `<div class="info red">` contains "Login failed" → stop bot, surface error in UI

**Session expiry detection:**
- On every page navigation, check if current URL has returned to `default.asp`
- If so: automatically re-run login flow
- If re-login fails: stop bot, surface error in UI

---

## Action Timer

Used by: Community Service, Career Training, Drug Manufacturing (deferred), Dog Trains (deferred), University Training (deferred), Training Centre (deferred).

**Reading timer state:**

```html
<!-- Ready -->
<span class="donation_timer" data-date-end="...">
  <span style="color: #00bb01; font-weight: bold;">Ready</span>
</span>

<!-- Counting down -->
<span class="donation_timer" data-date-end="6/6/2026 6:10:08 AM">00:09:48</span>
```

- **Ready:** inner content is the green "Ready" span
- **Waiting:** inner content is a countdown string; `data-date-end` holds expiry in server time
- Timer is available when server time >= `data-date-end`, or when "Ready" is shown

---

## Energy

**Reading energy:**
- `aria-valuenow` attribute on `<div class="progress-bar bg-energy">`
- Range: 0–100
- Drops to 0 after a crime is committed
- Threshold is configurable per crime type in bot config

**Energy gate (applied before every crime attempt):**
1. Read current energy
2. Compare to configured threshold for that crime
3. If below threshold: wait and poll until reached

---

## Aggravated Crimes

**Crimes in scope:** Pickpocket, Mugging, Breaking & Entering, Hack Bank Account
**Deferred:** Armed Robbery, Torch a Business

**Priority:**
- Bot attempts Primary crime first
- Falls back to Secondary crime if Primary is unavailable
- Availability rules:
  - **Hack:** skip if current city ≠ home city
  - **Mugging:** skip if no valid weapon available and none in stash
  - **Armed Robbery (future):** skip if no valid weapon available and none in stash

### Young Target Filter

Optional (`aggravated_crimes.target_young_only`, off by default). When enabled,
target lists for Pickpocket, Mugging, Breaking & Entering and Hack are filtered
against the player database: any name whose recorded `character_age` exceeds
`aggravated_crimes.young_age_threshold_hours` (in hours; stored ages are in
minutes) is removed. Names not present in the database are kept — an unknown age
is not a reason to skip a target. Armed Robbery, Torch and manual one-off
interactions are unaffected.

### Pre-Crime Weapon Check

**URL:** `https://mafiamatrix.com/profile/default.asp`

Parse `<div class="showWeapons">`:
- **Equipped slots:** labeled "Hand #1" or "Hand #2" — action links are Stash / Dispose / Sell
- **Stash slots:** labeled "Stash #N" — action links are Carry / Dispose / Sell
- Weapon name is in `<td class="item_content"><b>NAME</b></td>`

**For Mugging:**
- Need "Baseball Bat" or "Pistol" in Hand #1 or Hand #2
- If not equipped: search stash slots for Baseball Bat or Pistol → click its Carry link
- If none found: abort crime, log "no valid weapon available"

**For Armed Robbery (future):**
- Need any non-body-part weapon equipped
- Excluded items: Arms, Legs, Eyes, Brain, Heart
- Same equip-from-stash logic as mugging

### Crime Flow

**Step 1 — Select crime**
- Navigate to `https://mafiamatrix.com/income/agcrime.asp`
- Select radio button matching crime type (`value="pickpocket"` / `"mugging"` / `"breaking"` / `"hack"`)
- Submit ("Commit Crime")

**Step 2 — Iterate player list**
- Parse `<select>` dropdown on resulting page
- Extract all `<option value="X">X</option>` entries (skip "Please Select...")
- For each player:
  1. Skip if name == own name
  2. Select player in dropdown, submit (leave `cap` input at default)
  3. Check result page:
     - `<div id="success">` present → success, parse stolen amount, run payback if enabled, stop
     - `<div id="fail">` present → fail, continue to next player
  4. If list exhausted with no success: log "all targets failed", stop

### Success & Payback

**Parse stolen amount:**
- Regex `\$[\d,]+` against text content of `<div id="success">`

**Payback (if `payback_enabled: true`):**
1. Navigate to `https://mafiamatrix.com/income/bank.asp?option=transfers`
2. Fill `transferamount` = parsed stolen amount
3. Fill `transfername` = victim player name
4. Leave `transferreason` blank, leave anonymous unchecked
5. Submit

---

## Earns

**URL:** `https://mafiamatrix.com/income/earn.asp`

**Schedule:** Check every 30 minutes (TimerTask)

**Flow:**
1. Navigate to earn page
2. Click toggle checkbox (`#mm_earn_mode_toggle`) to enable AUTO mode if not already active
3. Read current queue count from `<span class="mm-earn-queue-cap">X / 200</span>` — parse left number
4. If count >= 10: do nothing, check again in 30 minutes
5. If count < 10:
   - Calculate top-up: `200 - current_count`
   - Select configured earn type in `<select name="schedule_earn_identifier">`
   - Set `<input name="schedule_count">` to top-up amount
   - Submit (POST to `/income/earn.asp` with `schedule_action=add`, `schedule_context=free`)

**Earn categories and options:**

| Category | Earn | schedule_earn_identifier value |
|---|---|---|
| Secret | Whore | `whore` |
| Secret | Streetfight | `street_fight` |
| Secret | Joyride | *(deferred — value TBD)* |
| Secret | Pimp | *(deferred — value TBD)* |
| General | Shoplift | `shoplift` |
| General | Steal cheques | `steal_cheques` |
| Hospital | Nurse | `nurse` |
| Hospital | Doctor | `doctor` |
| Hospital | Surgeon | `surgeon` |
| Engineering | Mechanic | `mechanic` |
| Bank | Work at local bank | `bank_teller` |
| Mortician | Mortician Assistant | `mortician_assistant` |
| Law | Legal Secretary | `legal_secretary` |

---

## Community Service

**URL:** `https://mafiamatrix.com/income/communityservice.asp`

**Trigger:** Action timer is Ready (EventDrivenTask)

**Flow:**
1. Check action timer — if not Ready, skip
2. Check current city vs home city
3. If in home city: select the last available `comservice` radio option in the list (highest tier), submit
4. If not in home city: select `csinothercities` value `"hospital"`, submit

---

## Career Training

**Trigger:** Action timer is Ready (EventDrivenTask)

**URLs:**
- Fire Department: `https://mafiamatrix.com/localcity/fire.asp`
- Customs: `https://mafiamatrix.com/localcity/customs.asp`
- Police: `https://mafiamatrix.com/localcity/policerecruit.asp`

**Flow (identical for all three):**
1. Check action timer — if not Ready, skip
2. Navigate to configured career training URL
3. Detect page state:
   - **Initial enroll:** select dropdown option containing "begin training", submit
   - **Ongoing study:** select dropdown option with value `"Yes"`, submit
4. Action timer is consumed on submit

---

## Deferred Actions

The following use the action timer and follow the same EventDrivenTask pattern. Workflows to be specced when accessible:

- Drug House Manufacturing
- Dog Trains
- University Training
- Training Centre (Martial Arts)

---

## Config Schema

```json
{
  "credentials": {
    "email": "",
    "password": ""
  },
  "earns": {
    "enabled": true,
    "category": "Hospital",
    "earn_type": "surgeon",
    "check_interval_minutes": 30
  },
  "aggravated_crimes": {
    "primary": {
      "crime": "hack",
      "energy_threshold": 60
    },
    "secondary": {
      "crime": "pickpocket",
      "energy_threshold": 50
    }
  },
  "action": {
    "type": "community_service",
    "sub_option": "reading"
  },
  "payback_enabled": true,
  "career_training": {
    "career": "fire"
  }
}
```

---

## UI Spec

**Stack:** Flask, plain HTML/CSS/JS

### Main Configuration Panel

**Credentials**
- Email: text input
- Password: password input

**Earn Selection**
- Combo 1: Category (Secret, General, Hospital, Engineering, Bank, Mortician, Law)
- Combo 2: Earn — populates based on category selection

**Aggravated Crime Selection**
- Primary: crime dropdown + Energy Threshold % number input
- Fallback: crime dropdown + Energy Threshold % number input
- Crime options: Pickpocket, Mugging, Breaking & Entering, Hack Bank Account, Armed Robbery *(future)*, Torch Business *(future)*

**Action Selection**
- Combo 1: Action type
- Combo 2: Sub-option — shown/hidden based on Combo 1 selection

| Action | Sub-options |
|---|---|
| Community Service | Scraping gum, Cleaning tags, Gardening, Pedestrian controller, Delivering pamphlets, Delivering groceries, Coaching football, Police line up, Reading to elderly |
| Career Training | Fire Department, Customs, Police |
| University Training | Business, Science, Medicine, Engineering, Law |
| Training Centre | *(placeholder)* |
| Drug Manufacturing | *(placeholder)* |
| Dog Trains | *(placeholder)* |

### Tabs

| Tab | Content |
|---|---|
| Aggravated Crimes Settings | Payback enabled toggle; further settings TBD |
| Business Settings | Placeholder |
| Promotion Settings | Placeholder |
| Case Work Settings | Placeholder |
| Jail Settings | Placeholder |

### Global Controls
- Save button
- Start / Stop bot toggle

---

## Extensibility Notes

- New actions → new Task subclass only, no changes to Scheduler or ActionExecutor
- New UI tabs → add tab panel, no changes to existing panels
- New earn categories → add to config schema and UI combo, no logic changes
- New crimes → add to crime dropdown and implement availability rule in task's `can_run`
