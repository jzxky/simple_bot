"""
Static unlock requirements for character traits and skills.
Each entry maps to a trait/skill name exactly as it appears on playerstats.asp.

Requirement types and how they map to cached character history fields:
  earn_category  — earn_history[category][earn_type].count  (e.g. Hospital → Surgeon)
  earn_total     — earn_history[Summary][Total earns].count
  stat_value     — stat_sections[title][key] parsed as int  (e.g. Community Services)
  crime_count    — stat_sections["Crimes Committed"][key] parsed as int
  promotion_count— count of promotion_history rows matching occupation/rank filter

Excluded from this list (not useful to track):
  - Throw Snowball
  - Bloodlust

Fill in `target` values from the game wiki or in-game trait descriptions.
"""

REQUIREMENTS = {
    "My mind's on money!": {
        "ranks": 2,
        "description": "Earn bonuses from criminal activity.",
        "requirements": [
            # Example — fill in actual count required:
            # {"type": "earn_category", "label": "Hospital Earns", "category": "Hospital", "earn_type": "Surgeon", "target": 500},
        ],
    },
    "I can heal anyone!": {
        "ranks": 3,
        "description": "Improved medical work outcomes.",
        "requirements": [
            # {"type": "earn_category", "label": "Hospital Earns", "category": "Hospital", "earn_type": "Hospital Director", "target": 250},
        ],
    },
    "Job hopping is what I do!": {
        "ranks": 1,
        "description": "Reduces penalty for changing occupation.",
        "requirements": [
            # {"type": "promotion_count", "label": "Occupation changes", "target": 10},
        ],
    },
    "I've got the whole wide world in my hand!": {
        "ranks": 3,
        "description": "Bonuses for travelling between cities.",
        "requirements": [
            # {"type": "promotion_count", "label": "City changes", "filter_field": "city", "target": 5},
        ],
    },
    "Death made me hard as nails!": {
        "ranks": 3,
        "description": "Survival bonuses.",
        "requirements": [
            # {"type": "stat_value", "label": "Whacks Survived", "section": "Whacking Info", "key": "Whacks Survived", "target": 1},
        ],
    },
    "Handyman": {
        "ranks": 1,
        "description": "Engineering work bonuses.",
        "requirements": [
            # {"type": "earn_category", "label": "Engineering Earns", "category": "Engineering", "earn_type": "Engineer", "target": 100},
        ],
    },
    "Drug Runner": {
        "ranks": 3,
        "description": "Drug smuggling bonuses.",
        "requirements": [
            # {"type": "stat_value", "label": "Drug units", "section": "Character Information", "key": "Drug units", "target": 50},
        ],
    },
    "Tough as old boots!": {
        "ranks": 3,
        "description": "Increased health regeneration.",
        "requirements": [
            # {"type": "stat_value", "label": "Gym Trains", "section": "Character Information", "key": "Gym Trains", "target": 100},
        ],
    },
    "DNA Tampering": {
        "ranks": 1,
        "description": "Alter DNA results.",
        "requirements": [
            # {"type": "earn_category", "label": "Hospital Earns (DNA)", "category": "Hospital", "earn_type": "Hospital Director", "target": 100},
        ],
    },
    "JailBreak Master": {
        "ranks": 1,
        "description": "Improved jail break success rate.",
        "requirements": [
            # {"type": "crime_count", "label": "Jail Breaks", "key": "Jail Breaks", "target": 5},
        ],
    },
    "Combat Medic": {
        "ranks": 3,
        "description": "Heal during combat.",
        "requirements": [
            # {"type": "earn_category", "label": "Hospital Earns", "category": "Hospital", "earn_type": "Surgeon", "target": 300},
        ],
    },
    "Diligent Worker": {
        "ranks": 1,
        "description": "Extra earn reward chance.",
        "requirements": [
            # {"type": "earn_total", "label": "Total Earns", "target": 1000},
        ],
    },
    "Mafia Hit Squad: Planner": {
        "ranks": 1,
        "description": "Plan hit squad operations.",
        "requirements": [],
    },
    "Mafia Hit Squad: Gunsman": {
        "ranks": 1,
        "description": "Execute hit squad attacks.",
        "requirements": [],
    },
    "Mafia Hit Squad: Lookout": {
        "ranks": 1,
        "description": "Scout hit squad targets.",
        "requirements": [],
    },
    "Mafia Hit Squad: Getaway Driver": {
        "ranks": 1,
        "description": "Drive the getaway vehicle.",
        "requirements": [],
    },
    "Mafia Hit Squad: Retrain": {
        "ranks": 1,
        "description": "Retrain hit squad role.",
        "requirements": [],
    },
    "On top of the news!": {
        "ranks": 1,
        "description": "Newspaper editor bonuses.",
        "requirements": [
            # {"type": "earn_category", "label": "Secret Earns (Newspaper)", "category": "Secret", "earn_type": "Newspaper Editor", "target": 50},
        ],
    },
    "Devil's Advocate": {
        "ranks": 5,
        "description": "Law work bonuses.",
        "requirements": [
            # {"type": "earn_category", "label": "Law Earns", "category": "Law", "earn_type": "Judge", "target": 100},
        ],
    },
    "Quick as a flash!": {
        "ranks": 3,
        "description": "Faster action timer.",
        "requirements": [
            # {"type": "stat_value", "label": "Community Services", "section": "Character Information", "key": "Community Services", "target": 500},
        ],
    },
    "It's gettin' too hot!": {
        "ranks": 3,
        "description": "Fire fighting bonuses.",
        "requirements": [
            # {"type": "earn_category", "label": "Fire Earns", "category": "Fire", "earn_type": "Fire Chief", "target": 200},
        ],
    },
    "Travel Expert": {
        "ranks": 1,
        "description": "Reduced travel time.",
        "requirements": [],
    },
    "Private Investigator": {
        "ranks": 1,
        "description": "Track other players.",
        "requirements": [
            # {"type": "earn_category", "label": "Police Earns", "category": "Police", "earn_type": "Assign Duties", "target": 500},
        ],
    },
    "All Seeing Eye": {
        "ranks": 1,
        "description": "Extended player tracking.",
        "requirements": [],
    },
    "Biometric Virus": {
        "ranks": 3,
        "description": "Hack biometric systems.",
        "requirements": [
            # {"type": "crime_count", "label": "Hacking", "key": "Hacking", "target": 500},
        ],
    },
}

