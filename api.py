
"""TripForge HTTP API. Runs the existing multi-module planning workflow."""
import json
import os
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse

from trip_engine import run_trip
from agents.multi_agent_coordinator import coordinate_trip


app = FastAPI(
    title="TripForge API",
    description="External API for the existing TripForge travel-planning orchestrator.",
    version="1.0.0",
)

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")

origins = [
    item.strip() for item in os.getenv(
        "TRIPFORGE_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",") if item.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=16)


class TripRequest(BaseModel):
    source: str = Field(min_length=2, max_length=120)
    destination: str = Field(min_length=2, max_length=120)
    days: int = Field(ge=1, le=60)
    budget: float = Field(gt=0, allow_inf_nan=False)
    transport_mode: Literal["flight", "train", "bus", "car"]
    travellers: int = Field(ge=1, le=30)
    start_date: date

    @field_validator("source", "destination")
    @classmethod
    def strip_location(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Location cannot be blank.")
        return value


@app.get("/health")
async def health():
    return {"status": "ok", "service": "TripForge API"}


@app.post("/api/trips/plan")
async def plan_trip(request: TripRequest):
    payload = request.model_dump()
    payload["start_date"] = request.start_date.strftime("%Y-%m-%d")

    try:
        result = await run_in_threadpool(
            coordinate_trip, run_trip, payload
        )

        return jsonable_encoder({
            "success": True,
            "trip_request": result.get("trip_request"),
            "plan": result.get("plan"),
            "search_results": result.get("search_results", {}),
            "agent_workflow": result.get("agent_workflow", {}),
        })

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except Exception as exc:
        print(f"TripForge request failed: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Trip planning failed. Check the TripForge server log for details.",
        ) from exc


# ==========================================================
# GEMINI CHAT CONFIGURATION
# ==========================================================

TRIP_CHAT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "assistant_message": {"type": "string"},
        "action": {"type": "string", "enum": ["chat", "plan"]},
        "source": {"type": ["string", "null"]},
        "destination": {"type": ["string", "null"]},
        "days": {"type": ["integer", "null"]},
        "budget": {"type": ["number", "null"]},
        "transport_mode": {
            "type": ["string", "null"],
            "enum": ["flight", "train", "bus", "car", None],
        },
        "travellers": {"type": ["integer", "null"]},
        "start_date": {"type": ["string", "null"]},
    },
    "required": [
        "assistant_message",
        "action",
        "source",
        "destination",
        "days",
        "budget",
        "transport_mode",
        "travellers",
        "start_date",
    ],
}


TRIP_CHAT_INSTRUCTIONS = """You are TripForge, a careful AI travel-planning assistant.

Your job is to collect trip requirements conversationally and, only when the user explicitly asks you to plan/search/generate the trip, trigger the existing TripForge planning engine.

Return only a valid JSON object matching the supplied schema.

Use action='chat' for greetings, travel questions, incomplete requests, corrections, and any discussion that is not an explicit request to run a trip search.

Use action='plan' only when the user clearly asks to plan/search/generate the trip AND all required fields are known:
source, destination, days, budget in INR, transport_mode (flight/train/bus/car), travellers, start_date (YYYY-MM-DD).

If any field is missing or ambiguous, ask one concise question for the most important missing detail and keep action='chat'.

Never invent missing trip details, dates, fares, hotel prices, availability, or search results. Do not claim that a search has happened.

If the user gives a relative date (e.g. tomorrow), resolve it using the current India date supplied below.

If they give a date without a year, choose the next future occurrence.

Normalize transport to one allowed value.

If a user asks to change a field, preserve all other known fields from conversation history.

Budget is the total group budget in Indian rupees.

Keep assistant_message concise, friendly, and clear.

Never expose API keys or internal implementation details.

Every response must contain all schema fields. Use null for unknown trip fields.

Required JSON schema:
{schema}

Current date in India: {today}.
"""


def _extract_gemini_response_text(payload: dict) -> str:
    """Extract generated text from a Gemini generateContent response."""
    candidates = payload.get("candidates", [])

    if not candidates:
        prompt_feedback = payload.get("promptFeedback", {})
        raise ValueError(
            f"Gemini returned no response candidates. {prompt_feedback}"
        )

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])

    chunks = [
        part.get("text", "")
        for part in parts
        if isinstance(part, dict) and part.get("text")
    ]

    if not chunks:
        raise ValueError("Gemini returned no response text.")

    return "".join(chunks)


