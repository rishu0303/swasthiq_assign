# Implementation plan

1. **Complete:** Build a deterministic clinic tool layer with explicit input validation, deduplicated 15-minute slots, guardian checks, and atomic mutations.
2. **Complete:** Build `POST /agent/run` around the supplied request and response contract. Inspect the whole fixed caller script before any mutation, prioritize urgent symptoms, and record every tool call.
3. **Complete:** Add a REST layer for the handoff queue and conversation detail view. Keep evaluation clinic state fresh per run while retaining UI audit history separately.
4. **Complete:** Cover the supplied 15 cases, concurrency, malformed inputs, and eight new adversarial scripts. Compare actual results with `expected`, since `runner.py` does not.
5. **Complete locally:** Build the two React screens from the PDF and document decisions, API contracts, measured latency, and a one-command local run. The frontend was inspected in a browser.

Publishing, a live deployment, a video, and an email require separate user action and are outside this local implementation.
