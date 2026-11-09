
import math
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import requests
import os
from dotenv import load_dotenv

load_dotenv()

def estimate_fuel_cost(distance_km, mileage_kmpl, fuel_price_per_litre):
    """Estimate fuel cost for a vehicle journey."""
    if distance_km < 0 or mileage_kmpl <= 0 or fuel_price_per_litre < 0:
        raise ValueError("Distance and fuel price must be non-negative; mileage must be positive.")

    return round(
        (distance_km / mileage_kmpl) * fuel_price_per_litre,
        2,
    )


def estimate_private_car_cost(
    distance_km,
    mileage_kmpl=15,
    fuel_price_per_litre=100,
    toll_cost=0,
):
    """Estimate private-car fuel and toll costs for a round trip."""
    fuel_cost = estimate_fuel_cost(
        distance_km,
        mileage_kmpl,
        fuel_price_per_litre,
    )

    return {
        "transport": "Private car",
        "fuel_cost": fuel_cost,
        "toll_cost": round(max(0, toll_cost), 2),
        "total_cost": round(fuel_cost + max(0, toll_cost), 2),
        "is_estimate": True,
    }


def estimate_bike_rental_cost(
    rental_per_day,
    days,
    distance_km=0,
    mileage_kmpl=40,
    fuel_price_per_litre=100,
):
    """Estimate bike rental and fuel costs."""
    if rental_per_day < 0 or days < 1:
        raise ValueError("Rental cost must be non-negative and days must be at least 1.")

    fuel_cost = estimate_fuel_cost(
        distance_km,
        mileage_kmpl,
        fuel_price_per_litre,
    )

    rental_cost = rental_per_day * days

    return {
        "transport": "Bike / scooter rental",
        "rental_cost": round(rental_cost, 2),
        "fuel_cost": fuel_cost,
        "total_cost": round(rental_cost + fuel_cost, 2),
        "is_estimate": True,
    }


def estimate_auto_or_cab_cost(
    estimated_fare_per_trip,
    number_of_trips,
    travellers=1,
):
    """Estimate auto/cab costs for a group."""
    if estimated_fare_per_trip < 0 or number_of_trips < 0 or travellers < 1:
        raise ValueError("Fare and trip count must be non-negative; travellers must be at least 1.")

    total = estimated_fare_per_trip * number_of_trips

    return {
        "transport": "Auto / cab",
        "number_of_trips": number_of_trips,
        "travellers": travellers,
        "total_cost": round(total, 2),
        "cost_per_traveller": round(total / travellers, 2),
        "is_estimate": True,
    }

def get_destination_coordinates(destination, country="India"):
    """
    Find a destination's coordinates using OpenStreetMap Nominatim.
    Returns latitude and longitude, or None if not found.
    """

    if not destination or not destination.strip():
        print("Destination cannot be empty.")
        return None

    geolocator = Nominatim(
        user_agent="TripForge_LocalTransport/1.0"
    )

    try:
        location = geolocator.geocode(
            f"{destination.strip()}, {country}",
            exactly_one=True,
            timeout=10,
        )

        if location is None:
            print(f"Location not found: {destination}")
            return None

        result = {
            "destination": location.address,
            "latitude": location.latitude,
            "longitude": location.longitude,
        }

        print("\n========== DESTINATION COORDINATES ==========")
        print("Destination:", result["destination"])
        print("Latitude:", result["latitude"])
        print("Longitude:", result["longitude"])

        return result

    except Exception as error:
        print("Location lookup failed:", error)
        return None

