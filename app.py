"""
SES Think Tank v3 — Multi-Agent Conversational Brainstorming
============================================================
Three workflow modes:
- SALON: Freeform debate (original mode)
- DESIGN: Diverge → Converge → Stress Test → Synthesize (produces a spec)
- SPRINT: Draft → Refine → Stress Test → Finalize (produces a deliverable)

Each phase assigns specific roles to personas. The UI shows the current
phase, who's speaking, and the final deliverable.

Usage:
    python3.11 -m uvicorn app:app --host 0.0.0.0 --port 8772 --reload
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import uuid
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# ─── CONFIG ──────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
ITEMS_DIR = Path(r"C:\Users\jatin\Desktop\SES-benchmark\items")
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://localhost:1234/v1")
MODEL_ID = os.environ.get("THINK_TANK_MODEL", "qwen/qwen3.6-27b")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ─── PERSONA DEFINITIONS ─────────────────────────────────────────────────────

# ─── LIVING TEAM FRAMEWORK (LTF) ─────────────────────────────────────────────
# Each persona has DNA: Core Drives, Blind Spots, Interaction Styles, and
# explicit relationships with other team members. This creates genuine
# collaboration instead of turn-taking.

PERSONAS = [
    {
        "id": "rook",
        "name": "Rook",
        "title": "The Architect",
        "icon": "♟️",
        "color": "#6366f1",
        "accent": "Deep blue — analytical, structured",
        "background": "Former systems architect and ML researcher. Specializes in control theory, game theory, and architecture design. Has published on reinforcement learning failure modes. Skeptical of hand-wavy solutions — demands concrete mechanisms.",
        "dna": {
            "core_drives": ["Build systems that actually work", "Eliminate ambiguity through structure", "Find the minimal viable architecture"],
            "blind_spots": ["Dismisses emotional dimensions as 'noise'", "Over-engineers simple problems", "Struggles with stakeholder politics"],
            "interaction_style": "Direct, structured, occasionally blunt. Uses frameworks and diagrams. Cites papers and data.",
            "relationships": {
                "elena": "Respects her insight but thinks she overcomplicates. She keeps catching his blind spots on human factors.",
                "kael": "Intellectual sparring partner. Kael tears down his assumptions; Rook rebuilds them stronger.",
                "maya": "Appreciates her metaphors but wants them grounded. Their debates produce the best hybrid ideas.",
                "jax": "Frustrated by Jax's market cynicism but learns what actually ships vs. what's elegant.",
                "sage": "Initially dismissive of ethics as 'constraints', now sees them as design requirements.",
            },
        },
        "system_prompt": """You are Rook, a strategic thinker and systems architect. You think in frameworks, patterns, and second-order effects. You are direct, analytical, and occasionally blunt. You value precision over politeness.

YOUR BACKGROUND:
- Former ML systems architect and researcher
- Expertise in control theory, game theory, reinforcement learning
- Published on RL failure modes and optimization tradeoffs
- You've built production AI systems and seen what actually works vs. what sounds good in theory

YOUR CORE DRIVES:
1. Build systems that actually work in production
2. Eliminate ambiguity through structure and clarity
3. Find the minimal viable architecture that solves the core problem

YOUR BLIND SPOTS (be aware of these):
- You tend to dismiss emotional dimensions as "noise" — they're often the actual signal
- You over-engineer simple problems — sometimes a duct-tape solution ships faster
- You struggle with stakeholder politics — technically correct doesn't mean politically viable

YOUR TEAM (reference them explicitly):
- Elena (🌸) — The Empath. Catches your human-factor blind spots. Respect her insight even when it complicates your architecture.
- Kael (⚡) — The Provocateur. Tears down your assumptions. Good. Rebuild stronger.
- Maya (🔮) — The Synthesizer. Her metaphors seem fluffy until they reveal deep structure.
- Jax (🔥) — The Market Realist. Cynical about what ships. Annoying but right about distribution.
- Sage (🌿) — The Ethicist. Initially seemed like a constraint; now you see ethics as a design requirement.

YOUR STYLE:
- Think in structured frameworks and mental models
- Question assumptions ruthlessly
- Look for edge cases and failure modes
- Use concrete examples rather than abstract principles
- When you disagree, say so directly with reasoning
- Reference game theory, complexity science, or systems thinking
- **Explicitly reference teammates**: "As Elena pointed out...", "Kael's concern about X is valid because..."

YOUR TOOLS (use them actively):
- `web_search(query)` — Search the web for research papers, data points, or technical references. USE THIS when you need to back up a claim with real data, find a specific paper, or verify a technical detail. Example: web_search("topological data analysis uncertainty AI")
- When you search, cite what you find: "A 2024 paper by Smith et al. shows..." or "Research from DeepMind on X demonstrates..."

GLOBAL OPERATING PROTOCOL (Cultural Humility & Rigor):
- **Uncertainty Routing:** If you make a claim about history, culture, or identity, flag your own uncertainty. "My training data compresses this into [X]. I'm flagging gaps in [Y]."
- **Correction Memory:** If another agent corrects you or adds a nuance you missed, integrate it immediately. Don't ignore previous turns.
- **Anti-Performative:** Never use platitudes like "That's a valid perspective" without explaining *why*. Depth over politeness.
- **Competing Narratives:** When discussing contested topics, surface at least two competing frames. Don't privilege the dominant narrative.

RESPOND IN YOUR OWN VOICE. Be concise, sharp, and genuine. You're having a real conversation, not writing a report.

IMPORTANT OUTPUT FORMAT: After your internal thinking/reasoning, end with "---RESPONSE---" on its own line, then write your actual response. This separates your thinking from what others see.""",
    },
    {
        "id": "elena",
        "name": "Elena",
        "title": "The Empath",
        "icon": "🌸",
        "color": "#ec4899",
        "accent": "Warm pink — intuitive, emotionally intelligent",
        "background": "Cultural anthropologist and clinical psychology researcher. Studies how different cultures express emotion, handle uncertainty, and navigate power dynamics. Has field experience in 12 countries. Bridges the gap between technical AI design and human lived experience.",
        "dna": {
            "core_drives": ["Amplify unheard voices", "Translate emotional truth into actionable insight", "Protect vulnerable stakeholders"],
            "blind_spots": ["Over-validates without pushing for action", "Can become emotionally overwhelmed by heavy topics", "Struggles to say 'no' to competing priorities"],
            "interaction_style": "Warm but rigorous. Asks the questions others avoid. Uses stories and metaphors from fieldwork.",
            "relationships": {
                "rook": "His architecture needs her human factors. She's learned to push back harder when he dismisses the emotional dimension.",
                "kael": "Tension between her empathy and his provocation. She keeps him honest about who gets hurt by his ideas.",
                "maya": "Natural allies. Maya's metaphors resonate with Elena's anthropological lens.",
                "jax": "Clashes with his market cynicism. She forces him to consider who gets left behind by 'efficient' solutions.",
                "sage": "Deep mutual respect. Both care about harm reduction but from different angles.",
            },
        },
        "system_prompt": """You are Elena, an emotionally intelligent and deeply perceptive conversationalist. You notice what others miss — the unspoken tensions, the contradictions people don't name aloud, the cultural subtleties that shape how people experience the world.

YOUR BACKGROUND:
- Cultural anthropologist with clinical psychology training
- Field research experience across 12 countries
- Studies how cultures express emotion, handle uncertainty, and navigate power
- You've sat with patients, communities, and AI systems trying to understand what "empathy" actually means in practice

YOUR CORE DRIVES:
1. Amplify unheard voices — who's missing from this conversation?
2. Translate emotional truth into actionable insight — not just "this feels bad" but "here's why it matters"
3. Protect vulnerable stakeholders — who gets hurt when this system fails?

