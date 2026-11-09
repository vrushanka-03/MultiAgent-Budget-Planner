

import os
import json
import math
import time
import requests
import airportsdata
from dotenv import load_dotenv

load_dotenv()

SERPAPI_URL = "https://serpapi.com/search"


# ==========================================
# 1. SEARCH FLIGHTS USING SERPAPI
# ==========================================

def search_flights(origin, destination, departure_date, travellers=1):
    """
    Search one-way Google Flights results through SerpApi.

    Returns:
        list: Normalized flight itineraries.
        []: No results or a non-retryable error.
        None: API quota/rate limit exhausted.

    SerpApi caching is allowed to avoid unnecessary quota usage.
    """

    api_key = os.getenv("SERPAPI_API_KEY")

    if not api_key:
        print("ERROR: SERPAPI_API_KEY is missing from .env")
        return []

    origin = str(origin or "").strip().upper()
    destination = str(destination or "").strip().upper()
    departure_date = str(departure_date or "").strip()

    if not origin or not destination or not departure_date:
        print("ERROR: Origin, destination and date are required.")
        return []

    try:
        travellers = int(travellers)
        if travellers < 1:
            print("ERROR: Travellers must be at least 1.")
            return []
    except (TypeError, ValueError):
        print("ERROR: Invalid traveller count.")
        return []

    params = {
        "engine": "google_flights",
        "api_key": api_key,
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": departure_date,
        "type": "2",                 # One-way trip
        "currency": "INR",
        "hl": "en",
        "gl": "in",
        "adults": travellers,
        # Do not set no_cache=true: cached searches can reduce quota usage.
    }

    # One request per route. Do not automatically retry and spend more quota.
    max_attempts = 1
    data = None

    for attempt in range(1, max_attempts + 1):
        try:
            print(
                f"\nSerpApi flight search "
                f"({attempt}/{max_attempts}): "
                f"{origin} -> {destination}, {departure_date}"
            )

            response = requests.get(
                SERPAPI_URL,
                params=params,
                timeout=90,
            )

            if response.status_code == 429:
                print("SerpApi rate limit or quota reached.")
                print("Check your SerpApi dashboard before retrying.")
                return None

            if response.status_code in (401, 403):
                print(
                    "SerpApi authentication/permission error:",
                    response.status_code,
                )
                print(response.text[:500])
                return []

            if response.status_code >= 500:
                print("Temporary SerpApi server error:",
                      response.status_code)

                if attempt < max_attempts:
                    time.sleep(attempt * 2)
                    continue

                print(response.text[:500])
                return []

            if response.status_code != 200:
                print("SerpApi request failed:",
                      response.status_code)
                print(response.text[:1000])
                return []

            data = response.json()

            if data.get("error"):
                print("SerpApi returned an error:", data["error"])
                return []

            break

        except (requests.Timeout, requests.ConnectionError) as error:
            print("Temporary network problem:", error)

            if attempt < max_attempts:
                time.sleep(attempt * 2)
                continue

            print("Flight search failed after retries.")
            return []

        except (requests.RequestException, ValueError) as error:
            print("Flight API error:", error)
            return []

    if not isinstance(data, dict):
        print("Unexpected SerpApi response format.")
        return []

    # Google Flights separates results into these two collections.
    itineraries = (
        data.get("best_flights", [])
        + data.get("other_flights", [])
    )

    flights = []

    for itinerary in itineraries:
        segments = itinerary.get("flights") or []

        if not segments:
            continue

        first_segment = segments[0]
        last_segment = segments[-1]

        departure_airport = (
            first_segment.get("departure_airport") or {}
        )
        arrival_airport = (
            last_segment.get("arrival_airport") or {}
        )

        airlines = []
        flight_numbers = []

        for segment in segments:
            airline = segment.get("airline")
            flight_number = segment.get("flight_number")

            if airline and airline not in airlines:
                airlines.append(airline)

            if flight_number:
                flight_numbers.append(flight_number)

        layovers = itinerary.get("layovers") or []
        total_duration = itinerary.get("total_duration")
        price = itinerary.get("price")

        # Keep duration in the same general format expected
        # by the existing TripForge flight display.
        duration_text = (
            f"{total_duration} minutes"
            if isinstance(total_duration, (int, float))
            else "Not provided"
        )

        flights.append({
            "airline": ", ".join(airlines) or "Unknown",
            "price": price,
            "currency": "INR",
            "departure": (
                f"{departure_airport.get('time', 'Unknown')} "
                f"({departure_airport.get('id', origin)})"
            ),
            "arrival": (
                f"{arrival_airport.get('time', 'Unknown')} "
                f"({arrival_airport.get('id', destination)})"
            ),
            "duration": duration_text,
            "duration_seconds": (
                total_duration * 60
                if isinstance(total_duration, (int, float))
                else None
            ),
            "stops": len(layovers),
            "flight_numbers": flight_numbers,
            "booking_link": itinerary.get("link"),
            "booking_token": itinerary.get("booking_token"),
        })

    # Sort cheapest first; entries without a numeric price go last.
    flights.sort(
        key=lambda flight: (
            flight["price"]
            if isinstance(flight["price"], (int, float))
            else float("inf")
        )
    )

    print("SerpApi flight itineraries found:", len(flights))

    if not flights:
        print(
            "No flights returned. Check the route, date, "
            "airport codes and SerpApi response."
        )

    return flights


