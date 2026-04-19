"""Pattern-detection agent — the Track-3 "agentic multi-step" moment.

On every turn Anchor watches which family members Margaret mentioned, and
independently checks the live schedule. When the two diverge — she's asking
about someone repeatedly but there's no event for them on the calendar —
we surface a soft signal to the carer:

    "Margaret's asked about Priya 4 times since this morning, but her next
     visit isn't until Thursday. A short call might help."

This is genuinely agentic: the system chains
    observe (NER over turn)
  → store (rolling query log)
  → retrieve (live ICS / scheduled_events)
  → compare (count vs. proximity)
  → decide (fire or wait, throttled by cooldown)
  → act (write a distinct-urgency carer notification)
No LLM is used in the loop itself — the signal is deterministic and cheap,
which is the point: a safety agent you can reason about end-to-end.

Idempotency:
    Same (person, signal_kind) won't re-fire inside COOLDOWN_HOURS.

Intentional non-goals:
    - Does not fire for deceased family members. Robert is explicitly
      skipped to avoid a tragic false-positive where the system alerts
      Priya "Margaret keeps asking about her husband". The painful-truth
      redirect in the prompt handles that case; this module must not
      overlap with it.
    - Does not use the LLM. Keyword-match NER over the profile's family
      list. Good enough at one-carer, one-profile scale.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from escalation import NOTIF_PATH

QUERY_LOG_PATH = Path("data/query_patterns.json")
PATTERN_FIRED_PATH = Path("data/pattern_fired.json")

# Tunables — chosen to be demo-friendly but defensible
WINDOW_HOURS = 6          # "recently" = within this many hours
REPEAT_THRESHOLD = 3       # how many mentions in-window triggers the check
LOOKAHEAD_DAYS = 7         # search this far ahead for a scheduled event
COOLDOWN_HOURS = 12        # don't re-fire for same person inside this window


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def extract_living_family_mentions(user_input: str, profile: dict) -> list[str]:
    """Return names of LIVING family members mentioned in the utterance.

    Case-insensitive whole-word match. Deceased members are deliberately
    skipped — see module docstring."""
    text = user_input.lower()
    names: list[str] = []
    for fam in profile.get("family", []):
        if fam.get("status") == "deceased":
            continue
        name = fam.get("name", "")
        if not name:
            continue
        # whole-word match avoids "James" triggering on "jam"
        lower = name.lower()
        tokens = {t.strip(".,!?;:'\"") for t in text.split()}
        if lower in tokens:
            names.append(name)
    return names


def record_query(user_input: str, profile: dict) -> list[str]:
    """Log today's mentions of living family members and return the names."""
    mentioned = extract_living_family_mentions(user_input, profile)
    if not mentioned:
        return []
    log: list[dict] = _load_json(QUERY_LOG_PATH, [])
    now_iso = datetime.now().isoformat()
    for name in mentioned:
        log.append({"time": now_iso, "person": name, "utterance": user_input})
    _save_json(QUERY_LOG_PATH, log)
    return mentioned


def _recent_mentions(name: str, window: timedelta) -> list[dict]:
    log: list[dict] = _load_json(QUERY_LOG_PATH, [])
    cutoff = datetime.now() - window
    out = []
    for entry in log:
        if entry.get("person") != name:
            continue
        try:
            t = datetime.fromisoformat(entry["time"])
        except (KeyError, ValueError):
            continue
        if t >= cutoff:
            out.append(entry)
    return out


def _has_upcoming_event(name: str, scheduled_events: list[dict]) -> bool:
    """Does any upcoming event mention this person?

    scheduled_events entries look like {"when": "Thursday 23rd, 15:00",
    "what": "Priya visits with James"}. We match on the "what" substring,
    which handles both live ICS feeds and the static profile."""
    lower = name.lower()
    for ev in scheduled_events or []:
        what = (ev.get("what") or "").lower()
        if lower in what:
            return True
    return False


