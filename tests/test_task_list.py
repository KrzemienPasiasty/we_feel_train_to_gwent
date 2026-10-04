import unittest
from datetime import datetime
from unittest.mock import patch
import customtkinter as ctk

from task import Task
from tag import Tag
import datas
from task_list import TaskListFrame, TaskCard, _format_deadline, _format_time_duration


class TestTaskList(unittest.TestCase):
    def setUp(self):
        self.original_tasks = list(datas.current_tasks_list)
        self.original_done = list(datas.done_tasks_list)
        datas.current_tasks_list.clear()
        datas.done_tasks_list.clear()

        # Add sample tasks
        t1 = Task()
        t1.id = 1
        t1.description = "Test task 1"
        t1.priority = 1
        t1.deadline = "2026-10-10T14:00:00"
        t1.time = "02:00"
        t1.focus = 8
        t1.tags = [Tag(1, "Work", (200, 50, 50), True)]

        t2 = Task()
        t2.id = 2
        t2.description = "Test task 2"
        t2.priority = 3
        t2.deadline = "2026-10-12T10:00:00"
        t2.time = "01:00"
        t2.focus = 5
        t2.tags = [Tag(2, "Home", (50, 200, 50), True)]

        datas.current_tasks_list.extend([t1, t2])

    def tearDown(self):
        datas.current_tasks_list[:] = self.original_tasks
        datas.done_tasks_list[:] = self.original_done

    def test_format_helpers(self):
        self.assertEqual(_format_deadline("2026-10-10T14:00:00"), "2026-10-10 14:00")
        self.assertEqual(_format_deadline(None), "Brak terminu")
        self.assertEqual(_format_time_duration("02:30"), "02:30")
        self.assertEqual(_format_time_duration(None), "Auto / Nie określono")

    @patch("datas.save_current_tasks_list_to_json")
    def test_delete_task(self, mock_save):
        t1 = datas.current_tasks_list[0]
        res = datas.delete_task(t1)
        self.assertTrue(res)
        self.assertEqual(len(datas.current_tasks_list), 1)
        self.assertEqual(datas.current_tasks_list[0].id, 2)
        mock_save.assert_called_once()

    @patch("datas.save_done_tasks_list_to_json")
    @patch("datas.save_current_tasks_list_to_json")
    def test_complete_task(self, mock_save_curr, mock_save_done):
        t1 = datas.current_tasks_list[0]
        res = datas.complete_task(t1)
        self.assertTrue(res)
        self.assertEqual(len(datas.current_tasks_list), 1)
        self.assertEqual(len(datas.done_tasks_list), 1)
        self.assertEqual(datas.done_tasks_list[0].id, 1)
        mock_save_curr.assert_called_once()
        mock_save_done.assert_called_once()

    def test_task_list_frame_ui(self):
        root = ctk.CTk()
        frame = TaskListFrame(root)
        frame.pack()
        root.update_idletasks()

        # Check badge shows count
        self.assertIn("2", frame.count_badge.cget("text"))

        # Test search filter
        frame.search_entry.insert(0, "task 1")
        frame._apply_filters()
        self.assertIn("1 / 2", frame.count_badge.cget("text"))

        # Test priority filter
        frame.search_entry.delete(0, "end")
        frame.priority_filter.set("1 - Krytyczny (⚡)")
        frame._apply_filters()
        self.assertIn("1 / 2", frame.count_badge.cget("text"))

        # Clean up
        root.destroy()


if __name__ == "__main__":
    unittest.main()
