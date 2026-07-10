#!/usr/bin/env python3
"""
Healthcare LLM Innovation Marathon
10-hour autonomous brainstorming with iterative refinement.

Structure:
  Phase 1: Broad Exploration (20 Salon sessions)    ~2.5h
  Phase 2: Deep Design (25 Design sessions)         ~3.0h
  Phase 3: Concrete Specs (15 Sprint sessions)      ~1.5h
  Phase 4: Reflection & Critique (10 Salon sessions) ~1.5h
  Phase 5: Iterative Redesign (10 Design sessions)   ~1.5h
  Phase 6: Final Polish (5 Sprint sessions)         ~0.5h
  ───────────────────────────────────────────────────────────
  Total: ~85 sessions, ~1,500 turns, ~8-10 hours

Each phase builds on the previous — ideas get refined, critiqued, and improved.
Progress is saved after every session so you can resume if interrupted.
"""

import asyncio
import json
import time
import sys
import os
from datetime import datetime

# Add parent directory (project root) to path
MARATHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MARATHON_DIR)
import importlib
import app as app_mod
importlib.reload(app_mod)

run_conversation = app_mod.run_conversation
PERSONAS = app_mod.PERSONAS

PROGRESS_FILE = 'outputs/marathon_progress.json'

# ═══════════════════════════════════════════════════════════════════════
# PHASE 1: BROAD EXPLORATION (Salon Mode, 20 sessions × 20 turns)
# ═══════════════════════════════════════════════════════════════════════
PHASE1_EXPLORATION = [
    # Mental Health (5)
    "What are the biggest gaps in mental healthcare that LLMs could genuinely fill? Focus on accessibility, stigma, early intervention, and underserved populations.",
    "How can AI therapy companions be designed ethically? What prevents harm while maintaining therapeutic value? Consider boundaries, escalation, and human oversight.",
    "Design an approach for detecting mental health crises from digital footprints (text messages, social media, journal entries). What are the false positive/negative risks?",
    "How can LLMs support therapists and counselors as decision support tools? Focus on treatment planning, progress tracking, and session preparation.",
    "What would an ideal AI mental health tool look like for teens and young adults? Consider engagement, privacy, parental involvement, and crisis detection.",
    
    # Chronic Disease (5)
    "How can LLMs help patients with diabetes, hypertension, or heart disease manage their conditions daily? Focus on behavior change, motivation, and personalization.",
    "What would an AI-powered chronic disease coach look like? How does it balance motivation with medical accuracy? Consider adherence, lifestyle changes, and emergency detection.",
    "How can LLMs reduce hospital readmissions through post-discharge support? Focus on medication adherence, symptom monitoring, and follow-up coordination.",
    "Design an LLM system for patients managing multiple chronic conditions simultaneously. How do you handle complexity, medication interactions, and care coordination?",
    "How can AI help make clinical trial data and research findings accessible to patients with chronic diseases? Focus on personalized relevance and actionability.",
    
    # Health Equity & Access (5)
    "How can LLMs reduce healthcare disparities for underserved communities? Focus on language barriers, cultural competence, digital literacy, and trust.",
    "Design an LLM system for rural healthcare where specialists are scarce. What capabilities are most valuable? Consider triage, second opinions, and telehealth support.",
    "How can AI help bridge the gap between complex medical research and patient understanding for low-literacy populations? Consider visual aids, simple language, and cultural adaptation.",
    "What LLM-powered tools could help undocumented immigrants and refugees access healthcare? Focus on language, legal concerns, cultural safety, and resource navigation.",
    "How can LLMs support community health workers in low-resource settings? Consider decision support, patient education, and data collection.",
    
    # Provider Support & Innovation (5)
    "What's the biggest source of physician burnout, and how can LLMs realistically help? Focus on documentation, communication, prior authorizations, and decision fatigue.",
    "Design an AI assistant that helps doctors communicate difficult diagnoses to patients with empathy and clarity. Consider emotional intelligence and cultural sensitivity.",
    "How can LLMs support nurses in managing patient flow, documentation, care coordination, and family communication?",
    "What breakthrough healthcare applications of LLMs don't exist yet? Think beyond chatbots — diagnosis, drug discovery, personalized medicine, and predictive analytics.",
    "How can LLMs be integrated into wearable health devices to provide real-time health insights, early warning, and personalized interventions?",
]

