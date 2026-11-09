
"""Read-only specialist agents for TripForge results.

These agents inspect results already returned by the existing trip engine.
They do not make external API calls or repeat provider searches.
"""


def _items(value):
    return value if isinstance(value, list) else []


def _is_positive_number(value):
    try:
        return float(value) > 0
    except (TypeError, ValueError, OverflowError):
        return False


class SpecialistAgent:
    name = "specialist"

    def review(self, search_results, plan):
        raise NotImplementedError


class TransportAgent(SpecialistAgent):
    name = "transport_agent"

    def review(self, search_results, plan):
        flights = _items(search_results.get("flight_options"))
        trains = _items(search_results.get("train_options"))

        selected_flight = search_results.get("selected_flight")
        selected_train = search_results.get("selected_train")

        mode = ""
        if isinstance(plan, dict):
            trip = plan.get("trip") or {}
            if isinstance(trip, dict):
                mode = str(trip.get("transport_mode") or "").lower()

        fare = search_results.get("train_transport_cost")

        if mode == "train":
            finding = (
                "available"
                if selected_train and _is_positive_number(fare)
                else "fare_unconfirmed"
            )
        elif mode == "flight":
            finding = (
                "available"
                if selected_flight and flights
                else "unavailable"
            )
        else:
            finding = "not_verified_by_current_provider"

        return {
            "agent": self.name,
            "execution_status": "completed",
            "finding_status": finding,
            "summary": {
                "transport_mode": mode or None,
                "flight_options_found": len(flights),
                "train_options_found": len(trains),
                "selected_flight": bool(selected_flight),
                "selected_train": bool(selected_train),
                "train_fare": fare,
                "train_fare_confirmed": _is_positive_number(fare),
            },
        }


class AccommodationAgent(SpecialistAgent):
    name = "accommodation_agent"

    def review(self, search_results, plan):
        hotels = _items(search_results.get("hotels"))
        rates = _items(search_results.get("hotel_group_rates"))

        selected_hotel = (
            plan.get("selected_hotel")
            if isinstance(plan, dict)
            else None
        )

        if selected_hotel:
            finding = "recommended_hotel_available"
        elif rates:
            finding = "rates_available_no_selection"
        else:
            finding = "unavailable"

        return {
            "agent": self.name,
            "execution_status": "completed",
            "finding_status": finding,
            "summary": {
                "hotels_found": len(hotels),
                "group_rates_found": len(rates),
                "selected_hotel": (
                    selected_hotel.get("name")
                    if isinstance(selected_hotel, dict)
                    else None
                ),
            },
        }


class FoodAgent(SpecialistAgent):
    name = "food_agent"

    def review(self, search_results, plan):
        restaurants = _items(search_results.get("restaurants"))

        food_totals = {}
        if isinstance(plan, dict):
            food_totals = plan.get("food_scenario_totals") or {}

        finding = (
            "estimates_available"
            if food_totals
            else "estimates_unavailable"
        )

        return {
            "agent": self.name,
            "execution_status": "completed",
            "finding_status": finding,
            "summary": {
                "restaurants_found": len(restaurants),
                "food_scenarios_calculated": len(food_totals),
                "food_validation_error": (
                    plan.get("food_validation_error")
                    if isinstance(plan, dict)
                    else None
                ),
            },
        }


class PlacesAgent(SpecialistAgent):
    name = "places_agent"

    def review(self, search_results, plan):
        attractions = _items(search_results.get("attractions"))
        accommodations = _items(search_results.get("accommodations"))

        finding = (
            "attractions_available"
            if attractions
            else "attractions_unavailable"
        )

        return {
            "agent": self.name,
            "execution_status": "completed",
            "finding_status": finding,
            "summary": {
                "attractions_found": len(attractions),
                "destination_stays_found": len(accommodations),
            },
        }


class LocalTransportAgent(SpecialistAgent):
    name = "local_transport_agent"

    def review(self, search_results, plan):
        transport = (
            plan.get("transport", {})
            if isinstance(plan, dict)
            else {}
        )

        road_transfer = transport.get("road_transfer_cost")
        train_transfer = transport.get("train_road_transfer_cost")

        has_transfer_cost = (
            _is_positive_number(road_transfer)
            or _is_positive_number(train_transfer)
        )

        return {
            "agent": self.name,
            "execution_status": "completed",
            "finding_status": (
                "cost_available"
                if has_transfer_cost
                else "cost_not_reported"
            ),
            "summary": {
                "road_transfer_cost": road_transfer,
                "train_road_transfer_cost": train_transfer,
            },
        }


class BudgetAgent(SpecialistAgent):
    name = "budget_agent"

    def review(self, search_results, plan):
        plan = plan if isinstance(plan, dict) else {}

        provisional = bool(plan.get("provisional"))
        estimate_available = bool(
            plan.get("full_trip_estimate_available")
        )
        total_confirmed = bool(
            plan.get("full_trip_total_confirmed")
        )

        if provisional:
            finding = "provisional_missing_transport_fare"
        elif estimate_available:
            finding = "estimate_available_not_confirmed"
        else:
            finding = "complete_estimate_unavailable"

        return {
            "agent": self.name,
            "execution_status": "completed",
            "finding_status": finding,
            "summary": {
                "status": plan.get("status"),
                "provisional": provisional,
                "full_trip_estimate_available": estimate_available,
                "full_trip_total_confirmed": total_confirmed,
                "budget_error": plan.get("budget_error"),
                "food_validation_error": plan.get(
                    "food_validation_error"
                ),
            },
        }
