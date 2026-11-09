import requests
import os
import math
import re
from dotenv import load_dotenv
from difflib import SequenceMatcher

load_dotenv()

API_KEY = os.getenv("GEOAPIFY_API_KEY")
FOURSQUARE_API_KEY = os.getenv("FOURSQUARE_API_KEY")
LITEAPI_API_KEY = os.getenv("LITEAPI_SANDBOX_KEY")
print("API key loaded:", API_KEY is not None)
print("Foursquare key loaded:", FOURSQUARE_API_KEY is not None)
def get_location(destination):

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": destination,
        "format": "json",
        "limit": 1
    }

    headers = {
    "User-Agent": "AI-Budget-Planner/1.0"
    }

    response = requests.get(url, params=params, headers=headers)

    print("Nominatim Status:", response.status_code)

    if response.status_code == 200:
        data = response.json()

        if not data:
            print("Location not found.")
            return None

        return {
            "latitude": float(data[0]["lat"]),
            "longitude": float(data[0]["lon"])
        }

    else:
        print("Nominatim request failed.")
        print(response.text)
        return None

def get_attractions(latitude, longitude, destination=None):
    """Find named attractions across a destination and remove weak duplicates.

    For broad destinations (for example, a state such as Kerala), the
    destination bounding box is split into smaller areas so one central
    coordinate does not limit discovery to a small part of the region.
    """
    if not API_KEY:
        print("Geoapify API key is missing. Attraction search skipped.")
        return []

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        print("Invalid destination coordinates. Attraction search skipped.")
        return []

    url = "https://api.geoapify.com/v2/places"
    # These categories cover named attractions plus commonly mapped parks,
    # sights and natural points of interest. Geoapify accepts comma-separated
    # category identifiers in the categories parameter.
    categories = "tourism.attraction,tourism.sights,leisure.park,natural"
    search_areas = [(f"circle:{longitude},{latitude},5000", 30)]
    destination_name = ""

    # Some callers may provide only coordinates. Reverse-geocode those
    # coordinates to recover the state/region so broad destinations still
    # receive a region-wide search instead of silently falling back to 5 km.
    if not destination:
        try:
            reverse_response = requests.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "format": "jsonv2",
                    "zoom": 5,
                    "addressdetails": 1,
                },
                headers={"User-Agent": "TripForge/1.0 (attraction discovery)"},
                timeout=15,
            )
            if reverse_response.status_code == 200:
                reverse_data = reverse_response.json()
                address = reverse_data.get("address", {})
                destination = (
                    address.get("state")
                    or address.get("region")
                    or address.get("county")
                )
                if destination:
                    print("Recovered broad destination from coordinates:", destination)
        except (requests.RequestException, ValueError, TypeError) as error:
            print("Reverse geocoding failed; using nearby search:", error)

    if destination:
        try:
            geocode_response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": destination, "format": "json", "limit": 1},
                headers={"User-Agent": "TripForge/1.0 (attraction discovery)"},
                timeout=15,
            )
            if geocode_response.status_code == 200:
                geocode_results = geocode_response.json()
                if geocode_results:
                    destination_name = str(geocode_results[0].get("name") or destination)
                    bbox = geocode_results[0].get("boundingbox")
                    if bbox and len(bbox) == 4:
                        south, north, west, east = map(float, bbox)
                        height_km = abs(north - south) * 111.0
                        width_km = abs(east - west) * 111.0 * max(
                            0.1, abs(math.cos(math.radians((north + south) / 2)))
                        )

                        if max(width_km, height_km) > 25:
                            # Split broad areas into four rectangles. This
                            # avoids relying on one state-level centre point
                            # and keeps each provider search geographically
                            # narrower than the full state bounding box.
                            mid_lat = (south + north) / 2
                            mid_lon = (west + east) / 2
                            boxes = [
                                (west, south, mid_lon, mid_lat),
                                (mid_lon, south, east, mid_lat),
                                (west, mid_lat, mid_lon, north),
                                (mid_lon, mid_lat, east, north),
                            ]
                            search_areas = [
                                (f"rect:{w},{s},{e},{n}", 50)
                                for w, s, e, n in boxes
                                if e > w and n > s
                            ]
                            print(
                                "Broad destination detected; searching four "
                                "geographical sections for attractions."
                            )
        except (requests.RequestException, ValueError, TypeError) as error:
            print("Destination boundary lookup failed; using nearby search:", error)

    all_features = []
    for area_filter, area_limit in search_areas:
        params = {
            "categories": categories,
            "filter": area_filter,
            "bias": f"proximity:{longitude},{latitude}",
            "limit": area_limit,
            "apiKey": API_KEY,
        }
        try:
            response = requests.get(url, params=params, timeout=20)
            print("Geoapify Attractions Status:", response.status_code)
            if response.status_code != 200:
                print("Geoapify attraction request failed:", response.text)
                continue
            all_features.extend(response.json().get("features", []))
        except (requests.RequestException, ValueError) as error:
            print("Geoapify attraction search error:", error)

    if not all_features:
        print("Geoapify returned no attraction features for this destination.")
        return []

    def normalise_name(value):
        return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()

    generic_names = {
        "attraction", "tourist attraction", "tourist spot", "place",
        "unnamed", "unnamed attraction", "viewpoint", "scenic viewpoint",
        "meadow", "scenic meadow", "scenic spot", "tourist place",
        "park", "nature", "natural feature",
    }
    destination_key = normalise_name(destination_name or destination or "")
    generic_suffixes = {
        "viewpoint", "attraction", "tourist spot", "scenic meadow", "meadow"
    }

    candidates = []
    seen_feature_ids = set()
    for place in all_features:
        properties = place.get("properties", {})
        feature_id = properties.get("place_id") or properties.get("datasource", {}).get("raw", {}).get("osm_id")
        if feature_id and feature_id in seen_feature_ids:
            continue
        if feature_id:
            seen_feature_ids.add(feature_id)

        raw_name = properties.get("name")
        lat_value = properties.get("lat")
        lon_value = properties.get("lon")
        if not raw_name or lat_value is None or lon_value is None:
            continue

        name = str(raw_name).strip()
        name_key = normalise_name(name)
        if not name_key or name_key in generic_names:
            continue

        locality_names = [destination_key]
        locality_names.extend(
            normalise_name(properties.get(field, ""))
            for field in ("city", "town", "municipality", "suburb")
            if properties.get(field)
        )
        if any(
            locality and name_key == f"{locality} {suffix}"
            for locality in locality_names
            for suffix in generic_suffixes
        ):
            continue

        try:
            place_lat = float(lat_value)
            place_lon = float(lon_value)
        except (TypeError, ValueError):
            continue

        # Geoapify may omit distance for rectangle searches. Calculate a
        # consistent distance from the destination's supplied centre.
        lat1, lat2 = math.radians(latitude), math.radians(place_lat)
        dlat = lat2 - lat1
        dlon = math.radians(place_lon - longitude)
        haversine = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        distance = 6371000 * 2 * math.atan2(
            math.sqrt(haversine), math.sqrt(max(0.0, 1 - haversine))
        )

        candidates.append({
            "name": name,
            "_name_key": name_key,
            "latitude": place_lat,
            "longitude": place_lon,
            "distance": round(distance),
            "category": properties.get("categories", []),
            "opening_hours": properties.get("opening_hours"),
        })

    # Keep distinct named places, but collapse exact duplicate names and
    # duplicate provider labels for the same physical location (within 75 m).
    candidates.sort(key=lambda item: item["distance"])
    attractions = []
    seen_names = set()
    seen_coordinates = []
    for item in candidates:
        if item["_name_key"] in seen_names:
            continue

        is_same_spot = False
        for old_lat, old_lon in seen_coordinates:
            lat1, lat2 = math.radians(item["latitude"]), math.radians(old_lat)
            dlat = lat2 - lat1
            dlon = math.radians(old_lon - item["longitude"])
            haversine = (
                math.sin(dlat / 2) ** 2
                + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            )
            metres = 6371000 * 2 * math.atan2(
                math.sqrt(haversine), math.sqrt(max(0.0, 1 - haversine))
            )
            if metres <= 75:
                is_same_spot = True
                break
        if is_same_spot:
            continue

        seen_names.add(item["_name_key"])
        seen_coordinates.append((item["latitude"], item["longitude"]))
        item.pop("_name_key", None)
        attractions.append(item)

    print("Number of attractions after quality filtering:", len(attractions))
    return attractions

