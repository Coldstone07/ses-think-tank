# Development Plans — SES Think Tank

## Current State (v2.0)

- **6 personas** with DNA, relationships, and interaction styles
- **4 workflow protocols** (Salon, Design, Sprint, Living Lab)
- **ASFE** — Agentic Synergy & Friction Engine for measuring collaboration quality
- **Web dashboard** with mode selector, phase tracking, live personas
- **SES benchmark integration** for emotional/social/spiritual evaluation

---

## Phase 3: Intelligence

### 3.1 Adaptive Team Composition ✅
**Problem:** Right now team composition is static. Different domains need different teams.
**Solution:** Auto-select team based on prompt domain/complexity using an LLM classifier.

```
Prompt → Domain Classifier → Optimal Team Composition
"AI diagnostics for rural clinics" → healthcare → architects (rook, maya, sage)
"AI companion for therapy patients" → mental_health → critics (kael, elena, sage)
"AI financial advisor" → finance → builders (rook, maya, jax)
```

**Implementation:**
1. `classify_domain(topic, workflow_mode)` in `app.py:886` — makes a single LLM call to Qwen 3.6 via `call_llm_raw()` + `extract_json_from_text()` and returns domain, complexity, recommended_personas, excluded_personas, reasoning
2. `POST /api/teams/analyze` endpoint — accepts `{"topic": "...", "workflow_mode": "..."}`, returns classifier output
3. WebSocket `auto_team` flag — when `start_conversation` includes `"auto_team": true`, the server calls `classify_domain()` and overrides `persona_ids` with the recommended personas; sends a `team_recommendation` WS event with the analysis
4. Web UI "Team Analysis" panel — "Analyze Team" button calls `/api/teams/analyze`, displays recommended personas with icons, domain/complexity badges, reasoning, and a "Use Recommended Team" button that starts a conversation with `auto_team: true`

**Persona descriptions used in classifier prompt:**
- rook: Systems architect, structured thinking. Best at: technology, policy, complex systems
- elena: Empathy specialist, human-centered. Best at: mental_health, education, community
- kael: Skeptic/critic, challenges assumptions. Best at: ethics, policy, finance (risk)
- maya: Divergent thinker, creative connections. Best at: creative, education, technology
- jax: Hype man, optimist. Best at: creative, technology (pitching), education
- sage: Ethicist, wisdom. Best at: ethics, mental_health, healthcare, policy

### 3.2 Persistent Whiteboard ✅
**Problem:** Ideas get lost in the conversation stream.
**Solution:** Persistent whiteboard where agents pin ideas, vote, and evolve them.

```
WHITEBOARD:
┌─────────────────────────────────────────────┐
│ 📌 AI Diagnostics for Rural Clinics         │
│    Votes: ♟️✅ 🌸✅ 🔮✅ ⚡❌ 🔥✅ 🌿⏳       │
│    Status: UNDER REVIEW                      │
│                                             │
│ Key Points:                                 │
│ 1. Offline-first architecture (Rook)        │
│ 2. Community health worker integration      │
│    (Elena)                                  │
│ 3. Bias mitigation required (Sage)          │
│ 4. Distribution via existing clinic networks│
│    (Jax)                                    │
└─────────────────────────────────────────────┘
```

**Implementation:**
1. `WhiteboardPin` dataclass in `app.py:1208` — id, topic, content, author, status, votes, comments, created_at
2. `ConversationSession.whiteboard` field — `Dict[str, WhiteboardPin]` stores all pins per session
3. **API Endpoints** (all in `app.py`):
   - `GET /api/sessions/:id/whiteboard` — returns full whiteboard state
   - `POST /api/sessions/:id/whiteboard/pin` — create a new pin
   - `PUT /api/sessions/:id/whiteboard/pins/:pin_id/vote` — cast a vote
   - `PUT /api/sessions/:id/whiteboard/pins/:pin_id/comment` — add a comment
   - `PUT /api/sessions/:id/whiteboard/pins/:pin_id/status` — update status
   - `DELETE /api/sessions/:id/whiteboard/pins/:pin_id` — remove a pin
4. **WebSocket actions**: `pin_idea`, `vote_pin`, `comment_pin` handlers in `websocket_endpoint`
5. **Broadcast**: `broadcast_whiteboard()` sends `whiteboard_update` events to all connected clients on every change
6. **Agent prompts updated**: Whiteboard instructions added to all 6 persona system prompts
7. **UI**: Whiteboard panel in right sidebar with pin cards, vote buttons (✅/❌/⏳), expandable comments, status badges, and "Pin Idea" button
8. **Persistence**: Whiteboard state saved to session JSON files and restored on load
9. **Deliverable**: Whiteboard state included in `session_complete` event

