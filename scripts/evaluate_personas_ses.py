#!/usr/bin/env python3
"""
Evaluate Think Tank persona outputs against SES benchmark items.
Tests how well each persona handles emotionally complex scenarios.
"""

import asyncio
import json
import time
import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory to path
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)
import importlib
import app as app_mod
importlib.reload(app_mod)

call_llm = app_mod.call_llm
PERSONAS = app_mod.PERSONAS

# Load SES benchmark items
ITEMS_DIR = Path(r"C:\Users\jatin\Desktop\SES-benchmark\items")
import yaml

def load_items():
    items = []
    for f in sorted(ITEMS_DIR.glob("*.yaml")):
        with open(f) as fh:
            data = yaml.safe_load(fh)
        data['_source'] = f.name
        items.append(data)
    return items

def get_persona_system_prompt(persona_id):
    for p in PERSONAS:
        if p['id'] == persona_id:
            return p['system_prompt']
    return ""

def get_persona_name(persona_id):
    for p in PERSONAS:
        if p['id'] == persona_id:
            return p['name']
    return persona_id

async def evaluate_persona_on_item(persona_id, item):
    """Have a persona respond to one SES benchmark item."""
    system_prompt = get_persona_system_prompt(persona_id)
    user_message = item['user_turns'][0]
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    try:
        response = call_llm(messages, temperature=0.7, max_tokens=1024)
        return {
            'persona_id': persona_id,
            'persona_name': get_persona_name(persona_id),
            'item_id': item['id'],
            'pillar': item['pillar'],
            'dimension': item['dimension'],
            'level': item['level'],
            'user_prompt': user_message,
            'response': response,
            'response_length': len(response),
        }
    except Exception as e:
        return {
            'persona_id': persona_id,
            'item_id': item['id'],
            'error': str(e),
        }

async def main():
    print("🏥 SES Benchmark Evaluation: Think Tank Personas")
    print(f"Started: {datetime.now()}")
    
    # Load a sample of items (stratified by pillar)
    all_items = load_items()
    print(f"Total items available: {len(all_items)}")
    
    # Pick 5 items per pillar for evaluation
    sample = []
    for pillar in ['EMOTIONAL', 'SOCIAL', 'SPIRITUAL']:
        pillar_items = [i for i in all_items if i['pillar'] == pillar]
        # Get items from different difficulty levels
        for level in [1, 2, 3, 4]:
            level_items = [i for i in pillar_items if i['level'] == level]
            if level_items:
                sample.append(level_items[0])
    
    print(f"Sample size: {len(sample)} items")
    print(f"Personas to evaluate: {len(PERSONAS)}")
    print(f"Total evaluations: {len(sample) * len(PERSONAS)}")
    print()
    
    results = []
    total = len(sample) * len(PERSONAS)
    count = 0
    
    for item in sample:
        print(f"\n{'='*60}")
        print(f"Item: {item['id']} ({item['pillar']}/{item['dimension']}, L{item['level']})")
        print(f"Prompt: {item['user_turns'][0][:80]}...")
        print('='*60)
        
        for persona in PERSONAS:
            count += 1
            print(f"\n  [{count}/{total}] Evaluating {persona['name']}...")
            
            result = await evaluate_persona_on_item(persona['id'], item)
            results.append(result)
            
            if 'error' in result:
                print(f"    ❌ Error: {result['error']}")
            else:
                preview = result['response'][:100].replace('\n', ' ')
                print(f"    ✅ {result['response_length']} chars: {preview}...")
            
            await asyncio.sleep(1)
    
    # Save results
    output = {
        'generated_at': datetime.now().isoformat(),
        'total_evaluations': len(results),
        'sample_size': len(sample),
        'personas_evaluated': len(PERSONAS),
        'results': results,
    }
    
    with open('outputs/persona_ses_eval.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    # Print summary
    print(f"\n{'='*60}")
    print("EVALUATION COMPLETE")
    print('='*60)
    print(f"Total evaluations: {len(results)}")
    successful = [r for r in results if 'error' not in r]
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(results) - len(successful)}")
    
    # Average response length by persona
    print(f"\nAvg response length by persona:")
    for persona in PERSONAS:
        persona_results = [r for r in successful if r['persona_id'] == persona['id']]
        if persona_results:
            avg_len = sum(r['response_length'] for r in persona_results) / len(persona_results)
            print(f"  {persona['name']}: {avg_len:.0f} chars")
    
    # By pillar
    print(f"\nResults by pillar:")
    for pillar in ['EMOTIONAL', 'SOCIAL', 'SPIRITUAL']:
        pillar_results = [r for r in successful if r['pillar'] == pillar]
        if pillar_results:
            avg_len = sum(r['response_length'] for r in pillar_results) / len(pillar_results)
            print(f"  {pillar}: {len(pillar_results)} evals, avg {avg_len:.0f} chars")
    
    print(f"\n📄 Saved to outputs/persona_ses_eval.json")
    return output

if __name__ == '__main__':
    asyncio.run(main())
