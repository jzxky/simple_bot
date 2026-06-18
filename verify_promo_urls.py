#!/usr/bin/env python3
"""
Verify which promotion URLs are valid on mafiamatrix.com.
A valid URL will redirect to main.asp (bot is ineligible but the page exists).
An invalid URL will stay on the given URL and show "Error 404" in the title.

Usage:
    python3 verify_promo_urls.py

Reads credentials from .env (EMAIL= and PASSWORD= keys).
"""

import os
import sys
import time

# Load .env credentials
def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    creds = {}
    if not os.path.exists(env_path):
        print("ERROR: .env file not found.")
        sys.exit(1)
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                creds[k.strip()] = v.strip().strip('"').strip("'")
    return creds

PROMOS = [
    ("Jail",         "Schooled",             "/promotion/schooled.asp"),
    ("Jail",         "Mule",                 "/promotion/mule.asp"),
    ("Jail",         "Hardrock",             "/promotion/hardrock.asp"),
    ("Jail",         "Lifer",                "/promotion/lifer.asp"),
    ("City",         "Mayor",                "/promotion/mayor.asp"),
    ("Bank",         "Bank Teller",          "/promotion/bankteller.asp"),
    ("Bank",         "Loan Officer",         "/promotion/loanofficer.asp"),
    ("Bank",         "Bank Manager",         "/promotion/bankmanager.asp"),
    ("Fire",         "Fire Fighter",         "/promotion/firefighter.asp"),
    ("Fire",         "Fire Chief",           "/promotion/firechief.asp"),
    ("Funeral",      "Mortician Assistant",  "/promotion/morticianassistant.asp"),
    ("Funeral",      "Mortician",            "/promotion/mortician.asp"),
    ("Funeral",      "Funeral Director",     "/promotion/funeraldirector.asp"),
    ("Hospital",     "Nurse",                "/promotion/nurse.asp"),
    ("Hospital",     "Doctor",               "/promotion/doctor.asp"),
    ("Hospital",     "Surgeon",              "/promotion/surgeon.asp"),
    ("Hospital",     "Hospital Director",    "/promotion/hospitaldirector.asp"),
    ("Law",          "Legal Secretary",      "/promotion/legalsecretary.asp"),
    ("Law",          "Lawyer",               "/promotion/lawyer.asp"),
    ("Law",          "Judge",                "/promotion/judge.asp"),
    ("Law",          "Supreme Court Judge",  "/promotion/supremecourtjudge.asp"),
    ("Construction", "Mechanic",             "/promotion/mechanic.asp"),
    ("Construction", "Technician",           "/promotion/technician.asp"),
    ("Construction", "Engineer",             "/promotion/engineer.asp"),
    ("Construction", "Chief Engineer",       "/promotion/chiefengineer.asp"),
    ("Customs",      "Supervisor",           "/promotion/supervisor.asp"),
    ("Customs",      "Superintendent",       "/promotion/superintendent.asp"),
    ("Customs",      "Commissioner-General", "/promotion/commissionergeneral.asp"),
    ("Police",       "Sergeant",             "/promotion/sergeant.asp"),
    ("Police",       "Senior Sergeant",      "/promotion/seniorsergeant.asp"),
    ("Police",       "Detective",            "/promotion/detective.asp"),
    ("Police",       "Commissioner",         "/promotion/commissioner.asp"),
    ("Gangster",     "Dealer",               "/promotion/dealer.asp"),
    ("Gangster",     "Giovane D'Honore",     "/promotion/giovaneDhonore.asp"),
    ("Gangster",     "Enforcer",             "/promotion/enforcer.asp"),
    ("Gangster",     "Piciotto",             "/promotion/piciotto.asp"),
    ("Gangster",     "Sgarrista",            "/promotion/sgarrista.asp"),
    ("Gangster",     "Capodecima",           "/promotion/capodecima.asp"),
    ("Gangster",     "Caporegime",           "/promotion/caporegime.asp"),
    ("Gangster",     "Boss",                 "/promotion/boss.asp"),
    ("Gangster",     "Don",                  "/promotion/don.asp"),
]

BASE_URL = "https://mafiamatrix.com"

def main():
    creds = _load_env()
    email = creds.get("EMAIL") or creds.get("email", "")
    password = creds.get("PASSWORD") or creds.get("password", "")
    if not email or not password:
        print("ERROR: EMAIL and PASSWORD must be set in .env")
        sys.exit(1)

    import browser
    import urls

    print("Launching browser and logging in...")
    browser.launch(headless=False)
    page = browser.page()

    # Log in
    page.goto(urls.BASE_URL + "/index.asp", wait_until="domcontentloaded", timeout=30000)
    page.fill("input[name='email']", email)
    page.fill("input[name='password']", password)
    page.click("input[type='submit']")
    page.wait_for_load_state("domcontentloaded", timeout=15000)
    time.sleep(1)

    if "loggedin" not in page.url and "main" not in page.url:
        print(f"ERROR: Login may have failed. Current URL: {page.url}")
        print("Proceeding anyway...")

    print(f"\nLogged in. Testing {len(PROMOS)} promotion URLs...\n")

    results = {"ok": [], "fail": [], "other": []}
    current_cat = None

    for cat, rank, path in PROMOS:
        if cat != current_cat:
            print(f"\n── {cat} ──")
            current_cat = cat

        url = urls.BASE_URL + path
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(0.3)
            final_url = page.url.rstrip("/").lower()
            title = page.title()

            if "404" in title or "error 404" in title.lower():
                status = "FAIL  (404)"
                results["fail"].append((cat, rank, path))
            elif final_url.endswith("/main.asp") or "/main.asp" in final_url:
                status = "OK    (→ main.asp)"
                results["ok"].append((cat, rank, path))
            else:
                status = f"??    (url={page.url[:60]}, title={title[:40]})"
                results["other"].append((cat, rank, path, page.url, title))
        except Exception as e:
            status = f"ERROR ({e})"
            results["fail"].append((cat, rank, path))

        print(f"  {rank:<25} {status}")

    print("\n" + "=" * 60)
    print(f"SUMMARY: {len(results['ok'])} OK  |  {len(results['fail'])} FAIL  |  {len(results['other'])} UNKNOWN")

    if results["fail"]:
        print("\nFAILED URLs (need correct paths):")
        for item in results["fail"]:
            print(f"  {item[1]:<25} {BASE_URL + item[2]}")

    if results["other"]:
        print("\nUNKNOWN results (manual review needed):")
        for item in results["other"]:
            print(f"  {item[1]:<25} landed on: {item[3]}")

    browser.close()

if __name__ == "__main__":
    main()