# ═══════════════════════════════════════════════════════════════════════
# PHASE 2: DEEP DESIGN (Design Studio Mode, 25 sessions × 14 turns)
# ═══════════════════════════════════════════════════════════════════════
PHASE2_DESIGN = [
    # Mental Health Systems (5)
    "Design a culturally-adaptive mental health chatbot for immigrant communities. Must handle multiple languages, cultural concepts of mental health, crisis escalation, and connection to human providers.",
    "Design an AI-powered peer support matching system for mental health. Connect people with similar experiences while ensuring safety, privacy, and appropriate boundaries.",
    "Design an LLM system for schools that provides mental health first aid to students. Include age-appropriate responses, teacher/parent notification, and crisis protocols.",
    "Design an AI tool that helps mental health patients track their symptoms, moods, and triggers over time, generating insights they can share with their therapist.",
    "Design an LLM-powered suicide risk assessment tool for emergency departments. Must be fast, accurate, culturally sensitive, and integrate with clinical workflow.",
    
    # Chronic Disease Systems (5)
    "Design an AI-powered medication adherence system for elderly patients with multiple prescriptions. Include smart reminders, side effect monitoring, drug interaction checks, and caregiver alerts.",
    "Design an LLM system for diabetes management that helps patients understand their CGM data, make food choices, and adjust behavior. Must work across literacy levels.",
    "Design an AI health coach for heart disease patients recovering from cardiac events. Cover medication, exercise, diet, stress management, and emergency recognition.",
    "Design an LLM-powered system for asthma management that helps patients understand triggers, use inhalers correctly, recognize worsening symptoms, and access care.",
    "Design an AI tool that helps patients prepare for doctor appointments — organizing symptoms, questions, medication lists, and medical history into clear summaries.",
    
    # Equity & Access Systems (5)
    "Design an LLM-powered health navigation system for uninsured/underinsured patients. Help them find affordable care, understand insurance options, and access community resources.",
    "Design an AI translation and cultural adaptation tool for clinical encounters with non-English speakers. Must preserve medical accuracy while adapting to cultural contexts.",
    "Design an LLM system for maternal health in underserved communities. Cover prenatal care, risk factor screening, labor support, and postpartum follow-up.",
    "Design an AI-powered tool for community health workers in low-resource settings. Include symptom assessment, treatment guidance, referral pathways, and data reporting.",
    "Design an LLM system that helps patients understand and navigate the healthcare system — from making appointments to understanding bills to filing insurance claims.",
    
    # Provider & Innovation Systems (5)
    "Design an AI assistant that automates clinical documentation while improving note quality. Must integrate with EHR systems, capture patient conversations, and generate structured notes.",
    "Design an LLM-powered prior authorization assistant that helps providers complete insurance paperwork efficiently, reducing administrative burden.",
    "Design an AI tool that helps healthcare teams communicate complex treatment plans to patients and families. Include visual aids, plain language, and cultural adaptation.",
    "Design an LLM system for detecting healthcare provider burnout from clinical notes and communications. Include early warning, resource referral, and organizational analytics.",
    "Design an AI-powered clinical decision support tool that helps primary care providers diagnose rare diseases by comparing symptoms against medical literature and case reports.",
    
    # Cross-Cutting (5)
    "Design an LLM system for pediatric healthcare that helps parents understand their child's symptoms, treatment options, developmental milestones, and when to seek urgent care.",
    "Design an AI companion for patients undergoing cancer treatment — tracking side effects, providing emotional support, coordinating with care teams, and connecting to support resources.",
    "Design an LLM-powered health education platform that adapts to the user's literacy level, cultural background, health beliefs, and preferred learning style.",
    "Design an AI system for geriatric care coordination — helping families manage multiple providers, medications, appointments, and care decisions for elderly relatives.",
    "Design an LLM-powered patient portal that makes medical records understandable. Include lab result explanations, imaging report summaries, and medication guides.",
]

