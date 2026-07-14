# Phase 3: Intelligence — Strategic Plan

## Goal
Transform SES Think Tank from a static multi-agent debate tool into an **adaptive, self-aware collaborative intelligence system** that produces better output than any single agent could alone.

---

## Current State (v2.0)
| Capability | Status |
|----------|--------|
| 6 personas with DNA, relationships, interaction styles | ✅ Live |
| 4 workflow protocols (Salon, Design, Sprint, Living Lab) | ✅ Live |
| ASFE synergy engine (post-hoc scoring) | ✅ Live |
| WebSocket streaming + web dashboard | ✅ Live |
| Comprehensive eval (26 tests, all passing) | ✅ Live |
| Medium priority cleanup (rate limiting, sessions, logging, health) | 🔄 In progress |

---

## Phase 3 Features — Priority Order

### 3.1 Adaptive Team Composition (Highest Priority)
**Why first:** Biggest impact on output quality. Right now all 6 personas debate everything regardless of domain.

**Problem:** Static team composition wastes tokens and dilutes signal. A healthcare ethics question doesn't need Jax (the hype man), but it desperately needs Sage (the ethicist).

**Solution:** Domain classifier → optimal team selection → auto-composition.

```
Input: "AI companion for therapy patients"
  ↓
Domain Classifier (LLM call):
  - domain: mental_health
  - complexity: high
  - needs_critique: true
  ↓
Team Selector:
  - Core: Rook (architect), Elena (empathy), Sage (ethics)
  - Optional: Maya (divergent thinking)
  - Exclude: Jax (hype), Kael (skeptic — too negative for mental health)
  ↓
Output: 3-4 person team optimized for domain
```

**Implementation:**
1. Add `classify_domain(topic)` function — single LLM call returns domain + complexity + recommended personas
2. Add `/api/teams/analyze` endpoint — given a topic, returns recommended team composition
3. Update WebSocket handler to accept `auto_team: true` flag
4. UI: Show "Recommended Team" panel before starting conversation
5. Log composition choices → build dataset for future optimization

**Deliverable:** `/api/teams/analyze` endpoint + auto-team UI panel + domain classifier

---

### 3.2 Persistent Whiteboard (Medium Priority)
**Why second:** Captures value from conversations. Right now great ideas get lost in the message stream.

**Problem:** Agents generate insights during debate, but there's no structured way to extract, pin, and evolve them.

**Solution:** Structured whiteboard where agents pin ideas, vote, and build consensus.

```
WHITEBOARD STATE (per session):
{
  "pins": [
    {
      "id": "pin_1",
      "topic": "Offline-first architecture",
      "content": "Clinics in rural areas need offline mode...",
      "author": "rook",
      "votes": {"rook": "approve", "maya": "approve", "sage": "approve", "jax": "approve", "elena": "approve", "kael": "neutral"},
      "status": "approved",
      "comments": [
        {"author": "elena", "text": "But how do we handle sync conflicts?"},
        {"author": "rook", "text": "CRDTs — I'll expand in next turn"}
      ]
    }
  ]
}
```

**Implementation:**
1. Add whiteboard data structure to session state
2. Add `/api/sessions/:id/whiteboard` endpoint (GET/POST/PUT)
3. Add agent instruction to "pin" key ideas: `pin_idea(topic, content)`
4. UI: Live whiteboard panel alongside conversation stream
5. Final deliverable includes whiteboard state as structured output

**Deliverable:** Whiteboard API + UI panel + agent pinning instructions

---

### 3.3 Real-Time Synergy Dashboard (Lower Priority)
**Why lower:** Nice-to-have visualization, doesn't directly improve output quality.

**Problem:** ASFE scores are calculated post-hoc. No way to see if the team is converging or spiraling during the conversation.

**Solution:** Live metrics showing team dynamics as they happen.

