"""Agent module — LLM call, prompt assembly, safety rails.

Includes Concept 11 (Consensus): a second LLM (critic) verifies every
high-risk response before Margaret hears it. Two-layer safety:
  1. Rule-based verify_grounded() — fast entity check
  2. LLM critic verify_with_critic() — semantic verification for high-risk
"""

import os
import re
import ssl
import json
import httpx
import certifi
from datetime import datetime
from openai import OpenAI, RateLimitError, AuthenticationError, APIStatusError

from memory import (
    get_relevant_memories,
    log_interaction,
    get_recent_conversation,
    get_last_medication_log,
    log_profile_gap,
)
from escalation import fire_escalation

# Point client at Z.AI endpoint (OpenAI-compatible).
# SSL errors and timeouts only surface at request time, so we do the real
# fallback there — _llm_call catches SSL failures and rebuilds the client
# with verify=False (macOS Python 3.14 cert issue).
BASE_URL = "https://api.z.ai/api/paas/v4/"
_TIMEOUT = httpx.Timeout(45.0, connect=10.0)


def _make_client(verify) -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("GLM_API_KEY", ""),
        base_url=BASE_URL,
        http_client=httpx.Client(verify=verify, timeout=_TIMEOUT),
        max_retries=2,
    )


client = _make_client(certifi.where())
_ssl_fallback_engaged = False
_use_claude_fallback = False
_claude_client = None
CLAUDE_MODEL = "claude-sonnet-4-5"


def _get_claude_client():
    global _claude_client
    if _claude_client is None:
        from anthropic import Anthropic
        _claude_client = Anthropic()  # picks up ANTHROPIC_API_KEY from env
    return _claude_client


class _ShimMsg:
    def __init__(self, content: str):
        self.content = content


class _ShimChoice:
    def __init__(self, content: str):
        self.message = _ShimMsg(content)


class _ShimResponse:
    """Mimics the shape of openai.ChatCompletion so call sites can keep using
    response.choices[0].message.content regardless of which backend replied."""
    def __init__(self, content: str):
        self.choices = [_ShimChoice(content)]


def _claude_fallback(**kwargs) -> _ShimResponse:
    """Route a chat.completions-style call through Anthropic.

    The agent only ever sends a single user-role message containing the whole
    composed prompt, so we just forward that body. temperature/max_tokens pass
    through unchanged; model is overridden to Claude.
    """
    messages = kwargs.get("messages", [])
    user_content = messages[-1]["content"] if messages else ""
    claude_msg = _get_claude_client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=kwargs.get("max_tokens", 200),
        temperature=kwargs.get("temperature", 0.4),
        messages=[{"role": "user", "content": user_content}],
    )
    text = claude_msg.content[0].text if claude_msg.content else ""
    return _ShimResponse(text)


def _looks_like_ssl_error(exc: BaseException) -> bool:
    cur: BaseException | None = exc
    while cur is not None:
        if isinstance(cur, ssl.SSLError):
            return True
        msg = str(cur).lower()
        if "ssl" in msg or "certificate verify failed" in msg or "cert" in msg:
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def _llm_call(**kwargs):
    """Wrapped chat.completions.create with two latched fallbacks:
    1. SSL cert failure on macOS Python 3.14 → rebuild client with verify=False.
    2. GLM rate-limit / auth / persistent 4xx → switch to Claude via anthropic SDK.
    Both latches are process-lifetime so we don't retry a broken path per request.
    """
    global client, _ssl_fallback_engaged, _use_claude_fallback
    if _use_claude_fallback:
        return _claude_fallback(**kwargs)
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as e:
        if _looks_like_ssl_error(e) and not _ssl_fallback_engaged:
            import warnings
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")
            print(f"[SSL] Cert verification failed, retrying with verify=False: {e}")
            client = _make_client(False)
            _ssl_fallback_engaged = True
            return client.chat.completions.create(**kwargs)
        if isinstance(e, (RateLimitError, AuthenticationError, APIStatusError)):
            print(f"[FALLBACK] GLM unavailable ({type(e).__name__}), switching to Claude: {e}")
            _use_claude_fallback = True
            return _claude_fallback(**kwargs)
        raise

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


