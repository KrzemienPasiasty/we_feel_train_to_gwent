import unittest

try:
    from apis.weatherAPI import (
        interpret_weather_code,
        interpret_european_aqi,
        interpret_us_aqi,
        geocode_location,
        fetch_weather,
        fetch_air_quality,
        download_weather_and_air_quality,
    )
except ImportError:
    from weatherAPI import (
        interpret_weather_code,
        interpret_european_aqi,
        interpret_us_aqi,
        geocode_location,
        fetch_weather,
        fetch_air_quality,
        download_weather_and_air_quality,
    )


class TestWeatherAPI(unittest.TestCase):

    def test_interpret_weather_code(self):
        self.assertEqual(interpret_weather_code(0), "Clear sky")
        self.assertEqual(interpret_weather_code(61), "Rain: Slight")
        self.assertEqual(interpret_weather_code(95), "Thunderstorm: Slight or moderate")
        self.assertEqual(interpret_weather_code(None), "Unknown")
        self.assertIn("9999", interpret_weather_code(9999))

    def test_interpret_aqi(self):
        self.assertEqual(interpret_european_aqi(10), "Good")
        self.assertEqual(interpret_european_aqi(30), "Fair")
        self.assertEqual(interpret_european_aqi(50), "Moderate")
        self.assertEqual(interpret_european_aqi(70), "Poor")
        self.assertEqual(interpret_european_aqi(90), "Very Poor")
        self.assertEqual(interpret_european_aqi(110), "Extremely Poor")
        self.assertEqual(interpret_european_aqi(None), "Unknown")

        self.assertEqual(interpret_us_aqi(25), "Good")
        self.assertEqual(interpret_us_aqi(75), "Moderate")
        self.assertEqual(interpret_us_aqi(125), "Unhealthy for Sensitive Groups")
        self.assertEqual(interpret_us_aqi(175), "Unhealthy")
        self.assertEqual(interpret_us_aqi(250), "Very Unhealthy")
        self.assertEqual(interpret_us_aqi(350), "Hazardous")
        self.assertEqual(interpret_us_aqi(None), "Unknown")

    def test_geocode_location(self):
        geo = geocode_location("Krakow")
        self.assertEqual(geo["name"], "Krakow")
        self.assertAlmostEqual(geo["latitude"], 50.06, delta=0.5)
        self.assertAlmostEqual(geo["longitude"], 19.94, delta=0.5)

    def test_geocode_invalid_location(self):
        with self.assertRaises(ValueError):
            geocode_location("NonExistentLocationXYZ123456789")

    def test_fetch_weather_and_air_quality_coordinates(self):
        # Krakow coordinates
        lat, lon = 50.0647, 19.9450
        data = download_weather_and_air_quality(latitude=lat, longitude=lon, forecast_days=1)
        self.assertIn("weather", data)
        self.assertIn("air_quality", data)
        self.assertIn("current", data["weather"])
        self.assertIn("current", data["air_quality"])
        self.assertTrue("temperature" in data["weather"]["current"] or "temperature_2m" in data["weather"]["current"])


if __name__ == "__main__":
    unittest.main()
