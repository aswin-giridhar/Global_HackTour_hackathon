# HACKATHON PROTOTYPE — NOT FOR USE WITH REAL PATIENT DATA

"""Anchor — main FastAPI application.

Serves the patient interface, carer notification view, and API routes
for the core conversation loop, carer notifications, and demo reset.
"""

import os
import sys
import json
from pathlib import Path
from contextlib import asynccontextmanager

# Ensure backend modules can import each other when running via uvicorn
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load .env before importing modules that use env vars
load_dotenv()

from agent import respond_to_margaret  # noqa: E402
from voice import synthesize_speech  # noqa: E402
from escalation import read_notifications, fire_escalation  # noqa: E402
import calendar_integration  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure data directories and files exist on startup."""
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)
    for fname in [
        "carer_notifications.json",
        "conversation_log.json",
        "profile_update_suggestions.json",
        "medication_log.json",
        "behavior_log.json",
        "reminder_confirmations.json",
        "missed_med_fired.json",
        "location.json",
        "query_patterns.json",
        "pattern_fired.json",
    ]:
        fpath = data_dir / fname
        if not fpath.exists():
            fpath.write_text("[]")
    yield


def _load_profile() -> dict:
    with open("backend/patient_profile.json") as f:
        return json.load(f)


def _today_iso() -> str:
    from datetime import datetime
    return datetime.now().date().isoformat()


app = FastAPI(title="Anchor", lifespan=lifespan)

# Serve the frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")


class PatientInput(BaseModel):
    text: str


@app.get("/")
def patient_interface():
    """Serve the main patient interface."""
    return FileResponse("frontend/index.html")


@app.get("/favicon.ico")
def favicon():
    """Serve favicon at root so browsers (and crawlers) find it without
    a redirect, and so /favicon.ico stops showing 404 in the console."""
    return FileResponse("frontend/assets/icons/favicon.ico", media_type="image/x-icon")


@app.get("/sw.js")
def service_worker():
    """Serve the service worker at root scope so it can control all pages.
    Cache-Control is 0 so updated workers deploy on next page load."""
    return FileResponse("frontend/sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "max-age=0, no-cache, no-store"})


@app.get("/privacy")
def privacy_page():
    """Honest privacy & data-handling disclosure — meets the 'acknowledge in
    pitch' bar from the build plan, not GDPR compliance itself."""
    return FileResponse("frontend/privacy.html")


@app.get("/carer")
def carer_interface():
    """Serve the carer notification view (second screen)."""
    return FileResponse("frontend/carer.html")


@app.get("/family")
def family_page():
    """Serve the family photo tiles page."""
    return FileResponse("frontend/family.html")


@app.get("/api/family")
def family_data():
    """Return living family members with role/visit info for the tiles page."""
    profile = _load_profile()
    living = [
        {
            "name": f["name"],
            "relation": f["relation"],
            "location": f.get("location", ""),
            "role": f.get("role", ""),
            "visits": f.get("visits", ""),
            "notes": f.get("notes", ""),
        }
        for f in profile["family"]
        if f.get("status") != "deceased"
    ]
    return {"family": living}


@app.get("/api/daily_brief")
def daily_brief():
    """Deterministic daily summary — no LLM, fast and reliable for proactive display."""
    from datetime import datetime
    profile = _load_profile()
    now = datetime.now()
    hour = now.hour
    if hour < 12:
        part = "morning"
    elif hour < 17:
        part = "afternoon"
    else:
        part = "evening"
    next_event = profile["scheduled_events"][0] if profile["scheduled_events"] else None

    # Morning medication status for the brief
    med_status = _medication_today_status(profile)

    day_name = now.strftime("%A")
    date_str = now.strftime("%-d %B") if os.name != "nt" else now.strftime("%#d %B")

    return {
        "day": day_name,
        "date": date_str,
        "part_of_day": part,
        "next_event": next_event,
        "medication_morning_taken": med_status["morning_taken"],
    }


def _medication_today_status(profile: dict) -> dict:
    """Look at today's medication_log entries and summarise what's been taken."""
    log_path = Path("data/medication_log.json")
    try:
        entries = json.loads(log_path.read_text()) if log_path.exists() else []
    except json.JSONDecodeError:
        entries = []
    today = _today_iso()
    today_entries = [e for e in entries if e.get("date") == today]
    morning_taken = any(e.get("slot") == "morning" for e in today_entries)
    evening_taken = any(e.get("slot") == "evening" for e in today_entries)
    return {
        "morning_taken": morning_taken,
        "evening_taken": evening_taken,
        "entries_today": today_entries,
        "morning_schedule": profile["routine"].get("medication_morning", {}),
        "evening_schedule": profile["routine"].get("medication_evening", {}),
    }


class MedicationMark(BaseModel):
    slot: str  # "morning" or "evening"
    marked_by: str = "carer"  # "patient" or "carer"


