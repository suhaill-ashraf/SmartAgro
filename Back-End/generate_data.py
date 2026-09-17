"""
SmartAgro Backend — ML Training Data Generator (Gray-Zone + Combination Edition)
Generates 5000 rows of synthetic training data for Random Forest classifier.

Key design:
  - days_since_spray capped at 20 days MAX
  - 40% HARD rows  → single-feature clearly over threshold
  - 60% GRAY rows  → combinations near threshold (rain=37+wind=17 → DELAY)
  - Labels by SCORING — combination of all features, not single hard rules
  - rain=37% + wind=17 km/h → combined delay_score → DELAY
  - Single safe features with borderline others → correct combined label

Thresholds (config.py):
  RAIN_THRESHOLD = 40%
  WIND_THRESHOLD = 20 km/h
  TEMP_MIN = 5°C  |  TEMP_MAX = 35°C
  days_since_spray max = 20 days

Output: data/training_data.csv
"""

import os
import random
from datetime import datetime

import pandas as pd

from config import (
    RAIN_THRESHOLD,
    WIND_THRESHOLD,
    TEMP_MIN,
    TEMP_MAX,
    GROWTH_STAGES,
    STAGE_INTERVALS,
    TRAINING_DATA_PATH,
    DATA_DIR,
    DECISION_SPRAY,
    DECISION_DELAY,
    DECISION_SKIP,
    RANDOM_STATE,
    FEATURES,
)

# ════════════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════════════
MAX_DAYS_SINCE_SPRAY = 20   # hard cap — never exceed 20 days


# ════════════════════════════════════════════════════════════════
# SCORING LABEL FUNCTION — Combination-aware
#
# delay_score:  rain + wind combined risk
# skip_score:   temp + interval combined risk
#
# KEY COMBINATION RULE:
#   rain=37% alone   → delay_score = 23  (not enough alone)
#   wind=17 alone    → delay_score = 17  (not enough alone)
#   rain=37+wind=17  → delay_score = 40  → DELAY ✓
#
# This is exactly what rules.py CANNOT do —
# it only checks each rule independently.
# ════════════════════════════════════════════════════════════════
def score_and_label(
    rain_prob:        float,
    wind_kmh:         float,
    temp_c:           float,
    days_since_spray: int,
    growth_stage:     str,
) -> str:

    min_interval = STAGE_INTERVALS.get(growth_stage, 14)
    delay_score  = 0
    skip_score   = 0

    # ── Rain risk (0–40 points) ──────────────────────────────────
    # >= 40%  → full 40 points  (single-feature DELAY)
    # 25–39%  → proportional    (gray zone — contributes to combination)
    # < 25%   → 0               (clearly safe)
    if rain_prob >= RAIN_THRESHOLD:                        # >= 40%
        delay_score += 40
    elif rain_prob >= RAIN_THRESHOLD - 15:                 # 25–39%
        delay_score += int((rain_prob / RAIN_THRESHOLD) * 25)
        # e.g. rain=37 → int(37/40 × 25) = int(23.1) = 23 pts

    # ── Wind risk (0–30 points) ──────────────────────────────────
    # >= 20   → full 30 points  (single-feature DELAY)
    # 12–19   → proportional    (gray zone — combines with rain)
    # < 12    → 0               (clearly safe)
    if wind_kmh >= WIND_THRESHOLD:                         # >= 20
        delay_score += 30
    elif wind_kmh >= WIND_THRESHOLD - 8:                   # 12–19
        delay_score += int((wind_kmh / WIND_THRESHOLD) * 25)
        # e.g. wind=17 → int(17/20 × 25) = int(21.25) = 21 pts

    # COMBINATION RESULT:
    # rain=37 → 23pts  +  wind=17 → 21pts  =  44pts → DELAY ✓
    # rain=37 alone   → 23pts               → not enough → check skip
    # wind=17 alone   → 21pts               → not enough → check skip

    # ── Temperature risk (0–25 points) ──────────────────────────
    # Outside 5–35°C → points scale with distance from boundary
    # Within 3°C of boundary → 10 borderline points
    if temp_c < TEMP_MIN:                                  # below 5°C
        skip_score += min(25, int((TEMP_MIN - temp_c) * 5))
        # e.g. temp=2°C → (5-2)*5 = 15 pts
    elif temp_c > TEMP_MAX:                                # above 35°C
        skip_score += min(25, int((temp_c - TEMP_MAX) * 5))
        # e.g. temp=38°C → (38-35)*5 = 15 pts
    elif temp_c < TEMP_MIN + 3 or temp_c > TEMP_MAX - 3:  # 5–8°C or 32–35°C
        skip_score += 10                                   # borderline temp

    # ── Interval risk (0–25 points) ─────────────────────────────
    # days_since < min_interval → points scale with how far below
    # exactly at threshold → 5 borderline points
    # Note: days_since is already capped at MAX_DAYS_SINCE_SPRAY=20
    if days_since_spray < min_interval:
        gap_ratio   = days_since_spray / max(min_interval, 1)
        skip_score += int((1 - gap_ratio) * 25)
        # e.g. days=0, interval=14 → (1-0)*25 = 25 pts
        # e.g. days=12, interval=14 → (1-12/14)*25 = 3 pts
    elif days_since_spray == min_interval:
        skip_score += 5                                    # exactly at threshold

    # ── Final combined decision ──────────────────────────────────
    #
    # Thresholds for decision:
    #   delay_score >= 35 → DELAY  (rain or wind clearly bad, or combined risk high)
    #   skip_score  >= 28 → SKIP   (temp or interval clearly bad)
    #   both 18–34        → gray zone → pick the higher risk
    #   both < 18         → SPRAY  (all conditions comfortably safe)
    #
    if delay_score >= 35:
        return DECISION_DELAY
    if skip_score >= 28:
        return DECISION_SKIP
    if delay_score >= 18 or skip_score >= 18:
        if delay_score > skip_score:
            return DECISION_DELAY
        elif skip_score > delay_score:
            return DECISION_SKIP
        else:
            return DECISION_SPRAY   # tie → safe enough
    return DECISION_SPRAY