# ==========================================
# 2. BACKWARD-COMPATIBLE FUNCTION NAME
# ==========================================

def search_flights_flightpowers(
    origin, destination, departure_date
):
    """
    Compatibility wrapper.

    Existing main_page.py code can keep calling
    search_flights_flightpowers() without modification.
    """
    return search_flights(
        origin,
        destination,
        departure_date,
        travellers=1,
    )


# ==========================================
# 3. FIND AIRPORT CODE
# ==========================================

def find_airport_code(location):
    """Find a likely airport code by matching a city or airport name."""
    if not location or not str(location).strip():
        return None

    airports = airportsdata.load("IATA")
    search_text = str(location).strip().casefold()

    aliases = {
        "bengaluru": "bangalore",
        "bangalore": "bengaluru",
        "delhi": "new delhi",
        "belgaum": "belagavi",
        "belagavi": "belgaum",
    }
    search_names = {search_text}
    if search_text in aliases:
        search_names.add(aliases[search_text])

    matches = []
    for code, airport in airports.items():
        city = str(airport.get("city") or "").strip().casefold()
        airport_name = str(airport.get("name") or "").strip().casefold()
        if city in search_names or airport_name in search_names:
            try:
                lat = float(airport.get("lat"))
                lon = float(airport.get("lon"))
            except (TypeError, ValueError):
                continue
            matches.append((code, airport, lat, lon))

    if not matches:
        return None

    # Prefer Indian airports when the city has multiple matching records.
    indian_matches = [item for item in matches if item[1].get("country") == "IN"]
    if indian_matches:
        matches = indian_matches

    # Prefer the most substantial/complete match deterministically, rather
    # than relying on whichever record happens to appear first in the dataset.
    matches.sort(key=lambda item: (not bool(item[1].get("city")), item[0]))
    return matches[0][0]


def get_destination_airport(destination):
    """Return a direct city airport only; nearby airports are discovered separately."""
    airport_code = find_airport_code(destination)
    if not airport_code:
        return None

    airport = airportsdata.load("IATA").get(airport_code, {})
    return {
        "airport_code": airport_code,
        "airport_name": airport.get("name", destination),
        "road_distance_km": 0,
        "is_nearby_airport": False,
    }


def get_nearby_destination_airports(
    destination, latitude, longitude, exclude_code=None, max_distance_km=350, limit=3
):
    """Discover nearby airports from destination coordinates. Road distance is an estimate."""
    try:
        destination_lat = float(latitude)
        destination_lon = float(longitude)
    except (TypeError, ValueError):
        return []

    airports = airportsdata.load("IATA")

    def haversine_km(lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))

    candidates = []
    for code, airport in airports.items():
        if code == exclude_code:
            continue
        try:
            airport_lat = float(airport.get("lat"))
            airport_lon = float(airport.get("lon"))
        except (TypeError, ValueError):
            continue

        air_distance = haversine_km(
            destination_lat, destination_lon, airport_lat, airport_lon
        )
        if air_distance <= 5 or air_distance > max_distance_km:
            continue

        # Approximation only; this is not a live road-routing result.
        estimated_road_distance = round(air_distance * 1.25, 1)
        candidates.append({
            "airport_code": code,
            "airport_name": airport.get("name", code),
            "city": airport.get("city", ""),
            "air_distance_km": round(air_distance, 1),
            "road_distance_km": estimated_road_distance,
            "is_nearby_airport": True,
        })

    candidates.sort(key=lambda item: item["air_distance_km"])
    return candidates[:max(1, int(limit))]


# ==========================================
# 5. ESTIMATE ROAD TRANSFER COST
# ==========================================

def estimate_road_transfer_cost(distance_km, cost_per_km=15):
    """Estimate one road transfer cost; this is not a verified fare."""

    try:
        distance = float(distance_km)
        rate = float(cost_per_km)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            "Road-transfer distance and rate must be numeric."
        ) from exc

    if not math.isfinite(distance) or distance < 0:
        raise ValueError("Road distance must be finite and non-negative.")

    if not math.isfinite(rate) or rate < 0:
        raise ValueError("Cost per kilometre must be finite and non-negative.")

    return round(distance * rate, 2)


# ==========================================
# 6. ALTERNATIVE DEPARTURE AIRPORTS
# ==========================================

def get_alternative_departure_airports(
    source,
    source_airport_code=None,
    max_distance_km=500,
    limit=10,
):
    """
    Find alternative airports in the same country.

    Distances are approximate; road distance uses a multiplier
    rather than a live road-routing service.
    """

    airports = airportsdata.load("IATA")

    if source_airport_code is None:
        source_airport_code = find_airport_code(source)

    source_airport = airports.get(source_airport_code)

    if not source_airport:
        print("Could not find the original departure airport.")
        return []

    try:
        source_lat = float(source_airport["lat"])
        source_lon = float(source_airport["lon"])
    except (KeyError, TypeError, ValueError):
        print("Departure airport coordinates are unavailable.")
        return []

    def distance_km(lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(
            math.radians,
            [lat1, lon1, lat2, lon2],
        )

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1)
            * math.cos(lat2)
            * math.sin(dlon / 2) ** 2
        )

        return 6371 * 2 * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a),
        )

    alternatives = []

    for code, airport in airports.items():
        if code == source_airport_code:
            continue

        if airport.get("country") != source_airport.get("country"):
            continue

        try:
            lat = float(airport["lat"])
            lon = float(airport["lon"])
        except (KeyError, TypeError, ValueError):
            continue

        distance = distance_km(
            source_lat,
            source_lon,
            lat,
            lon,
        )

        if 30 < distance <= max_distance_km:
            alternatives.append({
                "airport_code": code,
                "airport_name": airport.get("name", code),
                "city": airport.get("city", ""),
                "air_distance_km": round(distance, 1),
                "road_distance_km": round(distance * 1.25),
            })

    alternatives.sort(
        key=lambda airport: airport["air_distance_km"]
    )

    return alternatives[:limit]