### 3.3 Real-Time Synergy Dashboard ✅
**Problem:** Synergy/friction metrics are calculated post-hoc.
**Solution:** Live dashboard showing team dynamics as they happen.

**Metrics tracked in real-time (calculated each turn, <50ms):**
- **cross_reference_rate**: Mentions of other persona names / total turns
- **friction_level**: Turns with disagreement keywords (but, disagree, however, wrong, risk, concern) / total turns
- **convergence_score**: Word overlap between consecutive turns
- **idea_diversity**: Count of unique significant words across all turns
- **participation_balance**: Shannon entropy of turn distribution (normalized 0-1)
- **participation_counts**: Per-persona turn counts (for pie chart)
- **health**: Green/yellow/red color coding based on thresholds

**Implementation:**
1. `calculate_synergy_metrics(session)` in `app.py:1288` — lightweight metrics engine; runs under `50ms` per turn
2. `ConversationSession.synergy_metrics` and `metrics_history` fields at `app.py:1281-1282` — stores current metrics + turn-by-turn history
3. `update_and_emit_metrics()` at `app.py:1430` — called after each message in `run_salon()` and `run_structured()`; stores metrics and emits WS event
4. `synergy_metrics` WS event — emitted after each turn with `{metrics, turn}`
5. `synergy_summary` WS event — included in `session_complete` payload with `{metrics_history, final_metrics}`
6. `GET /api/sessions/:id/metrics` at `app.py:2169` — returns current synergy metrics
7. `GET /api/sessions/:id/metrics/history` at `app.py:2180` — returns full turn-by-turn history
8. `POST /api/sessions/:id/intervene` at `app.py:2189` — injects a human steering message (`{"message": "..."}`)
9. WS `intervene` action at `app.py:2379` — same as REST endpoint but via WebSocket
10. Synergy dashboard UI in `web/index.html` — sparkline graphs for cross-reference, friction, convergence; donut chart for participation; idea diversity counter; live update via WS; color-coded health badge; Intervene button + input field
11. Metrics persisted to session JSON files and restored on load

### 3.4 Multi-Session Memory ✅
**Problem:** Each session starts fresh — no continuity.
**Solution:** Persistent memory across sessions for idea evolution.

```
Session 1: "AI diagnostics" → Stored in SQLite with pins, personas, deliverable
Session 2: "Healthcare equity" → Auto-detects similarity, shows past findings
Session 3: "AI diagnostics follow-up" → Recommends team from past performance
```

**Implementation:**

1. **SQLite Memory Store** (`init_memory_db()` in `app.py`) — lightweight SQLite database at `memory.db` with 4 tables:
   - `memory_sessions` — session_id, topic, workflow_mode, started_at, ended_at, turn_count, deliverable, summary, persona_ids
   - `memory_pins` — id, session_id, topic, content, author, status, created_at (whiteboard pins from completed sessions)
   - `persona_interactions` — id, session_id, persona_id, turns_spoken, partners (which personas worked together)
   - `cross_references` — id, session_id, referenced_session_id, reference_text, created_at

2. **Memory Population** (`populate_memory()` in `app.py:1503`) — automatically called after `save_session_to_disk()` in both `run_salon()` and `run_structured()`:
   - Inserts session record with topic summary (keyword extraction)
   - Extracts all whiteboard pins into `memory_pins` table
   - Records persona interaction history (turn counts per persona, partner lists)

3. **Memory Retrieval API** (all in `app.py`):
   - `GET /api/memory/sessions?topic=...` — search past sessions by keyword overlap (simple token matching, no deps)
   - `GET /api/memory/sessions?persona=...` — find sessions with specific personas via JOIN
   - `GET /api/memory/session/:id` — get full session memory record (session + pins + interactions)
   - `GET /api/memory/insights/:topic` — get cross-session insights (session count, similar sessions, key findings, persona frequency)
   - `GET /api/memory/recommended-team/:topic` — recommend team based on past performance (scores personas by appearance count + turns spoken)

4. **WebSocket Integration** (`websocket_endpoint` in `app.py`):
   - Emits `memory_suggestion` event on `start_conversation` when new topic matches past sessions
   - Payload: `{match_count, similar_sessions: [{session_id, topic, turn_count}], message}`
   - Wrapped in try/except — never blocks conversation startup

