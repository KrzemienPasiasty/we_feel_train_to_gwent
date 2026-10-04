from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

from tag import Tag
from task import Task
from week_periods import DAYS_IN_WEEK, SLOT_MINUTES, SLOTS_PER_DAY, Weekday, WeeklySchedule
from .sleep_tracker import (
    SleepQualityData,
    SleepStageBreakdown,
    calculate_safte_effectiveness,
    download_garmin_sleep_data,
    download_samsung_sleep_data,
    download_sleep_quality_data,
    parse_garmin_sleep_data,
    parse_samsung_sleep_data,
    safte_scaling_factor_for_slot,
    scale_productivity_curve_with_safte,
)
from .physical_activity import (
    DEFAULT_ACTIVITY_TAGS,
    PhysicalActivityConfig,
    ScheduledActivity,
    calculate_activity_conditions_penalty,
    calculate_air_quality_slot_penalty,
    calculate_weather_slot_penalty,
    parse_physical_activities_from_weekly_schedule,
    parse_physical_activity,
)


# ==============================================================================
# Priority Multipliers for Penalties
# ==============================================================================

DEFAULT_PRIORITY_MULTIPLIERS: Dict[Any, float] = {
    1: 1.0,
    2: 1.5,
    3: 2.5,
    4: 4.0,
    "LOW": 1.0,
    "MEDIUM": 1.5,
    "HIGH": 2.5,
    "CRITICAL": 4.0,
}


def get_priority_multiplier(
    priority: Any,
    priority_multipliers: Optional[Dict[Any, float]] = None,
    default_multiplier: float = 1.0
) -> float:
    """
    Returns the penalty multiplier for a task based on its priority.

    Supports:
      - Integers (e.g. 1=LOW, 2=MEDIUM, 3=HIGH, 4=CRITICAL)
      - Strings (e.g. 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL', case-insensitive)
      - Custom dictionary overrides passed via `priority_multipliers`
      - Numeric fallbacks (using the numeric priority itself if > 0)
    """
    mapping = priority_multipliers if priority_multipliers is not None else DEFAULT_PRIORITY_MULTIPLIERS

    if priority is None:
        return default_multiplier

    # Direct key lookup
    if priority in mapping:
        return float(mapping[priority])

    # Case-insensitive string lookup
    if isinstance(priority, str):
        upper_p = priority.strip().upper()
        if upper_p in mapping:
            return float(mapping[upper_p])

    # Numeric fallback
    if isinstance(priority, (int, float)):
        return max(0.1, float(priority))

    return default_multiplier


# ==============================================================================
# Meal Configuration & Representation
# ==============================================================================

@dataclass
class ScheduledMeal:
    """Represents a scheduled meal block in the weekly schedule."""
    meal_index: int               # 0, 1, 2...
    name: str                     # "Breakfast", "Lunch", "Dinner", etc.
    day: int                      # 0..6 (Monday..Sunday)
    start_slot: int               # 0..95
    end_slot: int                 # start_slot + slots_needed
    start_time: time
    end_time: time
    duration_minutes: int
    tag: Optional[Tag] = None
    color: str = "#FF9800"

    def to_calendar_dict(self) -> Dict[str, Any]:
        """Formats the scheduled meal for WeeklyCalendarFrame."""
        return {
            "id": -(1000 + self.day * 10 + self.meal_index),
            "title": f"Meal: {self.name}",
            "day": self.day,
            "start_time": self.start_time,
            "duration_minutes": self.duration_minutes,
            "color": self.color,
            "priority": "HIGH",
            "is_meal": True
        }


@dataclass
class MealConfig:
    """Configuration for meal scheduling and spacing limits."""
    meals_per_day: int = 3
    meal_duration_minutes: int = 30
    min_time_between_meals_minutes: int = 180  # 3 hours minimum
    max_time_between_meals_minutes: int = 300  # 5 hours maximum
    earliest_meal_time: time = time(7, 0)
    latest_meal_time: time = time(21, 30)
    meal_spacing_penalty_per_minute: float = 0.5   # 30 pts per hour of spacing violation
    missing_meal_penalty: float = 100.0             # Penalty per missing meal
    meal_tag_names: Optional[List[str]] = None
    meal_color: str = "#FF9800"
    active_meal_days: Optional[List[int]] = None


# ==============================================================================
# Configuration
# ==============================================================================

@dataclass
class OptimizationConfig:
    """Holds all hyper-parameters and flags for the genetic optimizer."""
    population_size: int = 20                 # Size of the population
    reproduction_threshold: float = 0.75      # Only >= 75% of previous best score can reproduce
    convergence_threshold: float = 0.01       # Score difference threshold to consider convergence
    patience: int = 3                         # Consecutive generations below threshold before stopping
    max_generations: int = 50                 # Safeguard upper limit on generations
    mutation_chance: float = 0.15             # Probability of individual undergoing mutation
    elitism_count: int = 2                    # Direct survivors from previous generation
    default_task_duration_minutes: int = 60   # Fallback duration if task.time is None
    strict_deadline_cutoff: bool = False      # If True, discard/penalize schedules with missed deadlines heavily
    only_tagged_slots: bool = False           # If True, schedule tasks only into explicitly tagged slots
    higher_is_better: bool = True             # Fitness orientation
    tournament_size: int = 3                  # Size for tournament selection
    random_seed: Optional[int] = None         # Random seed for reproducibility
    reference_date: Optional[datetime] = None # Monday date corresponding to day 0 of the weekly schedule
    min_schedule_datetime: Optional[datetime] = None # Cutoff datetime; slots before this time are rejected as past
    earliest_task_time: time = time(6, 0)     # Earliest daytime hour to schedule tasks
    latest_task_time: time = time(23, 0)      # Latest daytime hour to schedule tasks
    unassigned_task_penalty: float = 50.0     # Base penalty per unassigned task
    priority_multipliers: Optional[Dict[Any, float]] = None  # Multiplier per task priority
    penalize_tag_mismatch: bool = True        # Exponential penalty for scheduling tasks into slots with alien tags
    tag_mismatch_base_penalty: float = 10.0   # Base penalty factor for tag mismatch
    tag_mismatch_growth_rate: float = 1.5     # Exponential base (growth rate per overlap unit)
    tag_mismatch_scale_unit: float = 1.0      # Number of slots (or units) per exponential step
    tag_mismatch_scale_by_priority: bool = True  # Whether to multiply tag mismatch penalty by task priority

    # Tag prioritization settings (specific tag assigned firstly to tasks with same tag)
    assign_same_tag_first: bool = True        # If True, tasks with matching tags are assigned first to specific tagged slots
    strict_tag_reservation: bool = True       # If True, prevents non-matching tasks from occupying tagged slots while matching tasks remain unassigned
    matching_tag_bonus: float = 5.0           # Score bonus when placing a task into a slot matching its own tag

    # Meal scheduling settings
    enable_meals: bool = True
    meals_per_day: int = 3
    meal_duration_minutes: int = 30
    min_time_between_meals_minutes: int = 180  # 3 hours
    max_time_between_meals_minutes: int = 300  # 5 hours
    earliest_meal_time: time = time(7, 0)
    latest_meal_time: time = time(21, 30)
    meal_spacing_penalty_per_minute: float = 0.5
    missing_meal_penalty: float = 100.0
    meal_tag_names: Optional[List[str]] = None
    meal_color: str = "#FF9800"
    active_meal_days: Optional[List[int]] = None
    meal_config: Optional[MealConfig] = None

    # Physical activity & weather / air quality settings
    enable_physical_activity: bool = False
    activity_duration_minutes: int = 60
    activities_per_week: int = 3
    weather_air_forecast: Optional[Any] = None
    weather_forecast: Optional[Any] = None
    air_quality_forecast: Optional[Any] = None
    activity_weather_weight: float = 1.0
    activity_air_quality_weight: float = 1.0
    physical_activity_config: Optional[PhysicalActivityConfig] = None

    # Sleep data & SAFTE scaling settings
    sleep_data: Optional[Any] = None
    enable_safte_scaling: bool = True
    safte_target_sleep_minutes: float = 480.0
    safte_baseline_effectiveness: float = 100.0

    def __post_init__(self):
        if self.meal_config is not None:
            self.meals_per_day = self.meal_config.meals_per_day
            self.meal_duration_minutes = self.meal_config.meal_duration_minutes
            self.min_time_between_meals_minutes = self.meal_config.min_time_between_meals_minutes
            self.max_time_between_meals_minutes = self.meal_config.max_time_between_meals_minutes
            self.earliest_meal_time = self.meal_config.earliest_meal_time
            self.latest_meal_time = self.meal_config.latest_meal_time
            self.meal_spacing_penalty_per_minute = self.meal_config.meal_spacing_penalty_per_minute
            self.missing_meal_penalty = self.meal_config.missing_meal_penalty
            self.meal_tag_names = self.meal_config.meal_tag_names
            self.meal_color = self.meal_config.meal_color
            self.active_meal_days = self.meal_config.active_meal_days

        if self.physical_activity_config is not None:
            self.enable_physical_activity = True
            self.activity_duration_minutes = self.physical_activity_config.duration_minutes
            self.activities_per_week = self.physical_activity_config.sessions_per_week
            self.activity_weather_weight = self.physical_activity_config.weather_weight
            self.activity_air_quality_weight = self.physical_activity_config.air_quality_weight


