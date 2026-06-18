"""
Promotion data: all 40 ranks, their stat options, and int-maximising defaults.
"""

PROMOTIONS = [
    {"category": "Jail",         "rank": "Schooled",             "slug": "schooled",             "path": "/promotion/schooled.asp",            "a": "off+25/def+25",          "b": "off+30/def+20",          "int_a": 0,  "int_b": 0,  "default": "A"},
    {"category": "Jail",         "rank": "Mule",                 "slug": "mule",                 "path": "/promotion/mule.asp",                "a": "off+100/def+80",         "b": "off+80/def+100",         "int_a": 0,  "int_b": 0,  "default": "A"},
    {"category": "Jail",         "rank": "Hardrock",             "slug": "hardrock",             "path": "/promotion/hardrock.asp",            "a": "off+200/def+150",        "b": "off+250/def+150",        "int_a": 0,  "int_b": 0,  "default": "A"},
    {"category": "Jail",         "rank": "Lifer",                "slug": "lifer",                "path": "/promotion/lifer.asp",               "a": "off+200/def+80",         "b": "off+250/def+80",         "int_a": 0,  "int_b": 0,  "default": "A"},
    {"category": "City",         "rank": "Mayor",                "slug": "mayor",                "path": "/promotion/mayor.asp",               "a": "off+10/def+350/int+15",  "b": "off+50/def+260/int+25",  "int_a": 15, "int_b": 25, "default": "B"},
    {"category": "Bank",         "rank": "Bank Teller",          "slug": "bank_teller",          "path": "/promotion/bankteller.asp",          "a": "off+5/def+10/int+10",    "b": "off+10/def+6/int+10",    "int_a": 10, "int_b": 10, "default": "A"},
    {"category": "Bank",         "rank": "Loan Officer",         "slug": "loan_officer",         "path": "/promotion/loanofficer.asp",         "a": "off+12/def+105/int+20",  "b": "off+25/def+95/int+5",    "int_a": 20, "int_b": 5,  "default": "A"},
    {"category": "Bank",         "rank": "Bank Manager",         "slug": "bank_manager",         "path": "/promotion/bankmanager.asp",         "a": "off+5/def+50/int+20",    "b": "off+22/def+116/int+5",   "int_a": 20, "int_b": 5,  "default": "A"},
    {"category": "Fire",         "rank": "Fire Fighter",         "slug": "fire_fighter",         "path": "/promotion/firefighter.asp",         "a": "off+65/def+115/int+10",  "b": "off+25/def+205/int+45",  "int_a": 10, "int_b": 45, "default": "B"},
    {"category": "Fire",         "rank": "Fire Chief",           "slug": "fire_chief",           "path": "/promotion/firechief.asp",           "a": "off+50/def+200/int+20",  "b": "off+100/def+150/int+25", "int_a": 20, "int_b": 25, "default": "B"},
    {"category": "Funeral",      "rank": "Mortician Assistant",  "slug": "mortician_assistant",  "path": "/promotion/morticianassistant.asp",  "a": "off+12/def+100/int+15",  "b": "off+30/def+60/int+30",   "int_a": 15, "int_b": 30, "default": "B"},
    {"category": "Funeral",      "rank": "Mortician",            "slug": "mortician",            "path": "/promotion/mortician.asp",           "a": "off+15/def+90/int+20",   "b": "off+25/def+120/int+5",   "int_a": 20, "int_b": 5,  "default": "A"},
    {"category": "Funeral",      "rank": "Funeral Director",     "slug": "funeral_director",     "path": "/promotion/funeraldirector.asp",     "a": "off+12/def+110/int+20",  "b": "off+40/def+95/int+5",    "int_a": 20, "int_b": 5,  "default": "A"},
    {"category": "Hospital",     "rank": "Nurse",                "slug": "nurse",                "path": "/promotion/nurse.asp",               "a": "off+12/def+10/int+25",   "b": "off+20/def+15/int+5",    "int_a": 25, "int_b": 5,  "default": "A"},
    {"category": "Hospital",     "rank": "Doctor",               "slug": "doctor",               "path": "/promotion/doctor.asp",              "a": "off+54/def+105/int+5",   "b": "off+15/def+185/int+35",  "int_a": 5,  "int_b": 35, "default": "B"},
    {"category": "Hospital",     "rank": "Surgeon",              "slug": "surgeon",              "path": "/promotion/surgeon.asp",             "a": "off+74/def+115/int+10",  "b": "off+25/def+205/int+55",  "int_a": 10, "int_b": 55, "default": "B"},
    {"category": "Hospital",     "rank": "Hospital Director",    "slug": "hospital_director",    "path": "/promotion/hospitaldirector.asp",    "a": "off+12/def+110/int+20",  "b": "off+50/def+80/int+5",    "int_a": 20, "int_b": 5,  "default": "A"},
    {"category": "Law",          "rank": "Legal Secretary",      "slug": "legal_secretary",      "path": "/promotion/legalsecretary.asp",      "a": "off+15/def+100/int+20",  "b": "off+22/def+80/int+25",   "int_a": 20, "int_b": 25, "default": "B"},
    {"category": "Law",          "rank": "Lawyer",               "slug": "lawyer",               "path": "/promotion/lawyer.asp",              "a": "off+15/def+110/int+20",  "b": "off+30/def+90/int+35",   "int_a": 20, "int_b": 35, "default": "B"},
    {"category": "Law",          "rank": "Judge",                "slug": "judge",                "path": "/promotion/judge.asp",               "a": "off+20/def+250/int+35",  "b": "off+20/def+250/int+35",  "int_a": 35, "int_b": 35, "default": "A"},
    {"category": "Law",          "rank": "Supreme Court Judge",  "slug": "supreme_court_judge",  "path": "/promotion/supremecourtjudge.asp",   "a": "off+350/def+100/int+35", "b": "off+100/def+350/int+55", "int_a": 35, "int_b": 55, "default": "B"},
    {"category": "Construction", "rank": "Mechanic",             "slug": "mechanic",             "path": "/promotion/mechanic.asp",            "a": "off+12/def+10/int+25",   "b": "off+20/def+15/int+5",    "int_a": 25, "int_b": 5,  "default": "A"},
    {"category": "Construction", "rank": "Technician",           "slug": "technician",           "path": "/promotion/technician.asp",          "a": "off+54/def+105/int+5",   "b": "off+15/def+185/int+35",  "int_a": 5,  "int_b": 35, "default": "B"},
    {"category": "Construction", "rank": "Engineer",             "slug": "engineer",             "path": "/promotion/engineer.asp",            "a": "off+74/def+115/int+10",  "b": "off+25/def+205/int+55",  "int_a": 10, "int_b": 55, "default": "B"},
    {"category": "Construction", "rank": "Chief Engineer",       "slug": "chief_engineer",       "path": "/promotion/chiefengineer.asp",       "a": "off+12/def+110/int+20",  "b": "off+50/def+80/int+5",    "int_a": 20, "int_b": 5,  "default": "A"},
    {"category": "Customs",      "rank": "Supervisor",           "slug": "supervisor",           "path": "/promotion/supervisor.asp",          "a": "off+15/def+90/int+20",   "b": "off+25/def+120/int+5",   "int_a": 20, "int_b": 5,  "default": "A"},
    {"category": "Customs",      "rank": "Superintendent",       "slug": "superintendent",       "path": "/promotion/superintendent.asp",      "a": "off+12/def+100/int+15",  "b": "off+30/def+60/int+30",   "int_a": 15, "int_b": 30, "default": "B"},
    {"category": "Customs",      "rank": "Commissioner-General", "slug": "commissioner_general", "path": "/promotion/commissionergeneral.asp", "a": "off+12/def+110/int+20",  "b": "off+40/def+95/int+5",    "int_a": 20, "int_b": 5,  "default": "A"},
    {"category": "Police",       "rank": "Sergeant",             "slug": "sergeant",             "path": "/promotion/sergeant.asp",            "a": "off+12/def+210/int+25",  "b": "off+45/def+150/int+35",  "int_a": 25, "int_b": 35, "default": "B"},
    {"category": "Police",       "rank": "Senior Sergeant",      "slug": "senior_sergeant",      "path": "/promotion/seniorsergeant.asp",      "a": "off+30/def+260/int+14",  "b": "off+35/def+150/int+12",  "int_a": 14, "int_b": 12, "default": "A"},
    {"category": "Police",       "rank": "Detective",            "slug": "detective",            "path": "/promotion/detective.asp",           "a": "off+12/def+210/int+15",  "b": "off+40/def+170/int+30",  "int_a": 15, "int_b": 30, "default": "B"},
    {"category": "Police",       "rank": "Commissioner",         "slug": "commissioner",         "path": "/promotion/commissioner.asp",        "a": "off+10/def+350/int+15",  "b": "off+50/def+260/int+25",  "int_a": 15, "int_b": 25, "default": "B"},
    {"category": "Gangster",     "rank": "Dealer",               "slug": "dealer",               "path": "/promotion/dealer.asp",              "a": "off+12/def+8/int+20",    "b": "off+22/def+16/int+5",    "int_a": 20, "int_b": 5,  "default": "A"},
    {"category": "Gangster",     "rank": "Giovane D'Honore",     "slug": "giovane_dhonore",      "path": "/promotion/giovaneDhonore.asp",      "a": "off+19/def+12/int+25",   "b": "off+29/def+20/int+10",   "int_a": 25, "int_b": 10, "default": "A"},
    {"category": "Gangster",     "rank": "Enforcer",             "slug": "enforcer",             "path": "/promotion/enforcer.asp",            "a": "off+18/def+20/int+30",   "b": "off+30/def+28/int+10",   "int_a": 30, "int_b": 10, "default": "A"},
    {"category": "Gangster",     "rank": "Piciotto",             "slug": "piciotto",             "path": "/promotion/piciotto.asp",            "a": "off+20/def+30/int+30",   "b": "off+35/def+21/int+12",   "int_a": 30, "int_b": 12, "default": "A"},
    {"category": "Gangster",     "rank": "Sgarrista",            "slug": "sgarrista",            "path": "/promotion/sgarrista.asp",           "a": "off+18/def+20/int+30",   "b": "off+30/def+28/int+10",   "int_a": 30, "int_b": 10, "default": "A"},
    {"category": "Gangster",     "rank": "Capodecima",           "slug": "capodecima",           "path": "/promotion/capodecima.asp",          "a": "off+18/def+20/int+30",   "b": "off+30/def+28/int+10",   "int_a": 30, "int_b": 10, "default": "A"},
    {"category": "Gangster",     "rank": "Caporegime",           "slug": "caporegime",           "path": "/promotion/caporegime.asp",          "a": "off+18/def+20/int+30",   "b": "off+30/def+28/int+10",   "int_a": 30, "int_b": 10, "default": "A"},
    {"category": "Gangster",     "rank": "Boss",                 "slug": "boss",                 "path": "/promotion/boss.asp",                "a": "off+24/def+20/int+10",   "b": "off+18/def+18/int+35",   "int_a": 10, "int_b": 35, "default": "B"},
    {"category": "Gangster",     "rank": "Don",                  "slug": "don",                  "path": "/promotion/don.asp",                 "a": "off+15/def+15/int+35",   "b": "off+20/def+20/int+15",   "int_a": 35, "int_b": 15, "default": "A"},
]

PROMO_BY_RANK = {p["rank"]: p for p in PROMOTIONS}
PROMO_BY_SLUG = {p["slug"]: p for p in PROMOTIONS}
PROMO_BY_PATH = {p["path"].lower(): p for p in PROMOTIONS}


def get_choice(slug: str) -> str:
    """Return 'A' or 'B' from config, falling back to the int-maximising default."""
    import config as cfg
    stored = cfg.load().get("promo", {}).get("choices", {}).get(slug)
    if stored in ("A", "B"):
        return stored
    promo = PROMO_BY_SLUG.get(slug)
    return promo["default"] if promo else "A"


def match_url(url: str):
    """Return the promotion dict whose path matches the given URL, or None."""
    url_lower = url.rstrip("/").lower()
    for path, promo in PROMO_BY_PATH.items():
        if url_lower.endswith(path.rstrip("/")):
            return promo
    return None
