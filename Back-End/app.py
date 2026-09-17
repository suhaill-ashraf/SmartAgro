"""
SmartAgro Backend — Main Flask Application
SKUAST-K 2026 | Kashmir Apple Orchards
Multi-user (login + per-user data) | Rules Engine + Random Forest | OpenWeatherMap + Groq
"""

import csv
import io
import logging
from datetime import datetime, date as date_type

from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
from groq import Groq

from config import (
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG,
    STAGE_INTERVALS,
    DEFAULT_MIN_INTERVAL,
    DECISION_SPRAY,
    DECISION_DELAY,
    DECISION_SKIP,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_HIGH,
    SPRAY_WINDOW_TEXT,
    GROQ_API_KEY,
    GROQ_MODEL,
    NOTIF_SPRAY_WINDOW,
    NOTIF_RAIN_RISK,
    NOTIF_WIND_RISK,
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
    notification_exists_today,
    register_user,
    login_user,
    get_user_by_token,
    advance_growth_stage, 
    has_log_for_date
)

from weather import (
    get_spray_weather_context,
    get_current_weather,
    get_forecast,
    get_daily_summary,
    get_tomorrow_weather,
    geocode_location, 
)

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


def success(data: dict, code: int = 200):
    return jsonify({"status": "success", **data}), code


def error(message: str, code: int = 400):
    log.error("API Error %d: %s", code, message)
    return jsonify({"status": "error", "message": message}), code


def calc_days_since(last_spray_date_str: str) -> int:
    try:
        last = datetime.strptime(last_spray_date_str, "%Y-%m-%d").date()
        return max(0, (date_type.today() - last).days)
    except Exception:
        return 99


def current_user(req):
    """Reads the token from the Authorization header and returns the user dict, or None."""
    auth = req.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    return get_user_by_token(token)


def build_decision(rule_result: dict, ml_result: dict, spray_data: dict) -> dict:
    if rule_result["decision"] in [DECISION_DELAY, DECISION_SKIP]:
        final = rule_result["decision"]
        reason = rule_result["reason"]
        confidence = 100
        risk = RISK_HIGH if final == DECISION_DELAY else RISK_LOW
    else:
        final = ml_result["decision"]
        reason = (
            f"All 4 rules passed. ML model predicts {final} "
            f"with {ml_result['confidence']}% confidence."
        )
        confidence = ml_result["confidence"]
        risk = RISK_LOW if final == DECISION_SPRAY else RISK_MEDIUM

    return {
        "decision": final,
        "reason": reason,
        "confidence": confidence,
        "risk_level": risk,
        "spray_window": SPRAY_WINDOW_TEXT if final == DECISION_SPRAY else None,
        "tags": rule_result.get("tags", []),
        "rules": rule_result.get("rules", {}),
        "fungicide": {
            "growth_stage": spray_data.get("growth_stage", ""),
            "spray_name": spray_data.get("spray_name", ""),
            "spray_type": spray_data.get("spray_type", ""),
            "dosage": spray_data.get("dosage", ""),
            "best_window": spray_data.get("best_window", ""),
            "target": spray_data.get("target", ""),
            "caution": spray_data.get("caution", ""),
            "source": spray_data.get("source", "SKUAST-K 2026"),
        },
    }


