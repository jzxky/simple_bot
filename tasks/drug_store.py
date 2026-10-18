"""
Watches the Auckland drug store from its own browser tab and buys wanted items
the moment they come into stock.

The scheduler only opens the tab: run() fires when logged in, not in jail or
hospital, in Auckland, enabled in config, and no tab is already open. From then
on bot.py calls tick_drug_store() once per loop iteration (cooperatively, the
same way the agg-crimes and snipe tabs work — patchright's sync API is bound to
the bot thread, so a real second thread can't drive the browser). Each tick:

  - closes the tab if the task was disabled, the bot left Auckland, or it is in
    jail / hospital / logged out
  - otherwise, once per configured interval (minimum 5s) and outside the 30-min
    post-purchase cooldown, refreshes drugstore.asp, which also refreshes
    game_state (clean money, city)
  - tops clean money up to the price of the most expensive wanted item by
    withdrawing from the bank (Maintain Cash keeps that same amount on hand
    while this task is active so it doesn't deposit the reserve straight back)
  - buys the first in-stock wanted item, following config priority_order (or
    wanted order if empty)

Only three items are relevant: Pseudoephedrine, Epipen, Medipack.
"""

import time
from bs4 import BeautifulSoup
import browser
from tasks.base import Task
from state import GameState

DRUG_STORE_PRICES = {"Pseudoephedrine": 500, "Epipen": 25_000, "Medipack": 1_000_000}
MIN_INTERVAL_SECS = 5
PURCHASE_COOLDOWN_SECS = 30 * 60
# After a withdrawal fails to reach the reserve (bank too low), don't retry for this long.
WITHDRAW_BACKOFF_SECS = 5 * 60
MAX_CONSECUTIVE_ERRORS = 3


def load_drug_store_state() -> dict:
    import config as cfg
    return cfg.load().get("drug_store_state", {})


def save_drug_store_state(updates: dict):
    import config as cfg
    c = cfg.load()
    c.setdefault("drug_store_state", {}).update(updates)
    cfg.save(c)


def drug_store_active(state: GameState) -> bool:
    """True while the drug store task applies: enabled in config and in Auckland."""
    import config as cfg
    if not cfg.load().get("drug_store", {}).get("enabled", False):
        return False
    return state.current_city.lower() == "auckland"


def drug_store_cash_floor() -> int:
    """Clean cash the drug store needs on hand: the price of the most
    expensive wanted item (0 if nothing is wanted). Maintain Cash keeps at
    least this much while the task is active."""
    wanted = _ordered_wanted()
    return max((DRUG_STORE_PRICES.get(i, 0) for i in wanted), default=0)


def interval_secs() -> int:
    import config as cfg
    d = cfg.load().get("drug_store", {})
    return max(MIN_INTERVAL_SECS, int(d.get("check_interval_minutes", 5)) * 60
               + int(d.get("check_interval_seconds", 0)))


def _ordered_wanted() -> list:
    import config as cfg
    d = cfg.load().get("drug_store", {})
    wanted = d.get("wanted_items", [])
    priority = d.get("priority_order", [])
    if priority:
        return [i for i in priority if i in wanted]
    return list(wanted)


