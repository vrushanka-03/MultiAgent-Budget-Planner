
import React, { useMemo, useState } from 'react';
import {
  Plane,
  TrainFront,
  Send,
  Sparkles,
  Users,
  ArrowRight,
  Hotel,
  Utensils,
  Compass,
  Wallet,
  LoaderCircle
} from 'lucide-react';

const API_BASE =
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

const money = (value) => {
  const amount = Number(value);

  return value !== null &&
    value !== undefined &&
    value !== '' &&
    Number.isFinite(amount)
    ? `₹${amount.toLocaleString('en-IN', {
        maximumFractionDigits: 2
      })}`
    : 'Not available';
};

function Result({ data }) {
  if (!data?.plan) {
    return (
      <div className="notice">
        Trip search finished, but the orchestrator did not return a complete
        plan. Check the server log.
      </div>
    );
  }

  const plan = data.plan;
  const results = data.search_results || {};

  const hotels =
    plan.stay?.group_rates ||
    results.hotel_group_rates ||
    [];

  const selectedHotel = plan.selected_hotel || null;

  const provisional = Boolean(plan.provisional);

  const estimateAvailable = Boolean(
    plan.full_trip_estimate_available
  );

  const scenarios = Object.entries(
    plan.food_scenario_totals || {}
  );

  const foodResults =
    plan.food?.food_budget_results ||
    results.food_budget_results ||
    {};

  const attractions = Array.isArray(plan.destination?.attractions)
    ? plan.destination.attractions
    : Array.isArray(results.attractions)
      ? results.attractions
      : [];

  const finalBudget = plan.final_budget || {};
  const transportBudgetCheck = plan.transport_budget_check || {};
  const overBudget =
    Boolean(transportBudgetCheck.exceeds_budget) ||
    Boolean(finalBudget.over_budget) ||
    Boolean(plan.budget_warning);

  const transport = plan.transport || {};

  const trainTransfer = results.train_road_transfer_cost;

  const flightOptions =
    results.flight_options ||
    transport.flight_options ||
    [];

  const selectedFlight = results.selected_flight;

  const agentReviews = data.agent_workflow?.agents || [];

  return (
    <div className="results">

      {/* Trip heading */}
      <div className="result-head">
        <div>
          <span className="eyebrow">YOUR TRIP PLAN</span>

          <h2>
            {plan.trip?.source}
            <ArrowRight size={18} />
            {plan.trip?.destination}
          </h2>

          <p>
            {plan.trip?.days} days ·{' '}
            {plan.trip?.travellers} travellers ·{' '}
            {plan.trip?.transport_mode}
          </p>
        </div>

        <span
          className={`status ${
            estimateAvailable ? 'good' : 'warn'
          }`}
        >
          {String(plan.status || 'Plan generated')
            .replaceAll('_', ' ')}
        </span>
      </div>

      {/* Important warnings */}
      {provisional && (
        <div className="notice">
          <strong>Provisional trip plan:</strong> The train fare
          has not been confirmed. The provisional budget calculation
          uses ₹0 for the missing train fare. Actual trip expenditure
          will be higher if a train fare is payable.
        </div>
      )}

      {overBudget && (
        <div className="notice">
          <strong>Trip planned won't fit into the given budget. Please change the budget.</strong>
          <p>
            {transportBudgetCheck.exceeds_budget
              ? `Transport alone costs ${money(transportBudgetCheck.transport_cost)} against a total budget of ${money(transportBudgetCheck.total_budget)}. Minimum shortfall: ${money(transportBudgetCheck.minimum_shortfall)}.`
              : `The recommended food-inclusive estimate is ${money(finalBudget.total_low)} – ${money(finalBudget.total_high)} against a budget of ${money(finalBudget.budget)}. Shortfall at the upper estimate: ${money(finalBudget.shortfall_at_high)}.`}
          </p>
        </div>
      )}

      {!estimateAvailable && !provisional && !overBudget && (
        <div className="notice">
          A complete food-inclusive trip estimate is unavailable.
          Some required costs or results are missing.
        </div>
      )}

      {/* Summary metrics */}
      <div className="metrics">

        <div className="metric">
          <span>Intercity transport</span>

          <strong>{money(transport.group_cost)}</strong>

          <small>
            {transport.fare_confirmed
              ? 'Fare returned by provider'
              : 'Fare not confirmed'}
          </small>
        </div>

        <div className="metric">
          <span>Accommodation options</span>

          <strong>{hotels.length}</strong>

          <small>Group/stay rates returned</small>
        </div>

        <div className="metric">
          <span>Full total confirmed</span>

          <strong>
            {plan.full_trip_total_confirmed ? 'Yes' : 'No'}
          </strong>

          <small>
            Estimates are not booking confirmations
          </small>
        </div>

      </div>

      {/* Flight results */}
      {transport.mode === 'flight' && (
        <section className="result-section">

          <h3>
            <Plane size={18} />
            Flight options
          </h3>

          {flightOptions.length > 0 ? (
            flightOptions.slice(0, 4).map((flight, index) => (
              <div className="option" key={index}>

                <div>
                  <b>{flight.airline || 'Flight'}</b>

                  <small>
                    {flight.departure || 'Departure unavailable'}
                    {' → '}
                    {flight.arrival || 'Arrival unavailable'}
                  </small>
                </div>

                <strong>
                  {money(flight.price)} / person
                </strong>

                {flight.booking_link && (
                  <a
                    href={flight.booking_link}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View option
                  </a>
                )}

              </div>
            ))
          ) : (
            <p className="muted">
              No verified flight options were returned.
            </p>
          )}

        </section>
      )}

      {/* Train results */}
      {transport.mode === 'train' && (
        <section className="result-section">

          <h3>
            <TrainFront size={18} />
            Train journey
          </h3>

          <div className="option">

            <div>
              <b>
                {results.selected_train?.train_name ||
                  results.selected_train?.name ||
                  'No confirmed train selected'}
              </b>

              <small>
                {results.selected_train?.train_number || ''}
              </small>
            </div>

            <strong>
              {money(results.train_transport_cost)} group fare
            </strong>

          </div>

          <p className="muted">
            Onward road transfer:{' '}
            {trainTransfer === null ||
            trainTransfer === undefined ||
            Number(trainTransfer) <= 0
             ? 'Not reported / not confirmed'
              : money(trainTransfer)}
          </p>

          {!transport.fare_confirmed && (
            <p className="muted">
              Train fare is unconfirmed. Do not treat the provisional
              transport allocation as a bookable fare.
            </p>
          )}

        </section>
      )}

      {/* Attractions */}
      <section className="result-section">
        <h3>
          <Compass size={18} />
          Attractions
        </h3>

        {attractions.length > 0 ? (
          attractions.slice(0, 10).map((attraction, index) => {
            const item = typeof attraction === 'string'
              ? { name: attraction }
              : attraction || {};

            return (
              <div className="option" key={item.id || item.place_id || index}>
                <div>
                  <b>{item.name || item.title || 'Attraction'}</b>
                  <small>
                    {[
                      item.category,
                      item.rating != null ? `Rating ${item.rating}` : null,
                      item.distance_m != null ? `${item.distance_m} m away` : null
                    ].filter(Boolean).join(' · ') || 'Details not supplied by source'}
                  </small>
                  {item.description && <small>{item.description}</small>}
                  {item.address && <small>{item.address}</small>}
                </div>
                {item.price != null && <strong>{money(item.price)}</strong>}
              </div>
            );
          })
        ) : (
          <p className="muted">
            {transportBudgetCheck.exceeds_budget
              ? 'Attraction search was skipped because intercity transport alone exceeds the total trip budget.'
              : 'No attractions found for this destination, or the attraction provider returned no listings.'}
          </p>
        )}
      </section>

      {/* Accommodation */}
      <section className="result-section">

        <h3>
          <Hotel size={18} />
          Accommodation
        </h3>

        {selectedHotel && (
          <div className="notice">
            <strong>Budget calculator recommendation:</strong>

            <p>
              {selectedHotel.name || 'Recommended accommodation'}
              {' · '}
              {money(
                selectedHotel.total_price ??
                selectedHotel.price
              )}
            </p>
          </div>
        )}

        {hotels.length > 0 ? (
          hotels.slice(0, 6).map((hotel, index) => (
            <div className="option" key={hotel.id || index}>

              <div>
                <b>{hotel.name || 'Accommodation'}</b>

                <small>
                  {hotel.room || 'Room details not supplied'}
                  {' · Rating '}
                  {hotel.rating ?? 'N/A'}
                </small>
              </div>

              <strong>
                {money(
                  hotel.total_price ?? hotel.price
                )}
              </strong>

            </div>
          ))
        ) : (
          <p className="muted">
            No complete group/stay rates were returned.
          </p>
        )}

        <p className="disclaimer">
          Returned accommodation rates are options, not confirmed
          bookings. Check the final price and availability before payment.
        </p>

      </section>

      {/* Food scenarios */}
      <section className="result-section">

        <h3>
          <Utensils size={18} />
          Food budget (separate estimate)
        </h3>

        {scenarios.length > 0 ? (
          <div className="scenario-grid">

            {scenarios.map(([name, scenario]) => {

              let scenarioLabel;

              const foodDetail = foodResults[name] || {};

              if (provisional) {
                scenarioLabel =
                  'Complete trip estimate is provisional — train fare excluded';
              } else if (
                scenario.status === 'within_budget'
              ) {
                scenarioLabel = 'Complete trip estimate is within budget';
              } else if (
                scenario.status === 'range_crosses_budget'
              ) {
                scenarioLabel = 'Complete trip estimate range crosses budget';
              } else {
                scenarioLabel = 'Complete trip estimate is over budget';
              }

              return (
                <div className="scenario" key={name}>

                  <b>{name}</b>

                  <strong>
                    {money(scenario.food_low)}
                    {' – '}
                    {money(scenario.food_high)}
                  </strong>

                  <small>{scenarioLabel}</small>

                  <small>
                    Group food estimate for {plan.trip?.travellers} traveller(s)
                    {' · '}
                    {plan.trip?.days} day(s)
                  </small>

                  {foodDetail.per_person_per_day_low != null &&
                    foodDetail.per_person_per_day_high != null && (
                      <small>
                        Per person/day: {money(foodDetail.per_person_per_day_low)}
                        {' – '}
                        {money(foodDetail.per_person_per_day_high)}
                      </small>
                    )}

                </div>
              );
            })}

          </div>
        ) : (
          <p className="muted">
            Separate food estimates could not be calculated from the returned results.
          </p>
        )}

        <p className="disclaimer">
          These are food-only group estimates, not verified restaurant menu
          prices. They are added once in the final trip expense breakdown below.
        </p>

      </section>

      {/* Final trip budget */}
      <section className="result-section">
        <h3>
          <Wallet size={18} />
          Final trip expense breakdown
        </h3>

        {finalBudget.available && finalBudget.components ? (
          <>
            <div className="option">
              <span>Intercity transport</span>
              <strong>{money(finalBudget.components.transport)}</strong>
            </div>
            <div className="option">
              <span>Accommodation · full stay/group</span>
              <strong>{money(finalBudget.components.accommodation)}</strong>
            </div>
            <div className="option">
              <span>Food · group estimate</span>
              <strong>
                {money(finalBudget.components.food?.low)}
                {' – '}
                {money(finalBudget.components.food?.high)}
              </strong>
            </div>
            <div className="option">
              <span>Local transport</span>
              <strong>{money(finalBudget.components.local_transport)}</strong>
            </div>
            <div className="option">
              <span>Attractions</span>
              <strong>{money(finalBudget.components.attractions)}</strong>
            </div>

            <div className="scenario">
              <b>
                Total estimated trip cost
                {finalBudget.scenario ? ` · ${finalBudget.scenario}` : ''}
              </b>
              <strong>
                {money(finalBudget.total_low)}
                {' – '}
                {money(finalBudget.total_high)}
              </strong>
              <small>Total trip budget: {money(finalBudget.budget)}</small>
              <small>
                {finalBudget.over_budget
                  ? `Shortfall at upper estimate: ${money(finalBudget.shortfall_at_high)}`
                  : `Remaining at upper estimate: ${money(finalBudget.remaining_at_high)}`}
              </small>
            </div>

            {!finalBudget.hotel_within_accommodation_budget && (
              <p className="notice">
                The accommodation amount uses the cheapest available group rate
                for estimation; it is above the allocated accommodation budget
                and is not an affordable recommendation.
              </p>
            )}
          </>
        ) : (
          <p className="muted">
            A complete final total is unavailable because one or more required
            prices are missing or unconfirmed. TripForge will not replace missing
            prices with zero or invent a total.
          </p>
        )}

        <p className="disclaimer">
          This is an estimate, not a booking confirmation. Confirm fares,
          accommodation rates, local transport and attraction charges before payment.
        </p>
      </section>

      {/* Errors and warnings */}
      {(
        plan.food_validation_error ||
        plan.budget_error ||
        plan.normalization_error
      ) && (
        <div className="notice">
          {[
            plan.food_validation_error,
            plan.budget_error,
            plan.normalization_error
          ]
            .filter(Boolean)
            .join(' · ')}
        </div>
      )}

      {/* Specialist agent execution */}
      {agentReviews.length > 0 && (
        <section className="result-section">

          <h3>
            <Sparkles size={18} />
            Multi-agent workflow
          </h3>

          {agentReviews.map((agent, index) => (
            <div className="option" key={agent.agent || index}>

              <div>
                <b>
                  {(agent.agent || 'Specialist agent')
                    .replaceAll('_', ' ')}
                </b>

                <small>
                  {agent.finding_status
                    ?.replaceAll('_', ' ') ||
                    'Review completed'}
                </small>
              </div>

              <span className="status good">
                {agent.execution_status || agent.status || 'Completed'}
              </span>

            </div>
          ))}

        </section>
      )}

    </div>
  );
}