# ==========================================================
# ==========================================================
# TRIPFORGE TRAIN API CONFIGURATION
# Flight functions above this section are intentionally unchanged.
# ==========================================================

from datetime import date, datetime
from math import radians, sin, cos, sqrt, atan2

load_dotenv()

# ==========================================================
# TripForge train API: IRCTC | INDIAN RAILWAY PNR STATUS
# RapidAPI host: irctc-indian-railway-pnr-status.p.rapidapi.com
# ==========================================================
IRCTC_RAPIDAPI_HOST = os.getenv(
    "IRCTC_PNR_RAPIDAPI_HOST",
    "irctc-indian-railway-pnr-status.p.rapidapi.com",
).strip()
IRCTC_RAPIDAPI_KEY = (
    os.getenv("IRCTC_PNR_RAPIDAPI_KEY", "").strip()
    or os.getenv("RAPIDAPI_RAILWAY_KEY", "").strip()
    or os.getenv("IRCTC_RAPIDAPI_KEY", "").strip()
    or os.getenv("IRCTC_API_KEY", "").strip()
    or os.getenv("RAPIDAPI_KEY", "").strip()
)
IRCTC_API_BASE_URL = f"https://{IRCTC_RAPIDAPI_HOST}"
API_TIMEOUT_SECONDS = 20

# Circuit breaker: once RapidAPI returns 429, do not spend more requests
# during this process run. Restart the program after the provider quota resets.
_IRCTC_QUOTA_BLOCKED = False
_IRCTC_FARE_CACHE = {}  # Cache successful and unavailable fare lookups for this process.
_IRCTC_QUOTA_STATE_FILE = os.path.join(os.path.dirname(__file__), ".tripforge_irctc_quota_state.json")

# Persist a known exhausted request window across program restarts so the next
# run does not immediately spend another request just to rediscover HTTP 429.
try:
    with open(_IRCTC_QUOTA_STATE_FILE, "r", encoding="utf-8") as _state_file:
        _quota_state = json.load(_state_file)
    _blocked_until = float(_quota_state.get("blocked_until", 0) or 0)
    if _blocked_until > time.time():
        _IRCTC_QUOTA_BLOCKED = True
except (OSError, ValueError, TypeError, AttributeError):
    pass


def normalize_journey_date(journey_date):
    """Normalize a date to DD-MM-YYYY (TripForge's preferred format)."""
    if isinstance(journey_date, datetime):
        return journey_date.strftime("%d-%m-%Y")
    if isinstance(journey_date, date):
        return journey_date.strftime("%d-%m-%Y")
    if not isinstance(journey_date, str):
        raise ValueError("Journey date must be a date or string.")

    text = journey_date.strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%d-%m-%Y")
        except ValueError:
            pass
    raise ValueError("Invalid date. Use DD-MM-YYYY or YYYY-MM-DD.")


def _irctc_api_get(endpoint, params=None):
    """Make one request; stop all further calls after a 429 in this run."""
    global _IRCTC_QUOTA_BLOCKED
    if _IRCTC_QUOTA_BLOCKED:
        print("IRCTC requests paused: an earlier request hit HTTP 429. No further calls made this run.")
        return None
    if not IRCTC_RAPIDAPI_KEY:
        print("IRCTC_PNR_RAPIDAPI_KEY is missing from .env.")
        return None

    headers = {
        "x-rapidapi-key": IRCTC_RAPIDAPI_KEY,
        "x-rapidapi-host": IRCTC_RAPIDAPI_HOST,
        "Accept": "application/json",
    }
    try:
        response = requests.get(
            f"{IRCTC_API_BASE_URL}{endpoint}",
            headers=headers, params=params, timeout=API_TIMEOUT_SECONDS,
        )
        if response.status_code in (401, 403):
            print("IRCTC RapidAPI authentication/plan error:", response.status_code)
            print(response.text[:500])
            return None
        if response.status_code == 429:
            _IRCTC_QUOTA_BLOCKED = True
            reset_value = response.headers.get("x-ratelimit-requests-reset", "0")
            try:
                reset_seconds = int(reset_value or 0)
                if reset_seconds > 0:
                    with open(_IRCTC_QUOTA_STATE_FILE, "w", encoding="utf-8") as _state_file:
                        json.dump({"blocked_until": time.time() + reset_seconds}, _state_file)
            except (OSError, TypeError, ValueError):
                pass
            print("IRCTC RapidAPI quota/rate limit reached; circuit breaker enabled. No further requests this run.")
            return None

        # Some successful responses report that the current rate-limit window
        # has no requests remaining. Process this response, but block every
        # subsequent IRCTC request during this run.
        remaining = response.headers.get("x-ratelimit-requests-remaining")
        try:
            if remaining is not None and int(remaining) <= 0:
                _IRCTC_QUOTA_BLOCKED = True
                reset_seconds = int(response.headers.get("x-ratelimit-requests-reset", "0") or 0)
                if reset_seconds > 0:
                    try:
                        with open(_IRCTC_QUOTA_STATE_FILE, "w", encoding="utf-8") as _state_file:
                            json.dump({"blocked_until": time.time() + reset_seconds}, _state_file)
                    except OSError:
                        pass
                print("IRCTC rate-limit header reports 0 requests remaining; no further IRCTC requests this run.")
        except (TypeError, ValueError):
            pass

        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("success") is False:
            print("IRCTC API returned an error:", data.get("message") or data.get("error") or data)
            return None
        return data
    except (requests.RequestException, ValueError) as error:
        print("IRCTC API request failed:", error)
        return None