def generate_tomorrow_notification(profile: dict, user_id: int) -> None:
    """
    Creates one notification today for tomorrow's spray outlook, for this user.
    Prevents duplicate daily notifications using app_settings.
    """
    try:
        setting_key = "tomorrow_spray_notification"

        if notification_exists_today(setting_key, user_id):
            return

        lat = profile.get("lat")
        lon = profile.get("lon")
        growth_stage = profile.get("growth_stage", "Fruit Set")
        min_interval = profile.get("min_interval_days", DEFAULT_MIN_INTERVAL)
        last_date = get_last_spray_date(user_id) or profile.get("last_spray_date")
        days_since_value = calc_days_since(last_date) if last_date else 99
        days_since_used = days_since_value + 1

        weather_data = get_tomorrow_weather(lat=lat, lon=lon)
        if "error" in weather_data:
            return

        temp = weather_data["temperature"]
        humidity = weather_data["humidity"]
        wind = weather_data["wind_speed"]
        rain_prob = weather_data["rain_prob"]
        forecast_time = weather_data.get("forecast_time", "")

        rule_result = get_spray_recommendation(
            rain_probability=rain_prob,
            wind_speed=wind,
            temp_c=temp,
            days_since_last_spray=days_since_used,
            growth_stage=growth_stage,
            min_interval=min_interval,
        )

        spray_data = get_spray_by_stage(growth_stage)
        spray_name = spray_data.get("spray_name", "Recommended spray")
        dosage = spray_data.get("dosage", "")
        best_window = spray_data.get("best_window", SPRAY_WINDOW_TEXT)
        decision = rule_result.get("decision")

        if rain_prob >= 40:
            save_notification(
                NOTIF_RAIN_RISK,
                "Rain Risk Tomorrow",
                f"Tomorrow rain probability is {rain_prob}%. Delay spray because wash-off risk is high.",
                user_id,
            )
        elif wind >= 20:
            save_notification(
                NOTIF_WIND_RISK,
                "High Wind Tomorrow",
                f"Tomorrow wind speed is {wind} km/h. Delay spray because drift risk is high.",
                user_id,
            )
        elif decision == DECISION_SPRAY:
            save_notification(
                NOTIF_SPRAY_WINDOW,
                "Spray Tomorrow",
                f"{spray_name} ({dosage}) is recommended tomorrow during {best_window}. Forecast time: {forecast_time}.",
                user_id,
            )
        else:
            save_notification(
                NOTIF_SPRAY_WINDOW,
                "Tomorrow Spray Update",
                f"Tomorrow status: {rule_result.get('reason', 'No spray recommended.')}",
                user_id,
            )

        update_setting(setting_key, datetime.now().strftime("%Y-%m-%d"), user_id)

    except Exception as e:
        log.exception("Tomorrow notification generation failed: %s", str(e))


