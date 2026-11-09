
import math


def validate_food_totals(result, non_food_total):
    """Validate food totals before calculating the full-trip estimate."""
    if not isinstance(result, dict):
        raise ValueError("Food result must be a dictionary.")

    low_food = float(result["group_total_low"])
    high_food = float(result["group_total_high"])
    non_food_total = float(non_food_total)

    if (
        not math.isfinite(low_food)
        or not math.isfinite(high_food)
        or not math.isfinite(non_food_total)
        or low_food < 0
        or high_food < low_food
        or non_food_total < 0
    ):
        raise ValueError("Invalid food or non-food totals.")

    low_total = non_food_total + low_food
    high_total = non_food_total + high_food

    if not math.isfinite(low_total) or not math.isfinite(high_total):
        raise ValueError("Full-trip total is not finite.")

    return low_total, high_total