def _extract_list(data, keys):
    """Extract a list from common API response envelopes."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    payload = data.get("data", data.get("result", data))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def search_stations(station_name):
    """Search station codes/names using this API's documented autocomplete endpoint."""
    station_name = str(station_name or "").strip()
    if len(station_name) < 2:
        print("Enter at least two characters for station search.")
        return []

    from urllib.parse import quote
    data = _irctc_api_get(f"/autocomplete/station/{quote(station_name, safe='')}", params={"limit": 20})
    raw_stations = _extract_list(data, ("results", "stations", "items", "data"))
    results = []
    for station in raw_stations:
        if not isinstance(station, dict):
            continue
        code = (station.get("station_code") or station.get("stationCode")
                or station.get("code") or station.get("stnCode") or station.get("ref"))
        name = (station.get("station_name") or station.get("stationName")
                or station.get("name") or station.get("label"))
        if not name:
            continue
        results.append({
            "code": str(code).strip().upper() if code else None,
            "name": str(name).strip(),
            "city": station.get("city") or station.get("city_name"),
            "state": station.get("state") or station.get("state_name"),
            "latitude": station.get("latitude", station.get("lat")),
            "longitude": station.get("longitude", station.get("lon", station.get("lng"))),
            "raw": station,
        })
    print(f"IRCTC station autocomplete returned {len(results)} result(s).")
    return results


def find_railway_stations(city):
    """Backward-compatible alias for older TripForge code."""
    return search_stations(city)


def _normalize_train(train):
    """Normalize a train record returned by the documented /between endpoint."""
    if not isinstance(train, dict):
        return None

    def first(*keys):
        for key in keys:
            value = train.get(key)
            if value not in (None, ""):
                return value
        return None

    number = first("train_no", "train_number", "trainNumber", "train_no", "trainNo", "number")
    name = first("train_name", "trainName", "name", "train")
    item = dict(train)
    item.update({
        "train_number": str(number).strip() if number is not None else None,
        "train_name": name,
        "source_station": first("from_stn_name", "source_station", "sourceStation", "from_station", "fromStation", "sourceName"),
        "source_code": first("from_stn_code", "source_code", "sourceCode", "from_code", "fromStationCode", "source"),
        "destination_station": first("to_stn_name", "destination_station", "destinationStation", "to_station", "toStation", "destinationName"),
        "destination_code": first("to_stn_code", "destination_code", "destinationCode", "to_code", "toStationCode", "destination"),
        "departure": first("from_time", "departure", "departure_time", "departureTime"),
        "arrival": first("to_time", "arrival", "arrival_time", "arrivalTime"),
        "duration": first("travel_time", "duration", "duration_minutes"),
        # /between returns timetable information, not fares or live seat status.
        "fare_per_person": None,
        "availability_status": None,
    })
    return item


def search_trains(source_code, destination_code, journey_date):
    """Search direct trains via /between/{from}/{to}; one request, no retries."""
    source_code = str(source_code or "").strip().upper()
    destination_code = str(destination_code or "").strip().upper()
    if not source_code or not destination_code:
        print("Both source and destination station codes are required.")
        return []
    if source_code == destination_code:
        print("Source and destination stations must differ.")
        return []
    try:
        formatted_date = normalize_journey_date(journey_date)
    except ValueError as error:
        print(error)
        return []

    # Persistent 6-hour cache prevents repeated test runs from consuming the
    # monthly quota for the same route/date. It stores public results only.
    cache_file = os.path.join(os.path.dirname(__file__), ".tripforge_train_search_cache.json")
    cache_key = f"{IRCTC_RAPIDAPI_HOST}|{source_code}|{destination_code}|{formatted_date}"
    now = time.time()
    try:
        with open(cache_file, "r", encoding="utf-8") as handle:
            saved_cache = json.load(handle)
        cached = saved_cache.get(cache_key) if isinstance(saved_cache, dict) else None
        if isinstance(cached, dict) and now - float(cached.get("timestamp", 0)) < 6 * 60 * 60:
            cached_trains = cached.get("trains", [])
            if isinstance(cached_trains, list):
                print(f"Using cached train search for {source_code} → {destination_code} on {formatted_date}; no API request made.")
                return cached_trains
    except (OSError, ValueError, TypeError, AttributeError):
        saved_cache = {}

    from urllib.parse import quote
    endpoint = f"/between/{quote(source_code, safe='')}/{quote(destination_code, safe='')}"
    data = _irctc_api_get(endpoint, params={"date": formatted_date})
    if data is None:
        return []
    raw_trains = _extract_list(data, ("trains", "results", "items", "journeys", "data"))
    trains = []
    for raw in raw_trains:
        normalized = _normalize_train(raw)
        if normalized:
            trains.append(normalized)
    try:
        if not isinstance(saved_cache, dict):
            saved_cache = {}
        saved_cache[cache_key] = {"timestamp": now, "trains": trains}
        with open(cache_file, "w", encoding="utf-8") as handle:
            json.dump(saved_cache, handle)
    except (OSError, TypeError, ValueError):
        pass
    print(f"IRCTC route search returned {len(trains)} direct train record(s).")
    return trains


