import unittest
from datetime import datetime, time, timedelta

from tag import Tag
from task import Task
from week_periods import WeeklySchedule
from physical_activity import (
    PhysicalActivityConfig,
    ScheduledActivity,
    calculate_activity_conditions_penalty,
    calculate_air_quality_slot_penalty,
    calculate_weather_slot_penalty,
    parse_physical_activities_from_weekly_schedule,
    parse_physical_activity,
)
from schedule_optimizer import Schedule, optimize_schedule
from productivity_scoring import create_focus_productivity_scoring_function


class TestPhysicalActivity(unittest.TestCase):

    def test_parse_physical_activity_with_custom_duration(self):
        """
        Verify parsing physical activity of duration passed as argument
        correctly sets slots, start/end times, and returns ScheduledActivity objects.
        """
        ws = WeeklySchedule()
        # Parse physical activity of duration 45 minutes
        activities_45 = parse_physical_activity(
            duration_minutes=45,
            weekly_schedule=ws,
            sessions_per_week=2
        )
        self.assertEqual(len(activities_45), 2)
        for act in activities_45:
            self.assertEqual(act.duration_minutes, 45)
            # 45 minutes = 3 slots (15 min each)
            self.assertEqual(act.end_slot - act.start_slot, 3)

        # Parse physical activity of duration 90 minutes
        activities_90 = parse_physical_activity(
            duration_minutes=90,
            weekly_schedule=ws,
            sessions_per_week=3
        )
        self.assertEqual(len(activities_90), 3)
        for act in activities_90:
            self.assertEqual(act.duration_minutes, 90)
            # 90 minutes = 6 slots
            self.assertEqual(act.end_slot - act.start_slot, 6)

    def test_punish_training_in_bad_weather(self):
        """
        Verify that training in bad weather (rain, thunderstorm, freezing cold)
        incurs high penalties compared to clear, temperate weather.
        """
        # Clear, ideal weather: 20 deg C, 0 rain, clear sky (code 0)
        clear_weather = {
            "weather_code": 0,
            "temperature": 20.0,
            "precipitation": 0.0,
            "wind_speed": 10.0
        }
        pen_clear = calculate_weather_slot_penalty(clear_weather)
        self.assertEqual(pen_clear, 0.0)

        # Bad weather 1: Heavy rain (code 65), 5 mm precipitation
        rainy_weather = {
            "weather_code": 65,
            "temperature": 12.0,
            "precipitation": 5.0,
            "wind_speed": 15.0
        }
        pen_rain = calculate_weather_slot_penalty(rainy_weather)
        # Expected code 65 (75.0) + min(40, 5 * 15 = 40.0) = 115.0
        self.assertGreaterEqual(pen_rain, 100.0)

        # Bad weather 2: Violent thunderstorm (code 99)
        storm_weather = {
            "weather_code": 99,
            "temperature": 18.0,
            "precipitation": 10.0,
            "wind_speed": 45.0
        }
        pen_storm = calculate_weather_slot_penalty(storm_weather)
        # Expected thunderstorm hail (120) + precip (40) + wind (5 * 1.5) = 167.5
        self.assertGreater(pen_storm, 150.0)

        # Bad weather 3: Freezing cold (-8 deg C)
        freezing_weather = {
            "weather_code": 0,
            "temperature": -8.0,
            "precipitation": 0.0,
            "wind_speed": 10.0
        }
        pen_freezing = calculate_weather_slot_penalty(freezing_weather)
        # Expected: 15 + 8 * 3 = 39.0
        self.assertEqual(pen_freezing, 39.0)

        # Bad weather 4: Heat wave (36 deg C)
        hot_weather = {
            "weather_code": 0,
            "temperature": 36.0,
            "precipitation": 0.0,
            "wind_speed": 10.0
        }
        pen_hot = calculate_weather_slot_penalty(hot_weather)
        # Expected: 25 + (36 - 33) * 5 = 40.0
        self.assertEqual(pen_hot, 40.0)

    def test_punish_training_in_bad_air_quality(self):
        """
        Verify that training in bad air quality (poor/hazardous AQI, high PM2.5)
        incurs high penalties compared to clean air.
        """
        # Clean air: European AQI 15 (Good), PM2.5 = 8 ug/m3
        good_air = {
            "european_aqi": 15,
            "pm2_5": 8.0
        }
        pen_good = calculate_air_quality_slot_penalty(good_air)
        self.assertEqual(pen_good, 0.0)

        # Moderate air: European AQI 50 (Moderate)
        mod_air = {
            "european_aqi": 50,
            "pm2_5": 20.0
        }
        pen_mod = calculate_air_quality_slot_penalty(mod_air)
        self.assertEqual(pen_mod, 25.0)

        # Bad air: European AQI 90 (Very Poor) + high PM2.5 (45 ug/m3)
        bad_air = {
            "european_aqi": 90,
            "pm2_5": 45.0
        }
        pen_bad = calculate_air_quality_slot_penalty(bad_air)
        # Expected: 95.0 + (45 - 25) * 1.5 = 95 + 30 = 125.0
        self.assertEqual(pen_bad, 125.0)

        # US AQI Hazardous
        hazardous_us_air = {
            "us_aqi": 320,
            "pm2_5": 80.0
        }
        pen_haz = calculate_air_quality_slot_penalty(hazardous_us_air)
        # Expected: 160 + (80 - 25) * 1.5 = 160 + 50 (capped) = 210.0
        self.assertGreater(pen_haz, 180.0)

    def test_optimizer_avoids_bad_weather_and_smog(self):
        """
        Verify that when parsing/scheduling physical activity, slots with
        bad weather and bad air quality are punished and avoided in favor of
        good weather slots.
        """
        ws = WeeklySchedule()

        # Build mock hourly forecast:
        # Day 0 (Monday): Morning is thunderstorm (code 95) and bad air (AQI 95).
        # Afternoon (15:00 - 18:00) is clear (code 0) and clean air (AQI 15).
        hourly_times = []
        weather_codes = []
        temps = []
        precips = []
        eu_aqis = []
        pm25s = []

        for d in range(7):
            for h in range(24):
                time_str = f"2026-10-{5+d:02d}T{h:02d}:00"
                hourly_times.append(time_str)
                if d == 0 and 7 <= h <= 12:
                    # Stormy morning on day 0
                    weather_codes.append(95)
                    temps.append(10.0)
                    precips.append(8.0)
                    eu_aqis.append(95)
                    pm25s.append(50.0)
                elif d == 0 and 15 <= h <= 18:
                    # Ideal afternoon on day 0
                    weather_codes.append(0)
                    temps.append(20.0)
                    precips.append(0.0)
                    eu_aqis.append(12)
                    pm25s.append(8.0)
                else:
                    # Average weather
                    weather_codes.append(1)
                    temps.append(18.0)
                    precips.append(0.0)
                    eu_aqis.append(20)
                    pm25s.append(10.0)

        weather_fc = {
            "hourly": {
                "time": hourly_times,
                "weather_code": weather_codes,
                "temperature_2m": temps,
                "precipitation": precips,
            }
        }
        air_fc = {
            "hourly": {
                "time": hourly_times,
                "european_aqi": eu_aqis,
                "pm2_5": pm25s,
            }
        }

        # Parse 60-minute physical activity on active day 0
        activities = parse_physical_activity(
            duration_minutes=60,
            weekly_schedule=ws,
            weather_forecast=weather_fc,
            air_quality_forecast=air_fc,
            sessions_per_week=1,
            active_days=[0]
        )

        self.assertEqual(len(activities), 1)
        selected_act = activities[0]
        # Must not be scheduled in the stormy morning (7 to 12)
        self.assertNotIn(selected_act.start_time.hour, range(7, 13), "Training was scheduled during morning thunderstorm!")
        self.assertGreaterEqual(selected_act.start_time.hour, 13)
        # Condition penalties should be zero or negligible
        self.assertEqual(selected_act.weather_penalty, 0.0)
        self.assertEqual(selected_act.air_quality_penalty, 0.0)

    def test_parse_physical_activity_from_weekly_schedule_tags(self):
        """
        Verify that slots tagged with 'Sport' or 'Trening' in WeeklySchedule
        are parsed into ScheduledActivity with evaluated weather & air penalties.
        """
        ws = WeeklySchedule()
        sport_tag = Tag("Sport")
        sport_tag.title = "Sport"

        # Monday 18:00 - 19:30 tagged as Sport
        ws.assign(0, time(18, 0), time(19, 30), sport_tag)

        # Weather with light drizzle (code 51) at 18:00
        weather_fc = {
            "current": {
                "weather_code": 51,
                "temperature": 15.0,
                "precipitation": 1.0,
                "wind_speed": 10.0
            }
        }
        air_fc = {
            "current": {
                "european_aqi": 30,  # Fair air
                "pm2_5": 12.0
            }
        }

        parsed = parse_physical_activities_from_weekly_schedule(
            weekly_schedule=ws,
            weather_forecast=weather_fc,
            air_quality_forecast=air_fc
        )

        self.assertEqual(len(parsed), 1)
        act = parsed[0]
        self.assertEqual(act.day, 0)
        self.assertEqual(act.start_time, time(18, 0))
        self.assertEqual(act.end_time, time(19, 30))
        self.assertEqual(act.duration_minutes, 90)
        # Should have penalties calculated for the drizzle & fair air
        self.assertGreater(act.weather_penalty, 0.0)
        self.assertGreater(act.air_quality_penalty, 0.0)

    def test_full_optimization_with_physical_activity_and_weather(self):
        """
        Verify optimize_schedule includes physical activities, avoids collisions
        with tasks, and exports them to calendar dicts.
        """
        ws = WeeklySchedule()
        work_tag = Tag("Work")
        work_tag.title = "Work"
        ws.assign(range(5), time(9, 0), time(17, 0), work_tag)

        tasks = []
        for i in range(3):
            t = Task()
            t.id = i + 1
            t.description = f"Project Task {i + 1}"
            t.time = 90
            t.focus = 6
            t.tags = [work_tag]
            tasks.append(t)

        weather_fc = {
            "current": {
                "weather_code": 0,
                "temperature": 21.0,
                "precipitation": 0.0,
                "wind_speed": 8.0
            }
        }
        air_fc = {
            "current": {
                "european_aqi": 15,
                "pm2_5": 8.0
            }
        }

        result = optimize_schedule(
            scoring_functions=None,
            task_list=tasks,
            weekly_schedule=ws,
            productivity_curve_data=[0.5] * 96,
            enable_physical_activity=True,
            activity_duration_minutes=60,
            activities_per_week=2,
            weather_forecast=weather_fc,
            air_quality_forecast=air_fc,
            population_size=10,
            max_generations=3,
            random_seed=42
        )

        # Check physical activities are present
        self.assertEqual(len(result.best_schedule.activities), 2)
        for act in result.best_schedule.activities:
            self.assertEqual(act.duration_minutes, 60)

        # Verify no collisions between tasks and physical activities
        act_slots_by_day = {}
        for a in result.best_schedule.activities:
            act_slots_by_day.setdefault(a.day, set()).update(range(a.start_slot, a.end_slot))

        for st in result.best_schedule.assignments:
            task_slots = set(range(st.start_slot, st.end_slot))
            colliding = task_slots & act_slots_by_day.get(st.day, set())
            self.assertEqual(len(colliding), 0, f"Task {st.task.id} collided with activity slots: {colliding}")

        # Check calendar dictionary export includes activities
        cal_dicts = result.to_calendar_dicts()
        act_entries = [entry for entry in cal_dicts if entry.get("is_activity")]
        self.assertEqual(len(act_entries), 2)


if __name__ == "__main__":
    unittest.main()