# ════════════════════════════════════════════════════════════════
# HARD ROW — 40% of dataset
# Single-feature clearly crosses threshold.
# Teaches model to be confident on obvious cases.
# days_since_spray capped at MAX_DAYS_SINCE_SPRAY = 20
# ════════════════════════════════════════════════════════════════
def sample_hard_row(growth_stage: str) -> dict:
    min_interval = STAGE_INTERVALS.get(growth_stage, 14)
    bucket = random.choice([
        "spray", "delay_rain", "delay_wind", "skip_temp", "skip_interval"
    ])

    if bucket == "spray":
        # All features clearly safe — far from every threshold
        temp_c     = round(random.uniform(TEMP_MIN + 5, TEMP_MAX - 5), 1)  # 10–30°C
        humidity   = round(random.uniform(30.0, 70.0), 1)
        wind_kmh   = round(random.uniform(0.0, WIND_THRESHOLD - 9), 1)     # 0–11 km/h
        rain_prob  = round(random.uniform(0.0, RAIN_THRESHOLD - 18), 1)    # 0–22%
        days_since = random.randint(
            min(min_interval + 1, MAX_DAYS_SINCE_SPRAY),
            MAX_DAYS_SINCE_SPRAY
        )

    elif bucket == "delay_rain":
        # Rain clearly over 40% — no ambiguity
        temp_c     = round(random.uniform(TEMP_MIN + 4, TEMP_MAX - 4), 1)  # 9–31°C
        humidity   = round(random.uniform(55.0, 95.0), 1)
        wind_kmh   = round(random.uniform(0.0, WIND_THRESHOLD - 6), 1)     # 0–14 km/h
        rain_prob  = round(random.uniform(RAIN_THRESHOLD + 12, 100.0), 1)  # 52–100%
        days_since = random.randint(
            min(min_interval, MAX_DAYS_SINCE_SPRAY),
            MAX_DAYS_SINCE_SPRAY
        )

    elif bucket == "delay_wind":
        # Wind clearly over 20 km/h — no ambiguity
        temp_c     = round(random.uniform(TEMP_MIN + 4, TEMP_MAX - 4), 1)  # 9–31°C
        humidity   = round(random.uniform(25.0, 65.0), 1)
        wind_kmh   = round(random.uniform(WIND_THRESHOLD + 5, 35.0), 1)    # 25–35 km/h
        rain_prob  = round(random.uniform(0.0, RAIN_THRESHOLD - 12), 1)    # 0–28%
        days_since = random.randint(
            min(min_interval, MAX_DAYS_SINCE_SPRAY),
            MAX_DAYS_SINCE_SPRAY
        )

    elif bucket == "skip_temp":
        # Temp clearly outside 5–35°C
        temp_c = random.choice([
            round(random.uniform(-5.0, TEMP_MIN - 3), 1),   # below 2°C
            round(random.uniform(TEMP_MAX + 3, 40.0), 1),   # above 38°C
        ])
        humidity   = round(random.uniform(20.0, 80.0), 1)
        wind_kmh   = round(random.uniform(0.0, WIND_THRESHOLD - 6), 1)
        rain_prob  = round(random.uniform(0.0, RAIN_THRESHOLD - 12), 1)
        days_since = random.randint(
            min(min_interval, MAX_DAYS_SINCE_SPRAY),
            MAX_DAYS_SINCE_SPRAY
        )

    else:  # skip_interval
        # days_since clearly below min_interval
        temp_c     = round(random.uniform(TEMP_MIN + 4, TEMP_MAX - 4), 1)
        humidity   = round(random.uniform(30.0, 70.0), 1)
        wind_kmh   = round(random.uniform(0.0, WIND_THRESHOLD - 6), 1)
        rain_prob  = round(random.uniform(0.0, RAIN_THRESHOLD - 12), 1)
        days_since = random.randint(0, max(1, min_interval - 4))
        days_since = min(days_since, MAX_DAYS_SINCE_SPRAY)  # cap

    return dict(
        temp_c=temp_c, humidity=humidity,
        wind_kmh=wind_kmh, rain_prob=rain_prob,
        days_since_spray=days_since, growth_stage=growth_stage,
    )


