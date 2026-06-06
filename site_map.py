"""
Site mapper for MafiaMatrix.
Logs in, visits all relevant URLs, and saves HTML + screenshots to ./site_map/

Usage:
    python site_map.py <email> <password>
"""

import sys
import os
import json
from pathlib import Path
from patchright.sync_api import sync_playwright

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)

BASE = "https://mafiamatrix.com"

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
    "training_centre":     BASE + "/localcity/trainingcentre.asp",
    "hospital":            BASE + "/localcity/hospital.asp",
    "black_market":        BASE + "/localcity/blackmarket.asp",
    "weapons":             BASE + "/weapons.asp",
    "city_bar":            BASE + "/localcity/bar.asp",
    "jail":                BASE + "/jail/default.asp",
    "online_players":      BASE + "/players/online.asp",
    "income_overview":     BASE + "/income/default.asp",
    "character_skills":    BASE + "/income/characterskills.asp",
    "dog_training":        BASE + "/localcity/dogtraining.asp",
    "vehicle_yard":        BASE + "/localcity/vehicleyard.asp",
    "airport":             BASE + "/localcity/airport.asp",
}

# After selecting each crime, capture the target selection page too
CRIME_TYPES = ["pickpocket", "mugging", "breaking", "hack", "gta"]

OUT_DIR = Path("site_map")


def save(name: str, page):
    OUT_DIR.mkdir(exist_ok=True)
    html_path = OUT_DIR / f"{name}.html"
    png_path = OUT_DIR / f"{name}.png"
    html_path.write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(png_path), full_page=True)
    print(f"  saved: {name}")


def run(email: str, password: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(user_agent=MOBILE_UA)
        page = ctx.new_page()

        # --- Login ---
        print("Logging in...")
        page.goto(BASE + "/default.asp", wait_until="domcontentloaded")
        save("01_login_page", page)

        page.fill("input#email", email)
        page.fill("input#pass", password)
        page.click("button.btn-login")
        page.wait_for_load_state("domcontentloaded")
        save("02_after_login", page)

        # Click PLAY NOW if present
        play = page.query_selector("a.btn-play")
        if play:
            page.goto(BASE + "/loggedin.asp?display=play", wait_until="domcontentloaded")
            save("03_after_play", page)
        else:
            print("  WARNING: PLAY NOW button not found — may not be logged in")

        # --- Visit all pages ---
        print("\nVisiting pages...")
        index = {}
        for i, (name, url) in enumerate(URLS.items(), start=4):
            print(f"  {name} -> {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                slug = f"{i:02d}_{name}"
                save(slug, page)
                index[slug] = {"name": name, "url": url, "title": page.title()}
            except Exception as e:
                print(f"  ERROR on {name}: {e}")

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
        print("Share the site_map/ folder for review.")

        browser.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python site_map.py <email> <password>")
        sys.exit(1)
    run(sys.argv[1], sys.argv[2])