class DrugStoreTask(Task):
    priority = 53
    label = "Drug Store"

    def __init__(self):
        s = load_drug_store_state()
        self.last_checked_at: float = 0.0
        self.last_stock: dict = s.get("last_stock", {})
        self.purchase_cooldown_until: float = float(s.get("purchase_cooldown_until", 0))
        self._page = None
        self._withdraw_backoff_until: float = 0.0
        self._errors = 0

    # ------------------------------------------------------------------
    # Scheduler side — only opens the tab
    # ------------------------------------------------------------------

    def _stop_reason(self, state: GameState) -> "str | None":
        import config as cfg
        if not state.logged_in:
            return "logged out"
        if state.in_jail:
            return "in jail"
        if state.in_hospital:
            return "in hospital"
        if not cfg.load().get("drug_store", {}).get("enabled", False):
            return "disabled"
        if state.current_city.lower() != "auckland":
            return "not in Auckland"
        return None

    def can_run(self, state: GameState) -> bool:
        if state.drug_store_tab_active:
            return False
        return self._stop_reason(state) is None

    def blocked_reasons(self, state):
        import config as cfg
        reasons = []
        if state.drug_store_tab_active:
            reasons.append("Tab running")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        if state.current_city.lower() != "auckland":
            reasons.append("Not in Auckland")
        if not cfg.load().get("drug_store", {}).get("enabled", False):
            reasons.append("Not enabled")
        return reasons

    def run(self, state: GameState, executor):
        try:
            self._page = browser.new_page()
        except Exception as e:
            state.add_log(f"Drug Store: failed to open tab: {e}")
            return
        self._errors = 0
        self.last_checked_at = 0.0
        state.drug_store_tab_active = True
        state.add_log(f"Drug Store: watching in a new tab (every {interval_secs()}s).")

    # ------------------------------------------------------------------
    # Tab side — called every bot-loop iteration while the tab is open
    # ------------------------------------------------------------------

    def next_poll_at(self) -> float:
        now = time.time()
        if self.purchase_cooldown_until > now:
            return self.purchase_cooldown_until
        return self.last_checked_at + interval_secs()

    def tick_drug_store(self, state: GameState):
        import bot as _bot

        if _bot._stop_event.is_set():
            self._finish(state, reason="bot stopping")
            return

        reason = self._stop_reason(state)
        if reason:
            self._finish(state, reason=reason)
            return

        if time.time() < self.next_poll_at():
            return

        saved_html, saved_url = state.page_html, state.current_url
        try:
            with browser.use_page(self._page):
                self._poll(state)
            self._errors = 0
        except Exception as e:
            if browser.is_lost_error(e):
                raise
            self._errors += 1
            state.add_log(f"Drug Store (tab): error — {e}")
            if self._errors >= MAX_CONSECUTIVE_ERRORS:
                self._finish(state, reason=f"{self._errors} errors in a row")
        finally:
            # Between ticks, state.page_html/current_url must keep describing the
            # main tab — many unrelated handlers read them assuming that.
            state.page_html, state.current_url = saved_html, saved_url

    def _finish(self, state: GameState, reason: str = ""):
        if self._page is not None:
            browser.close_page(self._page)
            self._page = None
        was_active = state.drug_store_tab_active
        state.drug_store_tab_active = False
        if reason and was_active:
            state.add_log(f"Drug Store: tab closed ({reason}).")

    def stop_tab(self, state: GameState):
        """External request to close the tab now (config reload, browser
        restart, bot shutdown)."""
        if self._page is not None or state.drug_store_tab_active:
            self._finish(state, reason="stopped")

    # ------------------------------------------------------------------
    # One poll of drugstore.asp (runs with browser.use_page(self._page))
    # ------------------------------------------------------------------

    def _load_store(self, state: GameState) -> "dict | None":
        """Navigate to the store and parse it. Returns None (after logging) if
        the poll can't continue — session expired, Cloudflare, or redirected."""
        from executor import _nav, _u, _check_session
        import bot as _bot

        _nav(_u("/localcity/drugstore.asp"), state)
        if "Just a moment" in (self._page.title() or ""):
            state.add_log("Drug Store: Cloudflare challenge on drug store tab — pausing bot. "
                          "Complete the challenge in that tab then press Resume.")
            _bot._pause_event.set()
            return None
        if not _check_session(state):
            return None
        if "drugstore.asp" not in browser.current_url():
            # Jail/hospital/travel redirect — state was refreshed by _nav, so the
            # next tick's _stop_reason() will close the tab if appropriate.
            return None
        return self._parse_store()

    def _parse_store(self) -> dict:
        soup = BeautifulSoup(self._page.content(), "html.parser")
        items = {}
        for row in soup.select("table tr"):
            radio = row.find("input", {"name": "product", "type": "radio"})
            if not radio:
                continue
            item_val = radio.get("value", "")
            tds = row.find_all("td")
            if len(tds) < 4:
                continue
            try:
                stock = int(tds[3].get_text(strip=True))
            except ValueError:
                continue
            items[item_val] = stock
        return items

    def _record_stock(self, state: GameState, store: dict):
        import config as cfg
        from executor import _notify
        if self.last_stock:
            restocked = [item for item, stock in store.items()
                         if stock > self.last_stock.get(item, 0)]
            if restocked:
                now_str = time.strftime("%Y-%m-%d %H:%M:%S")
                c = cfg.load()
                c.setdefault("drug_store", {})["last_restock_at"] = now_str
                cfg.save(c)
                import settings_rev; settings_rev.bump()
                msg = f"Drug Store restock detected ({', '.join(restocked)}) at {now_str}."
                state.add_log(msg)
                _notify(state, "drug_store_restock", msg)
        if store != self.last_stock:
            # Only persist on change — at a 5s interval, writing config.json on
            # every poll would race the UI's own saves.
            self.last_stock = dict(store)
            save_drug_store_state({"last_stock": self.last_stock})

    def _top_up_cash(self, state: GameState, reserve: int) -> bool:
        """Withdraw up to `reserve` clean cash. Returns True if a withdrawal
        was made (the tab is then on bank.asp and the store must be reloaded)."""
        from executor import handle_withdraw
        from tasks.base import Action
        if state.clean_money >= reserve or time.time() < self._withdraw_backoff_until:
            return False
        needed = reserve - state.clean_money
        state.add_log(f"Drug Store: clean cash ${state.clean_money:,} below ${reserve:,} — withdrawing ${needed:,}.")
        handle_withdraw(Action("withdraw", amount=needed), state)
        if state.clean_money < reserve:
            self._withdraw_backoff_until = time.time() + WITHDRAW_BACKOFF_SECS
            state.add_log(f"Drug Store: still short of ${reserve:,} after withdrawing — "
                          f"retrying in {WITHDRAW_BACKOFF_SECS // 60}m.")
        return True

    def _poll(self, state: GameState):
        from executor import _refresh_state, _notify
        self.last_checked_at = time.time()

        wanted = _ordered_wanted()
        if not wanted:
            return

        store = self._load_store(state)
        if store is None:
            return
        if state.current_city.lower() != "auckland":
            return  # next tick closes the tab

        reserve = drug_store_cash_floor()
        if self._top_up_cash(state, reserve):
            store = self._load_store(state)
            if store is None:
                return

        self._record_stock(state, store)

        for _attempt in range(3):
            can_buy = [i for i in wanted
                       if store.get(i, 0) > 0 and DRUG_STORE_PRICES.get(i, 0) <= state.clean_money]
            if not can_buy:
                in_stock = [i for i in wanted if store.get(i, 0) > 0]
                if in_stock:
                    state.add_log(f"Drug Store: {', '.join(in_stock)} in stock but not enough "
                                  f"clean cash (${state.clean_money:,}).")
                return

            target = can_buy[0]
            price = DRUG_STORE_PRICES.get(target, 0)
            state.add_log(f"Drug Store: purchasing {target} for ${price:,}.")
            self._page.check(f"input[name='product'][value='{target}']")
            self._page.click("input[type='submit'][name='B1'][value='Purchase']")
            self._page.wait_for_load_state("domcontentloaded")
            _refresh_state(state)

            result_soup = BeautifulSoup(self._page.content(), "html.parser")
            success_div = result_soup.find("div", id="success")
            fail_div = result_soup.find("div", id="fail")

            if success_div:
                msg = f"Drug Store: purchased {target} — {success_div.get_text(strip=True)}"
                state.add_log(msg)
                _notify(state, "drug_store_purchased", msg)
                self.purchase_cooldown_until = time.time() + PURCHASE_COOLDOWN_SECS
                save_drug_store_state({"purchase_cooldown_until": self.purchase_cooldown_until})
                state.add_log(f"Drug Store: cooldown for {PURCHASE_COOLDOWN_SECS // 60}m.")
                return
            if not fail_div:
                state.add_log("Drug Store: unexpected page after purchase — aborting this poll.")
                return

            state.add_log(f"Drug Store: purchase failed — {fail_div.get_text(strip=True)}, retrying.")
            store = self._load_store(state)
            if store is None:
                return
