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
from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load .env before importing modules that use env vars
load_dotenv()

from agent import respond_to_margaret  # noqa: E402
from voice import synthesize_speech  # noqa: E402
from escalation import read_notifications, fire_escalation  # noqa: E402


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
    """Prototype track list. Real deployment would serve licensed audio."""
    return {
        "tracks": [
            {"id": "hymn_ionian", "title": "Gentle hymn",
             "subtitle": "Generated tone — evokes Margaret's hymns",
             "url": "/static/assets/music/gentle_hymn.wav"},
            {"id": "dance_memory", "title": "Dance memory",
             "subtitle": "Generated tone — evokes 1940s wartime songs",
             "url": "/static/assets/music/dance_memory.wav"},
            {"id": "evening_calm", "title": "Evening calm",
             "subtitle": "Generated tone — soft ambient",
             "url": "/static/assets/music/evening_calm.wav"},
        ],
        "note": ("These are prototype-generated tones. A production build "
                 "would license Vera Lynn tracks, hymns, and family voice "
                 "recordings per Margaret's profile preferences."),
    }


@app.get("/music")
def music_page():
    return FileResponse("frontend/music.html")


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


# ─── Safety / location (honest placeholder, no fake GPS) ─────────────────

@app.get("/safety")
def safety_page():
    return FileResponse("frontend/safety.html")


@app.post("/api/safety/simulate_wandering")
def simulate_wandering():
    """Demo-only: fires a wandering escalation as if GPS had detected Margaret
    leaving the safe zone. Real deployment uses mobile-app location data."""
    fire_escalation(
        reason="wandering_safe_zone_breach",
        patient_said="[system] Simulated: Margaret left the 500m safe zone around home",
        anchor_replied="[system] Wandering alert — GPS placeholder simulation (demo).",
    )
    return {"ok": True, "note": "Simulated wandering alert fired to carer."}


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


@app.post("/api/reset")
def reset():
    """Reset all data files for a clean demo."""
    data_dir = Path("data")
    for fname in [
        "carer_notifications.json",
        "conversation_log.json",
        "profile_update_suggestions.json",
        "medication_log.json",
        "behavior_log.json",
        "reminder_confirmations.json",
        "missed_med_fired.json",
    ]:
        fpath = data_dir / fname
        fpath.write_text("[]")
    return {"ok": True}