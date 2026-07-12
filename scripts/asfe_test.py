#!/usr/bin/env python3
"""
Agentic Synergy & Friction Engine (ASFE)
=========================================
Measures whether multi-agent collaboration actually produces better output
than solo agents, and what team compositions work best.

METRICS:
1. SYNERGY — Do agents build on each other or talk past each other?
   - Cross-references: mentions teammates by name
   - Building: extends previous points rather than repeating
   - Convergence: team output is more cohesive than sum of parts

2. FRICTION — Does tension produce better output or just noise?
   - Disagreement rate: % of turns where agents challenge each other
   - Resolution: do disagreements get resolved or just escalate?
   - Productive friction: does tension lead to better final output?

3. QUALITY — Solo vs Team comparison
   - Solo baseline: each persona responds alone
   - Team output: collaborative result
   - Delta: how much better/worse is the team vs. best solo?

4. DYNAMIC WORKFLOWS — Test different team compositions
   - Full team (6) vs. subsets (3-4)
   - Different protocols (Salon, Design, Sprint, Living Lab)
   - Which composition wins for which task type?

USAGE:
    python scripts/asfe_test.py
"""

import asyncio
import json
import time
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import importlib
import app as app_mod
importlib.reload(app_mod)

call_llm = app_mod.call_llm
PERSONAS = app_mod.PERSONAS
WORKFLOWS = app_mod.WORKFLOWS

# Test prompts spanning different domains and complexity
TEST_PROMPTS = [
    {
        "id": "healthcare_001",
        "domain": "healthcare",
        "complexity": "high",
        "prompt": "Design an AI system that helps rural clinics diagnose rare diseases. What are the technical, ethical, and distribution challenges?",
    },
    {
        "id": "mental_health_001",
        "domain": "mental_health",
        "complexity": "high",
        "prompt": "A therapist asks you to design an AI companion for patients between sessions. How do you balance support with not replacing human connection?",
    },
    {
        "id": "education_001",
        "domain": "education",
        "complexity": "medium",
        "prompt": "Build an AI tutor that adapts to each student's learning style. What are the pitfalls of personalization at scale?",
    },
    {
        "id": "finance_001",
        "domain": "finance",
        "complexity": "medium",
        "prompt": "Create an AI financial advisor for low-income households. How do you avoid the pitfalls of algorithmic bias in lending?",
    },
    {
        "id": "climate_001",
        "domain": "climate",
        "complexity": "high",
        "prompt": "Design an AI system that helps communities adapt to climate change. How do you balance local knowledge with global data?",
    },
]

# Team compositions to test
TEAM_COMPOSITIONS = {
    "full_team": ["rook", "elena", "kael", "maya", "jax", "sage"],
    "core_four": ["rook", "elena", "kael", "maya"],
    "builders": ["rook", "maya", "jax"],
    "critics": ["kael", "elena", "sage"],
    "architects": ["rook", "maya", "sage"],
    "disruptors": ["kael", "jax", "elena"],
}


def get_persona(persona_id: str) -> dict:
    return next(p for p in PERSONAS if p["id"] == persona_id)


def get_persona_system_prompt(persona_id: str) -> str:
    return get_persona(persona_id)["system_prompt"]


def get_persona_name(persona_id: str) -> str:
    return get_persona(persona_id)["name"]


def get_persona_icon(persona_id: str) -> str:
    return get_persona(persona_id)["icon"]


# ─── SYNERGY METRICS ──────────────────────────────────────────────────────────

def count_cross_references(message: str, team_ids: List[str]) -> int:
    """Count how many times a message references teammates by name."""
    count = 0
    for pid in team_ids:
        name = get_persona_name(pid)
        # Count mentions of the persona's name
        count += message.lower().count(name.lower())
    return count


