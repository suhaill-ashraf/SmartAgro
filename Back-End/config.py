"""
SmartAgro Backend — Configuration
SKUAST-K 2026 | Kashmir Apple Orchards
All constants, thresholds, paths, and settings live here.
Every other file imports from this file — never hardcode values elsewhere.
"""

import os

# ════════════════════════════════════════════════
# BASE DIRECTORY — All paths are absolute
# ════════════════════════════════════════════════
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")

# ════════════════════════════════════════════════
# FLASK SERVER SETTINGS
# ════════════════════════════════════════════════
FLASK_HOST  = "0.0.0.0"    # Accept connections from phone on same WiFi
FLASK_PORT  = 5000
FLASK_DEBUG = True

# ════════════════════════════════════════════════
# DATABASE
# ════════════════════════════════════════════════
DB_PATH            = os.path.join(DATA_DIR, "smartagro.db")
TABLE_ORCHARD      = "orchard_profile"
TABLE_SPRAY_LOG    = "spray_log"
TABLE_SPRAY_DB     = "spray_lookup"
TABLE_SETTINGS      = "app_settings"
TABLE_NOTIFICATIONS = "notifications"

# ════════════════════════════════════════════════
# NOTIFICATION TYPES
# ════════════════════════════════════════════════
NOTIF_SPRAY_WINDOW = "SPRAY_WINDOW"
NOTIF_RAIN_RISK    = "RAIN_RISK"
NOTIF_WIND_RISK    = "WIND_RISK"
NOTIF_MISSED_SPRAY = "MISSED_SPRAY"
NOTIF_REPORT_READY = "REPORT_READY"
# ════════════════════════════════════════════════
# ML MODEL & TRAINING DATA
# ════════════════════════════════════════════════
DEFAULT_RAIN_RISK_ALERT       = 1
DEFAULT_SPRAY_WINDOW_ALERT    = 1
DEFAULT_MISSED_SPRAY_ALERT    = 1
DEFAULT_PREFERRED_HOURS       = "6 AM - 9 AM"
DEFAULT_WEATHER_REFRESH_HOURS = 6
DEFAULT_LANGUAGE              = "English"
# ════════════════════════════════════════════════
# ML MODEL & TRAINING DATA
# ════════════════════════════════════════════════
MODEL_PATH          = os.path.join(DATA_DIR, "spray_model.pkl")
TRAINING_DATA_PATH  = os.path.join(DATA_DIR, "training_data.csv")
RANDOM_STATE        = 42
N_ESTIMATORS        = 100
TEST_SIZE           = 0.2
FEATURES            = [
    "temp_c",
    "humidity",
    "wind_kmh",
    "rain_prob",
    "days_since_spray",
    "stage_encoded",
    "min_interval",
]

# ════════════════════════════════════════════════
# WEATHER API — OpenWeatherMap
# ════════════════════════════════════════════════
WEATHER_API_KEY  = os.getenv("WEATHER_API_KEY", "b05ff0059e9255a437c7392494bfb9a1")
WEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"
FORECAST_HOURS   = 24    # Hours ahead to check rain probability

# ════════════════════════════════════════════════
# DEFAULT LOCATION — Srinagar, Kashmir
# ════════════════════════════════════════════════
DEFAULT_LAT      = 34.0837
DEFAULT_LON      = 74.7973
DEFAULT_LOCATION = "Srinagar, Kashmir"

# ════════════════════════════════════════════════
# SPRAY DECISION — SKUAST-K 2026 Thresholds
# ════════════════════════════════════════════════
RAIN_THRESHOLD    = 40   # % — delay if rain probability above this
WIND_THRESHOLD    = 20     # km/h — delay if wind above this
TEMP_MIN          = 5      # °C — skip if below this
TEMP_MAX          = 35     # °C — skip if above this
SPRAY_WINDOW_START = 6     # 6 AM
SPRAY_WINDOW_END   = 9     # 9 AM
SPRAY_WINDOW_TEXT  = "6 AM – 9 AM"

# ════════════════════════════════════════════════
# DECISION & RISK LABELS
# ════════════════════════════════════════════════
DECISION_SPRAY = "SPRAY"
DECISION_DELAY = "DELAY"
DECISION_SKIP  = "SKIP"

RISK_LOW    = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH   = "HIGH"

# ════════════════════════════════════════════════
# SPRAY LOG STATUS VALUES
# ════════════════════════════════════════════════
STATUS_DONE      = "DONE"
STATUS_POSTPONED = "POSTPONED"
STATUS_SKIPPED   = "SKIPPED"

# ════════════════════════════════════════════════
# DEFAULT SPRAY INTERVAL
# ════════════════════════════════════════════════
DEFAULT_MIN_INTERVAL = 14  # days

# ════════════════════════════════════════════════
# SKUAST-K 2026 — GROWTH STAGES (in order)
# ════════════════════════════════════════════════
GROWTH_STAGES = [
    "Delayed Dormancy",
    "Green Tip",
    "Tight Cluster",
    "Pink Bud",
    "Flowering",
    "Petal Fall",
    "Fruitlet",
    "Fruit Set",
    "Fruit Development-I",
    "Fruit Development-II",
    "Fruit Development-III",
    "Fruit Development-IV",
    "Pre-Harvest",
    "Harvest",
    "Post-Harvest",
    "Dormancy",
]

# ════════════════════════════════════════════════
# STAGE-SPECIFIC MINIMUM INTERVALS (days)
# Based on SKUAST-K 2026 guidelines
# ════════════════════════════════════════════════
STAGE_INTERVALS = {
    "Delayed Dormancy":     21,
    "Green Tip":            14,
    "Tight Cluster":        14,
    "Pink Bud":             14,
    "Flowering":            10,
    "Petal Fall":           14,
    "Fruitlet":             14,
    "Fruit Set":            14,
    "Fruit Development-I":  14,
    "Fruit Development-II": 14,
    "Fruit Development-III":14,
    "Fruit Development-IV": 14,
    "Pre-Harvest":          14,
    "Harvest":               0,
    "Post-Harvest":         21,
    "Dormancy":             21,
}

# ════════════════════════════════════════════════
# GEMINI AI — Chatbot 
# ════════════════════════════════════════════════
# GEMINI_API_KEY = "AIzaSyDEfuwG9sM3PJk11mIlucGZzlUuq9vqDXA"
# GEMINI_MODEL = "gemini-2.0-flash-lite"

GROQ_API_KEY = "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"
GROQ_MODEL   = "llama-3.1-8b-instant"