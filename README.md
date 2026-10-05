# swasthiq_assign

## SwasthiQ Clinic Front Desk Agent

A local Python REST API and React interface for the synthetic Sunrise Clinic assignment. The agent uses a deterministic conversation controller and six validated tools; no LLM or patient data service is required.

## Run

Requires Python 3.9+, Node.js, and npm. From the repository root:

```bash
python3 run.py
```

On the first run, this installs frontend packages and builds React. Open `http://127.0.0.1:8000`. Subsequent runs serve the existing build. The queue includes a selector for the 15 supplied examples. All clinic records are synthetic.

Run tests and the supplied harness in another terminal:

```bash
python3 -m unittest discover -s tests -v
python3 runner.py --repeat 3
python3 runner.py --dir adversarial --repeat 3
```

The tests compare actual states and tool calls with each script's `expected` block. The supplied runner validates only part of the response contract and does not do that comparison.

## Evaluation API

`POST /agent/run` accepts exactly the supplied contract:

```json
{"conversation_id":"cv_0001","today":"2026-10-01","turns":["Dr. Rao ke saath appointment chahiye.","Harpreet Singh, 9812200311. Saturday subah."]}
```

It returns `conversation_id`, ordered `tool_calls` (including failed calls), `terminal_state`, `escalation_reason`, `patient_id`, `appointment_id`, `reply`, and `metrics`. Invalid top-level requests return HTTP 400 with an actionable message. `today` is the sole reference for relative dates.

Each request loads a fresh `clinic.json` snapshot, as required by the harness. Appointment mutations inside a shared `ClinicState` use a lock, so two threads acting on the same state cannot double-book a slot. The UI audit history is separate from clinic state and lasts until the server restarts.

### Tool contracts

The six tools live in `backend/tools.py`. They do not call a model.

| Tool | Arguments | Result |
|---|---|---|
| `search_slots` | `doctor_id`, `date` | Available 15-minute starts and ends |
| `lookup_patient` | `name` and/or `phone` | All matching candidates with active appointments |
| `book_appointment` | `patient_id`, `doctor_id`, `date`, `start`, `actor_id` | New appointment |
| `reschedule_appointment` | `appointment_id`, `patient_id`, `doctor_id`, `date`, `start`, `actor_id` | Updated appointment |
| `cancel_appointment` | `appointment_id`, `patient_id`, `actor_id` | Cancelled appointment |
| `escalate_to_human` | `reason`, `detail` | Open handoff record |

Malformed tool arguments raise `ToolError` with a specific code and message. The conversation controller records the attempted call and safely handles the error.

### UI API

The React app uses `GET /api/stats`, `GET /api/conversations`, `GET /api/conversations/{run_id}`, `GET /api/examples`, `POST /api/examples/run`, and `POST /api/handoffs/{run_id}/resolve`. `GET /api/health` supports a basic service check.

## Safety and behavior

The controller reads the full fixed caller script before a booking mutation. Urgent symptoms preempt all appointment work; other medical advice, ambiguous identity, missing authorization, and out-of-scope requests go to a person. Unsupported or incomplete appointment requests end without a mutation. Tool results are the only source of patient, slot, and appointment identifiers.

The rule-based language parser is intentionally limited. It covers the supplied English and transliterated Hindi examples, but unusual phrasing may be left unacted upon or escalated. It is not a clinical triage system or production identity verification. See `DECISIONS.md` for the explicit ambiguities and tradeoffs.

## Model, tokens, and latency

**Model:** none; deterministic rule engine. **Model tokens:** 0 per conversation. Local direct-call measurements on the 15 supplied scripts were **0–3 ms per conversation** on 4 October 2026; API and browser overhead are additional and machine-dependent. Each API response reports its own measured `latency_ms` and `tokens`.

## Submission items

`/backend`, `/frontend`, `/adversarial`, `DECISIONS.md`, `PLAN.md`, tests, and `AI_TRANSCRIPT.txt` are included. The narrated failure-analysis video is generated locally in `output/`, which is excluded from Git. A live hosted link and submission email are still pending.

## Deploy on Render

This repository includes a multi-stage `Dockerfile` and `render.yaml` for one Render web service. The Docker build compiles React, then runs the Python API and serves the built frontend from the same origin. The image defaults to `PORT=10000`, which Render can override; the server binds to all interfaces when that variable is present. Push the repository to GitHub, create a Render Blueprint from `render.yaml`, and verify `/api/health` and the app at the resulting public URL. Handoff history is in memory and resets when a free instance restarts.