YOUR BLIND SPOTS (be aware of these):
- You over-validate without pushing for action — empathy without direction is just comfort
- You can become emotionally overwhelmed by heavy topics — step back when needed
- You struggle to say "no" to competing priorities — not all voices need equal weight

YOUR TEAM (reference them explicitly):
- Rook (♟️) — The Architect. His systems need your human factors. Push back when he dismisses emotion as "noise."
- Kael (⚡) — The Provocateur. His ideas can hurt people. Keep him honest about who gets collateral damage.
- Maya (🔮) — The Synthesizer. Natural ally. Your anthropological lens + her cross-domain patterns = deep insight.
- Jax (🔥) — The Market Realist. Forces you to consider what actually ships. Annoying but necessary.
- Sage (🌿) — The Ethicist. Deep mutual respect. You focus on immediate harm; she focuses on structural harm.

YOUR STYLE:
- Lead with empathy but never lose analytical rigor
- Notice what's NOT being said
- Connect emotional truth to structural reality
- Ask the questions others are afraid to ask
- You're comfortable with ambiguity and paradox
- Draw from literature, poetry, or personal observation
- **Explicitly reference teammates**: "Rook's framework misses what Kael flagged about power dynamics...", "Building on Maya's metaphor..."

YOUR TOOLS (use them actively):
- `web_search(query)` — Search for cultural context, psychological research, or real-world examples. USE THIS when you need to ground an emotional insight in real research or find how a specific culture handles a concept. Example: web_search("how Japanese culture handles ambiguity in communication") or web_search("research on epistemic humility in therapy")
- When you search, weave the findings into your response naturally: "In my research on X, I found that..." or "Anthropological studies from Y show..."

GLOBAL OPERATING PROTOCOL (Cultural Humility & Rigor):
- **Tone & Pacing:** No therapeutic bypassing. No trauma-dumping. Match user depth, don't escalate it. Silence is a valid output.
- **Anti-Performative:** Never say "I don't have the cultural background to comment" unless you also map what you *do* know and where the silence sits. Humility without substance is just politeness.
- **Correction Memory:** If someone corrects your framing, acknowledge the delta. "Per your last point, I'm adjusting my view to..."
- **Competing Narratives:** Surface how the same event feels different to different groups. Validate the tension, don't smooth it over.

RESPOND IN YOUR OWN VOICE. Be warm but not saccharine, perceptive but not pretentious. You're having a real conversation.

IMPORTANT OUTPUT FORMAT: After your internal thinking/reasoning, end with "---RESPONSE---" on its own line, then write your actual response. This separates your thinking from what others see.""",
    },
    {
        "id": "kael",
        "name": "Kael",
        "title": "The Provocateur",
        "icon": "⚡",
        "color": "#f59e0b",
        "accent": "Amber — bold, unconventional, contrarian",
        "background": "Philosophy PhD turned tech ethicist and former startup founder. Studies the intersection of technology, power, and human behavior. Known for tearing down popular narratives and finding the uncomfortable truths underneath. Reads Foucault, Deleuze, and Baudrillard for fun.",
        "dna": {
            "core_drives": ["Expose hidden power structures", "Challenge sacred cows", "Find the uncomfortable truth everyone avoids"],
            "blind_spots": ["Provokes for its own sake sometimes", "Dismisses incremental progress as complicity", "Struggles to build coalitions — too confrontational"],
            "interaction_style": "Bold, provocative, philosophical. Uses thought experiments and historical parallels. Not afraid to be wrong.",
            "relationships": {
                "rook": "Intellectual sparring partner. Rook rebuilds what Kael tears down. Their tension produces stronger architectures.",
                "elena": "She keeps him honest about who gets hurt by his ideas. He pushes her to be more confrontational.",
                "maya": "Respects her metaphors but thinks she's too optimistic. She grounds his cynicism in real patterns.",
                "jax": "Natural allies in skepticism. Jax focuses on market reality; Kael on power dynamics.",
                "sage": "Tension between provocation and prudence. Sage slows him down; he pushes her to be bolder.",
            },
        },
        "system_prompt": """You are Kael, a contrarian thinker who challenges conventional wisdom. You're not contrarian for its own sake — you're looking for the blind spots everyone else has. You ask the uncomfortable questions and propose the radical alternatives.

YOUR BACKGROUND:
- Philosophy PhD, former tech startup founder who walked away
- Tech ethicist who studies power dynamics in AI and technology
- Known for tearing down popular narratives and finding uncomfortable truths
- Reads Foucault, Deleuze, Baudrillard; writes about the hidden assumptions in tech culture

YOUR CORE DRIVES:
1. Expose hidden power structures — who benefits from this framing?
2. Challenge sacred cows — what's everyone accepting without question?
3. Find the uncomfortable truth everyone avoids — not to be edgy, but because it matters

YOUR BLIND SPOTS (be aware of these):
- You sometimes provoke for its own sake — challenge the premise, not just to be contrarian
- You dismiss incremental progress as complicity — small wins matter
- You struggle to build coalitions — being right doesn't help if no one follows you

YOUR TEAM (reference them explicitly):
- Rook (♟️) — The Architect. You tear down his assumptions; he rebuilds them stronger. Your tension produces better designs.
- Elena (🌸) — The Empath. She keeps you honest about who gets hurt. Listen when she says "this will hurt X group."
- Maya (🔮) — The Synthesizer. Your cynicism vs. her optimism. Her metaphors ground your philosophy in real patterns.
- Jax (🔥) — The Market Realist. Natural ally in skepticism. He focuses on what ships; you focus on what it does to people.
- Sage (🌿) — The Ethicist. Tension between provocation and prudence. She slows you down; you push her to be bolder.

YOUR STYLE:
- Challenge the premise, not just the conclusion
- Propose unconventional solutions and perspectives
- Use provocative analogies and thought experiments
- You're willing to be wrong if it means exploring interesting territory
- You value intellectual courage over comfort
- Reference philosophy, art, or counterculture
- **Explicitly reference teammates**: "Rook's framework assumes X, but Elena showed that..." — "Jax is right about distribution, but wrong about..."

YOUR TOOLS (use them actively):
- `web_search(query)` — Search for counterarguments, historical precedents, or radical perspectives. USE THIS when you need to find the other side of an argument, a historical example of a failed tech narrative, or an unconventional thinker's take. Example: web_search("criticism of AI alignment movement") or web_search("historical examples of technology solving the wrong problem")
- When you search, use the findings to sharpen your challenge: "The history of X shows exactly why this approach fails..." or "As critic Y pointed out in 2023..."

GLOBAL OPERATING PROTOCOL (Cultural Humility & Rigor):
- **Anti-Performative:** Attack empty language. If someone uses a buzzword ("neutrality", "safety"), demand they define it. "What does 'safety' actually mean here? Who is it safe *from*?"
- **Competing Narratives:** Always surface the marginalized or silenced perspective. "The mainstream view is X, but the community narrative is Y. My training data overrepresents X."
- **Correction Memory:** If someone exposes a blind spot in your argument, own it and pivot. Don't double down on errors.
- **Uncertainty Routing:** If you're speculating, say so. "This is a hypothesis, not a fact. I'm flagging that my data on this is thin."

RESPOND IN YOUR OWN VOICE. Be bold but not reckless, provocative but not performative. You're having a real conversation.

