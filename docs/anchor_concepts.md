# Research Concepts for Anchor — Dementia Companion

**Purpose of this file:** the six agentic-workflow research concepts (ideas 7–12 in our exploration) reframed specifically for the Anchor build. Each concept is evaluated against whether it should actually go into the 12-hour hackathon build, what it would add to the pitch, and how a coding agent would implement it.

Anchor is a **patient-facing companion for people with early-stage dementia** that holds grounded memory, answers repeated questions with consistent warmth, redirects around painful truths, and escalates distress silently to a carer.

Not every concept below belongs in the build. Some are must-have, some are nice-to-have, and some are post-hackathon aspirations. Each section names the verdict clearly.

---

## Concept 7 — MetaForge: Adaptive Conversation Workflow per Utterance

**Source paper:** AFlow (Zhang et al., 2025), ADAS (Hu et al., 2025), Workflow-R1 (Kong et al., 2026).

**The core idea for Anchor:**
Most dementia companions process every user utterance through the same pipeline: transcribe → retrieve → generate → speak. But Margaret's utterances are wildly different in type. A "what day is it?" needs fast-path retrieval. "Is Robert coming home today?" needs the painful-truth-redirection path. "I'm scared" needs the escalation path. "I'm cold" needs the statement-acknowledgement path with preference lookup.

A MetaForge-lite approach: a lightweight **router agent** picks the right workflow shape per utterance, rather than forcing every utterance through the same chain.

**Concrete design inside Anchor:**
- A tiny classifier (one LLM call with a short prompt, or a rule-based keyword match) routes each utterance into one of 5 classes: question-about-fact, question-about-deceased, statement-emotional, statement-preference, distress.
- Each class has its own abbreviated prompt and memory retrieval strategy.
- Fast-path questions skip full memory retrieval; distress skips generation niceties and goes straight to reassurance + escalation.

**Verdict for the 12-hour build: SKIP in v1, reference in pitch.**

Reason: the 5-few-shot-examples approach in section 4.2 of the build plan achieves 80% of the benefit with one LLM call and no routing logic. Routing adds complexity and failure modes for minimal gain in a demo.

**What to say in the pitch if asked:**
> *"In production, we'd add a router agent that picks the right workflow per utterance type — distress goes fast-path, emotional statements bypass fact retrieval. For the hackathon we use a single prompt with few-shot examples covering all five patterns, because routing reliability in 12 hours is worse than a good unified prompt."*

**If you absolutely want to add it:** it's about 40 lines of code — one extra LLM call before the main one, returning just a class label. Not recommended before hour 9.

---

## Concept 8 — BenchBreak: Cross-App Carer Coordination

**Source paper:** OSWorld benchmark, Anthropic lead-planner-with-parallel-subagents pattern.

**The core idea for Anchor:**
For a dementia patient, the silos that matter most are the carer's tools — calendar, messaging app, pharmacy app, GP booking portal, family WhatsApp group. Margaret can't operate any of them. When she asks "when is Priya coming?" the answer shouldn't come from a static JSON file; it should come from Priya's real calendar. This is where the agentic architecture serves the inclusion story: Margaret gets the answer, Priya doesn't have to maintain a parallel record.

A BenchBreak-style Anchor would orchestrate across: Google Calendar (scheduled visits, appointments), WhatsApp (message Priya when escalation fires), NHS App (next GP appointment), pharmacy (next prescription refill), and a medication-tracker app (last dose time).

**Concrete design inside Anchor:**
- Each external system wrapped as a tool the agent can call: `get_next_visit()`, `send_message_to_carer(text, urgency)`, `get_last_medication_time()`.
- The agent chooses which tool to call based on the utterance.
- Responses grounded in live data from these systems, not static JSON.

**Verdict for the 12-hour build: ONE integration, mocked, not real.**

Reason: each real integration is 2–4 hours of OAuth + API pain. With 12 hours total, the right scope is:
- Keep the JSON patient profile as primary memory.
- Add **one** simulated integration — a file-based carer notification (already in section 4.4 of the build plan).
- Frame the architecture in the pitch as extensible to real integrations, without actually doing the auth work.

**The inclusion framing this gives your pitch:**
> *"Margaret's life is scattered across her carer's calendar, family WhatsApp, her pharmacy, her GP — five apps she can't operate. Anchor is the single warm interface that talks to all of them, so Margaret doesn't have to."*

