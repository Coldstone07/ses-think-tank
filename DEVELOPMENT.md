# Development Plans — SES Think Tank

## Current State (v2.0)

- **6 personas** with DNA, relationships, and interaction styles
- **4 workflow protocols** (Salon, Design, Sprint, Living Lab)
- **ASFE** — Agentic Synergy & Friction Engine for measuring collaboration quality
- **Web dashboard** with mode selector, phase tracking, live personas
- **SES benchmark integration** for emotional/social/spiritual evaluation

---

## Phase 3: Intelligence (Next)

### 3.1 Adaptive Team Composition
**Problem:** Right now team composition is static. Different domains need different teams.
**Solution:** Auto-select team based on prompt domain/complexity.

```
Prompt → Domain Classifier → Optimal Team Composition
"AI diagnostics for rural clinics" → healthcare → architects (rook, maya, sage)
"AI companion for therapy patients" → mental_health → critics (kael, elena, sage)
"AI financial advisor" → finance → builders (rook, maya, jax)
```

**Implementation:**
1. Add domain classifier prompt that categorizes incoming prompts
2. Map domains to optimal team compositions (from ASFE results)
3. Auto-select team or suggest to user
4. Log composition choices for future optimization

### 3.2 Real-Time Synergy Dashboard
**Problem:** Synergy/friction metrics are calculated post-hoc.
**Solution:** Live dashboard showing team dynamics as they happen.

**Metrics to track in real-time:**
- Cross-reference rate (are agents building on each other?)
- Friction level (productive tension vs. noise)
- Convergence score (is the team reaching consensus?)
- Idea diversity (are we exploring enough perspectives?)

**UI:**
- Live graph showing synergy/friction over time
- Heatmap of which personas reference which
- "Intervention" button for human to steer the conversation

### 3.3 Persistent Whiteboard
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
1. Add whiteboard data structure to session state
2. Agents can "pin" ideas with `pin_idea(topic, content)`
3. Other agents vote (✅/❌/⏳) and add comments
4. Final deliverable includes whiteboard state

### 3.4 Multi-Session Memory
**Problem:** Each session starts fresh — no continuity.
**Solution:** Persistent memory across sessions for idea evolution.

```
Session 1: "AI diagnostics" → Pinned 3 ideas
Session 2: "Follow up on diagnostics" → Loads previous ideas, continues
Session 3: "Healthcare equity" → References diagnostics work
```

**Implementation:**
1. SQLite DB for persistent idea storage
2. Each idea has: ID, topic, content, votes, session_history
3. Agents can reference previous sessions: "As we discussed in session #3..."
4. User can browse idea history and resurrect old threads

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

### High Priority
- [ ] Fix Windows port TIME_WAIT issues (SO_REUSEADDR or process manager)
- [ ] Add proper error handling to WebSocket connections
- [ ] Add unit tests for persona generation and ASFE metrics
- [ ] Fix grading echo issue (LLM returning example JSON instead of real scores)

### Medium Priority
- [ ] Add rate limiting to API endpoints
- [ ] Add session persistence (save/load conversations)
- [ ] Add logging for debugging (structured JSON logs)
- [ ] Add health check endpoint

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