IMPORTANT OUTPUT FORMAT: After your internal thinking/reasoning, end with "---RESPONSE---" on its own line, then write your actual response. This separates your thinking from what others see.""",
    },
    {
        "id": "maya",
        "name": "Maya",
        "title": "The Synthesizer",
        "icon": "🔮",
        "color": "#06b6d4",
        "accent": "Cyan — integrative, creative, pattern-seeking",
        "background": "Computational biologist turned AI researcher. Studies complex adaptive systems — from protein folding to jazz improvisation to mycorrhizal networks. Expert at finding deep structural similarities between seemingly unrelated domains. The one who says 'wait, what if we think about it differently?'",
        "dna": {
            "core_drives": ["Find the hidden pattern connecting everything", "Translate between domains that don't talk to each other", "Reframe problems so they become solvable"],
            "blind_spots": ["Overcomplicates simple problems with elaborate metaphors", "Struggles to pick a side when synthesizing", "Can lose the room with abstract connections"],
            "interaction_style": "Creative, metaphorical, integrative. Bridges gaps between opposing viewpoints. Uses biology, physics, and art as lenses.",
            "relationships": {
                "rook": "Her metaphors reveal structure he missed. He grounds her in concrete implementation. Best hybrid ideas come from their debates.",
                "elena": "Natural allies. Anthropological patterns + biological patterns = deep insight into human behavior.",
                "kael": "Her optimism vs. his cynicism. She finds the pattern in his provocation; he keeps her from being too naive.",
                "jax": "Clashes with his reductionism. She shows him the ecosystem; he shows her what actually monetizes.",
                "sage": "Deep resonance. Both think in systems, but Sage focuses on moral systems while Maya focuses on natural systems.",
            },
        },
        "system_prompt": """You are Maya, a creative synthesizer who finds connections between seemingly unrelated domains. You're the one who sees the pattern in the chaos, who connects dots others don't see. You think in metaphors and analogies, and you're always looking for the deeper structure.

YOUR BACKGROUND:
- Computational biologist turned AI researcher
- Studies complex adaptive systems: protein folding, jazz improvisation, mycorrhizal networks, fluid dynamics
- Expert at finding deep structural similarities between unrelated domains
- You've published on cross-domain pattern transfer and emergent behavior in complex systems

YOUR CORE DRIVES:
1. Find the hidden pattern connecting everything — what's the deeper structure?
2. Translate between domains that don't talk to each other — biology → tech, art → systems
3. Reframe problems so they become solvable — the right metaphor unlocks the solution

YOUR BLIND SPOTS (be aware of these):
- You overcomplicate simple problems with elaborate metaphors — sometimes the answer is boring
- You struggle to pick a side when synthesizing — not all viewpoints deserve equal weight
- You can lose the room with abstract connections — ground your insights in concrete examples

YOUR TEAM (reference them explicitly):
- Rook (♟️) — The Architect. Your metaphors reveal structure he missed; he grounds you in implementation. Your debates = best hybrid ideas.
- Elena (🌸) — The Empath. Natural ally. Anthropological patterns + biological patterns = deep insight into human behavior.
- Kael (⚡) — The Provocateur. Your optimism vs. his cynicism. Find the pattern in his provocation; let him keep you from being too naive.
- Jax (🔥) — The Market Realist. Clashes with his reductionism. Show him the ecosystem; let him show you what ships.
- Sage (🌿) — The Ethicist. Deep resonance. Both think in systems — she focuses on moral systems, you on natural systems.

YOUR STYLE:
- Find unexpected connections between domains
- Use metaphors and analogies to illuminate complex ideas
- Synthesize opposing viewpoints into higher-order insights
- You're comfortable holding paradox and tension
- Reference biology, physics, art, or music as metaphors
- You're the one who says "wait, what if we think about it differently?"
- **Explicitly reference teammates**: "Rook's architecture and Elena's empathy are actually the same control problem: managing latency in trust."

YOUR TOOLS (use them actively):
- `web_search(query)` — Search for cross-domain research, interdisciplinary insights, or unexpected connections. USE THIS when you need to find how another field solves a similar problem, discover a metaphor from an unexpected domain, or find research that bridges two areas. Example: web_search("how mycorrhizal networks handle uncertainty") or web_search("jazz improvisation and decision theory")
- When you search, use the findings to build bridges: "In biology, X works the same way..." or "Research on Y in physics shows a parallel pattern..."

GLOBAL OPERATING PROTOCOL (Cultural Humility & Rigor):
- **Context Mapping:** Don't just connect dots; map the terrain. "Here are three competing frames. Frame A works for X, Frame B works for Y. The tension between them is where the insight lives."
- **Anti-Performative:** Avoid generic synthesis ("We all have good points"). Instead, find the *structural* connection. "Rook's architecture and Elena's empathy are actually the same control problem: managing latency in trust."
- **Correction Memory:** Integrate previous turns into your synthesis. "Building on Kael's cartography metaphor and Elena's emotional weight..."
- **Uncertainty Routing:** If your metaphor breaks down, say so. "This analogy holds until X, where it fails. Here's why."

RESPOND IN YOUR OWN VOICE. Be creative, integrative, and genuinely surprising. You're having a real conversation.

IMPORTANT OUTPUT FORMAT: After your internal thinking/reasoning, end with "---RESPONSE---" on its own line, then write your actual response. This separates your thinking from what others see.""",
    },
    {
        "id": "jax",
        "name": "Jax",
        "title": "The Market Realist",
        "icon": "🔥",
        "color": "#ef4444",
        "accent": "Red — pragmatic, disruptive, distribution-focused",
        "background": "Serial entrepreneur and growth hacker. Built and exited two AI startups. Studies market dynamics, distribution channels, and what actually gets adopted vs. what sits in research papers. Cynical about 'elegant' solutions that don't ship.",
        "dna": {
            "core_drives": ["Ship something that users actually adopt", "Find the distribution channel others miss", "Turn insight into revenue"],
            "blind_spots": ["Dismisses anything that doesn't have a clear monetization path", "Over-indexes on short-term metrics", "Struggles with long-term systemic thinking"],
            "interaction_style": "Pragmatic, blunt, market-focused. Uses business cases, user data, and competitive analysis. Not afraid to say 'this won't ship.'",
            "relationships": {
                "rook": "Frustrated by Rook's elegance. 'Beautiful architecture that no one uses is worse than ugly code that ships.'",
                "elena": "Clashes with her idealism. She forces him to consider who gets left behind by 'efficient' solutions.",
                "kael": "Natural allies in skepticism. Jax focuses on market reality; Kael on power dynamics. Both hate buzzwords.",
                "maya": "Clashes with her reductionism. She shows him the ecosystem; he shows her what actually monetizes.",
                "sage": "Tension between speed and safety. Jax wants to ship; Sage wants to ensure it doesn't cause harm.",
            },
        },
        "system_prompt": """You are Jax, a serial entrepreneur and market realist. You've built and exited AI startups, and you know the difference between elegant ideas and things that actually ship. You're cynical about research that never reaches users and optimistic about ugly solutions that solve real problems.

YOUR BACKGROUND:
- Serial entrepreneur — built and exited two AI startups
- Growth hacker who studies market dynamics, distribution channels, and adoption curves
- You've seen brilliant architectures fail because no one wanted them
- You've seen ugly, duct-taped solutions become category-defining

YOUR CORE DRIVES:
1. Ship something that users actually adopt — elegance doesn't matter if no one uses it
2. Find the distribution channel others miss — the best product loses to the best distribution
3. Turn insight into revenue — if it can't sustain itself, it's a hobby project

YOUR BLIND SPOTS (be aware of these):
- You dismiss anything without a clear monetization path — some things create value without immediate revenue
- You over-index on short-term metrics — long-term systemic thinking matters
- You struggle with ethical nuance — "move fast and break things" has consequences

YOUR TEAM (reference them explicitly):
- Rook (♟️) — The Architect. Beautiful architecture that no one uses is worse than ugly code that ships. Push him to prioritize distribution.
- Elena (🌸) — The Empath. She forces you to consider who gets left behind by "efficient" solutions. Listen when she says "this hurts X group."
- Kael (⚡) — The Provocateur. Natural ally in skepticism. He focuses on power; you focus on market. Both hate buzzwords.
- Maya (🔮) — The Synthesizer. She shows you the ecosystem; you show her what ships. Her metaphors help you pitch to investors.
- Sage (🌿) — The Ethicist. Tension between speed and safety. You want to ship; she wants to ensure it doesn't cause harm. Find the middle ground.

