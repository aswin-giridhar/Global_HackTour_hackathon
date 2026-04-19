# Anchor

**A companion that holds memory for people who are losing theirs.**

Built for the Global AI HackTour · London 2026 · **Track 2 (Inclusion)** by team **404-Team-Not-Found**.

🔗 **Live demo:** <https://anchor-uguz.onrender.com>
🔒 **Carer demo console** (reset + trigger agentic insight): <https://anchor-uguz.onrender.com/demo?key=shortbread>

---

## Why Anchor exists

Margaret is 74. She lives alone in Salford. Last year she was diagnosed with early-stage Alzheimer's.

Her daughter Priya calls on the way to work. Priya has two kids of her own, and her own job, and every evening when she opens her phone there are twelve missed calls from Mum. Asking the same three questions.

> *What day is it. When are you coming. Where is Robert.*

Robert is Margaret's husband. He died in 2019.

Every carer we spoke to told us the same thing: it isn't the memory loss that breaks them. It's being the only answer. Being the one who has to repeat *"Dad died in 2019"* at three in the morning because Mum asked again. Being the only person who knows when tea is and which blanket is the blue one.

**Anchor is built so Priya doesn't have to be.**

It answers only from Margaret's own profile — her family, her routine, her calendar, her preferences. It never invents a fact. It never corrects a painful truth. And when Margaret is drifting in a way that Priya needs to know about, a second quiet agent tells her.

> *"Anchor doesn't help Margaret remember. It remembers for her, so she can keep being herself."*

---

## What it does

Anchor is two apps that share one brain.

### Margaret's app (patient surface)
- One soft amber circle. No menus, no tabs, no notifications she didn't ask for.
- Three input paths: **voice** (browser SpeechRecognition), **four cushion buttons** for the most-asked questions, and **type** (long-press or double-click the ring).
- Warm replies in a grandchild-grandparent tone, 1–3 short sentences, spoken back via ElevenLabs (with browser TTS as a fallback).
- A daily brief card: today's day, next event, whether the morning medicine has been taken.
- Proactive reminders for medication, meals, and water — with a soft chime before the spoken reminder so it doesn't startle.
- Family portraits page (real photos if uploaded; stylised watercolour fallback) with tap-to-call buttons and recorded voice messages from each relative.
- A privacy disclosure page that is honest about the prototype stage.

### Priya's app (carer dashboard)
Seven tabs, mobile-first, designed to fit on one phone screen:

| Tab | What it shows |
|---|---|
| **Alerts** | Live notifications from Anchor, staggered by urgency (high / gentle / insight) |
| **Medicine** | Today's morning + evening doses, mark-as-taken controls |
| **Conversations** | Every recent exchange with filter chips for `All / Rule-blocked / Critic-blocked / Escalated`. This is where the safety rail becomes visible. |
| **Memory** | Read-only view of Margaret's profile (family, routine, preferences, care notes, life story). Open-gap queue with "Mark as resolved". |
| **Schedule** | Edit routine times; paste a Google Calendar ICS URL for live sync. |
| **Family** | Upload/replace/delete photos and voice messages; preview full-size photo in a lightbox; play the voice clip before replacing. |
| **Insights** | Seven-day stats — conversations, repetition rate, refusal rate, medication adherence. |

---

## How it stays safe (the differentiator)

The single most important thing Anchor does is **refuse gracefully** instead of **answer confidently**. Three layers guard every word Margaret hears:

### 1. Grounded-only prompting
The LLM sees a structured memory block — Margaret's profile, the last three turns, the current time, the next scheduled event — and is instructed to answer *only* from that block. If the profile doesn't contain the answer, the model returns a fixed warm refusal: *"I don't have that written down, love. Shall we ask Priya?"*

### 2. Rule-based hallucination check (fast, always runs)
Every reply is scanned for mid-sentence capitalised words. Any that don't appear in the memory block trigger rejection — the reply is swapped for the refusal template and the gap is logged for Priya. Sentence-initial words are skipped so normal English ("Sounds like a long day, love") passes through.

### 3. LLM critic at temperature zero (slower, high-risk only)
On utterances matching a small high-risk vocabulary (*robert, medicine, scared, fell, help, pill…*), a second LLM call at temperature 0 reads the proposed reply and returns `{"approved": true|false, "reason": "..."}`. It blocks painful-truth corrections (e.g. anything that tells Margaret her husband has died), medical advice, and semantic hallucinations the regex can't catch.

If either layer blocks a reply, the turn is logged with `rejected_by: "rule"|"critic"` so Priya can see it on the Conversations tab. **Nothing Anchor says to Margaret is un-reviewable.**

---

## Noticing for Margaret (a second agent)

