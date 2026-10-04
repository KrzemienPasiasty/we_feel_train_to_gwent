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
        self.assertEqual(len(cal_dicts), len(result.best_schedule.assignments))
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
