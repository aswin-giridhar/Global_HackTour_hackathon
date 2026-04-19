"""Google Calendar integration via the private iCal (ICS) URL export.

Priya pastes the "Secret address in iCal format" URL from her Google
Calendar settings. Anchor fetches it on demand (cache 60 s) and feeds the
upcoming events into the agent's memory block instead of the static
scheduled_events from patient_profile.json. This gives Anchor a real
carer-side integration without any OAuth overhead — supporting the
inclusion story by letting Margaret hear answers from Priya's actual
calendar instead of a static copy that drifts.

We never put the ICS URL in logs or GET responses — it's treated as a
per-calendar shared secret.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any

ICS_CONFIG_PATH = Path("data/ics_config.json")
ICS_CACHE_TTL_SECONDS = 60
MAX_UPCOMING = 6


# Module-level cache — one process, one calendar.
_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"url": None, "events": [], "fetched_at": None,
                          "last_error": None, "last_success_at": None}


def _load_config() -> dict:
    try:
        if ICS_CONFIG_PATH.exists():
            data = json.loads(ICS_CONFIG_PATH.read_text())
            return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    return {}


def _save_config(cfg: dict) -> None:
    ICS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ICS_CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def set_ics_url(url: str) -> dict:
    url = (url or "").strip()
    if not url:
        raise ValueError("empty URL")
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("URL must start with http(s)://")
    cfg = _load_config()
    cfg["url"] = url
    cfg["updated_at"] = datetime.now().isoformat()
    _save_config(cfg)
    # Invalidate cache so the next read refetches
    with _cache_lock:
        _cache["url"] = None
        _cache["events"] = []
        _cache["fetched_at"] = None
    # Fetch immediately so the carer sees events without waiting
    try:
        events = _fetch_events(url)
        with _cache_lock:
            _cache.update(url=url, events=events,
                          fetched_at=datetime.now(),
                          last_success_at=datetime.now(),
                          last_error=None)
        return {"ok": True, "count": len(events)}
    except Exception as e:
        with _cache_lock:
            _cache.update(url=url, events=[],
                          fetched_at=datetime.now(),
                          last_error=str(e)[:200])
        return {"ok": False, "error": str(e)[:200]}


def clear_ics_url() -> None:
    cfg = _load_config()
    cfg.pop("url", None)
    _save_config(cfg)
    with _cache_lock:
        _cache.update(url=None, events=[], fetched_at=None,
                      last_error=None, last_success_at=None)


def status() -> dict:
    """Safe-to-return status for the carer UI. Never leaks the URL itself."""
    cfg = _load_config()
    url = cfg.get("url")
    with _cache_lock:
        last_success = _cache.get("last_success_at")
        last_error = _cache.get("last_error")
        event_count = len(_cache.get("events", []))
    return {
        "configured": bool(url),
        "event_count": event_count,
        "last_success_at": last_success.isoformat() if last_success else None,
        "last_error": last_error,
    }


def get_live_events(force_refresh: bool = False) -> list[dict]:
    """Return upcoming events formatted as {"when": str, "what": str}.

    Cache window is ICS_CACHE_TTL_SECONDS. On error, return the last good
    cache if the URL hasn't changed; otherwise empty list. Never raises.
    """
    cfg = _load_config()
    url = cfg.get("url")
    if not url:
        return []

    now = datetime.now()
    with _cache_lock:
        cached_url = _cache.get("url")
        cached_at = _cache.get("fetched_at")
        cached_events = _cache.get("events", [])

    fresh = (
        cached_url == url
        and cached_at is not None
        and (now - cached_at).total_seconds() < ICS_CACHE_TTL_SECONDS
    )
    if fresh and not force_refresh:
        return cached_events

    try:
        events = _fetch_events(url)
        with _cache_lock:
            _cache.update(url=url, events=events, fetched_at=now,
                          last_success_at=now, last_error=None)
        return events
    except Exception as e:
        print(f"[ICS] Fetch failed: {e}")
        with _cache_lock:
            _cache["fetched_at"] = now  # don't hot-loop on failure
            _cache["last_error"] = str(e)[:200]
            if cached_url == url:
                return cached_events
        return []


def _fetch_events(url: str) -> list[dict]:
    """Fetch + parse the ICS feed. Expands recurring events into their next
    occurrence within the upcoming 90 days. Returns up to MAX_UPCOMING
    events sorted by start time."""
    import requests
    from icalendar import Calendar

    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    cal = Calendar.from_ical(resp.content)

    now_local = datetime.now()
    # Window: from now to +90 days — covers recurring weekly visits etc.
    horizon = now_local + timedelta(days=90)

    raw: list[tuple[datetime, str]] = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        summary = str(component.get("summary") or "(untitled)")
        dtstart = component.get("dtstart")
        if not dtstart:
            continue
        start = dtstart.dt

        # Normalise start to a naive local datetime for comparison
        if isinstance(start, datetime):
            if start.tzinfo is not None:
                start = start.astimezone().replace(tzinfo=None)
        else:  # date (all-day)
            start = datetime.combine(start, datetime.min.time())

        # For RRULE-repeating events, expand the next occurrence cheaply:
        # step weekly/daily until we find one in the upcoming window.
        rrule = component.get("rrule")
        if rrule:
            freq = (rrule.get("FREQ") or [None])[0] if hasattr(rrule, "get") else None
            if freq == "WEEKLY":
                step = timedelta(days=7)
            elif freq == "DAILY":
                step = timedelta(days=1)
            else:
                step = None
            if step:
                occ = start
                # skip past occurrences
                while occ < now_local:
                    occ = occ + step
                # include first upcoming + next 3 occurrences within horizon
                for _ in range(4):
                    if occ > horizon:
                        break
                    raw.append((occ, summary))
                    occ = occ + step
                continue

        if now_local <= start <= horizon:
            raw.append((start, summary))

    raw.sort(key=lambda x: x[0])
    out: list[dict] = []
    for start, summary in raw[:MAX_UPCOMING]:
        out.append({
            "when": _format_when(start),
            "what": summary,
        })
    return out


def _format_when(dt: datetime) -> str:
    """Warm, readable date string like 'Thursday 24th, 15:00' that matches
    the tone used elsewhere in the memory block."""
    day = dt.day
    # Ordinal suffix without external deps
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    weekday = dt.strftime("%A")
    month = dt.strftime("%B")
    if dt.hour == 0 and dt.minute == 0:
        return f"{weekday} {day}{suffix} {month}"
    return f"{weekday} {day}{suffix} {month}, {dt.strftime('%H:%M')}"
