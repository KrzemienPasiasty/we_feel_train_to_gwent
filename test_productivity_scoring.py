import math
import unittest
from datetime import datetime, time, timedelta

from tag import Tag
from task import Task
from week_periods import WeeklySchedule
from schedule_optimizer import (
    DEFAULT_PRIORITY_MULTIPLIERS,
    MealConfig,
    Schedule,
    ScheduledMeal,
    ScheduledTask,
    calculate_meal_spacing_penalty,
    calculate_tag_mismatch_penalty,
    calculate_task_tag_mismatch_overlap,
    get_priority_multiplier,
    optimize_schedule,
    parse_meals_from_weekly_schedule,
)
from productivity_scoring import (
    create_focus_productivity_scoring_function,
    focus_productivity_difference_at_timestamp,
    integrate_focus_productivity_difference,
    integrate_series_difference,
)


class TestProductivityScoring(unittest.TestCase):

    def test_difference_calculation(self):
        # 1. diff > 0: focus = 0.8, prod = 0.5 -> diff = +0.3
        # constant = 2.0 -> abs(0.3 * 2.0) = 0.6
        val_pos = focus_productivity_difference_at_timestamp(0.8, 0.5, positive_constant=2.0)
        self.assertAlmostEqual(val_pos, 0.6)

        # 2. diff <= 0: focus = 0.4, prod = 0.7 -> diff = -0.3
        # abs(-0.3) = 0.3
        val_neg = focus_productivity_difference_at_timestamp(0.4, 0.7, positive_constant=2.0)
        self.assertAlmostEqual(val_neg, 0.3)

        # 3. diff == 0
        val_zero = focus_productivity_difference_at_timestamp(0.5, 0.5, positive_constant=2.0)
        self.assertAlmostEqual(val_zero, 0.0)

    def test_series_integration(self):
        # 4 timestamps, dt = 0.25 hours (15 min each = 1 hour total)
        focus = [0.8, 0.8, 0.3, 0.5]
        prod = [0.4, 0.4, 0.6, 0.5]
        # t0: diff = 0.4 > 0 -> 0.4 * 3.0 = 1.2
        # t1: diff = 0.4 > 0 -> 0.4 * 3.0 = 1.2
        # t2: diff = -0.3 <= 0 -> abs(-0.3) = 0.3
        # t3: diff = 0.0 -> 0.0
        # sum * 0.25 = (1.2 + 1.2 + 0.3 + 0.0) * 0.25 = 2.7 * 0.25 = 0.675
        integral = integrate_series_difference(focus, prod, dt=0.25, positive_constant=3.0)
        self.assertAlmostEqual(integral, 0.675)

    def test_schedule_integration(self):
        ws = WeeklySchedule()
        tag = Tag("Work")
        tag.title = "Work"
        ws.assign(0, time(9, 0), time(10, 0), tag)

        t = Task()
        t.id = 1
        t.focus = 8
        t.time = 60  # 4 slots
        t.tags = [tag]

        st = ScheduledTask(
            task=t,
            day=0,
            start_slot=36,  # 9:00
            end_slot=40,    # 10:00 (4 slots = 1.0 hour)
            start_time=time(9, 0),
            end_time=time(10, 0),
            duration_minutes=60,
        )

        schedule = Schedule(ws)
        schedule.add_assignment(st)

        # Curve has value 5 for all slots
        curve = [5.0] * 96

        # raw focus = 8, prod = 5 -> diff = 3 > 0
        # constant = 2.0 -> abs(3 * 2) = 6.0
        # 4 slots * (dt = 0.25 hours) * 6.0 = 6.0
        integral = integrate_focus_productivity_difference(
            schedule=schedule,
            productivity_curve_data=curve,
            positive_constant=2.0,
            time_unit="hours",
            normalize_scales=False,
            penalize_unassigned=False,
        )
        self.assertAlmostEqual(integral, 6.0)

    def test_priority_multiplier_resolution(self):
        """Test multiplier lookup by integer, uppercase string, lowercase string, and custom dict."""
        self.assertEqual(get_priority_multiplier(1), 1.0)
        self.assertEqual(get_priority_multiplier(2), 1.5)
        self.assertEqual(get_priority_multiplier(3), 2.5)
        self.assertEqual(get_priority_multiplier(4), 4.0)

        self.assertEqual(get_priority_multiplier("LOW"), 1.0)
        self.assertEqual(get_priority_multiplier("medium"), 1.5)
        self.assertEqual(get_priority_multiplier("High"), 2.5)
        self.assertEqual(get_priority_multiplier("CRITICAL"), 4.0)

        # Custom override
        custom_mults = {"CRITICAL": 10.0, 1: 0.5}
        self.assertEqual(get_priority_multiplier("critical", custom_mults), 10.0)
        self.assertEqual(get_priority_multiplier(1, custom_mults), 0.5)
        self.assertEqual(get_priority_multiplier(None, custom_mults), 1.0)

    def test_unassigned_penalty_with_priority_multipliers(self):
        """Verify unassigned task penalty scales according to task priority."""
        ws = WeeklySchedule()
        schedule = Schedule(ws)

        # 3 unassigned tasks with different priorities
        t_low = Task()
        t_low.id = 1
        t_low.priority = 1  # mult = 1.0

        t_med = Task()
        t_med.id = 2
        t_med.priority = "MEDIUM"  # mult = 1.5

        t_crit = Task()
        t_crit.id = 3
        t_crit.priority = 4  # mult = 4.0

        schedule.unassigned_tasks = [t_low, t_med, t_crit]

        # Base penalty = 50.0
        # Expected total = 50 * 1.0 + 50 * 1.5 + 50 * 4.0 = 50 + 75 + 200 = 325.0
        curve = [0.5] * 96
        total = integrate_focus_productivity_difference(
            schedule=schedule,
            productivity_curve_data=curve,
            penalize_unassigned=True,
            unassigned_penalty_per_task=50.0,
        )
        self.assertAlmostEqual(total, 325.0)

        # Check in scoring function adapter
        scorer = create_focus_productivity_scoring_function(
            productivity_curve_data=curve,
            baseline_score=1000.0,
            unassigned_penalty=100.0,
        )
        # Expected penalty = 100 * (1.0 + 1.5 + 4.0) = 650.0
        # Score = 1000 - 650 = 350.0
        score = scorer(schedule)
        self.assertAlmostEqual(score, 350.0)

    def test_tag_mismatch_exponential_growth(self):
        """
        Verify that assigning a task into a sleeping period incurs a penalty
        that grows exponentially with the overlap size.
        """
        ws = WeeklySchedule()
        sleep_tag = Tag("Sleeping")
        sleep_tag.title = "Sleeping"
        # 00:00 to 08:00 (slots 0 to 32) tagged as Sleeping
        ws.assign(0, time(0, 0), time(8, 0), sleep_tag)

        work_tag = Tag("Work")
        work_tag.title = "Work"

        # Task 1: 1 slot overlap with Sleeping period
        t1 = Task()
        t1.id = 1
        t1.tags = [work_tag]
        t1.priority = 1
        st1 = ScheduledTask(
            task=t1, day=0, start_slot=0, end_slot=1,
            start_time=time(0, 0), end_time=time(0, 15), duration_minutes=15
        )

        # Task 2: 2 slots overlap
        t2 = Task()
        t2.id = 2
        t2.tags = [work_tag]
        t2.priority = 1
        st2 = ScheduledTask(
            task=t2, day=0, start_slot=0, end_slot=2,
            start_time=time(0, 0), end_time=time(0, 30), duration_minutes=30
        )

        # Task 4: 4 slots overlap (1 hour)
        t4 = Task()
        t4.id = 4
        t4.tags = [work_tag]
        t4.priority = 1
        st4 = ScheduledTask(
            task=t4, day=0, start_slot=0, end_slot=4,
            start_time=time(0, 0), end_time=time(1, 0), duration_minutes=60
        )

        sched1 = Schedule(ws)
        sched1.add_assignment(st1)

        sched2 = Schedule(ws)
        sched2.add_assignment(st2)

        sched4 = Schedule(ws)
        sched4.add_assignment(st4)

        base_p = 10.0
        growth = 1.5

        p1 = calculate_tag_mismatch_penalty(sched1, base_penalty=base_p, growth_rate=growth, scale_unit=1.0)
        p2 = calculate_tag_mismatch_penalty(sched2, base_penalty=base_p, growth_rate=growth, scale_unit=1.0)
        p4 = calculate_tag_mismatch_penalty(sched4, base_penalty=base_p, growth_rate=growth, scale_unit=1.0)

        # 1 slot: 10 * (1.5^1 - 1) = 5.0
        self.assertAlmostEqual(p1, 5.0)
        # 2 slots: 10 * (1.5^2 - 1) = 12.5
        self.assertAlmostEqual(p2, 12.5)
        # 4 slots: 10 * (1.5^4 - 1) = 10 * (5.0625 - 1) = 40.625
        self.assertAlmostEqual(p4, 40.625)

        # Verify strict superlinear / exponential growth:
        self.assertGreater(p4, 2.0 * p2)
        self.assertGreater(p2, 2.0 * p1)

    def test_matching_tag_no_mismatch_penalty(self):
        """A task scheduled into slots with its own tag must receive 0 mismatch penalty."""
        ws = WeeklySchedule()
        work_tag = Tag("Work")
        work_tag.title = "Work"
        ws.assign(0, time(9, 0), time(17, 0), work_tag)

        t = Task()
        t.id = 1
        t.tags = [work_tag]
        st = ScheduledTask(
            task=t, day=0, start_slot=36, end_slot=40,
            start_time=time(9, 0), end_time=time(10, 0), duration_minutes=60
        )
        sched = Schedule(ws)
        sched.add_assignment(st)

        penalty = calculate_tag_mismatch_penalty(sched)
        self.assertEqual(penalty, 0.0)

    def test_optimizer_avoids_sleeping_period(self):
        """The optimizer should place tasks into Work slots, avoiding Sleep slots entirely."""
        ws = WeeklySchedule()
        sleep_tag = Tag("Sleep")
        sleep_tag.title = "Sleep"
        # Mark 00:00-08:00 as Sleep
        ws.assign(range(5), time(0, 0), time(8, 0), sleep_tag)

        work_tag = Tag("Work")
        work_tag.title = "Work"
        # Mark 09:00-17:00 as Work
        ws.assign(range(5), time(9, 0), time(17, 0), work_tag)

        tasks = []
        for i in range(3):
            t = Task()
            t.id = i + 1
            t.tags = [work_tag]
            t.time = 60  # 1 hour
            t.priority = 2
            tasks.append(t)

        curve = [0.5] * 96
        scorer = create_focus_productivity_scoring_function(
            productivity_curve_data=curve,
            penalize_tag_mismatch=True
        )

        result = optimize_schedule(
            scoring_functions=scorer,
            task_list=tasks,
            weekly_schedule=ws,
            productivity_curve_data=curve,
            population_size=10,
            max_generations=5,
            penalize_tag_mismatch=True,
            random_seed=42,
        )

        # All scheduled tasks should avoid slots 0 to 31 (00:00 - 08:00 Sleep period)
        for st in result.best_schedule.assignments:
            overlap = calculate_task_tag_mismatch_overlap(st, ws)
            self.assertEqual(overlap, 0, f"Task {st.task.id} overlapped with sleep slots!")

    def test_meal_spacing_penalty_within_limits(self):
        """Meals with spacing between min (180 min) and max (300 min) incur 0 penalty."""
        ws = WeeklySchedule()
        sched = Schedule(ws)

        # Meal 1: 08:00 to 08:30 (slots 32 to 34)
        m1 = ScheduledMeal(
            meal_index=0, name="Breakfast", day=0,
            start_slot=32, end_slot=34,
            start_time=time(8, 0), end_time=time(8, 30), duration_minutes=30
        )
        # Meal 2: 12:30 to 13:00 (slots 50 to 52) -> gap = (50 - 34) * 15 = 240 min (4h)
        m2 = ScheduledMeal(
            meal_index=1, name="Lunch", day=0,
            start_slot=50, end_slot=52,
            start_time=time(12, 30), end_time=time(13, 0), duration_minutes=30
        )
        # Meal 3: 17:30 to 18:00 (slots 70 to 72) -> gap = (70 - 52) * 15 = 270 min (4.5h)
        m3 = ScheduledMeal(
            meal_index=2, name="Dinner", day=0,
            start_slot=70, end_slot=72,
            start_time=time(17, 30), end_time=time(18, 0), duration_minutes=30
        )

        sched.add_meal(m1)
        sched.add_meal(m2)
        sched.add_meal(m3)

        penalty = calculate_meal_spacing_penalty(
            schedule=sched,
            min_time_between_meals_minutes=180,
            max_time_between_meals_minutes=300,
            penalty_per_minute=0.5,
            expected_meals_per_day=3,
            active_days=[0]
        )
        self.assertEqual(penalty, 0.0)

    def test_meal_spacing_penalty_too_short_and_too_long(self):
        """
        Verify penalties for periods shorter than min limit and longer than max limit:
        - min limit = 180 min (3h)
        - max limit = 300 min (5h)
        - rate = 0.5 per minute
        """
        ws = WeeklySchedule()
        sched = Schedule(ws)

        # Meal 1: 08:00 to 08:30 (end_slot=34)
        m1 = ScheduledMeal(
            meal_index=0, name="Breakfast", day=0,
            start_slot=32, end_slot=34,
            start_time=time(8, 0), end_time=time(8, 30), duration_minutes=30
        )
        # Meal 2: 10:00 to 10:30 (start_slot=40, end_slot=42)
        # gap = (40 - 34) * 15 = 90 min -> shortfall = 180 - 90 = 90 min -> penalty = 90 * 0.5 = 45.0
        m2 = ScheduledMeal(
            meal_index=1, name="Lunch", day=0,
            start_slot=40, end_slot=42,
            start_time=time(10, 0), end_time=time(10, 30), duration_minutes=30
        )
        # Meal 3: 17:30 to 18:00 (start_slot=70, end_slot=72)
        # gap = (70 - 42) * 15 = 420 min -> excess = 420 - 300 = 120 min -> penalty = 120 * 0.5 = 60.0
        m3 = ScheduledMeal(
            meal_index=2, name="Dinner", day=0,
            start_slot=70, end_slot=72,
            start_time=time(17, 30), end_time=time(18, 0), duration_minutes=30
        )

        sched.add_meal(m1)
        sched.add_meal(m2)
        sched.add_meal(m3)

        penalty = calculate_meal_spacing_penalty(
            schedule=sched,
            min_time_between_meals_minutes=180,
            max_time_between_meals_minutes=300,
            penalty_per_minute=0.5,
            expected_meals_per_day=3,
            active_days=[0]
        )
        # Expected: 45.0 + 60.0 = 105.0
        self.assertAlmostEqual(penalty, 105.0)

    def test_meal_parsing_and_optimization(self):
        """Verify meals are parsed into schedules and calendar dicts during optimization."""
        ws = WeeklySchedule()
        work_tag = Tag("Work")
        work_tag.title = "Work"
        ws.assign(range(5), time(9, 0), time(18, 0), work_tag)

        t1 = Task()
        t1.id = 1
        t1.description = "Deep Work 1"
        t1.time = 120
        t1.focus = 8
        t1.tags = [work_tag]

        t2 = Task()
        t2.id = 2
        t2.description = "Deep Work 2"
        t2.time = 90
        t2.focus = 7
        t2.tags = [work_tag]

        tasks = [t1, t2]

        curve = [0.6] * 96
        result = optimize_schedule(
            scoring_functions=None,
            task_list=tasks,
            weekly_schedule=ws,
            productivity_curve_data=curve,
            population_size=10,
            max_generations=4,
            enable_meals=True,
            meals_per_day=3,
            meal_duration_minutes=30,
            min_time_between_meals_minutes=180,
            max_time_between_meals_minutes=300,
            random_seed=42,
        )

        # Check that meals were generated
        self.assertGreater(len(result.best_schedule.meals), 0)

        # Check that calendar dicts contain meals
        cal_dicts = result.to_calendar_dicts()
        meal_entries = [entry for entry in cal_dicts if entry.get("is_meal")]
        self.assertGreater(len(meal_entries), 0)

        # Verify no task collides with any meal
        meal_slots_by_day = {}
        for m in result.best_schedule.meals:
            meal_slots_by_day.setdefault(m.day, set()).update(range(m.start_slot, m.end_slot))

        for st in result.best_schedule.assignments:
            task_slots = set(range(st.start_slot, st.end_slot))
            colliding = task_slots & meal_slots_by_day.get(st.day, set())
            self.assertEqual(len(colliding), 0, f"Task {st.task.id} collided with meal slots: {colliding}")


if __name__ == "__main__":
    unittest.main()
