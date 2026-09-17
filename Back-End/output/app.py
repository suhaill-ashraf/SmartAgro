"""
SmartAgro Backend — Main Flask Application
SKUAST-K 2026 | Kashmir Apple Orchards
17 Endpoints | Rules Engine + Random Forest | OpenWeatherMap + Gemini
"""

import csv
import io
import logging
from datetime import datetime, date as date_type
from flask import Flask, jsonify, request, make_response
from flask_cors import CORS

from config import (
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG,
    STAGE_INTERVALS,
    DEFAULT_MIN_INTERVAL,
    DECISION_SPRAY,
    DECISION_DELAY,
    DECISION_SKIP,
    GEMINI_API_KEY,
    GEMINI_MODEL,
)
from database import (
    init_db,
    save_orchard_profile,
    get_orchard_profile,
    save_spray_log,
    get_spray_history,
    get_last_spray_date,
    delete_spray_log,
    get_monthly_report,
    get_spray_by_stage,
    get_all_spray_stages,
    get_all_settings,
    get_setting,
    update_setting,
    save_notification,
    get_all_notifications,
    get_unread_notifications,
    mark_notification_read,
    mark_all_notifications_read,
    delete_notification,
    get_unread_count,
)
from weather import get_spray_weather_context, get_current_weather, get_forecast, get_daily_summary
from rules import (
    get_spray_recommendation,
    get_skuast_schedule,
    generate_spray_schedule,
    get_next_spray_date,
)
from train_model import predict, load_model


# ════════════════════════════════════════════════
# APP SETUP
# ════════════════════════════════════════════════
app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level   = logging.INFO,
    format  = "[%(asctime)s] %(levelname)s → %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════
def success(data: dict, code: int = 200):
    """Standard success response wrapper."""
    return jsonify({"status": "success", **data}), code


def error(message: str, code: int = 400):
    """Standard error response wrapper."""
    log.error("API Error %d: %s", code, message)
    return jsonify({"status": "error", "message": message}), code


def days_since(date_str: str) -> int:
    """Returns number of days since a given date string (YYYY-MM-DD)."""
    try:
        past  = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = date_type.today()
        return max(0, (today - past).days)
    except Exception:
        return 0


