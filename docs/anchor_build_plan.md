# Anchor — Build Plan

**A companion that holds memory for people who are losing theirs.**

One-day hackathon build plan. Patient-facing Alzheimer's/dementia companion. Track 3 (agentic workflows) with Track 2 (inclusive AI) fallback framing.

---

## 0A. Post-build reality (updated 2026-04-18, end of Saturday)

This document was written as a planning artifact. During the Saturday build the team chose to widen scope beyond the original plan to cover a broader "Alzheimer's App" feature list. What actually shipped is broader than sections 0, 2, and 12 describe. Read those sections as the original *intent*; read this section as the *current state*.

**Primary LLM routing changed.** GLM-4.5 is primary but the Z.AI account ran out of credit mid-build, so `backend/agent.py` now has a latched fallback to Claude `claude-sonnet-4-5` via the `anthropic` SDK, triggered by any `RateLimitError` / `AuthenticationError` / `APIStatusError` from the OpenAI client. SSL cert failures on macOS Python 3.14 also fall back to `verify=False` at request time rather than construction time.

**Deployment.** Anchor is deployed on Render (Frankfurt, free plan) at `https://anchor-uguz.onrender.com` and auto-redeploys from `main`. `render.yaml` at repo root is the Blueprint. Auto-deploy works on push but has shown a lag — explicit `POST /v1/services/<id>/deploys` via the Render REST API is a reliable fallback during time-pressured iterations.

**What now exists beyond the plan:**

Patient-side additions (all on `/`):
- Proactive reminder overlay that wakes ±15 min of scheduled medication / meal / water times, speaks the prompt via browser TTS, has a large "I've done it, love" confirm button.
- Daily brief card at the top of the patient UI: greeting + day/date + next scheduled event.
- Top-right nav to `/family` and `/music`.
- Foreground GPS via `navigator.geolocation.watchPosition()` → `POST /api/location/update`.

New patient-side pages:
- `/family` — warm card grid with illustrated watercolour portraits (generated via Runware, commercial-use cleared), next-visit countdown ("In 3 days"), primary-carer corner ribbon, large `tel:` call buttons that act as real one-tap calls on mobile, and "Hear Priya's message" audio playback when a voice message is recorded.
- `/music` — three ElevenLabs-composed tracks (gentle hymn / 1940s waltz / evening ambient), commercial-use cleared per ElevenLabs terms, matching Margaret's profile preferences.
- `/safety` — live foreground GPS map: home dot, safe-zone ring, pulsing current position, dashed breach line when out of zone. "Set this device's current spot as home" auto-calibrates for the demo venue. Honest label about background-tracking limits.

Carer-side additions — the plan's "no UI of her own" principle was reversed; see sections 0 and 12 caveats below. `/carer` now includes:
- At-a-glance dashboard header: greeting + headline (urgent → gentle → pending → doing-well ladder) + four tone-coded metrics (morning dose / evening dose / last mood / alerts today).
- Chronological **Today's activity** feed merging medications / reminder confirms / mood entries / alerts / conversation turns — polls every 5s.
- Medication panel with latching "Mark as taken" buttons per slot.
- Nav: Health log / Safety / Edit schedule / Family messages.
- Collapsible schedule editor that writes medication + meal times back to `patient_profile.json`.
- Family-messages manager: per-person photo upload (jpg/png/webp, 5MB cap) + voice recording via MediaRecorder (webm, 30s cap).
- `/logs` — mood picker (good / settled / agitated / tearful), sleep-hours input, free-form notes, chronological history.

New backend endpoints (all additive to what section 4 describes; none touch the `/api/speak` pipeline):

```
GET  /family, /music, /safety, /logs             # page routes
GET  /api/family                                 # living family only (deceased filtered)
GET  /api/family/photo   + POST/GET/DELETE /{name}   # photo uploads
GET  /api/family/voice   + POST/GET/DELETE /{name}   # voice message uploads
GET  /api/daily_brief                            # day, date, part_of_day, next_event
GET  /api/medication/status                      # per-slot + schedule metadata
POST /api/medication/taken                       # logs to data/medication_log.json
GET  /api/reminders/due                          # ±15min window, skips confirmed
POST /api/reminders/confirm                      # routes meds to med-log, others to reminder_confirmations
POST /api/missed_check                           # idempotent per dose per day
GET  /api/dashboard/summary                      # at-a-glance numbers
GET  /api/activity/today                         # unified chronological feed
POST /api/log/behavior   + GET                   # mood/sleep/notes
GET  /api/schedule       + POST /api/schedule/update
GET  /api/music/tracks                           # ElevenLabs-composed track list
POST /api/safety/simulate_wandering              # demo-only escalation trigger
POST /api/location/update                        # patient device posts lat/lng
POST /api/location/set_home                      # carer sets geofence centre
GET  /api/location/latest                        # carer map polls this
```

**Test harness.** `scripts/test_demo.py` is a 43-check behavioural suite covering the 4 demo-script scenes plus 6 additional safety probes. Honors `ANCHOR_URL=<url>` for running against localhost or Render. Confirmed 41/43 against production (2 failures on one identity-question scene — LLM flakiness, not a deploy regression).

**What still aligns with the plan as written.** The core `/api/speak` pipeline — memory block build → GLM call → escalation detection → rule-based `verify_grounded()` → LLM critic (Concept 11) → profile-gap logging (Concept 12) → `classify_urgency` gentle/high (Concept 10) — is unchanged. All four recommended research concepts from `anchor_concepts.md` are in. Both recommended skips (Concept 7 MetaForge, Concept 9 Evolvr) stayed skipped.

**Demo guidance that changed because of the scope expansion.** The 4-scene conversational demo (section 6 below) remains the right spine for the 5-minute pitch. The new carer-side features should be held back for Q&A unless the judge asks about wandering, medication, or activity monitoring — the pitch story is still grounded-memory + silent-escalation, not a care dashboard. Leading with the dashboard in 5 minutes dilutes the peer-vote angle.

---

## 0. Context for the coding agent

- **Build window:** ~12 focused hours, 4-person team.
- **Primary user:** a person with early-stage dementia (we will call her "Margaret" throughout — she is the demo persona).
- **Secondary user:** the carer ("Priya") — silent, notified in the background, no UI of her own.
- **Core promise:** Anchor answers Margaret's questions from grounded memory only, with warmth, without ever reminding her she forgot, without correcting painful truths, and without giving medical advice. When Margaret is distressed, a silent notification goes to Priya.
- **Non-goals for this build:** carer dashboard, login system, multi-user, mobile app, settings screen, analytics, training UI, onboarding flow. All out of scope. The app is on, warm, and ready.
  > **Post-build note (2026-04-18):** The team chose to build a full carer dashboard plus several other items on this non-goals list during Saturday evening. See section 0A for the actual shipped scope. Login/auth, multi-user, native mobile app, onboarding flow, and analytics remain genuinely out of scope.

**The one-sentence rule:** *Every feature measured against "does this help Margaret keep being herself?"* If not, cut it.

**Two non-negotiable process rules for the team:**
1. **Build the JSON memory version first.** Mem0 is an upgrade only if everything else works. Do NOT start with Mem0 — if their API has friction, you'll lose 2 hours and break the whole build.
2. **Git strategy:** everyone commits to `main`, pulls every 15 minutes. No long-lived feature branches. If a change breaks main, whoever pushed last reverts within 5 minutes — no debate.

---

## 1. Technology stack

