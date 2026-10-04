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
    Decoded schedule containing concrete assignments of tasks to days and slots.
    """

    def __init__(self, weekly_schedule: WeeklySchedule):
        self.weekly_schedule = weekly_schedule
        self.assignments: List[ScheduledTask] = []
        self.unassigned_tasks: List[Task] = []
        self.task_assignments: Dict[int, ScheduledTask] = {}
        # grid[day][slot] = task_id or None
        self.grid: List[List[Optional[int]]] = [
            [None for _ in range(SLOTS_PER_DAY)] for _ in range(DAYS_IN_WEEK)
        ]

    def add_assignment(self, scheduled: ScheduledTask) -> None:
        self.assignments.append(scheduled)
        self.task_assignments[scheduled.task.id] = scheduled
        for s in range(scheduled.start_slot, scheduled.end_slot):
            self.grid[scheduled.day][s] = scheduled.task.id

    def is_slot_free(self, day: int, slot: int) -> bool:
        return self.grid[day][slot] is None

    def is_window_free(self, day: int, start_slot: int, end_slot: int) -> bool:
        if end_slot > SLOTS_PER_DAY:
            return False
        return all(self.grid[day][s] is None for s in range(start_slot, end_slot))

    def to_calendar_dicts(self) -> List[Dict[str, Any]]:
        """
        Converts scheduled tasks to the dictionary format expected by
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
        return results


# ==============================================================================
# Helper Utilities
# ==============================================================================

def slot_to_time(slot_idx: int) -> time:
    minutes = slot_idx * SLOT_MINUTES
    return time(hour=(minutes // 60) % 24, minute=minutes % 60)


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
# Schedule Decoder
# ==============================================================================

def decode_permutation_to_schedule(
    permutation: List[int],
    tasks: List[Task],
    weekly_schedule: WeeklySchedule,
    productivity_curve: ProductivityCurve,
    config: OptimizationConfig,
    placement_bias: str = "balanced"  # "earliest", "productivity", "balanced"
) -> Schedule:
    """
    Decodes an ordered permutation of task indices into concrete time slots
    in the WeeklySchedule.
    """
    schedule = Schedule(weekly_schedule)

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

        # Scan all available days and slot windows
        for day in range(DAYS_IN_WEEK):
            # Scan slots within the day
            for s in range(0, SLOTS_PER_DAY - slots_needed + 1):
                e = s + slots_needed

                # Check window availability
                if not schedule.is_window_free(day, s, e):
                    continue

                # Check tags across the window
                window_slot_tags = []
                all_have_tags = True
                strictly_compatible = True
                matched_window_tags: List[Tag] = []

                for slot_idx in range(s, e):
                    slot_tags = weekly_schedule._slots[day][slot_idx]
                    if not slot_tags:
                        all_have_tags = False
                    is_compat, matched = match_tags(task.tags, slot_tags)
                    if task.tags and not is_compat:
                        strictly_compatible = False
                    matched_window_tags.extend(matched)
                    window_slot_tags.extend(slot_tags)

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
    """Calculates score based on meeting deadlines."""
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
    score -= len(schedule.unassigned_tasks) * 50.0
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
    # Tasks with highest focus requirement go first to seize peak productivity slots
    def focus_key(idx: int) -> float:
        t = tasks[idx]
        return -float(getattr(t, "focus", 0) or 0)

    focus_order = sorted(range(num_tasks), key=focus_key)

    # Calculate rank maps
    deadline_rank_map = {idx: rank for rank, idx in enumerate(deadline_order)}
    focus_rank_map = {idx: rank for rank, idx in enumerate(focus_order)}

    population: List[Individual] = []

    # Pure deadline individual
    ind_deadline = Individual(
        permutation=deadline_order.copy(),
        placement_bias="earliest"
    )
    population.append(ind_deadline)

    # Pure focus-productivity individual
    ind_productivity = Individual(
        permutation=focus_order.copy(),
        placement_bias="productivity"
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
        population.append(Individual(permutation=mixed_order, placement_bias=bias))

    # Decode and score all generated individuals
    for ind in population:
        ind.schedule = decode_permutation_to_schedule(
            ind.permutation,
            tasks,
            weekly_schedule,
            productivity_curve,
            config,
            placement_bias=ind.placement_bias
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

    def to_calendar_dicts(self) -> List[Dict[str, Any]]:
        """Direct access to GUI calendar dictionaries."""
        return self.best_schedule.to_calendar_dicts()

    def __iter__(self):
        yield self.best_schedule
        yield self.best_score

    def __repr__(self) -> str:
        return (
            f"OptimizationResult(best_score={self.best_score:.4f}, "
            f"generations_run={self.generations_run}, "
            f"converged={self.converged}, "
            f"assigned_tasks={len(self.best_schedule.assignments)}, "
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
    Optimizes task assignment into a weekly schedule using an evolutionary algorithm.

    Workflow:
      1. Generates the first population containing:
         - A schedule based strictly on earliest deadlines.
         - A schedule based strictly on task focus correlation with productivity curve.
         - Mixed combinations of both.
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
                    score=elite.score
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

            next_population.append(Individual(permutation=c1_perm, placement_bias=b1))
            if len(next_population) < cfg.population_size:
                next_population.append(Individual(permutation=c2_perm, placement_bias=b2))

        # Decode and score the newly formed population
        for ind in next_population:
            if ind.schedule is None:
                ind.schedule = decode_permutation_to_schedule(
                    ind.permutation,
                    task_list,
                    weekly_schedule,
                    prod_curve,
                    cfg,
                    placement_bias=ind.placement_bias
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
            best_individual.permutation, task_list, weekly_schedule, prod_curve, cfg
        ),
        best_score=best_score,
        best_individual=best_individual,
        history=history,
        generations_run=gen,
        converged=converged,
        config=cfg
    )