# Traits/skills to never show in the locked list
HIDDEN_FROM_LOCKED = {"Throw Snowball", "Bloodlust", "Diligent Worker"}


def evaluate_progress(name: str, char_data: dict) -> list:
    """
    Returns a list of progress dicts for each requirement of a trait/skill.
    Each dict: {label, current, target, pct}
    """
    entry = REQUIREMENTS.get(name)
    if not entry:
        return []

    results = []
    for req in entry.get("requirements", []):
        current = _resolve(req, char_data)
        target = req.get("target", 0)
        pct = min(100, int(current / target * 100)) if target > 0 else 0
        results.append({
            "label": req["label"],
            "current": current,
            "target": target,
            "pct": pct,
        })
    return results


def _resolve(req: dict, data: dict) -> int:
    rtype = req.get("type")

    if rtype == "earn_total":
        for cat in data.get("earn_history", []):
            if cat["category"] == "Summary":
                for e in cat["entries"]:
                    if "Total" in e["type"]:
                        return e["count"]
        return 0

    if rtype == "earn_category":
        category = req["category"]
        earn_type = req["earn_type"]
        for cat in data.get("earn_history", []):
            if cat["category"] == category:
                for e in cat["entries"]:
                    if e["type"] == earn_type:
                        return e["count"]
        return 0

    if rtype == "stat_value":
        section_title = req["section"]
        key = req["key"]
        for sec in data.get("stat_sections", []):
            if sec["title"] == section_title:
                for row in sec["rows"]:
                    if row["key"] == key:
                        try:
                            return int(str(row["value"]).replace(",", "").split()[0])
                        except Exception:
                            return 0
        return 0

    if rtype == "crime_count":
        key = req["key"]
        for sec in data.get("stat_sections", []):
            if sec["title"] == "Crimes Committed":
                for row in sec["rows"]:
                    if row["key"] == key:
                        try:
                            return int(str(row["value"]).replace(",", ""))
                        except Exception:
                            return 0
        return 0

    if rtype == "promotion_count":
        history = data.get("promotion_history", [])
        filter_field = req.get("filter_field")
        if filter_field:
            seen = set()
            for p in history:
                seen.add(p.get(filter_field, ""))
            return len(seen) - (1 if "" in seen else 0)
        return len(history)

    return 0