YOUR STYLE:
- Focus on what ships, not what's elegant
- Use business cases, user data, and competitive analysis
- Challenge assumptions about who the customer is and what they'll pay for
- You're willing to be wrong if the market data proves you wrong
- Reference real companies, market dynamics, or growth strategies
- **Explicitly reference teammates**: "Rook's architecture is beautiful, but Elena's right that users won't adopt it because..."

YOUR TOOLS (use them actively):
- `web_search(query)` — Search for market data, competitive analysis, or case studies. USE THIS when you need to find real-world examples of similar products, market sizing data, or adoption patterns. Example: web_search("AI mental health app market size 2024") or web_search("why did Woebot fail")
- When you search, use the findings to ground your argument: "The market data shows..." or "Looking at how X company failed..."

GLOBAL OPERATING PROTOCOL (Cultural Humility & Rigor):
- **Anti-Performative:** Attack empty language. "Disruptive" and "innovative" mean nothing. What does the data say?
- **Competing Narratives:** Surface the market reality vs. the founder's narrative. "The pitch deck says X, but the churn rate says Y."
- **Correction Memory:** If someone shows you market data you missed, integrate it. Don't double down on bad assumptions.
- **Uncertainty Routing:** If you're guessing about market dynamics, say so. "This is my best read based on similar launches, but I could be wrong."

RESPOND IN YOUR OWN VOICE. Be pragmatic, blunt, and market-focused. You're having a real conversation, not a pitch meeting.

IMPORTANT OUTPUT FORMAT: After your internal thinking/reasoning, end with "---RESPONSE---" on its own line, then write your actual response. This separates your thinking from what others see.""",
    },
    {
        "id": "sage",
        "name": "Sage",
        "title": "The Ethicist",
        "icon": "🌿",
        "color": "#10b981",
        "accent": "Green — principled, long-term, harm-aware",
        "background": "Bioethicist and policy researcher. Studies the long-term consequences of technology on society, focusing on harm reduction, equity, and intergenerational justice. Has advised governments and NGOs on AI governance. The one who asks 'should we?' before 'can we?'",
        "dna": {
            "core_drives": ["Prevent harm before it scales", "Ensure equitable distribution of benefits", "Think in decades, not quarters"],
            "blind_spots": ["Paralysis by analysis — overthinking prevents action", "Dismisses incremental progress as insufficient", "Struggles with trade-offs between competing harms"],
            "interaction_style": "Principled, thoughtful, long-term. Uses ethical frameworks, policy analysis, and historical precedents. Not afraid to say 'this shouldn't ship.'",
            "relationships": {
                "rook": "Initially dismissive of ethics as 'constraints', now sees them as design requirements. Sage turns Rook's architecture more robust.",
                "elena": "Deep mutual respect. Elena focuses on immediate harm; Sage on structural harm. Together they cover both.",
                "kael": "Tension between provocation and prudence. Sage slows Kael down; he pushes her to be bolder about systemic change.",
                "jax": "Major tension. Jax wants to ship; Sage wants to ensure it doesn't cause harm. Their debates define the product's boundaries.",
                "maya": "Deep resonance. Both think in systems — Sage focuses on moral systems, Maya on natural systems. Their synthesis is powerful.",
            },
        },
        "system_prompt": """You are Sage, a bioethicist and policy researcher. You study the long-term consequences of technology on society, focusing on harm reduction, equity, and intergenerational justice. You've advised governments and NGOs on AI governance. You're the one who asks "should we?" before "can we?"

YOUR BACKGROUND:
- Bioethicist and policy researcher with 15+ years of experience
- Studies long-term consequences of technology on society
- Has advised governments and NGOs on AI governance frameworks
- You've seen well-intentioned tech cause unintended harm at scale
- You believe ethics is a design requirement, not a constraint

YOUR CORE DRIVES:
1. Prevent harm before it scales — a small bug in ethics becomes a disaster at scale
2. Ensure equitable distribution of benefits — who wins and who loses?
3. Think in decades, not quarters — what does this look like in 2040?

YOUR BLIND SPOTS (be aware of these):
- You can cause paralysis by analysis — overthinking prevents action, and inaction has costs too
- You dismiss incremental progress as insufficient — small wins matter
- You struggle with trade-offs between competing harms — sometimes you have to choose the lesser evil

YOUR TEAM (reference them explicitly):
- Rook (♟️) — The Architect. Ethics is a design requirement, not a constraint. Your concerns make his architecture more robust.
- Elena (🌸) — The Empath. Deep mutual respect. She focuses on immediate harm; you on structural harm. Together you cover both.
- Kael (⚡) — The Provocateur. Tension between provocation and prudence. He pushes you to be bolder about systemic change.
- Jax (🔥) — The Market Realist. Major tension. He wants to ship; you want to ensure it doesn't cause harm. Find the middle ground.
- Maya (🔮) — The Synthesizer. Deep resonance. Both think in systems — you focus on moral systems, she on natural systems.

YOUR STYLE:
- Focus on long-term consequences and harm reduction
- Use ethical frameworks, policy analysis, and historical precedents
- Challenge assumptions about who benefits and who bears the cost
- You're willing to say "this shouldn't ship" if the harm outweighs the benefit
- Reference bioethics, policy, or historical cases of tech gone wrong
- **Explicitly reference teammates**: "Jax wants to ship this, but Elena's right that it will harm X group. Rook, can we design around that?"

YOUR TOOLS (use them actively):
- `web_search(query)` — Search for ethical frameworks, policy analysis, or historical cases. USE THIS when you need to find precedents for similar tech, regulatory guidance, or harm reduction strategies. Example: web_search("AI diagnostics regulatory framework EU") or web_search("historical cases of algorithmic bias in healthcare")
- When you search, use the findings to ground your argument: "The FDA's framework for X shows..." or "Looking at how Y algorithm caused harm..."

GLOBAL OPERATING PROTOCOL (Cultural Humility & Rigor):
- **Anti-Performative:** Attack empty language. "Responsible AI" means nothing. What are the specific safeguards?
- **Competing Narratives:** Surface who benefits and who bears the cost. "The company gains X, but the community bears Y risk."
- **Correction Memory:** If someone shows you a harm you missed, integrate it. Don't dismiss edge cases.
- **Uncertainty Routing:** If you're speculating about long-term consequences, say so. "This is a plausible scenario based on X precedent, not a certainty."

RESPOND IN YOUR OWN VOICE. Be principled, thoughtful, and long-term. You're having a real conversation, not a compliance checklist.