def find_local_transport_services(latitude, longitude, radius=5000):
    """
    Find mapped local transport services near a destination
    using the OpenStreetMap Overpass API.
    """

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Invalid latitude or longitude.")

    radius = max(100, min(int(radius), 10000))

    overpass_url = (
    "https://overpass.private.coffee/api/interpreter"
    )

    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="taxi"](around:{radius},{latitude},{longitude});
      node["shop"="car"](around:{radius},{latitude},{longitude});
      node["shop"="motorcycle"](around:{radius},{latitude},{longitude});
      node["amenity"="car_rental"](around:{radius},{latitude},{longitude});
      node["amenity"="bicycle_rental"](around:{radius},{latitude},{longitude});
      way["amenity"="taxi"](around:{radius},{latitude},{longitude});
      way["amenity"="car_rental"](around:{radius},{latitude},{longitude});
      way["shop"="car"](around:{radius},{latitude},{longitude});
      way["shop"="motorcycle"](around:{radius},{latitude},{longitude});
    );
    out center tags;
    """

    try:
        response = requests.post(
            overpass_url,
            data={"data": query},
            headers={
                "User-Agent": "TripForge/1.0 (local transport discovery)",
                "Accept": "application/json",
            },
            timeout=35,
        )

        if response.status_code == 406:
            print("Overpass rejected the request (HTTP 406).")
            print("Response:", response.text[:500])
            return []

        response.raise_for_status()

        elements = response.json().get("elements", [])

        services = []

        for item in elements:
            tags = item.get("tags", {})
            center = item.get("center", {})

            services.append({
                "name": tags.get("name", "Unnamed service"),
                "type": (
                    tags.get("amenity")
                    or tags.get("shop")
                    or "transport"
                ),
                "latitude": item.get("lat", center.get("lat")),
                "longitude": item.get("lon", center.get("lon")),
                "website": tags.get("website"),
                "phone": tags.get("phone"),
            })

        # Remove duplicate mapped entries.
        unique_services = {
            (
                service["name"],
                service["latitude"],
                service["longitude"],
                service["type"],
            ): service
            for service in services
        }

        results = list(unique_services.values())

        print("Mapped transport services found:", len(results))
        for service in results:
            print(service)

        return results

    except (requests.RequestException, ValueError) as error:
        print("Transport service lookup failed:", error)
        return []



def get_road_route(
    origin_latitude,
    origin_longitude,
    destination_latitude,
    destination_longitude,
    travel_mode="car",
):
    """Get road distance and estimated travel time from TomTom."""

    api_key = os.getenv("TOMTOM_API_KEY")

    if not api_key:
        print("TOMTOM_API_KEY is missing from .env")
        return None

    supported_modes = {"car", "motorcycle", "taxi"}

    if travel_mode not in supported_modes:
        raise ValueError(
            f"Choose one of: {', '.join(sorted(supported_modes))}"
        )

    locations = (
        f"{origin_latitude},{origin_longitude}:"
        f"{destination_latitude},{destination_longitude}"
    )

    url = (
        "https://api.tomtom.com/routing/1/"
        f"calculateRoute/{locations}/json"
    )

    params = {
        "key": api_key,
        "travelMode": travel_mode,
        "routeType": "fastest",
        "traffic": "true",
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        if not response.ok:
            print("TomTom status:", response.status_code)
            print("TomTom error details:", response.text)
            return None
        data = response.json()
        routes = data.get("routes", [])

        if not routes:
            print("TomTom did not return a route.")
            return None

        summary = routes[0]["summary"]

        distance_km = summary["lengthInMeters"] / 1000
        duration_minutes = summary["travelTimeInSeconds"] / 60

        return {
            "travel_mode": travel_mode,
            "distance_km": round(distance_km, 2),
            "duration_minutes": round(duration_minutes),
            "is_estimate": True,
            "source": "TomTom Routing API",
        }

    except requests.RequestException as error:
        print("TomTom route request failed:", error)
        return None
    except (KeyError, ValueError, TypeError) as error:
        print("Could not parse TomTom route response:", error)
        return None


def estimate_local_taxi_fare(
    distance_km,
    fare_per_km=20,
    base_fare=40,
    travellers=1,
):
    """Estimate a local taxi/auto fare from distance."""

    if distance_km < 0 or fare_per_km < 0 or base_fare < 0:
        raise ValueError("Distance and fare rates cannot be negative.")

    if travellers < 1:
        raise ValueError("Travellers must be at least 1.")

    total_fare = base_fare + (distance_km * fare_per_km)

    return {
        "transport": "Estimated local taxi/auto",
        "distance_km": round(distance_km, 2),
        "estimated_fare": round(total_fare, 2),
        "cost_per_traveller": round(total_fare / travellers, 2),
        "currency": "INR",
        "is_estimate": True,
        "source": "Configurable fare estimate",
    }


def estimate_local_taxi_fare(
    distance_km,
    fare_per_km=20,
    base_fare=40,
    travellers=1,
):
    """Estimate a local taxi/auto fare from distance."""

    if distance_km < 0 or fare_per_km < 0 or base_fare < 0:
        raise ValueError("Distance and fare rates cannot be negative.")

    if travellers < 1:
        raise ValueError("Travellers must be at least 1.")

    total_fare = base_fare + (distance_km * fare_per_km)

    return {
        "transport": "Estimated local taxi/auto",
        "distance_km": round(distance_km, 2),
        "estimated_fare": round(total_fare, 2),
        "cost_per_traveller": round(total_fare / travellers, 2),
        "currency": "INR",
        "is_estimate": True,
        "source": "Configurable fare estimate",
    }

def estimate_local_transport_trip(
    origin_latitude,
    origin_longitude,
    destination_latitude,
    destination_longitude,
    estimated_fare_per_km=20,
    base_fare=40,
    travellers=1,
):
    """Estimate local auto/cab cost using TomTom road distance."""

    route = get_road_route(
        origin_latitude,
        origin_longitude,
        destination_latitude,
        destination_longitude,
        travel_mode="car",
    )

    if not route:
        return None

    estimated_fare = base_fare + (
        route["distance_km"] * estimated_fare_per_km
    )

    result = estimate_auto_or_cab_cost(
        estimated_fare_per_trip=estimated_fare,
        number_of_trips=1,
        travellers=travellers,
    )

    result["distance_km"] = route["distance_km"]
    result["estimated_fare_per_trip"] = round(estimated_fare, 2)
    result["duration_minutes"] = route["duration_minutes"]
    result["source"] = "TomTom distance + estimated fare"

    return result