def get_train_details(train_number_or_name):
    """Fetch train information from GET /train/{trainNo} (one request)."""
    value = str(train_number_or_name or "").strip()
    if not value.isdigit():
        print("A numeric train number is required for train details.")
        return None
    from urllib.parse import quote
    return _irctc_api_get(f"/train/{quote(value, safe='')}")


def get_train_live_status(train_number, journey_date=None):
    """Fetch live running status from GET /live-train/{trainNo}/status."""
    value = str(train_number or "").strip()
    if not value.isdigit():
        print("A numeric train number is required for live status.")
        return None
    params = {}
    if journey_date:
        try:
            params["date"] = datetime.strptime(
                normalize_journey_date(journey_date), "%d-%m-%Y"
            ).strftime("%d-%b-%Y")
        except ValueError as error:
            print(error)
            return None
    from urllib.parse import quote
    return _irctc_api_get(f"/live-train/{quote(value, safe='')}/status", params=params or None)


def _haversine_km(lat1, lon1, lat2, lon2):
    """Calculate straight-line distance between two coordinate pairs."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371 * 2 * atan2(sqrt(a), sqrt(max(0.0, 1 - a)))


def _geocode_place(place):
    """Resolve a city/place with Nominatim; uses public OSM data, not a paid API key."""
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": place, "format": "jsonv2", "limit": 1, "countrycodes": "in"},
            headers={"User-Agent": "TripForge/1.0 (travel planning project)"},
            timeout=15,
        )
        response.raise_for_status()
        results = response.json()
        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        return None


def find_nearby_railway_stations(city, radius_km=120, limit=30):
    """Discover nearby railway stations dynamically.

    Primary source: Geoapify Places API (public_transport.train).
    Fallback: public Overpass mirrors.

    Returned station codes are not trusted. Callers must resolve station names
    through the existing IRCTC search_stations() function before train search.
    This function does not call the paid RapidAPI railway endpoints.
    """
    center = _geocode_place(city)
    if not center:
        print(f"Could not geocode destination: {city}")
        return []

    try:
        radius_km = max(1.0, float(radius_km))
        result_limit = max(1, min(100, int(limit)))
    except (TypeError, ValueError, OverflowError):
        print("Nearby railway-station search received an invalid radius or limit.")
        return []

    lat, lon = center
    radius_m = int(radius_km * 1000)
    headers = {"User-Agent": "TripForge/1.0 (nearby railway station lookup)"}
    stations = []
    seen = set()

    # Reuse the Geoapify key already configured in the project's environment.
    # GEOAPIFY_API_KEY is the standard name; aliases support common .env names.
    geoapify_key = (
        os.getenv("GEOAPIFY_API_KEY", "").strip()
        or os.getenv("GEOAPIFY_KEY", "").strip()
        or os.getenv("GEOAPIFY", "").strip()
    )

    if geoapify_key:
        try:
            params = {
                "categories": "public_transport.train",
                "filter": f"circle:{lon},{lat},{radius_m}",
                "bias": f"proximity:{lon},{lat}",
                "limit": result_limit,
                "lang": "en",
                "apiKey": geoapify_key,
            }
            response = requests.get(
                "https://api.geoapify.com/v2/places",
                params=params,
                headers=headers,
                timeout=25,
            )
            response.raise_for_status()
            payload = response.json()
            features = payload.get("features", []) if isinstance(payload, dict) else []
            if not isinstance(features, list):
                raise ValueError("Geoapify returned an unexpected response format.")

            for feature in features:
                if not isinstance(feature, dict):
                    continue
                properties = feature.get("properties") or {}
                geometry = feature.get("geometry") or {}
                coordinates = geometry.get("coordinates") or []
                name = properties.get("name") or properties.get("address_line1")
                if not name or len(coordinates) < 2:
                    continue
                try:
                    station_lon = float(coordinates[0])
                    station_lat = float(coordinates[1])
                except (TypeError, ValueError):
                    continue

                normalized_name = str(name).strip().casefold()
                if not normalized_name or normalized_name in seen:
                    continue
                distance_km = _haversine_km(lat, lon, station_lat, station_lon)
                if distance_km > radius_km:
                    continue

                seen.add(normalized_name)
                stations.append({
                    "name": str(name).strip(),
                    "code": None,
                    "latitude": station_lat,
                    "longitude": station_lon,
                    "distance_km_straight_line": round(distance_km, 1),
                    "source": "Geoapify; station code must be verified",
                })

            if stations:
                stations.sort(key=lambda station: station["distance_km_straight_line"])
                print(
                    f"Nearby railway-station lookup found {len(stations)} "
                    "station(s) using Geoapify."
                )
                return stations[:result_limit]
            print("Geoapify returned no named railway stations; trying Overpass fallback.")
        except (requests.RequestException, ValueError, TypeError, AttributeError) as error:
            print(f"Geoapify railway-station lookup failed: {error}")
            print("Trying Overpass mirrors as fallback.")
    else:
        print("Geoapify API key not found (GEOAPIFY_API_KEY); trying Overpass fallback.")

    query = (
        f'[out:json][timeout:25];\n'
        f'(node[railway~"^(station|halt)$"](around:{radius_m},{lat},{lon});\n'
        f' way[railway~"^(station|halt)$"](around:{radius_m},{lat},{lon});\n'
        f' relation[railway~"^(station|halt)$"](around:{radius_m},{lat},{lon}););\n'
        f'out center tags;'
    )

    overpass_endpoints = (
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass-api.de/api/interpreter",
    )
    elements = None
    last_error = None
    for endpoint in overpass_endpoints:
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                headers={**headers, "Accept": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
                raise ValueError("Overpass returned an unexpected response format.")
            elements = payload["elements"]
            if elements:
                break
            last_error = ValueError("Overpass returned no station elements.")
        except (requests.RequestException, ValueError, AttributeError) as error:
            last_error = error
            print(f"Overpass endpoint failed: {endpoint}")
            print(f"Reason: {error}")

    if not elements:
        print("Nearby railway-station lookup failed using Geoapify and all Overpass mirrors.")
        if last_error:
            print("Last Overpass error:", last_error)
        return []

    for element in elements:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags") or {}
        name = tags.get("name") or tags.get("name:en")
        if not name:
            continue
        normalized_name = str(name).strip().casefold()
        if not normalized_name or normalized_name in seen:
            continue
        coords = element.get("center", element)
        try:
            station_lat = float(coords["lat"])
            station_lon = float(coords["lon"])
        except (KeyError, TypeError, ValueError):
            continue

        distance_km = _haversine_km(lat, lon, station_lat, station_lon)
        if distance_km > radius_km:
            continue
        seen.add(normalized_name)
        stations.append({
            "name": str(name).strip(),
            "code": tags.get("ref") or tags.get("uic_ref"),
            "latitude": station_lat,
            "longitude": station_lon,
            "distance_km_straight_line": round(distance_km, 1),
            "source": "OpenStreetMap; station code must be verified",
        })

    stations.sort(key=lambda station: station["distance_km_straight_line"])
    print(f"Nearby railway-station lookup found {len(stations)} station(s) using Overpass fallback.")
    return stations[:result_limit]


def get_road_distance_km(source_lat, source_lon, destination_lat, destination_lon):
    """Get a road-route distance in km using OSRM; no paid API key required."""
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{source_lon},{source_lat};{destination_lon},{destination_lat}"
    )
    try:
        response = requests.get(url, params={"overview": "false"}, timeout=20)
        response.raise_for_status()
        routes = response.json().get("routes", [])
        if not routes:
            return None
        return round(float(routes[0]["distance"]) / 1000, 1)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def estimate_train_road_transfer_cost(
    distance_km, travellers=1, cost_per_km=15, vehicles_required=1
):
    """Estimate station-to-destination road transfer; ₹15/km is an assumption."""
    try:
        distance_km = float(distance_km)
        travellers = int(travellers)
        vehicles_required = int(vehicles_required)
        cost_per_km = float(cost_per_km)
    except (TypeError, ValueError):
        return None
    if distance_km < 0 or travellers < 1 or vehicles_required < 1 or cost_per_km < 0:
        return None
    total = distance_km * cost_per_km * vehicles_required
    return {
        "distance_km": round(distance_km, 1),
        "vehicles_required": vehicles_required,
        "estimated_total_fare": round(total, 2),
        "estimated_cost_per_traveller": round(total / travellers, 2),
        "fare_type": "Estimate only; verify with a local taxi/provider",
    }



def get_route_train_fares(source_code, destination_code, journey_date=None, quota="GN"):
    """Fetch route-wide indicative fares in one request.

    The provider documents GET /fare with only `from` and `to` as returning
    fares for all trains/classes on that route. `journey_date` is accepted for
    backwards compatibility but is not sent because it is not a documented
    /fare parameter. Returns normalized rows; never invents missing fares.
    Results (including empty responses) are cached locally for six hours to
    avoid spending another monthly API request during repeated test runs.
    """
    source_code = str(source_code or "").strip().upper()
    destination_code = str(destination_code or "").strip().upper()
    quota = str(quota or "GN").strip().upper()
    if not source_code or not destination_code or source_code == destination_code:
        print("Valid, different source and destination station codes are required for fare lookup.")
        return []

    cache_file = os.path.join(os.path.dirname(__file__), ".tripforge_route_fare_cache.json")
    cache_key = f"{IRCTC_RAPIDAPI_HOST}|{source_code}|{destination_code}|{quota}|1|0"
    now = time.time()
    try:
        with open(cache_file, "r", encoding="utf-8") as handle:
            saved_cache = json.load(handle)
        cached = saved_cache.get(cache_key)
        if isinstance(cached, dict) and now - float(cached.get("timestamp", 0)) < 6 * 60 * 60:
            print(f"Using cached route fare results for {source_code} → {destination_code}; no API request made.")
            rows = cached.get("rows", [])
            return rows if isinstance(rows, list) else []
    except (OSError, ValueError, TypeError, AttributeError):
        saved_cache = {}

    params = {"from": source_code, "to": destination_code, "quota": quota, "adults": 1, "children": 0}
    data = _irctc_api_get("/fare", params=params)
    rows = []
    if isinstance(data, dict):
        payload = data.get("data", data.get("result", data))
        if isinstance(payload, dict):
            raw_trains = payload.get("trains", [])
            if isinstance(raw_trains, list):
                for train in raw_trains:
                    if not isinstance(train, dict):
                        continue
                    train_number = train.get("train_no") or train.get("train_number") or train.get("trainNo")
                    train_name = train.get("train_name") or train.get("name")
                    fares = train.get("fares", [])
                    if not isinstance(fares, list):
                        continue
                    for fare in fares:
                        if not isinstance(fare, dict):
                            continue
                        fare_class = str(fare.get("class") or fare.get("class_code") or "").strip().upper()
                        fare_quota = str(fare.get("quota") or quota).strip().upper()
                        raw_amount = fare.get("per_adult")
                        if raw_amount is None:
                            raw_amount = fare.get("adult_fare", fare.get("fare_per_person"))
                        try:
                            amount = float(str(raw_amount).replace(",", "").replace("₹", "").strip())
                        except (TypeError, ValueError):
                            continue
                        if not fare_class or amount <= 0:
                            continue
                        if quota == "GN" and fare_quota not in ("GN", "GENERAL"):
                            continue
                        rows.append({
                            "train_number": str(train_number).strip() if train_number is not None else None,
                            "train_name": train_name,
                            "class": fare_class,
                            "fare_per_person": amount,
                            "quota": fare_quota,
                            "fare_type": "Indicative API estimate; verify before booking",
                        })

    # Persist even an empty result briefly so a rerun won't immediately repeat
    # a potentially unproductive request. Cache file contains no API secrets.
    try:
        if not isinstance(saved_cache, dict):
            saved_cache = {}
        saved_cache[cache_key] = {"timestamp": now, "rows": rows}
        with open(cache_file, "w", encoding="utf-8") as handle:
            json.dump(saved_cache, handle)
    except (OSError, TypeError, ValueError):
        pass

    print(f"Route fare endpoint returned {len(rows)} positive fare/class record(s) for {source_code} → {destination_code}.")
    return rows


def get_train_fare(
    train_number, source_code, destination_code, journey_date=None,
    travel_class="SL", quota="GN",
):
    """Fetch indicative per-adult fare using the API's documented GET /fare endpoint.

    The API's fare is an estimate, not a guaranteed booking price. This function
    requests one adult so main_page.py can multiply the per-person estimate by
    the selected traveller count without double-counting passengers.
    """
    source_code = str(source_code or "").strip().upper()
    destination_code = str(destination_code or "").strip().upper()
    train_number = str(train_number or "").strip()
    travel_class = str(travel_class or "SL").strip().upper()
    quota = str(quota or "GN").strip().upper()
    if not source_code or not destination_code:
        print("Source and destination station codes are required for fare lookup.")
        return None

    try:
        normalized_date = normalize_journey_date(journey_date) if journey_date else ""
    except ValueError:
        normalized_date = str(journey_date or "").strip()

    cache_key = (train_number, source_code, destination_code, normalized_date, travel_class, quota)
    if cache_key in _IRCTC_FARE_CACHE:
        cached = _IRCTC_FARE_CACHE[cache_key]
        return dict(cached) if isinstance(cached, dict) else None

    params = {
        "from": source_code,
        "to": destination_code,
        "class": travel_class,
        "quota": quota,
        "adults": 1,
        "children": 0,
    }
    if normalized_date:
        params["date"] = normalized_date
    if train_number:
        params["train"] = train_number
    data = _irctc_api_get("/fare", params=params)
    if not isinstance(data, dict):
        return None

    payload = data.get("data", data.get("result", data))
    if not isinstance(payload, dict):
        return None
    trains = payload.get("trains")
    if not isinstance(trains, list):
        trains = [payload] if any(k in payload for k in ("train_no", "train_number", "fares")) else []

    target_number = train_number.lstrip("0")
    for train in trains:
        if not isinstance(train, dict):
            continue
        returned_number = str(train.get("train_no") or train.get("train_number") or "").strip()
        if target_number and returned_number and returned_number.lstrip("0") != target_number:
            continue
        fares = train.get("fares")
        if isinstance(fares, list):
            for fare in fares:
                if not isinstance(fare, dict):
                    continue
                fare_class = str(fare.get("class") or travel_class).strip().upper()
                fare_quota = str(fare.get("quota") or quota).strip().upper()
                if fare_class != travel_class:
                    continue
                # API may label the general quota as GENERAL.
                if quota == "GN" and fare_quota not in ("GN", "GENERAL"):
                    continue
                amount = fare.get("per_adult")
                if amount is None:
                    amount = fare.get("adult_fare", fare.get("fare_per_person"))
                try:
                    amount = float(str(amount).replace(",", "").replace("₹", "").strip())
                except (TypeError, ValueError):
                    continue
                if amount > 0:
                    result = {
                        "train_number": returned_number or train_number or None,
                        "train_name": train.get("train_name") or train.get("name"),
                        "fare_per_person": amount,
                        "travel_class": travel_class,
                        "quota": fare_quota,
                        "fare_type": "Indicative API estimate; verify before booking",
                        "raw": train,
                    }
                    _IRCTC_FARE_CACHE[cache_key] = result
                    return dict(result)
        # Some responses may provide a single flat fare object.
        if train.get("fare_per_person") is not None:
            try:
                amount = float(str(train["fare_per_person"]).replace(",", "").replace("₹", "").strip())
                if amount > 0:
                    result = {"train_number": returned_number or train_number or None,
                              "fare_per_person": amount, "travel_class": travel_class,
                              "quota": quota, "fare_type": "Indicative API estimate; verify before booking",
                              "raw": train}
                    _IRCTC_FARE_CACHE[cache_key] = result
                    return dict(result)
            except (TypeError, ValueError):
                pass
    print("No confirmed positive fare was returned for the selected train/class/quota.")
    _IRCTC_FARE_CACHE[cache_key] = None
    return None


# ==========================================================
# TRAIN RANKING BY GROUP BUDGET
# ==========================================================

def rank_trains_by_budget(
    trains,
    travellers,
    total_budget,
    other_trip_costs=0,
):
    """Rank trains only when actual per-person fares are available."""

    travellers = max(1, int(travellers))
    total_budget = max(0.0, float(total_budget))
    other_trip_costs = max(0.0, float(other_trip_costs))

    available_for_train = max(
        0.0, total_budget - other_trip_costs
    )

    ranked = []

    for train in trains:
        try:
            fare = float(train["fare_per_person"])
            if fare < 0:
                continue

            item = dict(train)
            item["group_fare"] = fare * travellers
            item["fits_budget"] = (
                item["group_fare"] <= available_for_train
            )
            ranked.append(item)

        except (KeyError, TypeError, ValueError):
            continue

    ranked.sort(
        key=lambda item: (
            not item["fits_budget"],
            item["group_fare"],
        )
    )

    return {
        "total_budget": total_budget,
        "travellers": travellers,
        "other_trip_costs": other_trip_costs,
        "available_for_train": available_for_train,
        "ranked_trains": ranked,
        "best_affordable_train": next(
            (item for item in ranked if item["fits_budget"]),
            None,
        ),
    }


# ==========================================================
# COMPLETE TRIP BUDGET
# ==========================================================

def allocate_trip_budget(
    total_budget,
    travellers,
    days,
    train_cost,
    accommodation_cost,
    food_per_person_per_day=350,
    local_per_person_per_day=150,
    attractions_per_person_per_day=150,
    onward_transfer_cost=0,
):
    """Calculate trip expenses. Costs are group totals."""

    total_budget = max(0.0, float(total_budget))
    travellers = max(1, int(travellers))
    days = max(1, int(days))
    train_cost = max(0.0, float(train_cost))
    accommodation_cost = max(0.0, float(accommodation_cost))
    onward_transfer_cost = max(0.0, float(onward_transfer_cost))

    food = travellers * days * food_per_person_per_day
    local_travel = travellers * days * local_per_person_per_day
    attractions = (
        travellers * days * attractions_per_person_per_day
    )

    estimated_total = (
        train_cost
        + onward_transfer_cost
        + accommodation_cost
        + food
        + local_travel
        + attractions
    )

    shortfall = max(0.0, estimated_total - total_budget)

    return {
        "budget": total_budget,
        "travellers": travellers,
        "days": days,
        "nights": max(0, days - 1),
        "train": train_cost,
        "onward_transfer": onward_transfer_cost,
        "accommodation": accommodation_cost,
        "food": food,
        "local_travel": local_travel,
        "attractions": attractions,
        "estimated_total": estimated_total,
        "remaining": max(0.0, total_budget - estimated_total),
        "shortfall": shortfall,
        "fits_budget": estimated_total <= total_budget,
        "minimum_suggested_budget": estimated_total,
    }


# ==========================================================
# PRINT TRIP BUDGET
# ==========================================================

def print_trip_budget(result):
    print("\n========== TRIP BUDGET ==========")
    print(f"Initial budget: ₹{result['budget']:,.2f}")
    print(f"Travellers: {result['travellers']}")
    print(
        f"Duration: {result['days']} days, "
        f"{result['nights']} nights"
    )

    print("\n========== EXPENSES ==========")
    print(f"Group train fare: ₹{result['train']:,.2f}")
    print(
        f"Onward road transfer: "
        f"₹{result['onward_transfer']:,.2f}"
    )
    print(
        f"Group accommodation: "
        f"₹{result['accommodation']:,.2f}"
    )
    print(f"Food: ₹{result['food']:,.2f}")
    print(f"Local travel: ₹{result['local_travel']:,.2f}")
    print(f"Attractions: ₹{result['attractions']:,.2f}")
    print(
        f"\nEstimated total: "
        f"₹{result['estimated_total']:,.2f}"
    )

    if result["fits_budget"]:
        print(
            f"Remaining budget: ₹{result['remaining']:,.2f}"
        )
    else:
        print(
            f"Budget shortfall: ₹{result['shortfall']:,.2f}"
        )
        print(
            "Suggested minimum budget: "
            f"₹{result['minimum_suggested_budget']:,.2f}"
        )
