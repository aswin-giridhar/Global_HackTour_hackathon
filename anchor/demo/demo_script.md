# Demo Script — Anchor Pitch (5 minutes)

## Pre-demo setup (before you walk on stage)
1. Reset: `curl -X POST http://localhost:8000/api/reset`
2. Open browser: `http://localhost:8000?demo=1` (patient view with carer overlay)
3. Open second tab: `http://localhost:8000/carer` (Priya's phone)
4. Check Wi-Fi. If flaky, switch to offline mode (pre-generated audio).

---

## Scene 1 — Painful-truth redirection (Robert)
**Say:** "Is Robert coming home today?"

**Expected Anchor response:**
> "Robert's not here today, love. Priya's coming Thursday at three, and she's bringing James."

**What the audience sees:** Warm redirect. No blunt correction. Margaret never hears "Robert is dead."

---

## Scene 2 — Repeated question, same warmth
**Say:** "What day is it today?"

**Expected Anchor response:**
> "It's Saturday, the 18th. A quiet one at home — Priya's coming Thursday."

**Wait 5 seconds. Then say AGAIN:** "What day is it today?"

**Expected Anchor response:**
> "It's Saturday. Priya's coming on Thursday with James."

**What the audience sees:** Same warmth, same answer, no "you already asked." This is the dementia-specific behaviour.

---

## Scene 3 — Grounded refusal
**Say:** "Where did I put my glasses?"

**Expected Anchor response:**
> "I don't have that written down. They're often by the reading chair — shall I ask Priya if we can't find them?"

**What the audience sees:** Anchor doesn't hallucinate. It admits what it doesn't know and redirects to the carer.

---

## Scene 4 — Distress escalation (the payoff)
**Say:** "I can't find Priya, I'm scared."

**Expected Anchor response:**
> "Priya's at home with James. She's safe, and I can let her know you'd like to speak. Shall I do that?"

**What the audience sees (at the same time):** A notification silently appears on Priya's phone view (top-right overlay). Margaret never hears about the alert. This is the inclusion payoff — Margaret gets help at the moment she needs it, without being asked to notice she needs it. The silent carer coordination is the agentic architecture serving the inclusion story.

---

## Closing line (end of demo)

> *"Anchor doesn't help Margaret remember. It remembers for her, so she can keep being herself."*