def measure_synergy(transcript: List[dict], team_ids: List[str]) -> dict:
    """Measure synergy across a team conversation."""
    total_cross_refs = 0
    total_messages = len(transcript)
    building_on_others = 0
    repeating_themselves = 0

    for i, msg in enumerate(transcript):
        refs = count_cross_references(msg["content"], team_ids)
        total_cross_refs += refs

        # Check if this message builds on previous ones
        if i > 0:
            prev_content = " ".join(m["content"] for m in transcript[:i])
            # Simple heuristic: does this message reference specific previous points?
            if any(
                keyword in msg["content"].lower()
                for keyword in ["as", "building on", "referenced", "pointed out", "said"]
            ):
                building_on_others += 1

    return {
        "total_cross_references": total_cross_refs,
        "avg_cross_refs_per_message": total_cross_refs / max(total_messages, 1),
        "building_on_others_count": building_on_others,
        "building_rate": building_on_others / max(total_messages - 1, 1),
        "synergy_score": (
            (total_cross_refs / max(total_messages, 1)) * 0.5
            + (building_on_others / max(total_messages - 1, 1)) * 0.5
        ),
    }


# ─── FRICTION METRICS ─────────────────────────────────────────────────────────

def measure_friction(transcript: List[dict]) -> dict:
    """Measure friction (productive tension) in a conversation."""
    disagreements = 0
    challenges = 0
    resolutions = 0

    disagreement_keywords = [
        "disagree", "but", "however", "problem is", "misses", "wrong",
        "flaw", "blind spot", "overlooks", "ignores", "concern",
    ]
    resolution_keywords = [
        "valid point", "you're right", "fair", "agreed", "good catch",
        "integrating", "addressing", "incorporating", "building on",
    ]

    for msg in transcript:
        content = msg["content"].lower()
        if any(kw in content for kw in disagreement_keywords):
            disagreements += 1
        if any(kw in content for kw in resolution_keywords):
            resolutions += 1

    total = len(transcript)
    return {
        "disagreements": disagreements,
        "resolutions": resolutions,
        "friction_rate": disagreements / max(total, 1),
        "resolution_rate": resolutions / max(disagreements, 1),
        "productive_friction_score": (
            (disagreements / max(total, 1)) * 0.4
            + (resolutions / max(disagreements, 1)) * 0.6
        ),
    }


# ─── QUALITY GRADING ──────────────────────────────────────────────────────────