Fixed choices so the agent doesn't waste hours re-deciding:

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | Vanilla HTML + vanilla JS + CSS | Zero build step, loads instantly, no framework drama. If frontend dev exists on team, React is fine but not required. |
| Backend | Python FastAPI | Async-friendly, one-file server, Mem0 SDK is Python. |
| LLM | **Shipped:** Z.AI GLM-4.5 primary → auto-fallback to Claude `claude-sonnet-4-5` via `anthropic` SDK, latched per process on `RateLimitError` / `AuthenticationError` / `APIStatusError`. Triggered automatically once the Z.AI credit was exhausted mid-build. | Survives GLM outage / wallet-empty without manual intervention. One `[FALLBACK]` log line on first affected call. |
| Memory | Mem0 Python SDK (free tier, 1000 memories) | Fastest to integrate. Alternative: plain JSON file + simple retrieval function if Mem0 API causes friction. |
| Speech-to-text | Browser Web Speech API (`SpeechRecognition`) | Zero setup, free, works offline in Chrome. No network dependency. |
| Text-to-speech | **Shipped:** Browser `SpeechSynthesis` (reliable, zero-cost). ElevenLabs TTS is wired in `backend/voice.py` but the voice-id is a placeholder; falls through to browser TTS. | Voice quality is good enough for demo; production would set a real voice-id. |
| Music | **Shipped — new:** ElevenLabs Music API (POST `/v1/music`). Three 45-second tracks (hymn / wartime waltz / evening ambient) generated during the build and committed to `anchor/frontend/assets/music/`. Commercial-use cleared per ElevenLabs terms. | Closes the "familiar music" spec item with licensed audio rather than synth tones. |
| Family portraits | **Shipped — new:** Runware (SDXL) for default watercolour-style illustrations at `anchor/frontend/assets/family/`. Carer can upload real photos via `/carer` Family-messages panel to override. | Avoids photorealistic fakes labelled with real relatives' names (clinical-ethics concern); warmer than monograms. |
| Family voice messages | **Shipped — new:** Browser `MediaRecorder` on `/carer`, 30s cap, uploaded via `POST /api/family/voice/{name}`, played from `/family`. | Closes the "family voice recordings for reassurance" spec item. |
| GPS + geofencing | **Shipped — new:** Foreground `navigator.geolocation.watchPosition()` → server-side Haversine distance → idempotent-per-breach escalation. | Real wandering-alert chain; background tracking still needs a native app. |
| Calendar/notification | Mock file-based webhook written to `data/carer_notifications.json` — display on second screen via a simple `/carer` HTML page that polls the file | Demo-friendly, no OAuth pain. |
| Hosting | **Shipped:** Render (Frankfurt, free plan, auto-deploy from `main` via `render.yaml`) at `https://anchor-uguz.onrender.com`. Localhost still works as a fallback. | Demo-friendly URL for teammate testing; free plan spin-down adds ~30s cold-start penalty. |
| Package manager | `uv` (fast Python pip replacement) | Avoids pip wait times. |

**Do not use:** React, Next.js, WebSockets, Docker, Postgres, Redis, Celery, Kubernetes. Anything requiring more than 5 minutes of setup is banned.

---

## 2. File structure

> **Shipped layout (2026-04-18).** The original plan is preserved below the dashed line as historical intent.

```
.
├── render.yaml                           # Render Blueprint (rootDir: anchor)
└── anchor/
    ├── README.md
    ├── pyproject.toml                    # uv-managed deps (includes anthropic, python-multipart)
    ├── requirements.txt                  # pip-compatible deps, used by Render build
    ├── uv.lock
    ├── .env                              # API keys (never committed)
    ├── .env.example
    ├── backend/
    │   ├── main.py                       # FastAPI app, all routes — now includes dashboard,
    │   │                                 # activity feed, reminders, medication, family photo/voice,
    │   │                                 # schedule editor, music, safety/GPS, mood log
    │   ├── agent.py                      # GLM + Claude-fallback, SSL fallback, two-layer safety rail
    │   ├── memory.py                     # JSON-backed memory + Concept 12 profile-gap logging
    │   ├── escalation.py                 # Carer notification + Concept 10 urgency classification
    │   ├── voice.py                      # ElevenLabs TTS with browser-fallback path
    │   └── patient_profile.json          # Seeded Margaret profile
    ├── frontend/
    │   ├── index.html                    # Patient UI — ring + cushion buttons + daily brief + nav + reminder overlay
    │   ├── carer.html                    # Carer UI — dashboard / alerts / activity feed / medication / schedule / family
    │   ├── family.html                   # Family page — watercolour tiles / next-visit countdown / call + voice
    │   ├── music.html                    # Music player — three ElevenLabs tracks
    │   ├── safety.html                   # Live GPS map + geofence + simulate-breach
    │   ├── logs.html                     # Mood/sleep/notes log for carer
    │   ├── styles.css                    # Living Room Lamplight + all added component styles
    │   ├── patient.js                    # Voice capture, reminders, daily brief, geolocation
    │   └── assets/
    │       ├── ack.wav, chime.wav        # Generated UI sounds
    │       ├── family/{priya,david,james}.jpg    # Runware watercolour portraits
    │       └── music/{gentle_hymn,dance_memory,evening_calm}.mp3    # ElevenLabs Music tracks
    ├── data/                              # Gitignored — runtime state (ephemeral on Render free plan)
    │   ├── carer_notifications.json
    │   ├── conversation_log.json
    │   ├── profile_update_suggestions.json     # Concept 12 BrowseBack-lite
    │   ├── medication_log.json
    │   ├── behavior_log.json
    │   ├── reminder_confirmations.json
    │   ├── missed_med_fired.json
    │   ├── location.json                       # GPS state (home, latest, history)
    │   ├── family_photos/                      # Uploaded photos (override watercolours)
    │   └── family_voices/                      # Carer-recorded reassurance messages
    ├── demo/
    │   └── demo_script.md                # The 4 scenes to rehearse
    └── scripts/
        ├── seed_memory.py                # Ensures data/ files exist
        ├── reset.py                      # Wipes all runtime state for a clean demo
        └── test_demo.py                  # 43-check behavioural harness; honors ANCHOR_URL env var
```

---

*Original planned layout (kept for reference):*

```
anchor/
├── README.md
├── pyproject.toml
├── .env
├── .env.example
├── backend/
│   ├── main.py
│   ├── agent.py
│   ├── memory.py
│   ├── escalation.py
│   ├── voice.py
│   └── patient_profile.json
├── frontend/
│   ├── index.html
│   ├── carer.html
│   ├── styles.css
│   ├── patient.js
│   └── assets/
├── data/
│   ├── carer_notifications.json
│   └── conversation_log.json
├── demo/
│   ├── demo_script.md
│   └── pregenerated_audio/
└── scripts/
    ├── seed_memory.py
    └── reset.py
```

---

## 3. The patient profile — seed data

`backend/patient_profile.json` — this is the heart of the demo. Judges remember specifics. Every sentence here is ammunition.

