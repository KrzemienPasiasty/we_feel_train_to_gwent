import unittest
from datetime import datetime, time, timedelta

from models.task import Task
from models.tag import Tag
from models.week_periods import WeeklySchedule, DAYS_IN_WEEK, SLOT_MINUTES
from optimizer.schedule_optimizer import (
    optimize_schedule,
    OptimizationConfig,
    decode_permutation_to_schedule,
    populate_meals_for_schedule,
    Schedule,
)
from optimizer.physical_activity import (
    parse_physical_activity,
    PhysicalActivityConfig,
)


class TestSchedulingFromNow(unittest.TestCase):
    def test_tasks_only_scheduled_from_now_forward(self):
        """Tasks must never be placed into past days/slots when reference_date and min_schedule_datetime are set."""
        ws = WeeklySchedule()
        # Reference Monday: 2026-10-05 00:00:00
        ref_monday = datetime(2026, 10, 5, 0, 0, 0)
        # Suppose current time is Wednesday 14:00 (Day 2, 14:00)
        min_dt = ref_monday + timedelta(days=2, hours=14, minutes=0)

        tasks = []
        for i in range(5):
            t = Task()
            t.id = i + 1
            t.description = f"Task {i + 1}"
            t.time = "1h"
            t.priority = 2
            t.deadline = "2026-10-11T20:00:00"
            tasks.append(t)

        cfg = OptimizationConfig(
            reference_date=ref_monday,
            min_schedule_datetime=min_dt,
            earliest_task_time=time(6, 0),
            latest_task_time=time(23, 0),
            population_size=15,
            max_generations=15,
            random_seed=42,
        )

        res = optimize_schedule(
            scoring_functions=None,
            task_list=tasks,
            weekly_schedule=ws,
            productivity_curve_data=[0.5] * 96,
            config=cfg,
        )

        self.assertGreater(len(res.best_schedule.assignments), 0)
        for st in res.best_schedule.assignments:
            task_dt = ref_monday + timedelta(
                days=st.day,
                hours=st.start_time.hour,
                minutes=st.start_time.minute,
            )
            # Ensure scheduled time is >= min_schedule_datetime
            self.assertGreaterEqual(
                task_dt,
                min_dt,
                f"Task #{st.task.id} scheduled at {task_dt} which is before min_dt {min_dt}",
            )
            # Ensure scheduled time is within daytime hours (06:00 to 23:00)
            self.assertGreaterEqual(st.start_time, time(6, 0))
            self.assertLessEqual(st.end_time, time(23, 0))

    def test_meals_not_scheduled_in_the_past(self):
        """Meals must not be placed into days/slots that are in the past."""
        ws = WeeklySchedule()
        ref_monday = datetime(2026, 10, 5, 0, 0, 0)
        # Current time is Thursday 12:00
        min_dt = ref_monday + timedelta(days=3, hours=12, minutes=0)

        cfg = OptimizationConfig(
            reference_date=ref_monday,
            min_schedule_datetime=min_dt,
            meals_per_day=3,
        )
        sched = Schedule(ws)
        populate_meals_for_schedule(sched, ws, cfg)

        self.assertGreater(len(sched.meals), 0)
        for meal in sched.meals:
            meal_dt = ref_monday + timedelta(
                days=meal.day,
                hours=meal.start_time.hour,
                minutes=meal.start_time.minute,
            )
            self.assertGreaterEqual(
                meal_dt,
                min_dt,
                f"Meal {meal.name} scheduled at {meal_dt} which is before min_dt {min_dt}",
            )

    def test_physical_activities_spread_across_days_no_clustering(self):
        """Physical activity sessions should be spread across distinct days and not all on Monday."""
        ws = WeeklySchedule()
        ref_monday = datetime(2026, 10, 5, 0, 0, 0)

        # Flat weather forecast (all 0 penalty)
        flat_forecast = {
            "hourly": {
                "time": [f"2026-10-{5+d:02d}T{h:02d}:00" for d in range(7) for h in range(24)],
                "weather_code": [0] * (7 * 24),
                "temperature_2m": [18.0] * (7 * 24),
                "precipitation": [0.0] * (7 * 24),
                "wind_speed_10m": [10.0] * (7 * 24),
            },
            "air_quality": {
                "hourly": {
                    "time": [f"2026-10-{5+d:02d}T{h:02d}:00" for d in range(7) for h in range(24)],
                    "european_aqi": [15.0] * (7 * 24),
                }
            }
        }

        cfg = PhysicalActivityConfig(
            duration_minutes=60,
            sessions_per_week=3,
            reference_date=ref_monday,
            min_schedule_datetime=ref_monday,  # from Monday morning forward
        )

        activities = parse_physical_activity(
            duration_minutes=60,
            weekly_schedule=ws,
            weather_forecast=flat_forecast,
            sessions_per_week=3,
            config=cfg,
        )

        self.assertEqual(len(activities), 3)
        days = [a.day for a in activities]
        # In a 7-day week with 3 sessions needed, each session must be on a different day!
        self.assertEqual(len(set(days)), 3, f"Expected 3 distinct days for 3 sessions, got days: {days}")
        # Make sure Monday does NOT have 3 sessions
        mon_sessions = [a for a in activities if a.day == 0]
        self.assertLessEqual(len(mon_sessions), 1, "Monday has more than 1 session!")

    def test_physical_activities_skip_past_days(self):
        """Physical activities must skip days and times before min_schedule_datetime."""
        ws = WeeklySchedule()
        ref_monday = datetime(2026, 10, 5, 0, 0, 0)
        # Current time is Friday 10:00 (Day 4)
        min_dt = ref_monday + timedelta(days=4, hours=10, minutes=0)

        cfg = PhysicalActivityConfig(
            duration_minutes=60,
            sessions_per_week=3,
            reference_date=ref_monday,
            min_schedule_datetime=min_dt,
        )

        activities = parse_physical_activity(
            duration_minutes=60,
            weekly_schedule=ws,
            sessions_per_week=3,
            config=cfg,
        )

        for act in activities:
            act_dt = ref_monday + timedelta(
                days=act.day,
                hours=act.start_time.hour,
                minutes=act.start_time.minute,
            )
            self.assertGreaterEqual(
                act_dt,
                min_dt,
                f"Activity {act.name} scheduled at {act_dt} which is before min_dt {min_dt}",
            )


if __name__ == "__main__":
    unittest.main()