# ═══════════════════════════════════════════════════════════════════════
# PHASE 3: CONCRETE SPECIFICATIONS (Sprint Mode, 15 sessions × 10 turns)
# ═══════════════════════════════════════════════════════════════════════
PHASE3_SPRINT = [
    "Write a detailed system specification for an AI-powered mental health first aid tool for schools. Include safety protocols, age-appropriate response frameworks, crisis escalation paths, and evaluation metrics.",
    "Write a system prompt and architecture for an LLM that translates medical jargon into patient-friendly language while preserving critical information. Include accuracy validation and literacy level adaptation.",
    "Write a specification for an AI-powered medication interaction checker that patients can use at home. Include safety disclaimers, escalation protocols, drug database integration, and side effect reporting.",
    "Write a detailed spec for an AI health coach for pregnant women in underserved communities. Cover prenatal care reminders, risk factor screening, nutrition guidance, and hospital coordination.",
    "Write a system specification for an LLM-powered symptom checker that prioritizes safety. Include red flag detection, differential diagnosis display, uncertainty communication, and clear 'see a doctor' thresholds.",
    "Write a spec for an AI tool that helps healthcare providers write discharge instructions that are actually understandable. Include literacy level adaptation, cultural sensitivity, and follow-up scheduling.",
    "Write a detailed specification for an AI-powered health data interpreter that helps patients understand wearable device data (sleep, heart rate, activity, glucose) in medical context.",
    "Write a system spec for an LLM that supports end-of-life healthcare decision-making. Include ethical frameworks, family communication support, advance directive guidance, and palliative care resources.",
    "Write a specification for an AI-powered pediatric symptom assessor for parents. Include age-specific guidance, red flag symptoms, when-to-go-to-ER thresholds, and reassurance for common issues.",
    "Write a system spec for an LLM-powered clinical documentation assistant. Include conversation-to-note generation, structured data extraction, EHR integration, and quality assurance protocols.",
    "Write a detailed spec for an AI medication adherence coach for elderly patients. Include personalized reminder strategies, pill identification, side effect tracking, and pharmacist escalation.",
    "Write a system specification for an AI-powered health navigation tool for uninsured patients. Include resource finding, cost comparison, sliding scale clinic directories, and emergency care guidance.",
    "Write a spec for an LLM-powered chronic disease dashboard that helps patients understand their health data over time. Include trend analysis, goal tracking, provider sharing, and behavioral nudges.",
    "Write a detailed specification for an AI peer support matching system for mental health. Include compatibility algorithms, safety screening, conversation monitoring, and crisis intervention protocols.",
    "Write a system spec for an LLM-powered prior authorization assistant. Include insurance policy parsing, clinical justification generation, appeal letter drafting, and status tracking.",
]

# ═══════════════════════════════════════════════════════════════════════
# PHASE 4: REFLECTION & CRITIQUE (Salon Mode, 10 sessions × 20 turns)
# ═══════════════════════════════════════════════════════════════════════
PHASE4_REFLECTION = [
    "Review all the mental health AI designs we've created. What are the common weaknesses? Where do we fall short on safety, ethics, and real-world feasibility? Be brutally honest.",
    "Review all the chronic disease management designs. Where do they fail patients? Consider health literacy, cultural competence, emergency handling, and the digital divide.",
    "Review all the health equity designs. Do they actually serve underserved populations or just tokenize them? What blind spots do we have around trust, access, and cultural safety?",
    "Review all the provider support designs. Do they genuinely reduce burnout or add more complexity? Consider workflow integration, alert fatigue, and the human element of care.",
    "Review all the specifications we've written. Which ones are actually buildable with current technology? Which ones are over-engineered or under-specified?",
    "What are the biggest risks of deploying these AI healthcare tools? Consider bias amplification, diagnostic errors, privacy breaches, liability, and erosion of patient-provider trust.",
    "Which of our designs would actually pass FDA/CE medical device review? What regulatory hurdles do we need to address? Consider validation, clinical trials, and post-market surveillance.",
    "How do we measure whether these AI tools are actually improving patient outcomes? Design evaluation frameworks for each major category.",
    "What would happen if these AI tools failed catastrophically? Design failure mode analysis and contingency plans for our highest-risk systems.",
    "Synthesize everything: What are the top 3 AI healthcare innovations from our brainstorming that have the highest potential impact? What makes them stand out, and what needs to change?",
]