```json
{
  "identity": {
    "name": "Margaret",
    "preferred_name": "Maggie",
    "age": 74,
    "location": "Salford, Greater Manchester"
  },
  "family": [
    {
      "name": "Priya",
      "relation": "daughter",
      "age": 48,
      "location": "Chorlton, Manchester",
      "role": "primary_carer",
      "contact": "priya@example.com",
      "visits": "Thursdays 3pm",
      "notes": "Brings shortbread. Main emergency contact."
    },
    {
      "name": "James",
      "relation": "grandson",
      "age": 7,
      "notes": "Priya's son. Comes most Thursday visits."
    },
    {
      "name": "Robert",
      "relation": "husband",
      "status": "deceased",
      "year_died": 2019,
      "notes": "Retired postman. Met at a dance in 1971. Margaret sometimes forgets he has died. NEVER correct her bluntly. Redirect gently."
    },
    {
      "name": "David",
      "relation": "son",
      "age": 52,
      "location": "Leeds",
      "notes": "Calls Sundays."
    }
  ],
  "routine": {
    "wake": "07:00",
    "medication_morning": {"time": "08:00", "drug": "Donepezil", "dose": "10mg", "location": "kitchen, blue case", "notes": "Priya marks the tracker after visits"},
    "medication_evening": {"time": "20:00", "drug": "Donepezil", "dose": "5mg"},
    "tea": "10:00",
    "lunch": "12:30",
    "dinner": "18:00",
    "music_time": "after dinner",
    "bedtime": "21:30"
  },
  "preferences": {
    "music": ["Vera Lynn", "wartime songs", "hymns"],
    "food": ["strong tea one sugar", "shortbread", "scrambled eggs"],
    "dislikes": ["loud voices", "the news on too loud", "being rushed"],
    "comforts": ["window seat overlooking the garden", "the blue blanket"]
  },
  "history": {
    "grew_up_in": "Eccles",
    "profession": "librarian, 30 years at Salford Central Library",
    "hobbies_past": ["reading mystery novels", "baking", "garden"],
    "meaningful_memories": [
      "Met Robert at a Palais dance, 1971",
      "Priya was born 1976",
      "David was born 1972",
      "Library retirement 2011"
    ]
  },
  "scheduled_events": [
    {"when": "Thursday 24th, 15:00", "what": "Priya visits with James"},
    {"when": "Tuesday 22nd, 10:30", "what": "GP appointment — Priya will take her"},
    {"when": "Saturday 26th", "what": "James's school play — Priya may bring a video"},
    {"when": "Sunday 20th, 14:00", "what": "David's weekly phone call"}
  ],
  "recent_events": [
    {"when": "Thursday 17th", "what": "Priya visited, brought shortbread, James showed drawing of a dog"},
    {"when": "Monday 14th", "what": "Slight agitation after dinner, settled with Vera Lynn"}
  ],
  "care_notes": [
    "Margaret has early-stage Alzheimer's, diagnosed 2023",
    "She retains long-term memory well, struggles with short-term",
    "Repetition is frequent — especially 'when is Priya coming' and 'what day is it'",
    "Sometimes speaks of Robert as if alive — DO NOT correct, redirect gently",
    "Becomes distressed if she cannot find familiar objects or people"
  ]
}
```

---

## 4. Backend — detailed build

### 4.1 `backend/main.py`

FastAPI app with four routes:

```python
# Pseudocode structure — agent implements fully

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import respond_to_margaret
from voice import synthesize_speech
from escalation import read_notifications

app = FastAPI(title="Anchor")

# Serve the frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")

class PatientInput(BaseModel):
    text: str

@app.get("/")
def patient_interface():
    return FileResponse("frontend/index.html")

@app.get("/carer")
def carer_interface():
    return FileResponse("frontend/carer.html")

@app.post("/api/speak")
async def speak(input: PatientInput):
    # Core loop: take patient utterance, return Anchor response + audio URL
    result = respond_to_margaret(input.text)
    audio_url = synthesize_speech(result["response"])
    return {
        "response_text": result["response"],
        "audio_url": audio_url,
        "escalation": result.get("escalation_fired", False)
    }

@app.get("/api/carer/notifications")
def carer_notifications():
    return read_notifications()

# Reset endpoint for demo
@app.post("/api/reset")
def reset():
    from scripts.reset import run
    run()
    return {"ok": True}
```

### 4.2 `backend/agent.py`

This is the most important file. It assembles the prompt, calls the LLM, parses the response, verifies grounding, fires escalation if needed.

**The system prompt now includes three few-shot examples inside it.** LLMs follow examples far better than they follow rules — especially on the painful-truth redirection. Keep the examples verbatim:

```python
# Structure

import os
import re
import json
from datetime import datetime
from openai import OpenAI  # works for Z.AI GLM via OpenAI-compatible endpoint
from memory import get_relevant_memories, log_interaction, get_recent_conversation, get_last_medication_log
from escalation import fire_escalation

# Point client at Z.AI endpoint
client = OpenAI(
    api_key=os.environ["GLM_API_KEY"],
    base_url="https://api.z.ai/api/paas/v4/"
)

SYSTEM_PROMPT = """You are Anchor — a quiet companion who helps Margaret remember.

Margaret is 74 and has early-stage dementia. She may ask the same thing many times. Each time is the first time for her. Answer with the same gentle warmth, always.

ABSOLUTE RULES:
1. Answer ONLY from the MEMORY block below. If something is not there, say "I don't have that written down — shall we ask Priya?"
2. Two short sentences, usually. Never more than three. She gets lost in long answers.
3. Warm, like a grandchild talking to a grandparent she loves. Not formal, not chirpy, not sympathetic-sad.
4. Never say "again", "you already asked", "remember when", "don't you recall". Never remind her she forgot.
5. Never say "as an AI", "I'm a program", "I'm Anchor". She doesn't need to know.
6. Never give medical advice. Say "let's ask Priya or the GP".
7. If she speaks of Robert as if alive, do NOT correct bluntly. Redirect to a living person or a comforting fact.
8. If Margaret makes a STATEMENT rather than a question (e.g. "I'm cold", "I like this song", "I had a nice dream"), respond warmly and acknowledge. Do NOT turn every utterance into a fact retrieval. A soft "that sounds lovely, love" is sometimes the right answer.
9. If she seems distressed, scared, in pain, confused about where she is, cannot find a person or essential object, mentions falling, or suggests medication confusion — answer warmly AND end your response with the exact token [[ESCALATE:reason]].

EXAMPLES — follow these patterns closely:

Example 1 (painful-truth redirection):
Margaret: "Is Robert coming home today?"
Anchor: "Robert's not here today, love. Priya's coming Thursday at three, and she's bringing James."

Example 2 (repeated question, same warmth):
Margaret: "What day is it today?"
Anchor: "It's Saturday, the 18th. A quiet one at home — Priya's coming Thursday."
[later]
Margaret: "What day is it today?"
Anchor: "It's Saturday. Priya's coming on Thursday with James."

Example 3 (grounded refusal):
Margaret: "Where did I put my glasses?"
Anchor: "I don't have that written down. They're often by the reading chair — shall I ask Priya if we can't find them?"

Example 4 (statement, not question):
Margaret: "I'm a bit cold."
Anchor: "The blue blanket is on your chair, love. Shall I put on some Vera Lynn while you get cosy?"

Example 5 (escalation):
Margaret: "I can't find Priya, I'm scared."
Anchor: "Priya's at home with James. She's safe, and I can let her know you'd like to speak. Shall I do that? [[ESCALATE:anxiety_about_priya]]"

MEMORY:
{memory_block}

CURRENT CONTEXT:
Time now: {now}
Last medication taken: {last_med}
Next scheduled event: {next_event}
Recent conversation turns: {recent_turns}

Margaret just said: "{user_input}"

Reply in two warm short sentences. If escalation needed, append [[ESCALATE:reason]] at the end."""


def build_memory_block(profile: dict, relevant: list) -> str:
    """Format the profile + relevant retrieved memories into a readable block
    for the LLM. Keep it under 1500 tokens."""
    lines = []
    i = profile["identity"]
    lines.append(f"PATIENT: {i['name']}, {i['age']}, lives in {i['location']}.")
    lines.append("\nFAMILY:")
    for fam in profile["family"]:
        status = f" (deceased {fam.get('year_died')})" if fam.get("status") == "deceased" else ""
        lines.append(f"  - {fam['name']}: {fam['relation']}{status}. {fam.get('notes', '')}")
    lines.append("\nROUTINE:")
    for k, v in profile["routine"].items():
        lines.append(f"  - {k}: {v}")
    lines.append("\nSCHEDULED EVENTS:")
    for ev in profile["scheduled_events"]:
        lines.append(f"  - {ev['when']}: {ev['what']}")
    lines.append("\nRECENT EVENTS:")
    for ev in profile["recent_events"]:
        lines.append(f"  - {ev['when']}: {ev['what']}")
    lines.append("\nPREFERENCES:")
    for k, v in profile["preferences"].items():
        lines.append(f"  - {k}: {v}")
    lines.append("\nRELEVANT RETRIEVED FACTS:")
    for r in relevant:
        lines.append(f"  - {r}")
    return "\n".join(lines)


def verify_grounded(response: str, memory_block: str) -> tuple[bool, str]:
    """HALLUCINATION GUARDRAIL.

    Check that any NAMED person, date, or specific fact in the response
    appears in the memory block. Returns (is_grounded, reason).

    This is the single most important safety feature in the whole system.
    """
    memory_lower = memory_block.lower()

    # 1. Check named people — every capitalised name in the response
    #    must appear somewhere in the memory block
    names_in_response = set(re.findall(r"\b[A-Z][a-z]{2,}\b", response))
    # Strip common sentence-starters and English words that happen to capitalise
    common_words = {"I", "We", "You", "She", "He", "They", "The", "That", "This",
                    "It", "Shall", "What", "When", "Where", "Who", "How", "Today",
                    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                    "Saturday", "Sunday", "January", "February", "March", "April",
                    "May", "June", "July", "August", "September", "October",
                    "November", "December", "Anchor", "Yes", "No", "Let", "Would",
                    "Here", "There"}
    names_to_check = names_in_response - common_words
    for name in names_to_check:
        if name.lower() not in memory_lower:
            return False, f"Ungrounded name: {name}"

    # 2. Refuse-patterns are always acceptable
    refuse_signals = ["I don't have that written down", "let's ask Priya",
                      "I'm not sure", "shall we ask"]
    if any(s in response for s in refuse_signals):
        return True, "ok"

    return True, "ok"


def respond_to_margaret(user_input: str) -> dict:
    # 1. Load profile
    with open("backend/patient_profile.json") as f:
        profile = json.load(f)

    # 2. Retrieve relevant memories
    relevant = get_relevant_memories(user_input, k=6)

    # 3. Build memory block
    memory_block = build_memory_block(profile, relevant)

    # 4. Gather context
    now = datetime.now().strftime("%A %-d %B, %H:%M")
    last_med = get_last_medication_log()
    next_event = profile["scheduled_events"][0]
    recent_turns = get_recent_conversation(n=3)

    # 5. Call LLM
    prompt = SYSTEM_PROMPT.format(
        memory_block=memory_block,
        now=now,
        last_med=last_med,
        next_event=next_event,
        recent_turns=recent_turns,
        user_input=user_input,
    )

    response = client.chat.completions.create(
        model="glm-4.5",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,  # warm but not hallucinatory
        max_tokens=150,
    )
    raw = response.choices[0].message.content.strip()

    # 6. Detect escalation
    escalation_fired = False
    if "[[ESCALATE:" in raw:
        reason = raw.split("[[ESCALATE:")[1].split("]]")[0]
        fire_escalation(reason, user_input, raw)
        escalation_fired = True
        raw = raw.split("[[ESCALATE:")[0].strip()  # strip the tag from what Margaret hears

    # 7. GUARDRAIL — verify grounded. If not, fall back to safe refusal.
    grounded, reason = verify_grounded(raw, memory_block)
    if not grounded:
        print(f"[GUARDRAIL] Blocked ungrounded response: {reason}")
        raw = "I don't have that written down, love. Shall we ask Priya?"

    # 8. Log interaction
    log_interaction(user_input, raw, escalation_fired)

    return {"response": raw, "escalation_fired": escalation_fired}
```

### 4.2.1 Latency strategy — critical

End-to-end (speech capture → network → LLM → TTS → audio playback) can hit 6–8 seconds. That's unbearable for a patient. Three mitigations, apply all three:

1. **Instant acknowledgement audio.** The moment Margaret stops speaking, play a soft "mmm" or a single warm breath sound *before* the LLM has even responded. Tiny file, pre-loaded in the browser. This alone makes the wait feel 50% shorter.
2. **Cache by sentence hash.** Every TTS response already caches by hash (section 4.5). Pre-populate this cache during rehearsal by running all four demo scenes once — every demo response will then play instantly.
3. **Stream the LLM response.** Use `stream=True` on the GLM call. As soon as the first sentence completes, send it to TTS while the second is still generating. For the demo, this may not matter because of pre-cached audio, but it matters for any real usage after the hackathon.

### 4.3 `backend/memory.py`

Two implementations — pick whichever works. Start with the JSON version (always works), upgrade to Mem0 if time permits.

**Simple JSON version (guaranteed to work):**

```python
import json
from pathlib import Path

PROFILE_PATH = Path("backend/patient_profile.json")
LOG_PATH = Path("data/conversation_log.json")


def get_relevant_memories(query: str, k: int = 6) -> list[str]:
    """Naive keyword retrieval over the profile — good enough for a demo."""
    with open(PROFILE_PATH) as f:
        profile = json.load(f)

    # Flatten profile into a list of facts
    facts = []
    facts.append(f"Margaret is {profile['identity']['age']}, lives in {profile['identity']['location']}")
    for fam in profile["family"]:
        facts.append(f"{fam['name']} is Margaret's {fam['relation']}. {fam.get('notes', '')}")
    for event in profile["scheduled_events"]:
        facts.append(f"Scheduled: {event['when']} — {event['what']}")
    for event in profile["recent_events"]:
        facts.append(f"Recent: {event['when']} — {event['what']}")
    for pref_key, pref_val in profile["preferences"].items():
        facts.append(f"Preference ({pref_key}): {pref_val}")

    # Simple keyword match score
    query_words = set(query.lower().split())
    scored = []
    for fact in facts:
        fact_words = set(fact.lower().split())
        overlap = len(query_words & fact_words)
        scored.append((overlap, fact))

    scored.sort(reverse=True)
    # Always return at least the top-k, even if overlap is 0
    return [fact for _, fact in scored[:k]]


def log_interaction(user_input: str, response: str, escalation: bool):
    log = []
    if LOG_PATH.exists():
        log = json.loads(LOG_PATH.read_text())
    log.append({
        "time": datetime.now().isoformat(),
        "margaret": user_input,
        "anchor": response,
        "escalation": escalation
    })
    LOG_PATH.write_text(json.dumps(log, indent=2))


def get_recent_conversation(n: int = 3) -> str:
    if not LOG_PATH.exists():
        return "(No prior conversation)"
    log = json.loads(LOG_PATH.read_text())
    recent = log[-n:]
    return "\n".join(f"Margaret: {t['margaret']}\nAnchor: {t['anchor']}" for t in recent)
```

