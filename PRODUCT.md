# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two audiences, weighted equally:

- **Riders in Toronto** who use a manual or power wheelchair, a scooter, a walker, cane or crutches, or who have limited stamina. They plan a trip (often on a phone) and need to know before leaving whether the way there has stairs, broken station elevators, or likely sidewalk barriers.
- **Hackathon judges (HTV 11)** seeing a short live demo on a laptop or projector. They need to grasp in seconds what ClearPath does differently from a normal map app.

## Product Purpose

ClearPath plans Toronto trips for people with mobility limits. It compares an accessible street route that avoids stairs, TTC transit options checked against station elevators and live outages, and the "typical" route most map apps would suggest, so the person can see exactly what the typical route would have cost them. Success is someone choosing a route they can actually complete.

## Positioning

Routes are checked against three things a generic map ignores: stairs on the street network, TTC elevator availability and outages, and a forecast of sidewalk barrier reports (uncleared or damaged sidewalks) built from City of Toronto 311 data and weather. The typical route is shown side by side as the comparison.

## Operating Context

- Three-step flow: Where to → How you get around (mobility profile, TTC on/off, avoid likely barriers) → Your options (route cards, directions, notes).
- A map shows the chosen route, the typical route, stairs, unconfirmed segments, station elevator status, and a hexagon forecast of barrier risk for today and the next two days.
- A "Developer details" drawer exposes request/response JSON and barrier GeoJSON for debugging during development and demos.

## Capabilities and Constraints

- React + Vite + MapLibre frontend; FastAPI backend; OpenRouteService routing; OpenFreeMap vector tiles (Positron; Liberty via VITE_MAP_STYLE).
- Mobility profiles: manual wheelchair, power wheelchair or scooter, walker/cane/crutches, limited stamina.
- Barrier fixtures are fictional in development; risk is a forecast, not ground truth (see docs/data-limits.md).
- Existing frontend tests rely on current visible copy and accessible names; keep them passing.
- Trip mode: turn-by-turn on real GPS or a simulator, alerts ahead (barriers, rider reports, forecast, City road restrictions, TTC elevator outages), automatic re-routing, and rider reports ("blocked" / "clear") that routing avoids once two riders confirm a spot.
- Ward report cards: nonpartisan per-ward pages from City 311 data with live TTC, closure and forecast numbers and a Gemini-written plain-words summary (template fallback). No candidates, parties or ward comparisons.

## Brand Commitments

- Name: ClearPath (Toronto).
- Body face: Atkinson Hyperlegible, kept for low-vision legibility (user-confirmed).
- Voice: plain, direct, second person ("How do you get around?"), no apologies, honest about uncertainty.
- The Developer details panel stays visible in the UI (user-confirmed).

## Evidence on Hand

- Live model metrics shown in the UI (ROC-AUC, report lag) from the risk endpoint.
- No testimonials, user counts, partners or press exist. Do not fabricate them.

## Product Principles

1. Show the cost of the typical route, not just the alternative.
2. Be honest about uncertainty: unconfirmed segments and forecasts are labelled as such.
3. Legibility first: every user may have low vision, tremor, or fatigue.
4. The map supports the decision; the route options make it.

## Accessibility & Inclusion

WCAG 2.2 AA minimum: contrast, visible keyboard focus, screen-reader labels, large hit targets, reduced-motion respected. Users include people with low vision and limited fine motor control.
