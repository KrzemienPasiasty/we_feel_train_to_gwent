from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

from tag import Tag
from week_periods import DAYS_IN_WEEK, SLOT_MINUTES, SLOTS_PER_DAY, WeeklySchedule


# ==============================================================================
# Physical Activity Data Structures
# ==============================================================================

@dataclass
class ScheduledActivity:
    """Represents a scheduled physical activity / workout session."""
    activity_index: int               # 0, 1, 2...
    name: str                         # "Workout", "Running", "Gym", etc.
    day: int                          # 0..6 (Monday..Sunday)
    start_slot: int                   # 0..95
    end_slot: int                     # start_slot + slots_needed
    start_time: time
    end_time: time
    duration_minutes: int
    tag: Optional[Tag] = None
    color: str = "#4CAF50"            # Workout green
    outdoor: bool = True
    weather_penalty: float = 0.0
    air_quality_penalty: float = 0.0
    weather_description: str = "Unknown"
    air_quality_description: str = "Unknown"

    def to_calendar_dict(self) -> Dict[str, Any]:
        """Formats the scheduled activity for WeeklyCalendarFrame."""
        return {
            "id": -(2000 + self.day * 10 + self.activity_index),
            "title": f"Activity: {self.name}",
            "day": self.day,
            "start_time": self.start_time,
            "duration_minutes": self.duration_minutes,
            "color": self.color,
            "priority": "HIGH",
            "is_activity": True,
            "outdoor": self.outdoor,
            "weather_penalty": round(self.weather_penalty, 2),
            "air_quality_penalty": round(self.air_quality_penalty, 2),
            "weather_description": self.weather_description,
            "air_quality_description": self.air_quality_description,
        }


@dataclass
class PhysicalActivityConfig:
    """Configuration for physical activity scheduling, weather, and air quality constraints."""
    duration_minutes: int = 60
    sessions_per_week: int = 3
    earliest_time: time = time(6, 30)
    latest_time: time = time(21, 0)
    outdoor: bool = True
    tag_names: Optional[List[str]] = None
    color: str = "#4CAF50"
    active_days: Optional[List[int]] = None
    weather_weight: float = 1.0
    air_quality_weight: float = 1.0
    missing_session_penalty: float = 80.0


# ==============================================================================
# Helper Utilities
# ==============================================================================

