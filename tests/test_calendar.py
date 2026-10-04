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
    AddTagToTimeDialog,
    _parse_task_duration_minutes,
    rgb_to_hex,
)
from optimizer.schedule_optimizer import ScheduledMeal
from optimizer.physical_activity import ScheduledActivity
import tempfile
import os
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
        self.original_meals = list(datas.scheduled_meals_list)
        self.original_trainings = list(datas.trainings_list)
        datas.current_tasks_list.clear()
        datas.weekly_schedule_list.clear()
        datas.scheduled_meals_list.clear()
        datas.trainings_list.clear()

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
        datas.scheduled_meals_list[:] = self.original_meals
        datas.trainings_list[:] = self.original_trainings

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

    def test_save_and_load_meals_and_trainings(self):
        """Verifies saving and loading meals and trainings to/from JSON."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f_m:
            meals_file = f_m.name
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f_t:
            trainings_file = f_t.name

        try:
            m = ScheduledMeal(
                meal_index=1,
                name="Healthy Lunch",
                day=2,
                start_slot=48,
                end_slot=50,
                start_time=time(12, 0),
                end_time=time(12, 30),
                duration_minutes=30,
                color="#FF9800",
            )
            m.start_datetime = datetime(2026, 10, 7, 12, 0)
            m.end_datetime = datetime(2026, 10, 7, 12, 30)

            datas.save_scheduled_meals_to_json([m], meals_file)
            loaded_meals = []
            datas.load_scheduled_meals_from_json(loaded_meals, meals_file)
            self.assertEqual(len(loaded_meals), 1)
            self.assertEqual(loaded_meals[0].name, "Healthy Lunch")
            self.assertEqual(loaded_meals[0].start_datetime, datetime(2026, 10, 7, 12, 0))

            a = ScheduledActivity(
                activity_index=1,
                name="Running Session",
                day=3,
                start_slot=32,
                end_slot=36,
                start_time=time(8, 0),
                end_time=time(9, 0),
                duration_minutes=60,
                color="#4CAF50",
                outdoor=True,
            )
            a.start_datetime = datetime(2026, 10, 8, 8, 0)
            a.end_datetime = datetime(2026, 10, 8, 9, 0)

            datas.save_trainings_to_json([a], trainings_file)
            loaded_trainings = []
            datas.load_trainings_from_json(loaded_trainings, trainings_file)
            self.assertEqual(len(loaded_trainings), 1)
            self.assertEqual(loaded_trainings[0].name, "Running Session")
            self.assertEqual(loaded_trainings[0].start_datetime, datetime(2026, 10, 8, 8, 0))
        finally:
            if os.path.exists(meals_file):
                os.remove(meals_file)
            if os.path.exists(trainings_file):
                os.remove(trainings_file)

    def test_add_tag_to_time_dialog_save_and_remove(self):
        """Verifies adding a tag to schedule time intervals via AddTagToTimeDialog."""
        ws = WeeklySchedule()
        datas.weekly_schedule_list.append(ws)

        cal = CalendarFrame(self.root, is_weekly_view=True)

        dialog = AddTagToTimeDialog(
            master=cal,
            default_day=1,  # Tuesday
            default_start_time=time(9, 0),
            default_end_time=time(17, 0),
        )
        dialog.tag_entry.delete(0, "end")
        dialog.tag_entry.insert(0, "DeepFocus")

        # Save tag
        dialog._save_tag()

        # Tag must now be in datas.tags_list and ws.tags()
        matching_tags = [t for t in ws.tags() if t.title == "DeepFocus"]
        self.assertEqual(len(matching_tags), 1)
        tag = matching_tags[0]
        intervals = ws.intervals_for(tag)
        self.assertGreater(len(intervals), 0)

        # Test removing tag
        dialog2 = AddTagToTimeDialog(
            master=cal,
            default_day=1,
            default_start_time=time(9, 0),
            default_end_time=time(17, 0),
            default_tag=tag,
        )
        dialog2._remove_tag()
        self.assertEqual(len(ws.intervals_for(tag)), 0)

        cal.destroy()

    def test_calendar_renders_saved_meals_and_trainings(self):
        """Verifies that CalendarFrame renders persisted meals and trainings."""
        cal = CalendarFrame(self.root, is_weekly_view=True)
        ref_monday = datetime(2026, 10, 5, 0, 0)
        cal.target_date = ref_monday

        m = ScheduledMeal(
            meal_index=1,
            name="Dinner",
            day=0,
            start_slot=72,
            end_slot=74,
            start_time=time(18, 0),
            end_time=time(18, 30),
            duration_minutes=30,
        )
        m.start_datetime = datetime(2026, 10, 5, 18, 0)
        datas.scheduled_meals_list.append(m)

        a = ScheduledActivity(
            activity_index=1,
            name="Morning Gym",
            day=1,
            start_slot=28,
            end_slot=32,
            start_time=time(7, 0),
            end_time=time(8, 0),
            duration_minutes=60,
        )
        a.start_datetime = datetime(2026, 10, 6, 7, 0)
        datas.trainings_list.append(a)

        cal.refresh()

        meal_widgets = [w for w in cal.task_widgets if isinstance(w, ScheduledMealWidget)]
        act_widgets = [w for w in cal.task_widgets if isinstance(w, ScheduledActivityWidget)]

        self.assertEqual(len(meal_widgets), 1)
        self.assertEqual(len(act_widgets), 1)
        cal.destroy()


if __name__ == "__main__":
    unittest.main()