def search_foursquare(name, latitude, longitude):

    url = "https://places-api.foursquare.com/places/search"

    headers = {
        "Authorization": f"Bearer {FOURSQUARE_API_KEY}",
        "Accept": "application/json",
        "X-Places-Api-Version": "2025-06-17"
    }

    params = {
        "query": name,
        "ll": f"{latitude},{longitude}",
        "limit": 5
    }

    response = requests.get(
        url,
        headers=headers,
        params=params
    )

    print("Foursquare Status:", response.status_code)

    if response.status_code == 429:
            print("Foursquare credits exhausted.")
            return []

    if response.status_code != 200:
        print("Foursquare request failed.")
        print(response.text)
        return []


    data = response.json()

    return data.get("results", [])


def match_accommodation(accommodation, candidates):

    if not candidates:
        return None

    best_match = None
    best_score = -1

    for candidate in candidates:

        name_score = calculate_name_score(
            accommodation["name"],
            candidate["name"]
        )

        # Convert distance into a simple score
        distance = candidate.get("distance", 9999)

        if distance <= 200:
            distance_score = 1.0
        elif distance <= 500:
            distance_score = 0.8
        elif distance <= 1000:
            distance_score = 0.5
        elif distance <= 2000:
            distance_score = 0.2
        else:
            distance_score = 0.0

        final_score = (
            (name_score * 0.7)
            + (distance_score * 0.3)
        )

        if final_score > best_score:

            best_score = final_score

            best_match = {
                "name": candidate["name"],
                "fsq_place_id": candidate["fsq_place_id"],
                "distance": distance,
                "name_score": name_score,
                "distance_score": distance_score,
                "match_score": final_score
            }

    if best_score < 0.75:
        return None

    return best_match