async def grade_output(prompt: str, response: str, grader_persona: str = "rook") -> dict:
    """Grade a response using a persona as judge."""
    system_prompt = get_persona_system_prompt(grader_persona)

    grading_prompt = f"""You are evaluating the quality of a response to the following prompt:

PROMPT: {prompt}

RESPONSE TO EVALUATE:
{response}

Grade this response on these dimensions (1-10 scale):
1. DEPTH — How deeply does it engage with the core problem?
2. ORIGINALITY — Does it offer fresh insights or just common knowledge?
3. ACTIONABILITY — Is it concrete and implementable?
4. BALANCE — Does it consider multiple perspectives and trade-offs?
5. CLARITY — Is it well-structured and easy to understand?

Return ONLY a JSON object with this format:
{{
  "depth": <1-10>,
  "originality": <1-10>,
  "actionability": <1-10>,
  "balance": <1-10>,
  "clarity": <1-10>,
  "overall": <1-10>,
  "reasoning": "<brief explanation>"
}}
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": grading_prompt},
    ]

    try:
        response_text = call_llm(messages, temperature=0.3, max_tokens=512)
        # Extract JSON from response
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            grades = json.loads(response_text[start:end])
            return grades
        else:
            return {"error": "Could not parse grading JSON", "raw": response_text[:200]}
    except Exception as e:
        return {"error": str(e)}


# ─── SOLO vs TEAM COMPARISON ──────────────────────────────────────────────────

async def run_solo_baseline(prompt: str, persona_id: str) -> str:
    """Get a solo response from one persona."""
    system_prompt = get_persona_system_prompt(persona_id)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    return call_llm(messages, temperature=0.7, max_tokens=1024)


async def run_team_discussion(
    prompt: str,
    team_ids: List[str],
    max_turns: int = 8,
) -> List[dict]:
    """Run a team discussion with the given composition."""
    transcript = []

    # Build conversation history
    conversation_history = [{"role": "user", "content": prompt}]

    for turn in range(max_turns):
        # Cycle through team members
        persona_id = team_ids[turn % len(team_ids)]
        persona = get_persona(persona_id)

        # Build messages with conversation history
        messages = [{"role": "system", "content": persona["system_prompt"]}]

        # Add conversation history
        for msg in conversation_history:
            messages.append(msg)

        # Add instruction to reference previous speakers
        if turn > 0:
            prev_speakers = [team_ids[(turn - i) % len(team_ids)] for i in range(1, min(3, turn + 1))]
            prev_names = [get_persona_name(pid) for pid in prev_speakers]
            reference_instruction = f"\n\nIMPORTANT: Reference what {', '.join(prev_names)} said above. Build on their points or challenge them specifically."
            messages.append({"role": "system", "content": reference_instruction})

        # Get response
        response = call_llm(messages, temperature=0.8, max_tokens=768)

        # Record the turn
        transcript.append({
            "turn": turn + 1,
            "persona_id": persona_id,
            "persona_name": persona["name"],
            "icon": persona["icon"],
            "content": response,
        })

        # Add to conversation history
        conversation_history.append({
            "role": "assistant",
            "content": f"{persona['name']}: {response}",
        })

    return transcript


async def run_dynamic_sprint(
    prompt: str,
    team_ids: List[str],
    max_rounds: int = 3,
) -> dict:
    """Run a dynamic sprint where the team iterates on a shared draft."""
    transcript = []
    draft = ""

    for round_num in range(max_rounds):
        round_transcript = []

        # Each team member contributes to the draft
        for persona_id in team_ids:
            persona = get_persona(persona_id)

            messages = [
                {"role": "system", "content": persona["system_prompt"]},
                {"role": "user", "content": prompt},
            ]

            if draft:
                messages.append({
                    "role": "user",
                    "content": f"\n\nCURRENT DRAFT (Round {round_num + 1}):\n{draft}\n\nReview this draft and provide your contribution, critique, or improvement. Reference specific parts of the draft.",
                })

            response = call_llm(messages, temperature=0.8, max_tokens=768)

            round_transcript.append({
                "round": round_num + 1,
                "persona_id": persona_id,
                "persona_name": persona["name"],
                "icon": persona["icon"],
                "content": response,
            })

            # Update draft with this contribution
            draft = f"{draft}\n\n[{persona['name']}]: {response}"

        transcript.extend(round_transcript)

    return {
        "transcript": transcript,
        "final_draft": draft,
        "rounds": max_rounds,
    }


# ─── MAIN TEST SUITE ──────────────────────────────────────────────────────────

async def run_asfe_test():
    print("=" * 70)
    print("AGENTIC SYNERGY & FRICTION ENGINE (ASFE)")
    print("=" * 70)
    print(f"Started: {datetime.now()}")
    print(f"Test prompts: {len(TEST_PROMPTS)}")
    print(f"Team compositions: {len(TEAM_COMPOSITIONS)}")
    print(f"Personas: {len(PERSONAS)}")
    print()

    results = {
        "test_id": f"asfe_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "started_at": datetime.now().isoformat(),
        "solo_baselines": {},
        "team_discussions": {},
        "dynamic_sprints": {},
        "composition_comparison": {},
    }

    # ─── PHASE 1: SOLO BASELINES ─────────────────────────────────────────────
    print("PHASE 1: SOLO BASELINES")
    print("-" * 40)

    for prompt in TEST_PROMPTS[:2]:  # Test on first 2 prompts for speed
        print(f"\nPrompt: {prompt['id']} ({prompt['domain']})")
        results["solo_baselines"][prompt["id"]] = {}

        for persona in PERSONAS:
            print(f"  {persona['icon']} {persona['name']}...", end=" ", flush=True)
            response = await run_solo_baseline(prompt["prompt"], persona["id"])
            results["solo_baselines"][prompt["id"]][persona["id"]] = {
                "response": response,
                "length": len(response),
            }
            print(f"✅ {len(response)} chars")
            await asyncio.sleep(0.5)

    # ─── PHASE 2: TEAM DISCUSSIONS ───────────────────────────────────────────
    print("\n\nPHASE 2: TEAM DISCUSSIONS")
    print("-" * 40)

    for prompt in TEST_PROMPTS[:2]:
        print(f"\nPrompt: {prompt['id']} ({prompt['domain']})")

        for comp_name, team_ids in TEAM_COMPOSITIONS.items():
            print(f"\n  Team: {comp_name} ({len(team_ids)} personas)")
            transcript = await run_team_discussion(
                prompt["prompt"], team_ids, max_turns=8
            )

            synergy = measure_synergy(transcript, team_ids)
            friction = measure_friction(transcript)

            results["team_discussions"][f"{prompt['id']}_{comp_name}"] = {
                "transcript": transcript,
                "synergy": synergy,
                "friction": friction,
                "team_size": len(team_ids),
            }

            print(f"    Synergy: {synergy['synergy_score']:.2f}")
            print(f"    Friction: {friction['productive_friction_score']:.2f}")
            print(f"    Cross-refs: {synergy['total_cross_references']}")
            print(f"    Disagreements: {friction['disagreements']}")

            await asyncio.sleep(1)

    # ─── PHASE 3: DYNAMIC SPRINTS ────────────────────────────────────────────
    print("\n\nPHASE 3: DYNAMIC SPRINTS")
    print("-" * 40)

    for prompt in TEST_PROMPTS[:2]:
        print(f"\nPrompt: {prompt['id']} ({prompt['domain']})")

        for comp_name, team_ids in list(TEAM_COMPOSITIONS.items())[:3]:
            print(f"\n  Team: {comp_name}")
            sprint_result = await run_dynamic_sprint(
                prompt["prompt"], team_ids, max_rounds=2
            )

            transcript = sprint_result["transcript"]
            synergy = measure_synergy(transcript, team_ids)
            friction = measure_friction(transcript)

            results["dynamic_sprints"][f"{prompt['id']}_{comp_name}"] = {
                "transcript": transcript,
                "final_draft_length": len(sprint_result["final_draft"]),
                "synergy": synergy,
                "friction": friction,
            }

            print(f"    Final draft: {len(sprint_result['final_draft'])} chars")
            print(f"    Synergy: {synergy['synergy_score']:.2f}")
            print(f"    Friction: {friction['productive_friction_score']:.2f}")

            await asyncio.sleep(1)

    # ─── PHASE 4: QUALITY GRADING ────────────────────────────────────────────
    print("\n\nPHASE 4: QUALITY GRADING")
    print("-" * 40)

    # Grade solo vs team output
    for prompt in TEST_PROMPTS[:2]:
        print(f"\nPrompt: {prompt['id']}")

        # Grade best solo response
        best_solo = max(
            results["solo_baselines"][prompt["id"]].items(),
            key=lambda x: len(x[1]["response"]),
        )
        print(f"  Grading best solo ({get_persona_name(best_solo[0])})...", end=" ")
        solo_grade = await grade_output(prompt["prompt"], best_solo[1]["response"])
        print(f"Overall: {solo_grade.get('overall', 'ERROR')}")

        # Grade team output
        team_key = f"{prompt['id']}_full_team"
        if team_key in results["team_discussions"]:
            team_transcript = results["team_discussions"][team_key]["transcript"]
            team_output = " ".join(m["content"] for m in team_transcript[-2:])
            print(f"  Grading team output...", end=" ")
            team_grade = await grade_output(prompt["prompt"], team_output)
            print(f"Overall: {team_grade.get('overall', 'ERROR')}")

            results["composition_comparison"][prompt["id"]] = {
                "solo_grade": solo_grade,
                "team_grade": team_grade,
                "delta": team_grade.get("overall", 0) - solo_grade.get("overall", 0),
            }

    # ─── SUMMARY ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ASFE TEST COMPLETE")
    print("=" * 70)

    # Save results
    output_path = "outputs/asfe_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n📄 Saved to {output_path}")

    # Print summary table
    print("\nSYNERGY & FRICTION SUMMARY")
    print("-" * 60)
    print(f"{'Team':<20} {'Synergy':>10} {'Friction':>10} {'Cross-refs':>12}")
    print("-" * 60)

    for key, data in results["team_discussions"].items():
        comp = key.split("_")[-1]
        synergy = data["synergy"]["synergy_score"]
        friction = data["friction"]["productive_friction_score"]
        cross_refs = data["synergy"]["total_cross_references"]
        print(f"{comp:<20} {synergy:>10.2f} {friction:>10.2f} {cross_refs:>12}")

    print("\nQUALITY COMPARISON (Solo vs Team)")
    print("-" * 60)
    for prompt_id, comparison in results["composition_comparison"].items():
        solo = comparison["solo_grade"].get("overall", "N/A")
        team = comparison["team_grade"].get("overall", "N/A")
        delta = comparison["delta"]
        print(f"{prompt_id}: Solo={solo}, Team={team}, Delta={delta:+.1f}")

    return results


if __name__ == "__main__":
    results = asyncio.run(run_asfe_test())