@app.post("/api/medication/taken")
def medication_taken(payload: MedicationMark):
    """Record that medication was taken for the given slot."""
    from datetime import datetime
    if payload.slot not in ("morning", "evening"):
        return JSONResponse({"ok": False, "error": "slot must be morning or evening"}, status_code=400)
    log_path = Path("data/medication_log.json")
    try:
        entries = json.loads(log_path.read_text()) if log_path.exists() else []
    except json.JSONDecodeError:
        entries = []
    entries.append({
        "time": datetime.now().isoformat(),
        "date": _today_iso(),
        "slot": payload.slot,
        "marked_by": payload.marked_by,
    })
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(entries, indent=2))
    return {"ok": True, "count_today": len([e for e in entries if e.get("date") == _today_iso()])}


@app.get("/api/medication/status")
def medication_status():
    """Return today's medication status for the carer screen."""
    return _medication_today_status(_load_profile())


# ─── Proactive reminders (medication / meals / water) ────────────────────
# Reminders wake up within ±15 min of their scheduled time and disappear
# when the patient or carer confirms them. Pure JSON — no scheduler needed.

REMINDER_WINDOW_MIN = 15
MISSED_THRESHOLD_MIN = 120  # 2 hours late → auto-alert carer


def _parse_hhmm(hhmm: str) -> tuple[int, int] | None:
    try:
        h, m = hhmm.strip().split(":")
        return int(h), int(m)
    except Exception:
        return None


def _reminder_rows(profile: dict) -> list[dict]:
    """Flatten routine into a list of (kind, label, time, slot) rows."""
    r = profile.get("routine", {})
    out = []
    mm = r.get("medication_morning", {})
    if mm.get("time"):
        out.append({"kind": "medication", "slot": "morning",
                    "label": f"{mm.get('drug','Morning dose')} {mm.get('dose','')}".strip(),
                    "detail": mm.get("location", ""),
                    "time": mm["time"]})
    me = r.get("medication_evening", {})
    if me.get("time"):
        out.append({"kind": "medication", "slot": "evening",
                    "label": f"{me.get('drug','Evening dose')} {me.get('dose','')}".strip(),
                    "detail": "", "time": me["time"]})
    for meal_key, meal_label in [("tea", "Morning tea"), ("lunch", "Lunch"),
                                 ("dinner", "Dinner")]:
        if r.get(meal_key):
            out.append({"kind": "meal", "slot": meal_key, "label": meal_label,
                        "detail": "", "time": r[meal_key]})
    # Water — evenly spaced reminders
    for slot, time in [("water_mid_morning", "10:30"),
                       ("water_afternoon", "14:30"),
                       ("water_evening", "17:30")]:
        out.append({"kind": "water", "slot": slot, "label": "A glass of water",
                    "detail": "", "time": time})
    return out


def _reminder_confirmed_today(slot: str) -> bool:
    path = Path("data/reminder_confirmations.json")
    try:
        entries = json.loads(path.read_text()) if path.exists() else []
    except json.JSONDecodeError:
        entries = []
    today = _today_iso()
    return any(e.get("date") == today and e.get("slot") == slot for e in entries)


def _med_taken_today(slot: str) -> bool:
    path = Path("data/medication_log.json")
    try:
        entries = json.loads(path.read_text()) if path.exists() else []
    except json.JSONDecodeError:
        entries = []
    today = _today_iso()
    return any(e.get("date") == today and e.get("slot") == slot for e in entries)


@app.get("/api/reminders/due")
def reminders_due():
    """Return reminders whose scheduled time is within ±15 min of now AND
    haven't been confirmed today. Drives the proactive patient-side card."""
    from datetime import datetime
    profile = _load_profile()
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    due = []
    for row in _reminder_rows(profile):
        hm = _parse_hhmm(row["time"])
        if not hm:
            continue
        sched = hm[0] * 60 + hm[1]
        delta = now_min - sched
        if -REMINDER_WINDOW_MIN <= delta <= REMINDER_WINDOW_MIN:
            already = (_med_taken_today(row["slot"]) if row["kind"] == "medication"
                       else _reminder_confirmed_today(row["slot"]))
            if not already:
                due.append({**row, "overdue_minutes": max(0, delta)})
    return {"due": due, "now": now.strftime("%H:%M")}


class ReminderConfirm(BaseModel):
    slot: str
    kind: str = "meal"  # "meal" | "water" | "medication"
    marked_by: str = "patient"


