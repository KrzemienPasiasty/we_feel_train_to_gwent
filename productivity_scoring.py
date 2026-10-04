from __future__ import annotations

import math
from datetime import datetime, time, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

from schedule_optimizer import (
    DEFAULT_PRIORITY_MULTIPLIERS,
    DAYS_IN_WEEK,
    SLOT_MINUTES,
    SLOTS_PER_DAY,
    MealConfig,
    ProductivityCurve,
    Schedule,
    ScheduledMeal,
    ScheduledTask,
    calculate_meal_spacing_penalty,
    calculate_tag_mismatch_penalty,
    calculate_task_tag_mismatch_overlap,
    get_priority_multiplier,
)
from task import Task


# ==============================================================================
# Focus & Productivity Difference Function
# ==============================================================================

def focus_productivity_difference_at_timestamp(
    task_focus: float,
    productivity: float,
    positive_constant: float = 2.0
) -> float:
    """
    Calculates the transformed difference between task focus and productivity:
      diff = task_focus - productivity
      if diff > 0:
          result = abs(diff * positive_constant)
      else:
          result = abs(diff)

    Parameters:
      task_focus: Required mental focus for the task.
      productivity: Available productivity from the curve at this timestamp.
      positive_constant: Multiplier applied when task focus exceeds productivity
                         (i.e. task demands more focus than available energy).

    Returns:
      Transformed absolute difference value at this timestamp.
    """
    diff = task_focus - productivity
    if diff > 0:
        return abs(diff * positive_constant)
    else:
        return abs(diff)


# ==============================================================================
# Integration Over Time
# ==============================================================================

