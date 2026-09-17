"""
SmartAgro Backend — Spray Decision Rules Engine
SKUAST-K 2026 | 4 Rule-Based Checks + SKUAST Schedule + Calendar Generator
Priority: Rule 1 → Rule 2 → Rule 3 → Rule 4
Random Forest ML is called ONLY if ALL 4 rules pass.
"""

from datetime import datetime, timedelta, date as date_type
from typing import Optional

from config import (
    RAIN_THRESHOLD,
    WIND_THRESHOLD,
    TEMP_MIN,
    TEMP_MAX,
    DEFAULT_MIN_INTERVAL,
    STAGE_INTERVALS,
    DECISION_SPRAY,
    DECISION_DELAY,
    DECISION_SKIP,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_HIGH,
    GROWTH_STAGES,
    SPRAY_WINDOW_TEXT,
)


# ════════════════════════════════════════════════
# RULE 1 — RAIN CHECK
# ════════════════════════════════════════════════
def check_rain(rain_probability: float) -> dict:
    """
    Rule 1: DELAY if rain probability >= 40%.
    Rain washes away fungicide before absorption.
    SKUAST-K threshold for Kashmir orchards.
    """
    passed = rain_probability < RAIN_THRESHOLD
    return {
        "rule":    "Rain Check",
        "passed":  passed,
        "value":   rain_probability,
        "limit":   RAIN_THRESHOLD,
        "unit":    "%",
        "tag":     "RAIN_SAFE" if passed else "RAIN_RISK",
        "message": (
            f"Rain {rain_probability}% is safe (below {RAIN_THRESHOLD}%)."
            if passed else
            f"Rain {rain_probability}% exceeds {RAIN_THRESHOLD}% threshold. Delay — chemical will wash off."
        ),
    }


# ════════════════════════════════════════════════
# RULE 2 — WIND CHECK
# ════════════════════════════════════════════════
def check_wind(wind_speed: float) -> dict:
    """
    Rule 2: DELAY if wind speed >= 20 km/h.
    High wind causes spray drift — uneven coverage.
    Safe limit for Kashmir apple orchards: ≤ 20 km/h.
    """
    passed = wind_speed < WIND_THRESHOLD
    return {
        "rule":    "Wind Check",
        "passed":  passed,
        "value":   wind_speed,
        "limit":   WIND_THRESHOLD,
        "unit":    "km/h",
        "tag":     "WIND_SAFE" if passed else "WIND_RISK",
        "message": (
            f"Wind {wind_speed} km/h is safe (below {WIND_THRESHOLD} km/h)."
            if passed else
            f"Wind {wind_speed} km/h exceeds {WIND_THRESHOLD} km/h. Delay — droplets will drift off target."
        ),
    }


# ════════════════════════════════════════════════
# RULE 3 — TEMPERATURE CHECK
# ════════════════════════════════════════════════
def check_temperature(temp_c: float) -> dict:
    """
    Rule 3: SKIP if temp < 5°C or > 35°C.
    Below 5°C — stomata close, chemical cannot absorb.
    Above 35°C — leaves scorch, chemical evaporates.
    Optimal range: 10–28°C.
    """
    passed = TEMP_MIN <= temp_c <= TEMP_MAX

    if temp_c < TEMP_MIN:
        tag     = "TEMP_TOO_COLD"
        message = f"Temp {temp_c}°C is too cold (below {TEMP_MIN}°C). Stomata closed — skip spray."
    elif temp_c > TEMP_MAX:
        tag     = "TEMP_TOO_HOT"
        message = f"Temp {temp_c}°C is too hot (above {TEMP_MAX}°C). Leaves will scorch — skip spray."
    else:
        tag     = "TEMP_SAFE"
        message = f"Temp {temp_c}°C is within safe range ({TEMP_MIN}–{TEMP_MAX}°C)."

    return {
        "rule":    "Temperature Check",
        "passed":  passed,
        "value":   temp_c,
        "limit":   f"{TEMP_MIN}–{TEMP_MAX}",
        "unit":    "°C",
        "tag":     tag,
        "message": message,
    }