@app.post("/api/reminders/confirm")
def reminders_confirm(payload: ReminderConfirm):
    """Patient or carer confirms a reminder. Medications go through the
    dedicated medication log; everything else lands in reminder_confirmations."""
    from datetime import datetime
    if payload.kind == "medication":
        return medication_taken(MedicationMark(slot=payload.slot, marked_by=payload.marked_by))
    path = Path("data/reminder_confirmations.json")
    try:
        entries = json.loads(path.read_text()) if path.exists() else []
    except json.JSONDecodeError:
        entries = []
    entries.append({"time": datetime.now().isoformat(), "date": _today_iso(),
                    "slot": payload.slot, "kind": payload.kind,
                    "marked_by": payload.marked_by})
    path.write_text(json.dumps(entries, indent=2))
    return {"ok": True}


@app.post("/api/missed_check")
def missed_check():
    """Scan for medication doses that are more than MISSED_THRESHOLD_MIN
    late and fire a carer escalation for each — idempotent per dose per day."""
    from datetime import datetime
    profile = _load_profile()
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    fired_path = Path("data/missed_med_fired.json")
    try:
        fired = json.loads(fired_path.read_text()) if fired_path.exists() else []
    except json.JSONDecodeError:
        fired = []
    today = _today_iso()
    newly_fired = []
    for slot_key, label in [("medication_morning", "morning"),
                            ("medication_evening", "evening")]:
        sched = profile["routine"].get(slot_key, {})
        hm = _parse_hhmm(sched.get("time", ""))
        if not hm:
            continue
        sched_min = hm[0] * 60 + hm[1]
        if now_min - sched_min < MISSED_THRESHOLD_MIN:
            continue
        if _med_taken_today(label):
            continue
        key = f"{today}:{label}"
        if key in fired:
            continue
        fire_escalation(
            reason=f"missed_medication_{label}",
            patient_said=f"[system] {label} dose of {sched.get('drug','Donepezil')} "
                         f"{sched.get('dose','')} overdue since {sched.get('time','')}",
            anchor_replied="[system] Missed medication alert fired automatically.",
        )
        fired.append(key)
        newly_fired.append(key)
    fired_path.write_text(json.dumps(fired, indent=2))
    return {"ok": True, "newly_fired": newly_fired, "fired_total_today": len(fired)}


# ─── Behavior log (mood / sleep / notes) ─────────────────────────────────

class BehaviorEntry(BaseModel):
    mood: str | None = None           # "good" | "settled" | "agitated" | "tearful"
    sleep_hours: float | None = None
    note: str | None = None
    category: str = "note"            # "mood" | "sleep" | "note" | "incident"


@app.post("/api/log/behavior")
def log_behavior(entry: BehaviorEntry):
    from datetime import datetime
    path = Path("data/behavior_log.json")
    try:
        entries = json.loads(path.read_text()) if path.exists() else []
    except json.JSONDecodeError:
        entries = []
    entries.append({
        "time": datetime.now().isoformat(),
        "date": _today_iso(),
        "mood": entry.mood, "sleep_hours": entry.sleep_hours,
        "note": entry.note, "category": entry.category,
    })
    path.write_text(json.dumps(entries, indent=2))
    return {"ok": True, "count": len(entries)}


@app.get("/api/log/behavior")
def read_behavior_log():
    path = Path("data/behavior_log.json")
    try:
        return {"entries": json.loads(path.read_text()) if path.exists() else []}
    except json.JSONDecodeError:
        return {"entries": []}


# ─── Google Calendar (via private ICS URL, no OAuth) ─────────────────────

class IcsUrl(BaseModel):
    url: str


@app.post("/api/schedule/ics_url")
def schedule_set_ics(payload: IcsUrl):
    """Priya pastes her Google Calendar 'Secret address in iCal format'
    URL. Anchor fetches it immediately and every 60 s from then on."""
    try:
        result = calendar_integration.set_ics_url(payload.url)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return result


@app.delete("/api/schedule/ics_url")
def schedule_clear_ics():
    calendar_integration.clear_ics_url()
    return {"ok": True}


@app.get("/api/schedule/ics_url")
def schedule_ics_status():
    """Safe status for the carer UI. Never returns the URL itself."""
    return calendar_integration.status()


@app.get("/api/schedule/live")
def schedule_live_events():
    """Return the events Anchor is currently using as ground truth.
    Useful for debugging and for the carer to see what Anchor sees."""
    return {
        "events": calendar_integration.get_live_events(),
        "status": calendar_integration.status(),
    }


# ─── Remote schedule management ───────────────────────────────────────────

class ScheduleUpdate(BaseModel):
    medication_morning_time: str | None = None  # "HH:MM"
    medication_evening_time: str | None = None
    tea: str | None = None
    lunch: str | None = None
    dinner: str | None = None


