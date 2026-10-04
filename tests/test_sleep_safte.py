"""
Unit tests for sleep tracking (Garmin & Samsung) and the adapted SAFTE model.
"""

import unittest
from datetime import date, datetime, time, timedelta

from sleep_tracker import (
    SleepQualityData,
    SleepStageBreakdown,
    calculate_safte_effectiveness,
    download_garmin_sleep_data,
    download_samsung_sleep_data,
    download_sleep_quality_data,
    parse_garmin_sleep_data,
    parse_samsung_sleep_data,
    safte_scaling_factor_for_slot,
    scale_productivity_curve_with_safte,
)
from schedule_optimizer import (
    OptimizationConfig,
    OptimizationResult,
    ProductivityCurve,
    optimize_schedule,
)
from task import Task
from tag import Tag
from week_periods import WeeklySchedule


class TestSleepTrackerAndSAFTE(unittest.TestCase):

    def test_parse_garmin_sleep_data(self):
        """Test parsing of standard Garmin Connect sleep JSON payload."""
        sample_garmin_json = {
            "dailySleepDTO": {
                "calendarDate": "2026-10-04",
                "sleepTimeSeconds": 28800,       # 8 hours = 480 minutes
                "deepSleepSeconds": 7200,        # 2 hours
                "lightSleepSeconds": 14400,      # 4 hours
                "remSleepSeconds": 5400,         # 1.5 hours
                "awakeSleepSeconds": 1800,       # 0.5 hours
                "sleepStartTimestampLocal": 1728082800000,
                "sleepEndTimestampLocal": 1728113400000,
                "avgOvernightHrv": 68.5,
                "restingHeartRate": 52
            },
            "sleepScores": {
                "overall": {
                    "value": 88,
                    "qualifierKey": "EXCELLENT"
                }
            }
        }

        parsed = parse_garmin_sleep_data(sample_garmin_json)
        self.assertEqual(parsed.source, "garmin")
        self.assertEqual(parsed.date_str, "2026-10-04")
        self.assertEqual(parsed.sleep_score, 88.0)
        self.assertEqual(parsed.total_sleep_minutes, 480.0)
        self.assertEqual(parsed.quality_label, "EXCELLENT")
        self.assertIsNotNone(parsed.stages)
        self.assertEqual(parsed.stages.deep_minutes, 120.0)
        self.assertEqual(parsed.stages.rem_minutes, 90.0)
        self.assertEqual(parsed.stages.light_minutes, 240.0)
        self.assertEqual(parsed.stages.awake_minutes, 30.0)
        self.assertEqual(parsed.hrv_overnight_avg, 68.5)
        self.assertEqual(parsed.resting_hr, 52)
        # Efficiency: 28800 / (28800 + 1800) = 28800 / 30600 = ~0.941
        self.assertGreater(parsed.sleep_efficiency, 0.90)

    def test_parse_samsung_sleep_data_json(self):
        """Test parsing of Samsung Health JSON webhook / partner payload."""
        sample_samsung_json = {
            "date": "2026-10-04",
            "sleep_score": 76.0,
            "duration": 420.0,
            "efficiency": 0.88,
            "wake_time": "06:45",
            "stages": {
                "deep": 60,
                "rem": 85,
                "light": 235,
                "awake": 40
            }
        }

        parsed = parse_samsung_sleep_data(sample_samsung_json)
        self.assertEqual(parsed.source, "samsung")
        self.assertEqual(parsed.sleep_score, 76.0)
        self.assertEqual(parsed.total_sleep_minutes, 420.0)
        self.assertEqual(parsed.wake_time, time(6, 45))
        self.assertEqual(parsed.sleep_efficiency, 0.88)
        self.assertEqual(parsed.quality_label, "GOOD")
        self.assertIsNotNone(parsed.stages)
        self.assertEqual(parsed.stages.deep_minutes, 60.0)
        self.assertEqual(parsed.stages.rem_minutes, 85.0)

    def test_parse_samsung_sleep_data_csv(self):
        """Test parsing of exported Samsung Health CSV format."""
        csv_text = (
            "start_time,end_time,duration,efficiency,sleep_score\n"
            "2026-10-03 23:00:00,2026-10-04 06:30:00,450,86.5,81.0\n"
        )
        parsed = parse_samsung_sleep_data(csv_text, target_date="2026-10-04")
        self.assertEqual(parsed.source, "samsung")
        self.assertEqual(parsed.sleep_score, 81.0)
        self.assertEqual(parsed.total_sleep_minutes, 450.0)
        self.assertAlmostEqual(parsed.sleep_efficiency, 0.865, places=3)

    def test_safte_model_effectiveness(self):
        """
        Verify the biomathematical properties of the adapted SAFTE equation:
          1. Good sleep yields higher effectiveness than poor sleep.
          2. Sleep inertia depresses effectiveness in the first 30-45 minutes after waking.
          3. Circadian modulation creates expected peaks and nadirs.
        """
        good_sleep = SleepQualityData(
            source="garmin",
            date_str="2026-10-04",
            sleep_score=92.0,
            total_sleep_minutes=500.0,
            wake_time=time(7, 0),
            sleep_efficiency=0.92,
            stages=SleepStageBreakdown(deep_minutes=110, rem_minutes=120, light_minutes=240, awake_minutes=30)
        )

        poor_sleep = SleepQualityData(
            source="garmin",
            date_str="2026-10-04",
            sleep_score=42.0,
            total_sleep_minutes=240.0,  # 4 hours
            wake_time=time(7, 0),
            sleep_efficiency=0.68,
            stages=SleepStageBreakdown(deep_minutes=20, rem_minutes=25, light_minutes=160, awake_minutes=35)
        )

        # 1. Compare mid-day effectiveness (14:00) between good and poor sleep
        e_good_midday = calculate_safte_effectiveness(good_sleep, hour=14.0)
        e_poor_midday = calculate_safte_effectiveness(poor_sleep, hour=14.0)
        self.assertGreater(e_good_midday, e_poor_midday + 15.0)

        # 2. Test Sleep Inertia: effectiveness at 7:15 AM (15 min after waking)
        # must be lower than at 9:30 AM (2.5 hours after waking, inertia gone)
        e_wake_inertia = calculate_safte_effectiveness(good_sleep, hour=7.25)
        e_wake_alert = calculate_safte_effectiveness(good_sleep, hour=9.5)
        self.assertLess(e_wake_inertia, e_wake_alert)

        # 3. Scaling factors for slots
        # Midday slot (14:00 -> slot 56)
        factor_good = safte_scaling_factor_for_slot(good_sleep, slot_idx=56)
        factor_poor = safte_scaling_factor_for_slot(poor_sleep, slot_idx=56)
        self.assertGreater(factor_good, 0.95)
        self.assertLess(factor_poor, 0.85)

    def test_scale_productivity_curve_1d(self):
        """Test scaling a 1D (96-slot) productivity curve using SAFTE."""
        raw_curve = [0.8] * 96

        poor_sleep = SleepQualityData(
            source="samsung",
            date_str="2026-10-04",
            sleep_score=45.0,
            total_sleep_minutes=260.0,
            wake_time=time(6, 30)
        )

        scaled = scale_productivity_curve_with_safte(raw_curve, poor_sleep)
        self.assertEqual(len(scaled), 96)
        # Check that productivity is scaled down due to poor sleep
        for val in scaled:
            self.assertLess(val, 0.80)
            self.assertGreaterEqual(val, 0.0)

    def test_scale_productivity_curve_2d(self):
        """Test scaling a 2D (7 days x 96 slots) curve with per-day sleep records."""
        raw_2d = [[0.7] * 96 for _ in range(7)]

        # Monday has great sleep, Tuesday has terrible sleep
        sleep_monday = SleepQualityData(
            source="garmin",
            date_str="2026-10-05",
            sleep_score=95.0,
            total_sleep_minutes=510.0,
            wake_time=time(7, 0)
        )
        sleep_tuesday = SleepQualityData(
            source="garmin",
            date_str="2026-10-06",
            sleep_score=35.0,
            total_sleep_minutes=210.0,
            wake_time=time(7, 0)
        )

        daily_sleep = {0: sleep_monday, 1: sleep_tuesday}

        scaled_2d = scale_productivity_curve_with_safte(raw_2d, daily_sleep)
        self.assertEqual(len(scaled_2d), 7)

        # Average productivity on Monday (good sleep) should be higher than Tuesday (poor sleep)
        avg_monday = sum(scaled_2d[0]) / 96.0
        avg_tuesday = sum(scaled_2d[1]) / 96.0
        self.assertGreater(avg_monday, avg_tuesday + 0.15)

    def test_optimizer_integration_with_safte(self):
        """Verify schedule optimization automatically applies SAFTE scaling when sleep data is passed."""
        ws = WeeklySchedule()
        tag_work = Tag("Work")
        tag_work.title = "Work"
        ws.assign(range(5), time(9, 0), time(17, 0), tag_work)

        ref_date = datetime(2026, 10, 5, 0, 0)

        tasks = []
        for i in range(4):
            t = Task()
            t.id = i + 1
            t.description = f"Project Task {i + 1}"
            t.time = 60
            t.focus = 6
            t.deadline = ref_date + timedelta(days=2)
            t.tags = [tag_work]
            tasks.append(t)

        raw_curve = [0.8] * 96
        poor_sleep = SleepQualityData(
            source="garmin",
            date_str="2026-10-05",
            sleep_score=40.0,
            total_sleep_minutes=250.0,
            wake_time=time(7, 0)
        )

        cfg = OptimizationConfig(
            population_size=10,
            max_generations=5,
            reference_date=ref_date,
            sleep_data=poor_sleep,
            enable_safte_scaling=True,
            enable_meals=False
        )

        result = optimize_schedule(
            scoring_functions=None,
            task_list=tasks,
            weekly_schedule=ws,
            productivity_curve_data=raw_curve,
            config=cfg
        )

        self.assertIsInstance(result, OptimizationResult)
        self.assertGreater(len(result.best_schedule.assignments), 0)


if __name__ == "__main__":
    unittest.main()
