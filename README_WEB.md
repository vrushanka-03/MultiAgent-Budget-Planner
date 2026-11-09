# TripForge web app (first integration milestone)

This version adds a browser interface and FastAPI backend around the existing TripForge workflow. The existing data modules and `agents/orchestrator.py` are retained. Both the terminal entry point and HTTP API call `trip_engine.run_trip()`.

## Important architecture note

In the supplied project archive, the orchestrator coordinates results after the searches, while the provider searches are executed in the main planning workflow and imported data modules. The `agents/` directory currently contains `orchestrator.py` and `food_budget_validation.py`; it does not contain separate autonomous flight/train/hotel/food agent classes. This integration does not invent those classes or replace the existing workflow.

The OpenAI conversational layer now handles free-form trip requests and missing-detail follow-ups. It does not replace the existing provider modules or orchestrator; those remain responsible for live travel searches and budget coordination.

## OpenAI conversational layer

The browser chat is powered by the OpenAI Responses API. The backend uses Structured Outputs to extract trip details into a validated schema, asks follow-up questions when information is missing, and only calls the existing TripForge engine when the user explicitly asks to plan/search and all required fields are present. The default model is `gpt-4o-mini`; override it with `OPENAI_MODEL` if your OpenAI project has access to another compatible model.

Add these values to your private local `.env` file:

```text
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini
```

Do not put the OpenAI key in any `VITE_` frontend variable. It must remain on the backend. OpenAI API usage is billed separately according to your API account.

## 1. Protect credentials

The uploaded archive included a `.env` file. It is deliberately excluded from this generated package. Keep your original local `.env` file private in the project root; do not upload it to GitHub or include it in future ZIPs. If any credentials were shared beyond this private workspace, rotate them with their providers.

## 2. Install backend dependencies

From the `TripForge` project root, activate your existing virtual environment and run:

```bash
pip install -r requirements-web.txt
```

Keep your existing `.env` in this folder.

## 3. Start the API

```bash
uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

Health check: http://127.0.0.1:8000/health
API docs: http://127.0.0.1:8000/docs

## 4. Start the frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal (normally http://localhost:5173).

If the API is hosted somewhere other than localhost, create `frontend/.env` with:

```text
VITE_API_BASE_URL=https://your-api-domain.example
```

Also set `TRIPFORGE_CORS_ORIGINS` on the backend to the exact frontend origin.

## 5. Terminal mode

The original terminal workflow remains available:

```bash
python main_page.py
```

## Current scope and next work

- This is the first local web integration, not yet a public deployment.
- Provider calls are synchronous; the API runs the planner in a worker thread.
- The frontend sends conversational history to `/api/chat`; the backend asks OpenAI to extract trip details and only runs the planner after an explicit planning request with all required fields.
- The direct `/api/trips/plan` endpoint remains available for structured clients.
- Test with a harmless greeting first (OpenAI call only), then complete a trip request only when you are ready to use your travel-provider quotas.
- Deploy backend and frontend separately, setting API keys only as backend environment secrets.


## Multi-agent coordination layer

The API now routes trip execution through `agents/multi_agent_coordinator.py`. The coordinator calls the existing `trip_engine.run_trip()` workflow (which continues to invoke the existing `agents/orchestrator.py`), then dispatches the returned structured data to specialist review agents: Transport, Accommodation, Food, Places, Local Transport, and Budget. Their summaries are returned as `agent_workflow` in the API response. This is intentionally additive: the specialist review agents do not independently call providers or duplicate the existing search logic. Provider calls and all train/flight/accommodation calculations remain in the existing engine/data modules.

The OpenAI conversational layer remains in `api.py`: it gathers details, validates them, and only starts planning after an explicit request with all required fields. The existing terminal workflow remains available.