@app.post("/api/schedule/update")
def schedule_update(u: ScheduleUpdate):
    """Carer edits routine times in the profile. Writes back to disk."""
    profile = _load_profile()
    r = profile.setdefault("routine", {})
    if u.medication_morning_time and _parse_hhmm(u.medication_morning_time):
        r.setdefault("medication_morning", {})["time"] = u.medication_morning_time
    if u.medication_evening_time and _parse_hhmm(u.medication_evening_time):
        r.setdefault("medication_evening", {})["time"] = u.medication_evening_time
    for field in ("tea", "lunch", "dinner"):
        val = getattr(u, field)
        if val and _parse_hhmm(val):
            r[field] = val
    with open("backend/patient_profile.json", "w") as f:
        json.dump(profile, f, indent=2)
    return {"ok": True, "routine": r}


@app.get("/api/schedule")
def get_schedule():
    profile = _load_profile()
    return {"routine": profile.get("routine", {})}


# ─── Music (generated calming tones, licensing-honest) ───────────────────

@app.get("/api/music/tracks")
def music_tracks():
    """Tracks composed by ElevenLabs Music, cleared for commercial use
    per their terms. Chosen to fit Margaret's preferences in the profile
    (hymns, wartime songs, ambient calm)."""
    return {
        "tracks": [
            {"id": "gentle_hymn", "title": "Gentle hymn",
             "subtitle": "Traditional-style hymn, piano and strings",
             "url": "/static/assets/music/gentle_hymn.mp3"},
            {"id": "dance_memory", "title": "Dance memory",
             "subtitle": "1940s-style waltz, accordion and strings",
             "url": "/static/assets/music/dance_memory.mp3"},
            {"id": "evening_calm", "title": "Evening calm",
             "subtitle": "Soft piano and cello for settling down",
             "url": "/static/assets/music/evening_calm.mp3"},
        ],
        "note": ("Music composed with ElevenLabs Music API, cleared for "
                 "commercial use. Matched to Margaret's preferences "
                 "(hymns, wartime songs, ambient calm) from her profile."),
    }


@app.get("/music")
def music_page():
    return FileResponse("frontend/music.html")


# ─── Carer analytics — aggregate insights over conversation & log data ──
# Complements the real-time activity feed with weekly / multi-day stats
# Priya can actually show the GP. Pure counting and rate math — no ML.

from collections import Counter
import re


def _word_tokens(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in {
        "the","and","you","for","are","but","not","she","her","him","his","has",
        "have","had","with","what","when","where","who","why","how","shall","ask",
        "from","this","that","today","coming","going","love","yes","was","were",
    }]


@app.get("/api/analytics/summary")
def analytics_summary():
    """Longitudinal counts and rates a carer can act on or hand to a GP.
    Pulls from the existing log files — no extra instrumentation."""
    from datetime import datetime, timedelta
    convo = _safe_read_json(Path("data/conversation_log.json"))
    meds  = _safe_read_json(Path("data/medication_log.json"))
    behav = _safe_read_json(Path("data/behavior_log.json"))
    notifs = _safe_read_json(Path("data/carer_notifications.json"))
    gaps   = _safe_read_json(Path("data/profile_update_suggestions.json"))

    now = datetime.now()
    since_7d = (now - timedelta(days=7)).isoformat()
    since_24h = (now - timedelta(hours=24)).isoformat()

    convo_7d = [c for c in convo if (c.get("time") or "") >= since_7d]
    convo_24h = [c for c in convo if (c.get("time") or "") >= since_24h]

    # Most-asked topics in the last 7 days (crude but honest keyword counter)
    all_words = []
    for c in convo_7d:
        all_words.extend(_word_tokens(c.get("margaret", "")))
    top_words = Counter(all_words).most_common(5)

    # Repetition rate — how often the same margaret utterance repeats
    utterances = [c.get("margaret","").strip().lower() for c in convo_7d]
    utter_counts = Counter(utterances)
    repeats = sum(n - 1 for n in utter_counts.values() if n > 1)
    repetition_rate = round(repeats / len(utterances), 2) if utterances else 0.0

    # Medication adherence — for the last 7 days, did a morning and evening
    # confirmation land on each day?
    today = _today_iso()
    adherence_days = 0
    doses_possible = 0
    for i in range(7):
        d = (now - timedelta(days=i)).date().isoformat()
        entries = [m for m in meds if m.get("date") == d]
        has_morning = any(m.get("slot") == "morning" for m in entries)
        has_evening = any(m.get("slot") == "evening" for m in entries)
        doses_possible += 2
        adherence_days += int(has_morning) + int(has_evening)
    adherence_pct = round(100 * adherence_days / doses_possible, 1) if doses_possible else 0.0

    # Mood distribution (last 7 days)
    mood_counts = Counter(
        b["mood"] for b in behav
        if b.get("mood") and (b.get("time") or "") >= since_7d
    )

    # Refusal / critic-rejection rate — how often the guardrail fired
    rejected = sum(1 for c in convo_7d if c.get("rejected_by"))
    refusal_rate = round(rejected / len(convo_7d), 2) if convo_7d else 0.0

    # Escalations by urgency
    high_alerts = sum(1 for n in notifs if n.get("urgency") == "high" and (n.get("time") or "") >= since_7d)
    gentle_alerts = sum(1 for n in notifs if n.get("urgency") == "gentle" and (n.get("time") or "") >= since_7d)

    return {
        "window_days": 7,
        "conversations_7d": len(convo_7d),
        "conversations_24h": len(convo_24h),
        "top_topics": [{"word": w, "count": n} for w, n in top_words],
        "repetition_rate": repetition_rate,
        "refusal_rate": refusal_rate,
        "medication_adherence_pct": adherence_pct,
        "mood_counts_7d": dict(mood_counts),
        "alerts_high_7d": high_alerts,
        "alerts_gentle_7d": gentle_alerts,
        "open_profile_gaps": len(gaps),
    }