# ════════════════════════════════════════════════
# RULE 4 — INTERVAL CHECK
# ════════════════════════════════════════════════
def check_interval(
    days_since_last_spray: int,
    min_interval: int,
    growth_stage: Optional[str] = None,
) -> dict:
    """
    Rule 4: SKIP if minimum spray interval has not passed.
    Prevents over-spraying and pesticide resistance.
    Uses stage-specific interval from SKUAST-K if available.
    """
    # Use stage-specific interval if available
    if growth_stage and growth_stage in STAGE_INTERVALS:
        effective_interval = STAGE_INTERVALS[growth_stage]
    else:
        effective_interval = min_interval

    passed    = days_since_last_spray >= effective_interval
    days_left = max(0, effective_interval - days_since_last_spray)

    return {
        "rule":                "Interval Check",
        "passed":              passed,
        "value":               days_since_last_spray,
        "limit":               effective_interval,
        "unit":                "days",
        "days_left":           days_left,
        "tag":                 "INTERVAL_OK" if passed else "TOO_SOON",
        "message": (
            f"{days_since_last_spray} days since last spray. "
            f"Minimum interval of {effective_interval} days has passed."
            if passed else
            f"Only {days_since_last_spray} days since last spray. "
            f"Wait {days_left} more day(s) (min interval: {effective_interval} days)."
        ),
    }


# ════════════════════════════════════════════════
# MAIN — GET SPRAY RECOMMENDATION
# ════════════════════════════════════════════════
def get_spray_recommendation(
    rain_probability:     float,
    wind_speed:           float,
    temp_c:               float,
    days_since_last_spray: int,
    growth_stage:         str = "Fruit Set",
    min_interval:         int = DEFAULT_MIN_INTERVAL,
) -> dict:
    """
    Runs all 4 rules in strict priority order.
    Stops at first failure — Random Forest only called if ALL 4 pass.

    Priority:
        Rule 1 (Rain)     → DELAY
        Rule 2 (Wind)     → DELAY
        Rule 3 (Temp)     → SKIP
        Rule 4 (Interval) → SKIP
        All pass          → call ML model → SPRAY / DELAY / SKIP
    """
    rule1 = check_rain(rain_probability)
    rule2 = check_wind(wind_speed)
    rule3 = check_temperature(temp_c)
    rule4 = check_interval(days_since_last_spray, min_interval, growth_stage)

    all_rules = [rule1, rule2, rule3, rule4]
    tags      = [r["tag"] for r in all_rules]
    failed    = [r for r in all_rules if not r["passed"]]

    if failed:
        first_fail = failed[0]
        # Rain / Wind → DELAY (external condition — wait for better weather)
        if first_fail["tag"] in ["RAIN_RISK", "WIND_RISK"]:
            decision = DECISION_DELAY
            risk     = RISK_HIGH
        # Temp too cold/hot → SKIP (cannot fix by waiting a few hours)
        elif first_fail["tag"] in ["TEMP_TOO_COLD", "TEMP_TOO_HOT"]:
            decision = DECISION_SKIP
            risk     = RISK_MEDIUM
        # Interval not met → SKIP (must wait minimum days)
        else:
            decision = DECISION_SKIP
            risk     = RISK_LOW

        reason = first_fail["message"]
    else:
        # All 4 rules passed — ML model will make final decision
        decision = DECISION_SPRAY   # Tentative — overridden by ML in app.py
        risk     = RISK_LOW
        reason   = "All 4 conditions passed. Safe to spray."

    return {
        "decision":   decision,
        "reason":     reason,
        "risk_level": risk,
        "all_passed": len(failed) == 0,
        "tags":       tags,
        "rules": {
            "rule_1_rain":     rule1,
            "rule_2_wind":     rule2,
            "rule_3_temp":     rule3,
            "rule_4_interval": rule4,
        },
    }


# ════════════════════════════════════════════════
# SKUAST-K 2026 — PHENOLOGICAL SCHEDULE
# Dates are relative to current year — never hardcoded
# ════════════════════════════════════════════════
SKUAST_PHENOLOGY = [
    {"spray_number":  1, "stage": "Delayed Dormancy",     "month": 2, "day": 20, "spray_required": True},
    {"spray_number":  2, "stage": "Green Tip",            "month": 3, "day":  5, "spray_required": True},
    {"spray_number":  3, "stage": "Tight Cluster",        "month": 3, "day": 18, "spray_required": True},
    {"spray_number":  4, "stage": "Pink Bud",             "month": 3, "day": 28, "spray_required": True},
    {"spray_number":  5, "stage": "Flowering",            "month": 4, "day":  8, "spray_required": False},
    {"spray_number":  6, "stage": "Petal Fall",           "month": 4, "day": 22, "spray_required": True},
    {"spray_number":  7, "stage": "Fruitlet",             "month": 5, "day":  6, "spray_required": True},
    {"spray_number":  8, "stage": "Fruit Set",            "month": 5, "day": 22, "spray_required": True},
    {"spray_number":  9, "stage": "Fruit Development-I",  "month": 6, "day": 10, "spray_required": True},
    {"spray_number": 10, "stage": "Fruit Development-II", "month": 7, "day":  5, "spray_required": True},
    {"spray_number": 11, "stage": "Fruit Development-III","month": 8, "day":  5, "spray_required": True},
    {"spray_number": 12, "stage": "Fruit Development-IV", "month": 8, "day": 25, "spray_required": False},
    {"spray_number": 13, "stage": "Pre-Harvest",          "month": 9, "day":  5, "spray_required": True},
    {"spray_number": 14, "stage": "Harvest",              "month": 9, "day": 25, "spray_required": False},
    {"spray_number": 15, "stage": "Post-Harvest",         "month": 10,"day": 20, "spray_required": False},
    {"spray_number": 16, "stage": "Dormancy",             "month": 11,"day": 15, "spray_required": False},
]