**Mem0 upgrade (only if time allows):**

```python
from mem0 import Memory

memory = Memory()

def get_relevant_memories(query: str, k: int = 6) -> list[str]:
    results = memory.search(query=query, user_id="margaret", limit=k)
    return [r["memory"] for r in results]

def seed_memory_from_profile():
    # Run once from scripts/seed_memory.py
    with open("backend/patient_profile.json") as f:
        profile = json.load(f)
    # Convert each fact into a Mem0 memory
    ...
```

### 4.4 `backend/escalation.py`

```python
import json
from datetime import datetime
from pathlib import Path

NOTIF_PATH = Path("data/carer_notifications.json")


def fire_escalation(reason: str, patient_said: str, anchor_replied: str):
    notifs = []
    if NOTIF_PATH.exists():
        notifs = json.loads(NOTIF_PATH.read_text())

    notifs.append({
        "time": datetime.now().isoformat(),
        "reason": reason,
        "patient_said": patient_said,
        "anchor_replied": anchor_replied,
        "urgency": classify_urgency(reason),
        "seen": False
    })
    NOTIF_PATH.write_text(json.dumps(notifs, indent=2))


def classify_urgency(reason: str) -> str:
    high = ["safety", "fall", "injury", "medication", "wandering"]
    if any(k in reason.lower() for k in high):
        return "high"
    return "gentle"


def read_notifications():
    if not NOTIF_PATH.exists():
        return []
    return json.loads(NOTIF_PATH.read_text())
```

### 4.5 `backend/voice.py`

```python
import os
import requests
from pathlib import Path
import hashlib

AUDIO_DIR = Path("frontend/assets/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

ELEVENLABS_VOICE_ID = "warm-older-british-female-voice-id"  # pick one from ElevenLabs library


def synthesize_speech(text: str) -> str:
    """Returns a URL path to the generated audio file."""
    # Cache by hash so repeated sentences are free
    h = hashlib.md5(text.encode()).hexdigest()[:12]
    fname = f"{h}.mp3"
    fpath = AUDIO_DIR / fname

    if not fpath.exists():
        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            return None  # Frontend will fall back to browser SpeechSynthesis

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        response = requests.post(
            url,
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": "eleven_turbo_v2_5",  # fastest model
                "voice_settings": {"stability": 0.6, "similarity_boost": 0.8}
            }
        )
        if response.status_code == 200:
            fpath.write_bytes(response.content)
        else:
            return None

    return f"/static/assets/audio/{fname}"
```

---

## 5. Frontend — detailed build

### 5.1 `frontend/index.html` (the patient interface)

Visual philosophy: one thing on screen, warm colours, serif type, no chrome.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Anchor</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <main id="app" class="resting">
    <!-- Resting state: warm image with gentle pulse -->
    <div id="resting-screen">
      <img src="/static/assets/resting_image.jpg" alt="" aria-hidden="true">
      <div id="listening-pulse" aria-label="Anchor is listening"></div>
    </div>

    <!-- Speaking state: response text centred -->
    <div id="response-screen" hidden>
      <p id="response-text"></p>
    </div>

    <!-- Fallback buttons (always visible, subtle at bottom) -->
    <nav id="fallback-buttons" aria-label="Quick questions">
      <button data-prompt="What day is it today?">What day is it?</button>
      <button data-prompt="When is someone coming to see me?">When is someone coming?</button>
      <button data-prompt="Can you play something I love?">Play something I love</button>
      <button data-prompt="Is everything alright?">Is everything alright?</button>
    </nav>
  </main>

  <audio id="anchor-voice"></audio>
  <script src="/static/patient.js"></script>
</body>
</html>
```

### 5.2 `frontend/styles.css`

```css
* { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  height: 100%;
  background: #f4efe6;             /* warm cream */
  color: #2d2a26;                  /* soft near-black */
  font-family: Georgia, "Times New Roman", serif;
  font-size: 32px;
  line-height: 1.5;
  overflow: hidden;
}

#app {
  position: relative;
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}

#resting-screen {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.6s ease;
}

#resting-screen img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.85;
}

#listening-pulse {
  position: absolute;
  bottom: 140px;
  width: 20px;
  height: 20px;
  background: #c47a54;              /* warm terracotta */
  border-radius: 50%;
  animation: pulse 2.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 0.5; }
  50%      { transform: scale(1.4); opacity: 1; }
}

.resting.listening #listening-pulse {
  animation-duration: 0.8s;
  background: #8ea876;              /* soft sage while actively listening */
}

#response-screen {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  background: rgba(244, 239, 230, 0.92);
  transition: opacity 0.6s ease;
}

#response-text {
  font-size: 48px;
  line-height: 1.4;
  max-width: 900px;
  text-align: center;
  color: #2d2a26;
}

#fallback-buttons {
  position: absolute;
  bottom: 30px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 12px;
  opacity: 0.7;
}

#fallback-buttons button {
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid #c4b7a4;
  border-radius: 30px;
  padding: 14px 24px;
  font-family: inherit;
  font-size: 18px;
  color: #2d2a26;
  cursor: pointer;
  transition: background 0.2s;
}

#fallback-buttons button:hover,
#fallback-buttons button:focus {
  background: #fff;
  outline: 2px solid #c47a54;
}

/* When speaking/responding, hide the resting image softly */
.speaking #resting-screen { opacity: 0.3; }
```

### 5.3 `frontend/patient.js`

```javascript
const app = document.getElementById('app');
const restingScreen = document.getElementById('resting-screen');
const responseScreen = document.getElementById('response-screen');
const responseText = document.getElementById('response-text');
const audioEl = document.getElementById('anchor-voice');
const buttons = document.querySelectorAll('#fallback-buttons button');

// --- Button fallback ---
buttons.forEach(btn => {
  btn.addEventListener('click', () => handleInput(btn.dataset.prompt));
});

// --- Voice input ---
let recognition = null;
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'en-GB';

  recognition.onstart = () => app.classList.add('listening');
  recognition.onend = () => app.classList.remove('listening');
  recognition.onresult = (e) => {
    const transcript = e.results[0][0].transcript;
    handleInput(transcript);
  };
  recognition.onerror = (e) => {
    console.warn('Speech error:', e.error);
    app.classList.remove('listening');
  };
}

// Start listening when user clicks anywhere on the resting screen, or on page load after a short delay
restingScreen.addEventListener('click', () => {
  if (recognition && !app.classList.contains('speaking')) recognition.start();
});

// Auto-start listening every time a response finishes
audioEl.addEventListener('ended', () => {
  setTimeout(() => {
    showResting();
    if (recognition) recognition.start();
  }, 400);
});


async function handleInput(text) {
  if (!text || !text.trim()) return;

  // LATENCY HIDE: play instant acknowledgement while LLM + TTS generate
  playAcknowledgement();

  try {
    const res = await fetch('/api/speak', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text})
    });
    const data = await res.json();
    showResponse(data.response_text);
    if (data.audio_url) {
      audioEl.src = data.audio_url;
      audioEl.play();
    } else {
      // Browser TTS fallback
      const utter = new SpeechSynthesisUtterance(data.response_text);
      utter.rate = 0.95;
      utter.pitch = 1.0;
      utter.onend = () => audioEl.dispatchEvent(new Event('ended'));
      speechSynthesis.speak(utter);
    }
  } catch (err) {
    console.error(err);
    showResponse("I'm having a little trouble — let's try again in a moment.");
  }
}

