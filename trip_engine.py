import math
from agents.orchestrator import run_orchestrator
from datetime import datetime,timedelta
from data.Places import (
    get_location,
    get_attractions,
    get_accommodations,
    get_hotels, get_hotel_prices,
)
from data.Food import search_restaurants, calculate_food_budget
from data.Transport import (
    find_airport_code,
    search_flights_flightpowers,
    get_destination_airport,
    get_nearby_destination_airports,
    estimate_road_transfer_cost,
    get_alternative_departure_airports,
    search_trains,
    search_stations,
    get_train_fare,
    get_route_train_fares,
    get_train_details,
    get_train_live_status,
    find_nearby_railway_stations,
    get_road_distance_km,
    estimate_train_road_transfer_cost,
)

def run_trip(trip_input: dict) -> dict:
    """Run the existing TripForge search workflow for one validated trip request.

    The terminal interface and web API both call this same function.
    Existing transport, hotel, food and orchestrator logic is retained.
    """
    print("===== RUNNING TRIPFORGE PLANNING ENGINE =====")

    if not isinstance(trip_input, dict):
        raise ValueError("Trip input must be an object.")

    source = str(trip_input.get("source") or "").strip()
    destination = str(trip_input.get("destination") or "").strip()
    try:
        days = int(trip_input.get("days"))
        budget = float(trip_input.get("budget"))
        travellers = int(trip_input.get("travellers"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Days, budget and travellers must be valid numbers.") from exc

    transport_mode = str(trip_input.get("transport_mode") or "").strip().lower()
    if not source or not destination:
        raise ValueError("Starting location and destination are required.")
    if days < 1:
        raise ValueError("Number of days must be at least 1.")
    if budget <= 0 or not math.isfinite(budget):
        raise ValueError("Budget must be a finite amount greater than zero.")
    if travellers < 1:
        raise ValueError("Number of travellers must be at least 1.")
    if transport_mode not in {"bus", "train", "flight", "car"}:
        raise ValueError("Choose bus, train, flight, or car.")

    print("\n========== TRIP DETAILS ==========")
    print("Source:", source)
    print("Destination:", destination)
    print("Duration:", days, "days")
    print("Transport:", transport_mode)
    print("Total Budget: ₹", budget)
    print("Planning for", travellers, "traveller(s).")

    # ==========================================
    # 2. GET DESTINATION COORDINATES
    # ==========================================

    places = get_location(destination)

    if not places:
        print("Destination not found. Please try another location.")
        raise ValueError("Trip planning stopped because the supplied input or destination is invalid.")

    latitude = places["latitude"]
    longitude = places["longitude"]

    print("\nDestination coordinates:", latitude, longitude)


    # Traveller count is already validated from trip_input above.
    # Do not prompt interactively: this engine is also called by the web API.
    print("Planning for", travellers, "traveller(s).")

    # Food discovery and budget are intentionally printed at the end, after accommodation analysis.\n\nfrom datetime import datetime, timedelta

    # ==========================================
    # TRIP START DATE
    # ==========================================

    date_text = str(trip_input.get("start_date") or "").strip()
    try:
        try:
            start_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            start_date = datetime.strptime(date_text, "%d-%m-%Y").date()
        if start_date < datetime.today().date():
            raise ValueError("Trip start date must be today or a future date.")
    except ValueError as exc:
        raise ValueError("Invalid start date. Use YYYY-MM-DD or DD-MM-YYYY.") from exc

    check_in = start_date
    check_out = check_in + timedelta(days=days)

    # Format dates for display and API requests
    journey_date_display = start_date.strftime("%d-%m-%Y")
    journey_date_str = start_date.strftime("%Y-%m-%d")


    # ==========================================
    # FLIGHT SEARCH - SERPAPI
    # ==========================================

    flight_options = []
    airport_details = None
    road_transfer_cost = 0.0
    departure_road_distance_km = 0.0
    selected_source_airport = None
    selected_destination_airport = None
    selected_flight = None

    if transport_mode == "flight":
        source_airport = find_airport_code(source)
        direct_destination = get_destination_airport(destination)
        departure_date = start_date.strftime("%Y-%m-%d")

        if not source_airport:
            print("Could not identify an airport for the source. No flight search was made.")
        else:
            # Step 1: check the destination's own airport, if one can be identified.
            if direct_destination:
                direct_code = direct_destination["airport_code"]
                print("\n========== FLIGHT SEARCH ==========")
                print(f"Checking direct destination airport: {source_airport} -> {direct_code}")
                direct_options = search_flights_flightpowers(
                    source_airport, direct_code, departure_date
                )
                if direct_options is None:
                    print("SerpApi quota/rate limit reached. Stopping flight searches to protect quota.")
                    direct_options = []
                if direct_options:
                    flight_options = direct_options
                    selected_source_airport = source_airport
                    selected_destination_airport = direct_code
                    airport_details = direct_destination

            # Step 2: if no direct destination flight was found (or no direct
            # destination airport exists), try the closest practical airports.
            if not flight_options:
                if direct_destination:
                    print("\nNo flights returned for the destination's direct airport.")
                else:
                    print(f"\nNo direct airport was identified for {destination}.")

                nearby_airports = get_nearby_destination_airports(
                    destination, latitude, longitude,
                    exclude_code=(direct_destination or {}).get("airport_code"),
                    max_distance_km=350, limit=3,
                )

                if not nearby_airports:
                    print("No nearby airports with usable coordinates were found.")

                nearby_flight_candidates = []
                for nearby in nearby_airports:
                    nearby_code = nearby["airport_code"]
                    print(
                        "\nTrying nearby destination airport:",
                        nearby.get("airport_name", nearby_code),
                        f"({nearby_code})",
                    )
                    print(
                        "Estimated destination road distance:",
                        f"{nearby['road_distance_km']:.1f} km (approximate)",
                    )

                    candidate_options = search_flights_flightpowers(
                        source_airport, nearby_code, departure_date
                    )
                    if candidate_options is None:
                        print("SerpApi quota/rate limit reached. Stopping further searches.")
                        break
                    if not candidate_options:
                        continue

                    transfer_cost = estimate_road_transfer_cost(
                        nearby["road_distance_km"]
                    )
                    # Keep the cheapest flight itinerary from this route, then
                    # compare routes by group flight fare + one road transfer.
                    cheapest_route_flight = min(
                        (f for f in candidate_options
                         if isinstance(f.get("price"), (int, float)) and f["price"] > 0),
                        key=lambda f: f["price"],
                        default=None,
                    )
                    if cheapest_route_flight is None:
                        continue

                    nearby_flight_candidates.append({
                        "flight": cheapest_route_flight,
                        "airport": nearby,
                        "transfer_cost": transfer_cost,
                        "group_total": float(cheapest_route_flight["price"]) * travellers + transfer_cost,
                    })

                if nearby_flight_candidates:
                    chosen = min(nearby_flight_candidates, key=lambda item: item["group_total"])
                    flight_options = [chosen["flight"]]
                    selected_source_airport = source_airport
                    selected_destination_airport = chosen["airport"]["airport_code"]
                    airport_details = chosen["airport"]
                    road_transfer_cost = chosen["transfer_cost"]

            # If the source itself has no direct airport, search nearby departure
            # airports only after destination-side options fail. This avoids extra calls
            # when a usable direct-source route already exists.
            if not flight_options:
                print("No usable flight options were found for the source and nearby destination airports.")

            if flight_options:
                # Always choose the cheapest valid itinerary automatically.
                valid_flights = [
                    flight for flight in flight_options
                    if isinstance(flight.get("price"), (int, float)) and flight["price"] > 0
                ]
                if valid_flights:
                    selected_flight = min(valid_flights, key=lambda flight: flight["price"])
                    flight_options = [selected_flight]
                    print("\n========== AUTOMATIC FLIGHT SELECTION ==========")
                    print("Selected route:", selected_source_airport, "->", selected_destination_airport)
                    print("Airline:", selected_flight.get("airline", "Unknown"))
                    print("Flight fare per traveller:", f"₹{float(selected_flight['price']):,.2f}")
                    print("Group flight fare:", f"₹{float(selected_flight['price']) * travellers:,.2f}")
                    print("Destination road distance:", f"{float((airport_details or {}).get('road_distance_km', 0) or 0):,.1f} km (estimated)")
                    print("Estimated road transfer cost:", f"₹{road_transfer_cost:,.2f}")
                    print("Estimated transport total for group:", f"₹{float(selected_flight['price']) * travellers + road_transfer_cost:,.2f}")
                    print("Departure:", selected_flight.get("departure"))
                    print("Arrival:", selected_flight.get("arrival"))
                    print("Duration:", selected_flight.get("duration"))
                    print("Stops:", selected_flight.get("stops"))
                    print("Booking link:", selected_flight.get("booking_link"))
                else:
                    flight_options = []
                    print("Flight results did not contain a valid numeric fare. No fare was fabricated.")

    # ==========================================================
    # TRIPFORGE — TERMINAL TRAIN PLANNER
    # Train-only changes: flight, hotel, attractions and food code
    # remain unchanged.
    # ==========================================================

    train_transport_cost = None              # group train fare only
    train_fare_per_person = None
    train_road_transfer_cost = 0.0            # group road-transfer estimate
    source_station_code = None
    destination_station_code = None
    train_options = []
    selected_train = None
    fare_details = None
    selected_train_route = None

    if transport_mode == "train":
        print("\n========== AUTOMATIC TRAIN JOURNEY PLANNER ==========")
        print("Searching the requested station first, then nearby practical railheads if needed.")

        def _normalise_station_text(value):
            value = str(value or "").strip().casefold()
            for token in ("railway station", "railroad station", "junction", "jn.", "jn", "station"):
                value = value.replace(token, " ")
            return " ".join(value.replace(".", " ").replace(",", " ").split())

        def _auto_station(query, label):
            """Resolve a user-provided city/station through the existing station lookup."""
            normalized_query = _normalise_station_text(query)
            if not normalized_query:
                print(f"Cannot resolve {label} station: location is empty.")
                return None
            try:
                candidates = search_stations(str(query).strip()) or []
            except Exception as exc:
                print(f"Station search failed for {label} '{query}': {exc}")
                return None

            usable = []
            query_tokens = {part for part in normalized_query.split() if len(part) > 2}
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                code = str(item.get("code") or item.get("station_code") or "").strip().upper()
                if not code:
                    continue
                name = _normalise_station_text(item.get("name"))
                city = _normalise_station_text(item.get("city"))
                name_tokens = {part for part in name.split() if len(part) > 2}
                city_tokens = {part for part in city.split() if len(part) > 2}
                score = 0
                if name == normalized_query:
                    score = 100
                elif city == normalized_query:
                    score = 95
                elif normalized_query and (normalized_query in name or name in normalized_query):
                    score = 85
                elif query_tokens and query_tokens.intersection(name_tokens | city_tokens):
                    score = 70
                if score:
                    usable.append((score, dict(item), code))

            if not usable:
                print(f"No confident station-code match was returned for {label} '{query}'.")
                return None

            usable.sort(key=lambda row: row[0], reverse=True)
            _, chosen, code = usable[0]
            chosen["code"] = code
            print(f"Selected {label} station: {chosen.get('name', 'Unnamed station')} ({code})")
            return chosen

        chosen_source = _auto_station(source, "source")
        chosen_destination = _auto_station(destination, "destination")
        route_candidates = []

        if chosen_source and chosen_destination:
            source_station_code = chosen_source["code"]
            destination_station_code = chosen_destination["code"]

            if source_station_code == destination_station_code:
                print("Source and destination resolved to the same station; train search skipped.")
            else:
                print(f"\nSearching direct trains {source_station_code} → {destination_station_code}...")
                direct_trains = search_trains(
                    source_code=source_station_code,
                    destination_code=destination_station_code,
                    journey_date=journey_date_display,
                ) or []
                if direct_trains:
                    route_candidates.append({
                        "from": source_station_code,
                        "to": destination_station_code,
                        "label": f"{chosen_source.get('name')} → {chosen_destination.get('name')}",
                        "date": journey_date_display,
                        "trains": direct_trains,
                        "nearby_station": None,
                        "transfer_distance_km": 0.0,
                    })
                else:
                    print("No direct train was returned for the exact destination station.")

            # The current train API exposes direct /between searches, not a
            # multi-leg connection planner. Try a small number of dynamically
            # discovered nearby railheads; never invent an intermediate train.
            if not route_candidates:
                print("Looking for nearby railway stations that may have a direct train from the source...")
                nearby_stations = find_nearby_railway_stations(
                    destination, radius_km=120, limit=30
                ) or []
                candidates_for_search = []
                for station in nearby_stations:
                    if not isinstance(station, dict):
                        continue
                    name = str(station.get("name") or "").strip()
                    try:
                        distance = float(station.get("distance_km_straight_line"))
                        station_lat = float(station.get("latitude"))
                        station_lon = float(station.get("longitude"))
                    except (TypeError, ValueError):
                        continue
                    if not name or distance < 20 or distance > 120:
                        continue
                    if _normalise_station_text(name) == _normalise_station_text(destination):
                        continue
                    candidates_for_search.append({
                        "name": name,
                        "distance_km": distance,
                        "latitude": station_lat,
                        "longitude": station_lon,
                    })

                # Nearest practical railheads first. Try up to eight dynamically
                # discovered stations: the closest locations may be small halts
                # or may not resolve in IRCTC autocomplete. This bounded limit
                # avoids searching all 30 results and wasting RapidAPI quota.
                candidates_for_search.sort(key=lambda item: item["distance_km"])
                candidates_for_search = candidates_for_search[:8]
                print(
                    f"Checking up to {len(candidates_for_search)} nearby station candidates "
                    "with IRCTC autocomplete/train search."
                )

                seen_codes = {source_station_code, destination_station_code}
                for nearby in candidates_for_search:
                    nearby_station = _auto_station(nearby["name"], "nearby destination")
                    if not nearby_station:
                        continue
                    nearby_code = nearby_station["code"]
                    if nearby_code in seen_codes:
                        continue
                    seen_codes.add(nearby_code)

                    print(
                        f"Trying direct train to nearby railhead {nearby_station.get('name')} "
                        f"({nearby_code}); approx. {nearby['distance_km']:.1f} km from destination."
                    )
                    candidate_trains = search_trains(
                        source_code=source_station_code,
                        destination_code=nearby_code,
                        journey_date=journey_date_display,
                    ) or []
                    if candidate_trains:
                        route_candidates.append({
                            "from": source_station_code,
                            "to": nearby_code,
                            "label": f"{chosen_source.get('name')} → {nearby_station.get('name')}",
                            "date": journey_date_display,
                            "trains": candidate_trains,
                            "nearby_station": nearby,
                            "transfer_distance_km": nearby["distance_km"],
                        })
                        # Use the first reachable nearby railhead. This avoids
                        # unnecessary route/fare API calls and preserves quota.
                        break

        else:
            print("Source or destination station lookup failed; no train route search was made.")

        # Get fares only for a route that actually returned train records.
        # The route-wide endpoint is called at most once for the selected route.
        for leg in route_candidates:
            print(f"\nRetrieving fare data for {leg['label']}...")
            route_fares = get_route_train_fares(
                source_code=leg["from"],
                destination_code=leg["to"],
                journey_date=leg["date"],
                quota="GN",
            ) or []

            fares_by_train = {}
            for fare in route_fares:
                if not isinstance(fare, dict):
                    continue
                number = str(fare.get("train_number") or "").strip()
                travel_class = str(fare.get("class") or "").strip().upper()
                try:
                    amount = float(fare.get("fare_per_person"))
                except (TypeError, ValueError, OverflowError):
                    continue
                if number and travel_class and math.isfinite(amount) and amount > 0:
                    fares_by_train.setdefault(number, []).append({
                        "class": travel_class,
                        "fare_per_person": amount,
                    })

            priced_options = []
            for train in leg["trains"]:
                number = str(train.get("train_number") or train.get("train_no") or "").strip()
                candidate_fares = fares_by_train.get(number, [])
                if not candidate_fares and number:
                    for returned_number, returned_fares in fares_by_train.items():
                        if returned_number.lstrip("0") == number.lstrip("0"):
                            candidate_fares = returned_fares
                            break
                valid_fares = [
                    item for item in candidate_fares
                    if isinstance(item.get("fare_per_person"), (int, float))
                    and math.isfinite(float(item["fare_per_person"]))
                    and float(item["fare_per_person"]) > 0
                    and str(item.get("class") or "").strip()
                ]
                if valid_fares:
                    cheapest_class = min(valid_fares, key=lambda item: item["fare_per_person"])
                    priced_options.append({
                        "train": train,
                        "class": cheapest_class["class"],
                        "fare_per_person": float(cheapest_class["fare_per_person"]),
                    })

            if not priced_options:
                print(f"No usable per-person fare was returned for {leg['label']}.")
                continue

            best = min(priced_options, key=lambda item: item["fare_per_person"])
            selected_train = best["train"]
            selected_train_route = leg
            fare_details = best
            train_fare_per_person = best["fare_per_person"]
            train_transport_cost = train_fare_per_person * travellers

            # For a nearby railhead, estimate the onward road leg from the OSM
            # straight-line distance. It is explicitly an estimate, not a quoted fare.
            nearby = leg.get("nearby_station")
            if nearby:
                approximate_road_km = float(leg["transfer_distance_km"]) * 1.25
                vehicles_required = max(1, math.ceil(travellers / 4))
                transfer = estimate_train_road_transfer_cost(
                    approximate_road_km,
                    travellers=travellers,
                    vehicles_required=vehicles_required,
                )
                if isinstance(transfer, dict) and transfer.get("estimated_total_fare") is not None:
                    train_road_transfer_cost = float(transfer["estimated_total_fare"])
                else:
                    train_road_transfer_cost = 0.0
                    print("Warning: onward road transfer could not be estimated and is excluded.")

            print("\n========== TRAIN FARE BREAKDOWN ==========")
            print("Selected train:", selected_train.get("train_name") or selected_train.get("name") or "Train")
            print("Train number:", selected_train.get("train_number") or selected_train.get("train_no") or "Not provided")
            print("Selected class:", fare_details["class"])
            print(f"Fare per person: ₹{train_fare_per_person:,.2f}")
            print("Number of travellers:", travellers)
            print(f"Total train fare ({travellers} × ₹{train_fare_per_person:,.2f}): ₹{train_transport_cost:,.2f}")
            if nearby:
                print("Destination railhead:", leg["to"])
                print(f"Approximate onward road distance: {approximate_road_km:,.1f} km")
                print(f"Estimated group road transfer: ₹{train_road_transfer_cost:,.2f}")
            print(f"Group transport estimate: ₹{train_transport_cost + train_road_transfer_cost:,.2f}")
            print("Fare source: returned route-fare data; final booking amount/availability may differ.")
            break

        if train_transport_cost is None:
            print("\nNo usable train fare was returned for the direct or nearby-railhead searches.")
            print("The current API functions search direct station pairs; they do not discover multi-train connections.")
            print("TripForge will keep the train fare out of the budget rather than inventing a connection or amount.")


    print("Check-in:", check_in.strftime("%d-%m-%Y"))
    print("Check-out:", check_out.strftime("%d-%m-%Y"))




    # ==========================================================
    # EARLY TRANSPORT-ONLY BUDGET CHECK
    # Stop before attractions, accommodation, hotel rates or food
    # when the confirmed group transport cost already exceeds budget.
    # ==========================================================
    transport_group_cost = None
    transport_fare_per_person = None
    if transport_mode == "flight" and selected_flight:
        try:
            transport_fare_per_person = float(selected_flight.get("price"))
            candidate_total = transport_fare_per_person * travellers + float(road_transfer_cost or 0)
            if math.isfinite(candidate_total) and candidate_total > 0:
                transport_group_cost = candidate_total
        except (TypeError, ValueError, OverflowError):
            transport_group_cost = None
    elif transport_mode == "train" and train_transport_cost is not None:
        try:
            transport_group_cost = float(train_transport_cost) + float(train_road_transfer_cost or 0)
            transport_fare_per_person = float(train_fare_per_person) if train_fare_per_person is not None else None
            if not math.isfinite(transport_group_cost) or transport_group_cost <= 0:
                transport_group_cost = None
        except (TypeError, ValueError, OverflowError):
            transport_group_cost = None

    if transport_group_cost is not None and transport_group_cost > budget:
        minimum_shortfall = transport_group_cost - budget
        print("\n========== OVER-BUDGET: PLANNING PAUSED ==========")
        print(f"Total trip budget: ₹{budget:,.2f}")
        print(f"Intercity transport for {travellers} traveller(s): ₹{transport_group_cost:,.2f}")
        print(f"Minimum shortfall (transport alone): ₹{minimum_shortfall:,.2f}")
        print("Hotel, attraction and food searches were skipped because transport alone exceeds the budget.")

        trip_request = {
            "source": source, "destination": destination, "days": days,
            "budget": budget, "transport_mode": transport_mode,
            "travellers": travellers, "start_date": journey_date_display,
        }
        transport_details = {
            "mode": transport_mode,
            "group_cost": transport_group_cost,
            "fare_confirmed": True,
            "fare_per_person": transport_fare_per_person,
            "road_transfer_cost": road_transfer_cost if transport_mode == "flight" else train_road_transfer_cost,
            "flight_options": flight_options if transport_mode == "flight" else [],
            "selected_flight": selected_flight if transport_mode == "flight" else None,
        }
        plan = {
            "status": "transport_over_budget",
            "provisional": False,
            "full_trip_total_confirmed": False,
            "full_trip_estimate_available": False,
            "trip": trip_request,
            "transport": transport_details,
            "budget": {"total_budget": budget, "transport": transport_group_cost, "shortfall": minimum_shortfall},
            "transport_budget_check": {
                "exceeds_budget": True, "total_budget": budget,
                "transport_cost": transport_group_cost,
                "minimum_shortfall": minimum_shortfall,
                "travellers": travellers,
            },
            "stay": {"group_rates": []},
            "food": {"food_budget_results": {}},
            "food_scenario_totals": {},
            "budget_warning": "Trip planned won't fit into the given budget. Please change the budget.",
            "final_budget": {
                "available": False,
                "over_budget": True,
                "budget": budget,
                "components": {
                    "transport": transport_group_cost,
                    "accommodation": None,
                    "food": None,
                    "local_transport": None,
                    "attractions": None,
                },
                "total_low": None,
                "total_high": None,
                "remaining_at_high": None,
                "shortfall_at_high": minimum_shortfall,
                "status": "transport_over_budget",
                "warning": "Trip planned won't fit into the given budget. Please change the budget.",
                "is_estimate": True,
            },
        }
        return {
            "trip_request": trip_request,
            "plan": plan,
            "search_results": {
                "flight_options": flight_options,
                "selected_flight": selected_flight,
                "selected_source_airport": selected_source_airport,
                "selected_destination_airport": selected_destination_airport,
                "airport_details": airport_details,
                "train_options": train_options,
                "selected_train": selected_train,
                "fare_details": fare_details,
                "selected_train_route": selected_train_route,
                "train_transport_cost": train_transport_cost,
                "train_fare_per_person": train_fare_per_person,
                "train_road_transfer_cost": train_road_transfer_cost,
                "hotels": [], "hotel_group_rates": [],
                "attractions": [], "accommodations": [], "restaurants": [],
            },
        }

    # ==========================================
    # 3. GET ATTRACTIONS
    # ==========================================

    attractions = get_attractions(latitude, longitude, destination)

    print("\n========== ATTRACTIONS ==========")

    if not attractions:
        print("No attractions found for this destination.")

    else:
        for attraction in attractions:
            print(
                "Name:", attraction.get("name", "Unknown"),
                "| Category:", attraction.get("category"),
                "| Latitude:", attraction.get("latitude"),
                "| Longitude:", attraction.get("longitude")
            )


    # ==========================================
    # 4. GET ACCOMMODATIONS
    # ==========================================

    accommodations = get_accommodations(latitude, longitude)

    print("\n========== ACCOMMODATIONS ==========")

    if not accommodations:
        print("No accommodations found for this destination.")

    else:
        for accommodation in accommodations:
            print(
                "Name:", accommodation.get("name", "Unknown"),
                "| Distance:", accommodation.get("distance"),
                "m | Type:", accommodation.get("type")
            )


    # ==========================================
    # 2. GET HOTELS AND THEIR PRICES
    # ==========================================

    hotels = get_hotels(latitude, longitude) or []

    print("\n========== HOTEL DISCOVERY ==========")

    if not hotels:
        print("No hotels found.")
        hotel_prices = []

    else:
        for hotel in hotels:
            print(
                hotel.get("name", "Unknown"),
                "| Rating:", hotel.get("rating"),
                "| ID:", hotel.get("id")
            )

        # Extract hotel IDs from the discovered records
        hotel_ids = [
            hotel.get("id")
            for hotel in hotels
            if hotel.get("id")
        ]

        # Search for rates for the requested dates

        print("\nTotal hotel IDs to process:", len(hotel_ids))
        print("First 10 hotel IDs:", hotel_ids[:10])

        hotel_prices = []
        batch_size = 10
        for start in range(0, len(hotel_ids), batch_size):
            batch_ids = hotel_ids[start:start + batch_size]
            print(
            f"\nChecking hotel rates "
            f"{start + 1} to {start + len(batch_ids)} "
            f"of {len(hotel_ids)}"
            )

            batch_prices = get_hotel_prices(
                batch_ids,
                check_in,
                check_out,
                travellers
            )

            hotel_prices.extend(batch_prices)

    # Remove duplicate hotel results, if any.
        unique_prices = {}

        for rate in hotel_prices:
            hotel_id = rate.get("hotel_id")
            if hotel_id:
                unique_prices[hotel_id] = rate

        hotel_prices = list(unique_prices.values())

        print("\nTotal hotels with complete group rates:", len(hotel_prices))




    # ==========================================
    # 5. SUMMARY
    # ==========================================

    print("\n========== TRIP SEARCH SUMMARY ==========")

    print(f"Destination: {destination}")
    print(f"Total budget: ₹{budget:,.2f}")
    print(f"Number of travellers: {travellers}")
    print(f"Mode of transport: {transport_mode.title()}")
    print(f"Start date: {check_in.strftime('%d-%m-%Y')}")
    print(f"End date: {check_out.strftime('%d-%m-%Y')}")

    print("\nSearch completed.")

    # ==========================================
    # 3. ALLOCATE BUDGET AND RANK HOTEL OPTIONS
    # ==========================================


    # ==========================================
    # TRIPFORGE - BUDGET PLANNER
    # Independent Python module; no Streamlit
    # ==========================================

    def calculate_transport_cost(
        transport_mode,
        travellers,
        flight_options=None,
        train_transport_cost=None,
        road_transfer_cost=0,
        train_road_transfer_cost=0,
    ):
        """
        Calculate transport cost for the entire group.

        Flight price: per person.
        Train price: already the total for the group.
        Road transfer: total cost for the group.
        """

        travellers = max(1, int(travellers))
        mode = str(transport_mode).strip().lower()

        if mode == "flight":
            if not flight_options:
                raise ValueError("No flight options are available.")

            try:
                price_per_person = float(
                    flight_options[0]["price"]
                )
                road_cost = float(road_transfer_cost or 0)
                if not math.isfinite(price_per_person) or not math.isfinite(road_cost):
                    raise ValueError("Flight fare or road-transfer cost is not a valid number.")
            except (KeyError, TypeError, ValueError):
                raise ValueError(
                    "Flight fare or road-transfer cost is invalid."
                )

            if price_per_person <= 0:
                raise ValueError("Flight fare must be positive.")

            if road_cost < 0:
                raise ValueError(
                    "Road-transfer cost cannot be negative."
                )

            return price_per_person * travellers + road_cost

        elif mode == "train":
            if train_transport_cost is None:
                raise ValueError(
                    "Train fare is unavailable. Retrieve a valid fare first."
                )

            try:
                group_train_fare = float(train_transport_cost)
                transfer_cost = float(
                    train_road_transfer_cost or 0
                )
                if not math.isfinite(group_train_fare) or not math.isfinite(transfer_cost):
                    raise ValueError("Train fare or transfer cost is not a valid number.")
            except (TypeError, ValueError):
                raise ValueError(
                    "Train fare or transfer cost is invalid."
                )

            if group_train_fare <= 0:
                raise ValueError("Group train fare must be positive.")

            if transfer_cost < 0:
                raise ValueError(
                    "Train road-transfer cost cannot be negative."
                )

            return group_train_fare + transfer_cost

        else:
            raise ValueError(
                f"Unsupported transport mode: {transport_mode}"
            )


    def calculate_trip_budget(
        total_budget,
        travellers,
        days,
        transport_cost,
        hotel_prices,
        food_per_person_per_day=450,
        local_per_person_per_day=150,
        attractions_per_person_per_day=150,
    ):
        """
        Calculate a group budget for the complete trip.

        IMPORTANT:
        hotel_prices must contain prices for the entire group
        and the complete stay, not nightly or per-person prices.
        """

        try:
            total_budget = float(total_budget)
            transport_cost = float(transport_cost)
            food_per_person_per_day = float(food_per_person_per_day)
            local_per_person_per_day = float(local_per_person_per_day)
            attractions_per_person_per_day = float(attractions_per_person_per_day
            )
            travellers = int(travellers)
            days = int(days)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                "Budget inputs must contain valid numbers."
            ) from exc
        if not math.isfinite(total_budget) or total_budget <= 0:
            raise ValueError(
                "Budget must be finite and greater than zero."
            )
        if not math.isfinite(transport_cost) or transport_cost < 0:
            raise ValueError(
                "Transport cost must be finite and cannot be negative."
            )
        expenses = {
            "Food": food_per_person_per_day,
            "Local travel": local_per_person_per_day,
            "Attractions": attractions_per_person_per_day,
        }
        for name, amount in expenses.items():
            if not math.isfinite(amount) or amount < 0:
                raise ValueError(
                    f"{name} cost must be finite and cannot be negative."
                )

        if travellers < 1:
            raise ValueError("Travellers must be at least 1.")
        if days < 1:
            raise ValueError("Days must be at least 1.")
        nights = max(0, days - 1)

        food_total = (
            float(food_per_person_per_day) * travellers * days
        )

        local_total = (
            float(local_per_person_per_day) * travellers * days
        )

        attractions_total = (
            float(attractions_per_person_per_day)
            * travellers * days
        )

        essential_total = (
            transport_cost
            + food_total
            + local_total
            + attractions_total
        )

        accommodation_budget = max(
            0.0,
            total_budget - essential_total
        )

        # Keep only valid hotel prices for the full group and stay.
        valid_hotels = []
        if hotel_prices is None:
                hotel_prices = []
        if not isinstance(hotel_prices, (list, tuple)):
            raise ValueError("Hotel prices must be provided as a list.")


        for hotel in hotel_prices or []:
            try:
                price = float(
                    hotel.get(
                        "total_price",
                        hotel.get("price", 0)
                    )
                )

                if math.isfinite(price) and price > 0:
                    valid_hotels.append({
                        "name": hotel.get("name", "Unknown hotel"),
                        "price": price,
                        "rating": hotel.get("rating"),
                        "review_count": hotel.get("review_count"),
                        "id": hotel.get("id"),
                    })

            except (TypeError, ValueError, AttributeError):
                continue

        valid_hotels.sort(key=lambda hotel: hotel["price"])

        affordable_hotels = [
            hotel for hotel in valid_hotels
            if hotel["price"] <= accommodation_budget
        ]

        cheapest_hotel = (
            valid_hotels[0] if valid_hotels else None
        )

        recommended_hotel = (
            affordable_hotels[0] if affordable_hotels else None
        )

        estimated_total = None
        shortfall = None

        if cheapest_hotel is not None:
            estimated_total = (
                essential_total + cheapest_hotel["price"]
            )
            shortfall = max(
                0.0,
                estimated_total - total_budget
            )

        if recommended_hotel is not None:
            status = "within_budget"
        elif cheapest_hotel is not None:
            status = "over_budget"
        else:
            status = "hotel_price_unavailable"

        return {
            "status": status,
            "total_budget": total_budget,
            "travellers": travellers,
            "days": days,
            "nights": nights,
            "transport": transport_cost,
            "food": food_total,
            "local_travel": local_total,
            "attractions": attractions_total,
            "essential_total": essential_total,
            "accommodation_budget": accommodation_budget,
            "cheapest_hotel": cheapest_hotel,
            "recommended_hotel": recommended_hotel,
            "estimated_total": estimated_total,
            "shortfall": shortfall,
            "affordable_hotels": affordable_hotels,
        }


    def print_budget_summary(result):
        """Print a readable summary for a conversational bot."""

        print("\n========== TRIPFORGE BUDGET ==========")
        print(f"Budget: ₹{result['total_budget']:,.2f}")
        print(f"Travellers: {result['travellers']}")
        print(
            f"Duration: {result['days']} days, "
            f"{result['nights']} nights"
        )

        print("\nEstimated group expenses:")
        for label, key in [
            ("Transport", "transport"),
            ("Local travel", "local_travel"),
            ("Attractions", "attractions"),
        ]:
            print(f"{label}: ₹{result[key]:,.2f}")

        # Show the same moderate food range here that is detailed in the final food plan.
        # The existing budget calculation still uses its baseline food allowance, so
        # disclose it to avoid presenting the range as the amount used internally.
        food_low = 400 * result["travellers"] * result["days"]
        food_high = 600 * result["travellers"] * result["days"]
        print(
            f"Food (moderate estimate): ₹{food_low:,.2f}–₹{food_high:,.2f} "
            f"| baseline used in preliminary calculation: ₹{result['food']:,.2f}"
        )

        print(
            "Accommodation budget: "
            f"₹{result['accommodation_budget']:,.2f}"
        )

        if result["recommended_hotel"]:
            hotel = result["recommended_hotel"]
            print("\nAffordable hotel found:")
            print(f"Name: {hotel['name']}")
            print(f"Full-stay group price: ₹{hotel['price']:,.2f}")

            final_total = (
                result["essential_total"] + hotel["price"]
            )
            print(f"Estimated trip total: ₹{final_total:,.2f}")
            print(
                f"Remaining budget: "
                f"₹{result['total_budget'] - final_total:,.2f}"
            )

        elif result["cheapest_hotel"]:
            hotel = result["cheapest_hotel"]
            print("\nNo returned hotel fits the accommodation budget.")
            print(f"Cheapest returned hotel: {hotel['name']}")
            print(f"Full-stay group price: ₹{hotel['price']:,.2f}")
            print(f"Estimated shortfall: ₹{result['shortfall']:,.2f}")

        else:
            print(
                "\nHotel prices are unavailable. "
                "A complete-trip total cannot yet be confirmed."
            )

        print(f"\nBudget status: {result['status']}")




    # ==========================================================
    # FINAL AI BUDGET PLANNER SUMMARY
    # ==========================================================

    def _normalise_group_hotel_rates(rate_records, hotel_records):
        """Join rate rows with discovered hotel metadata without guessing prices."""
        hotel_lookup = {}
        for item in hotel_records or []:
            if not isinstance(item, dict):
                continue
            hid = item.get("hotelId", item.get("id", item.get("hotel_id")))
            if hid is not None:
                hotel_lookup[str(hid).strip()] = item

        normalised = []
        for rate in rate_records or []:
            if not isinstance(rate, dict):
                continue
            hid = rate.get("hotel_id", rate.get("hotelId", rate.get("id")))
            meta = hotel_lookup.get(str(hid).strip(), {}) if hid is not None else {}
            price = rate.get("total_price", rate.get("price", rate.get("amount")))
            try:
                price = float(price)
            except (TypeError, ValueError,OverflowError):
                continue
            if not math.isfinite(price) or price <= 0:
                continue
            normalised.append({
                "id": hid,
                "hotel_id": hid,
                "name": meta.get("name", rate.get("name", "Unknown hotel")),
                "rating": meta.get("rating", rate.get("rating")),
                "review_count": meta.get(
                "review_count",
                meta.get(
                    "reviewCount",
                    rate.get("review_count", rate.get("reviewCount"))
                )
            ),
            "price": price,
            "total_price": price,
            "room": rate.get("room", rate.get("roomName", "Not specified")),
            "meal_plan": rate.get("meal_plan", rate.get("mealPlan", "Not specified")),
            })

        return normalised


    print("\n========== AI BUDGET PLANNER ==========")

    # The orchestrator coordinates results already fetched above. It makes no API
    # requests; transport and budget helpers are injected from this file.
    trip_request = {
        "source": source,
        "destination": destination,
        "days": days,
        "budget": budget,
        "transport_mode": transport_mode,
        "travellers": travellers,
        "start_date": journey_date_display,
    }

    existing_results = {
        "flight_options": flight_options,
        "train_transport_cost": train_transport_cost,
        "train_fare_per_person": train_fare_per_person,
        "road_transfer_cost": road_transfer_cost,
        "train_road_transfer_cost": train_road_transfer_cost,
        "hotels": hotels,
        "hotel_prices": hotel_prices,
        "attractions": attractions,
        "accommodations": accommodations,
        "latitude": latitude,
        "longitude": longitude,
        "restaurants": [],  # Restaurant discovery happens in the final food section.
        "food_budget_results": {},  # Populated below after meal scenarios are calculated.
        "check_in": check_in,
        "check_out": check_out,
    }

    try:
        orchestrator_plan = run_orchestrator(
            trip_request,
            existing_results,
            calculate_transport_cost=calculate_transport_cost,
            normalise_group_hotel_rates=_normalise_group_hotel_rates,
            calculate_trip_budget=calculate_trip_budget,
        )
        # Print a compact summary locally; agents/orchestrator.py does not need
        # to define a separate print_orchestrator_summary() helper.
        if not isinstance(orchestrator_plan, dict):
            raise RuntimeError(
                "run_orchestrator() returned None or an invalid result. "
                "Check every return path in agents/orchestrator.py."
            )
        print("\n========== ORCHESTRATOR SUMMARY ==========")
        print("Status:", orchestrator_plan.get("status", "unknown"))
        print("Transport mode:", orchestrator_plan.get("transport", {}).get("mode", transport_mode))
        print("Provisional plan:", orchestrator_plan.get("provisional", False))
        if orchestrator_plan.get("normalization_error"):
            print(
            "Hotel-rate warning:",
            orchestrator_plan["normalization_error"],
            )

        # Preserve these names because the existing food-aware budget check below
        # consumes them. The orchestrator is now the sole owner of this calculation.
        budget_result = orchestrator_plan.get("budget")
        grouped_rates = orchestrator_plan.get("stay", {}).get("group_rates", [])
        transport_cost = orchestrator_plan.get("transport", {}).get("group_cost")

        if orchestrator_plan.get("provisional"):
            print("\nTrain fare is unavailable for the searched route; the provisional estimate excludes train fare.")
        elif transport_cost is None:
            print("\nCannot confirm the full-trip total because no verified intercity fare is available.")
            print("No missing fare has been replaced with a fabricated amount.")
        elif orchestrator_plan.get("budget_error"):
            print("Budget calculation failed safely:", orchestrator_plan["budget_error"])

        if budget_result:
            print("\nTop accommodation rates returned for the full stay/group:")
            if grouped_rates:
                ranked = sorted(
                    grouped_rates,
                    key=lambda item: (
                        item["price"] > budget_result["accommodation_budget"],
                        -(float(item["rating"]) if str(item.get("rating", "")).replace(".", "", 1).isdigit() else 0),
                        item["price"],
                    ),
                )
                for item in ranked[:5]:
                    print(
                        f"- {item['name']} | Rating: {item.get('rating', 'N/A')} | "
                        f"Full-stay price: ₹{item['price']:,.2f} | Room: {item['room']}"
                    )
            else:
                print("No valid group/stay hotel rates returned. Hotel discovery alone is not a confirmed price.")
    except (ValueError, TypeError, KeyError) as exc:
        orchestrator_plan = None
        budget_result = None
        grouped_rates = []
        transport_cost = None
        print("Trip orchestration failed safely:", exc)
        print("Destination discoveries are still available above; no fake transport fare has been added.")

    # ==========================================================
    # FINAL FOOD PLAN
    # Printed only after transport and accommodation analysis.
    # The cost bands below are explicitly planning estimates,
    # not verified restaurant menu prices.
    # ==========================================================

    print("\n========== FINAL FOOD BUDGET PLAN ==========")

    # These are transparent planning bands, not claims about live menu prices.
    # Per-person/day estimates cover breakfast + lunch + dinner combined.
    food_scenarios = {
        "Budget": {
            "breakfast": (60, 100),
            "lunch": (100, 150),
            "dinner": (100, 150),
        },
        "Moderate (recommended)": {
            "breakfast": (100, 150),
            "lunch": (150, 225),
            "dinner": (150, 225),
        },
        "Higher-spend": {
            "breakfast": (150, 250),
            "lunch": (250, 350),
            "dinner": (250, 350),
        },
    }

    print("\nNearby restaurant options (sorted by verified menu price where available):")
    try:
        restaurants = search_restaurants(latitude, longitude, radius=3000, limit=30)
        if not restaurants:
            print("No restaurant listings returned. No menu prices have been invented.")
        else:
            for restaurant in restaurants[:15]:
                print("\nName:", restaurant.get("name", "Unknown"))
                print("Address:", restaurant.get("address") or "Not provided")
                print("Distance:", f"{restaurant.get('distance_m')} m"
                      if restaurant.get("distance_m") is not None else "Not provided")
                print("Rating:", restaurant.get("rating")
                      if restaurant.get("rating") is not None else "Not provided")
                print("Review count:", restaurant.get("review_count")
                      if restaurant.get("review_count") is not None else "Not provided")
                if restaurant.get("menu_price") is not None:
                    print("Source-provided menu price:", restaurant["menu_price"],
                          "(confirm directly with the venue)")
                else:
                    print("Menu price: Not available from source")
                if restaurant.get("website"):
                    print("Website:", restaurant["website"])
    except (ValueError, TypeError, KeyError) as exc:
        print("Restaurant listings could not be displayed:", exc)

    food_budget_results = {}
    print("\nMeal-by-meal estimates (₹ per person per day; estimates, not verified menu prices):")
    for scenario_name, meal_ranges in food_scenarios.items():
        try:
            result = calculate_food_budget(travellers, days, meal_ranges)
            food_budget_results[scenario_name] = result
            print(f"\n{scenario_name}:")
            for meal_name in ("breakfast", "lunch", "dinner"):
                meal = result["meal_breakdown"][meal_name]
                print(
                    f"  {meal_name.title()}: ₹{meal['per_person_low']:,.0f}–"
                    f"₹{meal['per_person_high']:,.0f}"
                )
            print(
                f"  Daily total/person: ₹{result['per_person_per_day_low']:,.0f}–"
                f"₹{result['per_person_per_day_high']:,.0f}"
            )
            print(
                f"  Group total ({travellers} traveller(s) × {days} day(s)): "
                f"₹{result['group_total_low']:,.0f}–₹{result['group_total_high']:,.0f}"
            )
        except (ValueError, TypeError, KeyError) as exc:
            print(f"Could not calculate {scenario_name} food range:", exc)

    # Re-run orchestration with completed food-agent outputs. This is local
    # computation only and does not issue additional API requests.
    existing_results["restaurants"] = restaurants if "restaurants" in locals() else []
    existing_results["food_budget_results"] = food_budget_results
    existing_results["train_fare_per_person"] = train_fare_per_person
    # ==========================================================
    # FINAL FOOD-AWARE ORCHESTRATION
    # Local computation only — no additional API requests.
    # ==========================================================

    try:
        orchestrator_plan = run_orchestrator(
            trip_request,
            existing_results,
            calculate_transport_cost=calculate_transport_cost,
            normalise_group_hotel_rates=_normalise_group_hotel_rates,
            calculate_trip_budget=calculate_trip_budget,
        )

        if not isinstance(orchestrator_plan, dict):
            raise RuntimeError(
                "run_orchestrator() returned an invalid result."
            )

    except Exception as exc:
        orchestrator_plan = None
        print("Final food-aware orchestration failed safely:", exc)


    # ==========================================================
    # FINAL ORCHESTRATOR RESULT — PRINT ONLY ONCE
    # ==========================================================

    print("\n========== FINAL ORCHESTRATOR RESULT ==========")

    if not isinstance(orchestrator_plan, dict):

        print("Status: unavailable")
        print("Full trip total confirmed: False")
        print("The orchestrator did not return a valid result.")

    else:

        print("Status:", orchestrator_plan.get("status", "unknown"))

        print(
            "Full trip total confirmed:",
            orchestrator_plan.get("full_trip_total_confirmed", False)
        )

        print(
            "Provisional plan:",
            orchestrator_plan.get("provisional", False)
        )

        if orchestrator_plan.get("food_validation_error"):
            print(
                "Food validation:",
                orchestrator_plan["food_validation_error"]
            )

        if orchestrator_plan.get("budget_error"):
            print(
                "Budget calculation warning:",
                orchestrator_plan["budget_error"]
            )

        food_totals = orchestrator_plan.get(
            "food_scenario_totals", {}
        )

        if food_totals:

            print("\n========== COMPLETE FOOD-AWARE BUDGET ==========")

            for scenario_name, totals in food_totals.items():

                print(f"\n{scenario_name}")

                if orchestrator_plan.get("provisional") and transport_mode == "train":
                    print(
                        f"Estimated subtotal (train fare excluded): "
                        f"₹{totals['total_low']:,.2f}–"
                        f"₹{totals['total_high']:,.2f}"
                    )
                    print("Budget status: PROVISIONAL — train fare is excluded")
                    print("Remaining budget: Not final until the train fare is available")
                else:
                    print(
                        f"Estimated total: "
                        f"₹{totals['total_low']:,.2f}–"
                        f"₹{totals['total_high']:,.2f}"
                    )
                    print("Budget status:", totals["status"])
                    print(
                        "Remaining at higher estimate:",
                        f"₹{totals['remaining_at_high']:,.2f}"
                    )

                if totals.get("shortfall_at_high", 0) > 0 and not (orchestrator_plan.get("provisional") and transport_mode == "train"):
                    print(
                        "Budget shortfall:",
                        f"₹{totals['shortfall_at_high']:,.2f}"
                    )

        else:
            print("\nNo valid food-aware budget totals are available.")

    print("\nTripForge planning run finished.")

    # Structured response used by the API and external user interface.
    return {
        "trip_request": trip_request,
        "plan": orchestrator_plan if isinstance(orchestrator_plan, dict) else None,
        "search_results": {
            "flight_options": flight_options,
            "selected_flight": selected_flight,
            "selected_source_airport": selected_source_airport,
            "selected_destination_airport": selected_destination_airport,
            "airport_details": airport_details,
            "train_options": train_options,
            "selected_train": selected_train,
            "fare_details": fare_details,
            "selected_train_route": selected_train_route,
            "train_transport_cost": train_transport_cost,
            "train_fare_per_person": train_fare_per_person,
            "train_road_transfer_cost": train_road_transfer_cost,
            "hotels": hotels,
            "hotel_group_rates": grouped_rates,
            "attractions": attractions,
            "accommodations": accommodations,
            "restaurants": restaurants if "restaurants" in locals() else [],
            "food_budget_results": food_budget_results if "food_budget_results" in locals() else {},
        },
    }