# ─── Unified activity feed ───────────────────────────────────────────────
# Merges medication, reminder, mood, notification, and conversation events
# into one chronological stream so the carer dashboard can show an
# at-a-glance "what has happened today" view.

def _safe_read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


@app.get("/api/activity/today")
def activity_today():
    """Chronological feed of today's events across all logs. Newest last."""
    today = _today_iso()
    items: list[dict] = []

    for e in _safe_read_json(Path("data/medication_log.json")):
        if e.get("date") == today:
            items.append({"time": e.get("time"), "kind": "medication_taken",
                          "label": f"{e.get('slot','').title()} medication taken",
                          "meta": f"marked by {e.get('marked_by','carer')}"})

    for e in _safe_read_json(Path("data/reminder_confirmations.json")):
        if e.get("date") == today:
            kind = e.get("kind", "reminder")
            items.append({"time": e.get("time"), "kind": f"{kind}_taken",
                          "label": f"{kind.title()}: {e.get('slot','')} confirmed",
                          "meta": f"marked by {e.get('marked_by','patient')}"})

    for e in _safe_read_json(Path("data/behavior_log.json")):
        if e.get("date") == today:
            bits = []
            if e.get("mood"):         bits.append(f"mood {e['mood']}")
            if e.get("sleep_hours") is not None: bits.append(f"slept {e['sleep_hours']}h")
            if e.get("note"):         bits.append(e["note"])
            items.append({"time": e.get("time"), "kind": "behavior_log",
                          "label": "Health log entry",
                          "meta": " · ".join(bits) or "(empty)"})

    for e in _safe_read_json(Path("data/carer_notifications.json")):
        t = e.get("time", "")
        if t.startswith(today):
            items.append({"time": t,
                          "kind": f"alert_{e.get('urgency','gentle')}",
                          "label": f"Alert — {e.get('reason','')}".replace("_", " "),
                          "meta": e.get("patient_said", "")})

    for e in _safe_read_json(Path("data/conversation_log.json")):
        t = e.get("time", "")
        if t.startswith(today):
            items.append({"time": t, "kind": "conversation",
                          "label": f"Margaret: \u201c{e.get('margaret','')}\u201d",
                          "meta": f"Anchor: \u201c{e.get('anchor','')}\u201d"})

    items.sort(key=lambda x: x.get("time") or "")
    return {"items": items, "count": len(items), "date": today}


@app.get("/api/dashboard/summary")
def dashboard_summary():
    """At-a-glance numbers for the carer dashboard header."""
    profile = _load_profile()
    med = _medication_today_status(profile)
    notifs = _safe_read_json(Path("data/carer_notifications.json"))
    today = _today_iso()
    todays_notifs = [n for n in notifs if (n.get("time") or "").startswith(today)]
    high = sum(1 for n in todays_notifs if n.get("urgency") == "high")
    gentle = sum(1 for n in todays_notifs if n.get("urgency") == "gentle")
    behavior = _safe_read_json(Path("data/behavior_log.json"))
    today_moods = [e for e in behavior if e.get("date") == today and e.get("mood")]
    last_mood = today_moods[-1]["mood"] if today_moods else None
    convos = _safe_read_json(Path("data/conversation_log.json"))
    today_convo = [c for c in convos if (c.get("time") or "").startswith(today)]
    return {
        "date": today,
        "medication_morning_taken": med["morning_taken"],
        "medication_evening_taken": med["evening_taken"],
        "alerts_today_high": high,
        "alerts_today_gentle": gentle,
        "last_mood": last_mood,
        "conversations_today": len(today_convo),
    }


# ─── Family photo uploads ────────────────────────────────────────────────

ALLOWED_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PHOTO_BYTES = 5 * 1024 * 1024  # 5MB


def _family_names() -> set[str]:
    profile = _load_profile()
    return {f["name"] for f in profile["family"] if f.get("status") != "deceased"}


