"""
Weather and Air Quality API module.
Fetches real-time conditions, forecasts, and air pollution metrics for any given location
using Open-Meteo's Weather, Air Quality, and Geocoding APIs (no API key required).
"""

import os
import sys
import json
import argparse
import datetime
from typing import Dict, Any, Optional, Union, Tuple
import requests

# Ensure UTF-8 output when possible on Windows console
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNIFIED_CREDENTIALS_FILE = os.path.join(BASE_DIR, "api_credentials.json")

GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# WMO Weather interpretation codes (WW)
WMO_WEATHER_CODES: Dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Drizzle: Light",
    53: "Drizzle: Moderate",
    55: "Drizzle: Dense intensity",
    56: "Freezing Drizzle: Light",
    57: "Freezing Drizzle: Dense intensity",
    61: "Rain: Slight",
    63: "Rain: Moderate",
    65: "Rain: Heavy intensity",
    66: "Freezing Rain: Light",
    67: "Freezing Rain: Heavy intensity",
    71: "Snow fall: Slight",
    73: "Snow fall: Moderate",
    75: "Snow fall: Heavy intensity",
    77: "Snow grains",
    80: "Rain showers: Slight",
    81: "Rain showers: Moderate",
    82: "Rain showers: Violent",
    85: "Snow showers: Slight",
    86: "Snow showers: Heavy",
    95: "Thunderstorm: Slight or moderate",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def interpret_weather_code(code: Optional[int]) -> str:
    """Returns human-readable text for a WMO weather code."""
    if code is None:
        return "Unknown"
    return WMO_WEATHER_CODES.get(code, f"Weather code {code}")


def interpret_european_aqi(aqi: Optional[Union[int, float]]) -> str:
    """Categorizes European Air Quality Index (0 - 100+)."""
    if aqi is None:
        return "Unknown"
    if aqi <= 20:
        return "Good"
    elif aqi <= 40:
        return "Fair"
    elif aqi <= 60:
        return "Moderate"
    elif aqi <= 80:
        return "Poor"
    elif aqi <= 100:
        return "Very Poor"
    else:
        return "Extremely Poor"


def interpret_us_aqi(aqi: Optional[Union[int, float]]) -> str:
    """Categorizes US EPA Air Quality Index (0 - 500)."""
    if aqi is None:
        return "Unknown"
    if aqi <= 50:
        return "Good"
    elif aqi <= 100:
        return "Moderate"
    elif aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    elif aqi <= 200:
        return "Unhealthy"
    elif aqi <= 300:
        return "Very Unhealthy"
    else:
        return "Hazardous"