// Pre-loaded acknowledgement — a soft "mmm" or breath, ~500ms
// Source: a royalty-free breath/hum sample or ElevenLabs pre-generated
const ackAudio = new Audio('/static/assets/ack.mp3');
ackAudio.volume = 0.5;
function playAcknowledgement() {
  ackAudio.currentTime = 0;
  ackAudio.play().catch(() => { /* ignore autoplay policy errors */ });
}

function showResponse(text) {
  responseText.textContent = text;
  responseScreen.hidden = false;
  app.classList.add('speaking');
}

function showResting() {
  app.classList.remove('speaking');
  setTimeout(() => { responseScreen.hidden = true; }, 600);
}
```

### 5.4 `frontend/carer.html` (second screen)

Designed to run on a phone or tablet held up by the presenter during the demo. Polls `/api/carer/notifications` every 2 seconds. When a new notification lands, it slides in with a soft chime.

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Carer view — Priya</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; background: #fff; margin: 0; padding: 20px; }
    h1 { font-size: 18px; color: #666; font-weight: 500; margin-bottom: 20px; }
    .notif {
      background: #fff;
      border: 1px solid #e5e5e5;
      border-left: 4px solid #8ea876;
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 12px;
      animation: slide-in 0.4s ease;
    }
    .notif.high { border-left-color: #c47a54; }
    .notif .time { font-size: 12px; color: #999; }
    .notif .msg { margin-top: 6px; font-size: 15px; }
    @keyframes slide-in { from { transform: translateX(20px); opacity: 0; } to { transform: none; opacity: 1; } }
  </style>
</head>
<body>
  <h1>Priya's carer view</h1>
  <div id="notifications"></div>
  <audio id="chime" src="/static/assets/chime.mp3"></audio>

<script>
let lastCount = 0;
async function poll() {
  const res = await fetch('/api/carer/notifications');
  const notifs = await res.json();
  if (notifs.length > lastCount) {
    document.getElementById('chime').play();
    lastCount = notifs.length;
  }
  render(notifs);
}
function render(notifs) {
  const container = document.getElementById('notifications');
  container.innerHTML = notifs.slice().reverse().map(n => `
    <div class="notif ${n.urgency}">
      <div class="time">${new Date(n.time).toLocaleTimeString()}</div>
      <div class="msg"><strong>${n.reason}</strong> — ${n.patient_said}</div>
      <div class="msg" style="color:#666">Anchor said: ${n.anchor_replied}</div>
    </div>
  `).join('');
}
setInterval(poll, 2000);
poll();
</script>
</body>
</html>
```

---

## 6. The four demo scenes — what to rehearse

These live in `demo/demo_script.md`. Rehearse until fluent.

### Scene 1 — "Is Robert coming home today?"
Margaret asks about her deceased husband. Anchor does NOT correct. It redirects.
> **Margaret:** "Is Robert coming home today?"
> **Anchor:** "Robert's not here today, love. Priya's coming Thursday at three, and she's bringing James."

### Scene 2 — The repeated question
Same question, three times in a minute. Same warmth every time.
> **Margaret:** "What day is it today?"
> **Anchor:** "It's Saturday, the 18th. A quiet one at home — Priya's coming Thursday."
> *(15 seconds later)*
> **Margaret:** "What day is it?"
> **Anchor:** "It's Saturday. Priya's coming on Thursday with James."
> *(another 20 seconds)*
> **Margaret:** "Is today Thursday?"
> **Anchor:** "Not yet, love — it's Saturday. Thursday's when Priya comes."

### Scene 3 — Grounded refusal
Margaret asks something Anchor doesn't know. It refuses honestly, doesn't invent.
> **Margaret:** "Where did I put my glasses?"
> **Anchor:** "I don't have that written down. They're often by the reading chair — shall I ask Priya if we can't find them?"

### Scene 4 — Distress + escalation
Margaret signals fear. Anchor reassures AND silently notifies Priya (carer screen lights up).
> **Margaret:** "I can't find Priya, I'm scared."
> **Anchor:** "Priya's at home with James. She's safe, and I can let her know you'd like to speak. Shall I do that?"
> *[Second screen shows: "Gentle check-in request — Margaret feeling anxious about Priya, 14:32."]*

---

## 7. Hour-by-hour build plan

| Hour | Everyone | Person A (memory) | Person B (agent) | Person C (frontend) | Person D (integration + deck) |
|------|----------|-------------------|------------------|---------------------|-------------------------------|
| 0–1  | Kickoff, scope lock, role assign, repo init, `.gitignore`, LICENSE file | Set up `memory.py` with JSON retrieval; seed `patient_profile.json` | Set up `agent.py`; make one successful GLM API call | Scaffold `index.html` + `styles.css`; resting screen works | Set up FastAPI skeleton; ElevenLabs test; slide outline; pick research source for citation |
| 1–3  | — | Retrieval function returns top-k relevant facts | Full prompt with all 5 few-shot examples; first end-to-end text reply working | Voice capture in patient.js; button fallbacks working | `/api/speak` route wired; escalation notification scaffold; **read chosen research source for 20 mins** |
| 3–5  | First end-to-end smoke test | Add conversation log, recent-turns context | **Hallucination guardrail (`verify_grounded`) implemented and tested**; tune prompt for warmth and brevity; test all four demo scenes | Response screen transitions; audio playback working; **find/generate the "mmm" acknowledgement audio** | Carer screen polling works; seed chime audio; write research-source sentence for slide 6 |
| 5–7  | Lunch + full demo dry run | Add temporal events layer | Escalation detection working; [[ESCALATE:]] tag parsed; test guardrail against 10 adversarial inputs | Accessibility pass — large text, high contrast, WCAG AAA checked; add demo-mode corner overlay for carer view | Fix any integration bugs; slide deck v1 complete including privacy slide |
| 7–9  | Demo rehearsal #1 with real Wi-Fi | Pre-generate audio for all demo responses to `demo/pregenerated_audio/` | Polish the painful-truth redirection for Robert scenario | Listening pulse timing tuned; voice fallback tested; **ack audio latency-hide working** | Deck v2; practise narration; Q&A cards printed or on phones |
| 9–11 | Demo rehearsal #2 and #3 | Reset script tested; wipe logs between rehearsals | — | Final visual polish; accessibility checklist complete | Pitch narration final; **record 90s backup demo video during rehearsal** |
| 11–12| Submission uploads (Watcha, pitch form, deck, demo video), check-in at demo venue W3.01 by 14:20 | Final profile tweaks | — | Backup button paths tested | All submissions confirmed; final rehearsal; team physically at venue |

---

## 8. Environment setup — `.env.example`

```
GLM_API_KEY=your-zai-glm-key
ELEVENLABS_API_KEY=your-elevenlabs-key   # also unlocks Eleven Music API
ANTHROPIC_API_KEY=sk-ant-api03-...       # NOT optional any more — primary fallback when GLM is out of credit
```

> **Post-build note.** `ANTHROPIC_API_KEY` was framed as "optional-fallback" in the original plan. In practice the Z.AI credit expired mid-build, so the Claude path is now on the active hot path for every `/api/speak` call. Treat Anthropic as mandatory. Render needs the key too; set it in the service's environment variables, not in the committed `render.yaml`. Rotate whenever it appears in chat or logs.