@app.post("/api/family/photo/{name}")
async def upload_family_photo(name: str, file: UploadFile = File(...)):
    """Carer uploads a real photo for a living family member."""
    if name not in _family_names():
        raise HTTPException(status_code=404, detail=f"No living family member named {name!r}")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_PHOTO_EXT:
        raise HTTPException(status_code=400, detail=f"Allowed: {sorted(ALLOWED_PHOTO_EXT)}")
    data = await file.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo must be ≤5MB")
    photos_dir = Path("data/family_photos")
    photos_dir.mkdir(parents=True, exist_ok=True)
    # Clear any previous photo for this name with other extensions
    for old in photos_dir.glob(f"{name}.*"):
        old.unlink()
    target = photos_dir / f"{name}{ext}"
    target.write_bytes(data)
    return {"ok": True, "name": name, "bytes": len(data)}


@app.get("/api/family/photo/{name}")
def get_family_photo(name: str):
    """Serve the uploaded photo for a family member. 404 if none uploaded."""
    photos_dir = Path("data/family_photos")
    if not photos_dir.exists():
        raise HTTPException(status_code=404, detail="No photo")
    for ext in ALLOWED_PHOTO_EXT:
        p = photos_dir / f"{name}{ext}"
        if p.exists():
            return FileResponse(p)
    raise HTTPException(status_code=404, detail="No photo")


@app.delete("/api/family/photo/{name}")
def delete_family_photo(name: str):
    photos_dir = Path("data/family_photos")
    removed = 0
    if photos_dir.exists():
        for p in photos_dir.glob(f"{name}.*"):
            p.unlink()
            removed += 1
    return {"ok": True, "removed": removed}


# ─── Voice messages (family → patient) ───────────────────────────────────
# Priya records a short voice note for Margaret; Margaret sees a tile on
# /family with a "Play message" button. Storage is local filesystem.

ALLOWED_AUDIO_EXT = {".webm", ".mp3", ".wav", ".ogg", ".m4a"}
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10MB


@app.post("/api/family/voice/{name}")
async def upload_family_voice(name: str, file: UploadFile = File(...)):
    """Carer uploads a short reassurance message recorded in browser."""
    if name not in _family_names():
        raise HTTPException(status_code=404, detail=f"No living family member named {name!r}")
    ext = Path(file.filename or "").suffix.lower() or ".webm"
    if ext not in ALLOWED_AUDIO_EXT:
        raise HTTPException(status_code=400, detail=f"Allowed: {sorted(ALLOWED_AUDIO_EXT)}")
    data = await file.read()
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio must be ≤10MB")
    vdir = Path("data/family_voices")
    vdir.mkdir(parents=True, exist_ok=True)
    for old in vdir.glob(f"{name}.*"):
        old.unlink()
    target = vdir / f"{name}{ext}"
    target.write_bytes(data)
    return {"ok": True, "name": name, "bytes": len(data)}


@app.get("/api/family/voice/{name}")
def get_family_voice(name: str):
    vdir = Path("data/family_voices")
    if not vdir.exists():
        raise HTTPException(status_code=404, detail="No voice message")
    for ext in ALLOWED_AUDIO_EXT:
        p = vdir / f"{name}{ext}"
        if p.exists():
            return FileResponse(p)
    raise HTTPException(status_code=404, detail="No voice message")


@app.get("/api/family/voice")
def list_family_voices():
    """Lightweight listing so the family page knows who has a message."""
    vdir = Path("data/family_voices")
    if not vdir.exists():
        return {"voices": {}}
    voices = {}
    for p in vdir.iterdir():
        if p.suffix.lower() in ALLOWED_AUDIO_EXT:
            voices[p.stem] = f"/api/family/voice/{p.stem}"
    return {"voices": voices}


@app.delete("/api/family/voice/{name}")
def delete_family_voice(name: str):
    vdir = Path("data/family_voices")
    removed = 0
    if vdir.exists():
        for p in vdir.glob(f"{name}.*"):
            p.unlink()
            removed += 1
    return {"ok": True, "removed": removed}


@app.get("/api/family/photo")
def list_family_photos():
    """Which family members have an uploaded photo. Used by the family page
    to decide whether to render the photo or fall back to the illustration."""
    photos_dir = Path("data/family_photos")
    if not photos_dir.exists():
        return {"photos": {}}
    photos = {}
    for p in photos_dir.iterdir():
        if p.suffix.lower() in ALLOWED_PHOTO_EXT:
            photos[p.stem] = f"/api/family/photo/{p.stem}"
    return {"photos": photos}


# ─── Safety / location (real foreground GPS via browser Geolocation API) ─
# Works for always-on Anchor devices (tablet in the kitchen) and for the
# demo scenario where the judge walks away with the patient device. Does
# NOT do background tracking with the screen off — that needs a native
# companion app.

import math

LOCATION_PATH = Path("data/location.json")
DEFAULT_RADIUS_M = 500
LOCATION_HISTORY_LIMIT = 120