# ==============================================================================
# Productivity Curve Representation
# ==============================================================================

class ProductivityCurve:
    """
    Wraps productivity data across days and slots.
    Supports:
      - 2D matrix / nested list: curve[day][slot]
      - 1D list of length 96 (replicated across each day)
      - Dictionary with day keys
      - Generic callable fn(day: int, slot: int) -> float
    """

    def __init__(self, data: Any):
        self._data = data

    def get_value(self, day: int, slot: int) -> float:
        if callable(self._data):
            return float(self._data(day, slot))

        if isinstance(self._data, (list, tuple)):
            if len(self._data) == 0:
                return 0.5

            # 2D list: 7 days x 96 slots
            if isinstance(self._data[0], (list, tuple)):
                d_idx = day % len(self._data)
                s_idx = slot % len(self._data[d_idx])
                return float(self._data[d_idx][s_idx])
            else:
                # 1D list: standard daily curve across 96 slots
                s_idx = slot % len(self._data)
                return float(self._data[s_idx])

        if isinstance(self._data, dict):
            # Keyed by day integer or string
            day_data = self._data.get(day, self._data.get(str(day)))
            if day_data is not None:
                if isinstance(day_data, (list, tuple)):
                    return float(day_data[slot % len(day_data)])
                elif callable(day_data):
                    return float(day_data(slot))
                return float(day_data)
            return 0.5

        return 0.5

    def apply_safte_scaling(
        self,
        sleep_data: Any,
        target_sleep_minutes: float = 480.0,
        baseline_nominal_effectiveness: float = 100.0
    ) -> None:
        """Scales current productivity curve using the adapted SAFTE equation."""
        self._data = scale_productivity_curve_with_safte(
            self._data,
            sleep_data,
            target_sleep_minutes=target_sleep_minutes,
            baseline_nominal_effectiveness=baseline_nominal_effectiveness
        )


# ==============================================================================
# Schedule Representation & Decoding
# ==============================================================================

@dataclass
class ScheduledTask:
    """Represents a scheduled instance of a task."""
    task: Task
    day: int                  # 0..6 (Monday..Sunday)
    start_slot: int           # 0..95
    end_slot: int             # start_slot + slots_needed
    start_time: time
    end_time: time
    duration_minutes: int
    matched_tags: List[Tag] = field(default_factory=list)
    scheduled_datetime: Optional[datetime] = None


