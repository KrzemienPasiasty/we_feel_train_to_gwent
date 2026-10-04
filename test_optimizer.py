import unittest
from datetime import datetime, time, timedelta
import random

from tag import Tag
from task import Task
from week_periods import WeeklySchedule, Weekday
from schedule_optimizer import (
    OptimizationConfig,
    OptimizationResult,
    ProductivityCurve,
    Schedule,
    ScheduledTask,
    optimize_schedule,
    partially_mixed_crossover,
    mutate_permutation,
    is_eligible_to_reproduce,
    create_initial_population,
    decode_permutation_to_schedule
)


class TestScheduleOptimizer(unittest.TestCase):

    def test_pmx_crossover_validity(self):
        """Test PMX produces valid permutations with no duplicates or omissions."""
        random.seed(42)
        for _ in range(50):
            size = random.randint(3, 20)
            p1 = list(range(size))
            p2 = list(range(size))
            random.shuffle(p1)
            random.shuffle(p2)

            c1, c2 = partially_mixed_crossover(p1, p2)

            self.assertEqual(len(c1), size)
            self.assertEqual(len(c2), size)
            self.assertEqual(sorted(c1), list(range(size)))
            self.assertEqual(sorted(c2), list(range(size)))

    def test_pmx_small_sizes(self):
        c1, c2 = partially_mixed_crossover([0], [0])
        self.assertEqual(c1, [0])
        self.assertEqual(c2, [0])

        c1, c2 = partially_mixed_crossover([0, 1], [1, 0])
        self.assertEqual(sorted(c1), [0, 1])
        self.assertEqual(sorted(c2), [0, 1])

    def test_mutation_validity(self):
        """Ensure mutated permutation remains a valid permutation."""
        p = list(range(10))
        for _ in range(30):
            mutated = mutate_permutation(p, mutation_chance=1.0)
            self.assertEqual(sorted(mutated), list(range(10)))

    def test_reproduction_eligibility_threshold(self):
        """Check the 75% threshold condition."""
        best_prev = 100.0
        # 75% of 100 is 75.0
        self.assertTrue(is_eligible_to_reproduce(75.0, best_prev, threshold=0.75, higher_is_better=True))
        self.assertTrue(is_eligible_to_reproduce(80.0, best_prev, threshold=0.75, higher_is_better=True))
        self.assertFalse(is_eligible_to_reproduce(74.9, best_prev, threshold=0.75, higher_is_better=True))
        self.assertFalse(is_eligible_to_reproduce(50.0, best_prev, threshold=0.75, higher_is_better=True))

    def test_initial_population_structure(self):
        """Verify initial population includes pure deadline, pure focus, and mixed."""
        tag_work = Tag("Work")
        tag_work.title = "Work"

        sched = WeeklySchedule()
        sched.assign(range(5), time(9, 0), time(17, 0), tag_work)

        ref_date = datetime(2026, 10, 5, 0, 0)  # Monday

        tasks = []
        for i in range(5):
            t = Task()
            t.id = i + 1
            t.description = f"Task {i + 1}"
            t.deadline = ref_date + timedelta(days=5 - i, hours=12)
            t.focus = (i + 1) * 2
            t.time = 60
            t.tags = [tag_work]
            tasks.append(t)

        prod_curve = [0.8] * 96
        cfg = OptimizationConfig(population_size=10, reference_date=ref_date)

        pop = create_initial_population(tasks, sched, ProductivityCurve(prod_curve), None, cfg)

        self.assertEqual(len(pop), 10)
        # Check deadline individual has shortest deadline first (task 5 has earliest deadline: 5-4 = 1 day)
        deadline_ind = pop[0]
        self.assertEqual(deadline_ind.placement_bias, "earliest")
        self.assertEqual(deadline_ind.permutation[0], 4)  # Task 5 index

        # Check focus individual has highest focus first (task 5 has focus 10)
        focus_ind = pop[1]
        self.assertEqual(focus_ind.placement_bias, "productivity")
        self.assertEqual(focus_ind.permutation[0], 4)

    def test_specific_tag_assigned_firstly_to_matching_tasks(self):
        """
        Verify that to slots with a specific tag, tasks with the same tag
        are assigned firstly, before untagged tasks or tasks with other tags.
        """
        ws = WeeklySchedule()
        work_tag = Tag("Work")
        work_tag.title = "Work"
        study_tag = Tag("Study")
        study_tag.title = "Study"

        # Monday 09:00 - 11:00 has tag "Work"
        ws.assign(0, time(9, 0), time(11, 0), work_tag)
        # Tuesday 09:00 - 11:00 has tag "Study"
        ws.assign(1, time(9, 0), time(11, 0), study_tag)

        ref_date = datetime(2026, 10, 5, 0, 0)

        # Task 1: Untagged task with an urgent deadline (Monday 10:00)
        t_untagged = Task()
        t_untagged.id = 1
        t_untagged.description = "Urgent general chore"
        t_untagged.time = 60
        t_untagged.deadline = ref_date + timedelta(hours=10)
        t_untagged.tags = []

        # Task 2: Work task with a later deadline (Friday)
        t_work = Task()
        t_work.id = 2
        t_work.description = "Important company work"
        t_work.time = 60
        t_work.deadline = ref_date + timedelta(days=4)
        t_work.tags = [work_tag]

        # Task 3: Study task with a later deadline (Friday)
        t_study = Task()
        t_study.id = 3
        t_study.description = "Exam preparation"
        t_study.time = 60
        t_study.deadline = ref_date + timedelta(days=4)
        t_study.tags = [study_tag]

        tasks = [t_untagged, t_work, t_study]
        cfg = OptimizationConfig(
            reference_date=ref_date,
            assign_same_tag_first=True,
            strict_tag_reservation=True,
            enable_meals=False
        )

        # Decode permutation starting with untagged task [0, 1, 2]
        decoded = decode_permutation_to_schedule(
            permutation=[0, 1, 2],
            tasks=tasks,
            weekly_schedule=ws,
            productivity_curve=ProductivityCurve([0.5] * 96),
            config=cfg
        )

        work_assignment = decoded.task_assignments.get(2)
        study_assignment = decoded.task_assignments.get(3)
        untagged_assignment = decoded.task_assignments.get(1)

        # Task 2 (Work) MUST be assigned to the Work slots (Monday 09:00 - 11:00)
        self.assertIsNotNone(work_assignment)
        self.assertEqual(work_assignment.day, 0)
        self.assertEqual(work_assignment.start_time, time(9, 0))

        # Task 3 (Study) MUST be assigned to the Study slots (Tuesday 09:00 - 11:00)
        self.assertIsNotNone(study_assignment)
        self.assertEqual(study_assignment.day, 1)
        self.assertEqual(study_assignment.start_time, time(9, 0))

        # Task 1 (Untagged) should NOT take the Work or Study slot before matching tasks
        self.assertIsNotNone(untagged_assignment)
        # Should be placed outside Monday 9-10 and Tuesday 9-10
        self.assertFalse(
            (untagged_assignment.day == 0 and untagged_assignment.start_time == time(9, 0)) or
            (untagged_assignment.day == 1 and untagged_assignment.start_time == time(9, 0)),
            "Untagged task stole tagged slots from matching tasks!"
        )

    def test_multiple_tasks_with_same_tag_fill_tagged_slots_first(self):
        """
        Verify that multiple tasks with the same tag claim all available slots
        of that tag before any non-matching tasks can touch them.
        """
        ws = WeeklySchedule()
        work_tag = Tag("Work")
        work_tag.title = "Work"

        # Monday 09:00 - 12:00 has tag "Work" (3 hours = three 60-min slots)
        ws.assign(0, time(9, 0), time(12, 0), work_tag)

        ref_date = datetime(2026, 10, 5, 0, 0)

        # Non-matching task with very early deadline
        t_other = Task()
        t_other.id = 999
        t_other.description = "Urgent non-work errand"
        t_other.time = 60
        t_other.deadline = ref_date + timedelta(hours=9, minutes=30)
        t_other.tags = []

        # 3 tasks with "Work" tag
        work_tasks = []
        for i in range(3):
            t = Task()
            t.id = i + 10
            t.description = f"Work item {i + 1}"
            t.time = 60
            t.deadline = ref_date + timedelta(days=3)
            t.tags = [work_tag]
            work_tasks.append(t)

        tasks = [t_other] + work_tasks  # t_other is index 0
        cfg = OptimizationConfig(
            reference_date=ref_date,
            assign_same_tag_first=True,
            strict_tag_reservation=True,
            enable_meals=False
        )

        decoded = decode_permutation_to_schedule(
            permutation=[0, 1, 2, 3],
            tasks=tasks,
            weekly_schedule=ws,
            productivity_curve=ProductivityCurve([0.5] * 96),
            config=cfg
        )

        # Check all three work tasks are assigned in the Monday 9:00 - 12:00 window
        assigned_work_hours = set()
        for t in work_tasks:
            st = decoded.task_assignments.get(t.id)
            self.assertIsNotNone(st, f"Work task {t.id} was not assigned!")
            self.assertEqual(st.day, 0)
            self.assertTrue(time(9, 0) <= st.start_time < time(12, 0))
            assigned_work_hours.add(st.start_time.hour)

        self.assertEqual(assigned_work_hours, {9, 10, 11})

        # t_other must NOT be in Monday 9-12
        st_other = decoded.task_assignments.get(999)
        self.assertIsNotNone(st_other)
        if st_other.day == 0:
            self.assertFalse(time(9, 0) <= st_other.start_time < time(12, 0))

    def test_full_optimization_run(self):
        """Run full schedule optimization with custom scoring and convergence."""
        tag_study = Tag("Study")
        tag_study.title = "Study"
        tag_study.color = (30, 144, 255)

        ws = WeeklySchedule()
        # Monday to Friday 9:00 - 17:00 assigned to Study
        ws.assign(range(5), time(9, 0), time(17, 0), tag_study)

        ref_date = datetime(2026, 10, 5, 0, 0)

        tasks = []
        for i in range(6):
            t = Task()
            t.id = 100 + i
            t.description = f"Project Work {i + 1}"
            t.deadline = ref_date + timedelta(days=2 + i, hours=14)
            t.focus = 3 + (i % 7)
            t.time = 90  # 1.5 hours = 6 slots
            t.tags = [tag_study]
            tasks.append(t)

        # Productivity curve: morning peak (slots 36 to 48 -> 9:00 to 12:00)
        curve_data = [0.2] * 96
        for s in range(36, 48):
            curve_data[s] = 0.9

        # Custom scoring function
        def custom_scoring(schedule: Schedule) -> float:
            score = 100.0
            for st in schedule.assignments:
                # Reward morning slots
                if st.start_time.hour < 12:
                    score += 15.0
                score += st.task.focus * 2.0
            # Heavily penalize unassigned tasks
            score -= len(schedule.unassigned_tasks) * 50.0
            return score

        result = optimize_schedule(
            scoring_functions=custom_scoring,
            task_list=tasks,
            weekly_schedule=ws,
            productivity_curve_data=curve_data,
            population_size=20,
            reproduction_threshold=0.75,
            convergence_threshold=0.05,
            patience=2,
            mutation_chance=0.2,
            max_generations=20,
            reference_date=ref_date,
            random_seed=42
        )

        self.assertIsInstance(result, OptimizationResult)
        self.assertGreater(result.generations_run, 0)
        self.assertGreater(result.best_score, 0)
        self.assertGreaterEqual(len(result.best_schedule.assignments), 5)

        # Check unpackable behavior
        sched, score = result
        self.assertEqual(score, result.best_score)
        self.assertEqual(sched, result.best_schedule)

        # Check calendar dictionary export for GUI compatibility
        cal_dicts = result.to_calendar_dicts()
        self.assertEqual(len(cal_dicts), len(result.best_schedule.assignments) + len(result.best_schedule.meals))
        task_only_dicts = result.to_calendar_dicts(include_meals=False)
        self.assertEqual(len(task_only_dicts), len(result.best_schedule.assignments))
        for item in cal_dicts:
            self.assertIn("id", item)
            self.assertIn("title", item)
            self.assertIn("day", item)
            self.assertIn("start_time", item)
            self.assertIn("duration_minutes", item)
            self.assertIn("color", item)
            self.assertIn("priority", item)


if __name__ == "__main__":
    unittest.main()