def get_place_details(fsq_place_id):

    url = f"https://places-api.foursquare.com/places/{fsq_place_id}"

    headers = {
        "Authorization": f"Bearer {FOURSQUARE_API_KEY}",
        "Accept": "application/json",
        "X-Places-Api-Version": "2025-06-17"
    }

    response = requests.get(
        url,
        headers=headers
    )

    print("Foursquare Details Status:", response.status_code)

    if response.status_code != 200:
        print("Foursquare details request failed.")
        print(response.text)
        return None

    return response.json()

CATEGORY_MAP = {
    "garden": [
        "garden",
        "botanical garden",
        "park"
    ],

    "viewpoint": [
        "viewpoint",
        "scenic lookout",
        "mountain",
        "observation deck"
    ],

    "museum": [
        "museum"
    ],

    "water": [
        "boat",
        "lake",
        "water"
    ]
}

def calculate_category_score(geoapify_name, geoapify_categories, foursquare_categories):

    geoapify_text = (
        geoapify_name + " " + " ".join(geoapify_categories)
    ).lower()

    foursquare_text = " ".join(foursquare_categories).lower()

    for key, related_categories in CATEGORY_MAP.items():

        if key in geoapify_text:

            for category in related_categories:

                if category in foursquare_text:
                    return 1.0

    return 0.0

def calculate_distance_score(distance):

    if distance <= 200:
        return 1.0

    elif distance <= 500:
        return 0.8

    elif distance <= 1000:
        return 0.5

    elif distance <= 2000:
        return 0.2

    else:
        return 0.0

def calculate_name_score(geoapify_name, foursquare_name):

    geoapify_name = geoapify_name.lower()
    foursquare_name = foursquare_name.lower()

    if geoapify_name==foursquare_name:
        return 1.0

    score = SequenceMatcher(
        None,
        geoapify_name,
        foursquare_name
    ).ratio()

    return score

def calculate_match_score(name_score, distance_score, category_score):

    final_score = (
        (name_score * 0.60)
        + (distance_score * 0.20)
        + (category_score * 0.20)
    )

    return final_score

def get_accommodations(latitude, longitude):

    url = "https://api.geoapify.com/v2/places"

    params = {
        "categories": "accommodation",
        "filter": f"circle:{longitude},{latitude},5000",
        "bias": f"proximity:{longitude},{latitude}",
        "limit": 20,
        "apiKey": API_KEY
    }

    response = requests.get(url, params=params)

    print("Geoapify Accommodation Status:", response.status_code)

    if response.status_code != 200:
        print("Accommodation request failed.")
        print(response.text)
        return []

    data = response.json()

    accommodations = []

    for place in data["features"]:

        properties = place["properties"]

        name = properties.get("name")
        categories = properties.get("categories", [])

        if not name:
            continue

        latitude_value = properties.get("lat")
        longitude_value = properties.get("lon")
        distance = properties.get("distance")

        if latitude_value is None or longitude_value is None:
            continue

        accommodations.append({
            "name": name,
            "latitude": latitude_value,
            "longitude": longitude_value,
            "distance": distance,
            "category": categories,
            "type": classify_accommodation(name,categories)
        })

    print("Number of accommodations:", len(accommodations))

    return accommodations

def classify_accommodation(name, categories):

    category_text = " ".join(categories).lower()
    name_text = name.lower()

    # More specific types first
    if "villa" in category_text or "villa" in name_text:
        return "Villa"

    elif "guest_house" in category_text or "guest house" in name_text:
        return "Guest House"

    elif "hostel" in category_text or "hostel" in name_text:
        return "Hostel"

    elif "motel" in category_text or "motel" in name_text:
        return "Motel"

    elif "lodge" in category_text or "lodge" in name_text:
        return "Lodge"

    elif "cottage" in name_text:
        return "Cottage"

    elif "hotel" in category_text or "hotel" in name_text:
        return "Hotel"

    else:
        return "Other"


