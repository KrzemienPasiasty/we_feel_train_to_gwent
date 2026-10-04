import unittest
from datetime import datetime, timedelta, time
from unittest.mock import patch, MagicMock
import customtkinter as ctk

from models.task import Task
from models.tag import Tag
from models.week_periods import WeeklySchedule
import datas
from ui.calendar_my import (
    CalendarFrame,
    TaskWidget,
    ScheduledMealWidget,
    ScheduledActivityWidget,
    _parse_task_duration_minutes,
    rgb_to_hex,
)
from optimizer.schedule_optimizer import (
    optimize_schedule,
    OptimizationConfig,
    OptimizationResult,
    ScheduledTask,
    Schedule,
)


class TestCalendar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        self.original_tasks = list(datas.current_tasks_list)
        self.original_schedules = list(datas.weekly_schedule_list)
        datas.current_tasks_list.clear()
        datas.weekly_schedule_list.clear()

        # Add sample tasks
        t1 = Task()
        t1.id = 1
        t1.description = "Task 1: Work project"
        t1.priority = 1
        t1.deadline = "2026-10-10T14:00:00"
        t1.time = "1h"
        t1.focus = 8
        t1.tags = [Tag(1, "Work", (200, 50, 50), True)]

        t2 = Task()
        t2.id = 2
        t2.description = "Task 2: Buy groceries"
        t2.priority = 3
        t2.deadline = "2026-10-12T10:00:00"
        t2.time = "1:30"
        t2.focus = 4
        t2.tags = [Tag(2, "Home", (50, 200, 50), True)]

        datas.current_tasks_list.extend([t1, t2])

    def tearDown(self):
        datas.current_tasks_list[:] = self.original_tasks
        datas.weekly_schedule_list[:] = self.original_schedules

    def test_duration_parsing(self):
        t = Task()
        t.time = "1h"
        self.assertEqual(_parse_task_duration_minutes(t), 60)

        t.time = "1:30"
        self.assertEqual(_parse_task_duration_minutes(t), 90)

        t.time = "02:15"
        self.assertEqual(_parse_task_duration_minutes(t), 135)

        t.time = "4"
        self.assertEqual(_parse_task_duration_minutes(t), 240)

        t.time = 45
        self.assertEqual(_parse_task_duration_minutes(t), 45)

        t.time = timedelta(minutes=75)
        self.assertEqual(_parse_task_duration_minutes(t), 75)

    def test_rgb_to_hex(self):
        self.assertEqual(rgb_to_hex((255, 0, 0)), "#ff0000")
        self.assertEqual(rgb_to_hex((0, 255, 0)), "#00ff00")
        self.assertEqual(rgb_to_hex("#123456"), "#123456")

    def test_calendar_frame_initialization_weekly(self):
        cal = CalendarFrame(self.root, is_weekly_view=True)
        self.assertTrue(cal.is_weekly_view)
        self.assertEqual(cal.col_count, 7)
        self.assertIsNotNone(cal.organize_btn)
        self.assertIsNotNone(cal.status_label)
        cal.destroy()

    def test_calendar_frame_initialization_daily(self):
        cal = CalendarFrame(self.root, is_weekly_view=False)
        self.assertFalse(cal.is_weekly_view)
        self.assertEqual(cal.col_count, 1)
        cal.destroy()

    def test_calendar_navigation_and_toggle(self):
        cal = CalendarFrame(self.root, is_weekly_view=True)
        initial_date = cal.target_date

        cal._next_period()
        self.assertEqual(cal.target_date.date(), (initial_date + timedelta(days=7)).date())

        cal._prev_period()
        self.assertEqual(cal.target_date.date(), initial_date.date())

        cal._on_view_change("Dzień")
        self.assertFalse(cal.is_weekly_view)
        self.assertEqual(cal.col_count, 1)

        cal._on_view_change("Tydzień")
        self.assertTrue(cal.is_weekly_view)
        self.assertEqual(cal.col_count, 7)
        cal.destroy()

    @patch("datas.save_current_tasks_list_to_json")
    def test_organize_tasks_synchronous_execution(self, mock_save):
        """Verifies that the optimizer schedules tasks and updates assigned_time."""
        ws = WeeklySchedule()
        datas.weekly_schedule_list.append(ws)

        cal = CalendarFrame(self.root, is_weekly_view=True)

        ref_monday = datetime(2026, 10, 5, 0, 0)
        cal.target_date = ref_monday

        # Test running optimize_schedule directly as organize_tasks worker does
        cfg = OptimizationConfig(
            reference_date=ref_monday,
            population_size=10,
            max_generations=10,
            random_seed=42,
        )
        opt_res = optimize_schedule(
            scoring_functions=None,
            task_list=list(datas.current_tasks_list),
            weekly_schedule=ws,
            productivity_curve_data=[0.5] * 96,
            config=cfg,
        )

        self.assertIsInstance(opt_res, OptimizationResult)
        self.assertGreater(len(opt_res.best_schedule.assignments), 0)

        # Apply schedule assignments to tasks
        for st in opt_res.best_schedule.assignments:
            assigned_dt = ref_monday + timedelta(
                days=st.day,
                hours=st.start_time.hour,
                minutes=st.start_time.minute,
            )
            st.task.assigned_time = assigned_dt
            st.task.start = assigned_dt

        cal.last_optimization_result = opt_res
        cal.refresh()

        self.assertGreater(len(cal.task_widgets), 0)
        cal.destroy()


if __name__ == "__main__":
    unittest.main()