def slot_to_time(slot_idx: int) -> time:
    minutes = slot_idx * SLOT_MINUTES
    return time(hour=(minutes // 60) % 24, minute=minutes % 60)


def time_to_slot(t: time) -> int:
    return (t.hour * 60 + t.minute) // SLOT_MINUTES


DEFAULT_ACTIVITY_TAGS = [
    "sport", "workout", "gym", "training", "running", "jogging", "fitness",
    "exercise", "cycling", "trening", "bieganie", "siłownia", "ćwiczenia",
    "aktywność", "activity", "physical activity", "cardio"
]


# ==============================================================================
# Weather & Air Quality Condition Extraction
# ==============================================================================

def extract_hourly_conditions(
    day: int,
    hour: int,
    weather_forecast: Optional[Any] = None,
    air_quality_forecast: Optional[Any] = None
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Extracts weather and air quality metrics for a given day (0..6) and hour (0..23).

    Supports:
      - Unified dict with {"weather": ..., "air_quality": ...}
      - Direct Open-Meteo format with "hourly" lists
      - Daily lists / current fallbacks
      - Custom user dictionaries or callables
    """
    # Normalize inputs if unified dictionary is passed
    if isinstance(weather_forecast, dict) and "weather" in weather_forecast and air_quality_forecast is None:
        air_quality_forecast = weather_forecast.get("air_quality")
        weather_forecast = weather_forecast.get("weather")

    weather_cond: Dict[str, Any] = {
        "weather_code": 0,
        "temperature": 18.0,
        "precipitation": 0.0,
        "precipitation_probability": 0.0,
        "wind_speed": 10.0,
        "description": "Clear sky"
    }

    air_cond: Dict[str, Any] = {
        "european_aqi": 15.0,
        "us_aqi": 30.0,
        "pm2_5": 10.0,
        "pm10": 15.0,
        "description": "Good"
    }

    hour_idx = day * 24 + hour

    # --- Extract Weather ---
    if isinstance(weather_forecast, dict):
        hourly_w = weather_forecast.get("hourly")
        if isinstance(hourly_w, dict):
            # Check length of time series
            times = hourly_w.get("time", [])
            idx = hour_idx if (times and hour_idx < len(times)) else (hour % len(times) if times else 0)

            codes = hourly_w.get("weather_code", [])
            if codes and idx < len(codes):
                weather_cond["weather_code"] = codes[idx]

            temps = hourly_w.get("temperature_2m", [])
            if temps and idx < len(temps):
                weather_cond["temperature"] = temps[idx]

            precips = hourly_w.get("precipitation", [])
            if precips and idx < len(precips):
                weather_cond["precipitation"] = precips[idx]

            probs = hourly_w.get("precipitation_probability", [])
            if probs and idx < len(probs):
                weather_cond["precipitation_probability"] = probs[idx]

            winds = hourly_w.get("wind_speed_10m", [])
            if winds and idx < len(winds):
                weather_cond["wind_speed"] = winds[idx]

        elif "current" in weather_forecast and isinstance(weather_forecast["current"], dict):
            curr_w = weather_forecast["current"]
            weather_cond["weather_code"] = curr_w.get("weather_code", 0)
            weather_cond["temperature"] = curr_w.get("temperature", 18.0)
            weather_cond["precipitation"] = curr_w.get("precipitation", 0.0)
            weather_cond["wind_speed"] = curr_w.get("wind_speed", 10.0)
            weather_cond["description"] = curr_w.get("weather_description", "Current")

    elif callable(weather_forecast):
        try:
            res = weather_forecast(day, hour)
            if isinstance(res, dict):
                weather_cond.update(res)
        except Exception:
            pass

    # --- Extract Air Quality ---
    if isinstance(air_quality_forecast, dict):
        hourly_aq = air_quality_forecast.get("hourly")
        if isinstance(hourly_aq, dict):
            times = hourly_aq.get("time", [])
            idx = hour_idx if (times and hour_idx < len(times)) else (hour % len(times) if times else 0)

            eu_aqis = hourly_aq.get("european_aqi", [])
            if eu_aqis and idx < len(eu_aqis):
                weather_cond_val = eu_aqis[idx]
                if weather_cond_val is not None:
                    air_cond["european_aqi"] = weather_cond_val

            us_aqis = hourly_aq.get("us_aqi", [])
            if us_aqis and idx < len(us_aqis):
                val = us_aqis[idx]
                if val is not None:
                    air_cond["us_aqi"] = val

            pm25s = hourly_aq.get("pm2_5", [])
            if pm25s and idx < len(pm25s):
                val = pm25s[idx]
                if val is not None:
                    air_cond["pm2_5"] = val

            pm10s = hourly_aq.get("pm10", [])
            if pm10s and idx < len(pm10s):
                val = pm10s[idx]
                if val is not None:
                    air_cond["pm10"] = val

        elif "current" in air_quality_forecast and isinstance(air_quality_forecast["current"], dict):
            curr_aq = air_quality_forecast["current"]
            air_cond["european_aqi"] = curr_aq.get("european_aqi", 15.0)
            air_cond["us_aqi"] = curr_aq.get("us_aqi", 30.0)
            air_cond["pm2_5"] = curr_aq.get("pm2_5", 10.0)
            air_cond["pm10"] = curr_aq.get("pm10", 15.0)

    elif callable(air_quality_forecast):
        try:
            res = air_quality_forecast(day, hour)
            if isinstance(res, dict):
                air_cond.update(res)
        except Exception:
            pass

    return weather_cond, air_cond


# ==============================================================================
# Condition Penalty Calculations
# ==============================================================================

def calculate_weather_slot_penalty(weather_condition: Dict[str, Any]) -> float:
    """
    Calculates penalty for training in bad weather during a 15-minute slot.

    Punishes:
      - Rain, Drizzle, Freezing rain, Snow, Showers, Violent Thunderstorms (WMO codes)
      - High precipitation amount (mm)
      - Extreme temperatures (below freezing < 0C, freezing chill, extreme heat > 30C)
      - Dangerous wind gusts
    """
    penalty = 0.0
    code = weather_condition.get("weather_code") or 0
    precip = float(weather_condition.get("precipitation") or 0.0)
    temp = float(weather_condition.get("temperature") or 18.0)
    wind = float(weather_condition.get("wind_speed") or 10.0)

    # 1. Weather code penalties (WMO standard)
    if code in [51, 56]:           # Drizzle: Light
        penalty += 12.0
    elif code in [53]:             # Drizzle: Moderate
        penalty += 20.0
    elif code in [55, 57]:         # Drizzle: Dense intensity / Freezing
        penalty += 35.0
    elif code in [61, 80]:         # Rain: Slight / Light Showers
        penalty += 25.0
    elif code in [63, 81]:         # Rain: Moderate / Showers Moderate
        penalty += 45.0
    elif code in [65, 82]:         # Rain: Heavy intensity / Violent showers
        penalty += 75.0
    elif code in [66, 67]:         # Freezing Rain
        penalty += 80.0
    elif code in [71, 77, 85]:     # Snow: Slight / grains / showers slight
        penalty += 35.0
    elif code in [73, 75, 86]:     # Snow: Moderate to heavy
        penalty += 65.0
    elif code in [95]:             # Thunderstorm
        penalty += 90.0
    elif code in [96, 99]:         # Thunderstorm with hail
        penalty += 120.0

    # 2. Rain / Precipitation volume penalty
    if precip > 0:
        penalty += min(40.0, precip * 15.0)

    # 3. Temperature discomfort and risk penalties
    if temp < 0.0:
        # Freezing cold penalty grows with degrees below zero
        penalty += 15.0 + abs(temp) * 3.0
    elif temp < 5.0:
        # Chilly / near freezing
        penalty += (5.0 - temp) * 2.0
    elif temp > 33.0:
        # Heat stroke risk
        penalty += 25.0 + (temp - 33.0) * 5.0
    elif temp > 28.0:
        # Hot weather discomfort
        penalty += (temp - 28.0) * 3.0

    # 4. Gale / Storm wind penalties
    if wind > 40.0:
        penalty += (wind - 40.0) * 1.5

    return penalty


def calculate_air_quality_slot_penalty(air_condition: Dict[str, Any]) -> float:
    """
    Calculates penalty for training in bad air quality during a 15-minute slot.

    Punishes:
      - European AQI levels above Fair/Moderate (> 20, > 40, > 60, > 80)
      - US AQI levels (> 50, > 100, > 150, > 200, > 300)
      - High particulate matter concentrations (PM2.5 > 25 ug/m3, PM10 > 50 ug/m3)
    """
    penalty = 0.0
    eu_aqi = air_condition.get("european_aqi")
    us_aqi = air_condition.get("us_aqi")
    pm25 = air_condition.get("pm2_5")

    # 1. European AQI evaluation
    if eu_aqi is not None:
        eu_val = float(eu_aqi)
        if eu_val <= 20:       # Good
            pass
        elif eu_val <= 40:     # Fair
            penalty += 8.0
        elif eu_val <= 60:     # Moderate
            penalty += 25.0
        elif eu_val <= 80:     # Poor
            penalty += 55.0
        elif eu_val <= 100:    # Very Poor
            penalty += 95.0
        else:                  # Extremely Poor
            penalty += 140.0

    # 2. US AQI evaluation (used if European AQI not present or as cross-validation)
    elif us_aqi is not None:
        us_val = float(us_aqi)
        if us_val <= 50:       # Good
            pass
        elif us_val <= 100:    # Moderate
            penalty += 12.0
        elif us_val <= 150:    # Unhealthy for Sensitive Groups
            penalty += 35.0
        elif us_val <= 200:    # Unhealthy
            penalty += 70.0
        elif us_val <= 300:    # Very Unhealthy
            penalty += 110.0
        else:                  # Hazardous
            penalty += 160.0

    # 3. Fine particulate matter (PM2.5) penalty
    if pm25 is not None:
        pm_val = float(pm25)
        if pm_val > 25.0:
            penalty += min(50.0, (pm_val - 25.0) * 1.5)

    return penalty


def calculate_activity_conditions_penalty(
    activity: ScheduledActivity,
    weather_forecast: Optional[Any] = None,
    air_quality_forecast: Optional[Any] = None,
    weather_weight: float = 1.0,
    air_quality_weight: float = 1.0
) -> Tuple[float, float]:
    """
    Evaluates weather and air quality across all slots of a scheduled activity,
    returning (weather_penalty, air_quality_penalty).
    """
    if not activity.outdoor:
        # Indoor activities are protected from bad rain and weather
        return 0.0, 0.0

    total_w_pen = 0.0
    total_aq_pen = 0.0

    for slot in range(activity.start_slot, activity.end_slot):
        hour = (slot * SLOT_MINUTES) // 60
        w_cond, aq_cond = extract_hourly_conditions(
            day=activity.day,
            hour=hour,
            weather_forecast=weather_forecast,
            air_quality_forecast=air_quality_forecast
        )

        total_w_pen += calculate_weather_slot_penalty(w_cond)
        total_aq_pen += calculate_air_quality_slot_penalty(aq_cond)

    return total_w_pen * weather_weight, total_aq_pen * air_quality_weight


# ==============================================================================
# Parsing & Placement of Physical Activity
# ==============================================================================

def parse_physical_activities_from_weekly_schedule(
    weekly_schedule: WeeklySchedule,
    activity_tag_names: Optional[List[str]] = None,
    weather_forecast: Optional[Any] = None,
    air_quality_forecast: Optional[Any] = None
) -> List[ScheduledActivity]:
    """
    Scans WeeklySchedule for slots pre-tagged with physical activity / sport tags
    (e.g., 'Sport', 'Workout', 'Gym', 'Trening', etc.) and groups consecutive slots
    into ScheduledActivity blocks, computing weather and air quality penalties.
    """
    names = activity_tag_names if activity_tag_names is not None else DEFAULT_ACTIVITY_TAGS
    tag_set = {t.strip().lower() for t in names}
    parsed: List[ScheduledActivity] = []

    for day in range(DAYS_IN_WEEK):
        in_activity = False
        act_start = 0
        act_tags: List[Tag] = []

        for slot in range(SLOTS_PER_DAY):
            slot_tags = weekly_schedule._slots[day][slot]
            has_act_tag = any(
                str(getattr(st, "title", st)).strip().lower() in tag_set
                for st in slot_tags
            )

            if has_act_tag and not in_activity:
                in_activity = True
                act_start = slot
                act_tags = slot_tags
            elif not has_act_tag and in_activity:
                in_activity = False
                duration = (slot - act_start) * SLOT_MINUTES
                name = "Workout"
                for st in act_tags:
                    title = str(getattr(st, "title", st)).strip()
                    if title.lower() in tag_set:
                        name = title
                        break

                act = ScheduledActivity(
                    activity_index=len([a for a in parsed if a.day == day]),
                    name=name,
                    day=day,
                    start_slot=act_start,
                    end_slot=slot,
                    start_time=slot_to_time(act_start),
                    end_time=slot_to_time(slot),
                    duration_minutes=duration
                )
                w_pen, aq_pen = calculate_activity_conditions_penalty(
                    act, weather_forecast, air_quality_forecast
                )
                act.weather_penalty = w_pen
                act.air_quality_penalty = aq_pen
                parsed.append(act)
                act_tags = []

        if in_activity:
            duration = (SLOTS_PER_DAY - act_start) * SLOT_MINUTES
            name = "Workout"
            for st in act_tags:
                title = str(getattr(st, "title", st)).strip()
                if title.lower() in tag_set:
                    name = title
                    break
            act = ScheduledActivity(
                activity_index=len([a for a in parsed if a.day == day]),
                name=name,
                day=day,
                start_slot=act_start,
                end_slot=SLOTS_PER_DAY,
                start_time=slot_to_time(act_start),
                end_time=time(23, 59),
                duration_minutes=duration
            )
            w_pen, aq_pen = calculate_activity_conditions_penalty(
                act, weather_forecast, air_quality_forecast
            )
            act.weather_penalty = w_pen
            act.air_quality_penalty = aq_pen
            parsed.append(act)

    return parsed


def parse_physical_activity(
    duration_minutes: int,
    weekly_schedule: WeeklySchedule,
    weather_forecast: Optional[Any] = None,
    air_quality_forecast: Optional[Any] = None,
    sessions_per_week: int = 3,
    schedule: Optional[Any] = None,
    config: Optional[PhysicalActivityConfig] = None,
    **kwargs
) -> List[ScheduledActivity]:
    """
    Top-level function:
    Parses physical activity of duration `duration_minutes` into the weekly schedule,
    taking into account air quality and weather forecasts, and punishing training in
    bad weather and bad air quality.

    Workflow:
      1. Parses any existing pre-tagged physical activities in the WeeklySchedule.
      2. If more sessions are needed to reach `sessions_per_week`, dynamically evaluates
         candidate time windows of `duration_minutes`.
      3. For each candidate window, computes bad weather and bad air quality penalties.
      4. Selects optimal training windows that minimize bad weather and bad air quality penalties.
      5. If a Schedule object is passed, attaches activities and reserves slots in schedule.grid.

    Parameters:
      - duration_minutes: Target duration of physical activity session in minutes.
      - weekly_schedule: WeeklySchedule instance.
      - weather_forecast: Weather forecast data or unified weather+air dict.
      - air_quality_forecast: Optional separate air quality forecast data.
      - sessions_per_week: Number of training sessions to schedule across the week (default 3).
      - schedule: Optional Schedule instance to reserve grid slots and store activities.
      - config: Optional PhysicalActivityConfig instance.

    Returns:
      List of ScheduledActivity objects.
    """
    cfg = copy.copy(config) if config is not None else PhysicalActivityConfig(duration_minutes=duration_minutes)
    cfg.duration_minutes = duration_minutes
    if "sessions_per_week" in kwargs:
        cfg.sessions_per_week = kwargs["sessions_per_week"]
    else:
        cfg.sessions_per_week = sessions_per_week

    for k, v in kwargs.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)

    # 1. Parse existing physical activities tagged in WeeklySchedule
    existing_activities = parse_physical_activities_from_weekly_schedule(
        weekly_schedule=weekly_schedule,
        activity_tag_names=cfg.tag_names,
        weather_forecast=weather_forecast,
        air_quality_forecast=air_quality_forecast
    )

    all_activities: List[ScheduledActivity] = list(existing_activities)

    # 2. Determine how many additional sessions are needed
    needed = max(0, cfg.sessions_per_week - len(all_activities))
    if needed <= 0:
        if schedule is not None and hasattr(schedule, "add_activity"):
            for act in all_activities:
                schedule.add_activity(act)
        return all_activities

    slots_needed = max(1, math.ceil(cfg.duration_minutes / SLOT_MINUTES))
    earliest_s = time_to_slot(cfg.earliest_time)
    latest_s = time_to_slot(cfg.latest_time)

    candidate_days = cfg.active_days if cfg.active_days is not None else list(range(DAYS_IN_WEEK))
    # Prefer spreading activities (e.g. Mon, Wed, Fri or days without activities yet)
    days_with_activity = {act.day for act in all_activities}

    # Evaluate candidate windows across available days and slots
    candidate_windows: List[Tuple[float, int, int, float, float]] = []  # (total_cost, day, start_slot, w_pen, aq_pen)

    for day in candidate_days:
        for s in range(earliest_s, min(latest_s - slots_needed + 1, SLOTS_PER_DAY - slots_needed + 1)):
            e = s + slots_needed

            # Check collision with schedule grid if provided
            if schedule is not None and hasattr(schedule, "is_window_free"):
                if not schedule.is_window_free(day, s, e):
                    continue

            # Check collision with already chosen activities
            collision = any(
                a.day == day and not (e <= a.start_slot or s >= a.end_slot)
                for a in all_activities
            )
            if collision:
                continue

            # Calculate weather and air quality penalties for this candidate window
            temp_act = ScheduledActivity(
                activity_index=0,
                name="Training",
                day=day,
                start_slot=s,
                end_slot=e,
                start_time=slot_to_time(s),
                end_time=slot_to_time(e),
                duration_minutes=cfg.duration_minutes,
                outdoor=cfg.outdoor
            )
            w_pen, aq_pen = calculate_activity_conditions_penalty(
                activity=temp_act,
                weather_forecast=weather_forecast,
                air_quality_forecast=air_quality_forecast,
                weather_weight=cfg.weather_weight,
                air_quality_weight=cfg.air_quality_weight
            )

            # Preference cost: prefer spreading across different days and avoiding late night
            day_clustering_cost = 20.0 if day in days_with_activity else 0.0
            total_cost = w_pen + aq_pen + day_clustering_cost

            candidate_windows.append((total_cost, day, s, w_pen, aq_pen))

    # Sort windows by condition cost (lowest penalty = best weather & clean air)
    candidate_windows.sort(key=lambda item: item[0])

    # Greedily pick the best non-overlapping windows
    added_count = 0
    for cost, day, s, w_pen, aq_pen in candidate_windows:
        if added_count >= needed:
            break

        e = s + slots_needed
        # Check collision again with newly added activities
        collision = any(
            a.day == day and not (e <= a.start_slot or s >= a.end_slot)
            for a in all_activities
        )
        if collision:
            continue

        act = ScheduledActivity(
            activity_index=len([a for a in all_activities if a.day == day]),
            name="Training",
            day=day,
            start_slot=s,
            end_slot=e,
            start_time=slot_to_time(s),
            end_time=slot_to_time(e),
            duration_minutes=cfg.duration_minutes,
            color=cfg.color,
            outdoor=cfg.outdoor,
            weather_penalty=w_pen,
            air_quality_penalty=aq_pen
        )
        all_activities.append(act)
        days_with_activity.add(day)
        added_count += 1

        if schedule is not None and hasattr(schedule, "add_activity"):
            schedule.add_activity(act)

    all_activities.sort(key=lambda a: (a.day, a.start_slot))
    return all_activities