# ═══════════════════════════════════════════════════════════════════════
# PHASE 5: ITERATIVE REDESIGN (Design Studio Mode, 10 sessions × 14 turns)
# ═══════════════════════════════════════════════════════════════════════
PHASE5_REDESIGN = [
    "Take the best mental health AI design and rebuild it addressing all the critique points. Make it safer, more culturally competent, and more feasible. Design the improved version.",
    "Take the best chronic disease management design and rebuild it. Address health literacy gaps, emergency handling, and the digital divide. Design the improved version.",
    "Take the best health equity design and rebuild it. Address trust, real-world access, cultural safety, and community partnership. Design the improved version.",
    "Take the best provider support design and rebuild it. Address workflow integration, alert fatigue, and human-centered design. Design the improved version.",
    "Take the most promising AI healthcare innovation and design a comprehensive implementation roadmap. Include pilot design, stakeholder engagement, and scale-up strategy.",
    "Design a safety framework that applies across all our AI healthcare tools. Include risk assessment, monitoring, incident reporting, and continuous improvement protocols.",
    "Design a patient consent and transparency system for AI-powered healthcare tools. How do patients understand what AI is doing with their data and how to opt out?",
    "Design a bias detection and mitigation system for healthcare AI. Include training data auditing, outcome monitoring across demographics, and corrective action protocols.",
    "Design a clinical validation framework for our AI healthcare tools. Include study design, outcome measures, comparison groups, and publication strategy.",
    "Design a comprehensive AI healthcare toolkit that integrates our best mental health, chronic disease, equity, and provider support tools into one cohesive platform.",
]

# ═══════════════════════════════════════════════════════════════════════
# PHASE 6: FINAL POLISH (Sprint Mode, 5 sessions × 10 turns)
# ═══════════════════════════════════════════════════════════════════════
PHASE6_FINAL = [
    "Write the final polished specification for our best mental health AI innovation. Include complete system architecture, safety protocols, evaluation plan, and implementation roadmap.",
    "Write the final polished specification for our best chronic disease management AI. Include complete system architecture, patient engagement strategy, clinical validation plan, and scale-up approach.",
    "Write the final polished specification for our best health equity AI tool. Include community partnership framework, cultural adaptation protocol, access strategy, and impact measurement.",
    "Write the final polished specification for our best provider support AI tool. Include workflow integration plan, EHR compatibility, adoption strategy, and burnout reduction metrics.",
    "Write the master healthcare AI innovation report. Synthesize all our work into a comprehensive document: top innovations, safety frameworks, implementation roadmaps, and impact projections.",
]