def _load_location() -> dict:
    """Load location state. Tolerates the lifespan's default '[]' init."""
    try:
        data = json.loads(LOCATION_PATH.read_text()) if LOCATION_PATH.exists() else {}
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_location(state: dict) -> None:
    LOCATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCATION_PATH.write_text(json.dumps(state, indent=2))


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


class LocationUpdate(BaseModel):
    lat: float
    lng: float
    accuracy: float | None = None


class HomeSet(BaseModel):
    lat: float
    lng: float
    radius_m: float = DEFAULT_RADIUS_M


@app.post("/api/location/update")
def location_update(pos: LocationUpdate):
    """Patient device posts its current position. If it's outside the
    configured safe zone, fire a wandering escalation — idempotent per
    breach: one alert per contiguous out-of-zone period."""
    from datetime import datetime
    state = _load_location()
    now_iso = datetime.now().isoformat()
    entry = {"time": now_iso, "lat": pos.lat, "lng": pos.lng,
             "accuracy": pos.accuracy}
    history = state.get("history", [])
    history.append(entry)
    if len(history) > LOCATION_HISTORY_LIMIT:
        history = history[-LOCATION_HISTORY_LIMIT:]
    state["history"] = history
    state["latest"] = entry

    home = state.get("home")
    inside = True
    distance_m = 0.0
    if home:
        distance_m = _haversine_m(home["lat"], home["lng"], pos.lat, pos.lng)
        inside = distance_m <= home.get("radius_m", DEFAULT_RADIUS_M)
        was_inside = state.get("inside_safe_zone", True)
        if was_inside and not inside:
            # Fresh breach — fire the carer escalation once
            fire_escalation(
                reason="wandering_safe_zone_breach",
                patient_said=f"[location] Device left the {int(home.get('radius_m',DEFAULT_RADIUS_M))}m safe zone ({int(distance_m)}m from home)",
                anchor_replied="[system] Live wandering alert — device GPS reports out of zone.",
            )
            state["last_breach_at"] = now_iso
        state["inside_safe_zone"] = inside

    _save_location(state)
    return {"ok": True, "inside_safe_zone": inside,
            "distance_m": round(distance_m, 1), "home_set": bool(home)}


@app.post("/api/location/set_home")
def location_set_home(home: HomeSet):
    state = _load_location()
    state["home"] = {"lat": home.lat, "lng": home.lng,
                     "radius_m": home.radius_m}
    state["inside_safe_zone"] = True
    _save_location(state)
    return {"ok": True, "home": state["home"]}


@app.get("/api/location/latest")
def location_latest():
    """Carer polls this to show Margaret's position and safe-zone state."""
    state = _load_location()
    home = state.get("home")
    latest = state.get("latest")
    distance_m = None
    inside = True
    if home and latest:
        distance_m = round(_haversine_m(home["lat"], home["lng"],
                                        latest["lat"], latest["lng"]), 1)
        inside = distance_m <= home.get("radius_m", DEFAULT_RADIUS_M)
    return {
        "latest": latest,
        "home": home,
        "inside_safe_zone": inside,
        "distance_m": distance_m,
        "last_breach_at": state.get("last_breach_at"),
        "history_count": len(state.get("history", [])),
    }


@app.get("/safety")
def safety_page():
    return FileResponse("frontend/safety.html")


@app.post("/api/safety/simulate_wandering")
def simulate_wandering():
    """Demo hook — fires a wandering escalation directly, bypassing GPS.
    Useful during a pitch when the presenter can't physically walk the
    device out of the safe zone."""
    fire_escalation(
        reason="wandering_safe_zone_breach",
        patient_said="[simulation] Margaret left the 500m safe zone around home",
        anchor_replied="[system] Wandering alert — demo simulation.",
    )
    return {"ok": True, "note": "Simulated wandering alert fired to carer."}


@app.get("/api/patterns/state")
def patterns_state():
    """Return the recent query log so the carer dashboard can show
    "asked 4× today about Priya" next to the notification."""
    import patterns
    log = patterns._load_json(patterns.QUERY_LOG_PATH, [])
    # Return last 24h, grouped by person
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(hours=24)
    recent = []
    for e in log:
        try:
            if datetime.fromisoformat(e["time"]) >= cutoff:
                recent.append(e)
        except (KeyError, ValueError):
            continue
    counts: dict[str, int] = {}
    for e in recent:
        counts[e["person"]] = counts.get(e["person"], 0) + 1
    return {"last_24h": counts, "total": len(recent)}