export default function App() {

  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        "Hey! I'm TripForge, your AI travel planner. Tell me where you'd like to go, where you're starting from, and anything you've decided so far. I'll ask for the missing details before searching."
    }
  ]);

  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const tail = useMemo(
    () => messages.slice(-12),
    [messages]
  );

  async function send(event) {

    event.preventDefault();

    const text = draft.trim();

    if (!text || busy) return;

    const next = [
      ...messages,
      { role: 'user', content: text }
    ];

    setMessages(next);
    setDraft('');
    setBusy(true);
    setError('');

    try {

      const response = await fetch(
        `${API_BASE}/api/chat`,
        {
          method: 'POST',

          headers: {
            'Content-Type': 'application/json'
          },

          body: JSON.stringify({
            messages: next.slice(-12)
          })
        }
      );

      const body = await response.json();

      if (!response.ok) {
        throw new Error(
          body.detail || 'Chat request failed.'
        );
      }

      setMessages(old => [
        ...old,
        {
          role: 'assistant',
          content: body.assistant_message
        }
      ]);

      if (body.plan_result) {
        setResult(body.plan_result);
      }

    } catch (err) {

      setError(err.message);

      setMessages(old => [
        ...old,
        {
          role: 'assistant',
          content:
            `I couldn't process that just now: ${err.message}`
        }
      ]);

    } finally {

      setBusy(false);

    }
  }

  return (

    <main className="app-shell">

      {/* Sidebar */}
      <aside className="sidebar">

        <div className="brand">

          <div className="brand-icon">
            <Compass />
          </div>

          <div>
            <b>TripForge</b>
            <small>Multi-agent travel planner</small>
          </div>

        </div>

        <div className="side-label">
          WORKSPACE
        </div>

        <div className="side-active">
          <Sparkles size={17} />
          AI trip assistant
        </div>

        <div className="sidebar-note">

          <b>Planning, coordinated.</b>

          <p>
            Gemini understands your request. TripForge's existing
            travel workflow and orchestrator handle provider searches
            and budget coordination.
          </p>

        </div>

        <div className="side-bottom">
          TripForge · AI preview
        </div>

      </aside>

      {/* Main content */}
      <section className="main">

        <header className="topbar">

          <div>
            <span className="eyebrow">
              MULTI-AGENT SYSTEM WORK MODE ON
            </span>

            <h1>Where would you like to go?</h1>
          </div>

          <div className="online">
            <i />
            AI assistant ready
          </div>

        </header>

        <div className="chat-area">

          {/* Chat messages */}
          <div className="messages">

            {messages.map((message, index) => (

              <div
                className={`message ${message.role}`}
                key={index}
              >

                <div className="avatar">

                  {message.role === 'assistant'
                    ? <Sparkles size={16} />
                    : <Users size={16} />}

                </div>

                <div className="bubble">
                  {message.content}
                </div>

              </div>

            ))}

            {busy && (

              <div className="message assistant">

                <div className="avatar">
                  <Sparkles size={16} />
                </div>

                <div className="bubble loading">

                  <LoaderCircle
                    className="spin"
                    size={17}
                  />

                  TripForge is thinking…

                </div>

              </div>

            )}

          </div>

          {/* Chat input */}
          <form
            className="chat-composer"
            onSubmit={send}
          >

            <div className="composer-hint">

              <Sparkles size={15} />

              Chat naturally. I'll ask for anything missing
              before starting live searches.

            </div>

            <div className="composer-row">

              <textarea
                value={draft}
                onChange={event =>
                  setDraft(event.target.value)
                }
                onKeyDown={event => {

                  if (
                    event.key === 'Enter' &&
                    !event.shiftKey
                  ) {
                    event.preventDefault();
                    event.currentTarget.form.requestSubmit();
                  }

                }}
                placeholder="e.g. Plan a 3-day trip from Bengaluru to Ooty for 4 people…"
                rows={2}
                maxLength={4000}
              />

              <button
                className="send-button"
                type="submit"
                disabled={busy || !draft.trim()}
                aria-label="Send message"
              >

                {busy
                  ? <LoaderCircle className="spin" size={18} />
                  : <Send size={18} />}

              </button>

            </div>

            <div className="composer-foot">
              Enter to send · Shift + Enter for a new line
            </div>

          </form>

          {error && (
            <div className="error">
              {error}
            </div>
          )}

          {result && (
            <Result data={result} />
          )}

        </div>

        <footer>
          TripForge estimates are not booking confirmations.
          Confirm provider fares, rates and availability before payment.
        </footer>

      </section>

    </main>
  );
}