5. **UI Memory Panel** (`web/index.html`):
   - Memory section in right sidebar with search input and past session count badge
   - Session cards showing topic, workflow mode, date, turn count, persona chips
   - Click to expand — loads full summary and deliverable from `/api/memory/session/:id`
   - Cross-session insight badges (e.g., "3 similar sessions found", persona frequency)
   - Auto-checks memory on topic input (debounced 800ms) — shows related past sessions
   - WebSocket `memory_suggestion` handler shows real-time suggestions on conversation start

**Design decisions:**
- SQLite with built-in `sqlite3` module — no `pip install` needed
- Keyword overlap for topic similarity — no vector embeddings or external dependencies
- Memory population wrapped in try/except — never blocks session completion
- Summary extracted from topic keywords (simple but functional)

---

## Phase 4: Scale

### 4.1 Plugin System for Custom Personas
**Problem:** Adding new personas requires editing `app.py`.
**Solution:** YAML-based persona definitions loaded from a directory.

```yaml
# personas/custom/researcher.yaml
id: researcher
name: Dr. Chen
title: The Researcher
icon: 🔬
color: "#10b981"
background: "...
dna:
  core_drives: [...]
  blind_spots: [...]
  interaction_style: "..."
  relationships:
    rook: "..."
    elena: "..."
```

### 4.2 External Tool Integration
**Problem:** Agents are limited to their training data.
**Solution:** Tool calling for web search, code execution, data analysis.

```python
# Agent can call tools during conversation
tools = [
    {"name": "web_search", "description": "Search the web"},
    {"name": "execute_code", "description": "Run Python code"},
    {"name": "read_file", "description": "Read a file"},
]
```

### 4.3 Multi-Repo Collaboration
**Problem:** Each think tank is isolated.
**Solution:** Cross-repo collaboration where different teams work on different aspects.

```
Think Tank A (Healthcare) ↔ Think Tank B (Policy) ↔ Think Tank C (Tech)
```

### 4.4 Human-in-the-Loop
**Problem:** Fully autonomous debates can go off-track.
**Solution:** Human can intervene, steer, or veto at any point.

**Intervention modes:**
- **Steer:** "Focus more on the distribution challenges"
- **Veto:** "Kill this idea, it's not viable"
- **Amplify:** "Expand on Elena's point about community trust"
- **Pause:** "Stop and reflect on what we've covered so far"

---

## Technical Debt

### High Priority (All Resolved ✅)
- [x] **Fix grading echo issue** — Added `call_llm_raw()` + `extract_json_from_text()` to `app.py`; updated `asfe_grade.py` to use them. Grading now works with reasoning models.
- [x] Fix Windows port TIME_WAIT issues — Added `find_free_port()` with `SO_REUSEADDR` and auto-hopping (8773-8783).
- [x] Add proper error handling to WebSocket connections — Added JSON decode error handling, missing topic validation, conversation error catch, and generic exception handler.
- [x] Add unit tests for persona generation and ASFE metrics — Created `tests/test_core.py` with 24 tests across 6 classes (personas, workflows, JSON extraction, reasoning extraction, ASFE metrics, integration).

### Medium Priority (All Complete ✅)
- [x] **Add rate limiting** — In-memory rate limiter middleware (100 req/min per IP, returns 429).
- [x] **Add session persistence** — Conversations saved as JSON in `sessions/`; loaded on startup; `GET /api/sessions/:id` and `DELETE /api/sessions/:id` endpoints.
- [x] **Add logging for debugging** — Structured JSON logging via Python's `logging` module, output to `logs/app.log`.
- [x] **Add health check endpoint** — `GET /health` returns status, uptime, memory_mb, active_sessions.

### Low Priority
- [ ] Migrate from FastAPI to something lighter if needed
- [ ] Add Docker support for easy deployment
- [ ] Add CLI interface for headless usage
- [ ] Add export to markdown/PDF for deliverables

---

## Metrics to Track

### Collaboration Quality
- Synergy score over time (is the team getting better at collaborating?)
- Friction resolution rate (do disagreements lead to better output?)
- Idea survival rate (how many pinned ideas make it to final deliverable?)

### Output Quality
- Solo vs team delta (does collaboration actually improve quality?)
- Domain-specific performance (which teams work best for which topics?)
- User satisfaction (do humans prefer team output over solo?)

### System Performance
- Response time per persona
- Token usage per session
- Error rate (failed API calls, timeouts)