@app.post("/api/patterns/simulate")
def patterns_simulate(person: str = "Priya", count: int = 4, force: bool = True):
    """Demo hook — seeds a repeated-asking pattern so the agentic signal
    fires on the next check. Useful on stage to guarantee Priya's phone
    shows the insight during the demo.

    force=True (default) pretends the calendar is empty for `person`, so
    the signal always fires on seeded data. Set force=False to run the
    real check against the live schedule (useful for verifying the
    suppression logic — e.g. the default Priya/David both have scheduled
    events and should NOT fire)."""
    import patterns
    profile = _load_profile()
    if force:
        events: list[dict] = []
    else:
        try:
            from calendar_integration import get_live_events
            live = get_live_events()
            events = live if live else profile.get("scheduled_events", [])
        except Exception:
            events = profile.get("scheduled_events", [])
    signal = patterns.simulate(profile, events, person=person, count=count)
    return {
        "ok": True,
        "fired": signal is not None,
        "force": force,
        "signal": signal,
        "note": (
            f"Seeded {count} mentions of {person}. "
            + ("Calendar override: no event. Signal fired."
               if force else
               "Real calendar used — signal only fires if no upcoming event.")
        ),
    }


# ─── Mood / sleep / behavior page (carer) ────────────────────────────────

@app.get("/logs")
def logs_page():
    return FileResponse("frontend/logs.html")


@app.post("/api/speak")
async def speak(input: PatientInput):
    """Core loop: take patient utterance, return Anchor response + audio URL."""
    result = respond_to_margaret(input.text)
    audio_url = synthesize_speech(result["response"])
    return {
        "response_text": result["response"],
        "audio_url": audio_url,
        "escalation": result.get("escalation_fired", False),
    }


@app.get("/api/carer/notifications")
def carer_notifications():
    """Return all carer notifications (polled by carer.html every 2s)."""
    return read_notifications()


# ─── Carer-side visibility: conversation browser + memory viewer ─────────
# The two endpoints below power the Conversations and Memory tabs on the
# carer dashboard. Both are read-heavy and touch only existing files.

@app.get("/api/conversations/recent")
def conversations_recent(limit: int = 50):
    """Return the last `limit` conversation turns, newest first.
    Each entry already carries optional rejected_by / escalation fields
    so the UI can surface them without a second call."""
    log = _safe_read_json(Path("data/conversation_log.json"))
    tail = log[-max(0, int(limit)):]
    tail.reverse()
    return {"turns": tail, "total_stored": len(log)}


@app.get("/api/profile")
def profile_view():
    """Return Margaret's full profile for the carer's Memory tab.
    Read-only in this release — editing lands in the next iteration."""
    return _load_profile()


@app.get("/api/profile/gaps")
def profile_gaps():
    """Return the BrowseBack-lite gap log — questions Margaret asked
    whose answers weren't in her profile. Priya resolves these by
    updating the profile (today: manually; future: via a form)."""
    return {"gaps": _safe_read_json(Path("data/profile_update_suggestions.json"))}


class GapResolve(BaseModel):
    index: int


@app.post("/api/profile/gaps/resolve")
def profile_gaps_resolve(payload: GapResolve):
    """Remove a single gap from the suggestion log once Priya has
    addressed it (either by updating the profile JSON or deciding
    it doesn't matter). Idempotent on out-of-range indexes."""
    path = Path("data/profile_update_suggestions.json")
    gaps = _safe_read_json(path)
    i = payload.index
    if 0 <= i < len(gaps):
        removed = gaps.pop(i)
        path.write_text(json.dumps(gaps, indent=2))
        return {"ok": True, "removed": removed, "remaining": len(gaps)}
    return {"ok": False, "error": "index out of range", "remaining": len(gaps)}


def _check_demo_key(key: str | None) -> None:
    """If DEMO_RESET_KEY is set, require the caller's key to match.
    Unset env var → open (dev/local). This protects prod from accidental
    or drive-by resets without breaking local scripts."""
    expected = os.environ.get("DEMO_RESET_KEY")
    if expected and key != expected:
        raise HTTPException(status_code=403, detail="reset not authorised")


@app.post("/api/reset")
def reset(key: str | None = None):
    """Reset all data files for a clean demo."""
    _check_demo_key(key)
    data_dir = Path("data")
    for fname in [
        "carer_notifications.json",
        "conversation_log.json",
        "profile_update_suggestions.json",
        "medication_log.json",
        "behavior_log.json",
        "reminder_confirmations.json",
        "missed_med_fired.json",
        "location.json",
        "query_patterns.json",
        "pattern_fired.json",
    ]:
        fpath = data_dir / fname
        fpath.write_text("[]")
    return {"ok": True}


@app.get("/demo")
def demo_console(key: str | None = None):
    """Password-gated control panel for clearing demo state on stage.

    Gate: if DEMO_RESET_KEY env var is set, the `?key=` query param must match.
    If the env var is unset (local dev), the page opens freely.

    Deliberately unlinked from the rest of the UI — you reach it by typing
    the URL, which is exactly what you want for a break-glass tool."""
    expected = os.environ.get("DEMO_RESET_KEY")
    if expected and key != expected:
        return FileResponse("frontend/demo_locked.html", status_code=403)
    return FileResponse("frontend/demo.html")