class Schedule:
    """
    Decoded schedule containing concrete assignments of tasks, meals, and
    physical activities to days and slots.
    """

    def __init__(self, weekly_schedule: WeeklySchedule):
        self.weekly_schedule = weekly_schedule
        self.assignments: List[ScheduledTask] = []
        self.meals: List[ScheduledMeal] = []
        self.activities: List[ScheduledActivity] = []
        self.unassigned_tasks: List[Task] = []
        self.task_assignments: Dict[int, ScheduledTask] = {}
        # grid[day][slot] = task_id, negative ID for meal/activity, or None
        self.grid: List[List[Optional[int]]] = [
            [None for _ in range(SLOTS_PER_DAY)] for _ in range(DAYS_IN_WEEK)
        ]

    def add_assignment(self, scheduled: ScheduledTask) -> None:
        self.assignments.append(scheduled)
        self.task_assignments[scheduled.task.id] = scheduled
        for s in range(scheduled.start_slot, scheduled.end_slot):
            self.grid[scheduled.day][s] = scheduled.task.id

    def add_meal(self, meal: ScheduledMeal) -> None:
        self.meals.append(meal)
        meal_id = -(1000 + meal.day * 10 + meal.meal_index)
        for s in range(meal.start_slot, meal.end_slot):
            self.grid[meal.day][s] = meal_id

    def get_meals_for_day(self, day: int) -> List[ScheduledMeal]:
        day_meals = [m for m in self.meals if m.day == day]
        day_meals.sort(key=lambda m: m.start_slot)
        return day_meals

    def add_activity(self, activity: ScheduledActivity) -> None:
        self.activities.append(activity)
        act_id = -(2000 + activity.day * 10 + activity.activity_index)
        for s in range(activity.start_slot, activity.end_slot):
            self.grid[activity.day][s] = act_id

    def get_activities_for_day(self, day: int) -> List[ScheduledActivity]:
        day_acts = [a for a in self.activities if a.day == day]
        day_acts.sort(key=lambda a: a.start_slot)
        return day_acts

    def is_slot_free(self, day: int, slot: int) -> bool:
        return self.grid[day][slot] is None

    def is_window_free(self, day: int, start_slot: int, end_slot: int) -> bool:
        if end_slot > SLOTS_PER_DAY:
            return False
        return all(self.grid[day][s] is None for s in range(start_slot, end_slot))

    def to_calendar_dicts(
        self,
        include_meals: bool = True,
        include_activities: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Converts scheduled tasks, meals, and physical activities to the dictionary
        format expected by WeeklyCalendarFrame.set_tasks(...) in calender.py.
        """
        results = []
        for st in self.assignments:
            # Color resolution
            color = "#1E88E5"
            if st.matched_tags and hasattr(st.matched_tags[0], "color"):
                raw_color = st.matched_tags[0].color
                if isinstance(raw_color, (tuple, list)) and len(raw_color) == 3:
                    color = f"#{raw_color[0]:02x}{raw_color[1]:02x}{raw_color[2]:02x}"
                elif isinstance(raw_color, str):
                    color = raw_color
            elif st.task.tags and hasattr(st.task.tags[0], "color"):
                raw_color = st.task.tags[0].color
                if isinstance(raw_color, (tuple, list)) and len(raw_color) == 3:
                    color = f"#{raw_color[0]:02x}{raw_color[1]:02x}{raw_color[2]:02x}"
                elif isinstance(raw_color, str):
                    color = raw_color

            # Priority label resolution
            p = st.task.priority
            priority_map = {1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}
            priority_str = priority_map.get(p, "MEDIUM") if isinstance(p, int) else str(p or "MEDIUM")

            title = st.task.description.split("\n")[0] if st.task.description else f"Task {st.task.id}"

            results.append({
                "id": st.task.id,
                "title": title,
                "day": st.day,
                "start_time": st.start_time,
                "duration_minutes": st.duration_minutes,
                "color": color,
                "priority": priority_str,
                "task": st.task
            })

        if include_meals:
            for m in self.meals:
                results.append(m.to_calendar_dict())

        if include_activities:
            for a in self.activities:
                results.append(a.to_calendar_dict())

        return results


# ==============================================================================
# Helper Utilities
# ==============================================================================

def slot_to_time(slot_idx: int) -> time:
    minutes = slot_idx * SLOT_MINUTES
    return time(hour=(minutes // 60) % 24, minute=minutes % 60)


def time_to_slot(t: time) -> int:
    return (t.hour * 60 + t.minute) // SLOT_MINUTES


def parse_deadline_datetime(val: Any) -> Optional[datetime]:
    """Parse a deadline into the local, timezone-naive clock used by schedules.

    Integrations commonly provide UTC-aware timestamps, while calendar slots are
    represented as local naive datetimes. Convert aware deadlines to local time
    before dropping the timezone so comparisons use a consistent clock.
    """
    def local_naive(value: datetime) -> datetime:
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone().replace(tzinfo=None)
        return value

    if val is None:
        return None
    if isinstance(val, datetime):
        return local_naive(val)
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return local_naive(datetime.fromisoformat(s.replace("Z", "+00:00")))
        except Exception:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    return datetime.strptime(s, fmt)
                except Exception:
                    pass
    return None


def get_task_duration_minutes(task: Task, default_minutes: int = 60) -> int:
    """Extracts duration in minutes from task.time or fallback attribute."""
    if task.time is not None:
        if isinstance(task.time, (int, float)):
            return max(15, int(task.time))
        if isinstance(task.time, timedelta):
            return max(15, int(task.time.total_seconds() // 60))
        if isinstance(task.time, time):
            return max(15, task.time.hour * 60 + task.time.minute)
        if isinstance(task.time, datetime):
            return max(15, task.time.hour * 60 + task.time.minute)
        if isinstance(task.time, str):
            s = task.time.strip().lower()
            if s:
                if "h" in s:
                    try:
                        parts = s.split("h")
                        hours = float(parts[0].strip())
                        mins = float(parts[1].replace("m", "").strip()) if len(parts) > 1 and parts[1].strip() else 0
                        return max(15, int(hours * 60 + mins))
                    except Exception:
                        pass
                if ":" in s:
                    try:
                        parts = s.split(":")
                        if len(parts) >= 2:
                            return max(15, int(parts[0]) * 60 + int(parts[1]))
                    except Exception:
                        pass
                try:
                    val = float(s)
                    if val <= 12:
                        return max(15, int(val * 60))
                    return max(15, int(val))
                except Exception:
                    pass
    return default_minutes


def tag_identifiers(tags: Optional[Iterable[Any]]) -> set:
    """Returns normalized set of string representations/identifiers for tags."""
    if not tags:
        return set()
    result = set()
    for t in tags:
        if hasattr(t, "title") and t.title:
            result.add(str(t.title).strip().lower())
        elif hasattr(t, "name") and t.name:
            result.add(str(t.name).strip().lower())
        else:
            result.add(str(t).strip().lower())
    return result


def match_tags(task_tags: List[Tag], slot_tags: List[Tag]) -> Tuple[bool, List[Tag]]:
    """Checks whether task tags intersect with slot tags."""
    if not task_tags:
        return True, slot_tags

    task_set = tag_identifiers(task_tags)
    matching = []
    for st in slot_tags:
        s_id = tag_identifiers([st])
        if s_id & task_set:
            matching.append(st)

    return (len(matching) > 0), matching


def calculate_task_tag_mismatch_overlap(
    scheduled_task: ScheduledTask,
    weekly_schedule: WeeklySchedule
) -> int:
    """
    Returns the number of 15-minute slots in which the scheduled task
    overlaps with a tag other than one from its own list (e.g. sleeping period).
    """
    task_tag_ids = tag_identifiers(scheduled_task.task.tags)
    mismatched_slots = 0
    day = scheduled_task.day

    for slot_idx in range(scheduled_task.start_slot, scheduled_task.end_slot):
        slot_tags = weekly_schedule._slots[day][slot_idx]
        if not slot_tags:
            continue
        # Check if slot contains any tag other than one in task tags
        alien_tags = [st for st in slot_tags if not (tag_identifiers([st]) & task_tag_ids)]
        if alien_tags:
            mismatched_slots += 1

    return mismatched_slots


def calculate_tag_mismatch_penalty(
    schedule: Schedule,
    base_penalty: float = 10.0,
    growth_rate: float = 1.5,
    scale_unit: float = 1.0,
    overlap_unit: str = "slots",
    scale_by_priority: bool = True,
    priority_multipliers: Optional[Dict[Any, float]] = None
) -> float:
    """
    Calculates exponential penalty for tasks assigned to time slots with tags
    other than their own (e.g. assigning a task for a sleeping period).
    The penalty grows exponentially with the overlap size:
      exponent = overlap / scale_unit
      penalty = base_penalty * (growth_rate ** exponent - 1) * priority_multiplier
    """
    total_penalty = 0.0
    safe_growth = max(1.001, float(growth_rate))
    safe_scale = max(1e-4, float(scale_unit))

    for st in schedule.assignments:
        mismatched_slots = calculate_task_tag_mismatch_overlap(st, schedule.weekly_schedule)
        if mismatched_slots <= 0:
            continue

        if overlap_unit.lower() == "hours":
            overlap_val = mismatched_slots * (SLOT_MINUTES / 60.0)
        elif overlap_unit.lower() == "minutes":
            overlap_val = float(mismatched_slots * SLOT_MINUTES)
        else:  # "slots"
            overlap_val = float(mismatched_slots)

        exponent = overlap_val / safe_scale
        task_penalty = base_penalty * (math.pow(safe_growth, exponent) - 1.0)

        if scale_by_priority:
            task_penalty *= get_priority_multiplier(st.task.priority, priority_multipliers)

        total_penalty += task_penalty

    return total_penalty


def task_finish_datetime(
    day: int,
    end_slot: int,
    reference_date: Optional[datetime]
) -> Optional[datetime]:
    """Computes completion datetime given schedule day (0..6) and slot."""
    if not reference_date:
        return None
    # Day 0 is reference_date (Monday)
    date_day = reference_date + timedelta(days=day)
    t = slot_to_time(end_slot)
    return datetime.combine(date_day, t)


# ==============================================================================
# Meal Parsing, Placement & Spacing Penalty
# ==============================================================================

def parse_meals_from_weekly_schedule(
    weekly_schedule: WeeklySchedule,
    meal_tag_names: Optional[List[str]] = None
) -> List[ScheduledMeal]:
    """
    Scans WeeklySchedule for slots tagged with meal/food tags (e.g. 'Meal', 'Lunch', etc.)
    and groups consecutive slots into ScheduledMeal instances.
    """
    if meal_tag_names is None:
        meal_tag_names = ["meal", "food", "breakfast", "lunch", "dinner", "supper", "posiłek", "jedzenie", "obiad", "śniadanie", "kolacja"]

    tag_set = {t.lower() for t in meal_tag_names}
    parsed_meals: List[ScheduledMeal] = []

    for day in range(DAYS_IN_WEEK):
        in_meal = False
        meal_start = 0
        meal_tags: List[Tag] = []

        for slot in range(SLOTS_PER_DAY):
            slot_tags = weekly_schedule._slots[day][slot]
            has_meal_tag = any(
                str(getattr(st, "title", st)).strip().lower() in tag_set
                for st in slot_tags
            )

            if has_meal_tag and not in_meal:
                in_meal = True
                meal_start = slot
                meal_tags = slot_tags
            elif not has_meal_tag and in_meal:
                in_meal = False
                duration = (slot - meal_start) * SLOT_MINUTES
                meal_name = "Meal"
                for st in meal_tags:
                    title = str(getattr(st, "title", st)).strip()
                    if title.lower() in tag_set:
                        meal_name = title
                        break

                parsed_meals.append(ScheduledMeal(
                    meal_index=len([m for m in parsed_meals if m.day == day]),
                    name=meal_name,
                    day=day,
                    start_slot=meal_start,
                    end_slot=slot,
                    start_time=slot_to_time(meal_start),
                    end_time=slot_to_time(slot),
                    duration_minutes=duration
                ))
                meal_tags = []

        if in_meal:
            duration = (SLOTS_PER_DAY - meal_start) * SLOT_MINUTES
            meal_name = "Meal"
            for st in meal_tags:
                title = str(getattr(st, "title", st)).strip()
                if title.lower() in tag_set:
                    meal_name = title
                    break
            parsed_meals.append(ScheduledMeal(
                meal_index=len([m for m in parsed_meals if m.day == day]),
                name=meal_name,
                day=day,
                start_slot=meal_start,
                end_slot=SLOTS_PER_DAY,
                start_time=slot_to_time(meal_start),
                end_time=time(23, 59),
                duration_minutes=duration
            ))

    return parsed_meals


def populate_meals_for_schedule(
    schedule: Schedule,
    weekly_schedule: WeeklySchedule,
    config: OptimizationConfig,
    meal_offsets: Optional[List[int]] = None
) -> None:
    """
    Parses meals from WeeklySchedule and dynamically places scheduled meals
    for active days up to config.meals_per_day.
    Each placed meal marks its occupied slots as reserved in schedule.grid so
    tasks will not collide with meal periods.
    """
    if not getattr(config, "enable_meals", True) or getattr(config, "meals_per_day", 0) <= 0:
        return

    # 1. Parse existing meals from weekly schedule
    parsed_existing = parse_meals_from_weekly_schedule(
        weekly_schedule,
        getattr(config, "meal_tag_names", None)
    )
    for m in parsed_existing:
        schedule.add_meal(m)

    # 2. Determine active days for meal placement
    active_days = getattr(config, "active_meal_days", None)
    if active_days is None:
        active_days = list(range(DAYS_IN_WEEK))

    meals_needed = getattr(config, "meals_per_day", 3)
    duration_minutes = getattr(config, "meal_duration_minutes", 30)
    duration_s = max(1, math.ceil(duration_minutes / SLOT_MINUTES))

    earliest_t = getattr(config, "earliest_meal_time", time(7, 0))
    latest_t = getattr(config, "latest_meal_time", time(21, 30))
    earliest_s = time_to_slot(earliest_t)
    latest_s = time_to_slot(latest_t)

    default_names = ["Breakfast", "Lunch", "Dinner", "Snack", "Supper"]

    ref_dt = getattr(config, "reference_date", None)
    min_dt = getattr(config, "min_schedule_datetime", None)

    for day in active_days:
        if ref_dt and min_dt:
            day_latest_dt = ref_dt + timedelta(days=day, hours=latest_t.hour, minutes=latest_t.minute)
            if day_latest_dt < min_dt:
                continue

        existing_on_day = schedule.get_meals_for_day(day)
        if len(existing_on_day) >= meals_needed:
            continue

        for k in range(len(existing_on_day), meals_needed):
            if meals_needed > 1:
                nominal_s = earliest_s + int(round(k * (latest_s - duration_s - earliest_s) / (meals_needed - 1)))
            else:
                nominal_s = (earliest_s + latest_s) // 2

            if meal_offsets and k < len(meal_offsets):
                nominal_s += meal_offsets[k] // SLOT_MINUTES

            nominal_s = max(earliest_s, min(latest_s - duration_s, nominal_s))

            # Find nearest free window of duration_s slots around nominal_s
            best_s = None
            for offset in range(SLOTS_PER_DAY):
                for s_cand in [nominal_s + offset, nominal_s - offset]:
                    if earliest_s <= s_cand <= latest_s - duration_s:
                        if ref_dt and min_dt:
                            meal_start_dt = ref_dt + timedelta(days=day, minutes=s_cand * SLOT_MINUTES)
                            if meal_start_dt < min_dt:
                                continue
                        if schedule.is_window_free(day, s_cand, s_cand + duration_s):
                            best_s = s_cand
                            break
                if best_s is not None:
                    break

            if best_s is not None:
                schedule.add_meal(ScheduledMeal(
                    meal_index=k,
                    name=default_names[k % len(default_names)],
                    day=day,
                    start_slot=best_s,
                    end_slot=best_s + duration_s,
                    start_time=slot_to_time(best_s),
                    end_time=slot_to_time(best_s + duration_s),
                    duration_minutes=duration_s * SLOT_MINUTES,
                    color=getattr(config, "meal_color", "#FF9800")
                ))


def calculate_meal_spacing_penalty(
    schedule: Schedule,
    min_time_between_meals_minutes: int = 180,
    max_time_between_meals_minutes: int = 300,
    penalty_per_minute: float = 0.5,
    missing_meal_penalty: float = 100.0,
    expected_meals_per_day: int = 3,
    active_days: Optional[List[int]] = None
) -> float:
    """
    Calculates penalty for periods between meals that are longer or shorter
    than the set limits, as well as missing meals.
    """
    if expected_meals_per_day <= 0:
        return 0.0

    if active_days is None:
        # Check days where tasks are assigned or meals exist
        active_days = list(set(st.day for st in schedule.assignments) | set(m.day for m in schedule.meals))
        if not active_days:
            return 0.0

    total_penalty = 0.0

    for day in active_days:
        day_meals = schedule.get_meals_for_day(day)

        if len(day_meals) < expected_meals_per_day:
            missing = expected_meals_per_day - len(day_meals)
            total_penalty += missing * missing_meal_penalty

        if len(day_meals) >= 2:
            for i in range(len(day_meals) - 1):
                m1 = day_meals[i]
                m2 = day_meals[i + 1]
                gap_minutes = (m2.start_slot - m1.end_slot) * SLOT_MINUTES

                if gap_minutes < min_time_between_meals_minutes:
                    shortfall = min_time_between_meals_minutes - gap_minutes
                    total_penalty += shortfall * penalty_per_minute

                if gap_minutes > max_time_between_meals_minutes:
                    excess = gap_minutes - max_time_between_meals_minutes
                    total_penalty += excess * penalty_per_minute

    return total_penalty


# ==============================================================================
# Schedule Decoder
# ==============================================================================

def decode_permutation_to_schedule(
    permutation: List[int],
    tasks: List[Task],
    weekly_schedule: WeeklySchedule,
    productivity_curve: ProductivityCurve,
    config: OptimizationConfig,
    placement_bias: str = "balanced",  # "earliest", "productivity", "balanced"
    meal_offsets: Optional[List[int]] = None
) -> Schedule:
    """
    Decodes an ordered permutation of task indices into concrete time slots
    in the WeeklySchedule, parsing and respecting meal times, physical activities,
    and tag constraints.

    Enforces that to specific tagged slots, tasks with the same tag are assigned firstly.
    """
    schedule = Schedule(weekly_schedule)

    # 1. Parse and place meals into the schedule grid first
    if getattr(config, "enable_meals", True) and getattr(config, "meals_per_day", 0) > 0:
        populate_meals_for_schedule(
            schedule=schedule,
            weekly_schedule=weekly_schedule,
            config=config,
            meal_offsets=meal_offsets
        )

    # 2. Parse and place physical activities if enabled
    if getattr(config, "enable_physical_activity", False):
        w_fc = getattr(config, "weather_air_forecast", None) or getattr(config, "weather_forecast", None)
        aq_fc = getattr(config, "air_quality_forecast", None)
        parse_physical_activity(
            duration_minutes=getattr(config, "activity_duration_minutes", 60),
            weekly_schedule=weekly_schedule,
            weather_forecast=w_fc,
            air_quality_forecast=aq_fc,
            sessions_per_week=getattr(config, "activities_per_week", 3),
            schedule=schedule,
            config=getattr(config, "physical_activity_config", None),
            reference_date=getattr(config, "reference_date", None),
            min_schedule_datetime=getattr(config, "min_schedule_datetime", None),
            weather_weight=getattr(config, "activity_weather_weight", 1.0),
            air_quality_weight=getattr(config, "activity_air_quality_weight", 1.0)
        )

    # 3. Determine task execution order: assign tasks matching schedule tags first
    assign_same_tag_first = getattr(config, "assign_same_tag_first", True)
    strict_tag_reservation = getattr(config, "strict_tag_reservation", True)
    matching_tag_bonus = float(getattr(config, "matching_tag_bonus", 5.0))

    if assign_same_tag_first:
        # Determine all tag identifiers present in the weekly schedule
        sched_tag_ids = set()
        for d in range(DAYS_IN_WEEK):
            for s in range(SLOTS_PER_DAY):
                slot_tags = weekly_schedule._slots[d][s]
                if slot_tags:
                    sched_tag_ids.update(tag_identifiers(slot_tags))

        # Split permutation: tasks matching any schedule tag go first
        matching_tasks = []
        other_tasks = []
        for idx in permutation:
            t = tasks[idx]
            if tag_identifiers(t.tags) & sched_tag_ids:
                matching_tasks.append(idx)
            else:
                other_tasks.append(idx)
        task_execution_order = matching_tasks + other_tasks
    else:
        task_execution_order = list(permutation)

    remaining_unassigned_indices = list(task_execution_order)

    # 4. Place tasks around meals, activities, and reserved windows
    penalize_mismatch = getattr(config, "penalize_tag_mismatch", True)
    growth = max(1.001, float(getattr(config, "tag_mismatch_growth_rate", 1.5)))
    base_mismatch_p = float(getattr(config, "tag_mismatch_base_penalty", 10.0))
    scale_by_prio = getattr(config, "tag_mismatch_scale_by_priority", True)

    for task_idx in task_execution_order:
        remaining_unassigned_indices.remove(task_idx)
        task = tasks[task_idx]
        duration_minutes = get_task_duration_minutes(task, config.default_task_duration_minutes)
        slots_needed = max(1, math.ceil(duration_minutes / SLOT_MINUTES))

        best_day = None
        best_start = None
        best_end = None
        best_matched_tags: List[Tag] = []
        best_candidate_score = -float("inf")

        deadline_dt = parse_deadline_datetime(getattr(task, "deadline", None))
        focus_val = float(getattr(task, "focus", 5) or 5)
        # Normalize focus roughly to 0..1
        focus_norm = min(1.0, max(0.0, focus_val / 10.0 if focus_val <= 10 else focus_val / 100.0))
        task_tag_ids = tag_identifiers(task.tags)

        earliest_task_t = getattr(config, "earliest_task_time", time(6, 0))
        latest_task_t = getattr(config, "latest_task_time", time(23, 0))
        earliest_task_s = time_to_slot(earliest_task_t)
        latest_task_s = time_to_slot(latest_task_t)
        ref_dt = getattr(config, "reference_date", None)
        min_dt = getattr(config, "min_schedule_datetime", None)

        # Scan all available days and slot windows
        for day in range(DAYS_IN_WEEK):
            if ref_dt and min_dt:
                day_end_dt = ref_dt + timedelta(days=day, hours=latest_task_t.hour, minutes=latest_task_t.minute)
                if day_end_dt < min_dt:
                    continue

            # Check slots within the day
            for s in range(0, SLOTS_PER_DAY - slots_needed + 1):
                e = s + slots_needed

                in_daytime = (earliest_task_s <= s and e <= latest_task_s)
                if not in_daytime:
                    if not task_tag_ids:
                        continue
                    has_matching_tagged_slot = any(
                        bool(tag_identifiers(weekly_schedule._slots[day][slot_i]) & task_tag_ids)
                        for slot_i in range(s, e)
                    )
                    if not has_matching_tagged_slot:
                        continue

                if ref_dt and min_dt:
                    slot_start_dt = ref_dt + timedelta(days=day, minutes=s * SLOT_MINUTES)
                    if slot_start_dt < min_dt:
                        continue

                # Check window availability (meals, activities, and other tasks are marked as occupied)
                if not schedule.is_window_free(day, s, e):
                    continue

                # Inspect tag compatibility across the window
                window_slot_tags: List[Tag] = []
                all_have_tags = True
                strictly_compatible = True
                matched_window_tags: List[Tag] = []
                mismatched_slots = 0
                matched_slots_count = 0
                window_tag_ids = set()

                for slot_idx in range(s, e):
                    slot_tags = weekly_schedule._slots[day][slot_idx]
                    if not slot_tags:
                        all_have_tags = False
                    is_match, matched = match_tags(task.tags, slot_tags)
                    if is_match and task.tags:
                        matched_slots_count += 1
                    if not is_match and task.tags:
                        strictly_compatible = False
                    matched_window_tags.extend(matched)
                    window_slot_tags.extend(slot_tags)

                    if slot_tags:
                        slot_t_ids = tag_identifiers(slot_tags)
                        window_tag_ids.update(slot_t_ids)
                        # Count slots with alien tags (tags not belonging to the task)
                        alien_tags = [st for st in slot_tags if not (slot_t_ids & task_tag_ids)]
                        if alien_tags:
                            mismatched_slots += 1

                if config.only_tagged_slots and task_tag_ids and not all_have_tags:
                    continue

                # Enforce condition: to a specific tag, tasks with the same tag are assigned firstly
                has_matching_tag = bool(task_tag_ids & window_tag_ids)
                if assign_same_tag_first and strict_tag_reservation and window_tag_ids and not has_matching_tag:
                    # Check if there are other unassigned tasks that have this specific tag
                    other_matching_exist = any(
                        bool(tag_identifiers(tasks[rem_i].tags) & window_tag_ids)
                        for rem_i in remaining_unassigned_indices
                    )
                    if other_matching_exist:
                        # This tagged slot window is reserved for tasks that have this specific tag!
                        continue

                # Average productivity in window
                avg_prod = sum(productivity_curve.get_value(day, slot_i) for slot_i in range(s, e)) / slots_needed

                # Earliest time factor (normalized within week: 0 to 1)
                earliness = 1.0 - ((day * SLOTS_PER_DAY + s) / (DAYS_IN_WEEK * SLOTS_PER_DAY))

                # Productivity correlation factor (smaller absolute difference between focus and productivity)
                prod_match = 1.0 - abs(focus_norm - avg_prod)

                # Deadline compliance bonus / penalty
                deadline_factor = 0.0
                if deadline_dt and config.reference_date:
                    scheduled_end_dt = task_finish_datetime(day, e, config.reference_date)
                    if scheduled_end_dt:
                        diff_hours = (deadline_dt - scheduled_end_dt).total_seconds() / 3600.0
                        if diff_hours >= 0:
                            # Finishes before deadline: bonus scaled by margin (max +1.0)
                            deadline_factor = min(1.0, diff_hours / 24.0)
                        else:
                            # Misses deadline
                            deadline_factor = -abs(diff_hours) / 12.0

                if not task_tag_ids:
                    # Task has no tags: naturally prioritize assigning to time where no tag is found
                    if not window_tag_ids:
                        tag_bonus = matching_tag_bonus
                    else:
                        tag_bonus = 0.0
                else:
                    if matched_slots_count > 0:
                        # Bonus scales with the proportion of matching tagged slots in the window
                        tag_bonus = matching_tag_bonus * (matched_slots_count / slots_needed)
                    elif not window_tag_ids:
                        # Tagged task placed in untagged slot window (acceptable fallback)
                        tag_bonus = 0.25
                    elif strictly_compatible:
                        tag_bonus = 0.5
                    else:
                        tag_bonus = 0.0

                # Combine factors according to placement_bias
                if placement_bias == "earliest":
                    candidate_score = (
                        0.50 * earliness
                        + 0.35 * deadline_factor
                        + 0.15 * prod_match
                        + tag_bonus
                    )
                elif placement_bias == "productivity":
                    candidate_score = (
                        0.60 * prod_match
                        + 0.25 * deadline_factor
                        + 0.15 * earliness
                        + tag_bonus
                    )
                else:  # balanced
                    candidate_score = (
                        0.35 * prod_match
                        + 0.35 * deadline_factor
                        + 0.30 * earliness
                        + tag_bonus
                    )

                # Exponential penalty for alien tag overlap during candidate placement
                if penalize_mismatch and mismatched_slots > 0:
                    exp_penalty = base_mismatch_p * (math.pow(growth, mismatched_slots) - 1.0)
                    if scale_by_prio:
                        exp_penalty *= get_priority_multiplier(task.priority, config.priority_multipliers)
                    candidate_score -= exp_penalty

                if candidate_score > best_candidate_score:
                    best_candidate_score = candidate_score
                    best_day = day
                    best_start = s
                    best_end = e
                    best_matched_tags = matched_window_tags

        if best_day is not None and best_start is not None and best_end is not None:
            start_t = slot_to_time(best_start)
            end_t = slot_to_time(best_end)
            sched_dt = task_finish_datetime(best_day, best_end, config.reference_date)

            st = ScheduledTask(
                task=task,
                day=best_day,
                start_slot=best_start,
                end_slot=best_end,
                start_time=start_t,
                end_time=end_t,
                duration_minutes=duration_minutes,
                matched_tags=best_matched_tags,
                scheduled_datetime=sched_dt
            )
            schedule.add_assignment(st)
        else:
            schedule.unassigned_tasks.append(task)

    return schedule


# ==============================================================================
# Genetic Operators: PMX & Mutation
# ==============================================================================

def partially_mixed_crossover(parent1: List[int], parent2: List[int]) -> Tuple[List[int], List[int]]:
    """
    Partially Mapped Crossover (PMX) for permutation-encoded individuals.
    Ensures every offspring is a valid permutation without missing or duplicated genes.
    """
    size = len(parent1)
    if size < 2:
        return parent1.copy(), parent2.copy()

    cx1 = random.randint(0, size - 2)
    cx2 = random.randint(cx1 + 1, size - 1)

    child1 = [None] * size
    child2 = [None] * size

    # 1. Copy crossover segment from parent1 to child1, parent2 to child2
    child1[cx1:cx2 + 1] = parent1[cx1:cx2 + 1]
    child2[cx1:cx2 + 1] = parent2[cx1:cx2 + 1]

    # 2. Map items from parent2 segment into child1
    for i in range(cx1, cx2 + 1):
        gene = parent2[i]
        if gene not in child1[cx1:cx2 + 1]:
            curr_pos = i
            while cx1 <= curr_pos <= cx2:
                mapped_val = parent1[curr_pos]
                curr_pos = parent2.index(mapped_val)
            child1[curr_pos] = gene

    # 3. Fill remaining positions in child1 from parent2
    for i in range(size):
        if child1[i] is None:
            child1[i] = parent2[i]

    # Repeat for child2
    for i in range(cx1, cx2 + 1):
        gene = parent1[i]
        if gene not in child2[cx1:cx2 + 1]:
            curr_pos = i
            while cx1 <= curr_pos <= cx2:
                mapped_val = parent2[curr_pos]
                curr_pos = parent1.index(mapped_val)
            child2[curr_pos] = gene

    for i in range(size):
        if child2[i] is None:
            child2[i] = parent1[i]

    return child1, child2


def mutate_permutation(permutation: List[int], mutation_chance: float) -> List[int]:
    """
    Applies swap or inversion mutation on permutation with probability mutation_chance.
    """
    if len(permutation) < 2 or random.random() > mutation_chance:
        return permutation.copy()

    mutated = permutation.copy()
    op = random.choice(["swap", "invert"])

    if op == "swap":
        i, j = random.sample(range(len(mutated)), 2)
        mutated[i], mutated[j] = mutated[j], mutated[i]
    else:  # invert slice
        i, j = sorted(random.sample(range(len(mutated)), 2))
        mutated[i:j + 1] = reversed(mutated[i:j + 1])

    return mutated


# ==============================================================================
# Default Scoring Functions
# ==============================================================================

def default_deadline_score(schedule: Schedule, config: OptimizationConfig) -> float:
    """Calculates score based on meeting deadlines, unassigned tasks, tag mismatch, meal spacing, and weather/air."""
    score = 100.0
    for st in schedule.assignments:
        task_dl = parse_deadline_datetime(st.task.deadline)
        if task_dl:
            finish_dt = st.scheduled_datetime or task_finish_datetime(
                st.day, st.end_slot, config.reference_date
            )
            if finish_dt:
                if finish_dt <= task_dl:
                    score += 20.0
                else:
                    late_hours = (finish_dt - task_dl).total_seconds() / 3600.0
                    score -= late_hours * 10.0

    # Unassigned tasks penalty scaled by priority multiplier
    base_penalty = getattr(config, "unassigned_task_penalty", 50.0)
    for task in schedule.unassigned_tasks:
        mult = get_priority_multiplier(task.priority, config.priority_multipliers)
        score -= base_penalty * mult

    # Tag mismatch penalty (e.g. task assigned for sleeping period)
    if getattr(config, "penalize_tag_mismatch", True):
        tag_penalty = calculate_tag_mismatch_penalty(
            schedule=schedule,
            base_penalty=getattr(config, "tag_mismatch_base_penalty", 10.0),
            growth_rate=getattr(config, "tag_mismatch_growth_rate", 1.5),
            scale_unit=getattr(config, "tag_mismatch_scale_unit", 1.0),
            scale_by_priority=getattr(config, "tag_mismatch_scale_by_priority", True),
            priority_multipliers=config.priority_multipliers
        )
        score -= tag_penalty

    # Meal spacing penalty
    if getattr(config, "enable_meals", True) and getattr(config, "meals_per_day", 0) > 0:
        meal_penalty = calculate_meal_spacing_penalty(
            schedule=schedule,
            min_time_between_meals_minutes=getattr(config, "min_time_between_meals_minutes", 180),
            max_time_between_meals_minutes=getattr(config, "max_time_between_meals_minutes", 300),
            penalty_per_minute=getattr(config, "meal_spacing_penalty_per_minute", 0.5),
            missing_meal_penalty=getattr(config, "missing_meal_penalty", 100.0),
            expected_meals_per_day=getattr(config, "meals_per_day", 3),
            active_days=getattr(config, "active_meal_days", None)
        )
        score -= meal_penalty

    # Physical activity bad conditions penalties
    for act in schedule.activities:
        score -= (act.weather_penalty + act.air_quality_penalty)

    return score


def default_productivity_score(schedule: Schedule, productivity_curve: ProductivityCurve) -> float:
    """Calculates correlation of task focus with productivity curve."""
    if not schedule.assignments:
        return 0.0

    total_corr = 0.0
    for st in schedule.assignments:
        focus = float(getattr(st.task, "focus", 5) or 5)
        norm_focus = min(1.0, max(0.0, focus / 10.0 if focus <= 10 else focus / 100.0))

        slots = list(range(st.start_slot, st.end_slot))
        if slots:
            avg_prod = sum(productivity_curve.get_value(st.day, s) for s in slots) / len(slots)
            # Higher score when focus and productivity are closely aligned
            diff = abs(norm_focus - avg_prod)
            total_corr += (1.0 - diff) * 20.0

    total_corr -= len(schedule.unassigned_tasks) * 30.0
    return total_corr


def evaluate_schedule(
    schedule: Schedule,
    scoring_functions: Optional[Union[Callable[[Schedule], float], List[Callable[[Schedule], float]]]],
    productivity_curve: ProductivityCurve,
    config: OptimizationConfig
) -> float:
    """Evaluates a schedule against passed scoring function(s) or defaults."""
    if scoring_functions is None:
        d_score = default_deadline_score(schedule, config)
        p_score = default_productivity_score(schedule, productivity_curve)
        return 0.5 * d_score + 0.5 * p_score

    if callable(scoring_functions):
        return float(scoring_functions(schedule))

    if isinstance(scoring_functions, (list, tuple)):
        scores = [float(fn(schedule)) for fn in scoring_functions if callable(fn)]
        return sum(scores) / len(scores) if scores else 0.0

    return 0.0


# ==============================================================================
# Population Management
# ==============================================================================

@dataclass
class Individual:
    permutation: List[int]
    placement_bias: str
    schedule: Optional[Schedule] = None
    score: float = -float("inf")
    meal_offsets: List[int] = field(default_factory=list)


def create_initial_population(
    tasks: List[Task],
    weekly_schedule: WeeklySchedule,
    productivity_curve: ProductivityCurve,
    scoring_functions: Optional[Union[Callable[[Schedule], float], List[Callable[[Schedule], float]]]],
    config: OptimizationConfig
) -> List[Individual]:
    """
    Builds the 1st Population containing:
      - 1 schedule based only on shortest time to deadline first.
      - 1 schedule based only on highest task focus correlation with productivity curve.
      - (population_size - 2) schedules based on mixed permutations of both.
    """
    num_tasks = len(tasks)
    if num_tasks == 0:
        return []

    # 1. Deadline ranking (shortest deadline goes first)
    def deadline_key(idx: int) -> float:
        t = tasks[idx]
        dl = parse_deadline_datetime(getattr(t, "deadline", None))
        if dl is None:
            return float("inf")
        return dl.timestamp()

    deadline_order = sorted(range(num_tasks), key=deadline_key)

    # 2. Focus-Productivity correlation ranking
    def focus_key(idx: int) -> float:
        t = tasks[idx]
        return -float(getattr(t, "focus", 0) or 0)

    focus_order = sorted(range(num_tasks), key=focus_key)

    # Map rank positions
    deadline_rank_map = {idx: rank for rank, idx in enumerate(deadline_order)}
    focus_rank_map = {idx: rank for rank, idx in enumerate(focus_order)}

    population: List[Individual] = []
    meals_count = getattr(config, "meals_per_day", 3)

    # Pure deadline individual (standard meal placement)
    ind_deadline = Individual(
        permutation=deadline_order.copy(),
        placement_bias="earliest",
        meal_offsets=[0] * meals_count
    )
    population.append(ind_deadline)

    # Pure focus-productivity individual (meals slightly shifted to avoid focus peaks)
    prod_offsets = []
    for m_idx in range(meals_count):
        offset_val = 15 if m_idx % 2 == 1 else -15
        prod_offsets.append(offset_val)

    ind_productivity = Individual(
        permutation=focus_order.copy(),
        placement_bias="productivity",
        meal_offsets=prod_offsets
    )
    population.append(ind_productivity)

    # Mixed individuals
    needed_mixed = max(0, config.population_size - len(population))
    for i in range(needed_mixed):
        # Blend ratio alpha from 0.1 to 0.9 with random jitter
        a = (i + 1) / (needed_mixed + 1)
        bias = "balanced" if (0.3 <= a <= 0.7) else ("earliest" if a > 0.7 else "productivity")

        def mixed_key(idx: int) -> float:
            d_rank = deadline_rank_map[idx]
            f_rank = focus_rank_map[idx]
            jitter = random.uniform(-0.15, 0.15) * num_tasks
            return a * d_rank + (1.0 - a) * f_rank + jitter

        mixed_order = sorted(range(num_tasks), key=mixed_key)
        rand_offsets = [random.choice([-30, -15, 0, 15, 30]) for _ in range(meals_count)]
        population.append(Individual(
            permutation=mixed_order,
            placement_bias=bias,
            meal_offsets=rand_offsets
        ))

    # Decode and score all generated individuals
    for ind in population:
        ind.schedule = decode_permutation_to_schedule(
            ind.permutation,
            tasks,
            weekly_schedule,
            productivity_curve,
            config,
            placement_bias=ind.placement_bias,
            meal_offsets=ind.meal_offsets
        )
        ind.score = evaluate_schedule(ind.schedule, scoring_functions, productivity_curve, config)

    return population


def is_eligible_to_reproduce(
    candidate_score: float,
    previous_best_score: float,
    threshold: float = 0.75,
    higher_is_better: bool = True
) -> bool:
    """
    Checks if a candidate's score meets the reproduction eligibility threshold:
    Score must be better than 75% of best score from previous population.
    """
    if higher_is_better:
        if previous_best_score >= 0:
            cutoff = previous_best_score * threshold
        else:
            cutoff = previous_best_score * (2.0 - threshold)
        return candidate_score >= cutoff
    else:
        # Lower is better (cost minimization)
        cutoff = previous_best_score / threshold if previous_best_score > 0 else previous_best_score * threshold
        return candidate_score <= cutoff


def tournament_select(
    eligible_pool: List[Individual],
    tournament_size: int,
    higher_is_better: bool = True
) -> Individual:
    """Selects one individual via tournament selection from eligible pool."""
    k = min(len(eligible_pool), max(1, tournament_size))
    contestants = random.sample(eligible_pool, k)
    if higher_is_better:
        return max(contestants, key=lambda ind: ind.score)
    else:
        return min(contestants, key=lambda ind: ind.score)


# ==============================================================================
# Main Optimization Function
# ==============================================================================

class OptimizationResult:
    """Encapsulates the final optimization results and history."""

    def __init__(
        self,
        best_schedule: Schedule,
        best_score: float,
        best_individual: Individual,
        history: List[Dict[str, float]],
        generations_run: int,
        converged: bool,
        config: OptimizationConfig
    ):
        self.best_schedule = best_schedule
        self.best_score = best_score
        self.best_individual = best_individual
        self.history = history
        self.generations_run = generations_run
        self.converged = converged
        self.config = config

    def to_calendar_dicts(
        self,
        include_meals: bool = True,
        include_activities: bool = True
    ) -> List[Dict[str, Any]]:
        """Direct access to GUI calendar dictionaries."""
        return self.best_schedule.to_calendar_dicts(
            include_meals=include_meals,
            include_activities=include_activities
        )

    def __iter__(self):
        yield self.best_schedule
        yield self.best_score

    def __repr__(self) -> str:
        return (
            f"OptimizationResult(best_score={self.best_score:.2f}, "
            f"generations_run={self.generations_run}, "
            f"converged={self.converged}, "
            f"assigned_tasks={len(self.best_schedule.assignments)}, "
            f"scheduled_meals={len(self.best_schedule.meals)}, "
            f"scheduled_activities={len(self.best_schedule.activities)}, "
            f"unassigned_tasks={len(self.best_schedule.unassigned_tasks)})"
        )


def optimize_schedule(
    scoring_functions: Optional[Union[Callable[[Schedule], float], List[Callable[[Schedule], float]]]],
    task_list: List[Task],
    weekly_schedule: WeeklySchedule,
    productivity_curve_data: Any,
    config: Optional[OptimizationConfig] = None,
    **kwargs
) -> OptimizationResult:
    """
    Optimizes task assignment, meal scheduling, and physical activity into a weekly
    schedule using an evolutionary algorithm.

    Workflow:
      1. Generates the first population containing:
         - A schedule based strictly on earliest deadlines.
         - A schedule based strictly on task focus correlation with productivity curve.
         - Mixed combinations of both.
         - Meal blocks respecting duration, counts, and spacing limits.
         - Physical activities avoiding bad weather and poor air quality.
         - Assigning tasks with matching tags first to slots with specific tags.
      2. Scores all generated schedules with the passed scoring function(s).
      3. Generates consecutive populations using Partially Mapped Crossover (PMX)
         and mutation.
      4. Restricts reproduction strictly to individuals whose score is better
         than 75% of the previous generation's best score.
      5. Evolves new populations until the score difference between consecutive
         populations achieves a value below the convergence threshold for `patience` rounds.

    All parameters are editable via OptimizationConfig or direct keyword arguments.
    """
    # Initialize or override configuration
    if config is not None:
        cfg = copy.copy(config)
    else:
        cfg = OptimizationConfig()

    for k, v in kwargs.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)

    if cfg.random_seed is not None:
        random.seed(cfg.random_seed)

    # Scale productivity curve using adapted SAFTE model if sleep data is provided
    if getattr(cfg, "enable_safte_scaling", True) and getattr(cfg, "sleep_data", None) is not None:
        productivity_curve_data = scale_productivity_curve_with_safte(
            productivity_curve_data,
            cfg.sleep_data,
            target_sleep_minutes=getattr(cfg, "safte_target_sleep_minutes", 480.0),
            baseline_nominal_effectiveness=getattr(cfg, "safte_baseline_effectiveness", 100.0)
        )

    # Wrap productivity curve
    prod_curve = ProductivityCurve(productivity_curve_data)

    # Edge case: empty task list
    if not task_list:
        empty_schedule = Schedule(weekly_schedule)
        if cfg.enable_meals and cfg.meals_per_day > 0:
            populate_meals_for_schedule(empty_schedule, weekly_schedule, cfg)
        if cfg.enable_physical_activity:
            w_fc = getattr(cfg, "weather_air_forecast", None) or getattr(cfg, "weather_forecast", None)
            aq_fc = getattr(cfg, "air_quality_forecast", None)
            parse_physical_activity(
                duration_minutes=cfg.activity_duration_minutes,
                weekly_schedule=weekly_schedule,
                weather_forecast=w_fc,
                air_quality_forecast=aq_fc,
                sessions_per_week=cfg.activities_per_week,
                schedule=empty_schedule,
                config=cfg.physical_activity_config,
                weather_weight=cfg.activity_weather_weight,
                air_quality_weight=cfg.activity_air_quality_weight
            )
        return OptimizationResult(
            best_schedule=empty_schedule,
            best_score=0.0,
            best_individual=Individual([], "balanced", empty_schedule, 0.0),
            history=[],
            generations_run=0,
            converged=True,
            config=cfg
        )

    # --------------------------------------------------------------------------
    # Step 1: Generate and score 1st Population
    # --------------------------------------------------------------------------
    current_population = create_initial_population(
        task_list, weekly_schedule, prod_curve, scoring_functions, cfg
    )

    if cfg.higher_is_better:
        best_individual = max(current_population, key=lambda ind: ind.score)
    else:
        best_individual = min(current_population, key=lambda ind: ind.score)

    best_score = best_individual.score
    history: List[Dict[str, float]] = [{
        "generation": 1,
        "best_score": best_score,
        "mean_score": sum(ind.score for ind in current_population) / len(current_population)
    }]

    generations_run = 1
    converged = False
    consecutive_converged = 0

    # --------------------------------------------------------------------------
    # Step 2: Evolutionary Loop (Consecutive Generations)
    # --------------------------------------------------------------------------
    for gen in range(2, cfg.max_generations + 1):
        prev_best_score = best_score

        # Filter reproduction pool: only those with score better than 75% of previous best
        eligible_pool = [
            ind for ind in current_population
            if is_eligible_to_reproduce(
                ind.score,
                prev_best_score,
                threshold=cfg.reproduction_threshold,
                higher_is_better=cfg.higher_is_better
            )
        ]

        # Fallback if nobody qualified
        if not eligible_pool:
            if cfg.higher_is_better:
                top_cutoff = max(1, int(len(current_population) * 0.25))
                sorted_pop = sorted(current_population, key=lambda ind: ind.score, reverse=True)
            else:
                top_cutoff = max(1, int(len(current_population) * 0.25))
                sorted_pop = sorted(current_population, key=lambda ind: ind.score)
            eligible_pool = sorted_pop[:top_cutoff]

        next_population: List[Individual] = []

        # Elitism: preserve top performers
        if cfg.elitism_count > 0:
            if cfg.higher_is_better:
                elites = sorted(current_population, key=lambda ind: ind.score, reverse=True)[:cfg.elitism_count]
            else:
                elites = sorted(current_population, key=lambda ind: ind.score)[:cfg.elitism_count]
            for elite in elites:
                next_population.append(Individual(
                    permutation=elite.permutation.copy(),
                    placement_bias=elite.placement_bias,
                    schedule=elite.schedule,
                    score=elite.score,
                    meal_offsets=elite.meal_offsets.copy() if elite.meal_offsets else []
                ))

        # Generate offspring via PMX crossover and mutation
        while len(next_population) < cfg.population_size:
            p1 = tournament_select(eligible_pool, cfg.tournament_size, cfg.higher_is_better)
            p2 = tournament_select(eligible_pool, cfg.tournament_size, cfg.higher_is_better)

            # Partially Mapped Crossover (PMX)
            c1_perm, c2_perm = partially_mixed_crossover(p1.permutation, p2.permutation)

            # Mutation
            c1_perm = mutate_permutation(c1_perm, cfg.mutation_chance)
            c2_perm = mutate_permutation(c2_perm, cfg.mutation_chance)

            b1 = random.choice([p1.placement_bias, p2.placement_bias])
            b2 = random.choice([p1.placement_bias, p2.placement_bias])

            # Crossover & mutate meal offsets
            c1_offs = []
            c2_offs = []
            p1_offs = p1.meal_offsets or [0] * cfg.meals_per_day
            p2_offs = p2.meal_offsets or [0] * cfg.meals_per_day
            for o1, o2 in zip(p1_offs, p2_offs):
                if random.random() < 0.5:
                    c1_offs.append(o1)
                    c2_offs.append(o2)
                else:
                    c1_offs.append(o2)
                    c2_offs.append(o1)

            if random.random() < cfg.mutation_chance and c1_offs:
                idx_m = random.randrange(len(c1_offs))
                c1_offs[idx_m] = max(-90, min(90, c1_offs[idx_m] + random.choice([-30, -15, 15, 30])))
            if random.random() < cfg.mutation_chance and c2_offs:
                idx_m = random.randrange(len(c2_offs))
                c2_offs[idx_m] = max(-90, min(90, c2_offs[idx_m] + random.choice([-30, -15, 15, 30])))

            next_population.append(Individual(
                permutation=c1_perm, placement_bias=b1, meal_offsets=c1_offs
            ))
            if len(next_population) < cfg.population_size:
                next_population.append(Individual(
                    permutation=c2_perm, placement_bias=b2, meal_offsets=c2_offs
                ))

        # Decode and score the newly formed population
        for ind in next_population:
            if ind.schedule is None:
                ind.schedule = decode_permutation_to_schedule(
                    ind.permutation,
                    task_list,
                    weekly_schedule,
                    prod_curve,
                    cfg,
                    placement_bias=ind.placement_bias,
                    meal_offsets=ind.meal_offsets
                )
                ind.score = evaluate_schedule(
                    ind.schedule, scoring_functions, prod_curve, cfg
                )

        current_population = next_population
        generations_run = gen

        # Track top performer
        if cfg.higher_is_better:
            current_best = max(current_population, key=lambda ind: ind.score)
        else:
            current_best = min(current_population, key=lambda ind: ind.score)

        if cfg.higher_is_better and current_best.score > best_score:
            best_score = current_best.score
            best_individual = current_best
        elif not cfg.higher_is_better and current_best.score < best_score:
            best_score = current_best.score
            best_individual = current_best

        # Convergence test: score difference between new populations achieves value below set threshold
        score_diff = abs(best_score - prev_best_score)

        history.append({
            "generation": gen,
            "best_score": best_score,
            "mean_score": sum(ind.score for ind in current_population) / len(current_population),
            "score_diff": score_diff
        })

        if score_diff <= cfg.convergence_threshold:
            consecutive_converged += 1
            if consecutive_converged >= cfg.patience:
                converged = True
                break
        else:
            consecutive_converged = 0

    return OptimizationResult(
        best_schedule=best_individual.schedule or decode_permutation_to_schedule(
            best_individual.permutation, task_list, weekly_schedule, prod_curve, cfg, meal_offsets=best_individual.meal_offsets
        ),
        best_score=best_score,
        best_individual=best_individual,
        history=history,
        generations_run=generations_run,
        converged=converged,
        config=cfg
    )
