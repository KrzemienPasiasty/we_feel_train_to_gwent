"""
Sleep Quality Tracking and SAFTE Model Module.
Supports downloading sleep data from Garmin Connect and Samsung Health,
and scaling productivity curves using an adapted SAFTE (Sleep, Activity, Fatigue,
and Task Effectiveness) biomathematical model.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNIFIED_CREDENTIALS_FILE = os.path.join(BASE_DIR, "api_credentials.json")


# ==============================================================================
# Sleep Data Models
# ==============================================================================

@dataclass
class SleepStageBreakdown:
    """Breakdown of sleep duration by physiological sleep stages."""
    deep_minutes: float = 0.0
    rem_minutes: float = 0.0
    light_minutes: float = 0.0
    awake_minutes: float = 0.0

    @property
    def total_sleep_minutes(self) -> float:
        return self.deep_minutes + self.rem_minutes + self.light_minutes

    @property
    def restorative_minutes(self) -> float:
        """Deep + REM sleep are considered restorative for cognitive and physical recovery."""
        return self.deep_minutes + self.rem_minutes


@dataclass
class SleepQualityData:
    """
    Standardized sleep quality representation across Garmin, Samsung,
    and other wearable ecosystems.
    """
    source: str                                # "garmin", "samsung", "manual"
    date_str: str                              # "YYYY-MM-DD"
    sleep_score: float                         # 0 to 100 overall quality score
    total_sleep_minutes: float                 # Total duration asleep in minutes
    wake_time: time = time(7, 0)               # Time of morning awakening
    bed_time: time = time(23, 0)               # Time of falling asleep
    sleep_efficiency: float = 0.85             # Ratio of time asleep vs time in bed (0.0 to 1.0)
    stages: Optional[SleepStageBreakdown] = None
    hrv_overnight_avg: Optional[float] = None  # Heart Rate Variability in ms
    resting_hr: Optional[float] = None         # Lowest or average resting heart rate during sleep
    quality_label: str = "GOOD"                # "EXCELLENT", "GOOD", "FAIR", "POOR"
    raw_data: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        # Normalize efficiency to 0.0 .. 1.0 if given as 0 .. 100
        if self.sleep_efficiency > 1.0:
            self.sleep_efficiency = min(1.0, self.sleep_efficiency / 100.0)

        # Infer quality label if default
        if not self.quality_label or self.quality_label == "GOOD":
            if self.sleep_score >= 85:
                self.quality_label = "EXCELLENT"
            elif self.sleep_score >= 70:
                self.quality_label = "GOOD"
            elif self.sleep_score >= 50:
                self.quality_label = "FAIR"
            else:
                self.quality_label = "POOR"


# ==============================================================================
# Garmin Sleep Data Downloader & Parser
# ==============================================================================

def parse_garmin_sleep_data(data: Dict[str, Any], target_date: Optional[str] = None) -> SleepQualityData:
    """
    Parses a Garmin Connect sleep JSON dictionary (e.g. from get_sleep_data())
    into unified SleepQualityData.
    """
    daily_dto = data.get("dailySleepDTO", {})
    scores_dict = data.get("sleepScores", {})

    # Extract date
    date_val = target_date or daily_dto.get("calendarDate") or date.today().isoformat()

    # Extract sleep durations in seconds -> minutes
    sleep_time_sec = float(daily_dto.get("sleepTimeSeconds", 0) or 0)
    deep_sec = float(daily_dto.get("deepSleepSeconds", 0) or 0)
    light_sec = float(daily_dto.get("lightSleepSeconds", 0) or 0)
    rem_sec = float(daily_dto.get("remSleepSeconds", 0) or 0)
    awake_sec = float(daily_dto.get("awakeSleepSeconds", 0) or 0)

    total_sleep_min = sleep_time_sec / 60.0
    if total_sleep_min <= 0 and (deep_sec + light_sec + rem_sec) > 0:
        total_sleep_min = (deep_sec + light_sec + rem_sec) / 60.0

    stages = SleepStageBreakdown(
        deep_minutes=deep_sec / 60.0,
        rem_minutes=rem_sec / 60.0,
        light_minutes=light_sec / 60.0,
        awake_minutes=awake_sec / 60.0
    )

    # Extract score (0-100)
    overall_score = 0.0
    if isinstance(scores_dict, dict) and "overall" in scores_dict:
        ov = scores_dict["overall"]
        if isinstance(ov, dict):
            overall_score = float(ov.get("value", 0) or 0)
        elif isinstance(ov, (int, float)):
            overall_score = float(ov)
    elif "sleepScore" in daily_dto:
        overall_score = float(daily_dto.get("sleepScore", 0) or 0)

    # Fallback score estimation from duration and restorative stages if score missing
    if overall_score <= 0:
        # Benchmark: 8h (480m) sleep + 1.5h restorative -> ~80 score
        dur_score = min(50.0, (total_sleep_min / 480.0) * 50.0)
        rest_score = min(50.0, (stages.restorative_minutes / 120.0) * 50.0)
        overall_score = round(dur_score + rest_score, 1)

    # Wake time and bed time
    wake_t = time(7, 0)
    bed_t = time(23, 0)

    end_ts = daily_dto.get("sleepEndTimestampLocal")
    if end_ts:
        try:
            if isinstance(end_ts, (int, float)):
                # epoch ms or s
                dt = datetime.fromtimestamp(end_ts / 1000.0 if end_ts > 1e11 else end_ts)
                wake_t = dt.time()
            elif isinstance(end_ts, str):
                dt = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
                wake_t = dt.time()
        except Exception:
            pass

    start_ts = daily_dto.get("sleepStartTimestampLocal")
    if start_ts:
        try:
            if isinstance(start_ts, (int, float)):
                dt = datetime.fromtimestamp(start_ts / 1000.0 if start_ts > 1e11 else start_ts)
                bed_t = dt.time()
            elif isinstance(start_ts, str):
                dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                bed_t = dt.time()
        except Exception:
            pass

    # Efficiency
    in_bed_sec = sleep_time_sec + awake_sec
    eff = (sleep_time_sec / in_bed_sec) if in_bed_sec > 0 else 0.85

    return SleepQualityData(
        source="garmin",
        date_str=str(date_val),
        sleep_score=max(0.0, min(100.0, overall_score)),
        total_sleep_minutes=total_sleep_min,
        wake_time=wake_t,
        bed_time=bed_t,
        sleep_efficiency=eff,
        stages=stages,
        hrv_overnight_avg=daily_dto.get("avgOvernightHrv"),
        resting_hr=daily_dto.get("restingHeartRate"),
        raw_data=data
    )


def download_garmin_sleep_data(
    email: Optional[str] = None,
    password: Optional[str] = None,
    token_dir: Optional[str] = None,
    date_str: Optional[str] = None,
    credentials_path: Optional[str] = None
) -> Optional[SleepQualityData]:
    """
    Downloads sleep data from Garmin Connect.
    Uses credentials from arguments or api_credentials.json.
    Supports official or third-party garminconnect library, or local cached token dumps.
    """
    cred_file = credentials_path or UNIFIED_CREDENTIALS_FILE
    if os.path.exists(cred_file):
        try:
            with open(cred_file, "r", encoding="utf-8") as f:
                creds = json.load(f)
                garmin_creds = creds.get("garmin", {})
                if not email and "email" in garmin_creds:
                    email = garmin_creds["email"]
                if not password and "password" in garmin_creds:
                    password = garmin_creds["password"]
                if not token_dir and "token_dir" in garmin_creds:
                    token_dir = garmin_creds["token_dir"]
        except Exception:
            pass

    target_date = date_str or date.today().isoformat()

    # 1. Try python garminconnect library if installed
    try:
        from garminconnect import Garmin, GarminConnectAuthenticationError  # type: ignore

        client = None
        if token_dir:
            expanded_token_dir = os.path.expanduser(token_dir)
            if os.path.exists(expanded_token_dir):
                client = Garmin()
                client.login(tokenstore=expanded_token_dir)

        if client is None and email and password and "YOUR_" not in email:
            client = Garmin(email, password)
            client.login()

        if client is not None:
            raw_data = client.get_sleep_data(target_date)
            return parse_garmin_sleep_data(raw_data, target_date=target_date)
    except ImportError:
        pass
    except Exception as e:
        print(f"[Garmin Sleep API] Note: Could not query live Garmin API ({e}). Checking local cache...", file=sys.stderr)

    # 2. Check local cached file or export
    cache_candidates = [
        os.path.join(BASE_DIR, "garmin_sleep.json"),
        os.path.join(BASE_DIR, "garmin_sleep_data.json"),
        os.path.expanduser("~/.garminconnect/sleep_data.json"),
    ]
    for c_path in cache_candidates:
        if os.path.exists(c_path):
            try:
                with open(c_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return parse_garmin_sleep_data(data, target_date=target_date)
            except Exception:
                continue

    return None


# ==============================================================================
# Samsung Health Sleep Data Downloader & Parser
# ==============================================================================

def parse_samsung_sleep_data(
    data_payload: Union[Dict[str, Any], str, bytes],
    target_date: Optional[str] = None
) -> SleepQualityData:
    """
    Parses Samsung Health sleep data from JSON dict, CSV text, or ZIP export archive.
    """
    # Case A: JSON dict (from Health Connect webhook or Partner API)
    if isinstance(data_payload, dict):
        score = float(data_payload.get("sleep_score", data_payload.get("score", 75)) or 75)
        duration_min = float(data_payload.get("duration", data_payload.get("duration_minutes", 450)) or 450)
        eff = float(data_payload.get("efficiency", 0.85) or 0.85)

        stages_dict = data_payload.get("stages", {})
        stages = None
        if stages_dict:
            stages = SleepStageBreakdown(
                deep_minutes=float(stages_dict.get("deep", 0)),
                rem_minutes=float(stages_dict.get("rem", 0)),
                light_minutes=float(stages_dict.get("light", 0)),
                awake_minutes=float(stages_dict.get("awake", 0))
            )

        wake_t = time(7, 0)
        bed_t = time(23, 0)
        if "wake_time" in data_payload:
            wt = data_payload["wake_time"]
            if isinstance(wt, str) and ":" in wt:
                h, m = map(int, wt.split(":")[:2])
                wake_t = time(h, m)

        return SleepQualityData(
            source="samsung",
            date_str=target_date or data_payload.get("date", date.today().isoformat()),
            sleep_score=max(0.0, min(100.0, score)),
            total_sleep_minutes=duration_min,
            wake_time=wake_t,
            bed_time=bed_t,
            sleep_efficiency=eff,
            stages=stages,
            raw_data=data_payload
        )

    # Case B: CSV content string
    if isinstance(data_payload, str) and ("com.samsung.shealth.sleep" in data_payload or "start_time" in data_payload):
        lines = [line.strip() for line in data_payload.splitlines() if line.strip()]
        # Skip comment/metadata lines if present
        header_idx = 0
        for idx, line in enumerate(lines[:5]):
            if "start_time" in line or "duration" in line or "efficiency" in line:
                header_idx = idx
                break

        reader = csv.DictReader(lines[header_idx:])
        rows = list(reader)
        if rows:
            last_row = rows[-1]
            eff = float(last_row.get("efficiency", 85) or 85)
            # Duration in ms or minutes
            dur_val = float(last_row.get("duration", 0) or 0)
            if dur_val > 100000:
                total_min = dur_val / 60000.0
            elif dur_val > 0:
                total_min = dur_val
            else:
                total_min = 450.0

            score = float(last_row.get("sleep_score", 0) or 0)
            if score <= 0:
                score = round(min(100.0, (total_min / 480.0) * 80.0 + (eff if eff <= 1.0 else eff / 100.0) * 20.0), 1)

            return SleepQualityData(
                source="samsung",
                date_str=target_date or date.today().isoformat(),
                sleep_score=score,
                total_sleep_minutes=total_min,
                sleep_efficiency=eff,
                raw_data=last_row
            )

    # Fallback default Samsung model
    return SleepQualityData(
        source="samsung",
        date_str=target_date or date.today().isoformat(),
        sleep_score=75.0,
        total_sleep_minutes=450.0,
        sleep_efficiency=0.85
    )


def download_samsung_sleep_data(
    export_path: Optional[str] = None,
    api_token: Optional[str] = None,
    date_str: Optional[str] = None,
    credentials_path: Optional[str] = None
) -> Optional[SleepQualityData]:
    """
    Downloads or parses Samsung Health sleep data.
    Checks export_path (ZIP archive or extracted folder) or configured api_credentials.json.
    """
    cred_file = credentials_path or UNIFIED_CREDENTIALS_FILE
    if os.path.exists(cred_file):
        try:
            with open(cred_file, "r", encoding="utf-8") as f:
                creds = json.load(f)
                samsung_creds = creds.get("samsung", {})
                if not export_path and "export_path" in samsung_creds:
                    export_path = samsung_creds["export_path"]
                if not api_token and "api_token" in samsung_creds:
                    api_token = samsung_creds["api_token"]
        except Exception:
            pass

    target_date = date_str or date.today().isoformat()

    # 1. Check if export_path is a ZIP archive
    if export_path and os.path.exists(export_path):
        if zipfile.is_zipfile(export_path):
            try:
                with zipfile.ZipFile(export_path, "r") as z:
                    # Search for sleep summary file
                    summary_files = [f for f in z.namelist() if "shealth.sleep." in f and f.endswith(".csv")]
                    if summary_files:
                        with z.open(summary_files[0]) as csv_file:
                            content = csv_file.read().decode("utf-8", errors="replace")
                            return parse_samsung_sleep_data(content, target_date=target_date)
            except Exception as e:
                print(f"[Samsung Health] Failed reading ZIP archive: {e}", file=sys.stderr)
        elif os.path.isdir(export_path):
            for fname in os.listdir(export_path):
                if "shealth.sleep." in fname and fname.endswith(".csv"):
                    try:
                        with open(os.path.join(export_path, fname), "r", encoding="utf-8") as f:
                            return parse_samsung_sleep_data(f.read(), target_date=target_date)
                    except Exception:
                        pass
        elif os.path.isfile(export_path):
            try:
                with open(export_path, "r", encoding="utf-8") as f:
                    if export_path.endswith(".json"):
                        return parse_samsung_sleep_data(json.load(f), target_date=target_date)
                    return parse_samsung_sleep_data(f.read(), target_date=target_date)
            except Exception:
                pass

    # 2. Check local fallback files
    local_candidates = [
        os.path.join(BASE_DIR, "samsung_sleep.json"),
        os.path.join(BASE_DIR, "samsung_sleep.csv"),
    ]
    for cand in local_candidates:
        if os.path.exists(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    if cand.endswith(".json"):
                        return parse_samsung_sleep_data(json.load(f), target_date=target_date)
                    return parse_samsung_sleep_data(f.read(), target_date=target_date)
            except Exception:
                continue

    return None


def download_sleep_quality_data(
    source: str = "auto",  # "auto", "garmin", "samsung"
    date_str: Optional[str] = None,
    credentials_path: Optional[str] = None
) -> Optional[SleepQualityData]:
    """
    Unified entry point to download sleep quality data from Garmin or Samsung.
    If source='auto', tries Garmin first, then Samsung.
    """
    target_date = date_str or date.today().isoformat()

    if source.lower() == "garmin":
        return download_garmin_sleep_data(date_str=target_date, credentials_path=credentials_path)
    elif source.lower() == "samsung":
        return download_samsung_sleep_data(date_str=target_date, credentials_path=credentials_path)
    else:  # auto
        g_data = download_garmin_sleep_data(date_str=target_date, credentials_path=credentials_path)
        if g_data:
            return g_data
        s_data = download_samsung_sleep_data(date_str=target_date, credentials_path=credentials_path)
        if s_data:
            return s_data

    return None


# ==============================================================================
# Adapted SAFTE Biomathematical Model
# ==============================================================================

def calculate_safte_effectiveness(
    sleep_data: SleepQualityData,
    hour: float,
    wake_time_hour: Optional[float] = None,
    target_sleep_minutes: float = 480.0,
    rc_capacity: float = 2880.0
) -> float:
    """
    Calculates cognitive effectiveness E(t) using the SAFTE model
    adapted for wearable sleep metrics:

      E(t) = 100 * (R(t) / R_c) + C(t) - I(t)

    Where:
      - R(t): Homeostatic sleep reservoir, replenished by sleep quality & duration,
              and depleted by 30 units/hour during wakefulness.
      - C(t): Circadian oscillator (24h primary harmonic + 12h secondary harmonic).
      - I(t): Sleep inertia penalty immediately following awakening.
    """
    # 1. Wake hour determination
    if wake_time_hour is None:
        wake_time_hour = sleep_data.wake_time.hour + sleep_data.wake_time.minute / 60.0

    # 2. Quality factor from wearable data (sleep score, duration, stages, efficiency)
    actual_sleep_min = max(60.0, float(sleep_data.total_sleep_minutes))
    score_factor = max(0.1, min(1.0, float(sleep_data.sleep_score) / 100.0))
    duration_factor = min(1.15, max(0.2, actual_sleep_min / target_sleep_minutes))

    stage_factor = 1.0
    if sleep_data.stages and sleep_data.stages.total_sleep_minutes > 0:
        deep = sleep_data.stages.deep_minutes
        rem = sleep_data.stages.rem_minutes
        light = sleep_data.stages.light_minutes
        total = sleep_data.stages.total_sleep_minutes
        # Restorative weighting
        weighted_val = (1.35 * deep + 1.15 * rem + 0.85 * light) / total
        stage_factor = max(0.7, min(1.2, weighted_val))

    eff = sleep_data.sleep_efficiency if sleep_data.sleep_efficiency <= 1.0 else sleep_data.sleep_efficiency / 100.0
    eff_factor = max(0.7, min(1.1, eff / 0.85))

    # Overall sleep replenishment quality Q
    q_replenish = (0.45 * score_factor + 0.25 * duration_factor + 0.15 * stage_factor + 0.15 * eff_factor)

    # Initial reservoir at awakening (R0)
    # A full 100-score, 8-hour sleep replenishes to 100% capacity (rc_capacity)
    r_initial = rc_capacity * min(1.10, max(0.30, q_replenish))

    # 3. Homeostatic Depletion during wakefulness
    # Time awake since waking up
    delta_t = (hour - wake_time_hour) % 24.0
    depletion_rate_per_hour = 30.0  # 0.5 units/minute in SAFTE
    r_current = max(0.0, r_initial - depletion_rate_per_hour * delta_t)

    homeostatic_term = 100.0 * (r_current / rc_capacity)

    # 4. Circadian Oscillator C(t)
    # Primary peak p = 17.5h (5:30 PM), secondary harmonic p' = 14.5h (mid-afternoon dip), beta = 0.5
    phi_1 = 17.5
    phi_2 = 14.5
    c_raw = math.cos(2.0 * math.pi * (hour - phi_1) / 24.0) + 0.5 * math.cos(4.0 * math.pi * (hour - phi_2) / 24.0)

    # Sleep debt widens circadian amplitude
    sleep_debt = max(0.0, (rc_capacity - r_current) / rc_capacity)
    circadian_term = c_raw * (8.0 + 4.0 * sleep_debt)

    # 5. Sleep Inertia I(t)
    # Dissipates exponentially within 1.5 - 2 hours after waking up
    inertia_term = 0.0
    if 0.0 <= delta_t <= 2.5:
        i_max = 14.0 * (1.0 + 0.5 * sleep_debt)  # higher inertia if sleep deprived
        decay_constant = 0.6  # hours
        inertia_term = i_max * math.exp(-delta_t / decay_constant)

    # 6. Combined Task Effectiveness E(t)
    effectiveness = homeostatic_term + circadian_term - inertia_term
    return max(15.0, min(120.0, effectiveness))


def safte_scaling_factor_for_slot(
    sleep_data: SleepQualityData,
    slot_idx: int,
    baseline_nominal_effectiveness: float = 100.0,
    target_sleep_minutes: float = 480.0
) -> float:
    """
    Computes the multiplier factor for a 15-minute slot (0..95) from the SAFTE model.
    A well-rested baseline yields ~1.0. Poor sleep yields < 1.0 (e.g. 0.6 - 0.85).
    """
    hour = (slot_idx * 15.0) / 60.0
    effectiveness = calculate_safte_effectiveness(
        sleep_data=sleep_data,
        hour=hour,
        target_sleep_minutes=target_sleep_minutes
    )
    # Scaling factor relative to nominal 100% effectiveness
    raw_factor = effectiveness / baseline_nominal_effectiveness
    return max(0.20, min(1.30, raw_factor))


def scale_productivity_curve_with_safte(
    productivity_curve_data: Any,
    sleep_data: Union[SleepQualityData, List[SleepQualityData], Dict[Any, SleepQualityData]],
    target_sleep_minutes: float = 480.0,
    baseline_nominal_effectiveness: float = 100.0
) -> Any:
    """
    Scales a productivity curve using the adapted SAFTE equation based on sleep data.

    Supports:
      - 2D list: curve[day][slot] (7 days x 96 slots)
      - 1D list: curve[slot] (96 slots)
      - Single SleepQualityData (applied across all days)
      - List or Dict of SleepQualityData mapped by day index (0..6)
    """
    if sleep_data is None:
        return productivity_curve_data

    # Helper to resolve sleep data for a given day
    def get_sleep_for_day(day_idx: int) -> Optional[SleepQualityData]:
        if isinstance(sleep_data, SleepQualityData):
            return sleep_data
        if isinstance(sleep_data, dict):
            return sleep_data.get(day_idx, sleep_data.get(str(day_idx)))
        if isinstance(sleep_data, (list, tuple)):
            if len(sleep_data) == 0:
                return None
            return sleep_data[day_idx % len(sleep_data)]
        return None

    # Case 1: 2D list curve[day][slot]
    if isinstance(productivity_curve_data, list) and len(productivity_curve_data) > 0 and isinstance(productivity_curve_data[0], list):
        scaled_2d = []
        for d_idx, day_slots in enumerate(productivity_curve_data):
            day_sleep = get_sleep_for_day(d_idx)
            scaled_day = []
            for s_idx, val in enumerate(day_slots):
                if day_sleep is not None:
                    factor = safte_scaling_factor_for_slot(
                        sleep_data=day_sleep,
                        slot_idx=s_idx,
                        baseline_nominal_effectiveness=baseline_nominal_effectiveness,
                        target_sleep_minutes=target_sleep_minutes
                    )
                    new_val = max(0.0, min(1.0, float(val) * factor))
                else:
                    new_val = float(val)
                scaled_day.append(round(new_val, 4))
            scaled_2d.append(scaled_day)
        return scaled_2d

    # Case 2: 1D list curve[slot] (96 slots)
    if isinstance(productivity_curve_data, list):
        default_sleep = get_sleep_for_day(0)
        scaled_1d = []
        for s_idx, val in enumerate(productivity_curve_data):
            if default_sleep is not None:
                factor = safte_scaling_factor_for_slot(
                    sleep_data=default_sleep,
                    slot_idx=s_idx,
                    baseline_nominal_effectiveness=baseline_nominal_effectiveness,
                    target_sleep_minutes=target_sleep_minutes
                )
                new_val = max(0.0, min(1.0, float(val) * factor))
            else:
                new_val = float(val)
            scaled_1d.append(round(new_val, 4))
        return scaled_1d

    return productivity_curve_data