# ════════════════════════════════════════════════════════════════
# GRAY ROW — 60% of dataset
# Features sampled near thresholds so combinations matter.
# This is where rain=37+wind=17 rows live.
# days_since_spray capped at MAX_DAYS_SINCE_SPRAY = 20
# ════════════════════════════════════════════════════════════════
def sample_gray_row(growth_stage: str) -> dict:
    min_interval = STAGE_INTERVALS.get(growth_stage, 14)

    temp_c     = round(random.uniform(TEMP_MIN - 3, TEMP_MAX + 3), 1)       # 2–38°C
    humidity   = round(random.uniform(25.0, 90.0), 1)
    wind_kmh   = round(random.uniform(
        max(0.0, WIND_THRESHOLD - 8), WIND_THRESHOLD + 8), 1)               # 12–28 km/h
    rain_prob  = round(random.uniform(
        max(0.0, RAIN_THRESHOLD - 15), min(100.0, RAIN_THRESHOLD + 15)), 1) # 25–55%
    days_since = random.randint(
        max(0, min_interval - 3),
        min(min_interval + 3, MAX_DAYS_SINCE_SPRAY)                          # cap at 20
    )

    return dict(
        temp_c=temp_c, humidity=humidity,
        wind_kmh=wind_kmh, rain_prob=rain_prob,
        days_since_spray=days_since, growth_stage=growth_stage,
    )


