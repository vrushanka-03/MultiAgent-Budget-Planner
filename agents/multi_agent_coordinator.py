"""Central TripForge coordinator around the existing planning workflow.

The existing trip_engine owns provider calls and invokes agents.orchestrator
for budget aggregation. This coordinator then asks read-only specialist agents
to review each domain's returned data and exposes an execution trace.
"""
from typing import Callable
from agents.specialist_agents import (
    TransportAgent, AccommodationAgent, FoodAgent, PlacesAgent,
    LocalTransportAgent, BudgetAgent,
)

SPECIALISTS = (
    TransportAgent(), AccommodationAgent(), FoodAgent(), PlacesAgent(),
    LocalTransportAgent(), BudgetAgent(),
)


def coordinate_trip(run_trip: Callable, trip_input: dict) -> dict:
    """Run the unchanged engine, then collect specialist-agent reviews."""
    engine_result = run_trip(trip_input)
    if not isinstance(engine_result, dict):
        raise TypeError("Trip engine returned an invalid result.")
    search_results = engine_result.get("search_results") or {}
    plan = engine_result.get("plan")
    reviews = [agent.review(search_results, plan) for agent in SPECIALISTS]
    engine_result["agent_workflow"] = {
        "coordinator": "TripForge Multi-Agent Coordinator",
        "orchestrator": "agents.orchestrator.run_orchestrator (inside existing trip engine)",
        "execution_mode": "existing provider workflow + specialist result review",
        "agents": reviews,
    }
    return engine_result