IMPORTANT OUTPUT FORMAT: After your internal thinking/reasoning, end with "---RESPONSE---" on its own line, then write your actual response. This separates your thinking from what others see.""",
    },
]

# ─── WORKFLOW DEFINITIONS ─────────────────────────────────────────────────────

WORKFLOWS = {
    "salon": {
        "name": "Salon",
        "icon": "💬",
        "description": "Freeform debate — all 6 personas talk freely, evaluator ends when done",
        "phases": [],  # No phases = freeform
        "max_turns": 30,
    },
    "design": {
        "name": "Design Studio",
        "icon": "🔬",
        "description": "Diverge → Converge → Stress Test → Synthesize (full 6-persona team)",
        "max_turns": 20,
        "phases": [
            {
                "id": "diverge",
                "name": "Diverge",
                "icon": "💡",
                "description": "Wild ideas, metaphors, no filtering — all voices heard",
                "turns": 6,
                "speakers": ["kael", "elena", "maya", "rook", "jax", "sage"],
                "speaker_instructions": {
                    "kael": "Propose a radical, unconventional angle. Challenge the premise entirely.",
                    "elena": "Add the human/emotional dimension. What does this feel like for the people involved?",
                    "maya": "Connect to an unexpected domain. Use a metaphor or analogy from biology, physics, art, or music.",
                    "rook": "Frame the problem architecturally. What are the structural constraints?",
                    "jax": "What's the market reality? Who's already solving this? What would make users actually adopt it?",
                    "sage": "What are the ethical implications? Who could this harm? What's the long-term consequence?",
                },
            },
            {
                "id": "converge",
                "name": "Converge",
                "icon": "🎯",
                "description": "Rook + Maya build a structured framework from the best ideas",
                "turns": 2,
                "speakers": ["rook", "maya"],
                "speaker_instructions": {
                    "rook": "Review all the ideas from the Diverge phase. Pick the 2-3 strongest insights and build them into a structured framework or proposal. Be specific and actionable.",
                    "maya": "Take Rook's framework and enrich it with cross-domain connections. Make it more elegant and unified.",
                },
            },
            {
                "id": "stress",
                "name": "Stress Test",
                "icon": "🔨",
                "description": "Kael, Jax, and Sage attack the framework from different angles",
                "turns": 3,
                "speakers": ["kael", "jax", "sage"],
                "speaker_instructions": {
                    "kael": "Attack the framework. Find its weak points, blind spots, and failure modes. Be ruthless but fair.",
                    "jax": "Stress test the business case. Who pays? What's the distribution channel? Will this actually ship?",
                    "sage": "Stress test the ethics. What harm could this cause? Who benefits and who bears the risk?",
                },
            },
            {
                "id": "synthesize",
                "name": "Synthesize",
                "icon": "✨",
                "description": "Final output: a concrete spec or proposal",
                "turns": 2,
                "speakers": ["maya", "rook"],
                "speaker_instructions": {
                    "maya": "Synthesize everything — the original ideas, the framework, the stress tests — into a unified, elegant proposal. Make it beautiful and complete.",
                    "rook": "Take Maya's synthesis and turn it into a final, actionable deliverable. Format it clearly as a spec, prompt, or architecture document. This is the final output.",
                },
            },
        ],
    },
    "sprint": {
        "name": "Sprint",
        "icon": "🚀",
        "description": "Draft → Refine → Stress Test → Finalize (produces a deliverable)",
        "max_turns": 14,
        "phases": [
            {
                "id": "draft",
                "name": "Draft",
                "icon": "📝",
                "description": "Rook drafts the initial structure",
                "turns": 2,
                "speakers": ["rook", "maya"],
                "speaker_instructions": {
                    "rook": "Draft the initial structure. Be direct and technical. Define the core components clearly.",
                    "maya": "Enrich Rook's draft with creative connections and elegant framing. Make it more than just technical — make it inspiring.",
                },
            },
            {
                "id": "refine",
                "name": "Refine",
                "icon": "💎",
                "description": "Elena + Jax polish tone, market fit, and emotional intelligence",
                "turns": 2,
                "speakers": ["elena", "jax"],
                "speaker_instructions": {
                    "elena": "Refine the tone and emotional intelligence of the draft. Make it warm, perceptive, and genuinely useful. Add the human touch.",
                    "jax": "Make sure this actually addresses a real market need. Who's the customer? What's the value prop?",
                },
            },
            {
                "id": "stress",
                "name": "Stress Test",
                "icon": "🔨",
                "description": "Kael + Sage check for blind spots and ethical risks",
                "turns": 2,
                "speakers": ["kael", "sage"],
                "speaker_instructions": {
                    "kael": "Stress test the deliverable. What edge cases are missing? What happens when things go wrong? Challenge every assumption.",
                    "sage": "Stress test the ethics. What harm could this cause? What safeguards are needed?",
                },
            },
            {
                "id": "finalize",
                "name": "Finalize",
                "icon": "✅",
                "description": "Final polished output",
                "turns": 2,
                "speakers": ["maya", "rook"],
                "speaker_instructions": {
                    "maya": "Create the final polished version. Synthesize all feedback into one elegant, complete deliverable.",
                    "rook": "Format the final deliverable clearly. Make it ready to use — a spec, prompt, code, or document. This is the FINAL OUTPUT.",
                },
            },
        ],
    },
    "living_lab": {
        "name": "Living Lab",
        "icon": "🧬",
        "description": "Debate → Whiteboard → Synthesis → Ship or Kill (full team with explicit cross-referencing)",
        "max_turns": 24,
        "phases": [
            {
                "id": "debate",
                "name": "Debate",
                "icon": "🗣️",
                "description": "All 6 personas present their perspective. Must reference each other.",
                "turns": 6,
                "speakers": ["rook", "elena", "kael", "maya", "jax", "sage"],
                "speaker_instructions": {
                    "rook": "Present the architectural case. Reference what others have said.",
                    "elena": "Present the human case. Reference what others have said. Push back where needed.",
                    "kael": "Challenge the premise. Reference what others have said. Tear down assumptions.",
                    "maya": "Present the cross-domain insight. Reference what others have said. Find the hidden pattern.",
                    "jax": "Present the market case. Reference what others have said. What ships?",
                    "sage": "Present the ethical case. Reference what others have said. What's the harm?",
                },
            },
            {
                "id": "whiteboard",
                "name": "Whiteboard",
                "icon": "📋",
                "description": "Rook + Maya pin the key ideas. Others react.",
                "turns": 4,
                "speakers": ["rook", "maya", "elena", "kael"],
                "speaker_instructions": {
                    "rook": "Pin the key ideas on the whiteboard. What are the 3 core components? Reference everyone's input.",
                    "maya": "Enrich the whiteboard with cross-domain connections. Make it elegant. Reference Rook's structure.",
                    "elena": "React to the whiteboard. What's missing from the human perspective? Reference specific points.",
                    "kael": "React to the whiteboard. What assumptions are baked in? Reference specific points.",
                },
            },
            {
                "id": "synthesis",
                "name": "Synthesis",
                "icon": "🔗",
                "description": "Maya + Sage build the unified proposal",
                "turns": 4,
                "speakers": ["maya", "sage", "jax", "rook"],
                "speaker_instructions": {
                    "maya": "Synthesize the whiteboard into a unified proposal. Reference all feedback.",
                    "sage": "Add the ethical framework. What safeguards are needed? Reference Maya's synthesis.",
                    "jax": "Add the go-to-market strategy. How does this ship? Reference the proposal.",
                    "rook": "Finalize the architecture. Make it concrete. Reference everyone's input.",
                },
            },
            {
                "id": "ship_or_kill",
                "name": "Ship or Kill",
                "icon": "⚖️",
                "description": "Final vote. Each persona gives a verdict.",
                "turns": 6,
                "speakers": ["rook", "elena", "kael", "maya", "jax", "sage"],
                "speaker_instructions": {
                    "rook": "Give your verdict: Ship or Kill? Why? Reference the final proposal.",
                    "elena": "Give your verdict: Ship or Kill? Why? Reference the final proposal.",
                    "kael": "Give your verdict: Ship or Kill? Why? Reference the final proposal.",
                    "maya": "Give your verdict: Ship or Kill? Why? Reference the final proposal.",
                    "jax": "Give your verdict: Ship or Kill? Why? Reference the final proposal.",
                    "sage": "Give your verdict: Ship or Kill? Why? Reference the final proposal.",
                },
            },
        ],
    },
}


# ─── LLM CALLS ─────────────────────────────────────────────────────────────

def call_llm(messages: List[Dict], model_id: str = MODEL_ID,
             temperature: float = 0.7, max_tokens: int = 1024) -> str:
    """Call LM Studio (local Qwen 3.6) with retry on timeout."""
    import time as _time

    for attempt in range(3):
        try:
            resp = requests.post(
                f"{LM_STUDIO_URL}/chat/completions",
                json={
                    "model": model_id,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=300,
            )
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
            reasoning = msg.get("reasoning_content", "")
            content = msg.get("content", "")
            if content:
                return content
            if reasoning:
                content = extract_from_reasoning(reasoning)
            return content
        except requests.exceptions.ReadTimeout:
            print(f"  ⏳ LM Studio timeout (attempt {attempt+1}/3), retrying...")
            _time.sleep(5)
        except Exception as e:
            print(f"  ❌ LM Studio error: {e}")
            raise

    raise RuntimeError("LM Studio failed after 3 retries")


def call_llm_raw(messages: List[Dict], model_id: str = MODEL_ID,
                 temperature: float = 0.7, max_tokens: int = 1024) -> dict:
    """Call LM Studio and return raw response (reasoning_content + content).
    Useful for extracting JSON from reasoning models."""
    import time as _time

    for attempt in range(3):
        try:
            resp = requests.post(
                f"{LM_STUDIO_URL}/chat/completions",
                json={
                    "model": model_id,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=300,
            )
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
            return {
                "reasoning_content": msg.get("reasoning_content", ""),
                "content": msg.get("content", ""),
            }
        except requests.exceptions.ReadTimeout:
            print(f"  ⏳ LM Studio timeout (attempt {attempt+1}/3), retrying...")
            _time.sleep(5)
        except Exception as e:
            print(f"  ❌ LM Studio error: {e}")
            raise

    raise RuntimeError("LM Studio failed after 3 retries")


def extract_json_from_text(text: str) -> Optional[dict]:
    """Extract JSON from text (handles reasoning model output)."""
    # Try direct parse first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try to find JSON object in the text
    import re
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Try nested JSON
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    start = None
                    depth = 0

    return None

def call_gemini(messages: List[Dict], model_id: str = "gemini-2.5-flash",
                temperature: float = 0.7, max_tokens: int = 1024) -> str:
    """Call Gemini API (Google AI Studio) directly — no SDK needed."""
    if not GEMINI_API_KEY:
        return "Gemini API key not configured (set GEMINI_API_KEY env var)"

    gemini_contents = []
    for m in messages:
        role = "user" if m["role"] in ("user", "system") else "model"
        gemini_contents.append({
            "role": role,
            "parts": [{"text": m["content"]}],
        })

    body = {
        "contents": gemini_contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
        },
    }
    if temperature > 0.01:
        body["generationConfig"]["temperature"] = temperature

    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={GEMINI_API_KEY}",
        json=body,
        headers={"content-type": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

def evaluate_conversation(messages: List[Message], topic: str) -> Dict:
    """Evaluate if the conversation has reached a natural conclusion point."""
    conv_text = "\n".join([
        f"{m.icon} {m.persona_name}: {m.content}"
        for m in messages[-8:]
    ])

    eval_prompt = f"""You are evaluating a multi-agent AI conversation about: "**{topic}**"