@app.post("/api/chat")
async def tripforge_chat(request: ChatRequest):

    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Gemini is not configured. Add GEMINI_API_KEY to your .env file and restart the API.",
        )

    model = (
        os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
        or "gemini-3.8-flash"
    )
    print("DEBUG - Gemini model being used:", model)

    # Keep recent conversation context within predictable limits.
    history = [
        {
            "role": "model" if item.role == "assistant" else "user",
            "parts": [{"text": item.content}],
        }
        for item in request.messages[-12:]
    ]

    today = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).date().isoformat()

    instructions = TRIP_CHAT_INSTRUCTIONS.format(
        today=today,
        schema=json.dumps(TRIP_CHAT_SCHEMA),
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent"
    )

    try:
        response = requests.post(
            url,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "systemInstruction": {
                    "parts": [{"text": instructions}]
                },
                "contents": history,
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 1000,
                },
            },
            timeout=120,
        )

        if not response.ok:
            print(
                f"Gemini API error {response.status_code}: "
                f"{response.text[:1200]}"
            )

            try:
                error_data = response.json()
                error_message = error_data.get(
                    "error", {}
                ).get("message", "Unknown Gemini API error")
                error_status = error_data.get(
                    "error", {}
                ).get("status", "unknown")
            except ValueError:
                error_message = "Could not read Gemini error response"
                error_status = "unknown"

            raise HTTPException(
                status_code=502,
                detail=(
                    f"Gemini error ({response.status_code}, "
                    f"{error_status}): {error_message}"
                ),
            )

        gemini_payload = response.json()

        parsed = json.loads(
            _extract_gemini_response_text(gemini_payload)
        )

        if not isinstance(parsed, dict):
            raise ValueError("Gemini response was not a JSON object.")

        required_fields = [
            "assistant_message",
            "action",
            "source",
            "destination",
            "days",
            "budget",
            "transport_mode",
            "travellers",
            "start_date",
        ]

        missing_fields = [
            field for field in required_fields
            if field not in parsed
        ]

        if missing_fields:
            raise ValueError(
                f"Gemini response is missing fields: {missing_fields}"
            )

        if not isinstance(parsed["assistant_message"], str):
            raise ValueError("Gemini returned an invalid assistant message.")

        if parsed["action"] not in ("chat", "plan"):
            raise ValueError("Gemini returned an invalid action.")

    except HTTPException:
        raise

    except requests.Timeout as exc:
        print("Gemini request timed out.")
        raise HTTPException(
            status_code=504,
            detail="Gemini took too long to respond. Please try again.",
        ) from exc

    except requests.RequestException as exc:
        print(f"Gemini connection error: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=502,
            detail="Could not reach Gemini. Please check your internet connection and try again.",
        ) from exc

    except (ValueError, KeyError, TypeError) as exc:
        print(f"Gemini response parsing error: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=502,
            detail="Gemini returned an unreadable response. Please try again.",
        ) from exc

    trip_fields = {
        key: parsed.get(key)
        for key in (
            "source",
            "destination",
            "days",
            "budget",
            "transport_mode",
            "travellers",
            "start_date",
        )
    }

    if parsed["action"] != "plan":
        return {
            "success": True,
            "assistant_message": parsed["assistant_message"],
            "trip_fields": trip_fields,
            "plan_result": None,
        }

    # Validate trip details before invoking the existing planner.
    try:
        validated = TripRequest(**trip_fields)

    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Trip details need correction: {exc}",
        ) from exc

    payload = validated.model_dump()
    payload["start_date"] = validated.start_date.strftime("%Y-%m-%d")

    try:
        result = await run_in_threadpool(
            coordinate_trip, run_trip, payload
        )

        encoded = jsonable_encoder({
            "success": True,
            "trip_request": result.get("trip_request"),
            "plan": result.get("plan"),
            "search_results": result.get("search_results", {}),
            "agent_workflow": result.get("agent_workflow", {}),
        })

        return {
            "success": True,
            "assistant_message": parsed["assistant_message"],
            "trip_fields": trip_fields,
            "plan_result": encoded,
            "agent_workflow": result.get("agent_workflow", {}),
        }

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except Exception as exc:
        print(
            f"TripForge chat planning failed: "
            f"{type(exc).__name__}: {exc}"
        )

        raise HTTPException(
            status_code=500,
            detail="Trip planning failed. Check the TripForge server log.",
        ) from exc