# ════════════════════════════════════════════════════════════════
# GENERATE 5000 ROWS — 40% hard + 60% gray
# Balanced: ~1666 each for SPRAY / DELAY / SKIP
# ════════════════════════════════════════════════════════════════
def generate_rows(n_rows: int = 5000) -> list:
    random.seed(RANDOM_STATE)
    rows = []

    target       = n_rows // 3
    counts       = {DECISION_SPRAY: 0, DECISION_DELAY: 0, DECISION_SKIP: 0}
    hard_limit   = int(n_rows * 0.40)   # 2000 hard rows
    gray_limit   = n_rows - hard_limit  # 3000 gray rows
    hard_count   = 0
    gray_count   = 0
    attempts     = 0
    max_attempts = n_rows * 60

    while min(counts.values()) < target and attempts < max_attempts:
        attempts += 1
        growth_stage = random.choice(GROWTH_STAGES)

        if hard_count < hard_limit and (
            gray_count >= gray_limit or random.random() < 0.40
        ):
            sample  = sample_hard_row(growth_stage)
            is_hard = True
        else:
            sample  = sample_gray_row(growth_stage)
            is_hard = False

        label = score_and_label(
            rain_prob        = sample["rain_prob"],
            wind_kmh         = sample["wind_kmh"],
            temp_c           = sample["temp_c"],
            days_since_spray = sample["days_since_spray"],
            growth_stage     = growth_stage,
        )

        if counts[label] >= target:
            continue

        min_interval  = STAGE_INTERVALS.get(growth_stage, 14)
        stage_encoded = GROWTH_STAGES.index(growth_stage)

        rows.append({
            "temp_c":           sample["temp_c"],
            "humidity":         sample["humidity"],
            "wind_kmh":         sample["wind_kmh"],
            "rain_prob":        sample["rain_prob"],
            "days_since_spray": sample["days_since_spray"],
            "stage_encoded":    stage_encoded,
            "min_interval":     min_interval,
            "growth_stage":     growth_stage,
            "label":            label,
        })

        counts[label] += 1
        if is_hard:
            hard_count += 1
        else:
            gray_count += 1

    return rows


# ════════════════════════════════════════════════
# SAVE CSV
# ════════════════════════════════════════════════
def save_csv(rows: list) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    df = pd.DataFrame(rows)
    df = df[FEATURES + ["growth_stage", "label"]]
    df.to_csv(TRAINING_DATA_PATH, index=False)
    print(f"  [DATA] Saved {len(df)} rows → {TRAINING_DATA_PATH}")


# ════════════════════════════════════════════════
# PRINT SUMMARY
# ════════════════════════════════════════════════
def print_summary(rows: list) -> None:
    df = pd.DataFrame(rows)
    print("\n" + "=" * 55)
    print("  TRAINING DATA SUMMARY")
    print("=" * 55)
    print(f"  Total rows       : {len(df)}")
    print(f"  Max days_since   : {df['days_since_spray'].max()} (cap={MAX_DAYS_SINCE_SPRAY})")
    print(f"  Features         : {FEATURES}")
    print()

    print("  Label Distribution:")
    for label, count in df["label"].value_counts().items():
        pct = round(count / len(df) * 100, 1)
        bar = "█" * (count // 50)
        print(f"    {label:<10} {count:>5} rows  ({pct}%)  {bar}")

    print()
    print("  Stage Distribution:")
    for stage, count in df["growth_stage"].value_counts().sort_index().items():
        print(f"    {stage:<30} {count:>5} rows")

    print()
    print("  Weather Ranges:")
    for col in ["temp_c", "humidity", "wind_kmh", "rain_prob", "days_since_spray"]:
        print(
            f"    {col:<22} "
            f"min={df[col].min():.1f}  "
            f"max={df[col].max():.1f}  "
            f"mean={df[col].mean():.1f}"
        )

    print()
    print("  Label × Stage cross-check:")
    cross = df.groupby(["label", "growth_stage"]).size().unstack(fill_value=0)
    print(cross.to_string())
    print("=" * 55 + "\n")


# ════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  SMARTAGRO — GENERATING TRAINING DATA")
    print("=" * 55)
    print(f"  Mode             : 40% hard + 60% gray-zone")
    print(f"  Target rows      : 5000 (~1666 per class)")
    print(f"  RAIN threshold   : {RAIN_THRESHOLD}%")
    print(f"  WIND threshold   : {WIND_THRESHOLD} km/h")
    print(f"  TEMP range       : {TEMP_MIN}–{TEMP_MAX}°C")
    print(f"  Max days_since   : {MAX_DAYS_SINCE_SPRAY} days")
    print(f"  Started          : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Output           : {TRAINING_DATA_PATH}")
    print()

    if os.path.exists(TRAINING_DATA_PATH):
        answer = input(
            "  training_data.csv already exists. Regenerate? (y/n): "
        ).strip().lower()
        if answer != "y":
            print("  Skipped — using existing training data.")
            raise SystemExit(0)

    print("  Generating rows...")
    rows = generate_rows(n_rows=5000)
    save_csv(rows)
    print_summary(rows)

    print(f"  Finished : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("  Next step: python train_model.py\n")