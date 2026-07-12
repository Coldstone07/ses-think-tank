# SES Think Tank — Multi-Agent Collaborative Brainstorming Platform

A local-first multi-agent system for structured debate, design sprints, and creative synthesis. Built on the [SES Benchmark](https://github.com/Coldstone07/SES-benchmark) framework for evaluating emotional, social, and spiritual presence in AI interactions.

## 🧬 The Living Team Framework (LTF)

Six AI personas with distinct **DNA** — core drives, blind spots, interaction styles, and explicit relationships with each other. They don't just take turns; they **collaborate, debate, and build on each other's ideas**.

### The Team

| Persona | Role | Core Drive | Blind Spot |
|---------|------|------------|------------|
| ♟️ **Rook** | The Architect | Build systems that work | Dismisses emotion as "noise" |
| 🌸 **Elena** | The Empath | Amplify unheard voices | Over-validates without action |
| ⚡ **Kael** | The Provocateur | Expose hidden power | Provokes for its own sake |
| 🔮 **Maya** | The Synthesizer | Find hidden patterns | Overcomplicates with metaphors |
| 🔥 **Jax** | The Market Realist | Ship what users adopt | Dismisses non-monetizable ideas |
| 🌿 **Sage** | The Ethicist | Prevent harm at scale | Paralysis by analysis |

### Collaboration Protocols

| Mode | Phases | Best For |
|------|--------|----------|
| 💬 **Salon** | Freeform debate | Open exploration |
| 🔬 **Design Studio** | Diverge → Converge → Stress → Synthesize | Building detailed architectures |
| 🚀 **Sprint** | Draft → Refine → Stress → Finalize | Shipping concrete deliverables |
| 🧬 **Living Lab** | Debate → Whiteboard → Synthesis → Ship/Kill | Full team with cross-referencing and final vote |

## 🚀 Quick Start

```bash
# Start the server
cd ses-think-tank
python3.11 -m uvicorn app:app --host 0.0.0.0 --port 8773

# Open the dashboard
# http://localhost:8773
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/personas` | GET | List all 6 personas with DNA |
| `/api/workflows` | GET | List all workflow modes |
| `/api/items` | GET | List SES benchmark items (174) |
| `/api/chat` | POST | Chat with a single persona |
| `/ws/conversation` | WebSocket | Multi-agent session (Salon/Design/Sprint/Living Lab) |
| `/api/evaluate` | POST | Evaluate a conversation |

### Chat API Example

```bash
curl -X POST http://localhost:8773/api/chat \
  -H "Content-Type: application/json" \
  -d '{"persona_id":"jax","message":"AI diagnostics for rural clinics — what do you think?"}'
```

## 📊 Agentic Synergy & Friction Engine (ASFE)

Measures whether multi-agent collaboration actually produces better output than solo agents.

### Metrics

| Metric | What It Measures |
|--------|-----------------|
| **Synergy** | Cross-references between agents, building on previous points |
| **Friction** | Productive tension vs. noise — disagreements and resolutions |
| **Quality** | Solo vs. team comparison with 5-dimension grading |
| **Dynamic Sprints** | Iterative draft refinement across rounds |

### Running Tests

```bash
# Full ASFE test (solo baselines + team discussions + sprints + grading)
python3.11 scripts/asfe_test.py

# Quality grading on existing results
python3.11 scripts/asfe_grade.py

# SES benchmark evaluation for personas
python3.11 scripts/evaluate_personas_ses.py
```

### Key Findings

| Domain | Best Synergy | Best Friction | Winner |
|--------|-------------|---------------|--------|
| Healthcare | `full_team` (2.50) | `core_four` (0.70) | **Architects** (balanced) |
| Mental Health | `full_team` (3.38) | `core_four` (0.78) | **Critics** (3.06 synergy) |

## 📁 Project Structure

```
ses-think-tank/
├── app.py                      # FastAPI backend (personas, workflows, WebSocket)
├── scripts/
│   ├── asfe_test.py            # Agentic Synergy & Friction Engine
│   ├── asfe_grade.py           # Quality grading for ASFE results
│   ├── evaluate_personas_ses.py # SES benchmark evaluation
│   └── healthcare_marathon.py  # Healthcare LLM innovation marathon
├── web/
│   ├── index.html              # Main dashboard (Salon/Design/Sprint modes)
│   └── live_personas.html      # Live personas playground
├── outputs/                    # Generated transcripts and results
│   ├── asfe_results.json       # ASFE test results
│   ├── persona_ses_eval.json   # SES evaluation results
│   └── ...
├── agents/                     # (Reserved for future agent definitions)
└── README.md                   # This file
```

## 🔧 Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `LM_STUDIO_URL` | `http://localhost:1234/v1` | LM Studio API endpoint |
| `THINK_TANK_MODEL` | `qwen/qwen3.6-27b` | Model to use for personas |
| `GEMINI_API_KEY` | *(empty)* | Gemini API key for evaluation (optional) |

## 📈 Roadmap

### Phase 1: Foundation ✅
- [x] 6 personas with DNA and relationships
- [x] 4 collaboration protocols (Salon, Design, Sprint, Living Lab)
- [x] WebSocket streaming with phase tracking
- [x] Web dashboard with mode selector
- [x] SES benchmark integration

### Phase 2: Measurement ✅
- [x] Agentic Synergy & Friction Engine (ASFE)
- [x] Solo vs. team quality comparison
- [x] Team composition optimization
- [x] Dynamic sprint workflows

### Phase 3: Intelligence (Next)
- [ ] Adaptive team composition based on prompt domain
- [ ] Real-time synergy/friction dashboard
- [ ] Persistent whiteboard with idea tracking
- [ ] Multi-session memory and idea evolution

### Phase 4: Scale (Future)
- [ ] Plugin system for custom personas
- [ ] External tool integration (web search, code execution)
- [ ] Multi-repo collaboration across think tanks
- [ ] Real-time human-in-the-loop intervention

## 📄 License

MIT

## 🔗 Related Projects

- [SES Benchmark](https://github.com/Coldstone07/SES-benchmark) — Emotional, Social, Spiritual evaluation framework
- [Hermes Agent](https://hermes-agent.nousresearch.com) — Local AI agent platform
