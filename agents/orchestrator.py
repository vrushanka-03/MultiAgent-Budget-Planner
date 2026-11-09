"""
TripForge agent orchestrator.

Coordinates already-fetched destination, transport, accommodation, and food
results. This module does not call external APIs. Helpers are injected by
main_page.py so API usage stays in one place.
"""
import math
from typing import Any, Callable


def _normalise_transport_mode(mode: Any) -> str:
    value = str(mode or "").strip().lower()
    allowed = {"flight", "train", "bus", "car"}
    if value not in allowed:
        raise ValueError("Transport mode must be flight, train, bus, or car.")
    return value


def _validate_trip_request(trip_request: dict) -> dict:
    if not isinstance(trip_request, dict):
        raise ValueError("Trip request must be a dictionary.")

    source = str(trip_request.get("source") or "").strip()
    destination = str(trip_request.get("destination") or "").strip()
    if not source or not destination:
        raise ValueError("Source and destination are required.")

    try:
        days = int(trip_request.get("days"))
        travellers = int(trip_request.get("travellers"))
        budget = float(trip_request.get("budget"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Days, travellers, and budget must be valid numbers.") from exc

    if days < 1:
        raise ValueError("Days must be at least 1.")
    if travellers < 1:
        raise ValueError("Travellers must be at least 1.")
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError("Budget must be finite and greater than zero.")

    return {
        **trip_request,
        "source": source,
        "destination": destination,
        "days": days,
        "travellers": travellers,
        "budget": budget,
        "transport_mode": _normalise_transport_mode(
            trip_request.get("transport_mode")
        ),
    }


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _get_transport_cost(
    request: dict,
    results: dict,
    calculate_transport_cost: Callable,
):
    mode = request["transport_mode"]

    # No verified bus/car fare provider is currently wired into this planner.
    if mode in {"bus", "car"}:
        return None

    if mode == "flight" and not _as_list(results.get("flight_options")):
        return None
    if mode == "train" and results.get("train_transport_cost") is None:
        return None

    try:
        cost = calculate_transport_cost(
            transport_mode=mode,
            travellers=request["travellers"],
            flight_options=_as_list(results.get("flight_options")),
            train_transport_cost=results.get("train_transport_cost"),
            road_transfer_cost=results.get("road_transfer_cost", 0.0),
            train_road_transfer_cost=results.get("train_road_transfer_cost", 0.0),
        )
        cost = float(cost)
        if not math.isfinite(cost) or cost <= 0:
            return None
        return cost
    except Exception as exc:
        if mode == "train":
            print(f"Train transport-cost calculation failed: {exc}")
        return None


def _valid_nonnegative_number(value: Any) -> bool:
    try:
        number = float(value)
        return math.isfinite(number) and number >= 0
    except (TypeError, ValueError, OverflowError):
        return False


def _hotel_price(hotel: Any):
    if not isinstance(hotel, dict):
        return None
    # Normalized records contain both keys with the same full-stay group amount.
    for key in ("total_price", "price"):
        value = hotel.get(key)
        try:
            amount = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(amount) and amount > 0:
            return amount
    return None


def run_orchestrator(
    trip_request: dict,
    existing_results: dict,
    *,
    calculate_transport_cost: Callable,
    normalise_group_hotel_rates: Callable,
    calculate_trip_budget: Callable,
) -> dict:
    """Build a structured plan from user inputs and existing API results."""
    request = _validate_trip_request(trip_request)
    results = _as_dict(existing_results)

    destination_data = {
        "latitude": results.get("latitude"),
        "longitude": results.get("longitude"),
        "attractions": _as_list(results.get("attractions")),
        "accommodations": _as_list(results.get("accommodations")),
        "restaurants": _as_list(results.get("restaurants")),
    }

    transport_cost = _get_transport_cost(
        request, results, calculate_transport_cost
    )
    transport_over_budget = (
        transport_cost is not None and transport_cost > request["budget"]
    )
    transport_budget_check = {
        "exceeds_budget": transport_over_budget,
        "total_budget": request["budget"],
        "transport_cost": transport_cost,
        "minimum_shortfall": (
            max(0.0, transport_cost - request["budget"])
            if transport_cost is not None else None
        ),
        "travellers": request["travellers"],
    }

    transport_data = {
        "mode": request["transport_mode"],
        "group_cost": transport_cost,
        "fare_confirmed": transport_cost is not None,
        "flight_options": _as_list(results.get("flight_options")),
        "train_transport_cost": results.get("train_transport_cost"),
        "road_transfer_cost": results.get("road_transfer_cost", 0.0),
        "train_road_transfer_cost": results.get("train_road_transfer_cost", 0.0),
        "train_fare_per_person": results.get("train_fare_per_person"),
        "travellers": request["travellers"]
    }

    normalization_error = None
    try:
        grouped_rates = normalise_group_hotel_rates(
            _as_list(results.get("hotel_prices")),
            _as_list(results.get("hotels")),
        )
        if not isinstance(grouped_rates, list):
            grouped_rates = []
            normalization_error = "Hotel-rate normalizer returned an invalid result."
    except Exception as exc:
        grouped_rates = []
        normalization_error = f"Hotel-rate normalization failed: {exc}"

    stay_data = {
        "hotels": _as_list(results.get("hotels")),
        "group_rates": grouped_rates,
        "check_in": results.get("check_in"),
        "check_out": results.get("check_out"),
    }

    budget_result = None
    budget_error = None
    provisional = False

    if transport_cost is not None:
        try:
            budget_result = calculate_trip_budget(
                total_budget=request["budget"],
                travellers=request["travellers"],
                days=request["days"],
                transport_cost=transport_cost,
                hotel_prices=grouped_rates,
            )
            if not isinstance(budget_result, dict):
                raise TypeError("Budget calculator did not return a dictionary.")
        except Exception as exc:
            budget_result = None
            budget_error = f"Budget calculation failed: {exc}"
    elif request["transport_mode"] == "train":
        # Internal placeholder used only for provisional allocation.
        try:
            budget_result = calculate_trip_budget(
                total_budget=request["budget"],
                travellers=request["travellers"],
                days=request["days"],
                transport_cost=0.0,
                hotel_prices=grouped_rates,
            )
            if not isinstance(budget_result, dict):
                raise TypeError("Budget calculator did not return a dictionary.")
        except Exception as exc:
            budget_result = None
            budget_error = f"Provisional budget calculation failed: {exc}"
        provisional = True
    else:
        budget_error = (
            "A verified transport fare is unavailable. "
            "A confirmed full-trip total cannot be calculated."
        )

    food_data = {
        "restaurants": _as_list(results.get("restaurants")),
        "food_budget_results": _as_dict(results.get("food_budget_results")),
    }

    if provisional:
        status = "provisional_train_fare_missing"
    elif transport_cost is None:
        status = "transport_fare_unavailable"
    elif budget_error:
        status = "budget_calculation_failed"
    elif isinstance(budget_result, dict):
        status = budget_result.get("status", "budget_calculated")
    else:
        status = "budget_unavailable"

    selected_hotel = None
    cheapest_available_hotel = None
    accommodation_budget = None
    affordable_group_rates = []
    if isinstance(budget_result, dict):
        recommended = budget_result.get("recommended_hotel")
        cheapest_available_hotel = budget_result.get("cheapest_hotel")
        accommodation_budget = budget_result.get("accommodation_budget")
        if isinstance(recommended, dict):
            selected_hotel = recommended
        if _valid_nonnegative_number(accommodation_budget):
            accommodation_budget = float(accommodation_budget)

            affordable_group_rates = [
                hotel
                for hotel in grouped_rates
                if (
                    _hotel_price(hotel) is not None
                    and _hotel_price(hotel) <= accommodation_budget
                )
            ]
    stay_data["group_rates"] = affordable_group_rates
    stay_data["all_group_rates"] = grouped_rates
    stay_data["accommodation_budget"] = accommodation_budget
    stay_data["cheapest_available_hotel"] = cheapest_available_hotel
    stay_data["affordable_group_rates_count"] = len(affordable_group_rates)

    selected_hotel_price = _hotel_price(selected_hotel)
    budget_reference_hotel = (
        selected_hotel
        if selected_hotel is not None
        else cheapest_available_hotel
    )
    hotel_price_for_estimate = _hotel_price(budget_reference_hotel)

    required_expense_fields = ("transport", "local_travel", "attractions")
    valid_expense_fields = isinstance(budget_result, dict)
    if valid_expense_fields:
        for field in required_expense_fields:
            if field not in budget_result or not _valid_nonnegative_number(
                budget_result[field]
            ):
                valid_expense_fields = False
                break

    food_scenario_totals = {}
    food_validation_error = None
    food_results = food_data["food_budget_results"]

    if food_results:
        try:
            if not isinstance(budget_result, dict):
                raise ValueError("Base budget result is unavailable.")
            if hotel_price_for_estimate is None:
                raise ValueError(
                    "No valid full-stay group hotel price is available. "
                    "Food-inclusive trip totals cannot be calculated."
                )

            non_food_expenses = [
                float(budget_result["transport"]),
                float(budget_result["local_travel"]),
                float(budget_result["attractions"]),
                hotel_price_for_estimate,
            ]
            if any(
                not math.isfinite(value) or value < 0
                for value in non_food_expenses
            ):
                raise ValueError("One or more non-food expense values are invalid.")

            non_food_total = sum(non_food_expenses)
            if not math.isfinite(non_food_total):
                raise ValueError("Non-food total is invalid.")

            for scenario_name, food_result in food_results.items():
                if not isinstance(scenario_name, str) or not scenario_name.strip():
                    raise ValueError("Food scenario name is invalid.")
                if not isinstance(food_result, dict):
                    raise ValueError(f"Food scenario {scenario_name!r} is invalid.")

                low_food = float(food_result["group_total_low"])
                high_food = float(food_result["group_total_high"])
                if (
                    not math.isfinite(low_food)
                    or not math.isfinite(high_food)
                    or low_food < 0
                    or high_food < low_food
                ):
                    raise ValueError(f"Food totals are invalid for {scenario_name!r}.")

                low_total = non_food_total + low_food
                high_total = non_food_total + high_food
                remaining = request["budget"] - high_total

                if not math.isfinite(low_total) or not math.isfinite(high_total):
                    raise ValueError(f"Full-trip totals are invalid for {scenario_name!r}.")

                scenario_status = (
                    "within_budget"
                    if high_total <= request["budget"]
                    else "range_crosses_budget"
                    if low_total <= request["budget"]
                    else "over_budget"
                )
                food_scenario_totals[scenario_name] = {
                    "food_low": low_food,
                    "food_high": high_food,
                    "non_food_total": non_food_total,
                    "total_low": low_total,
                    "total_high": high_total,
                    "remaining_at_high": remaining,
                    "shortfall_at_high": max(0.0, -remaining),
                    "status": scenario_status,

                    "hotel_name": (
                        budget_reference_hotel.get("name")
                        if isinstance(budget_reference_hotel, dict)
                        else None
                    ),
                    "hotel_within_accommodation_budget": selected_hotel is not None,
                }
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            food_validation_error = str(exc)
            food_scenario_totals = {}
    else:
        food_validation_error = "Food budget scenarios are missing."

    # Food amounts produced by calculate_food_budget are planning estimates,
    # not verified restaurant expenditure. Therefore the complete trip amount
    # is an estimate, not a fully confirmed/verified total.
    verified_transport = transport_cost is not None and _valid_nonnegative_number(transport_cost)
    verified_hotel = hotel_price_for_estimate is not None
    full_trip_estimate_available = (
        verified_transport
        and not provisional
        and budget_error is None
        and valid_expense_fields
        and verified_hotel
        and bool(food_scenario_totals)
        and food_validation_error is None
    )

    full_trip_total_confirmed = False

    # Build one explicit final expense breakdown using the recommended
    # Moderate scenario (or the first available scenario as a safe fallback).
    # Food is added exactly once here; the baseline food allowance used by the
    # accommodation allocator is not added to this final estimate.
    final_budget = {
        "available": False,
        "over_budget": False,
        "budget": request["budget"],
        "components": {},
        "total_low": None,
        "total_high": None,
        "remaining_at_high": None,
        "shortfall_at_high": None,
        "scenario": None,
        "status": "unavailable",
        "warning": None,
    }

    preferred_scenario = "Moderate (recommended)"
    selected_scenario_name = (
        preferred_scenario
        if preferred_scenario in food_scenario_totals
        else next(iter(food_scenario_totals), None)
    )

    if selected_scenario_name is not None and isinstance(budget_result, dict):
        scenario = food_scenario_totals[selected_scenario_name]
        component_values = {
            "transport": budget_result.get("transport"),
            "accommodation": hotel_price_for_estimate,
            "local_transport": budget_result.get("local_travel"),
            "attractions": budget_result.get("attractions"),
            "food_low": scenario.get("food_low"),
            "food_high": scenario.get("food_high"),
        }
        component_values_valid = all(
            _valid_nonnegative_number(value)
            for value in component_values.values()
        )

        if component_values_valid:
            total_low = (
                float(component_values["transport"])
                + float(component_values["accommodation"])
                + float(component_values["local_transport"])
                + float(component_values["attractions"])
                + float(component_values["food_low"])
            )
            total_high = (
                float(component_values["transport"])
                + float(component_values["accommodation"])
                + float(component_values["local_transport"])
                + float(component_values["attractions"])
                + float(component_values["food_high"])
            )
            remaining_at_high = request["budget"] - total_high
            shortfall_at_high = max(0.0, -remaining_at_high)
            over_budget = total_high > request["budget"]
            range_crosses_budget = (
                total_low <= request["budget"] < total_high
            )

            final_budget = {
                "available": True,
                "over_budget": over_budget,
                "budget": request["budget"],
                "components": {
                    "transport": float(component_values["transport"]),
                    "accommodation": float(component_values["accommodation"]),
                    "food": {
                        "low": float(component_values["food_low"]),
                        "high": float(component_values["food_high"]),
                    },
                    "local_transport": float(component_values["local_transport"]),
                    "attractions": float(component_values["attractions"]),
                },
                "total_low": total_low,
                "total_high": total_high,
                "remaining_at_high": remaining_at_high,
                "shortfall_at_high": shortfall_at_high,
                "scenario": selected_scenario_name,
                "status": (
                    "over_budget"
                    if over_budget and not range_crosses_budget
                    else "range_crosses_budget"
                    if range_crosses_budget
                    else "within_budget"
                ),
                "warning": (
                    "Trip planned won't fit into the given budget. Please change the budget."
                    if over_budget else None
                ),
                "hotel_name": (
                    budget_reference_hotel.get("name")
                    if isinstance(budget_reference_hotel, dict)
                    else None
                ),
                "hotel_within_accommodation_budget": selected_hotel is not None,
                "is_estimate": True,
            }

    budget_warning = final_budget.get("warning")
    if transport_over_budget:
        budget_warning = (
            "Trip planned won't fit into the given budget. Please change the budget."
        )
        final_budget["over_budget"] = True
        final_budget["status"] = "transport_over_budget"
        final_budget["warning"] = budget_warning
        if final_budget.get("shortfall_at_high") is None:
            final_budget["shortfall_at_high"] = max(
                0.0, transport_cost - request["budget"]
            )

    if provisional:
        status = "provisional_train_fare_missing"
    elif transport_cost is None:
        status = "transport_fare_unavailable"
    elif budget_error:
        status = "budget_calculation_failed"
    elif not verified_hotel:
        status = "hotel_price_unavailable"
    elif food_validation_error:
        status = "food_budget_unavailable"
    elif full_trip_estimate_available:
        status = "trip_estimate_available"
    else:
        status = "budget_unavailable"

    if transport_over_budget:
        status = "transport_over_budget"
    elif final_budget.get("available") and final_budget.get("over_budget"):
        status = "trip_estimate_over_budget"

    return {
        "trip": {
            "source": request["source"],
            "destination": request["destination"],
            "days": request["days"],
            "travellers": request["travellers"],
            "budget": request["budget"],
            "transport_mode": request["transport_mode"],
            "start_date": request.get("start_date"),
        },
        "destination": destination_data,
        "transport": transport_data,
        "transport_budget_check": transport_budget_check,
        "stay": stay_data,
        "food": food_data,
        "budget": budget_result,
        "status": status,
        "provisional": provisional,
        "normalization_error": normalization_error,
        "budget_error": budget_error,
        "food_validation_error": food_validation_error,
        "food_scenario_totals": food_scenario_totals,
        "final_budget": final_budget,
        "budget_warning": budget_warning,
        "selected_hotel": selected_hotel,
        "budget_reference_hotel": budget_reference_hotel,
        "hotel_within_accommodation_budget": selected_hotel is not None,
        "full_trip_estimate_available": full_trip_estimate_available,
        "full_trip_total_confirmed": full_trip_total_confirmed,
    }


def print_orchestrator_summary(plan: dict) -> None:
    """Display a concise summary of the orchestrator's result."""
    if not isinstance(plan, dict):
        print("TripForge orchestrator returned an invalid plan.")
        return

    trip = _as_dict(plan.get("trip"))
    transport = _as_dict(plan.get("transport"))
    budget = _as_dict(plan.get("budget"))

    print("\n========== TRIPFORGE ORCHESTRATOR ==========")
    print(f"Route: {trip.get('source', 'Unknown')} -> {trip.get('destination', 'Unknown')}")
    print(f"Duration: {trip.get('days', 'N/A')} day(s)")
    print(f"Travellers: {trip.get('travellers', 'N/A')}")
    print(f"Transport: {trip.get('transport_mode', 'N/A')}")
    try:
        print(f"Budget: ₹{float(trip.get('budget')):,.2f}")
    except (TypeError, ValueError):
        print("Budget: Not available")

    if plan.get("provisional"):
        print("WARNING: This is a provisional allocation; the train fare is unconfirmed.")

    if plan.get("full_trip_estimate_available"):
        print("Food-inclusive trip estimate: AVAILABLE (food is an estimate, not a verified bill).")
    else:
        print("Food-inclusive trip estimate: NOT AVAILABLE")

    if plan.get("normalization_error"):
        print("Hotel-rate warning:", plan["normalization_error"])
    if plan.get("budget_error"):
        print("Budget note:", plan["budget_error"])
    if plan.get("food_validation_error"):
        print("Food validation:", plan["food_validation_error"])

    if budget:
        print("Budget status:", budget.get("status", plan.get("status")))
        hotel = plan.get("selected_hotel")
        if isinstance(hotel, dict):
            print("Selected hotel:", hotel.get("name", "Unknown"))
            price = _hotel_price(hotel)
            if price is not None:
                print(f"Full-stay group price: ₹{price:,.2f}")
        else:
            print("No usable hotel price was returned.")

    print("============================================")
