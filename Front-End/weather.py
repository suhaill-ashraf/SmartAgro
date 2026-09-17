"""
SmartAgro Backend — Weather Module
OpenWeatherMap API | Current weather + 5-day forecast
Spray safety flags | Next 24-hour rain probability
"""

import requests
from datetime import datetime
from typing import Optional

from config import (
    WEATHER_API_KEY,
    WEATHER_BASE_URL,
    DEFAULT_LAT,
    DEFAULT_LON,
    DEFAULT_LOCATION,
    RAIN_THRESHOLD,
    WIND_THRESHOLD,
    TEMP_MIN,
    TEMP_MAX,
    FORECAST_HOURS,
)



# ════════════════════════════════════════════════
# HELPER — ms to km/h conversion
# ════════════════════════════════════════════════
def _ms_to_kmh(ms: float) -> float:
    """Converts wind speed from m/s to km/h."""
    return round(ms * 3.6, 1)


# ════════════════════════════════════════════════
# FETCH CURRENT WEATHER
# ════════════════════════════════════════════════
def get_current_weather(
    lat: Optional[float] = None,
    lon: Optional[float] = None
) -> dict:
    """
    Fetches current weather from OpenWeatherMap.
    Returns clean dict with all fields Android needs.
    Returns {"error": "..."} on failure — never crashes.
    """
    lat = lat or DEFAULT_LAT
    lon = lon or DEFAULT_LON

    try:
        response = requests.get(
            f"{WEATHER_BASE_URL}/weather",
            params={
                "lat":   lat,
                "lon":   lon,
                "appid": WEATHER_API_KEY,
                "units": "metric",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        return {
            "city":        data.get("name", DEFAULT_LOCATION),
            "country":     data["sys"].get("country", "IN"),
            "temperature": round(data["main"]["temp"], 1),
            "feels_like":  round(data["main"]["feels_like"], 1),
            "temp_min":    round(data["main"]["temp_min"], 1),
            "temp_max":    round(data["main"]["temp_max"], 1),
            "humidity":    round(data["main"]["humidity"], 1),
            "pressure":    data["main"]["pressure"],
            "wind_speed":  _ms_to_kmh(data["wind"]["speed"]),
            "wind_deg":    data["wind"].get("deg", 0),
            "visibility":  round(data.get("visibility", 10000) / 1000, 1),  # m → km
            "description": data["weather"][0]["description"].title(),
            "icon":        data["weather"][0]["icon"],
            "icon_url":    f"https://openweathermap.org/img/wn/{data['weather'][0]['icon']}@2x.png",
            "sunrise":     datetime.fromtimestamp(data["sys"]["sunrise"]).strftime("%I:%M %p"),
            "sunset":      datetime.fromtimestamp(data["sys"]["sunset"]).strftime("%I:%M %p"),
            "timestamp":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    except requests.exceptions.Timeout:
        return {"error": "Weather API timeout. Please try again."}
    except requests.exceptions.ConnectionError:
        return {"error": "No internet connection."}
    except requests.exceptions.HTTPError as e:
        return {"error": f"Weather API error: {str(e)}"}
    except KeyError as e:
        return {"error": f"Unexpected API response format: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# ════════════════════════════════════════════════
# FETCH 5-DAY FORECAST
# ════════════════════════════════════════════════
def get_forecast(
    lat: Optional[float] = None,
    lon: Optional[float] = None
) -> list:
    """
    Fetches 5-day / 3-hour forecast from OpenWeatherMap.
    Returns list of 40 readings (5 days × 8 per day).
    Returns [] on failure — never crashes.
    """
    lat = lat or DEFAULT_LAT
    lon = lon or DEFAULT_LON

    try:
        response = requests.get(
            f"{WEATHER_BASE_URL}/forecast",
            params={
                "lat":   lat,
                "lon":   lon,
                "appid": WEATHER_API_KEY,
                "units": "metric",
                "cnt":   40,   # 5 days × 8 readings
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        forecast = []
        for item in data["list"]:
            dt = datetime.strptime(item["dt_txt"], "%Y-%m-%d %H:%M:%S")
            forecast.append({
                "datetime":    item["dt_txt"],
                "date":        dt.strftime("%d %b %Y"),
                "time":        dt.strftime("%I:%M %p"),
                "day":         dt.strftime("%A"),
                "short_day":   dt.strftime("%a").upper(),
                "temperature": round(item["main"]["temp"], 1),
                "feels_like":  round(item["main"]["feels_like"], 1),
                "humidity":    round(item["main"]["humidity"], 1),
                "wind_speed":  _ms_to_kmh(item["wind"]["speed"]),
                "rain_prob":   round(item.get("pop", 0) * 100, 0),
                "description": item["weather"][0]["description"].title(),
                "icon":        item["weather"][0]["icon"],
                "icon_url":    f"https://openweathermap.org/img/wn/{item['weather'][0]['icon']}@2x.png",
            })

        return forecast

    except Exception:
        return []


# ════════════════════════════════════════════════
# NEXT 24-HOUR RAIN PROBABILITY
# ════════════════════════════════════════════════
def get_next_rain_probability(
    lat: Optional[float] = None,
    lon: Optional[float] = None
) -> float:
    """
    Returns MAX rain probability in next 24 hours (0–100).
    Used by rules engine for Rule 1 (Rain Check).
    """
    forecast = get_forecast(lat=lat, lon=lon)
    if not forecast:
        return 0.0

    next_24h   = forecast[:8]   # 8 readings × 3 hours = 24 hours
    rain_probs = [f["rain_prob"] for f in next_24h]
    return float(max(rain_probs)) if rain_probs else 0.0


# ════════════════════════════════════════════════
# DAILY FORECAST SUMMARY (for Calendar screen)
# ════════════════════════════════════════════════
def get_daily_summary(
    lat: Optional[float] = None,
    lon: Optional[float] = None
) -> list:
    """
    Returns one summary per day for next 5 days.
    Used by the 5-day forecast row in Weather screen.
    """
    forecast = get_forecast(lat=lat, lon=lon)
    if not forecast:
        return []

    days = {}
    for item in forecast:
        date_key = item["datetime"][:10]   # "2026-05-12"
        if date_key not in days:
            days[date_key] = {
                "date":       item["date"],
                "day":        item["day"],
                "short_day":  item["short_day"],
                "temps":      [],
                "rain_probs": [],
                "icons":      [],
            }
        days[date_key]["temps"].append(item["temperature"])
        days[date_key]["rain_probs"].append(item["rain_prob"])
        days[date_key]["icons"].append(item["icon"])

    daily = []
    for date_key, d in days.items():
        # Most common icon for the day
        icon = max(set(d["icons"]), key=d["icons"].count)
        daily.append({
            "date":       d["date"],
            "day":        d["day"],
            "short_day":  d["short_day"],
            "temp_min":   min(d["temps"]),
            "temp_max":   max(d["temps"]),
            "rain_prob":  max(d["rain_probs"]),
            "icon":       icon,
            "icon_url":   f"https://openweathermap.org/img/wn/{icon}@2x.png",
        })

    return daily[:5]   # Return max 5 days


# ════════════════════════════════════════════════
# SPRAY SAFETY FLAGS
# ════════════════════════════════════════════════
def get_spray_safety(current: dict, rain_prob: float) -> dict:
    """
    Returns spray safety flags based on current weather.
    Called by /api/decision and /api/weather endpoints.
    """
    temp      = current.get("temperature", 20)
    wind      = current.get("wind_speed",  0)

    rain_safe = rain_prob  < RAIN_THRESHOLD
    wind_safe = wind       < WIND_THRESHOLD
    temp_safe = TEMP_MIN  <= temp <= TEMP_MAX
    all_clear = rain_safe and wind_safe and temp_safe

    # Determine risk level
    failed = sum([not rain_safe, not wind_safe, not temp_safe])
    if   failed == 0: risk = "LOW"
    elif failed == 1: risk = "MEDIUM"
    else:             risk = "HIGH"

    return {
        "rain_safe":  rain_safe,
        "wind_safe":  wind_safe,
        "temp_safe":  temp_safe,
        "all_clear":  all_clear,
        "risk_level": risk,
        "checks": {
            "rain":  f"{rain_prob}% (limit: {RAIN_THRESHOLD}%)",
            "wind":  f"{wind} km/h (limit: {WIND_THRESHOLD} km/h)",
            "temp":  f"{temp}°C (range: {TEMP_MIN}–{TEMP_MAX}°C)",
        },
    }

    # ════════════════════════════════════════════════
# GEOCODING — Convert a place name to coordinates
# ════════════════════════════════════════════════
def geocode_location(query: str, limit: int = 5) -> list:
    """
    Looks up a place name using OpenWeatherMap's Geocoding API.
    Returns a list of matches with name, state, country, lat, lon.
    Returns [] on failure — never crashes.
    """
    try:
        response = requests.get(
            "http://api.openweathermap.org/geo/1.0/direct",
            params={
                "q":     query,
                "limit": limit,
                "appid": WEATHER_API_KEY,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data:
            name    = item.get("name", "")
            state   = item.get("state", "")
            country = item.get("country", "")
            label   = ", ".join(p for p in [name, state, country] if p)
            results.append({
                "name":         name,
                "state":        state,
                "country":      country,
                "lat":          item.get("lat"),
                "lon":          item.get("lon"),
                "display_name": label,
            })
        return results

    except Exception:
        return []


# ════════════════════════════════════════════════
# FULL WEATHER CONTEXT — Used by /api/decision
# ════════════════════════════════════════════════
def get_spray_weather_context(
    lat: Optional[float] = None,
    lon: Optional[float] = None
) -> dict:
    """
    Returns complete weather context for spray decision.
    Single function called by /api/decision endpoint.
    Includes: current + forecast + rain probability + safety flags.
    """
    lat = lat or DEFAULT_LAT
    lon = lon or DEFAULT_LON

    # Fetch current weather
    current = get_current_weather(lat=lat, lon=lon)
    if "error" in current:
        return {"error": current["error"]}

    # Fetch forecast
    forecast      = get_forecast(lat=lat, lon=lon)
    daily_summary = get_daily_summary(lat=lat, lon=lon)
    rain_prob     = get_next_rain_probability(lat=lat, lon=lon)
    safety        = get_spray_safety(current, rain_prob)

    return {
        "current":       current,
        "forecast":      forecast[:8],       # Next 24 hours (3-hr intervals)
        "daily_summary": daily_summary,      # 5-day summary for forecast row
        "next_rain_prob": rain_prob,
        "location": {
            "lat":  lat,
            "lon":  lon,
            "city": current.get("city", DEFAULT_LOCATION),
        },
        "spray_safety":  safety,
    }
# ════════════════════════════════════════════════
# GET TOMORROW WEATHER — For next-day spray advice
# ════════════════════════════════════════════════
def get_tomorrow_weather(lat: float = None, lon: float = None) -> dict:
    from datetime import datetime, timedelta

    lat = lat or DEFAULT_LAT
    lon = lon or DEFAULT_LON

    forecast = get_forecast(lat=lat, lon=lon)
    if not forecast:
        return {"error": "Could not fetch forecast data."}

    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    preferred_hours = ["06:00:00", "09:00:00", "12:00:00"]
    best_slot = None

    for hour in preferred_hours:
        target = f"{tomorrow} {hour}"
        for slot in forecast:
            if slot["datetime"] == target:
                best_slot = slot
                break
        if best_slot:
            break

    if not best_slot:
        for slot in forecast:
            if slot["datetime"].startswith(tomorrow):
                best_slot = slot
                break

    if not best_slot:
        return {"error": f"No forecast available for tomorrow ({tomorrow})."}

    return {
        "temperature": best_slot["temperature"],
        "humidity": best_slot["humidity"],
        "wind_speed": best_slot["wind_speed"],
        "rain_prob": best_slot["rain_prob"],
        "description": best_slot["description"],
        "icon": best_slot["icon"],
        "icon_url": best_slot.get("icon_url", ""),
        "city": DEFAULT_LOCATION,
        "forecast_time": best_slot["datetime"],
        "is_forecast": True,
    }