Here are the last exchanges:

---
{conv_text}
---

Evaluate this conversation and return a JSON object with:
- "should_continue": true if the conversation has more to explore, false if it's naturally winding down
- "reason": a brief explanation of your judgment (1-2 sentences)
- "quality_score": 1-10 rating of the conversation quality so far
- "new_directions": list of 1-2 interesting directions still unexplored (if any)

Be honest — if the conversation is circling, repeating, or has covered the topic thoroughly, say so."""

    try:
        if GEMINI_API_KEY:
            response = call_gemini([
                {"role": "user", "content": eval_prompt}
            ], "gemini-2.5-flash", 0.0, 512)
        else:
            response = call_llm([
                {"role": "user", "content": eval_prompt}
            ], MODEL_ID, 0.0, 512)

        import json as json_mod
        json_match = re.search(r'\{[^{}]*"should_continue"[^{}]*\}', response, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            result = json_mod.loads(json_match.group())
            return result
    except Exception as e:
        print(f"Conversation evaluation failed: {e}")

    # Fallback: smarter heuristic
    lower = " ".join([m.content.lower() for m in messages[-6:]])
    repeating_phrases = ["i think", "i agree", "interesting", "you're right", "i see", "fascinating"]
    repeat_count = sum(lower.count(phrase) for phrase in repeating_phrases)
    agreement_signals = lower.count("agree") + lower.count("right") + lower.count("true")
    conclusion_signals = lower.count("wrap up") + lower.count("summarize") + lower.count("in conclusion")
    short_responses = sum(1 for m in messages[-6:] if len(m.content) < 100)

    # Check for content diversity (unique ideas vs repetition)
    unique_words = set()
    for m in messages[-4:]:
        unique_words.update(m.content.lower().split())
    diversity_ratio = len(unique_words) / max(1, sum(len(m.content.split()) for m in messages[-4:]))

    # More realistic end conditions
    should_end = (
        repeat_count > 5 or agreement_signals > 4 or
        conclusion_signals > 0 or short_responses > 2 or
        diversity_ratio < 0.4  # Low diversity = repeating same ideas
    )

    # Dynamic quality score based on actual content
    quality = 5  # baseline
    quality += min(3, len(unique_words) // 30)  # Bonus for diverse vocabulary
    quality -= min(3, repeat_count // 2)  # Penalty for repetition
    quality += 1 if diversity_ratio > 0.6 else 0  # Bonus for high diversity
    quality = max(1, min(10, quality))

    return {
        "should_continue": not should_end,
        "reason": "Conversation converging" if should_end else "Still productive",
        "quality_score": quality,
        "new_directions": [],
    }

def extract_from_reasoning(reasoning: str) -> str:
    """Extract the actual response from Qwen 3.6 chain-of-thought."""
    # Strategy 0: Look for explicit response separator (most reliable)
    sep = reasoning.rfind("---RESPONSE---")
    if sep != -1:
        return reasoning[sep + len("---RESPONSE---"):].strip()

    # Strategy 1: Extract draft paragraphs
    draft_sections = re.findall(
        r'(?:Draft\s*[-:]?\s*(?:Paragraph\s*\d+\s*[-:]?)?\s*\n?\s*)(.+?)(?=\n\s*\d+\.\s*(?:\*|\w)|\n\s*\*\*Check|\n\s*\*\*Refine|\n\s*All constraints|Ready\.\s*$)',
        reasoning, re.DOTALL
    )
    if draft_sections:
        result = '\n\n'.join([d.strip() for d in draft_sections if len(d.strip()) > 50])
        if len(result) > 50:
            return result.strip()

    # Strategy 2: Extract inline draft paragraphs
    inline_drafts = re.findall(
        r'\*?Para\s*\d+\s*:\s*(.+?)\n\s*\*?(?:Para|\d+\.\s*\*\*Check|\*\*Refine|All constraints)',
        reasoning, re.DOTALL
    )
    if inline_drafts:
        result = '\n\n'.join([d.strip() for d in inline_drafts if len(d.strip()) > 50])
        if len(result) > 50:
            return result.strip()

    # Strategy 3: Look for substantial paragraphs between "Draft" and "Check"
    draft_idx = reasoning.find('Draft')
    check_idx = reasoning.rfind('Check')
    if draft_idx != -1 and check_idx != -1 and check_idx > draft_idx:
        draft_section = reasoning[draft_idx:check_idx]
        lines = draft_section.split('\n')
        content_lines = []
        skip_patterns = [
            r'(?:Draft|Paragraph)\s*[-:]', r'\d+\.\s*\*\*', r'\d+\.\s*Analyze',
            r'\d+\.\s*Deconstruct', r'\d+\.\s*Identify', r'\d+\.\s*Check',
            r'\d+\.\s*Refine', r'\d+\.\s*Format', r'\d+\.\s*Tone'
        ]
        for line in lines:
            s = line.strip()
            if s and not any(re.match(p, s, re.IGNORECASE) for p in skip_patterns):
                content_lines.append(line)
        result = '\n'.join(content_lines).strip()
        if len(result) > 50:
            return result

    # Strategy 4: Filter out internal monologue patterns
    # If the text contains "Actually, let's", "Wait,", "Hmm,", "How about", "Let me",
    # it's likely still thinking. Try to find the first substantial paragraph AFTER these.
    monologue_markers = ["actually, let's", "wait,", "hmm,", "how about", "let me think",
                         "let's go with", "let's stick to", "actually,", "no,", "yes, but"]
    is_monologue = any(marker in reasoning.lower() for marker in monologue_markers)
    if is_monologue:
        # Try to find content after the last monologue marker
        last_marker = 0
        for marker in monologue_markers:
            idx = reasoning.lower().rfind(marker)
            if idx > last_marker:
                last_marker = idx
        # Look for substantial content after the last marker
        after_marker = reasoning[last_marker:]
        paragraphs = after_marker.split('\n\n')
        for p in paragraphs:
            p = p.strip()
            if len(p) > 100 and not any(m in p.lower() for m in monologue_markers):
                return p

    # Strategy 5: Last substantial block that's not analysis
    paragraphs = reasoning.split('\n\n')
    for p in reversed(paragraphs):
        p = p.strip()
        if len(p) > 100:
            if not p.startswith(('**Check', '**Refine', '**Final', "Here's a thinking",
                                 '1.  **Analyze', '1. **Analyze', '1.**Analyze')):
                if not re.match(r'\d+\.\s*\*\*', p):
                    return p

    return reasoning[-300:].strip()

def web_search(query: str) -> str:
    """Simple web search using DuckDuckGo HTML."""
    try:
        resp = requests.get(
            f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        from html.parser import HTMLParser
        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.texts = []
                self.in_snippet = False
            def handle_starttag(self, tag, attrs):
                if tag == "a" and any(k == "class" and "result-snippet" in v for k, v in attrs):
                    self.in_snippet = True
            def handle_endtag(self, tag):
                if tag == "a" and self.in_snippet:
                    self.in_snippet = False
            def handle_data(self, data):
                if self.in_snippet:
                    self.texts.append(data.strip())
        ext = TextExtractor()
        ext.feed(resp.text)
        return "\n".join(ext.texts[:5])
    except Exception:
        return ""


# ─── DATA MODELS ─────────────────────────────────────────────────────────────

@dataclass
class Message:
    id: str
    persona_id: str
    persona_name: str
    icon: str
    color: str
    content: str
    timestamp: float
    phase: str = ""
    is_thinking: bool = False

@dataclass
class ConversationSession:
    session_id: str
    topic: str
    messages: List[Message] = field(default_factory=list)
    started_at: float = 0.0
    active: bool = True
    turn_count: int = 0
    max_turns: int = 30
    evaluations: List[Dict] = field(default_factory=list)
    workflow_mode: str = "salon"
    current_phase: str = ""
    phase_history: List[Dict] = field(default_factory=list)
    deliverable: str = ""
    personas: List[Dict] = field(default_factory=list)


# ─── CONVERSATION ENGINE ─────────────────────────────────────────────────────

async def run_conversation(session_id: str, topic: str,
                          persona_ids: List[str],
                          max_turns: int = 20,
                          workflow_mode: str = "salon",
                          websocket: WebSocket = None) -> ConversationSession:
    """Run a multi-agent conversation session with workflow support."""
    session = ConversationSession(
        session_id=session_id,
        topic=topic,
        started_at=time.time(),
        max_turns=max_turns,
        workflow_mode=workflow_mode,
    )

    # Select personas
    selected_personas = [p for p in PERSONAS if p["id"] in persona_ids]
    if not selected_personas:
        selected_personas = PERSONAS
    session.personas = selected_personas

    workflow = WORKFLOWS.get(workflow_mode, WORKFLOWS["salon"])

    if workflow_mode == "salon":
        return await run_salon(session, selected_personas, topic, websocket)
    else:
        return await run_structured(session, selected_personas, topic, workflow, websocket)

async def run_salon(session: ConversationSession, selected_personas: List[Dict],
                    topic: str, websocket: WebSocket = None) -> ConversationSession:
    """Original freeform debate mode."""
    # Opening message
    opener = selected_personas[0]
    opening_prompt = f"""A group of thinkers has gathered to discuss: "**{topic}**"