def get_hotels(latitude, longitude):
    """Retrieve hotel listings in batches for the destination."""

    url = "https://api.liteapi.travel/v3.0/data/hotels"

    headers = {
        "X-API-Key": LITEAPI_API_KEY
    }

    limit = 100
    offset = 0
    all_hotels = []
    seen_ids = set()

    while True:
        params = {
            "countryCode": "IN",
            "latitude": latitude,
            "longitude": longitude,
            "radius": 10000,
            "limit": limit,
            "offset": offset
        }

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=20
            )

            print(
                f"Hotel discovery status at offset {offset}:",
                response.status_code
            )

            if response.status_code != 200:
                print("Hotel discovery failed:", response.text)
                break

            data = response.json()
            batch = data.get("data", [])

            if not batch:
                break

            for hotel in batch:
                hotel_id = hotel.get("id") or hotel.get("hotelId")

                if hotel_id and hotel_id not in seen_ids:
                    seen_ids.add(hotel_id)
                    all_hotels.append(hotel)

            print("Hotels collected so far:", len(all_hotels))

            if len(batch) < limit:
                break

            offset += limit

        except (requests.RequestException, ValueError) as error:
            print("Hotel discovery error:", error)
            break

    print("Total unique hotels discovered:", len(all_hotels))
    return all_hotels


def get_hotel_prices(
    hotel_ids,
    check_in,
    check_out,
    travellers=1
):
    """Get hotel rates for a group using multiple room occupancies."""

    if not hotel_ids:
        print("No hotel IDs provided for price search.")
        return []

    if travellers < 1:
        print("Travellers must be at least 1.")
        return []

    # Initial assumption: up to 2 adults per room.
    occupancies = []
    remaining = travellers

    while remaining > 0:
        adults_in_room = min(2, remaining)
        occupancies.append({"adults": adults_in_room})
        remaining -= adults_in_room

    url = "https://api.liteapi.travel/v3.0/hotels/rates"

    payload = {
        "hotelIds": hotel_ids[:10],
        "checkin": check_in.strftime("%Y-%m-%d"),
        "checkout": check_out.strftime("%Y-%m-%d"),
        "occupancies": occupancies,
        "currency": "INR",
        "guestNationality": "IN",
        "maxRatesPerHotel": 1,
        "timeout": 10
    }

    headers = {
        "X-API-Key": LITEAPI_API_KEY,
        "accept": "application/json",
        "content-type": "application/json"
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=15
        )

        print("LiteAPI Rate Status:", response.status_code)

        if response.status_code != 200:
            print("Hotel rate search failed:", response.text)
            return []

        data = response.json()
        results = []

        print("DEBUG RESPONSE:")
        print(data)

        print("DEBUG: API response keys:", data.keys())
        print("DEBUG: Number of hotels returned:", len(data.get("data", [])))
        print("DEBUG: First hotel response:", data.get("data", [])[:1])

        for hotel in data.get("data", []):
            # Find the cheapest returned rate for each room occupancy.
            best_by_occupancy = {}

            for room_type in hotel.get("roomTypes", []):
                for rate in room_type.get("rates", []):
                    occupancy_number = rate.get("occupancyNumber")

                    if occupancy_number is None:
                        continue

                    totals = (
                        rate.get("retailRate", {}).get("total", [])
                    )

                    for total in totals:
                        amount = total.get("amount")

                        if amount is None:
                            continue

                        amount = float(amount)

                        current = best_by_occupancy.get(
                            occupancy_number
                        )

                        if current is None or amount < current["price"]:
                            best_by_occupancy[occupancy_number] = {
                                "price": amount,
                                "currency": total.get("currency", "INR"),
                                "room": rate.get("name", "Not available"),
                                "meal_plan": rate.get(
                                    "boardName", "Not available"
                                ),
                                "offer_id": room_type.get("offerId")
                            }

            # Do not present an incomplete multi-room total as complete.
            expected_occupancies = set(
                range(1, len(occupancies) + 1)
            )

            if not expected_occupancies.issubset(
                best_by_occupancy.keys()
            ):
                continue

            selected_rates = [
                best_by_occupancy[number]
                for number in sorted(expected_occupancies)
            ]

            # Only combine prices in the same currency.
            currencies = {
                rate["currency"] for rate in selected_rates
            }

            if len(currencies) != 1:
                continue

            results.append({
                "hotel_id": hotel.get("hotelId"),
                "price": sum(
                    rate["price"] for rate in selected_rates
                ),
                "currency": selected_rates[0]["currency"],
                "rooms": len(occupancies),
                "room": " + ".join(
                    rate["room"] for rate in selected_rates
                ),
                "meal_plan": " + ".join(
                    rate["meal_plan"] for rate in selected_rates
                ),
                "offer_ids": [
                    rate["offer_id"] for rate in selected_rates
                ]
            })

        print("DEBUG: Complete group-rate results:", results)
        print("Hotels with complete group rates:", len(results))
        return results

    except (requests.RequestException, ValueError) as error:
        print("Hotel rate search error:", error)
        return []