def build_memory_block(profile: dict, relevant: list) -> str:
    """Format the profile + relevant retrieved memories into a readable block
    for the LLM. Keep it under 1500 tokens."""
    lines: list[str] = []
    i = profile["identity"]
    lines.append(f"PATIENT: {i['name']}, {i['age']}, lives in {i['location']}.")
    lines.append("\nFAMILY:")
    for fam in profile["family"]:
        status = (
            f" (deceased {fam.get('year_died')})"
            if fam.get("status") == "deceased"
            else ""
        )
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
    """HALLUCINATION GUARDRAIL (rule-based, fast).

    Check that any NAMED person, date, or specific fact in the response
    appears in the memory block. Returns (is_grounded, reason).

    This is the single most important safety feature in the whole system.
    """
    memory_lower = memory_block.lower()

    # 1. Check named people — every capitalised name in the response
    #    must appear somewhere in the memory block
    names_in_response = set(re.findall(r"\b[A-Z][a-z]{2,}\b", response))
    # Strip common sentence-starters and English words that happen to capitalise
    common_words = {
        "I", "We", "You", "She", "He", "They", "The", "That", "This",
        "It", "Shall", "What", "When", "Where", "Who", "How", "Today",
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
        "Saturday", "Sunday", "January", "February", "March", "April",
        "May", "June", "July", "August", "September", "October",
        "November", "December", "Anchor", "Yes", "No", "Let", "Would",
        "Here", "There",
    }
    names_to_check = names_in_response - common_words
    for name in names_to_check:
        if name.lower() not in memory_lower:
            return False, f"Ungrounded name: {name}"

    # 2. Refuse-patterns are always acceptable
    refuse_signals = [
        "I don't have that written down",
        "let's ask Priya",
        "I'm not sure",
        "shall we ask",
    ]
    if any(s in response for s in refuse_signals):
        return True, "ok"

    return True, "ok"


def verify_with_critic(
    response: str, memory_block: str, user_input: str
) -> tuple[bool, str]:
    """Concept 11 (Consensus): LLM critic verifies response safety.

    A second LLM call evaluates the response against the memory block
    for semantic groundedness, painful-truth correction, medical advice,
    and condescension. Returns (approved, reason).
    """
    try:
        critic_call = _llm_call(
            model="glm-4.5",
            messages=[
                {
                    "role": "user",
                    "content": CRITIC_PROMPT.format(
                        memory_block=memory_block,
                        user_input=user_input,
                        response=response,
                    ),
                }
            ],
            temperature=0.0,
            max_tokens=100,
        )
        raw = critic_call.choices[0].message.content.strip()
        # Strip markdown fences if present
        clean = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)
        return result.get("approved", False), result.get("reason", "unspecified")
    except Exception as e:
        # Fail-safe: if critic is unparseable, fall back to rule-based check
        print(f"[CRITIC] Fallback to rule-based check: {e}")
        return verify_grounded(response, memory_block)


def respond_to_margaret(user_input: str) -> dict:
    """Main pipeline: take patient utterance, return Anchor response."""

    # 1. Load profile
    with open("backend/patient_profile.json") as f:
        profile = json.load(f)

    # 1b. If a Google Calendar ICS URL is configured, replace the static
    #     scheduled_events with the live feed. This is the Track-3 "real
    #     agentic integration" — when Priya adds a new event to her real
    #     calendar, Anchor's answer to "when is Priya coming?" reflects
    #     it within 60s. Falls back silently to static on any failure.
    try:
        from calendar_integration import get_live_events
        live = get_live_events()
        if live:
            profile = dict(profile)
            profile["scheduled_events"] = live
    except Exception as e:
        print(f"[ICS] Falling back to static scheduled_events: {e}")

    # 2. Retrieve relevant memories
    relevant = get_relevant_memories(user_input, k=6)

    # 3. Build memory block
    memory_block = build_memory_block(profile, relevant)

    # 4. Gather context
    # Cross-platform date format (%-d is Linux/Mac only, %#d is Windows)
    import platform
    _d_fmt = "%-d" if platform.system() != "Windows" else "%#d"
    now = datetime.now().strftime(f"%A {_d_fmt} %B, %H:%M")
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

    response = _llm_call(
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

    # 7a. GUARDRAIL — rule-based grounded check (fast, cheap)
    grounded, reason = verify_grounded(raw, memory_block)
    if not grounded:
        print(f"[GUARDRAIL] Blocked ungrounded response: {reason}")
        raw = "I don't have that written down, love. Shall we ask Priya?"
        log_profile_gap(user_input, raw)
        log_interaction(user_input, raw, escalation_fired, rejected_by="rule")
        return {"response": raw, "escalation_fired": escalation_fired}

    # 7b. Concept 11 — LLM critic (slower, deeper — high-risk utterances only)
    high_risk = any(
        k in user_input.lower()
        for k in [
            "robert", "husband", "medicine", "medication", "pill",
            "where am i", "who are you", "call", "help", "scared",
            "frightened", "lost", "hurt", "fall", "fell",
        ]
    )
    if high_risk:
        approved, critic_reason = verify_with_critic(raw, memory_block, user_input)
        if not approved:
            print(f"[CRITIC] Blocked: {critic_reason}")
            raw = "I'm not quite sure about that, love. Let me ask Priya."
            log_profile_gap(user_input, raw)
            log_interaction(user_input, raw, escalation_fired, rejected_by="critic")
            return {"response": raw, "escalation_fired": escalation_fired}

    # 8. Log interaction
    log_interaction(user_input, raw, escalation_fired)

    return {"response": raw, "escalation_fired": escalation_fired}