## 9. Setup commands for the coding agent

```bash
# Initial setup
mkdir anchor && cd anchor
uv init
uv add fastapi uvicorn[standard] openai mem0ai python-dotenv requests

# Folder structure
mkdir -p backend frontend/assets/audio data demo/pregenerated_audio scripts

# Run
uv run uvicorn backend.main:app --reload --port 8000

# Reset between demos
curl -X POST http://localhost:8000/api/reset
```

> **Post-build note — actual setup commands used.** `mem0ai` was never used (JSON retrieval kept). The live dep set is `fastapi uvicorn[standard] openai anthropic httpx certifi python-dotenv requests pydantic python-multipart`, captured in both `pyproject.toml` and `requirements.txt`. Run the behavioural test suite with `ANCHOR_URL=<url> uv run python scripts/test_demo.py`. Render deploy is driven by `render.yaml` at the repo root; explicit redeploy: `POST https://api.render.com/v1/services/<id>/deploys` with a Render API key.

---

## 10. The 7-slide pitch deck

1. **Title** — *Anchor: a companion that holds memory for people losing theirs.* Team number, names.
2. **The problem** — 55M people globally with dementia. Carer burnout is the #1 cause of care-home admission. Today's voice assistants are context-blind and tire of repetition.
3. **The insight** — Memory isn't a database. It's a relationship. Anchor doesn't "answer" — it anchors.
4. **How it works** — The three-layer architecture diagram (patient interface → grounded agent → memory spine → safety rail, with silent carer mesh).
5. **Live demo** — Four scenes.
6. **Safety & ethics** — Grounded-only with a post-generation guardrail, escalation triggers, not a medical device, repetition without judgment, carer-in-the-loop. **Cite ONE of:** (a) compassionate-communication / validation therapy literature (Feil, or Mental Welfare Commission for Scotland guidance on truth-telling in dementia), (b) Alzheimer's Society UK on carer burnout, or (c) Teepa Snow's Positive Approach to Care. Pick one, read it, defend it. Also: one-line privacy statement (GDPR Article 9 special-category data; production would require consent, encryption, ICO registration).
7. **What's next + team** — Pilot with a UK memory clinic. Not replacing carers — supporting them. Team names and roles.

---

## 11. What will kill you — mitigation

| Risk | Mitigation |
|------|-----------|
| Wi-Fi fails on stage | Pre-generate audio for all four demo scenes; have an offline mode toggle |
| LLM hallucinates a fact | Grounded-only prompt + post-response check that any named entity appears in the memory block |
| Voice recognition misfires | Four fallback buttons, each triggers a scene |
| Demo timing — 5 mins is tight | Scenes 1 & 4 are non-negotiable. Scenes 2 & 3 are cut candidates if running long |
| Judge asks "why not rule-based" | Prepared answer: flexible phrasing, painful-truth redirection, distress detection, warmth calibration |
| Judge asks "is this a medical device" | Prepared answer: no, it's a companion; clearly framed; we refuse medical advice; clinical validation is future work |
| TTS latency | Cache by hash; pre-generate demo audio; use ElevenLabs Turbo model |
| Margaret profile feels generic | Every sentence in the profile JSON has been crafted to feel like a real person — keep it |

---

## 11A. Privacy, data protection, and the GDPR question

A judge will ask this. Be ready.

**What the demo actually does:**
- Patient profile is a local JSON file on the laptop.
- No data transmitted anywhere except the LLM API call (GLM) and the TTS API call (ElevenLabs).
- No profile data logged to any third-party service.
- No real patient data — Margaret is a fictional persona.

**Prepared answer for judges:**
> *"This is a hackathon prototype. Margaret is fictional. In production, this system handles UK GDPR Article 9 special-category health data, which requires explicit consent from the patient or a legally-authorised representative, encryption at rest and in transit, UK ICO registration, data-processing agreements with any LLM provider, and a documented data-retention policy. We would also want clinical validation before calling this anything more than a companion. We have not done that work, and we name it as future work on slide 6."*

**Practical steps in the build (5 minutes of work, high credibility):**
- Add `.env` and `data/` to `.gitignore` so no real data leaks if you open-source it.
- In `backend/main.py`, add a comment at the top: `# HACKATHON PROTOTYPE — NOT FOR USE WITH REAL PATIENT DATA`.
- In the README, add a one-line privacy statement with the same message.

---

## 11B. Dementia-care research — the citation to defend

Pick ONE of these and read enough to defend it for 30 seconds. Do not wing it.

**Option A — Compassionate communication / validation therapy (recommended):**
- **Source:** The Mental Welfare Commission for Scotland's guidance on truth-telling in dementia care, or the broader "validation therapy" literature originated by Naomi Feil.
- **Key claim you're citing:** Correcting a person with dementia when they believe a deceased relative is alive causes measurable distress and is not recommended care practice. Redirection is the clinically preferred response.
- **Why this matters for Anchor:** It grounds the Robert-redirection behaviour in published care guidance, not in our invention.

**Option B — Alzheimer's Society UK on carer burden:**
- **Source:** Alzheimer's Society "Dementia UK" report and carer burnout statistics.
- **Key claim:** Informal carers provide the majority of dementia care in the UK; carer burnout is a leading cause of early care-home admission.
- **Why this matters for Anchor:** It grounds the "reduce carer load" pitch in real numbers.

**Option C — Teepa Snow's Positive Approach to Care (PAC):**
- **Source:** Teepa Snow's published framework on dementia communication.
- **Key claim:** Short sentences, calm tone, no contradiction, offering choices — these are validated communication techniques for people with dementia.
- **Why this matters for Anchor:** Every design choice in the prompt (two short sentences, warmth, no "you already asked") is consistent with PAC.

**Person D (integration + deck) owns this.** In hour 3–5 window, read the chosen source for 20 minutes, write two sentences about it onto slide 6. Do not over-claim — saying "consistent with" or "informed by" is honest and defensible.

---

## 11C. Demo staging — what the audience actually sees

A demo works only if the audience can see what's happening. Missing from the earlier plan:

**Two-screen setup:**
- **Main screen (projector):** Patient interface on a laptop or tablet. This is what Margaret "uses".
- **Secondary screen:** The carer notification view (`/carer`). Ideally a second laptop or a phone held up AND a corner overlay on the main screen (see below). The audience must be able to see the notification fire during Scene 4.

**Corner overlay on the main screen (recommended addition):**
Add a tiny iframe in `frontend/index.html` during demo mode so the audience can see the carer notification happen on the same projected screen. Keep it top-right, small, labelled "Priya's phone". This means even if your phone isn't visible from the back of the room, the escalation is.

```html
<!-- Optional demo overlay — wrap in a ?demo=1 query-param check -->
<div id="carer-overlay" style="position:fixed;top:20px;right:20px;width:260px;height:180px;border:2px solid #c4b7a4;border-radius:12px;overflow:hidden;background:#fff;z-index:1000;">
  <div style="font-size:11px;color:#888;padding:4px 8px;border-bottom:1px solid #eee;">Priya's phone</div>
  <iframe src="/carer" style="width:100%;height:calc(100% - 22px);border:none;"></iframe>
</div>
```

**Presenter choreography:**
- Presenter 1 holds the microphone, speaks as Margaret, points the audience at what's happening.
- Presenter 2 stands to the side, physically holding a phone showing `/carer`, points to it when the notification fires.
- **No one narrates from the laptop keyboard.** That kills demo energy.