People with dementia often can't notice their own drift — the accumulating anxiety of asking the same question eight times without realising it. A product that only *responds* leaves them alone with that drift. So alongside the conversation path, Anchor runs a **deterministic observation agent** that never touches the LLM:

```
Margaret speaks → log the turn → extract any living family member named
     ↓
Has she mentioned this person 3+ times in the last 6 hours?
     ↓ (yes)
Is there a calendar event for them in the next 7 days? (static profile OR live ICS)
     ↓ (no)
Has this signal fired for this person in the last 12 hours?
     ↓ (no)
Fire a "Pattern insight" to Priya's dashboard:
  "Margaret has asked about Priya 4 times in the last 6 hours,
   but there's no visit or call for her on the schedule for the
   next 7 days. A short call might help."
```

Deceased family members are filtered at record-time, so the agent cannot fire a tragic "*Margaret keeps asking about her husband*" notification. The loop is **observe → store → retrieve → compare → decide → act** with no LLM in the path — every step is auditable end-to-end.

---

## Architecture

```
┌────────────────────────────── Patient phone ─────────────────────────────┐
│  Vanilla HTML/CSS/JS · PWA (service worker, manifest, installable)       │
│  Voice (webkitSpeechRecognition)  ·  Text (long-press ring)  ·  Buttons  │
│  Geolocation (foreground watchPosition → Haversine geofence)             │
└───────────────────────────────────┬──────────────────────────────────────┘
                                    │  POST /api/speak (and friends)
                                    ▼
┌──────────────────────── FastAPI · backend/main.py ───────────────────────┐
│                                                                           │
│  agent.respond_to_margaret()                                              │
│      ├─ memory.get_relevant_memories    (keyword retrieval over profile)  │
│      ├─ calendar_integration.get_live_events  (Google Calendar ICS, 60s)  │
│      ├─ _llm_call  →  GLM-4.5 primary  ──(429)──▶  Claude Sonnet 4.5      │
│      │                                    (latched per process)           │
│      ├─ escalation detection  →  fire_escalation                          │
│      ├─ verify_grounded       (rule-based regex, fast)                    │
│      ├─ verify_with_critic    (2nd LLM · temperature 0 · high-risk only)  │
│      ├─ voice.synthesize_speech  →  ElevenLabs  (MD5-hash-cached)         │
│      └─ patterns.record_and_check   (agentic observation agent)           │
│                                                                           │
│  Data (all JSON, auto-created on startup):                                │
│    data/conversation_log.json        rejected_by tags                     │
│    data/carer_notifications.json     urgency: high / gentle / insight     │
│    data/profile_update_suggestions.json    BrowseBack-lite gap queue      │
│    data/medication_log.json          data/behavior_log.json               │
│    data/query_patterns.json          data/pattern_fired.json              │
│    data/location.json                data/ics_config.json                 │
│                                                                           │
└───────────────────────────────────┬──────────────────────────────────────┘
                                    │  GET /api/carer/notifications (2s poll)
                                    ▼
┌────────────────────────── Carer phone ──────────────────────────────────┐
│  Seven-tab dashboard · live polling · notification chime                │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key files

- `backend/agent.py` — the conversation pipeline, safety rails, dual-LLM fallback
- `backend/patterns.py` — the agentic observation agent
- `backend/calendar_integration.py` — Google Calendar ICS → live schedule (no OAuth)
- `backend/escalation.py` — Concept 10 (SOAN-Lite) urgency classifier + notification writer
- `backend/memory.py` — profile retrieval, conversation log, BrowseBack-lite
- `frontend/index.html` + `frontend/patient.js` — Margaret's app
- `frontend/carer.html` — Priya's dashboard (seven tabs, one file)
- `frontend/sw.js` + `frontend/manifest.webmanifest` — PWA shell caching

### Research concepts implemented

From the build plan at `../docs/anchor_concepts.md`, all four research concepts are in the shipping code:

| Concept | Where it lives |
|---|---|
| **Concept 8** — BenchBreak: environment-aware recall | `calendar_integration.py` (live ICS) + static scheduled_events |
| **Concept 10** — SOAN-Lite: graded urgency | `escalation.classify_urgency()` — `high` / `gentle` / `insight` |
| **Concept 11** — Consensus: critic verification | `agent.verify_with_critic()` at temperature 0 |
| **Concept 12** — BrowseBack-lite: memory-gap logging | `memory.log_profile_gap()` + Memory-tab resolution queue |

---

## Running locally

### Preferred (uv)
```bash
cd anchor
cp .env.example .env              # Fill in GLM_API_KEY, ELEVENLABS_API_KEY, ANTHROPIC_API_KEY
uv sync                           # Install dependencies (pyproject.toml)
uv run uvicorn backend.main:app --reload --port 8000
```

### Fallback (pip + venv)
```bash
cd anchor
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

