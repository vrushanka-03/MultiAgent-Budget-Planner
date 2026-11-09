# TripForge – Multi-Agent AI Travel Planner

**Plan smarter. Travel better. Stay within your budget.**

TripForge is a multi-agent AI travel planning application that helps users generate budget-aware travel plans using real-world travel data and multiple API integrations.

Instead of simply suggesting destinations, TripForge collects the user's travel requirements, retrieves relevant travel information, coordinates specialist agents, and organizes the available information into a structured trip budget.

## Live Application

- **Live Website:** https://multi-agent-budget-planner.vercel.app/
- **Backend API:** https://multiagent-budget-planner.onrender.com/
- **API Documentation:** https://multiagent-budget-planner.onrender.com/docs
- **GitHub Repository:** https://github.com/vrushanka-03/MultiAgent-Budget-Planner

## Key Features

- **Conversational AI Interface:** Uses Gemini to understand natural-language travel requests and collect missing trip details through follow-up questions.
- **Multi-Agent Coordination:** Coordinates specialist agents responsible for transport, accommodation, food, places, local transport, and budget review.
- **Budget-Aware Planning:** Organizes the available trip information around the user's total group budget.
- **Flight Search:** Retrieves flight options through SerpApi's Google Flights search.
- **Train Search:** Integrates railway information through the IRCTC RapidAPI service.
- **Hotel Discovery and Pricing:** Retrieves hotel listings and group accommodation rates through LiteAPI.
- **Attraction Discovery:** Uses Geoapify to discover destination attractions.
- **Restaurant Discovery:** Finds nearby restaurants and displays source-provided information where available.
- **Group Cost Calculation:** Accounts for the number of travellers when calculating relevant transport and accommodation costs.
- **Transparent Budget Estimates:** Separates available provider prices from planning estimates and avoids treating missing fares as confirmed costs.

## How TripForge Works

1. **Understand the request:** Gemini processes the conversation and identifies the trip requirements.
2. **Collect missing details:** TripForge asks follow-up questions when essential information is missing.
3. **Validate the trip:** The backend validates the source, destination, duration, budget, transport mode, traveller count, and start date.
4. **Retrieve travel information:** The existing trip engine fetches relevant transportation, accommodation, attraction, and restaurant information.
5. **Coordinate the workflow:** The multi-agent coordinator runs the existing planning engine and sends its results to specialist review agents.
6. **Calculate the budget:** The existing orchestrator combines available costs and budget estimates.
7. **Generate the result:** The frontend displays the resulting trip plan and budget breakdown.

## Multi-Agent Architecture

TripForge uses a central coordinator and six specialist review agents.

| Agent | Responsibility |
|---|---|
| Transport Agent | Reviews flight and train search results and transport availability. |
| Accommodation Agent | Reviews hotel listings, group rates, and selected accommodation. |
| Food Agent | Reviews restaurant discovery and meal-budget calculations. |
| Places Agent | Reviews attractions and destination accommodation discoveries. |
| Local Transport Agent | Reviews available road-transfer cost information. |
| Budget Agent | Reviews the overall budget, provisional status, and calculation warnings. |

The existing trip engine performs provider searches and budget calculations. Specialist agents review the resulting data rather than independently repeating external API calls.

## Technology Stack

**Frontend**
- React
- Vite
- JavaScript
- CSS

**Backend**
- Python
- FastAPI
- Uvicorn
- Pydantic

**AI**
- Google Gemini API
- Gemini 3.1 Flash-Lite (configured deployment model)

**External Data Integrations**
- SerpApi – Flight search
- IRCTC RapidAPI – Railway information
- LiteAPI – Hotel discovery and rates
- Geoapify – Places, attractions, and restaurant discovery
- OpenStreetMap Nominatim – Geocoding
- OpenStreetMap Overpass – Geographic and nearby-place data

**Deployment**
- Vercel – Frontend hosting
- Render – Backend hosting
- GitHub – Version control

## Project Structure

```text
MultiAgent-Budget-Planner/
│
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py
│   ├── multi_agent_coordinator.py
│   ├── specialist_agents.py
│   └── food_budget_validation.py
│
├── data/
│   ├── Places.py
│   ├── Transport.py
│   ├── Food.py
│   └── LocalTransport.py
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── styles.css
│   ├── package.json
│   └── index.html
│
├── api.py
├── trip_engine.py
├── main_page.py
├── requirements-web.txt
├── README.md
└── .gitignore
```

## Run Locally

### Prerequisites

- Python 3.10 or later
- Node.js and npm
- Git
- Required API credentials

### 1. Clone the repository

```bash
git clone https://github.com/vrushanka-03/MultiAgent-Budget-Planner.git

cd MultiAgent-Budget-Planner
```

### 2. Set up the backend

Create and activate a virtual environment:

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

Install backend dependencies:

```bash
pip install -r requirements-web.txt
```

### 3. Configure environment variables

Create a private `.env` file in the project root:

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite

GEOAPIFY_API_KEY=your_geoapify_api_key
LITEAPI_SANDBOX_KEY=your_liteapi_key
SERPAPI_API_KEY=your_serpapi_key
IRCTC_PNR_RAPIDAPI_KEY=your_rapidapi_key

TRIPFORGE_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Use your own provider credentials. Never upload `.env` or expose API keys in frontend code or GitHub.

### 4. Start the backend

From the project root:

```bash
uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

Backend documentation:

```text
http://127.0.0.1:8000/docs
```

### 5. Configure the frontend

Open a second terminal:

```bash
cd frontend
npm install
```

Create a frontend environment file named `.env` inside the `frontend` directory:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### 6. Start the frontend

```bash
npm run dev
```

Open the local Vite URL shown in the terminal, normally:

```text
http://localhost:5173
```

## Backend API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Checks backend health. |
| POST | `/api/chat` | Handles conversational trip requests. |
| POST | `/api/trips/plan` | Accepts structured trip-planning requests. |
| GET | `/docs` | Opens interactive FastAPI documentation. |

## Deployment Architecture

```text
                 USER
                   |
                   v
          REACT + VITE FRONTEND
                 VERCEL
                   |
                   v
             FASTAPI BACKEND
                 RENDER
                   |
             GEMINI API
                   |
                   v
          TRIP PLANNING ENGINE
                   |
          MULTI-AGENT COORDINATOR
                   |
       +-----------+-----------+
       |           |           |
    Transport  Accommodation  Food
       |           |           |
     Places   Local Transport Budget
       |           |           |
       +-----------+-----------+
                   |
                   v
          FINAL TRIP PLAN
```

## Screenshots and Demo

Screenshots and a demonstration video will be added here to showcase:

- TripForge home interface.
- Conversational trip requirement collection.
- Destination and travel options.
- Hotel discovery and accommodation rates.
- Budget allocation and expense breakdown.
- Final generated trip plan.

## Important Notes

- Travel prices and availability depend on external providers and may change.
- API quotas and rate limits can affect search results.
- Some meal, local transport, and attraction costs are planning estimates rather than verified transaction prices.
- A provisional plan may be returned when a required fare or price cannot be confirmed.
- The Render free instance may take additional time to respond after inactivity.

## Future Improvements

- Improve resilience with retry handling and fallback AI models.
- Expand transport-provider integrations.
- Improve trip recommendation and budget optimization.
- Add more detailed itinerary customization.
- Enhance the user interface and trip comparison experience.

---

**TripForge – Multi-Agent Work Mode ON**

Built with Python, React, FastAPI, Gemini, and external travel APIs.