def integrate_focus_productivity_difference(
    schedule: Schedule,
    productivity_curve_data: Any,
    positive_constant: float = 2.0,
    time_unit: str = "hours",
    normalize_scales: bool = False,
    max_focus_scale: float = 10.0,
    max_productivity_scale: float = 1.0,
    penalize_unassigned: bool = True,
    unassigned_penalty_per_task: float = 50.0,
    priority_multipliers: Optional[Dict[Any, float]] = None,
    penalize_tag_mismatch: bool = False,
    tag_mismatch_base_penalty: float = 10.0,
    tag_mismatch_growth_rate: float = 1.5,
    tag_mismatch_scale_unit: float = 1.0,
    tag_mismatch_overlap_unit: str = "slots",
    tag_mismatch_scale_by_priority: bool = True,
    penalize_meal_spacing: bool = False,
    min_time_between_meals_minutes: int = 180,
    max_time_between_meals_minutes: int = 300,
    meal_spacing_penalty_per_minute: float = 0.5,
    missing_meal_penalty: float = 100.0,
    expected_meals_per_day: int = 3,
    active_meal_days: Optional[List[int]] = None
) -> float:
    """
    Calculates the difference between task focus and productivity across all
    scheduled timestamps:
      (task.focus - productivity)
    If the difference is positive, it multiplies it by `positive_constant` and
    takes the absolute value. Then, integrates this difference function over time.
    For unassigned tasks, applies penalty points scaled by each task's priority multiplier.
    Optionally includes an exponential penalty for tasks assigned to time slots with
    alien tags (e.g. sleeping period), and penalty for meal spacing outside limits.

    Parameters:
      schedule: The Schedule instance containing task and meal assignments.
      productivity_curve_data: Productivity curve data.
      positive_constant: Multiplier when task focus exceeds available productivity.
      time_unit: Unit for integration dt ("hours", "minutes", or "slots").
      normalize_scales: If True, normalizes task.focus and productivity to [0, 1].
      max_focus_scale: Scale for normalizing task.focus.
      max_productivity_scale: Scale for normalizing productivity.
      penalize_unassigned: If True, adds penalty for unassigned tasks.
      unassigned_penalty_per_task: Base cost added for each unassigned task.
      priority_multipliers: Custom mapping of priority to penalty multipliers.
      penalize_tag_mismatch: If True, adds exponential penalty for tag mismatch.
      penalize_meal_spacing: If True, adds penalty for meal intervals outside [min, max].
      min_time_between_meals_minutes: Minimum duration between consecutive meals.
      max_time_between_meals_minutes: Maximum duration between consecutive meals.
      meal_spacing_penalty_per_minute: Penalty per minute outside bounds.
      missing_meal_penalty: Penalty per missing meal.
      expected_meals_per_day: Target amount of meals per day.

    Returns:
      The total integrated value plus penalties.
    """
    # Wrap productivity curve
    if isinstance(productivity_curve_data, ProductivityCurve):
        curve = productivity_curve_data
    else:
        curve = ProductivityCurve(productivity_curve_data)

    # Determine dt
    if time_unit.lower() == "hours":
        dt = SLOT_MINUTES / 60.0  # 0.25 hours per slot
    elif time_unit.lower() == "minutes":
        dt = float(SLOT_MINUTES)  # 15.0 minutes per slot
    elif time_unit.lower() == "slots":
        dt = 1.0
    else:
        raise ValueError(f"Unknown time_unit: {time_unit}. Use 'hours', 'minutes', or 'slots'.")

    total_integral = 0.0

    # Iterate through all scheduled tasks and their occupied 15-minute slots
    for st in schedule.assignments:
        task = st.task
        raw_focus = float(getattr(task, "focus", 0.0) or 0.0)

        # Scale normalization if requested
        if normalize_scales:
            task_focus = raw_focus / max(1e-6, max_focus_scale)
        else:
            task_focus = raw_focus

        # Integrate over each slot occupied by the task
        for slot in range(st.start_slot, st.end_slot):
            raw_prod = curve.get_value(st.day, slot)

            if normalize_scales:
                prod = raw_prod / max(1e-6, max_productivity_scale)
            else:
                prod = raw_prod

            val_at_t = focus_productivity_difference_at_timestamp(
                task_focus=task_focus,
                productivity=prod,
                positive_constant=positive_constant
            )

            # Numerical integration: f(t) * dt
            total_integral += val_at_t * dt

    if penalize_unassigned:
        for task in schedule.unassigned_tasks:
            mult = get_priority_multiplier(task.priority, priority_multipliers)
            total_integral += unassigned_penalty_per_task * mult

    if penalize_tag_mismatch:
        tag_penalty = calculate_tag_mismatch_penalty(
            schedule=schedule,
            base_penalty=tag_mismatch_base_penalty,
            growth_rate=tag_mismatch_growth_rate,
            scale_unit=tag_mismatch_scale_unit,
            overlap_unit=tag_mismatch_overlap_unit,
            scale_by_priority=tag_mismatch_scale_by_priority,
            priority_multipliers=priority_multipliers
        )
        total_integral += tag_penalty

    if penalize_meal_spacing:
        meal_penalty = calculate_meal_spacing_penalty(
            schedule=schedule,
            min_time_between_meals_minutes=min_time_between_meals_minutes,
            max_time_between_meals_minutes=max_time_between_meals_minutes,
            penalty_per_minute=meal_spacing_penalty_per_minute,
            missing_meal_penalty=missing_meal_penalty,
            expected_meals_per_day=expected_meals_per_day,
            active_days=active_meal_days
        )
        total_integral += meal_penalty

    return total_integral


# ==============================================================================
# Discrete Series Integration (General helper for timestamped sequences)
# ==============================================================================

def integrate_series_difference(
    focus_series: List[float],
    productivity_series: List[float],
    dt: float = 0.25,
    positive_constant: float = 2.0
) -> float:
    """
    Integrates the difference function over a series of aligned discrete timestamps:
      diff = focus[i] - productivity[i]
      if diff > 0:
          f_i = abs(diff * positive_constant)
      else:
          f_i = abs(diff)
      Integral = sum(f_i * dt)
    """
    if len(focus_series) != len(productivity_series):
        raise ValueError("focus_series and productivity_series must have the same length.")

    total_integral = 0.0
    for f_val, p_val in zip(focus_series, productivity_series):
        val = focus_productivity_difference_at_timestamp(
            task_focus=f_val,
            productivity=p_val,
            positive_constant=positive_constant
        )
        total_integral += val * dt

    return total_integral