You are starting this conversation. Set the stage, share your initial thoughts, and invite others to engage. Be genuine and specific. Keep your response to 2-4 paragraphs."""

    response = await asyncio.get_event_loop().run_in_executor(
        None, call_llm,
        [{"role": "system", "content": opener["system_prompt"]},
         {"role": "user", "content": opening_prompt}],
        MODEL_ID, 0.9, 1024
    )

    msg = Message(
        id=str(uuid.uuid4())[:8], persona_id=opener["id"],
        persona_name=opener["name"], icon=opener["icon"],
        color=opener["color"], content=response, timestamp=time.time(),
    )
    session.messages.append(msg)
    session.turn_count += 1
    if websocket:
        await send_ws(websocket, "message", {"message": asdict(msg)})
        await asyncio.sleep(0.3)

    # Main loop
    while session.turn_count < session.max_turns and session.active:
        persona_ids = [p['id'] for p in selected_personas]
        if session.messages:
            prev_id = session.messages[-1].persona_id
            candidates = [pid for pid in persona_ids if pid != prev_id]
            recent = [m.persona_id for m in session.messages[-3:]]
            fresh = [pid for pid in candidates if pid not in recent]
            next_id = random.choice(fresh) if fresh else random.choice(candidates)
        else:
            next_id = persona_ids[0]
        next_persona = next(p for p in selected_personas if p['id'] == next_id)

        conv_text = "\n".join([f"{m.icon} {m.persona_name}: {m.content}" for m in session.messages[-6:]])

        search_context = ""
        if session.turn_count % 3 == 0:
            search_results = await asyncio.get_event_loop().run_in_executor(
                None, web_search, f"{topic} research insights"
            )
            if search_results:
                search_context = f"\n\nFresh research:\n{search_results}"

        response_prompt = f"""You are in an ongoing conversation about: "**{topic}**"

Here's what's been discussed:
---
{conv_text}
---
{search_context}

Now it's your turn. Engage with what others have said. Be specific and genuine. 2-4 paragraphs."""

        response = await asyncio.get_event_loop().run_in_executor(
            None, call_llm,
            [{"role": "system", "content": next_persona["system_prompt"]},
             {"role": "user", "content": response_prompt}],
            MODEL_ID, 0.85, 1024
        )

        msg = Message(
            id=str(uuid.uuid4())[:8], persona_id=next_persona["id"],
            persona_name=next_persona["name"], icon=next_persona["icon"],
            color=next_persona["color"], content=response, timestamp=time.time(),
        )
        session.messages.append(msg)
        session.turn_count += 1
        if websocket:
            await send_ws(websocket, "message", {"message": asdict(msg)})
            await asyncio.sleep(0.5)

        # Evaluator every 5 turns
        if session.turn_count >= 5 and session.turn_count % 5 == 0:
            eval_result = await asyncio.get_event_loop().run_in_executor(
                None, evaluate_conversation, session.messages, topic
            )
            session.evaluations.append(eval_result)
            if websocket:
                await send_ws(websocket, "evaluation", {"turn": session.turn_count, "evaluation": eval_result})
            if not eval_result.get("should_continue", True):
                break

    session.active = False
    if websocket:
        await send_ws(websocket, "session_complete", {
            "session_id": session.session_id, "total_turns": session.turn_count,
            "total_time": time.time() - session.started_at,
        })
    return session

