#!/usr/bin/env python3
"""
ASFE Quality Grading — runs on existing ASFE results.
"""

import asyncio
import json
import sys
import os
import re
from datetime import datetime

sys.path.insert(0, '/c/Users/jatin/Desktop/ses-think-tank')
import importlib
import app as app_mod
importlib.reload(app_mod)

call_llm = app_mod.call_llm
PERSONAS = app_mod.PERSONAS

def get_persona_system_prompt(persona_id: str) -> str:
    return next(p for p in PERSONAS if p["id"] == persona_id)["system_prompt"]

def get_persona_name(persona_id: str) -> str:
    return next(p for p in PERSONAS if p["id"] == persona_id)["name"]

async def grade_output(prompt: str, response: str) -> dict:
    """Grade a response — returns clean JSON."""
    grading_prompt = f"""Evaluate this response. Return ONLY valid JSON.

PROMPT: {prompt}

RESPONSE (truncated):
{response[:1500]}

Grade (1-10):
{{"depth":7,"originality":6,"actionability":8,"balance":7,"clarity":8,"overall":7,"reasoning":"brief"}}
"""
    messages = [
        {"role": "system", "content": "You are a grader. Return ONLY valid JSON. No other text."},
        {"role": "user", "content": grading_prompt},
    ]

    try:
        response_text = call_llm(messages, temperature=0.1, max_tokens=256)
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            grades = json.loads(response_text[start:end])
            for key in ["depth", "originality", "actionability", "balance", "clarity", "overall"]:
                if key not in grades:
                    grades[key] = 5
            return grades
    except:
        pass

    # Fallback: extract numbers
    try:
        numbers = re.findall(r'"(\w+)":\s*(\d+)', response_text)
        if numbers:
            grades = {k: int(v) for k, v in numbers}
            grades["overall"] = grades.get("overall", 5)
            return grades
    except:
        pass

    return {"error": "parse failed", "raw": response_text[:100]}

async def main():
    print("🔍 ASFE QUALITY GRADING")
    print("=" * 60)

    with open('outputs/asfe_results.json') as f:
        results = json.load(f)

    # Grade solo baselines
    print("\nGRADING SOLO BASELINES")
    print("-" * 40)

    for prompt_id, personas in results["solo_baselines"].items():
        # Find the test prompt
        test_prompts = {
            "healthcare_001": "Design an AI system that helps rural clinics diagnose rare diseases. What are the technical, ethical, and distribution challenges?",
            "mental_health_001": "A therapist asks you to design an AI companion for patients between sessions. How do you balance support with not replacing human connection?",
        }
        prompt = test_prompts.get(prompt_id, "")

        print(f"\n{prompt_id}:")
        for pid, data in personas.items():
            print(f"  {get_persona_name(pid)}...", end=" ", flush=True)
            grade = await grade_output(prompt, data["response"])
            data["grade"] = grade
            if "error" in grade:
                print(f"❌ {grade['error']}")
            else:
                print(f"✅ Overall: {grade['overall']}/10")
            await asyncio.sleep(0.5)

    # Grade team outputs
    print("\n\nGRADING TEAM OUTPUTS")
    print("-" * 40)

    for key, data in results["team_discussions"].items():
        prompt_id = key.rsplit("_", 1)[0]
        test_prompts = {
            "healthcare_001": "Design an AI system that helps rural clinics diagnose rare diseases. What are the technical, ethical, and distribution challenges?",
            "mental_health_001": "A therapist asks you to design an AI companion for patients between sessions. How do you balance support with not replacing human connection?",
        }
        prompt = test_prompts.get(prompt_id, "")

        # Use last 2 turns as team output
        team_output = " ".join(m["content"] for m in data["transcript"][-2:])
        comp = key.rsplit("_", 1)[1]

        print(f"\n{prompt_id} / {comp}...", end=" ", flush=True)
        grade = await grade_output(prompt, team_output)
        data["grade"] = grade
        if "error" in grade:
            print(f"❌ {grade['error']}")
        else:
            print(f"✅ Overall: {grade['overall']}/10")
        await asyncio.sleep(0.5)

    # Save updated results
    with open('outputs/asfe_results_graded.json', 'w') as f:
        json.dump(results, f, indent=2)

    # Print comparison
    print("\n\n" + "=" * 60)
    print("SOLO vs TEAM COMPARISON")
    print("=" * 60)

    for prompt_id in results["solo_baselines"]:
        print(f"\n{prompt_id}:")
        print(f"{'Persona':<12} {'Overall':>8} {'Depth':>6} {'Balance':>8}")
        print("-" * 40)

        # Solo
        for pid, data in results["solo_baselines"][prompt_id].items():
            grade = data.get("grade", {})
            if "error" not in grade:
                print(f"{get_persona_name(pid):<12} {grade['overall']:>8} {grade['depth']:>6} {grade['balance']:>8}")

        # Team
        for key, data in results["team_discussions"].items():
            if key.startswith(prompt_id):
                comp = key.rsplit("_", 1)[1]
                grade = data.get("grade", {})
                if "error" not in grade:
                    print(f"{comp:<12} {grade['overall']:>8} {grade['depth']:>6} {grade['balance']:>8}")

    print("\n📄 Saved to outputs/asfe_results_graded.json")

if __name__ == '__main__':
    asyncio.run(main())
