import requests
from datetime import date, timedelta

BASE = "http://127.0.0.1:5000"   # runs on the same laptop as app.py, so localhost is correct

# Newest spray first; each entry is 14 days before the previous one.
start = date(2026, 6, 15)
gap = timedelta(days=14)

# (spray name, dosage, growth stage, status, notes)
plan = [
    ("Captan 50% WP",               "300 g / 100 L water", "Fruit Set",     "DONE",      "Sprayed 7 AM, clear sky, good coverage"),
    ("Mancozeb 75% WP",             "300 g / 100 L water", "Fruitlet",      "DONE",      "Low wind, full canopy covered"),
    ("Zineb + Hexaconazole 72% WP", "125 g / 100 L water", "Petal Fall",    "POSTPONED", "Rain forecast — delayed application"),
    ("Dodine 65% WP",               "60 g / 100 L water",  "Pink Bud",      "DONE",      "Primary scab spray"),
    ("Mancozeb 75% WP",             "300 g / 100 L water", "Tight Cluster", "SKIPPED",   "Skipped — heavy rain all week"),
    ("Horticultural Mineral Oil",   "2 L / 100 L water",   "Green Tip",     "DONE",      "Dormant oil for scale and aphid eggs"),
]

ok = 0
for i, (name, dosage, stage, status, notes) in enumerate(plan):
    d = start - gap * i
    entry = {
        "date": d.isoformat(),
        "spray_name": name,
        "dosage": dosage,
        "growth_stage": stage,
        "status": status,
        "notes": notes,
    }
    try:
        r = requests.post(f"{BASE}/api/log", json=entry, timeout=5)
        print(d.isoformat(), status, "->", r.status_code)
        if r.status_code in (200, 201):
            ok += 1
    except Exception as e:
        print("FAILED:", e)

print(f"\nDone. {ok}/{len(plan)} entries added. Refresh the Logs tab in the app.")