**Metrics:**
- **Cross-reference rate** — Are agents building on each other? (mentions of other personas per turn)
- **Friction level** — Productive tension vs. noise (disagreement frequency × resolution quality)
- **Convergence score** — Is the team reaching consensus? (idea overlap over time)
- **Idea diversity** — Are we exploring enough perspectives? (unique topics raised)
- **Participation balance** — Is one persona dominating? (turn count per persona)

**UI:**
- Live sparkline graph: synergy/friction over time
- Heatmap: which personas reference which
- Participation pie chart
- "Intervention" button: human can steer conversation

**Implementation:**
1. Add lightweight real-time metrics calculator (runs after each turn)
2. Emit metrics via WebSocket alongside conversation messages
3. UI: Real-time metrics panel with sparklines and heatmaps
4. Store metrics history for post-hoc analysis

**Deliverable:** Real-time metrics WebSocket events + UI dashboard

---

### 3.4 Multi-Session Memory (Future)
**Why last:** Requires infrastructure (SQLite DB) and changes how sessions work fundamentally.

**Problem:** Each session starts fresh — no continuity across conversations.

**Solution:** Persistent memory across sessions for idea evolution.

```
Session 1: "AI diagnostics for rural clinics"
  → Pinned 3 ideas: offline-first, community health workers, bias mitigation

Session 2: "Follow up on diagnostics"
  → Loads previous 3 ideas, continues refinement

Session 3: "Healthcare equity"
  → References diagnostics work: "As we discussed in session #1, offline-first is critical"
```

**Implementation:**
1. SQLite DB for persistent idea storage
2. Each idea has: ID, topic, content, votes, session_history, status
3. Agents can reference: "As we discussed in session #3..."
4. User can browse idea history and resurrect old threads

**Deliverable:** SQLite memory layer + cross-session references + idea browser UI

---

## Implementation Strategy

### Week 1: Adaptive Teams (3.1)
- Day 1: Domain classifier + `/api/teams/analyze` endpoint
- Day 2: Auto-team WebSocket handler + UI "Recommended Team" panel
- Day 3: Test & iterate — compare auto-team vs manual team output quality

### Week 2: Whiteboard (3.2)
- Day 1: Whiteboard data structure + API endpoints
- Day 2: Agent pinning instructions + voting mechanism
- Day 3: UI whiteboard panel + integration with deliverables

### Week 3: Synergy Dashboard (3.3)
- Day 1: Real-time metrics calculator
- Day 2: WebSocket metric emission + UI sparklines/heatmaps
- Day 3: Intervention button + human-in-the-loop steering

### Week 4: Memory (3.4)
- Day 1: SQLite schema + idea persistence
- Day 2: Cross-session references + idea browser
- Day 3: Agent memory injection + integration testing

---

## Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Solo vs team delta | 0.5 points | 1.0+ points |
| Idea survival rate | N/A (no whiteboard) | 60%+ of pinned ideas in final deliverable |
| Team composition accuracy | N/A (static) | 80%+ user approval of auto-selected teams |
| Convergence speed | ~15 turns | ~10 turns (faster consensus) |
| Output quality (SES eval) | 2.71/4.0 | 3.2+/4.0 |

---

## Tech Stack Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Session storage | JSON files → SQLite | Start simple, migrate when cross-session needed |
| Whiteboard format | JSON state | Easy to serialize, diff, and version |
| Metrics engine | Lightweight Python | No heavy deps, runs in-process |
| Domain classifier | LLM call (Qwen 3.6) | Already have local model, no extra infra |
| UI framework | Vanilla JS (current) | Keep lightweight, no framework overhead |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Domain classifier misclassifies | Wrong team → poor output | User can override; log misclassifications for tuning |
| Whiteboard adds token overhead | Slower turns, higher cost | Pin only key ideas; prune old pins |
| Real-time metrics slow down server | Latency spikes | Run metrics calculation async, emit on next turn |
| Memory grows unbounded | Performance degradation | Cap at 100 ideas; archive old sessions |