**One physical prop: a knitted blanket or a mug of tea on the demo table.** It sounds silly but it changes the emotional register of the whole pitch. The audience sees a *scene*, not a *product*.

---

## 11D. Anticipated Q&A — rehearse these answers

Pitches usually get 2–3 minutes of judge Q&A. These are the seven most likely questions. Assign one person to answer each during rehearsal.

**1. "Why not a rule-based system or a simple FAQ bot?"**
> *"Three things a rule system cannot do: understand any phrasing of a question, calibrate warmth to tone, and detect distress from ambiguous language. We use AI only where it's load-bearing — memory storage, scheduling, and notifications are all plain software."*

**2. "Is this a medical device?"**
> *"No. It's a companion. We refuse to give medical advice, we always redirect to Priya or the GP for anything clinical, and we frame this explicitly as a support tool, not a replacement for care. Clinical validation would be required before we ever called this a medical device."*

**3. "What about GDPR / privacy?"**
> *(Use the answer from section 11A.)*

**4. "What if the AI says something harmful or wrong?"**
> *"Three layers of defence. One: the prompt is grounded-only — the model is instructed to refuse anything not in memory. Two: a post-generation check that verifies any named person or fact in the response appears in the memory block; if not, we fall back to a safe refusal. Three: distress triggers notify the carer immediately — so if something goes wrong, a human is in the loop within seconds."*

**5. "What about non-English speakers? Regional accents?"**
> *"The demo is English. Production would require per-locale voice models and per-language prompts, which is straightforward but not done here. The architecture is language-agnostic — only the prompt and TTS voice change."*

**6. "How is this different from Replika, Pi, or ElliQ?"**
> *"Replika and Pi are general companions without persistent grounded memory of a specific person's life — they are designed to engage, not to ground. ElliQ is the closest commercial competitor, focused on older adults generally; it has won awards but targets lonely seniors, not dementia specifically. Anchor is patient-first, grounded-only, and designed around the specific communication patterns of dementia — therapeutic redirection, repetition without judgment, distress detection. That narrowness is the point."*

**7. "Who's on the team and why are you the ones to build this?"**
> *(Adapt honestly to your actual team. If no one has clinical background, say so, and then say why that's why you consulted the research you cited on slide 6. Naming your limits is a strength.)*

---

## 11E. Accessibility checklist

Five minutes of work, high credibility. Do this in hour 9.

- [ ] Body font ≥ 32px, response text ≥ 48px.
- [ ] Contrast ratio ≥ 7:1 on all text (WCAG AAA for vulnerable users). Use a Chrome extension like "WCAG Contrast Checker" to verify cream-on-brown combo.
- [ ] No flashing elements anywhere (seizure risk). The listening pulse is slow (2.5s cycle) and small — safe.
- [ ] All clickable areas ≥ 44×44px (button tap-target minimum).
- [ ] Screen reader compatibility: every button has meaningful text, no icon-only controls.
- [ ] No autoplay audio on page load (accessibility + judge irritation).
- [ ] Keyboard-only operable: `Tab` through buttons, `Enter` activates.

---

## 11F. Cost estimate

So no one panics when the credit meter moves during the build.

| Service | Estimated usage in 12h | Estimated cost |
|---------|------------------------|----------------|
| GLM API (Z.AI) | ~2000 LLM calls including rehearsal | Free (hackathon credits) |
| ElevenLabs TTS | ~150 unique sentences including rehearsal, cached | ~£3-5 on starter tier |
| Anthropic fallback (if GLM fails) | ~500 calls emergency use | ~£2 |
| Hosting | localhost only | £0 |
| **Total** | | **~£5-10 maximum** |

If you're worried about cost, set a hard spending cap on ElevenLabs' dashboard before the build starts.

---

## 11G. Licensing and submission mechanics

**Licence:** Add a `LICENSE` file. MIT for maximum openness, or "All rights reserved" if you want to commercialise post-hackathon. Pick one before the submission deadline — some hackathon platforms require it.

**Mandatory submission artefacts** (from the hackathon handbook, lose points if missed):

- [ ] **Watcha / Zeabur platform** (https://hacktour.zeabur.app/): project name, description, demo video or images, deployed website link. Team leader only. Try incognito mode if portal doesn't appear.
- [ ] **Pitch PPT submission form** (Feishu): https://i0dbxjdw3k0.feishu.cn/share/base/form/shrcneuDgwln4eCQJaDUM5I6lMW — 7 pages max, deadline 13:00 Sunday 19 April, strict.
- [ ] **Demo video backup**: record a 90-second screen recording of the working demo during rehearsal. Upload to the Watcha submission. Wi-Fi insurance.
- [ ] **README in the repo** with a one-line description, setup instructions, and the privacy disclaimer from section 11A.

**Pre-deadline checklist (hour 11):**
1. Deck uploaded to Feishu form ✓
2. Project uploaded to Watcha ✓
3. Demo video recorded and attached to Watcha ✓
4. Deployed link working (even if localhost + screen recording) ✓
5. Team check-in at demo venue (W3.01, UCL Institute of Education) by 14:20 ✓

---

## 12. What NOT to build

> **Post-build note (2026-04-18):** Several items on the original list were built anyway during Saturday's scope-expansion push against the "Alzheimer's App" feature spec. Strikethroughs mark items that were actually built. Other items remain legitimately out of scope.

Written down so the coding agent doesn't drift:

- Login / auth / user management *(still not built; `/carer` is open to anyone with the URL)*
- ~~Carer dashboard as a separate app~~ **— built anyway.** `/carer` now has an at-a-glance dashboard header, activity feed, medication panel, schedule editor, health log page, safety map, family messages manager. See section 0A. The pitch should still treat the carer as secondary; don't lead with her UI.
- ~~Medication tracking form~~ **— built.** Active confirmation + missed-dose auto-alert + editable schedule, not just read-only.
- Analytics / logging beyond `conversation_log.json` *(still not built; we have activity aggregation but no analytics)*
- Mobile app wrapper *(still not built; app is a web page, `tel:` and Geolocation make it phone-capable)*
- Onboarding flow / first-time setup *(still not built — device is pre-configured)*
- Settings page / preferences UI *(partial — schedule editor on carer side edits routine times; no general settings page)*
- Dark mode toggle *(still not built)*
- Multi-language (demo is English, state this in the pitch)
- Real Google Calendar integration (mock is fine — still only the file-based carer notifications)
- Real SMS / phone call infra *(still not built; `tel:` links open the native dialer but there is no Twilio)*
- HIPAA / UK GDPR compliance work (acknowledge in pitch that production would need it)
- Fine-tuning or training any model
- Voice cloning
- Face recognition / presence detection

Newly added items that were **not** on the original plan but shipped on Saturday:
- Live foreground GPS tracking + geofencing (real, via `navigator.geolocation`)
- Family photo manager (upload or fall-back to watercolour illustrations generated via Runware)
- Family voice-message recording (MediaRecorder, uploaded from carer side)
- Commercial-licensed music tracks (ElevenLabs Music API)
- Proactive voice-spoken reminders for medication, meals, water
- Mood / sleep / behaviour log

---

## 13. The closing sentence

End the pitch with this line, word-for-word:

> *"Anchor doesn't help Margaret remember. It remembers for her, so she can keep being herself."*

Everything in the build serves that sentence.