async def run_session(session_config, session_num, previous_context=""):
    """Run a single Think Tank session."""
    print(f"\n{'='*70}")
    print(f"SESSION {session_num}: {session_config['label']}")
    print(f"Mode: {session_config['mode']} | Max turns: {session_config['max_turns']}")
    print(f"{'='*70}")
    
    messages_log = []
    deliverable = ''
    eval_scores = []
    
    class CaptureWS:
        async def send_json(self, data):
            d = data
            if d.get('type') == 'phase_change':
                print(f"  🔄 {d['icon']} {d['name']}")
            elif d.get('type') == 'message':
                msg = d['message']
                messages_log.append(msg)
                content = msg['content']
                preview = content[:50].replace('\n', ' ')
                print(f"  ✅ [{msg['persona_name']}] {preview}...")
            elif d.get('type') == 'deliverable':
                nonlocal deliverable
                deliverable = d['content']
                print(f"  📋 Deliverable: {len(deliverable)} chars")
            elif d.get('type') == 'evaluation':
                eval_scores.append(d['evaluation']['quality_score'])
    
    ws = CaptureWS()
    personas = [p['id'] for p in PERSONAS]
    t0 = time.time()
    
    full_topic = session_config['topic']
    if previous_context:
        full_topic = f"{session_config['topic']}\n\nKey insights from previous sessions to build on:\n{previous_context}"
    
    try:
        session_id = f"healthcare_{session_config['mode']}_{session_num}"
        session = await run_conversation(
            session_id, 
            full_topic, 
            personas, 
            max_turns=session_config['max_turns'],
            workflow_mode=session_config['mode'],
            websocket=ws
        )
        
        result = {
            'session_num': session_num,
            'label': session_config['label'],
            'mode': session_config['mode'],
            'topic': session_config['topic'],
            'turns': session.turn_count,
            'time': round(time.time() - t0),
            'deliverable': deliverable,
            'eval_scores': eval_scores,
            'messages': messages_log,
        }
        
        print(f"✅ Done: {session.turn_count} turns, {time.time()-t0:.0f}s")
        return result
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return {
            'session_num': session_num,
            'label': session_config['label'],
            'error': str(e),
            'time': round(time.time() - t0),
        }

def extract_key_ideas(results, count=5):
    """Extract key ideas from recent sessions for iterative context."""
    ideas = []
    for r in results:
        if r.get('deliverable') and len(r['deliverable']) > 100:
            ideas.append(f"- [{r['label']}] {r['deliverable'][:250]}...")
    return "\n".join(ideas[-count:])

def save_progress(phase, session_num, results, start_time):
    """Save progress after each session."""
    progress = {
        'phase': phase,
        'session': session_num,
        'total_sessions': len(results),
        'time_elapsed': round(time.time() - start_time),
        'time_elapsed_hours': round((time.time() - start_time) / 3600, 2),
        'results': results,
    }
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

