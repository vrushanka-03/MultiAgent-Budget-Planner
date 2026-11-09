"""TripForge food discovery and meal-budget helpers.

Important: Geoapify place listings generally do not guarantee restaurant menu
prices. This module never invents menu prices or assumes fixed breakfast,
lunch, or dinner costs. Missing prices remain None and must be sourced or
provided as estimates by the caller with an explicit label.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")


def search_restaurants(latitude, longitude, radius=3000, limit=30):
    """Find restaurants/cafes/fast-food venues near arbitrary coordinates.

    Returns source-provided details only. Menu prices are not inferred from
    price level, ratings, or hotel-room prices.
    """
    if not GEOAPIFY_API_KEY:
        print("GEOAPIFY_API_KEY is missing; restaurant discovery skipped.")
        return []

    url = "https://api.geoapify.com/v2/places"
    params = {
        "categories": "catering.restaurant,catering.cafe,catering.fast_food",
        "filter": f"circle:{longitude},{latitude},{int(radius)}",
        "bias": f"proximity:{longitude},{latitude}",
        "limit": max(1, min(int(limit), 50)),
        "apiKey": GEOAPIFY_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        print("Geoapify Restaurant Status:", response.status_code)
        if response.status_code != 200:
            print("Restaurant discovery failed:", response.text[:500])
            return []

        restaurants = []
        seen = set()
        for feature in response.json().get("features", []):
            properties = feature.get("properties", {})
            name = properties.get("name")
            lat = properties.get("lat")
            lon = properties.get("lon")
            if not name or lat is None or lon is None:
                continue

            raw = (properties.get("datasource") or {}).get("raw") or {}
            menu_price = properties.get("menu_price", raw.get("menu_price"))
            key = (name.strip().casefold(), round(float(lat), 5), round(float(lon), 5))
            if key in seen:
                continue
            seen.add(key)

            restaurants.append({
                "name": name,
                "latitude": float(lat),
                "longitude": float(lon),
                "distance_m": properties.get("distance"),
                "address": properties.get("formatted") or properties.get("address_line1"),
                "categories": properties.get("categories", []),
                "cuisine": raw.get("cuisine") or raw.get("cuisine_type"),
                "rating": properties.get("rating", raw.get("rating", raw.get("stars"))),
                "review_count": properties.get(
                    "review_count", raw.get("user_ratings_total", raw.get("reviews"))
                ),
                "price_level": properties.get("price_level", raw.get("price_level")),
                "menu_price": menu_price,
                "price_verified": menu_price is not None,
                "website": properties.get("website") or raw.get("website"),
                "phone": properties.get("phone") or raw.get("phone"),
                "opening_hours": properties.get("opening_hours"),
                "source": "Geoapify",
            })

        # Sort by a real menu price only when one is actually supplied; otherwise
        # keep unknown-price venues after priced venues, then use proximity.
        def sort_key(item):
            try:
                price_key = (0, float(item["menu_price"]))
            except (TypeError, ValueError):
                price_key = (1, float("inf"))
            try:
                distance = float(item["distance_m"])
            except (TypeError, ValueError):
                distance = float("inf")
            return (*price_key, distance, item["name"].casefold())

        restaurants.sort(key=sort_key)
        print("Restaurants discovered:", len(restaurants))
        return restaurants

    except (requests.RequestException, ValueError, TypeError) as error:
        print("Restaurant discovery error:", error)
        return []


def calculate_food_budget(travellers, days, meal_cost_ranges):
    """Calculate a food-budget range from externally sourced meal-cost ranges.

    Args:
        travellers: number of travellers (positive integer).
        days: trip duration in days (positive integer).
        meal_cost_ranges: mapping with breakfast/lunch/dinner keys. Each value
            must be a (low, high) tuple of per-person-per-day costs sourced from
            menus or explicitly supplied estimates. No defaults are provided.

    Example input shape (values are intentionally not supplied here):
        {"breakfast": (low, high), "lunch": (low, high), "dinner": (low, high)}
    """
    try:
        travellers = int(travellers)
        days = int(days)
    except (TypeError, ValueError) as error:
        raise ValueError("Travellers and days must be whole numbers.") from error

    if travellers < 1 or days < 1:
        raise ValueError("Travellers and days must both be at least 1.")
    if not isinstance(meal_cost_ranges, dict):
        raise ValueError("meal_cost_ranges must be a mapping for breakfast, lunch, and dinner.")

    required_meals = ("breakfast", "lunch", "dinner")
    missing = [meal for meal in required_meals if meal not in meal_cost_ranges]
    if missing:
        raise ValueError("Missing meal cost ranges for: " + ", ".join(missing))

    per_person_low = 0.0
    per_person_high = 0.0
    meal_breakdown = {}
    for meal in required_meals:
        value = meal_cost_ranges[meal]
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise ValueError(f"{meal} must have a (low, high) cost range.")
        try:
            low, high = float(value[0]), float(value[1])
        except (TypeError, ValueError) as error:
            raise ValueError(f"{meal} range must contain numeric costs.") from error
        if low < 0 or high < low:
            raise ValueError(f"Invalid {meal} range: ensure 0 <= low <= high.")
        meal_breakdown[meal] = {"per_person_low": low, "per_person_high": high}
        per_person_low += low
        per_person_high += high

    multiplier = travellers * days
    return {
        "travellers": travellers,
        "days": days,
        "meal_breakdown": meal_breakdown,
        "per_person_per_day_low": per_person_low,
        "per_person_per_day_high": per_person_high,
        "group_total_low": per_person_low * multiplier,
        "group_total_high": per_person_high * multiplier,
        "basis": "Calculated only from the meal-cost ranges supplied by the caller.",
    }