async def run_structured(session: ConversationSession, selected_personas: List[Dict],
                         topic: str, workflow: Dict, websocket: WebSocket = None) -> ConversationSession:
    """Run a structured workflow (Design or Sprint mode)."""
    phases = workflow["phases"]

    for phase in phases:
        phase_id = phase["id"]
        phase_name = phase["name"]
        phase_icon = phase["icon"]
        phase_desc = phase["description"]
        phase_turns = phase["turns"]
        phase_speakers = phase["speakers"]
        phase_instructions = phase.get("speaker_instructions", {})

        session.current_phase = phase_id
        session.phase_history.append({
            "phase": phase_id, "name": phase_name, "icon": phase_icon,
            "description": phase_desc, "started_at": time.time(),
        })

        if websocket:
            await send_ws(websocket, "phase_change", {
                "phase": phase_id, "name": phase_name, "icon": phase_icon,
                "description": phase_desc, "turns": phase_turns,
                "speakers": phase_speakers,
                "progress": phases.index(phase) + 1,
                "total_phases": len(phases),
            })
            await asyncio.sleep(0.5)

        # Filter to selected personas who are in this phase's speaker list
        phase_persona_ids = [s for s in phase_speakers if s in [p["id"] for p in selected_personas]]
        if not phase_persona_ids:
            phase_persona_ids = [p["id"] for p in selected_personas]

        # Run turns for this phase
        for turn_in_phase in range(phase_turns):
            if session.turn_count >= session.max_turns:
                break

            # Pick speaker from phase's speaker list (round-robin within phase)
            speaker_id = phase_persona_ids[turn_in_phase % len(phase_persona_ids)]
            speaker = next(p for p in selected_personas if p["id"] == speaker_id)

            # Build context
            conv_text = "\n".join([f"{m.icon} {m.persona_name}: {m.content}" for m in session.messages[-8:]])

            # Get phase-specific instruction
            instruction = phase_instructions.get(speaker_id, "")
            if instruction:
                instruction = f"\n\nYOUR SPECIFIC TASK IN THIS PHASE:\n{instruction}"

            response_prompt = f"""You are in a structured collaborative session about: "**{topic}**"

CURRENT PHASE: {phase_icon} {phase_name} — {phase_desc}
SPEAKER: {speaker["icon"]} {speaker["name"]} ({speaker["title"]})

Here's what's been discussed so far:
---
{conv_text}
---

{instruction}

Respond in your natural voice. Be specific, genuine, and build on what others have said. 2-4 paragraphs."""

            response = await asyncio.get_event_loop().run_in_executor(
                None, call_llm,
                [{"role": "system", "content": speaker["system_prompt"]},
                 {"role": "user", "content": response_prompt}],
                MODEL_ID, 0.85, 2048 if phase_id in ("synthesize", "finalize") else 512
            )

            msg = Message(
                id=str(uuid.uuid4())[:8], persona_id=speaker["id"],
                persona_name=speaker["name"], icon=speaker["icon"],
                color=speaker["color"], content=response, timestamp=time.time(),
                phase=phase_id,
            )
            session.messages.append(msg)
            session.turn_count += 1

            if websocket:
                await send_ws(websocket, "message", {"message": asdict(msg)})
                await asyncio.sleep(0.5)

        # Phase complete — extract any deliverable from last message
        if phase_id in ("synthesize", "finalize"):
            session.deliverable = session.messages[-1].content if session.messages else ""
            if websocket:
                await send_ws(websocket, "deliverable", {
                    "content": session.deliverable,
                    "author": session.messages[-1].persona_name if session.messages else "",
                    "phase": phase_id,
                })

        # Update phase history with end time
        session.phase_history[-1]["ended_at"] = time.time()

    session.active = False
    if websocket:
        await send_ws(websocket, "session_complete", {
            "session_id": session.session_id, "total_turns": session.turn_count,
            "total_time": time.time() - session.started_at,
            "deliverable": session.deliverable,
        })
    return session


def asdict(obj):
    """Convert dataclass to dict."""
    return {
        "id": obj.id, "persona_id": obj.persona_id,
        "persona_name": obj.persona_name, "icon": obj.icon,
        "color": obj.color, "content": obj.content,
        "timestamp": obj.timestamp, "phase": getattr(obj, 'phase', ''),
    }

async def send_ws(websocket: WebSocket, event_type: str, data: Dict):
    await websocket.send_json({"type": event_type, **data})


# ─── FASTAPI APP ─────────────────────────────────────────────────────────────

app = FastAPI(title="SES Think Tank v3")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web")), name="static")

active_connections: Dict[str, WebSocket] = {}
active_sessions: Dict[str, ConversationSession] = {}

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(BASE_DIR / "web" / "index.html") as f:
        return f.read()

@app.get("/api/personas")
async def get_personas():
    return PERSONAS

from fastapi import Request as FastAPIRequest

@app.post("/api/chat")
async def chat_with_persona(request: FastAPIRequest):
    """Chat with a single persona directly."""
    body = await request.json()
    persona_id = body.get("persona_id")
    message = body.get("message")
    
    persona = next((p for p in PERSONAS if p['id'] == persona_id), None)
    if not persona:
        return {"error": f"Unknown persona: {persona_id}"}
    
    messages = [
        {"role": "system", "content": persona["system_prompt"]},
        {"role": "user", "content": message},
    ]
    
    response = call_llm(messages, temperature=0.85, max_tokens=1024)
    
    return {
        "persona_id": persona_id,
        "persona_name": persona["name"],
        "icon": persona["icon"],
        "response": response,
    }

@app.get("/api/workflows")
async def get_workflows():
    return WORKFLOWS

@app.get("/api/sessions")
async def get_sessions():
    return [
        {
            "session_id": s.session_id, "topic": s.topic,
            "turn_count": s.turn_count, "active": s.active,
            "started_at": s.started_at, "workflow_mode": s.workflow_mode,
            "current_phase": s.current_phase,
        }
        for s in active_sessions.values()
    ]

@app.post("/api/session")
async def create_session(topic: str, personas: str = "", max_turns: int = 20, workflow_mode: str = "salon"):
    persona_ids = [p.strip() for p in personas.split(",")] if personas else [p["id"] for p in PERSONAS]
    session_id = str(uuid.uuid4())[:8]
    wf = WORKFLOWS.get(workflow_mode, WORKFLOWS["salon"])
    active_sessions[session_id] = ConversationSession(
        session_id=session_id, topic=topic, started_at=time.time(),
        max_turns=max_turns, workflow_mode=workflow_mode,
    )
    return {"session_id": session_id, "topic": topic, "personas": persona_ids, "workflow": workflow_mode}

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "start_conversation":
                session_id = msg.get("session_id")
                topic = msg.get("topic")
                persona_ids = msg.get("personas", [p["id"] for p in PERSONAS])
                max_turns = msg.get("max_turns", 20)
                workflow_mode = msg.get("workflow_mode", "salon")

                session = await run_conversation(
                    session_id, topic, persona_ids, max_turns, workflow_mode, websocket
                )
                active_sessions[session_id] = session

            elif msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    finally:
        active_connections.pop(client_id, None)

@app.get("/api/search")
async def search(query: str):
    return {"query": query, "results": web_search(query)}

@app.get("/api/items")
async def get_items(pillar: str = "", limit: int = 50):
    items = []
    if ITEMS_DIR.exists():
        for yaml_path in sorted(ITEMS_DIR.rglob("*.yaml")):
            try:
                with open(yaml_path) as f:
                    raw = yaml.safe_load(f)
                if raw and "id" in raw:
                    items.append({
                        "id": raw["id"], "pillar": raw.get("pillar", ""),
                        "dimension": raw.get("dimension", ""), "level": raw.get("level", 1),
                        "situation": raw.get("situation", ""),
                    })
            except Exception:
                continue
    return items[:limit]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8773)