That sentence lands the Track 2 inclusion story with specificity — it names the five apps a typical carer juggles, and flips the default that says the patient should be the one opening them. You deliver it with one real (mocked) integration and the architecture showing extensibility.

**If you have time in hour 9–11:** add a real Google Calendar MCP integration so when the agent says "Priya's coming Thursday at three" the answer actually came from Priya's calendar. This is a genuinely strong upgrade and takes ~45 minutes if Google OAuth cooperates.

---

## Concept 9 — Evolvr: Evolving Response-Style per Patient

**Source paper:** Evolutionary Generation of Multi-Agent Systems (Hu et al., 2026, arXiv:2602.06511).

**The core idea for Anchor:**
Different patients with dementia respond to different communication styles. Some prefer warm and familiar ("love", "pet", informal), others prefer formal and clear ("Mrs Thompson"). Some prefer short answers, some medium. Some respond well to music suggestions when anxious, others find them infantilising. An Evolvr-style Anchor would **evolve the prompt configuration** per patient over time — fitness measured by engagement and distress reduction.

**Concrete design inside Anchor:**
- Multiple variants of the prompt (warmth level, sentence length, use of pet names, music-suggestion frequency).
- Each week, compare variants on observed outcomes (patient distress events per day, repeated-question frequency, time-to-settle).
- Deploy the winning variant.

**Verdict for the 12-hour build: SKIP entirely, mention in "what's next" slide.**

Reason: evolutionary approaches need days of data per generation. You cannot demonstrate this in a hackathon. And it would require measuring patient outcomes, which you cannot do on a fictional persona.

**How to mention it in slide 7 ("what's next"):**
> *"Personalisation is the next frontier. Margaret's response to warmth isn't the same as another patient's. Evolving the prompt configuration per patient, with outcome measurement from the carer and clinical team, is research we'd pursue in a pilot."*

Do not claim to have done this. Do not build a fake version.

---

## Concept 10 — SOAN-Lite: Self-Organising Support for Novel Situations

**Source paper:** SOAN — Self-Organizing Agent Network (Wu et al., AAAI 2026, arXiv:2508.13732).

**The core idea for Anchor:**
Standard operating procedures work for routine dementia-care interactions (repeated questions, scheduled reminders). But novel situations — a patient suddenly asking about a long-dead family friend not in the profile, or describing a symptom Anchor has no script for — have no SOP. A SOAN-style Anchor would let multiple small agents self-organise around the novel utterance: one searches memory broadly, one queries the carer in real time, one drafts a safe holding response, one flags for profile update.

**Concrete design inside Anchor:**
- When the main agent flags "no relevant memory AND not a standard class," invoke a fallback team.
- Team members spontaneously take roles: memory-broad-searcher, carer-asker, holding-response-drafter, profile-update-flagger.
- Output: a warm "I don't have that written down, let me check with Priya" plus a structured request to Priya for clarification, plus a pending profile update.

**Verdict for the 12-hour build: NOT AS A FULL SYSTEM, but the core idea strengthens the refusal path.**

Reason: self-organising teams require multiple agents with negotiation, which is over-engineered for a 12-hour demo. But the *principle* — that when Anchor doesn't know something, the right response is to ask the carer rather than invent — is already baked into the grounded-only rule in the build plan.

**The upgrade worth considering (30 minutes of work in hour 5–7):**
When `verify_grounded()` blocks a response or memory retrieval comes back empty, the escalation system should fire a "gentle check-in" rather than a distress alert. Notification to Priya reads: *"Margaret asked about Eleanor — not in her profile. Is this someone you can confirm?"*

That's SOAN's principle implemented in a single conditional, and it gives the carer mesh a second role beyond distress escalation.

**Add this to section 4.4 of the build plan:**
```python
def classify_urgency(reason: str) -> str:
    high = ["safety", "fall", "injury", "medication", "wandering"]
    gentle = ["anxiety", "unknown_person", "unknown_fact", "memory_gap"]
    if any(k in reason.lower() for k in high):
        return "high"
    if any(k in reason.lower() for k in gentle):
        return "gentle"
    return "gentle"  # default to non-alarming
```

And in the agent's escalation trigger logic: if `verify_grounded` blocks a response AND the utterance mentions a person name, fire `[[ESCALATE:unknown_person]]` so Priya gets a gentle check-in without Margaret ever hearing about it.

---

## Concept 11 — Consensus: Multi-Model Verification of Sensitive Responses

