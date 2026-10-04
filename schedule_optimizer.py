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
    """
    Configuration parameters for genetic schedule optimization.
    All parameters are fully editable via variables or keyword arguments.
    """
    population_size: int = 50
    reproduction_threshold: float = 0.75      # Only individuals >= 75% of previous best score can reproduce
    convergence_threshold: float = 0.01       # Score difference between consecutive populations to stop
    mutation_chance: float = 0.15             # Probability of mutation for an offspring
    crossover_chance: float = 0.85            # Probability of PMX crossover
    max_generations: int = 100                # Hard limit on generations
    min_generations: int = 2                  # Minimum generations before convergence can trigger
    patience: int = 2                         # Consecutive generations below threshold needed to converge
    elitism_count: int = 2                    # Number of best solutions to carry over unchanged
    higher_is_better: bool = True             # True if higher score is better
    default_task_duration_minutes: int = 60   # Default duration when task.time is not specified
    require_tag_match: bool = False           # If True, task tags must strictly match slot tags
    only_tagged_slots: bool = False           # If True, tasks can only be scheduled into tagged slots
    convergence_metric: str = "best"          # "best" or "average"
    tournament_size: int = 3                  # Size for tournament selection
    random_seed: Optional[int] = None         # Random seed for reproducibility
    reference_date: Optional[datetime] = None # Monday date corresponding to day 0 of the weekly schedule
    unassigned_task_penalty: float = 50.0     # Base penalty per unassigned task
    priority_multipliers: Optional[Dict[Any, float]] = None  # Multiplier per task priority
    penalize_tag_mismatch: bool = True        # Exponential penalty for scheduling tasks into slots with alien tags
    tag_mismatch_base_penalty: float = 10.0   # Base penalty factor for tag mismatch
    tag_mismatch_growth_rate: float = 1.5     # Exponential base (growth rate per overlap unit)
    tag_mismatch_scale_unit: float = 1.0      # Number of slots (or units) per exponential step
    tag_mismatch_scale_by_priority: bool = True  # Whether to multiply tag mismatch penalty by task priority

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


# ==============================================================================
# Productivity Curve Model
# ==============================================================================