async def run_marathon():
    """Run the full healthcare brainstorming marathon."""
    start_time = time.time()
    
    print("🏥 HEALTHCARE LLM INNOVATION MARATHON")
    print(f"Started: {datetime.now()}")
    total_sessions = (len(PHASE1_EXPLORATION) + len(PHASE2_DESIGN) + 
                      len(PHASE3_SPRINT) + len(PHASE4_REFLECTION) + 
                      len(PHASE5_REDESIGN) + len(PHASE6_FINAL))
    print(f"Total sessions: {total_sessions}")
    print(f"Estimated time: ~8-10 hours")
    print()
    
    results = []
    session_num = 0
    
    # ─── PHASE 1: Broad Exploration ─────────────────────────────
    print("\n" + "🔍"*35)
    print("PHASE 1: BROAD EXPLORATION (Salon Mode)")
    print(f"Sessions: {len(PHASE1_EXPLORATION)}")
    print("🔍"*35)
    
    for i, topic in enumerate(PHASE1_EXPLORATION, 1):
        session_num += 1
        config = {
            'label': f"Exploration {i}/{len(PHASE1_EXPLORATION)}",
            'topic': topic,
            'mode': 'salon',
            'max_turns': 20,
        }
        result = await run_session(config, session_num)
        results.append(result)
        save_progress(1, session_num, results, start_time)
        await asyncio.sleep(5)
    
    # ─── PHASE 2: Deep Design ───────────────────────────────────
    print("\n" + "🎨"*35)
    print("PHASE 2: DEEP DESIGN (Design Studio Mode)")
    print(f"Sessions: {len(PHASE2_DESIGN)}")
    print("🎨"*35)
    
    previous_ideas = extract_key_ideas(results, count=8)
    
    for i, topic in enumerate(PHASE2_DESIGN, 1):
        session_num += 1
        config = {
            'label': f"Design {i}/{len(PHASE2_DESIGN)}",
            'topic': topic,
            'mode': 'design',
            'max_turns': 14,
        }
        result = await run_session(config, session_num, previous_context=previous_ideas)
        results.append(result)
        save_progress(2, session_num, results, start_time)
        await asyncio.sleep(5)
    
    # ─── PHASE 3: Concrete Specifications ───────────────────────
    print("\n" + "📝"*35)
    print("PHASE 3: CONCRETE SPECIFICATIONS (Sprint Mode)")
    print(f"Sessions: {len(PHASE3_SPRINT)}")
    print("📝"*35)
    
    all_ideas = extract_key_ideas(results, count=10)
    
    for i, topic in enumerate(PHASE3_SPRINT, 1):
        session_num += 1
        config = {
            'label': f"Sprint {i}/{len(PHASE3_SPRINT)}",
            'topic': topic,
            'mode': 'sprint',
            'max_turns': 10,
        }
        result = await run_session(config, session_num, previous_context=all_ideas)
        results.append(result)
        save_progress(3, session_num, results, start_time)
        await asyncio.sleep(5)
    
    # ─── PHASE 4: Reflection & Critique ─────────────────────────
    print("\n" + "🔎"*35)
    print("PHASE 4: REFLECTION & CRITIQUE (Salon Mode)")
    print(f"Sessions: {len(PHASE4_REFLECTION)}")
    print("🔎"*35)
    
    all_deliverables = extract_key_ideas(results, count=15)
    
    for i, topic in enumerate(PHASE4_REFLECTION, 1):
        session_num += 1
        config = {
            'label': f"Reflection {i}/{len(PHASE4_REFLECTION)}",
            'topic': topic,
            'mode': 'salon',
            'max_turns': 20,
        }
        result = await run_session(config, session_num, previous_context=all_deliverables)
        results.append(result)
        save_progress(4, session_num, results, start_time)
        await asyncio.sleep(5)
    
    # ─── PHASE 5: Iterative Redesign ────────────────────────────
    print("\n" + "🔧"*35)
    print("PHASE 5: ITERATIVE REDESIGN (Design Studio Mode)")
    print(f"Sessions: {len(PHASE5_REDESIGN)}")
    print("🔧"*35)
    
    critique_summary = extract_key_ideas(results, count=10)
    
    for i, topic in enumerate(PHASE5_REDESIGN, 1):
        session_num += 1
        config = {
            'label': f"Redesign {i}/{len(PHASE5_REDESIGN)}",
            'topic': topic,
            'mode': 'design',
            'max_turns': 14,
        }
        result = await run_session(config, session_num, previous_context=critique_summary)
        results.append(result)
        save_progress(5, session_num, results, start_time)
        await asyncio.sleep(5)
    
    # ─── PHASE 6: Final Polish ──────────────────────────────────
    print("\n" + "✨"*35)
    print("PHASE 6: FINAL POLISH (Sprint Mode)")
    print(f"Sessions: {len(PHASE6_FINAL)}")
    print("✨"*35)
    
    final_context = extract_key_ideas(results, count=15)
    
    for i, topic in enumerate(PHASE6_FINAL, 1):
        session_num += 1
        config = {
            'label': f"Final {i}/{len(PHASE6_FINAL)}",
            'topic': topic,
            'mode': 'sprint',
            'max_turns': 10,
        }
        result = await run_session(config, session_num, previous_context=final_context)
        results.append(result)
        save_progress(6, session_num, results, start_time)
        await asyncio.sleep(5)
    
    # ─── FINAL REPORT ───────────────────────────────────────────
    print("\n" + "📊"*35)
    print("COMPILING FINAL REPORT")
    print("📊"*35)
    
    total_time = time.time() - start_time
    report = compile_final_report(results, total_time)
    
    with open('outputs/healthcare_marathon_final.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    summary = generate_summary(report)
    with open('outputs/healthcare_marathon_summary.md', 'w') as f:
        f.write(summary)
    
    print(f"\n{'='*70}")
    print("✅ MARATHON COMPLETE!")
    print(f"{'='*70}")
    print(f"Total time: {total_time:.0f}s ({total_time/3600:.1f}h)")
    successful = len([r for r in results if 'error' not in r])
    failed = len([r for r in results if 'error' in r])
    print(f"Sessions completed: {successful}/{len(results)}")
    print(f"Failed sessions: {failed}")
    print(f"\n📄 outputs/healthcare_marathon_summary.md (readable report)")
    print(f"📊 outputs/healthcare_marathon_final.json (full data)")
    print(f"💾 outputs/marathon_progress.json (progress log)")


def compile_final_report(results, total_time):
    """Compile all results into a structured report."""
    successful = [r for r in results if 'error' not in r]
    failed = [r for r in results if 'error' in r]
    
    return {
        'title': 'Healthcare LLM Innovation Report',
        'subtitle': 'Autonomous 10-Hour Brainstorming Marathon',
        'generated_at': datetime.now().isoformat(),
        'total_sessions': len(results),
        'successful_sessions': len(successful),
        'failed_sessions': len(failed),
        'total_time': round(total_time),
        'total_time_hours': round(total_time / 3600, 1),
        'by_phase': {
            'exploration': [r for r in results if r.get('mode') == 'salon' and 'Exploration' in r.get('label', '')],
            'design': [r for r in results if r.get('mode') == 'design' and 'Design' in r.get('label', '')],
            'sprint': [r for r in results if r.get('mode') == 'sprint' and 'Sprint' in r.get('label', '')],
            'reflection': [r for r in results if 'Reflection' in r.get('label', '')],
            'redesign': [r for r in results if 'Redesign' in r.get('label', '')],
            'final': [r for r in results if 'Final' in r.get('label', '')],
        },
        'deliverables': [
            {
                'session': r['session_num'],
                'label': r['label'],
                'mode': r['mode'],
                'topic': r['topic'],
                'deliverable': r.get('deliverable', ''),
                'eval_scores': r.get('eval_scores', []),
            }
            for r in successful if r.get('deliverable')
        ],
        'failed_sessions': failed,
    }


def generate_summary(report):
    """Generate a human-readable markdown summary."""
    lines = [
        "# 🏥 Healthcare LLM Innovation Report",
        "",
        "> Autonomous 10-Hour Brainstorming Marathon",
        "",
        f"**Generated:** {report['generated_at']}",
        f"**Total Sessions:** {report['total_sessions']} ({report['successful_sessions']} successful, {report['failed_sessions']} failed)",
        f"**Total Time:** {report['total_time']}s ({report['total_time_hours']}h)",
        "",
        "---",
        "",
        "## 📊 Summary by Phase",
        "",
        "| Phase | Sessions | Deliverables |",
        "|---|---|---|",
    ]
    
    phase_names = {
        'exploration': '🔍 Exploration',
        'design': '🎨 Design',
        'sprint': '📝 Sprint',
        'reflection': '🔎 Reflection',
        'redesign': '🔧 Redesign',
        'final': '✨ Final',
    }
    
    for phase_key, phase_name in phase_names.items():
        sessions = report['by_phase'].get(phase_key, [])
        deliverables = [s for s in sessions if s.get('deliverable')]
        lines.append(f"| {phase_name} | {len(sessions)} | {len(deliverables)} |")
    
    lines.extend(["", "---", ""])
    
    # Full deliverables
    for phase_key, phase_name in phase_names.items():
        lines.extend([f"## {phase_name}", ""])
        
        for d in report['by_phase'].get(phase_key, []):
            if d.get('deliverable'):
                lines.extend([
                    f"### {d['label']}",
                    "",
                    f"**Topic:** {d['topic']}",
                    "",
                    d['deliverable'],
                    "",
                    "---",
                    "",
                ])
    
    return "\n".join(lines)


if __name__ == '__main__':
    asyncio.run(run_marathon())
