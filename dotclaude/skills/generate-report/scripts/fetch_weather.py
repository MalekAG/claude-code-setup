#!/usr/bin/env python3
"""
Fetch weather data for Canadian cities from Open-Meteo API.
No API key required - completely free and open source.
https://open-meteo.com/
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

# Default Canadian cities with coordinates
CANADA_CITIES = {
    # West Coast
    "Vancouver": {"lat": 49.2827, "lon": -123.1207, "region": "West Coast"},
    "Victoria": {"lat": 48.4284, "lon": -123.3656, "region": "West Coast"},
    # Prairies
    "Calgary": {"lat": 51.0447, "lon": -114.0719, "region": "Prairies"},
    "Edmonton": {"lat": 53.5461, "lon": -113.4938, "region": "Prairies"},
    "Winnipeg": {"lat": 49.8951, "lon": -97.1384, "region": "Prairies"},
    # Central
    "Toronto": {"lat": 43.6532, "lon": -79.3832, "region": "Central"},
    "Ottawa": {"lat": 45.4215, "lon": -75.6972, "region": "Central"},
    "Montreal": {"lat": 45.5017, "lon": -73.5673, "region": "Central"},
    # Atlantic
    "Halifax": {"lat": 44.6488, "lon": -63.5752, "region": "Atlantic"},
    "St. John's": {"lat": 47.5615, "lon": -52.7126, "region": "Atlantic"},
    # North
    "Whitehorse": {"lat": 60.7212, "lon": -135.0568, "region": "North"},
    "Yellowknife": {"lat": 62.4540, "lon": -114.3718, "region": "North"},
}

BASE_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_weather(lat: float, lon: float, forecast_days: int = 7) -> dict:
    """Fetch weather data from Open-Meteo API."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation_probability",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
            "wind_direction_10m",
        ]),
        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "apparent_temperature_max",
            "apparent_temperature_min",
            "precipitation_sum",
            "precipitation_probability_max",
            "wind_speed_10m_max",
        ]),
        "current": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "weather_code",
            "wind_speed_10m",
            "wind_direction_10m",
            "precipitation",
        ]),
        "timezone": "auto",
        "forecast_days": min(forecast_days, 16),  # Max 16 days
    }

    for attempt in range(3):
        try:
            response = requests.get(BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if attempt < 2:
                print(f"  Retry {attempt + 1}/3 after error: {e}")
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise

    return {}


def weather_code_to_description(code: int) -> str:
    """Convert WMO weather code to human-readable description."""
    codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return codes.get(code, "Unknown")


def process_daily_forecast(data: dict) -> list:
    """Process daily forecast data into structured format."""
    daily = data.get("daily", {})
    dates = daily.get("time", [])

    forecasts = []
    for i, date in enumerate(dates):
        forecasts.append({
            "date": date,
            "high": daily.get("temperature_2m_max", [None])[i],
            "low": daily.get("temperature_2m_min", [None])[i],
            "feels_like_high": daily.get("apparent_temperature_max", [None])[i],
            "feels_like_low": daily.get("apparent_temperature_min", [None])[i],
            "condition": weather_code_to_description(
                daily.get("weather_code", [0])[i] or 0
            ),
            "precip_sum": daily.get("precipitation_sum", [0])[i] or 0,
            "precip_chance": daily.get("precipitation_probability_max", [0])[i] or 0,
            "wind_max": daily.get("wind_speed_10m_max", [0])[i] or 0,
        })

    return forecasts


def fetch_all_cities(cities: dict, forecast_days: int = 7) -> dict:
    """Fetch weather data for all specified cities."""
    results = {
        "generated_at": datetime.now().isoformat(),
        "week_start": datetime.now().strftime("%Y-%m-%d"),
        "week_end": (datetime.now() + timedelta(days=forecast_days - 1)).strftime("%Y-%m-%d"),
        "data_source": "Open-Meteo (https://open-meteo.com/)",
        "regions": {},
        "cities": {},
        "national_summary": {},
    }

    all_temps = []

    for city_name, city_info in cities.items():
        print(f"Fetching weather for {city_name}...")

        try:
            data = fetch_weather(city_info["lat"], city_info["lon"], forecast_days)
            current = data.get("current", {})

            city_data = {
                "name": city_name,
                "region": city_info["region"],
                "coordinates": {"lat": city_info["lat"], "lon": city_info["lon"]},
                "timezone": data.get("timezone", "Unknown"),
                "current": {
                    "temp": current.get("temperature_2m"),
                    "feels_like": current.get("apparent_temperature"),
                    "humidity": current.get("relative_humidity_2m"),
                    "wind_speed": current.get("wind_speed_10m"),
                    "wind_direction": current.get("wind_direction_10m"),
                    "precipitation": current.get("precipitation"),
                    "condition": weather_code_to_description(
                        current.get("weather_code", 0) or 0
                    ),
                },
                "forecast": process_daily_forecast(data),
            }

            results["cities"][city_name] = city_data

            # Add to regional grouping
            region = city_info["region"]
            if region not in results["regions"]:
                results["regions"][region] = []
            results["regions"][region].append(city_name)

            # Collect for national summary
            if current.get("temperature_2m") is not None:
                all_temps.append(current["temperature_2m"])

            # Small delay to be respectful to the API
            time.sleep(0.3)

        except Exception as e:
            print(f"  Warning: Failed to fetch data for {city_name}: {e}")
            continue

    # Calculate national summary
    if all_temps:
        warmest_city = max(
            results["cities"].items(),
            key=lambda x: x[1]["current"]["temp"] or -999
        )[0]
        coldest_city = min(
            results["cities"].items(),
            key=lambda x: x[1]["current"]["temp"] if x[1]["current"]["temp"] is not None else 999
        )[0]

        results["national_summary"] = {
            "avg_temp": round(sum(all_temps) / len(all_temps), 1),
            "max_temp": round(max(all_temps), 1),
            "min_temp": round(min(all_temps), 1),
            "warmest_city": warmest_city,
            "coldest_city": coldest_city,
            "cities_covered": len(results["cities"]),
        }

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Canadian weather data from Open-Meteo (free, no API key)"
    )
    parser.add_argument("--output", "-o", default=".tmp/canada_weather.json",
                        help="Output JSON file path")
    parser.add_argument("--cities", "-c", type=str, default=None,
                        help="Comma-separated list of cities (default: all major cities)")
    parser.add_argument("--days", "-d", type=int, default=7,
                        help="Number of forecast days (default: 7, max: 16)")

    args = parser.parse_args()

    # Filter cities if specified
    if args.cities:
        city_list = [c.strip() for c in args.cities.split(",")]
        cities = {k: v for k, v in CANADA_CITIES.items() if k in city_list}
        if not cities:
            print(f"Error: No valid cities found in: {args.cities}")
            print(f"Available cities: {', '.join(CANADA_CITIES.keys())}")
            sys.exit(1)
    else:
        cities = CANADA_CITIES

    print(f"Fetching weather data for {len(cities)} Canadian cities...")
    print(f"Data source: Open-Meteo (free, no API key required)\n")

    # Fetch all weather data
    weather_data = fetch_all_cities(cities, args.days)

    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save to JSON
    with open(output_path, "w") as f:
        json.dump(weather_data, f, indent=2)

    print(f"\nWeather data saved to: {output_path}")
    print(f"Cities covered: {weather_data['national_summary'].get('cities_covered', 0)}")
    print(f"Week: {weather_data['week_start']} to {weather_data['week_end']}")

    if weather_data["national_summary"]:
        print(f"\nNational Summary:")
        print(f"  Average temp: {weather_data['national_summary']['avg_temp']}C")
        print(f"  Warmest: {weather_data['national_summary']['warmest_city']}")
        print(f"  Coldest: {weather_data['national_summary']['coldest_city']}")


if __name__ == "__main__":
    main()