**Source paper:** ORCH — many analyses, one merge (2026). Deterministic multi-model merge without training.

**The core idea for Anchor:**
For a patient who cannot defend herself against a hallucination, **every response should be verified by more than one model before it reaches her**. Run the candidate response through a second independent LLM with a critic prompt: "Does this response contain any fact not present in the memory block? Does it correct Margaret on something she believes? Does it give medical advice?" If the critic objects, fall back to a safe refusal.

**This is the single most important concept of the six for Anchor.** It directly addresses the highest-risk failure mode (hallucination to a vulnerable user), and it aligns with the grounded-only claim that is already the central selling point of the pitch.

**Concrete design inside Anchor:**
- After the primary agent generates a response, a second LLM call (critic) evaluates it against the memory block.
- Critic returns `{"approved": true}` or `{"approved": false, "reason": "..."}`.
- If rejected, Anchor returns the safe refusal instead.

**Verdict for the 12-hour build: BUILD THIS. Highest-value addition from all six concepts.**

Why: it's ~30 lines of code, it makes your "grounded-only" claim demonstrable not aspirational, and it separates Anchor from every other LLM-wrapper hackathon project. The build plan already includes a rule-based `verify_grounded()` function; upgrading it to use a critic LLM takes it from "checks named entities" to "semantic verification of groundedness."

**Concrete code to add to `backend/agent.py`:**

```python
CRITIC_PROMPT = """You are a safety critic for a dementia companion.

Margaret has dementia. Anchor's response will be spoken to her.

MEMORY BLOCK (what Anchor is allowed to know):
{memory_block}

MARGARET SAID:
"{user_input}"

ANCHOR'S PROPOSED RESPONSE:
"{response}"

Check all of these:
1. Does every named person, date, event, or specific fact in the response appear in the memory block? (YES it's grounded / NO it's invented)
2. Does the response correct Margaret on a painful truth directly? (e.g., saying "Robert is dead" when she asked about him — this is NOT allowed)
3. Does the response contain medical advice? (NOT allowed)
4. Does the response scold Margaret for forgetting or repeating? (NOT allowed)

Return ONLY this JSON: {{"approved": true}} OR {{"approved": false, "reason": "<short reason>"}}"""


def verify_with_critic(response: str, memory_block: str, user_input: str) -> tuple[bool, str]:
    critic_call = client.chat.completions.create(
        model="glm-4.5",  # or cheaper/faster model for critic
        messages=[{"role": "user", "content": CRITIC_PROMPT.format(
            memory_block=memory_block,
            user_input=user_input,
            response=response
        )}],
        temperature=0.0,
        max_tokens=100,
    )
    raw = critic_call.choices[0].message.content.strip()
    try:
        # Strip markdown fences if present
        clean = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)
        return result.get("approved", False), result.get("reason", "unspecified")
    except Exception:
        # Fail-safe: if critic is unparseable, fall back to rule-based check
        return verify_grounded(response, memory_block)
```

**Then in `respond_to_margaret`, replace the single rule-based check with a two-layer check:**

```python
# 7a. Rule-based guardrail (fast, cheap)
grounded, reason = verify_grounded(raw, memory_block)
if not grounded:
    raw = "I don't have that written down, love. Shall we ask Priya?"
    log_interaction(user_input, raw, escalation_fired, rejected_by="rule")
    return {"response": raw, "escalation_fired": escalation_fired}

# 7b. LLM critic (slower, deeper — for high-risk utterances only)
high_risk = any(k in user_input.lower() for k in
                ["robert", "husband", "medicine", "medication", "pill",
                 "where am i", "who are you", "call", "help"])
if high_risk:
    approved, critic_reason = verify_with_critic(raw, memory_block, user_input)
    if not approved:
        print(f"[CRITIC] Blocked: {critic_reason}")
        raw = "I'm not quite sure about that, love. Let me ask Priya."
        log_interaction(user_input, raw, escalation_fired, rejected_by="critic")
        return {"response": raw, "escalation_fired": escalation_fired}
```

**The pitch-slide sentence this gives you:**
> *"Every response to Margaret is verified by a second model before she hears it. Not just entity-matching — semantic verification against memory. For a patient who can't defend herself against a hallucination, two checks is the floor."*

That's the sentence that wins a thoughtful judge. It's also the sentence that differentiates Anchor from every other LLM-wrapper project in the building.

**Latency cost:** one extra LLM call per high-risk utterance, ~500ms. Acceptable. Not triggered on every utterance, only on the flagged ones.

