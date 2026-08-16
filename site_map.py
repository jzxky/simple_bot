"""
Site mapper for MafiaMatrix.
Logs in, crawls same-origin pages via link discovery (BFS), and saves HTML +
screenshots to ./site_map/, then zips the output.

Usage:
    python site_map.py <email> <password> [--dry-run]
"""

import argparse
import json
import re
import shutil
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from patchright.sync_api import sync_playwright

import urls

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1"
)

BASE = urls.BASE_URL

URLS = {
    "home":                BASE + "/default.asp",
    "logged_in":           BASE + "/loggedin.asp",
    "profile":             BASE + "/profile/default.asp",
    "earn":                BASE + "/income/earn.asp",
    "agg_crime":           BASE + "/income/agcrime.asp",
    "community_service":   BASE + "/income/communityservice.asp",
    "bank_transfers":      BASE + "/income/bank.asp?option=transfers",
    "fire_training":       BASE + "/localcity/fire.asp",
    "customs_training":    BASE + "/localcity/customs.asp",
    "police_training":     BASE + "/localcity/policerecruit.asp",
    "drug_house":          BASE + "/income/drughouse.asp",
    "university":          BASE + "/localcity/university.asp",
    "training_centre":     BASE + "/localcity/training.asp",
    "hospital":            BASE + "/localcity/hospital.asp",
    "black_market":        BASE + "/localcity/blackmarket.asp",
    "weapons":             BASE + "/weapons.asp",
    "city_bar":            BASE + "/localcity/bar.asp",
    "jail":                BASE + "/jail/default.asp",
    "online_players":      BASE + "/players/online.asp",
    "income_overview":     BASE + "/income/default.asp",
    "character_skills":    BASE + "/income/charskills.asp",
    "dog_training":        BASE + "/localcity/dogtraining.asp",
    "vehicle_yard":        BASE + "/localcity/vehicleyard.asp",
    "airport":             BASE + "/localcity/airport.asp",
}

# After selecting each crime, capture the target selection page too
CRIME_TYPES = ["pickpocket", "mugging", "breaking", "hack", "gta"]

OUT_DIR = Path("site_map")

# How many hops beyond the seed URLS to follow discovered links.
MAX_DEPTH = 3

# Links containing any of these substrings (case-insensitive) are never visited or
# followed. This is a live multiplayer game — repeatedly hitting action endpoints
# during a crawl could spend resources, trigger cooldowns, or take irreversible
# actions. Treat this as a starting point, not exhaustive: review it against the
# real site (or use --dry-run) before trusting it.
EXCLUDE_SUBSTRINGS = [
    "logout", "signout", "log_out",
    "delete", "leave", "quit", "abandon", "disown", "kick", "resign",
    "transfer",
    "attack", "shoot", "kill", "hit",
    "agcrime.asp",
]


def save(name: str, page):
    OUT_DIR.mkdir(exist_ok=True)
    html_path = OUT_DIR / f"{name}.html"
    png_path = OUT_DIR / f"{name}.png"
    html_path.write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(png_path), full_page=True)
    print(f"  saved: {name}")


def login(page, email: str, password: str) -> bool:
    page.goto(BASE + "/default.asp", wait_until="load", timeout=30000)
    save("01_login_page", page)

    page.wait_for_selector("form#loginForm", timeout=10000)
    page.fill("input#email", email)
    page.fill("input#pass", password)
    page.click("button.btn-login")
    page.wait_for_load_state("networkidle", timeout=15000)
    save("02_after_login", page)

    soup = BeautifulSoup(page.content(), "html.parser")
    err = soup.find("div", class_="info red")
    if err and "login failed" in err.get_text(strip=True).lower():
        print(f"ERROR: Login failed — {err.get_text(strip=True)}")
        return False

    if soup.find("a", class_="btn-play"):
        page.goto(BASE + "/loggedin.asp?display=play", wait_until="networkidle", timeout=15000)
        save("03_after_play", page)
    else:
        print("  WARNING: PLAY NOW button not found — may not be logged in")

    return True


def extract_links(page) -> set:
    soup = BeautifulSoup(page.content(), "html.parser")
    base_netloc = urlparse(BASE).netloc
    found = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        full = urljoin(page.url, href)
        parsed = urlparse(full)
        if parsed.netloc and parsed.netloc != base_netloc:
            continue  # off-site
        normalized = parsed._replace(fragment="").geturl()
        if any(bad in normalized.lower() for bad in EXCLUDE_SUBSTRINGS):
            continue
        found.add(normalized)
    return found


def derive_slug(url: str, counter: int) -> str:
    stem = Path(urlparse(url).path).stem
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", stem).strip("_") or "page"
    return f"{counter:02d}_{slug}"


def crawl(page, index: dict, dry_run: bool):
    queue = deque((url, 1) for url in URLS.values())
    visited = set()
    counter = 4  # continues numbering after 01_login_page/02_after_login/03_after_play

    while queue:
        url, depth = queue.popleft()
        norm = urlparse(url)._replace(fragment="").geturl()
        if norm in visited:
            continue
        visited.add(norm)

        if dry_run:
            print(f"  [dry-run][{depth}] would visit: {url}")
            continue

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            print(f"  ERROR fetching {url}: {e}")
            continue

        final_norm = urlparse(page.url)._replace(fragment="").geturl()
        visited.add(final_norm)

        slug = derive_slug(url, counter)
        counter += 1
        save(slug, page)
        index[slug] = {"url": page.url, "title": page.title(), "depth": depth}
        print(f"  [{depth}] {page.url}")

        if depth < MAX_DEPTH:
            for link in extract_links(page):
                if link not in visited:
                    queue.append((link, depth + 1))


def run(email: str, password: str, dry_run: bool = False):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=MOBILE_UA)
        page = ctx.new_page()

        print("Logging in...")
        if not login(page, email, password):
            browser.close()
            return

        print("\nCrawling pages...")
        index = {}
        crawl(page, index, dry_run)

        if dry_run:
            print("\nDry run complete — no files saved.")
            browser.close()
            return

        # --- Crime target selection pages ---
        print("\nCapturing crime target pages...")
        for crime in CRIME_TYPES:
            try:
                page.goto(BASE + "/income/agcrime.asp", wait_until="domcontentloaded")
                radio = page.query_selector(f"input[type='radio'][value='{crime}']")
                if radio:
                    radio.check()
                    page.click("input[type='submit'][name='B1']")
                    page.wait_for_load_state("domcontentloaded")
                    slug = f"crime_target_{crime}"
                    save(slug, page)
                    index[slug] = {"name": f"crime_target_{crime}", "url": page.url}
                else:
                    print(f"  {crime} radio not found (may not be unlocked)")
            except Exception as e:
                print(f"  ERROR on crime {crime}: {e}")

        # Save index
        (OUT_DIR / "index.json").write_text(json.dumps(index, indent=2))
        print(f"\nDone. {len(index)} pages saved to ./{OUT_DIR}/")

        zip_path = shutil.make_archive(str(OUT_DIR), "zip", root_dir=OUT_DIR)
        print(f"Zipped output to {zip_path}")
        print("Share the site_map.zip for review.")

        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("password")
    parser.add_argument("--dry-run", action="store_true",
                         help="Print URLs that would be visited without navigating or saving anything")
    args = parser.parse_args()
    run(args.email, args.password, dry_run=args.dry_run)