# ════════════════════════════════════════════════
# ENDPOINT 1 — HEALTH CHECK
# GET /api/health
# ════════════════════════════════════════════════
@app.route("/api/health", methods=["GET"])
def health():
    """Server health check."""
    return success({
        "message":   "SmartAgro API is running.",
        "version":   "4.0.0",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


# ════════════════════════════════════════════════
# ENDPOINT 2 — SAVE ORCHARD PROFILE
# POST /api/profile
# ════════════════════════════════════════════════
@app.route("/api/profile", methods=["POST"])
def post_profile():
    """Saves farmer's orchard profile."""
    data = request.get_json(silent=True)
    if not data:
        return error("Request body must be JSON.")
    try:
        save_orchard_profile(data)
        log.info("Profile saved for farmer: %s", data.get("farmer_name"))
        return success({"message": "Profile saved successfully."}, 201)
    except ValueError as e:
        return error(str(e), 400)
    except Exception as e:
        return error(f"Failed to save profile: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 3 — GET ORCHARD PROFILE
# GET /api/profile
# ════════════════════════════════════════════════
@app.route("/api/profile", methods=["GET"])
def get_profile():
    """Returns saved orchard profile."""
    try:
        profile = get_orchard_profile()
        if not profile:
            return error("No profile found. Please complete orchard setup.", 404)
        return success({"profile": profile})
    except Exception as e:
        return error(f"Failed to get profile: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 4 — SPRAY DECISION (Core Feature)
# GET /api/decision
# ════════════════════════════════════════════════
@app.route("/api/decision", methods=["GET"])
def get_decision():
    """
    Core endpoint — returns today's spray recommendation.
    Flow:
      1. Load orchard profile
      2. Fetch live weather
      3. Run 4 SKUAST-K rules
      4. If all 4 pass → call ML model
      5. Return final decision with full explanation
    """
    try:
        profile = get_orchard_profile()
        if not profile:
            return error("No orchard profile found. Please complete setup.", 404)

        growth_stage = profile.get("growth_stage",    "Fruit Set")
        last_spray   = profile.get("last_spray_date", "2026-01-01")
        min_interval = STAGE_INTERVALS.get(
            growth_stage, profile.get("min_interval_days", DEFAULT_MIN_INTERVAL)
        )
        lat = profile.get("lat")
        lon = profile.get("lon")

        weather_ctx = get_spray_weather_context(lat=lat, lon=lon)
        if "error" in weather_ctx:
            return error(f"Weather fetch failed: {weather_ctx['error']}", 503)

        current   = weather_ctx["current"]
        rain_prob = weather_ctx["next_rain_prob"]
        temp      = current["temperature"]
        wind      = current["wind_speed"]
        humidity  = current["humidity"]
        d_since   = days_since(last_spray)

        rules_result = get_spray_recommendation(
            rain_probability      = rain_prob,
            wind_speed            = wind,
            temp_c                = temp,
            days_since_last_spray = d_since,
            growth_stage          = growth_stage,
            min_interval          = min_interval,
        )

        ml_result = None
        if rules_result["all_passed"]:
            ml_result = predict(
                temp_c           = temp,
                humidity         = humidity,
                wind_kmh         = wind,
                rain_prob        = rain_prob,
                days_since_spray = d_since,
                growth_stage     = growth_stage,
                min_interval     = min_interval,
            )
            final_decision = ml_result.get("decision", DECISION_SPRAY)
            confidence     = ml_result.get("confidence", 100)
            reason         = (
                f"All 4 conditions passed. ML model recommends: {final_decision} "
                f"(confidence: {confidence}%)."
            )
        else:
            final_decision = rules_result["decision"]
            confidence     = 100
            reason         = rules_result["reason"]

        spray_info = get_spray_by_stage(growth_stage)
        next_spray = get_next_spray_date(last_spray, min_interval)

        log.info(
            "Decision → %s | Stage: %s | Rain: %s%% | Wind: %s km/h | Temp: %s°C",
            final_decision, growth_stage, rain_prob, wind, temp
        )

        return success({
            "decision":         final_decision,
            "confidence":       confidence,
            "reason":           reason,
            "risk_level":       rules_result["risk_level"],
            "rules":            rules_result["rules"],
            "all_rules_passed": rules_result["all_passed"],
            "ml":               ml_result,
            "weather": {
                "temperature":  temp,
                "humidity":     humidity,
                "wind_speed":   wind,
                "rain_prob":    rain_prob,
                "description":  current.get("description", ""),
                "icon_url":     current.get("icon_url", ""),
                "spray_safety": weather_ctx["spray_safety"],
            },
            "farm": {
                "growth_stage":     growth_stage,
                "last_spray_date":  last_spray,
                "days_since_spray": d_since,
                "min_interval":     min_interval,
                "next_spray":       next_spray,
            },
            "spray_info":    spray_info,
            "daily_summary": weather_ctx["daily_summary"],
        })

    except Exception as e:
        log.exception("Decision endpoint error")
        return error(f"Decision failed: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 5 — LIVE WEATHER
# GET /api/weather
# ════════════════════════════════════════════════
@app.route("/api/weather", methods=["GET"])
def get_weather():
    """Returns full live weather for Weather Center screen."""
    try:
        profile = get_orchard_profile()
        lat     = profile.get("lat") if profile else None
        lon     = profile.get("lon") if profile else None

        weather_ctx = get_spray_weather_context(lat=lat, lon=lon)
        if "error" in weather_ctx:
            return error(f"Weather fetch failed: {weather_ctx['error']}", 503)

        return success({
            "current":        weather_ctx["current"],
            "forecast":       weather_ctx["forecast"],
            "daily_summary":  weather_ctx["daily_summary"],
            "spray_safety":   weather_ctx["spray_safety"],
            "next_rain_prob": weather_ctx["next_rain_prob"],
            "location":       weather_ctx["location"],
        })
    except Exception as e:
        return error(f"Weather fetch failed: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 6 — SKUAST-K SCHEDULE
# GET /api/schedule
# ════════════════════════════════════════════════
@app.route("/api/schedule", methods=["GET"])
def get_schedule():
    """Returns full SKUAST-K 2026 phenological spray schedule."""
    try:
        year     = request.args.get("year", type=int)
        schedule = get_skuast_schedule(year=year)
        return success({
            "schedule": schedule,
            "total":    len(schedule),
            "year":     year or date_type.today().year,
        })
    except Exception as e:
        return error(f"Schedule fetch failed: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 7 — YEARLY CALENDAR
# GET /api/calendar
# ════════════════════════════════════════════════
@app.route("/api/calendar", methods=["GET"])
def get_calendar():
    """Returns interval-based spray calendar from farmer's last spray date."""
    try:
        profile = get_orchard_profile()
        if profile:
            last_spray   = profile.get("last_spray_date", "2026-01-01")
            growth_stage = profile.get("growth_stage", "Fruit Set")
            interval     = STAGE_INTERVALS.get(
                growth_stage,
                profile.get("min_interval_days", DEFAULT_MIN_INTERVAL)
            )
        else:
            last_spray = request.args.get(
                "last_spray_date",
                date_type.today().strftime("%Y-%m-%d")
            )
            interval = DEFAULT_MIN_INTERVAL

        calendar = generate_spray_schedule(
            start_date    = last_spray,
            interval_days = interval,
            total_sprays  = 20,
        )
        return success({
            "calendar":      calendar,
            "total":         len(calendar),
            "interval_days": interval,
            "start_date":    last_spray,
        })
    except Exception as e:
        return error(f"Calendar fetch failed: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 8 — LOG A SPRAY
# POST /api/log
# ════════════════════════════════════════════════
@app.route("/api/log", methods=["POST"])
def post_log():
    """Saves a spray log entry."""
    data = request.get_json(silent=True)
    if not data:
        return error("Request body must be JSON.")
    try:
        save_spray_log(data)
        log.info(
            "Spray logged → %s | %s | %s",
            data.get("date"), data.get("spray_name"), data.get("status")
        )
        return success({"message": "Spray log saved successfully."}, 201)
    except ValueError as e:
        return error(str(e), 400)
    except Exception as e:
        return error(f"Failed to save log: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 9 — SPRAY HISTORY
# GET /api/history
# ════════════════════════════════════════════════
@app.route("/api/history", methods=["GET"])
def get_history():
    """Returns all spray log entries ordered by date descending."""
    try:
        history = get_spray_history()
        return success({"history": history, "total": len(history)})
    except Exception as e:
        return error(f"Failed to get history: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 10 — DELETE SPRAY LOG
# DELETE /api/log/<id>
# ════════════════════════════════════════════════
@app.route("/api/log/<int:log_id>", methods=["DELETE"])
def delete_log(log_id: int):
    """Deletes a spray log entry by ID."""
    try:
        deleted = delete_spray_log(log_id)
        if not deleted:
            return error(f"Log entry {log_id} not found.", 404)
        log.info("Log entry deleted → ID: %d", log_id)
        return success({"message": f"Log entry {log_id} deleted."})
    except Exception as e:
        return error(f"Failed to delete log: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 11 — MONTHLY REPORT
# GET /api/report?year=2026&month=5
# ════════════════════════════════════════════════
@app.route("/api/report", methods=["GET"])
def get_report():
    """Returns monthly spray compliance report."""
    try:
        today = date_type.today()
        year  = request.args.get("year",  default=today.year,  type=int)
        month = request.args.get("month", default=today.month, type=int)

        if not (1 <= month <= 12):
            return error("Month must be between 1 and 12.", 400)
        if year < 2020 or year > 2100:
            return error("Year must be between 2020 and 2100.", 400)

        report = get_monthly_report(year, month)
        return success({"report": report})
    except Exception as e:
        return error(f"Failed to get report: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 12 — EXPORT REPORT AS CSV
# GET /api/report/export?year=2026&month=5
# ════════════════════════════════════════════════
@app.route("/api/report/export", methods=["GET"])
def export_report():
    """Exports monthly spray history as a downloadable CSV file."""
    try:
        today = date_type.today()
        year  = request.args.get("year",  default=today.year,  type=int)
        month = request.args.get("month", default=today.month, type=int)

        history = get_spray_history()
        prefix  = f"{year}-{str(month).zfill(2)}"
        rows    = [r for r in history if r.get("date", "").startswith(prefix)]

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "id", "date", "spray_name", "dosage", "growth_stage",
            "status", "notes", "temp_at_spray", "humidity_at_spray",
            "wind_at_spray", "created_at",
        ])
        writer.writeheader()
        writer.writerows(rows)

        response = make_response(output.getvalue())
        response.headers["Content-Type"]        = "text/csv"
        response.headers["Content-Disposition"] = (
            f"attachment; filename=smartagro_report_{prefix}.csv"
        )
        log.info("CSV export → %s | %d rows", prefix, len(rows))
        return response

    except Exception as e:
        return error(f"Export failed: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 13 — ALL SPRAY STAGES
# GET /api/spray-stages
# ════════════════════════════════════════════════
@app.route("/api/spray-stages", methods=["GET"])
def get_spray_stages():
    """Returns all 16 SKUAST-K spray stage entries."""
    try:
        stages = get_all_spray_stages()
        return success({"stages": stages, "total": len(stages)})
    except Exception as e:
        return error(f"Failed to get spray stages: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 14 — GET SETTINGS
# GET /api/settings
# ════════════════════════════════════════════════
@app.route("/api/settings", methods=["GET"])
def get_settings():
    """Returns all app settings as key-value pairs."""
    try:
        settings = get_all_settings()
        return success({"settings": settings})
    except Exception as e:
        return error(f"Failed to get settings: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 15 — SAVE SETTINGS
# POST /api/settings
# Body: { "rain_risk_alert": "1", "language": "Urdu", ... }
# ════════════════════════════════════════════════
@app.route("/api/settings", methods=["POST"])
def post_settings():
    """
    Updates one or more settings.
    Send only the keys you want to change.
    """
    data = request.get_json(silent=True)
    if not data:
        return error("Request body must be JSON.")
    try:
        for key, value in data.items():
            update_setting(key, str(value))
        log.info("Settings updated: %s", list(data.keys()))
        return success({"message": "Settings saved successfully."})
    except Exception as e:
        return error(f"Failed to save settings: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 16 — NOTIFICATIONS
# GET  /api/notifications          → all notifications
# GET  /api/notifications?unread=1 → unread only
# GET  /api/notifications/count    → unread badge count
# POST /api/notifications/read-all → mark all read
# POST /api/notifications/<id>/read → mark one read
# DELETE /api/notifications/<id>   → delete one
# ════════════════════════════════════════════════
@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    """Returns all or only unread notifications."""
    try:
        unread_only = request.args.get("unread", "0") == "1"
        notifications = (
            get_unread_notifications() if unread_only
            else get_all_notifications()
        )
        return success({
            "notifications": notifications,
            "total":         len(notifications),
        })
    except Exception as e:
        return error(f"Failed to get notifications: {str(e)}", 500)


@app.route("/api/notifications/count", methods=["GET"])
def notifications_count():
    """Returns unread notification count — used for Android badge."""
    try:
        count = get_unread_count()
        return success({"unread_count": count})
    except Exception as e:
        return error(f"Failed to get count: {str(e)}", 500)


@app.route("/api/notifications/read-all", methods=["POST"])
def read_all_notifications():
    """Marks all notifications as read."""
    try:
        mark_all_notifications_read()
        return success({"message": "All notifications marked as read."})
    except Exception as e:
        return error(f"Failed to mark notifications: {str(e)}", 500)


@app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
def read_notification(notif_id: int):
    """Marks a single notification as read."""
    try:
        updated = mark_notification_read(notif_id)
        if not updated:
            return error(f"Notification {notif_id} not found.", 404)
        return success({"message": f"Notification {notif_id} marked as read."})
    except Exception as e:
        return error(f"Failed to mark notification: {str(e)}", 500)


@app.route("/api/notifications/<int:notif_id>", methods=["DELETE"])
def remove_notification(notif_id: int):
    """Deletes a notification by ID."""
    try:
        deleted = delete_notification(notif_id)
        if not deleted:
            return error(f"Notification {notif_id} not found.", 404)
        log.info("Notification deleted → ID: %d", notif_id)
        return success({"message": f"Notification {notif_id} deleted."})
    except Exception as e:
        return error(f"Failed to delete notification: {str(e)}", 500)


# ════════════════════════════════════════════════
# ENDPOINT 17 — AI CHATBOT
# POST /api/chat
# Body: { "message": "Should I spray today?" }
# ════════════════════════════════════════════════
@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Gemini-powered farmer assistant chatbot.
    Answers questions about spray schedule, weather, growth stages.
    Injects live farm context (weather + profile) into the prompt.
    """
    data = request.get_json(silent=True)
    if not data or not data.get("message"):
        return error("Request body must include a 'message' field.")

    if not GEMINI_API_KEY:
        return error("Gemini API key not configured.", 503)

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)

        # Build context from live farm data
        profile     = get_orchard_profile()
        weather_ctx = {}
        try:
            lat = profile.get("lat") if profile else None
            lon = profile.get("lon") if profile else None
            weather_ctx = get_spray_weather_context(lat=lat, lon=lon)
        except Exception:
            pass

        current      = weather_ctx.get("current", {})
        growth_stage = profile.get("growth_stage", "Unknown") if profile else "Unknown"
        last_spray   = profile.get("last_spray_date", "Unknown") if profile else "Unknown"

        system_prompt = f"""You are SmartAgro Assistant, an expert agricultural advisor
for Kashmir apple orchards. You follow SKUAST-K 2026 spray guidelines.

Current farm context:
- Growth Stage: {growth_stage}
- Last Spray Date: {last_spray}
- Temperature: {current.get("temperature", "N/A")}°C
- Humidity: {current.get("humidity", "N/A")}%
- Wind Speed: {current.get("wind_speed", "N/A")} km/h
- Rain Probability: {weather_ctx.get("next_rain_prob", "N/A")}%

Answer in simple language a farmer can understand.
Keep answers short (3-5 sentences max).
Always mention safety cautions when relevant."""

        model    = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            f"{system_prompt}\n\nFarmer question: {data['message']}"
        )
        reply = response.text.strip()

        log.info("Chat → Q: %s | A: %s...", data["message"][:50], reply[:50])
        return success({"reply": reply, "model": GEMINI_MODEL})

    except Exception as e:
        log.exception("Chat endpoint error")
        return error(f"Chat failed: {str(e)}", 500)


# ════════════════════════════════════════════════
# STARTUP — Init DB + Load Model
# ════════════════════════════════════════════════
def startup() -> None:
    """Initialises DB and loads ML model before first request."""
    print("\n" + "═" * 55)
    print("  SMARTAGRO BACKEND — STARTING UP")
    print("═" * 55)

    init_db()

    try:
        bundle = load_model()
        print(
            f"  [ML] Model ready → "
            f"accuracy: {bundle['accuracy']}% | "
            f"trained: {bundle['trained_at']}"
        )
    except FileNotFoundError:
        print(
            "  [ML] WARNING: Model not found. "
            "Run generate_data.py then train_model.py."
        )

    print("═" * 55)
    print(f"  Server → http://{FLASK_HOST}:{FLASK_PORT}")
    print("═" * 55 + "\n")


# ════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════
if __name__ == "__main__":
    startup()
    app.run(
        host  = FLASK_HOST,
        port  = FLASK_PORT,
        debug = FLASK_DEBUG,
    )