def _was_fired_recently(name: str, cooldown: timedelta) -> bool:
    fired: list[dict] = _load_json(PATTERN_FIRED_PATH, [])
    cutoff = datetime.now() - cooldown
    for entry in fired:
        if entry.get("person") != name:
            continue
        try:
            t = datetime.fromisoformat(entry["time"])
        except (KeyError, ValueError):
            continue
        if t >= cutoff:
            return True
    return False


def _mark_fired(name: str, count: int) -> None:
    fired: list[dict] = _load_json(PATTERN_FIRED_PATH, [])
    fired.append({
        "time": datetime.now().isoformat(),
        "person": name,
        "count": count,
    })
    _save_json(PATTERN_FIRED_PATH, fired)


def _append_notification(notif: dict) -> None:
    """Write a notification directly (parallel to escalation.fire_escalation,
    but with our own urgency class and richer 'reason' body)."""
    notifs: list[dict] = []
    if NOTIF_PATH.exists():
        try:
            notifs = json.loads(NOTIF_PATH.read_text())
        except json.JSONDecodeError:
            notifs = []
    notifs.append(notif)
    NOTIF_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTIF_PATH.write_text(json.dumps(notifs, indent=2))


def check_asking_pattern(profile: dict, scheduled_events: list[dict]) -> dict | None:
    """The core agentic check. Returns the fired signal dict, or None.

    Runs against every LIVING family member — so the same utterance can
    contribute evidence across multiple people if it mentions several."""
    window = timedelta(hours=WINDOW_HOURS)
    cooldown = timedelta(hours=COOLDOWN_HOURS)

    for fam in profile.get("family", []):
        if fam.get("status") == "deceased":
            continue
        name = fam.get("name", "")
        if not name:
            continue

        recent = _recent_mentions(name, window)
        if len(recent) < REPEAT_THRESHOLD:
            continue
        if _has_upcoming_event(name, scheduled_events):
            continue
        if _was_fired_recently(name, cooldown):
            continue

        signal = {
            "time": datetime.now().isoformat(),
            "reason": "pattern_insight_no_scheduled_visit",
            "patient_said": recent[-1]["utterance"],
            "anchor_replied": (
                f"Margaret has asked about {name} {len(recent)} times in the last "
                f"{WINDOW_HOURS} hours, but there's no visit or call for them "
                f"on the schedule for the next {LOOKAHEAD_DAYS} days. "
                f"A short call or a quick visit might help."
            ),
            "urgency": "insight",
            "kind": "asked_but_not_scheduled",
            "person": name,
            "mention_count": len(recent),
            "first_mention_at": recent[0]["time"],
            "last_mention_at": recent[-1]["time"],
            "seen": False,
        }
        _append_notification(signal)
        _mark_fired(name, len(recent))
        return signal

    return None


def record_and_check(user_input: str, profile: dict,
                     scheduled_events: list[dict]) -> dict | None:
    """Convenience wrapper called once per turn from agent.py.
    Records the mention log then runs the pattern check."""
    record_query(user_input, profile)
    return check_asking_pattern(profile, scheduled_events)


def simulate(profile: dict, scheduled_events: list[dict],
             person: str = "Priya", count: int = 4) -> dict | None:
    """Seed a pattern for stage demos: writes N back-dated mentions of
    `person` so the live check will fire on the next call. Used by
    POST /api/patterns/simulate — never fires automatically."""
    log: list[dict] = _load_json(QUERY_LOG_PATH, [])
    now = datetime.now()
    for i in range(count):
        log.append({
            "time": (now - timedelta(minutes=10 * (count - i))).isoformat(),
            "person": person,
            "utterance": f"When is {person} coming?",
        })
    _save_json(QUERY_LOG_PATH, log)
    # Also clear any old cooldown entry for this person so simulate always fires
    fired = _load_json(PATTERN_FIRED_PATH, [])
    fired = [f for f in fired if f.get("person") != person]
    _save_json(PATTERN_FIRED_PATH, fired)
    return check_asking_pattern(profile, scheduled_events)