# ════════════════════════════════════════════════
# ENDPOINT — HEALTH CHECK
# ════════════════════════════════════════════════
@app.route("/api/health", methods=["GET"])
def health():
    return success({
        "message":   "SmartAgro API is running.",
        "version":   "5.0.0",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


# ════════════════════════════════════════════════
# AUTH — REGISTER
# ════════════════════════════════════════════════
@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    if not data:
        return error("Request body must be JSON.")
    result = register_user(data.get("username"), data.get("password"))
    if "error" in result:
        return error(result["error"], 400)
    log.info("New user registered: %s", result["username"])
    return success({
        "message": "Account created.",
        "token": result["token"],
        "username": result["username"],
    }, 201)


# ════════════════════════════════════════════════
# AUTH — LOGIN
# ════════════════════════════════════════════════
@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not data:
        return error("Request body must be JSON.")
    result = login_user(data.get("username"), data.get("password"))
    if "error" in result:
        return error(result["error"], 401)
    log.info("User logged in: %s", result["username"])
    return success({
        "message": "Logged in.",
        "token": result["token"],
        "username": result["username"],
    })


# ════════════════════════════════════════════════
# PROFILE
# ════════════════════════════════════════════════
@app.route("/api/profile", methods=["POST"])
def post_profile():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    data = request.get_json(silent=True)
    if not data:
        return error("Request body must be JSON.")
    try:
        save_orchard_profile(data, user["id"])
        log.info("Profile saved for farmer: %s", data.get("farmer_name"))
        return success({"message": "Profile saved successfully."}, 201)
    except ValueError as e:
        return error(str(e), 400)
    except Exception as e:
        return error(f"Failed to save profile: {str(e)}", 500)


@app.route("/api/profile", methods=["GET"])
def get_profile():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        profile = get_orchard_profile(user["id"])
        if not profile:
            return error("No profile found. Please complete orchard setup.", 404)
        return success({"profile": profile})
    except Exception as e:
        return error(f"Failed to get profile: {str(e)}", 500)


# ════════════════════════════════════════════════
# SPRAY DECISION
# ════════════════════════════════════════════════
@app.route("/api/decision", methods=["GET"])
def decision():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        profile = get_orchard_profile(user["id"])
        if not profile:
            return error("Orchard profile not set. Please complete setup.", 400)

        try:
            generate_tomorrow_notification(profile, user["id"])
        except Exception:
            pass

        growth_stage = profile.get("growth_stage", "Fruit Set")
        min_interval = profile.get("min_interval_days", DEFAULT_MIN_INTERVAL)
        last_date = get_last_spray_date(user["id"]) or profile.get("last_spray_date")
        days_since_value = calc_days_since(last_date) if last_date else 99
        lat = profile.get("lat")
        lon = profile.get("lon")
       # ── GATE CHECK: is today the scheduled spray day, not yet acted on? ──
        from datetime import timedelta
        today_str = date_type.today().strftime("%Y-%m-%d")
        interval = STAGE_INTERVALS.get(growth_stage, min_interval)
        next_spray_str = None
        if last_date:
            try:
                last_dt = datetime.strptime(last_date[:10], "%Y-%m-%d").date()   # [:10] guards against stray time text
                next_spray_str = (last_dt + timedelta(days=interval)).strftime("%Y-%m-%d")
            except Exception:
                next_spray_str = None

        is_spray_day = (next_spray_str is not None) and (today_str >= next_spray_str)
        already_acted = has_log_for_date(user["id"], today_str)
        gated = is_spray_day and not already_acted

        mode = request.args.get("mode", "today").strip().lower()
        # When it's the actual spray day and not yet acted on, lock to TODAY.
        if gated:
            mode = "today"
        if mode not in ["today", "tomorrow"]:
            return error("Invalid mode. Use ?mode=today or ?mode=tomorrow", 400)

        if mode == "tomorrow":
            weather_data = get_tomorrow_weather(lat=lat, lon=lon)
            if "error" in weather_data:
                return error(weather_data["error"], 503)

            temp = weather_data["temperature"]
            humidity = weather_data["humidity"]
            wind = weather_data["wind_speed"]
            rain_prob = weather_data["rain_prob"]
            days_since_used = days_since_value + 1
            weather_label = "Tomorrow Forecast"
            forecast_time = weather_data.get("forecast_time", "")
            weather_response = weather_data
        else:
            context = get_spray_weather_context(lat=lat, lon=lon)
            if "error" in context:
                return error(context["error"], 503)

            current = context["current"]
            temp = current["temperature"]
            humidity = current["humidity"]
            wind = current["wind_speed"]
            rain_prob = context["next_rain_prob"]
            days_since_used = days_since_value
            weather_label = "Today Live Weather"
            forecast_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            weather_response = current

        rule_result = get_spray_recommendation(
            rain_probability=rain_prob,
            wind_speed=wind,
            temp_c=temp,
            days_since_last_spray=days_since_used,
            growth_stage=growth_stage,
            min_interval=min_interval,
        )

        ml_result = predict(
            temp_c=temp,
            humidity=humidity,
            wind_kmh=wind,
            rain_prob=rain_prob,
            days_since_spray=days_since_used,
            growth_stage=growth_stage,
            min_interval=min_interval,
        )

        spray_data = get_spray_by_stage(growth_stage)
        result = build_decision(rule_result, ml_result, spray_data)

        if mode == "tomorrow":
            result["reason"] = f"[Tomorrow: {forecast_time}] {result['reason']}"

        return success({
            "mode": mode,
            "weather_source": weather_label,
            "forecast_time": forecast_time,
            "decision": result,
            "gated": gated,
            "logged_today": already_acted,
            "next_spray_date": next_spray_str,
            "weather": {
                "temperature": temp,
                "humidity": humidity,
                "wind_speed": wind,
                "rain_prob": rain_prob,
                "description": weather_response.get("description", ""),
                "icon": weather_response.get("icon", ""),
                "icon_url": weather_response.get("icon_url", ""),
            },
            "profile": {
                "farmer_name": profile.get("farmer_name"),
                "location": profile.get("location"),
                "growth_stage": growth_stage,
                "days_since_spray": days_since_value,
                "days_since_used_for_decision": days_since_used,
                "min_interval": min_interval,
            },
        })

    except Exception as e:
        log.exception("Decision route failed")
        return error(f"Decision failed: {str(e)}", 500)


# ════════════════════════════════════════════════
# LIVE WEATHER
# ════════════════════════════════════════════════
@app.route("/api/weather", methods=["GET"])
def get_weather():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        profile = get_orchard_profile(user["id"])
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
# SKUAST-K SCHEDULE (public reference data)
# ════════════════════════════════════════════════
@app.route("/api/schedule", methods=["GET"])
def get_schedule():
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
# YEARLY CALENDAR
# ════════════════════════════════════════════════
@app.route("/api/calendar", methods=["GET"])
def get_calendar():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        profile = get_orchard_profile(user["id"])
        if profile:
            last_spray   = profile.get("last_spray_date", "2026-01-01")
            growth_stage = profile.get("growth_stage", "Fruit Set")
            interval     = STAGE_INTERVALS.get(
                growth_stage,
                profile.get("min_interval_days", DEFAULT_MIN_INTERVAL)
            )
        else:
            last_spray = request.args.get("last_spray_date", date_type.today().strftime("%Y-%m-%d"))
            interval   = DEFAULT_MIN_INTERVAL

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
# LOG A SPRAY
# ════════════════════════════════════════════════


@app.route("/api/log", methods=["POST"])
def post_log():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    data = request.get_json(silent=True)
    if not data:
        return error("Request body must be JSON.")
    try:
        save_spray_log(data, user["id"])

        # Done OR Skip → advance to the next stage (move forward, no trap).
        # Delay (POSTPONED) → do NOT advance, so the gate re-asks tomorrow.
        new_stage = None
        if data.get("status") in ("DONE", "SKIPPED"):
            new_stage = advance_growth_stage(user["id"])

        log.info("Spray logged → %s | %s | %s",
                 data.get("date"), data.get("spray_name"), data.get("status"))
        return success({
            "message": "Spray log saved successfully.",
            "new_growth_stage": new_stage,
        }, 201)
    except ValueError as e:
        return error(str(e), 400)
    except Exception as e:
        return error(f"Failed to save log: {str(e)}", 500)


# ════════════════════════════════════════════════
# SPRAY HISTORY
# ════════════════════════════════════════════════
@app.route("/api/history", methods=["GET"])
def get_history():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        history = get_spray_history(user["id"])
        return success({"history": history, "total": len(history)})
    except Exception as e:
        return error(f"Failed to get history: {str(e)}", 500)


# ════════════════════════════════════════════════
# DELETE SPRAY LOG
# ════════════════════════════════════════════════
@app.route("/api/log/<int:log_id>", methods=["DELETE"])
def delete_log(log_id: int):
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        deleted = delete_spray_log(log_id, user["id"])
        if not deleted:
            return error(f"Log entry {log_id} not found.", 404)
        log.info("Log entry deleted → ID: %d", log_id)
        return success({"message": f"Log entry {log_id} deleted."})
    except Exception as e:
        return error(f"Failed to delete log: {str(e)}", 500)


# ════════════════════════════════════════════════
# MONTHLY REPORT
# ════════════════════════════════════════════════
@app.route("/api/report", methods=["GET"])
def get_report():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        today = date_type.today()
        year  = request.args.get("year",  default=today.year,  type=int)
        month = request.args.get("month", default=today.month, type=int)
        if not (1 <= month <= 12):
            return error("Month must be between 1 and 12.", 400)
        if year < 2020 or year > 2100:
            return error("Year must be between 2020 and 2100.", 400)
        report = get_monthly_report(year, month, user["id"])
        return success({"report": report})
    except Exception as e:
        return error(f"Failed to get report: {str(e)}", 500)


# ════════════════════════════════════════════════
# EXPORT REPORT AS CSV
# Token passed as ?token=... because browsers can't set headers on a link.
# ════════════════════════════════════════════════
@app.route("/api/report/export", methods=["GET"])
def export_report():
    token = request.args.get("token", "")
    user = get_user_by_token(token)
    if not user:
        return error("Not logged in.", 401)
    try:
        today  = date_type.today()
        year   = request.args.get("year",  default=today.year,  type=int)
        month  = request.args.get("month", default=today.month, type=int)
        prefix = f"{year}-{str(month).zfill(2)}"

        history = get_spray_history(user["id"])
        rows    = [r for r in history if r.get("date", "").startswith(prefix)]

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "id", "user_id", "date", "spray_name", "dosage", "growth_stage",
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
        return response
    except Exception as e:
        return error(f"Export failed: {str(e)}", 500)


# ════════════════════════════════════════════════
# ALL SPRAY STAGES (public reference data)
# ════════════════════════════════════════════════
@app.route("/api/spray-stages", methods=["GET"])
def get_spray_stages():
    try:
        stages = get_all_spray_stages()
        return success({"stages": stages, "total": len(stages)})
    except Exception as e:
        return error(f"Failed to get spray stages: {str(e)}", 500)


# ════════════════════════════════════════════════
# SETTINGS
# ════════════════════════════════════════════════
@app.route("/api/settings", methods=["GET"])
def get_settings():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        settings = get_all_settings(user["id"])
        return success({"settings": settings})
    except Exception as e:
        return error(f"Failed to get settings: {str(e)}", 500)


@app.route("/api/settings", methods=["POST"])
def post_settings():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    data = request.get_json(silent=True)
    if not data:
        return error("Request body must be JSON.")
    try:
        for key, value in data.items():
            update_setting(key, str(value), user["id"])
        log.info("Settings updated: %s", list(data.keys()))
        return success({"message": "Settings saved successfully."})
    except Exception as e:
        return error(f"Failed to save settings: {str(e)}", 500)

# ════════════════════════════════════════════════
# GEOCODE — Search for a place name → lat/lon
# GET /api/geocode?query=Sopore
# ════════════════════════════════════════════════
@app.route("/api/geocode", methods=["GET"])
def geocode():
    query = request.args.get("query", "").strip()
    if not query:
        return error("Query parameter 'query' is required.", 400)
    try:
        results = geocode_location(query)
        return success({"results": results, "total": len(results)})
    except Exception as e:
        return error(f"Geocode search failed: {str(e)}", 500)
# ════════════════════════════════════════════════
# NOTIFICATIONS
# ════════════════════════════════════════════════
@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        unread_only = request.args.get("unread", "0") == "1"
        notifications = get_unread_notifications(user["id"]) if unread_only else get_all_notifications(user["id"])
        return success({"notifications": notifications, "total": len(notifications)})
    except Exception as e:
        return error(f"Failed to get notifications: {str(e)}", 500)


@app.route("/api/notifications/count", methods=["GET"])
def notifications_count():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        count = get_unread_count(user["id"])
        return success({"unread_count": count})
    except Exception as e:
        return error(f"Failed to get count: {str(e)}", 500)


@app.route("/api/notifications/read-all", methods=["POST"])
def read_all_notifications():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        mark_all_notifications_read(user["id"])
        return success({"message": "All notifications marked as read."})
    except Exception as e:
        return error(f"Failed to mark notifications: {str(e)}", 500)


@app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
def read_notification(notif_id: int):
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        updated = mark_notification_read(notif_id, user["id"])
        if not updated:
            return error(f"Notification {notif_id} not found.", 404)
        return success({"message": f"Notification {notif_id} marked as read."})
    except Exception as e:
        return error(f"Failed to mark notification: {str(e)}", 500)


@app.route("/api/notifications/<int:notif_id>", methods=["DELETE"])
def remove_notification(notif_id: int):
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        deleted = delete_notification(notif_id, user["id"])
        if not deleted:
            return error(f"Notification {notif_id} not found.", 404)
        return success({"message": f"Notification {notif_id} deleted."})
    except Exception as e:
        return error(f"Failed to delete notification: {str(e)}", 500)


@app.route("/api/notifications/generate", methods=["POST", "GET"])
def generate_notifications_now():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    try:
        profile = get_orchard_profile(user["id"])
        if not profile:
            return error("Orchard profile not set. Please complete setup.", 400)
        generate_tomorrow_notification(profile, user["id"])
        return success({"message": "Tomorrow notification generation checked."})
    except Exception as e:
        return error(f"Failed to generate notification: {str(e)}", 500)


# ════════════════════════════════════════════════
# AI CHATBOT (Groq)
# ════════════════════════════════════════════════
@app.route("/api/chat", methods=["POST"])
def chat():
    user = current_user(request)
    if not user:
        return error("Not logged in.", 401)
    data = request.get_json(silent=True)
    if not data or not data.get("message"):
        return error("Request body must include a 'message' field.")
    if not GROQ_API_KEY:
        return error("Groq API key not configured.", 503)
    try:
        from groq import Groq

        profile     = get_orchard_profile(user["id"])
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

        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model    = GROQ_MODEL,
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": data["message"]},
            ],
            max_tokens = 300,
        )
        reply = response.choices[0].message.content.strip()
        log.info("Chat → Q: %s", data["message"][:60])
        return success({"reply": reply, "model": GROQ_MODEL})

    except Exception as e:
        log.exception("Chat endpoint error")
        return error(f"Chat failed: {str(e)}", 500)


# ════════════════════════════════════════════════
# STARTUP
# ════════════════════════════════════════════════
def startup() -> None:
    print("\n" + "═" * 55)
    print(" SMARTAGRO BACKEND — STARTING UP")
    print("═" * 55)
    init_db()
    try:
        bundle = load_model()
        print(f" [ML] Model ready → accuracy: {bundle['accuracy']}% | trained: {bundle['trained_at']}")
    except FileNotFoundError:
        print(" [ML] WARNING: Model not found. Run generate_data.py then train_model.py.")

    print("═" * 55)
    print(f" Server → http://{FLASK_HOST}:{FLASK_PORT}")
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