# ==============================================================================
# Scoring Function Adapter for Genetic Optimizer
# ==============================================================================

def create_focus_productivity_scoring_function(
    productivity_curve_data: Any,
    positive_constant: float = 2.0,
    time_unit: str = "hours",
    normalize_scales: bool = True,
    baseline_score: float = 1000.0,
    penalty_weight: float = 10.0,
    unassigned_penalty: float = 100.0,
    priority_multipliers: Optional[Dict[Any, float]] = None,
    penalize_tag_mismatch: bool = True,
    tag_mismatch_base_penalty: float = 10.0,
    tag_mismatch_growth_rate: float = 1.5,
    tag_mismatch_scale_unit: float = 1.0,
    tag_mismatch_overlap_unit: str = "slots",
    tag_mismatch_scale_by_priority: bool = True,
    penalize_meal_spacing: bool = False,
    min_time_between_meals_minutes: int = 180,
    max_time_between_meals_minutes: int = 300,
    meal_spacing_penalty_per_minute: float = 0.5,
    missing_meal_penalty: float = 100.0,
    expected_meals_per_day: int = 3,
    active_meal_days: Optional[List[int]] = None
) -> Callable[[Schedule], float]:
    """
    Creates a scoring function compatible with optimize_schedule.
    Higher fitness is achieved by:
      - Minimizing the integrated difference between task focus and productivity curve.
      - Avoiding leaving high-priority tasks unassigned (priority multiplier scaled).
      - Avoiding assigning tasks during alien tagged periods (e.g. sleeping period).
      - Optionally keeping meal spacing strictly within [min_time_between_meals, max_time_between_meals],
        penalizing intervals that are either shorter or longer than set limits.

    Score = baseline_score - (penalty_weight * integral) - unassigned_cost - tag_mismatch_cost - meal_spacing_cost
    """
    def scoring_fn(schedule: Schedule) -> float:
        integral = integrate_focus_productivity_difference(
            schedule=schedule,
            productivity_curve_data=productivity_curve_data,
            positive_constant=positive_constant,
            time_unit=time_unit,
            normalize_scales=normalize_scales,
            penalize_unassigned=False,
            penalize_tag_mismatch=False,
            penalize_meal_spacing=False
        )

        unassigned_cost = sum(
            unassigned_penalty * get_priority_multiplier(task.priority, priority_multipliers)
            for task in schedule.unassigned_tasks
        )

        tag_mismatch_cost = 0.0
        if penalize_tag_mismatch:
            tag_mismatch_cost = calculate_tag_mismatch_penalty(
                schedule=schedule,
                base_penalty=tag_mismatch_base_penalty,
                growth_rate=tag_mismatch_growth_rate,
                scale_unit=tag_mismatch_scale_unit,
                overlap_unit=tag_mismatch_overlap_unit,
                scale_by_priority=tag_mismatch_scale_by_priority,
                priority_multipliers=priority_multipliers
            )

        meal_spacing_cost = 0.0
        if penalize_meal_spacing and expected_meals_per_day > 0:
            meal_spacing_cost = calculate_meal_spacing_penalty(
                schedule=schedule,
                min_time_between_meals_minutes=min_time_between_meals_minutes,
                max_time_between_meals_minutes=max_time_between_meals_minutes,
                penalty_per_minute=meal_spacing_penalty_per_minute,
                missing_meal_penalty=missing_meal_penalty,
                expected_meals_per_day=expected_meals_per_day,
                active_days=active_meal_days
            )

        score = baseline_score - (penalty_weight * integral) - unassigned_cost - tag_mismatch_cost - meal_spacing_cost
        return score

    return scoring_fn