class ProductivityCurve:
    """
    Wrapper for productivity curve data.
    Supports:
      - 2D array: [day][slot] (7 days x 96 slots)
      - 1D array: [slot] of 96 values (reused for each day)
      - 1D array: [hour] of 24 values
      - Dict: {(day, slot): value} or {slot: value}
      - Callable: f(day, slot) -> float
      - Scalar float
    """

    def __init__(self, data: Any):
        self.data = data

    def get_value(self, day: int, slot: int) -> float:
        if self.data is None:
            return 1.0

        if callable(self.data):
            try:
                return float(self.data(day, slot))
            except Exception:
                return 1.0

        if isinstance(self.data, dict):
            if (day, slot) in self.data:
                return float(self.data[(day, slot)])
            if slot in self.data:
                return float(self.data[slot])
            return 0.5

        if isinstance(self.data, (list, tuple)):
            if len(self.data) == 0:
                return 0.5
            if len(self.data) == DAYS_IN_WEEK and isinstance(self.data[0], (list, tuple)):
                day_data = self.data[day % DAYS_IN_WEEK]
                if slot < len(day_data):
                    return float(day_data[slot])
                return 0.5
            if len(self.data) == SLOTS_PER_DAY:
                return float(self.data[slot % SLOTS_PER_DAY])
            if len(self.data) == 24:
                return float(self.data[(slot * SLOT_MINUTES // 60) % 24])

        if isinstance(self.data, (int, float)):
            return float(self.data)

        return 0.5

    def average_window(self, day: int, start_slot: int, end_slot: int) -> float:
        if end_slot <= start_slot:
            return self.get_value(day, start_slot)
        total = sum(self.get_value(day, s) for s in range(start_slot, end_slot))
        return total / (end_slot - start_slot)


# ==============================================================================
# Schedule Representation
# ==============================================================================

@dataclass
class ScheduledTask:
    """Represents a task assigned to a specific time interval in the week."""
    task: Task
    day: int                 # 0 = Monday, ..., 6 = Sunday
    start_slot: int          # 0..95
    end_slot: int            # start_slot + slots_needed
    start_time: time
    end_time: time
    duration_minutes: int
    scheduled_datetime: Optional[datetime] = None
    matched_tags: List[Tag] = field(default_factory=list)


class Schedule:
    """
    Decoded schedule containing concrete assignments of tasks and meals
    to days and slots.
    """

    def __init__(self, weekly_schedule: WeeklySchedule):
        self.weekly_schedule = weekly_schedule
        self.assignments: List[ScheduledTask] = []
        self.meals: List[ScheduledMeal] = []
        self.unassigned_tasks: List[Task] = []
        self.task_assignments: Dict[int, ScheduledTask] = {}
        # grid[day][slot] = task_id, negative ID for meal, or None
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

    def is_slot_free(self, day: int, slot: int) -> bool:
        return self.grid[day][slot] is None

    def is_window_free(self, day: int, start_slot: int, end_slot: int) -> bool:
        if end_slot > SLOTS_PER_DAY:
            return False
        return all(self.grid[day][s] is None for s in range(start_slot, end_slot))

    def to_calendar_dicts(self, include_meals: bool = True) -> List[Dict[str, Any]]:
        """
        Converts scheduled tasks and meals to the dictionary format expected by
        WeeklyCalendarFrame.set_tasks(...) in calender.py.
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

        return results


# ==============================================================================
# Helper Utilities
# ==============================================================================

def slot_to_time(slot_idx: int) -> time:
    minutes = slot_idx * SLOT_MINUTES
    return time(hour=(minutes // 60) % 24, minute=minutes % 60)


def time_to_slot(t: time) -> int:
    return (t.hour * 60 + t.minute) // SLOT_MINUTES


def get_task_duration_minutes(task: Task, default_minutes: int = 60) -> int:
    """Extracts duration in minutes from task.time or fallback attribute."""
    if task.time is not None:
        if isinstance(task.time, (int, float)):
            return max(15, int(task.time))
        if isinstance(task.time, timedelta):
            return max(15, int(task.time.total_seconds() // 60))
        if isinstance(task.time, time):
            mins = task.time.hour * 60 + task.time.minute
            return max(15, mins) if mins > 0 else default_minutes
        if isinstance(task.time, datetime):
            mins = task.time.hour * 60 + task.time.minute
            return max(15, mins) if mins > 0 else default_minutes

    if hasattr(task, "duration") and task.duration is not None:
        try:
            return max(15, int(task.duration))
        except (ValueError, TypeError):
            pass

    return max(15, default_minutes)


def tag_identifiers(tags: Iterable[Tag]) -> set:
    ids = set()
    for t in tags:
        if hasattr(t, "title") and t.title:
            ids.add(str(t.title).strip().lower())
        if hasattr(t, "id") and t.id is not None:
            ids.add(f"id:{t.id}")
        if not hasattr(t, "title") and not hasattr(t, "id"):
            ids.add(str(t).strip().lower())
    return ids


def match_tags(task_tags: List[Tag], slot_tags: List[Tag]) -> Tuple[bool, List[Tag]]:
    """Checks if task tags match slot tags, returning compatibility and matching tags."""
    if not task_tags:
        # If task has no specific tags, it can fit in any slot
        return True, slot_tags

    if not slot_tags:
        return False, []

    task_set = tag_identifiers(task_tags)
    matching = [st for st in slot_tags if tag_identifiers([st]) & task_set]
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
    """Calculates the concrete finish datetime for a scheduled task."""
    if reference_date is None:
        return None
    # day 0 is reference_date (Monday)
    date_day = reference_date.date() + timedelta(days=day)
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

    for day in active_days:
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
    in the WeeklySchedule, parsing and respecting meal times and tag constraints.
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

    # 2. Place tasks around meals and reserved windows
    penalize_mismatch = getattr(config, "penalize_tag_mismatch", True)
    growth = max(1.001, float(getattr(config, "tag_mismatch_growth_rate", 1.5)))
    base_mismatch_p = float(getattr(config, "tag_mismatch_base_penalty", 10.0))
    scale_by_prio = getattr(config, "tag_mismatch_scale_by_priority", True)

    for task_idx in permutation:
        task = tasks[task_idx]
        duration_minutes = get_task_duration_minutes(task, config.default_task_duration_minutes)
        slots_needed = max(1, math.ceil(duration_minutes / SLOT_MINUTES))

        best_day = None
        best_start = None
        best_end = None
        best_matched_tags: List[Tag] = []
        best_candidate_score = -float("inf")

        focus_val = float(getattr(task, "focus", 5) or 5)
        # Normalize focus roughly to 0..1
        focus_norm = min(1.0, max(0.0, focus_val / 10.0 if focus_val <= 10 else focus_val / 100.0))
        task_tag_ids = tag_identifiers(task.tags)

        # Scan all available days and slot windows
        for day in range(DAYS_IN_WEEK):
            # Scan slots within the day
            for s in range(0, SLOTS_PER_DAY - slots_needed + 1):
                e = s + slots_needed

                # Check window availability (meals and other tasks are marked as occupied)
                if not schedule.is_window_free(day, s, e):
                    continue

                # Check tags across the window
                window_slot_tags = []
                all_have_tags = True
                strictly_compatible = True
                matched_window_tags: List[Tag] = []
                mismatched_slots = 0

                for slot_idx in range(s, e):
                    slot_tags = weekly_schedule._slots[day][slot_idx]
                    if not slot_tags:
                        all_have_tags = False
                    is_compat, matched = match_tags(task.tags, slot_tags)
                    if task.tags and not is_compat:
                        strictly_compatible = False
                    matched_window_tags.extend(matched)
                    window_slot_tags.extend(slot_tags)

                    # Count slots with alien tags (tags not belonging to the task)
                    if slot_tags:
                        alien_tags = [st for st in slot_tags if not (tag_identifiers([st]) & task_tag_ids)]
                        if alien_tags:
                            mismatched_slots += 1

                if config.only_tagged_slots and not all_have_tags:
                    continue

                if config.require_tag_match and task.tags and not strictly_compatible:
                    continue

                # Candidate window evaluation
                time_cost = (day * SLOTS_PER_DAY + s) / (DAYS_IN_WEEK * SLOTS_PER_DAY)  # 0 (start) to 1 (end)
                avg_prod = productivity_curve.average_window(day, s, e)

                # Productivity correlation: high focus benefits from high productivity
                prod_alignment = 1.0 - abs(focus_norm - avg_prod)

                # Deadline penalty/bonus in placement
                deadline_factor = 0.0
                if task.deadline:
                    dt = task_finish_datetime(day, e, config.reference_date)
                    if dt:
                        if dt <= task.deadline:
                            deadline_factor = 1.0 - (task.deadline - dt).total_seconds() / (7 * 86400)
                        else:
                            # Late
                            deadline_factor = -2.0

                tag_bonus = 2.0 if matched_window_tags else (0.5 if not task.tags else -1.0)

                # Placement scoring by bias
                if placement_bias == "earliest":
                    candidate_score = 10.0 * (1.0 - time_cost) + 2.0 * deadline_factor + tag_bonus
                elif placement_bias == "productivity":
                    candidate_score = 10.0 * prod_alignment + 3.0 * avg_prod + tag_bonus - 0.5 * time_cost
                else:  # balanced
                    candidate_score = (
                        5.0 * (1.0 - time_cost)
                        + 5.0 * prod_alignment
                        + 2.0 * deadline_factor
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
            scheduled = ScheduledTask(
                task=task,
                day=best_day,
                start_slot=best_start,
                end_slot=best_end,
                start_time=slot_to_time(best_start),
                end_time=slot_to_time(best_end),
                duration_minutes=slots_needed * SLOT_MINUTES,
                scheduled_datetime=task_finish_datetime(best_day, best_end, config.reference_date),
                matched_tags=best_matched_tags
            )
            schedule.add_assignment(scheduled)
        else:
            schedule.unassigned_tasks.append(task)

    return schedule


# ==============================================================================
# Genetic Operators: PMX Crossover and Mutation
# ==============================================================================

def partially_mixed_crossover(parent1: List[int], parent2: List[int]) -> Tuple[List[int], List[int]]:
    """
    Partially Mapped Crossover (PMX), also known as Partially Mixed Crossover.
    Produces two valid offspring permutations from two parent permutations.
    """
    size = len(parent1)
    if size <= 1:
        return parent1.copy(), parent2.copy()

    # Pick two distinct crossover points
    cx1 = random.randint(0, size - 2)
    cx2 = random.randint(cx1 + 1, size - 1)

    child1: List[Optional[int]] = [None] * size
    child2: List[Optional[int]] = [None] * size

    # Copy the chosen slice
    child1[cx1:cx2 + 1] = parent1[cx1:cx2 + 1]
    child2[cx1:cx2 + 1] = parent2[cx1:cx2 + 1]

    # Map elements for child1 from parent2
    for i in range(cx1, cx2 + 1):
        val = parent2[i]
        if val not in child1[cx1:cx2 + 1]:
            curr = i
            while cx1 <= curr <= cx2:
                mapped_val = parent1[curr]
                curr = parent2.index(mapped_val)
            child1[curr] = val

    # Map elements for child2 from parent1
    for i in range(cx1, cx2 + 1):
        val = parent1[i]
        if val not in child2[cx1:cx2 + 1]:
            curr = i
            while cx1 <= curr <= cx2:
                mapped_val = parent2[curr]
                curr = parent1.index(mapped_val)
            child2[curr] = val

    # Fill remaining positions directly
    for i in range(size):
        if child1[i] is None:
            child1[i] = parent2[i]
        if child2[i] is None:
            child2[i] = parent1[i]

    return [int(x) for x in child1], [int(x) for x in child2]


def mutate_permutation(permutation: List[int], mutation_chance: float) -> List[int]:
    """
    Applies mutation to a permutation with probability mutation_chance.
    Uses swap or segment inversion.
    """
    mutated = permutation.copy()
    if len(mutated) < 2:
        return mutated

    if random.random() < mutation_chance:
        mutation_type = random.choice(["swap", "invert"])
        i, j = sorted(random.sample(range(len(mutated)), 2))
        if mutation_type == "swap":
            mutated[i], mutated[j] = mutated[j], mutated[i]
        elif mutation_type == "invert":
            mutated[i:j + 1] = reversed(mutated[i:j + 1])

    return mutated


# ==============================================================================
# Scoring and Evaluation
# ==============================================================================

def default_deadline_score(schedule: Schedule, config: OptimizationConfig) -> float:
    """Calculates score based on meeting deadlines, unassigned tasks, tag mismatch, and meal spacing."""
    score = 100.0
    for st in schedule.assignments:
        if st.task.deadline:
            finish_dt = st.scheduled_datetime or task_finish_datetime(
                st.day, st.end_slot, config.reference_date
            )
            if finish_dt:
                if finish_dt <= st.task.deadline:
                    score += 20.0
                else:
                    late_hours = (finish_dt - st.task.deadline).total_seconds() / 3600.0
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

    return score


def default_productivity_score(schedule: Schedule, productivity_curve: ProductivityCurve) -> float:
    """Calculates correlation of task focus with productivity curve."""
    total_alignment = 0.0
    for st in schedule.assignments:
        focus = float(getattr(st.task, "focus", 5) or 5)
        focus_norm = min(1.0, max(0.0, focus / 10.0 if focus <= 10 else focus / 100.0))
        avg_prod = productivity_curve.average_window(st.day, st.start_slot, st.end_slot)
        alignment = 1.0 - abs(focus_norm - avg_prod)
        total_alignment += alignment * 25.0
    return total_alignment


def evaluate_schedule(
    schedule: Schedule,
    scoring_functions: Union[Callable[[Schedule], float], Iterable[Callable[[Schedule], float]], None],
    productivity_curve: ProductivityCurve,
    config: OptimizationConfig
) -> float:
    """Evaluates a schedule using the user-provided scoring function(s) or defaults."""
    if scoring_functions is None:
        return default_deadline_score(schedule, config) + default_productivity_score(schedule, productivity_curve)

    if callable(scoring_functions):
        return float(scoring_functions(schedule))

    if isinstance(scoring_functions, Iterable):
        total = 0.0
        for fn in scoring_functions:
            if callable(fn):
                total += float(fn(schedule))
        return total

    return default_deadline_score(schedule, config)


# ==============================================================================
# Individual and Population Management
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
    scoring_functions: Any,
    config: OptimizationConfig
) -> List[Individual]:
    """
    Creates the first population according to requirements:
      1. Schedule based only on time to deadlines (shortest time to deadline goes first).
      2. Schedule based only on correlation of task focus with productivity curve.
      3. Mixed combinations of both with varying blends and diversity.
    """
    num_tasks = len(tasks)
    if num_tasks == 0:
        return []

    # 1. Deadline-based ranking (Earliest Due Date)
    now_ref = config.reference_date or datetime.now()

    def deadline_key(idx: int) -> float:
        t = tasks[idx]
        if t.deadline is None:
            return float("inf")
        if isinstance(t.deadline, datetime):
            return t.deadline.timestamp()
        return float("inf")

    deadline_order = sorted(range(num_tasks), key=deadline_key)

    # 2. Focus-Productivity correlation ranking
    def focus_key(idx: int) -> float:
        t = tasks[idx]
        return -float(getattr(t, "focus", 0) or 0)

    focus_order = sorted(range(num_tasks), key=focus_key)

    # Calculate rank maps
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
        # Evenly spread slight offsets
        offset_val = 15 if m_idx % 2 == 1 else -15
        prod_offsets.append(offset_val)

    ind_productivity = Individual(
        permutation=focus_order.copy(),
        placement_bias="productivity",
        meal_offsets=prod_offsets
    )
    population.append(ind_productivity)

    # Mixed individuals
    num_mixed = max(0, config.population_size - len(population))
    for k in range(num_mixed):
        # Varying mix ratio alpha from 0.05 to 0.95
        alpha = (k + 1) / (num_mixed + 1)
        bias = "earliest" if alpha > 0.65 else ("productivity" if alpha < 0.35 else "balanced")

        def mixed_key(idx: int, a=alpha) -> float:
            d_rank = deadline_rank_map[idx] / max(1, num_tasks - 1)
            f_rank = focus_rank_map[idx] / max(1, num_tasks - 1)
            jitter = random.gauss(0, 0.05)
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


def select_parent(
    candidates: List[Individual],
    tournament_size: int,
    higher_is_better: bool
) -> Individual:
    """Selects an individual using tournament selection."""
    pool_size = min(len(candidates), max(1, tournament_size))
    sample = random.sample(candidates, pool_size)
    if higher_is_better:
        return max(sample, key=lambda ind: ind.score)
    else:
        return min(sample, key=lambda ind: ind.score)


def is_eligible_to_reproduce(
    ind_score: float,
    best_score_prev: float,
    threshold: float,
    higher_is_better: bool
) -> bool:
    """
    Checks if an individual score is better than threshold (e.g. 75%)
    of the best score from the previous population.
    """
    if higher_is_better:
        if best_score_prev > 0:
            return ind_score >= threshold * best_score_prev
        elif best_score_prev == 0:
            return ind_score >= 0.0
        else:
            # Negative scores: threshold better means closer to best_score_prev
            allowed_drop = abs(best_score_prev) * (1.0 - threshold)
            return ind_score >= (best_score_prev - allowed_drop)
    else:
        # Minimization
        if best_score_prev > 0:
            allowed_increase = best_score_prev * (1.0 - threshold)
            return ind_score <= (best_score_prev + allowed_increase)
        else:
            return ind_score <= threshold * best_score_prev


# ==============================================================================
# Optimization Result & Stats
# ==============================================================================

@dataclass
class GenerationStats:
    generation: int
    best_score: float
    average_score: float
    eligible_count: int
    score_difference: float


class OptimizationResult:
    """
    Container for the final optimization results.
    Can be unpacked like a tuple (best_schedule, best_score).
    """

    def __init__(
        self,
        best_schedule: Schedule,
        best_score: float,
        best_individual: Individual,
        history: List[GenerationStats],
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

    def to_calendar_dicts(self, include_meals: bool = True) -> List[Dict[str, Any]]:
        """Direct access to GUI calendar dictionaries."""
        return self.best_schedule.to_calendar_dicts(include_meals=include_meals)

    def __iter__(self):
        yield self.best_schedule
        yield self.best_score

    def __repr__(self) -> str:
        return (
            f"OptimizationResult(best_score={self.best_score:.4f}, "
            f"generations_run={self.generations_run}, "
            f"converged={self.converged}, "
            f"assigned_tasks={len(self.best_schedule.assignments)}, "
            f"scheduled_meals={len(self.best_schedule.meals)}, "
            f"unassigned_tasks={len(self.best_schedule.unassigned_tasks)})"
        )


# ==============================================================================
# Main Optimization Function
# ==============================================================================

def optimize_schedule(
    scoring_functions: Union[Callable[[Schedule], float], Iterable[Callable[[Schedule], float]], None],
    task_list: List[Task],
    weekly_schedule: WeeklySchedule,
    productivity_curve_data: Any,
    config: Optional[OptimizationConfig] = None,
    **kwargs
) -> OptimizationResult:
    """
    Optimizes task assignment and meal scheduling into a weekly schedule using
    an evolutionary algorithm.

    Workflow:
      1. Generates the first population containing:
         - A schedule based strictly on earliest deadlines.
         - A schedule based strictly on task focus correlation with productivity curve.
         - Mixed combinations of both.
         - Meal blocks respecting duration, counts, and spacing limits.
      2. Scores all generated schedules with the passed scoring function(s).
      3. Generates consecutive populations using Partially Mapped Crossover (PMX)
         and mutation.
      4. In 2nd and subsequent populations, only individuals with scores better than
         75% of the previous population's best score are allowed to reproduce.
      5. Terminates when the score difference between consecutive populations falls
         below the set threshold (or max generations is reached).

    Parameters:
      - scoring_functions: single scoring function or list of scoring functions.
      - task_list: list of Task instances to schedule.
      - weekly_schedule: WeeklySchedule instance with assigned tags.
      - productivity_curve_data: 2D/1D list, dict, or callable for productivity curve.
      - config: Optional OptimizationConfig object.
      - **kwargs: Any OptimizationConfig parameter can be passed directly here.

    Returns:
      OptimizationResult with the best schedule and run statistics.
    """
    # Merge config and keyword arguments
    if config is None:
        cfg = OptimizationConfig(**kwargs)
    else:
        cfg = copy.copy(config)
        for k, v in kwargs.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)

    if cfg.random_seed is not None:
        random.seed(cfg.random_seed)

    # Wrap productivity curve
    prod_curve = ProductivityCurve(productivity_curve_data)

    # Edge case: empty task list
    if not task_list:
        empty_schedule = Schedule(weekly_schedule)
        if cfg.enable_meals and cfg.meals_per_day > 0:
            populate_meals_for_schedule(empty_schedule, weekly_schedule, cfg)
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
    avg_score = sum(ind.score for ind in current_population) / len(current_population)

    history: List[GenerationStats] = [
        GenerationStats(
            generation=0,
            best_score=best_score,
            average_score=avg_score,
            eligible_count=len(current_population),
            score_difference=0.0
        )
    ]

    previous_best_score = best_score
    consecutive_converged = 0
    converged = False
    gen = 0

    # --------------------------------------------------------------------------
    # Step 2: Generational Evolution Loop
    # --------------------------------------------------------------------------
    while gen < cfg.max_generations:
        gen += 1

        # Determine eligible reproducers:
        # For Gen 1 (producing Gen 2), all Gen 0 individuals are valid parents.
        # For Gen 2+, only individuals with score better than 75% of previous best score reproduce.
        if gen == 1:
            eligible_parents = current_population
        else:
            eligible_parents = [
                ind for ind in current_population
                if is_eligible_to_reproduce(
                    ind.score,
                    previous_best_score,
                    cfg.reproduction_threshold,
                    cfg.higher_is_better
                )
            ]

        # Guard against empty or single-individual breeding pool
        if len(eligible_parents) < 2:
            sorted_pop = sorted(
                current_population,
                key=lambda ind: ind.score,
                reverse=cfg.higher_is_better
            )
            eligible_parents = sorted_pop[:max(2, min(len(sorted_pop), cfg.elitism_count))]

        # Elitism: retain top individuals
        next_population: List[Individual] = []
        if cfg.elitism_count > 0:
            sorted_current = sorted(
                current_population,
                key=lambda ind: ind.score,
                reverse=cfg.higher_is_better
            )
            for elite in sorted_current[:cfg.elitism_count]:
                next_population.append(Individual(
                    permutation=elite.permutation.copy(),
                    placement_bias=elite.placement_bias,
                    schedule=elite.schedule,
                    score=elite.score,
                    meal_offsets=elite.meal_offsets.copy() if elite.meal_offsets else []
                ))

        # Generate offspring via PMX crossover and mutation
        while len(next_population) < cfg.population_size:
            p1 = select_parent(eligible_parents, cfg.tournament_size, cfg.higher_is_better)
            p2 = select_parent(eligible_parents, cfg.tournament_size, cfg.higher_is_better)

            if random.random() < cfg.crossover_chance:
                c1_perm, c2_perm = partially_mixed_crossover(p1.permutation, p2.permutation)
            else:
                c1_perm, c2_perm = p1.permutation.copy(), p2.permutation.copy()

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

        # Update best tracking
        if cfg.higher_is_better:
            gen_best_ind = max(next_population, key=lambda ind: ind.score)
        else:
            gen_best_ind = min(next_population, key=lambda ind: ind.score)

        gen_best_score = gen_best_ind.score
        gen_avg_score = sum(ind.score for ind in next_population) / len(next_population)

        # Score difference between current new population and previous population
        if cfg.convergence_metric == "average":
            score_diff = abs(gen_avg_score - avg_score)
        else:
            score_diff = abs(gen_best_score - previous_best_score)

        history.append(GenerationStats(
            generation=gen,
            best_score=gen_best_score,
            average_score=gen_avg_score,
            eligible_count=len(eligible_parents),
            score_difference=score_diff
        ))

        if cfg.higher_is_better and gen_best_score > best_score:
            best_score = gen_best_score
            best_individual = gen_best_ind
        elif not cfg.higher_is_better and gen_best_score < best_score:
            best_score = gen_best_score
            best_individual = gen_best_ind

        # Check convergence condition
        if gen >= cfg.min_generations and score_diff <= cfg.convergence_threshold:
            consecutive_converged += 1
            if consecutive_converged >= cfg.patience:
                converged = True
                break
        else:
            consecutive_converged = 0

        # Advance to next iteration
        previous_best_score = gen_best_score
        avg_score = gen_avg_score
        current_population = next_population

    return OptimizationResult(
        best_schedule=best_individual.schedule or decode_permutation_to_schedule(
            best_individual.permutation, task_list, weekly_schedule, prod_curve, cfg, meal_offsets=best_individual.meal_offsets
        ),
        best_score=best_score,
        best_individual=best_individual,
        history=history,
        generations_run=gen,
        converged=converged,
        config=cfg
    )