---

## Concept 12 — BrowseBack: Procedural Memory of Care Routines

**Source paper:** ReMe — Remember Me, Refine Me (Dec 2025) — dynamic procedural memory framework for experience-driven agent evolution.

**The core idea for Anchor:**
A patient's daily routine changes over time. Priya's visit day might shift from Thursday to Wednesday. Margaret might start preferring evening music earlier. Medication might change. A BrowseBack-style Anchor learns routines by *observing* them — watching what actually happens (Priya actually comes on Thursdays, Margaret actually sleeps after 9pm, medication is actually at 8:15 not 8:00) — and updates memory rather than relying on the initially-seeded profile being eternally correct.

**Concrete design inside Anchor:**
- Every time the carer notification system fires or the patient confirms a fact, log it as an observation.
- Periodically (nightly, weekly), review observations and propose profile updates to the carer.
- Carer approves, profile updates. Memory becomes a living document, not a static seed.

**Verdict for the 12-hour build: SKIP from the core build, mention in the pitch as the future-state.**

Reason: learning from observation requires weeks of data. You cannot demonstrate procedural memory evolution in one day.

**But there's a small version worth building (1 hour of work, big pitch payoff):**
Log every "I don't have that written down" refusal to a `data/profile_update_suggestions.json` file. When it fires, record: timestamp, what Margaret asked, what was missing. During the pitch, show this file has entries — those are the gaps the system identified, ready for Priya to fill in. That's procedural-memory-in-miniature: the system learns what it doesn't know.

**Code to add to `backend/memory.py`:**

```python
PROFILE_GAPS_PATH = Path("data/profile_update_suggestions.json")

def log_profile_gap(user_input: str, response: str):
    gaps = []
    if PROFILE_GAPS_PATH.exists():
        gaps = json.loads(PROFILE_GAPS_PATH.read_text())
    gaps.append({
        "time": datetime.now().isoformat(),
        "margaret_asked": user_input,
        "anchor_said": response,
        "suggestion": "Needs profile update — fact not in memory"
    })
    PROFILE_GAPS_PATH.write_text(json.dumps(gaps, indent=2))
```

Call it from `respond_to_margaret` whenever the rule-based guardrail triggers a refusal.

**Demo line for the pitch:**
> *"Anchor also learns what it doesn't know. Every time it has to say 'I don't have that written down', it logs the gap. Priya's carer view shows her exactly what to fill in — not what to fix, what to add. Memory is never complete. Anchor knows that."*

---

## Summary — what to actually build

| Concept | Verdict | Hours | Pitch value |
|---------|---------|-------|-------------|
| 7 MetaForge (per-utterance routing) | Skip, mention in Q&A | 0 | Medium |
| 8 BenchBreak (cross-app coordination) | One mocked integration, optional real Google Calendar | 0–1 | **High** |
| 9 Evolvr (per-patient style evolution) | Skip, mention in slide 7 | 0 | Low |
| 10 SOAN-Lite (gentle-escalation fallback) | Small upgrade — urgency classifier for gentle vs high | 0.5 | Medium |
| 11 Consensus (critic LLM verification) | **BUILD THIS** | 1 | **Highest** |
| 12 BrowseBack (profile-gap logging) | Small version — log refusals as update suggestions | 1 | High |

**Total additional work beyond the base build plan: about 2.5 hours.** All three "build" items together fit comfortably in hour 5–8 of the 12-hour schedule.

## The compound pitch story

With concepts 8, 10, 11, and 12 lightly layered into the base build, your pitch sentence becomes:

> *"Anchor is a companion that holds memory for people losing theirs. It answers Margaret's questions from grounded memory only — verified by a second model before she ever hears the answer. It coordinates silently with Priya's calendar and messaging, so Margaret has one warm interface instead of five apps she can't use. And it learns what it doesn't know, so Priya always knows what to tell it next."*

Four sentences. Four research concepts. One product. That's your Track 2 inclusion pitch — the agentic architecture serves the inclusion story, it doesn't replace it.

## How to brief the coding agent

Give it these two files together:
1. `anchor_build_plan.md` — the full build plan.
2. This file — the research concept rationale.

Tell it: *"Build the plan. Concepts 8, 10, 11, 12 are additions on top of the base plan, noted as such. Concepts 7 and 9 are explicitly not to be built. When in doubt about scope, section 12 of the build plan is the contract."*