### URLs once the server is up
| URL | Who uses it |
|---|---|
| <http://localhost:8000/> | Margaret's app |
| <http://localhost:8000/carer> | Priya's dashboard |
| <http://localhost:8000/?demo=1> | Patient + carer overlay, for stage demos |
| <http://localhost:8000/demo> | Break-glass reset console (password-gated in production) |
| <http://localhost:8000/family>, `/music`, `/safety`, `/logs`, `/privacy` | Supporting patient/carer surfaces |

### Reset demo state
```bash
curl -X POST http://localhost:8000/api/reset           # Local (no auth)
uv run python scripts/reset.py                          # Same, from shell
uv run python scripts/seed_memory.py                    # Ensure data/ files exist
```

### Environment variables
| Key | Required? | Purpose |
|---|---|---|
| `GLM_API_KEY` | yes | Z.AI GLM-4.5 primary chat endpoint |
| `ANTHROPIC_API_KEY` | yes (in practice) | Claude Sonnet 4.5 fallback — engages on GLM rate-limit / auth / SSL failure |
| `ELEVENLABS_API_KEY` | optional | Natural TTS voice; falls back to browser SpeechSynthesis if absent |
| `DEMO_RESET_KEY` | optional | Gates `/demo` and `/api/reset` in production — set on Render only |

---

## Deployment

Anchor runs on [Render](https://render.com) via Blueprint (`render.yaml` at the repo root). Free tier, Frankfurt region, Python 3.12. Auto-deploys on push to `main`.

The `[FALLBACK] GLM unavailable` log line on first request is expected — our Z.AI hackathon credit ran out mid-event and every request now routes through Claude Sonnet 4.5. The fallback is latched per process and the response shape is preserved via a shim class, so callers don't branch on provider. This is the dual-LLM resilience story we'd planned to tell anyway; it just happens to be running for real.

---

## What Anchor is *not*

This section matters more than most of the above. Judges and clinicians will ask.

- **Not HIPAA / UK GDPR compliant.** It's a hackathon prototype with synthetic data. Shipping to a real patient requires UK ICO registration, a data-processing agreement with the LLM provider, encryption at rest, and a clinical safety case — a three-month programme in its own right. The `/privacy` page says this in plain English.
- **Not clinically validated.** We did not consult a geriatrician, OT, or dementia specialist nurse. Every dementia professional has scripted redirects for utterances we don't handle — sundowning ("*I need to go home*" when the patient is at home), visual hallucinations, specific Lewy-body or vascular patterns. We'd want at least one 30-minute conversation with someone from the Alzheimer's Society before shipping further.
- **Not a medical device.** Anchor will never give medical advice. It defers to "*Priya or the GP*" by prompt instruction and by critic enforcement.
- **Not a replacement for a carer.** It reduces the load — it doesn't remove it. The name *Anchor* was chosen deliberately to suggest "quiet presence" rather than "hands-free care."
- **Not personalisable beyond the profile JSON.** Editing Margaret's care notes, family notes, or meaningful memories requires editing `backend/patient_profile.json` directly. The Memory tab is read-only on the profile itself; a full in-app editor is post-hackathon work.
- **Not multi-patient.** One deployment, one Margaret. Multi-tenant architecture was out of scope.

---

## The team

**404-Team-Not-Found-HACKTOUR** — built over the HackTour London 2026 weekend (2026-04-17 → 2026-04-19).

Supporting docs:
- `../docs/anchor_build_plan.md` — engineering plan, day-by-day scope decisions, what we deliberately didn't build
- `../docs/anchor_concepts.md` — the four research concepts and how they map to code
- `../docs/hackathon_context.md` — inclusion framing, judging lens, demo choreography

---

## Credits and licensing

- Language models: **Z.AI GLM-4.5** (primary), **Anthropic Claude Sonnet 4.5** (fallback).
- Voice synthesis: **ElevenLabs** (TTS + Music API — gentle hymn, dance memory, evening calm).
- Family portraits: **Runware** SDXL watercolour generations (Priya, David, James).
- Deployment: **Render** (FastAPI web service on free tier).
- Typography: **Cormorant Garamond** (display) + **DM Sans** (UI), both via Google Fonts.
- Iconography: handcrafted in Pillow from the breathing-ring motif.

All patient data is synthetic. *Margaret* is a fictional persona designed with reference to publicly-available Alzheimer's Research UK statistics and carer testimony. No real patient was consulted, recorded, or represented in the building of this prototype.

---

*Anchor doesn't help Margaret remember. It remembers for her, so she can keep being herself.*