def get_skuast_schedule(year: Optional[int] = None) -> list:
    """
    Returns SKUAST-K schedule for a given year.
    Defaults to current year — dates are always dynamic.
    Each entry has PAST / TODAY / UPCOMING status.
    """
    today     = date_type.today()
    use_year  = year or today.year

    result = []
    for item in SKUAST_PHENOLOGY:
        try:
            spray_date = date_type(use_year, item["month"], item["day"])
        except ValueError:
            # Handle Feb 29 in non-leap years
            spray_date = date_type(use_year, item["month"], 28)

        if   spray_date <  today: status = "PAST"
        elif spray_date == today: status = "TODAY"
        else:                     status = "UPCOMING"

        result.append({
            "spray_number":   item["spray_number"],
            "stage":          item["stage"],
            "date":           spray_date.strftime("%Y-%m-%d"),
            "display_date":   spray_date.strftime("%d %b %Y"),
            "day":            spray_date.strftime("%A"),
            "spray_required": item["spray_required"],
            "status":         status,
        })

    return result


# ════════════════════════════════════════════════
# INTERVAL CALENDAR — Used by /api/calendar
# ════════════════════════════════════════════════
def generate_spray_schedule(
    start_date:   str,
    interval_days: int  = DEFAULT_MIN_INTERVAL,
    total_sprays:  int  = 20,
) -> list:
    """
    Generates interval-based spray calendar from farmer's last spray date.
    Used for the Yearly Calendar view in Android app.
    Each entry includes PAST / TODAY / UPCOMING status.
    """
    today = date_type.today()

    try:
        current = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        current = today

    schedule = []
    for i in range(1, total_sprays + 1):
        if   current <  today: status = "PAST"
        elif current == today: status = "TODAY"
        else:                  status = "UPCOMING"

        schedule.append({
            "spray_number": i,
            "date":         current.strftime("%Y-%m-%d"),
            "display_date": current.strftime("%d %b %Y"),
            "day":          current.strftime("%A"),
            "status":       status,
        })

        current += timedelta(days=interval_days)

    return schedule


# ════════════════════════════════════════════════
# NEXT SPRAY DATE — Used by Home Dashboard
# ════════════════════════════════════════════════
def get_next_spray_date(
    last_spray_date: str,
    interval_days:   int = DEFAULT_MIN_INTERVAL,
) -> dict:
    """
    Returns the next recommended spray date based on last spray + interval.
    Used by Home Dashboard to show 'Next spray in X days'.
    """
    today = date_type.today()

    try:
        last = datetime.strptime(last_spray_date, "%Y-%m-%d").date()
    except ValueError:
        last = today

    next_date  = last + timedelta(days=interval_days)
    days_until = (next_date - today).days

    if days_until < 0:
        label = "Overdue"
    elif days_until == 0:
        label = "Today"
    elif days_until == 1:
        label = "Tomorrow"
    else:
        label = f"In {days_until} days"

    return {
        "next_date":    next_date.strftime("%Y-%m-%d"),
        "display_date": next_date.strftime("%d %b %Y"),
        "day":          next_date.strftime("%A"),
        "days_until":   days_until,
        "label":        label,
        "overdue":      days_until < 0,
    }
def is_borderline(
    rain_prob: float,
    wind_speed: float,
    temp_c: float,
    humidity: float,
    days_since_spray: int,
    min_interval: int,
) -> bool:
    """
    Borderline detector for cases that passed hard rules
    but are still close to risky conditions.
    """
    if 30 <= rain_prob <= 40:                        return True
    if 15 <= wind_speed <= 20:                       return True
    if 5  <= temp_c     <= 8:                        return True
    if 30 <= temp_c     <= 35:                       return True
    if humidity >= 80:                               return True
    if 0 <= (days_since_spray - min_interval) <= 2:  return True
    return False