def get_default_location(credentials_path: Optional[str] = None) -> Optional[str]:
    """Retrieves default location from credentials file or environment variable."""
    env_loc = os.environ.get("WEATHER_LOCATION") or os.environ.get("DEFAULT_LOCATION")
    if env_loc:
        return env_loc.strip()

    cred_file = credentials_path or UNIFIED_CREDENTIALS_FILE
    if os.path.exists(cred_file):
        try:
            with open(cred_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                loc = cfg.get("weather", {}).get("default_location")
                if loc and isinstance(loc, str) and loc.strip():
                    return loc.strip()
        except Exception:
            pass

    return None


def geocode_location(
    location_name: str,
    language: str = "en",
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    Looks up geographic coordinates for a given city or place name.
    
    :param location_name: City or address name (e.g. "Krakow", "Warsaw", "London").
    :param language: Language code for results.
    :param timeout: Network request timeout in seconds.
    :return: Dictionary containing coordinates and location metadata.
    """
    cleaned_name = location_name.strip()
    if not cleaned_name:
        raise ValueError("Location name cannot be empty.")

    params = {
        "name": cleaned_name,
        "count": 5,
        "language": language,
        "format": "json",
    }
    resp = requests.get(GEOCODING_API_URL, params=params, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"Geocoding API error ({resp.status_code}): {resp.text}")

    data = resp.json()
    results = data.get("results")
    if not results or len(results) == 0:
        raise ValueError(f"Location '{location_name}' could not be found.")

    first = results[0]
    return {
        "name": first.get("name"),
        "latitude": first.get("latitude"),
        "longitude": first.get("longitude"),
        "country": first.get("country"),
        "country_code": first.get("country_code"),
        "admin1": first.get("admin1"),
        "timezone": first.get("timezone"),
        "elevation": first.get("elevation"),
        "all_matches": results,
    }


def fetch_weather(
    latitude: float,
    longitude: float,
    timezone: str = "auto",
    forecast_days: int = 7,
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    Fetches weather forecast and current weather conditions.
    
    :param latitude: Latitude coordinate.
    :param longitude: Longitude coordinate.
    :param timezone: Timezone string or 'auto'.
    :param forecast_days: Number of forecast days (1-16).
    :param timeout: Request timeout in seconds.
    :return: Formatted weather dictionary.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "forecast_days": forecast_days,
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,"
            "precipitation,rain,showers,snowfall,weather_code,cloud_cover,"
            "wind_speed_10m,wind_direction_10m,wind_gusts_10m"
        ),
        "hourly": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "precipitation_probability,precipitation,weather_code,wind_speed_10m"
        ),
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,"
            "apparent_temperature_max,apparent_temperature_min,sunrise,sunset,"
            "precipitation_sum,precipitation_probability_max,wind_speed_10m_max"
        ),
    }

    resp = requests.get(WEATHER_API_URL, params=params, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"Weather API error ({resp.status_code}): {resp.text}")

    raw = resp.json()
    current_raw = raw.get("current", {})
    daily_raw = raw.get("daily", {})
    hourly_raw = raw.get("hourly", {})
    units = raw.get("current_units", {})

    w_code = current_raw.get("weather_code")
    current_weather = {
        "time": current_raw.get("time"),
        "temperature": current_raw.get("temperature_2m"),
        "apparent_temperature": current_raw.get("apparent_temperature"),
        "relative_humidity": current_raw.get("relative_humidity_2m"),
        "weather_code": w_code,
        "weather_description": interpret_weather_code(w_code),
        "precipitation": current_raw.get("precipitation"),
        "rain": current_raw.get("rain"),
        "snowfall": current_raw.get("snowfall"),
        "cloud_cover": current_raw.get("cloud_cover"),
        "wind_speed": current_raw.get("wind_speed_10m"),
        "wind_direction": current_raw.get("wind_direction_10m"),
        "wind_gusts": current_raw.get("wind_gusts_10m"),
        "is_day": bool(current_raw.get("is_day", 1)),
        "units": units,
    }

    # Format daily forecast
    daily_forecasts = []
    dates = daily_raw.get("time", [])
    for idx, date_str in enumerate(dates):
        day_code = daily_raw.get("weather_code", [])[idx] if idx < len(daily_raw.get("weather_code", [])) else None
        daily_forecasts.append({
            "date": date_str,
            "weather_code": day_code,
            "weather_description": interpret_weather_code(day_code),
            "temperature_max": daily_raw.get("temperature_2m_max", [])[idx] if idx < len(daily_raw.get("temperature_2m_max", [])) else None,
            "temperature_min": daily_raw.get("temperature_2m_min", [])[idx] if idx < len(daily_raw.get("temperature_2m_min", [])) else None,
            "apparent_temperature_max": daily_raw.get("apparent_temperature_max", [])[idx] if idx < len(daily_raw.get("apparent_temperature_max", [])) else None,
            "apparent_temperature_min": daily_raw.get("apparent_temperature_min", [])[idx] if idx < len(daily_raw.get("apparent_temperature_min", [])) else None,
            "precipitation_sum": daily_raw.get("precipitation_sum", [])[idx] if idx < len(daily_raw.get("precipitation_sum", [])) else None,
            "precipitation_probability_max": daily_raw.get("precipitation_probability_max", [])[idx] if idx < len(daily_raw.get("precipitation_probability_max", [])) else None,
            "wind_speed_max": daily_raw.get("wind_speed_10m_max", [])[idx] if idx < len(daily_raw.get("wind_speed_10m_max", [])) else None,
            "sunrise": daily_raw.get("sunrise", [])[idx] if idx < len(daily_raw.get("sunrise", [])) else None,
            "sunset": daily_raw.get("sunset", [])[idx] if idx < len(daily_raw.get("sunset", [])) else None,
        })

    return {
        "current": current_weather,
        "daily": daily_forecasts,
        "hourly": hourly_raw,
        "raw": raw,
    }


def fetch_air_quality(
    latitude: float,
    longitude: float,
    timezone: str = "auto",
    forecast_days: int = 5,
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    Fetches air quality data and air pollution forecast.
    
    :param latitude: Latitude coordinate.
    :param longitude: Longitude coordinate.
    :param timezone: Timezone string or 'auto'.
    :param forecast_days: Number of forecast days (1-7).
    :param timeout: Request timeout in seconds.
    :return: Formatted air quality dictionary.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "forecast_days": forecast_days,
        "current": (
            "european_aqi,us_aqi,pm10,pm2_5,carbon_monoxide,"
            "nitrogen_dioxide,sulphur_dioxide,ozone"
        ),
        "hourly": (
            "european_aqi,us_aqi,pm10,pm2_5,carbon_monoxide,"
            "nitrogen_dioxide,sulphur_dioxide,ozone"
        ),
    }

    resp = requests.get(AIR_QUALITY_API_URL, params=params, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"Air Quality API error ({resp.status_code}): {resp.text}")

    raw = resp.json()
    current_raw = raw.get("current", {})
    hourly_raw = raw.get("hourly", {})
    units = raw.get("current_units", {})

    eu_aqi = current_raw.get("european_aqi")
    us_aqi = current_raw.get("us_aqi")

    current_aq = {
        "time": current_raw.get("time"),
        "european_aqi": eu_aqi,
        "european_aqi_level": interpret_european_aqi(eu_aqi),
        "us_aqi": us_aqi,
        "us_aqi_level": interpret_us_aqi(us_aqi),
        "pm2_5": current_raw.get("pm2_5"),
        "pm10": current_raw.get("pm10"),
        "nitrogen_dioxide": current_raw.get("nitrogen_dioxide"),
        "ozone": current_raw.get("ozone"),
        "carbon_monoxide": current_raw.get("carbon_monoxide"),
        "sulphur_dioxide": current_raw.get("sulphur_dioxide"),
        "units": units,
    }

    return {
        "current": current_aq,
        "hourly": hourly_raw,
        "raw": raw,
    }


def download_weather_and_air_quality(
    location: Optional[Union[str, Tuple[float, float], Dict[str, Any]]] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timezone: str = "auto",
    forecast_days: int = 7,
    credentials_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Downloads both weather forecast and air quality data for a specified location.

    :param location: City name (e.g. "Krakow"), (lat, lon) tuple, or dictionary with coordinates.
    :param latitude: Optional explicit latitude.
    :param longitude: Optional explicit longitude.
    :param timezone: Timezone string or 'auto'.
    :param forecast_days: Number of forecast days.
    :param credentials_path: Optional path to credentials file to look up default location.
    :return: Complete dictionary containing location, weather, and air quality information.
    """
    loc_meta: Dict[str, Any] = {}

    # Coordinate determination
    if latitude is not None and longitude is not None:
        lat = float(latitude)
        lon = float(longitude)
        loc_meta = {
            "name": f"Coordinates ({lat:.4f}, {lon:.4f})",
            "latitude": lat,
            "longitude": lon,
            "timezone": timezone,
        }
    elif isinstance(location, (tuple, list)) and len(location) >= 2:
        lat = float(location[0])
        lon = float(location[1])
        loc_meta = {
            "name": f"Coordinates ({lat:.4f}, {lon:.4f})",
            "latitude": lat,
            "longitude": lon,
            "timezone": timezone,
        }
    elif isinstance(location, dict) and ("latitude" in location or "lat" in location):
        lat = float(location.get("latitude", location.get("lat")))
        lon = float(location.get("longitude", location.get("lon")))
        loc_meta = {
            "name": location.get("name", f"Coordinates ({lat:.4f}, {lon:.4f})"),
            "latitude": lat,
            "longitude": lon,
            "country": location.get("country"),
            "timezone": location.get("timezone", timezone),
        }
    else:
        # String location lookup
        loc_str = location if isinstance(location, str) and location.strip() else None
        if not loc_str:
            loc_str = get_default_location(credentials_path)

        if not loc_str:
            raise ValueError(
                "No location provided. Please specify a location name, coordinates, "
                "or configure 'weather.default_location' in api_credentials.json."
            )

        loc_meta = geocode_location(loc_str)
        lat = loc_meta["latitude"]
        lon = loc_meta["longitude"]

    # Fetch weather and air quality
    weather_data = fetch_weather(
        latitude=lat,
        longitude=lon,
        timezone=timezone,
        forecast_days=forecast_days,
    )
    aq_data = fetch_air_quality(
        latitude=lat,
        longitude=lon,
        timezone=timezone,
        forecast_days=min(forecast_days, 7),
    )

    return {
        "location": loc_meta,
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "weather": weather_data,
        "air_quality": aq_data,
    }


def save_to_file(data: Dict[str, Any], filepath: str) -> None:
    """Saves fetched data to a JSON file."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def format_summary_text(data: Dict[str, Any]) -> str:
    """Formats weather and air quality data into a clean, human-readable text summary."""
    loc = data.get("location", {})
    loc_name = loc.get("name", "Unknown")
    country = loc.get("country", "")
    admin1 = loc.get("admin1", "")
    full_loc = ", ".join(filter(bool, [loc_name, admin1, country]))

    w_curr = data.get("weather", {}).get("current", {})
    aq_curr = data.get("air_quality", {}).get("current", {})
    daily = data.get("weather", {}).get("daily", [])

    lines = [
        "=" * 60,
        f"  LOCATION: {full_loc} (Lat: {loc.get('latitude')}, Lon: {loc.get('longitude')})",
        "=" * 60,
        "",
        "CURRENT WEATHER:",
        f"  - Condition:           {w_curr.get('weather_description')}",
        f"  - Temperature:         {w_curr.get('temperature')} C (Feels like: {w_curr.get('apparent_temperature')} C)",
        f"  - Relative Humidity:   {w_curr.get('relative_humidity')} %",
        f"  - Precipitation:       {w_curr.get('precipitation')} mm",
        f"  - Wind Speed:          {w_curr.get('wind_speed')} km/h (Gusts: {w_curr.get('wind_gusts')} km/h)",
        "",
        "CURRENT AIR QUALITY:",
        f"  - European AQI:        {aq_curr.get('european_aqi')} ({aq_curr.get('european_aqi_level')})",
        f"  - US AQI:              {aq_curr.get('us_aqi')} ({aq_curr.get('us_aqi_level')})",
        f"  - PM2.5 (Fine dust):   {aq_curr.get('pm2_5')} ug/m3",
        f"  - PM10 (Particulate):  {aq_curr.get('pm10')} ug/m3",
        f"  - Nitrogen Dioxide:    {aq_curr.get('nitrogen_dioxide')} ug/m3",
        f"  - Ozone:               {aq_curr.get('ozone')} ug/m3",
        "",
        "DAILY FORECAST:",
    ]

    for day in daily[:5]:
        lines.append(
            f"  {day.get('date')}: {day.get('weather_description'):<22} "
            f"Temp: {day.get('temperature_min')} C to {day.get('temperature_max')} C | "
            f"Rain prob: {day.get('precipitation_probability_max')}% ({day.get('precipitation_sum')} mm)"
        )

    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download weather forecast and air quality data for a provided location."
    )
    parser.add_argument(
        "--location", "-l",
        type=str,
        default=None,
        help="Location name (city or address, e.g. 'Krakow', 'Warsaw')",
    )
    parser.add_argument("--lat", type=float, default=None, help="Latitude coordinate")
    parser.add_argument("--lon", type=float, default=None, help="Longitude coordinate")
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Path to save downloaded data as JSON (e.g. weather.json)",
    )
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=7,
        help="Number of forecast days (default: 7)",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Output full raw JSON to console instead of formatted summary",
    )

    args = parser.parse_args()

    # Determine location or default to Krakow if none given
    loc_input = args.location
    if not loc_input and args.lat is None and args.lon is None:
        loc_input = get_default_location() or "Krakow"

    print(f"Fetching weather forecast and air quality data for '{loc_input or (args.lat, args.lon)}'...")

    try:
        data = download_weather_and_air_quality(
            location=loc_input,
            latitude=args.lat,
            longitude=args.lon,
            forecast_days=args.days,
        )

        if args.output:
            save_to_file(data, args.output)
            print(f"Saved data to {args.output}")

        if args.raw:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            summary = format_summary_text(data)
            try:
                print(summary)
            except UnicodeEncodeError:
                print(summary.encode("ascii", errors="replace").decode("ascii"))

    except Exception as e:
        print(f"Error fetching data: {e}")
        exit(1)
