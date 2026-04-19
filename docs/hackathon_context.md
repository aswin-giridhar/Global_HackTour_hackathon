# Hackathon Context — Global AI HackTour London 2026

**Purpose of this file:** hand this to a coding agent, a teammate, or a new joiner at any point so they understand the rules, stakes, deadlines, and scoring model for the Anchor build. Every design decision in the build plan was made against these constraints.

---

## 1. Event essentials

- **Event:** Global AI HackTour London — London Station
- **Dates:** Saturday 18 April – Sunday 19 April 2026
- **Format:** Two-day intensive build hackathon, projects built from scratch during the event
- **Strategic partner:** Z.AI (providing free GLM API credits to all teams)

## 2. Venues

| Day | Venue | Nearest tube |
|-----|-------|--------------|
| Sat 18 Apr | UCL Institute of Archaeology, G06 LT, WC1H 0PY | Euston Square (6 min walk) |
| Sun 19 Apr | UCL Institute of Education, W3.01 / W3.07 / W3.08, WC1H 0AL | Russell Square (4 min walk) |

- WiFi: UCL Guest & Eduroam
- Bring: laptop charger and extension lead (power is limited)

## 3. The three tracks

Each team picks **ONE** track only.

### Track 1 — The Creative Renaissance (AI × Media)
Redefining content creation and interactive art through generative AI. Punk rebellion, fashion, cinematic narrative angle.

### Track 2 — The Inclusive London (AI 4 Good) ⭐
Bridging the digital divide. Solving real-world problems for underserved communities. "Warm code" that includes people technology usually leaves behind.

### Track 3 — The Invisible Tube (AI × Agentic Workflows)
Breaking down application silos. Enabling AI to manage end-to-end digital workflows autonomously. Building the next invisible operating system.

### Anchor's track choice

**Submitted to: Track 2 — The Inclusive London (AI 4 Good).**

Framing: people with dementia are a population almost entirely designed-out of modern AI. Mainstream voice assistants assume intact short-term memory. Chatbots assume you can type, read paragraphs, and tolerate the occasional made-up fact. Screens assume you understand that a button is a button. Anchor inverts every one of those defaults — grounded-only answers, one-circle interface, refusal-not-invention, pattern-watching agent that notices for Margaret when she can't notice for herself. Inclusion isn't a label we added; it's the entire design brief.

**Track 3 positioning (retired after Saturday's opening ceremony).** An earlier version of this doc listed Track 3 (Invisible Tube / agentic workflows) as primary because Anchor does carry genuine agentic architecture — a deterministic observation agent running alongside the LLM, plus a Google Calendar ICS integration. Those remain in the code and the pitch as *technical differentiators*, but they aren't the headline. The Track 2 story is stronger for the peer-vote half of scoring and truer to why we built this.

## 4. Key schedule

### Saturday 18 April
- **10:30–11:30** Check-in, team formation, badge collection, networking
- **11:30–12:00** Opening ceremony — track announcements, rule briefing, resource introduction
- **12:00–12:25** Z.AI speech by Cara Li (venue G06 LT)
- **12:00–13:00** Z.AI technical workshop (same venue) — get API credits here, this is critical
- **13:00–18:00** Development session with lunch, snacks, drinks

### Sunday 19 April
- **10:00–13:00** Final sprint and project submission
- **13:00 STRICT** Project submission deadline — no amendments after this
- **13:00–14:20** Two guest panel discussions (W3.01)
- **14:20–15:50** Parallel demos across 3 rooms, 5 minutes per team + showcase
- **15:50–16:10** Judges' meeting
- **16:10–17:00** Awards ceremony
- **17:10–18:00** Closing and afterparty

## 5. Scoring model — CRITICAL

**The final ranking combines two components, weighted:**
1. **Judge score** — evaluated against the official criteria (below)
2. **Contestant votes** — other participants vote through the showcase

This means you are **not just pitching to 5 judges — you are pitching to every other hackathon participant in the room.** That changes strategy.

**Judge evaluation criteria:**
- Value of the problem
- Innovation
- Technical implementation
- Completion
- User experience
- Clarity of presentation

## 6. What this scoring model means for Anchor

**Because half the score is peer votes, emotional resonance matters more than enterprise-readiness.**

Anchor's four demo scenes are designed for the peer-vote half:
- Scene 1 (Robert redirection) — emotional peak
- Scene 2 (repeated question, same warmth) — concept-demonstration
- Scene 3 (grounded refusal) — credibility
- Scene 4 (distress escalation with silent carer notification) — inclusion payoff: Margaret gets help without being asked to recognise she needs it

Rivals building enterprise dashboards, crypto tools, or dev-infra plays will score well with judges but probably poorly with peers. Anchor is engineered to score on both halves.

## 7. Rules that affect the build

- **Project must be mainly built during the event.** Pre-completed projects are not permitted. The system prompt, research citations, and pitch deck can be drafted before; the code must be written during.
- **Judges focus on work done during the event.** Reusing your Mem0 knowledge is fine; reusing your Reed taxonomy code is not.
- **Each team picks ONE track.** Off-topic projects may be excluded from judging.
- **Submission deadline is strict.** No late submissions. No amendments. Deadline is 13:00 Sunday 19 April.
- **Pitch is 5 minutes strict.** Overtime will be stopped by the moderator.
- **Demo venue check-in is 14:20 Sunday.** Miss this and you lose your slot.

## 8. Pitch format

- **Maximum 7 pages.**
- **Video embedding not recommended** — use demo page screenshots instead. Matters because Wi-Fi on a projector is unreliable; pre-recorded videos fail.
- **Title format:** `[Team Number] – Project Name`
- **Font specification:** Alibaba PuHui 3.0 or Times New Roman. Can adjust size.
- **Submission methods:** two separate platforms, both mandatory.

## 9. Mandatory submissions — both must be complete before 13:00 Sunday

### Submission 1 — Watcha / Zeabur Platform
URL: https://hacktour.zeabur.app/
- Project name
- Project description
- Relevant images or demo video
- Deployed website link and other materials
- **Only team leader can submit.** Edits allowed until deadline.
- If the submission portal doesn't appear, try incognito/private mode.

### Submission 2 — Feishu Pitch Submission Form
URL: https://i0dbxjdw3k0.feishu.cn/share/base/form/shrcneuDgwln4eCQJaDUM5I6lMW
- Pitch deck (7 pages max)
- Submit before 13:00 Sunday

### Demo video backup (strongly recommended)
Record a 90-second screen recording of the working demo during rehearsal on Sunday morning. Attach to Watcha submission. This is Wi-Fi insurance — if the projector or Wi-Fi fails during the live demo, the judges can still see the video through the submission.

## 10. Technical resources

### Z.AI GLM API — free for all teams
- Collect API credits at the Z.AI technical workshop (12:00–13:00 Saturday, G06 LT)
- This is the primary LLM for Anchor's production use
- OpenAI-compatible endpoint, so the SDK just points at `https://api.z.ai/api/paas/v4/` with an API key
- Model: `glm-4.5`

### Official Event Toolkit
- Computing credits, API limits, cloud vouchers, premium platform features
- Released at opening ceremony
- Valid only during the hackathon
- **Important:** toolkit resources are not scoring criteria. Using more tools does not improve your score. Judges evaluate problem-solving and execution, not resource volume.

### Technical support
- Check official docs first
- Unresolved issues via official channels (Discord)
- Providers coordinate through organisers, not one-to-one

## 11. Other resources

Recommended stack for Anchor specifically (see `anchor_build_plan.md` section 1 for full table):

| Layer | Choice | Reason |
|-------|--------|--------|
| LLM | Z.AI GLM-4.5 (free credits) | Primary |
| LLM fallback | Claude via Anthropic API | Only if GLM has friction |
| Memory | JSON file + keyword retrieval | Guaranteed to work; Mem0 optional upgrade |
| Voice input | Browser Web Speech API | Free, zero setup |
| Voice output | ElevenLabs (Turbo model) | Warm voice, ~£5 in credits |
| Backend | Python FastAPI | Fast scaffolding |
| Frontend | Vanilla HTML/CSS/JS | No build step |
| Calendar | Mock file-based webhook | Avoid OAuth pain |
| Package manager | `uv` | Fast dep install |

## 12. What Anchor is NOT trying to win

Being honest about where Anchor's pitch has limits helps you prepare for Q&A:

- **Not a technical novelty competition winner.** Teams pitching cross-app orchestration (BenchBreak concept), evolutionary agents (Evolvr), or novel research implementations will score higher on "innovation" on the strict engineering axis. Anchor's innovation is *applied* — the critic-model verification, the grounded-only architecture, the carer-mesh fallback for the unknown.
- **Not a demo-theatre winner.** Teams with live-evolving dashboards or cross-app browser agents have more visual spectacle. Anchor's demo is quieter.
- **Not a scale-story winner.** Teams pitching enterprise B2B with a six-figure contract story will outcompete on commercial potential.

**What Anchor wins on:**
- Emotional resonance (peer vote)
- Ethical care (judge score)
- Problem value (judge score — 55M people globally with dementia is a big number)
- Completion (you can actually ship a working demo in 12 hours)
- Clarity of presentation (four scenes, tight narrative, single-sentence close)

This is a deliberate positioning. Other strategies are possible but they don't play to the scoring model.

## 13. Code of conduct and logistics

- Respect all participants
- No unauthorised departure from venue (counts as withdrawal)
- Do not enter restricted areas
- Take care of facilities (damage = compensation)
- Safety first: reasonable rest, safe electricity use, secure valuables
- Disclose medical conditions to staff (allergies, heart conditions, asthma, hypoglycaemia)
- Catering provided: lunch both days, afternoon tea, snacks, drinks. Ask staff about allergies.

## 14. Hour-by-hour critical-path timeline

This is the compressed version. Full hour-by-hour build plan is in `anchor_build_plan.md` section 7.

### Saturday
- **10:30** Arrive Institute of Archaeology. Check in. Team forms.
- **11:30** Opening ceremony. Confirm track choice.
- **12:00** Z.AI workshop — **get API credits here**. Non-negotiable.
- **13:00** Development starts. Build plan hour 0 begins.
- **13:00–18:00** Build hours 0–5. Skeleton working end-to-end by hour 5.
- **Evening** Team continues if capacity allows, otherwise sleep. Decide together. Don't be heroes.

### Sunday
- **Early morning** Resume building. Build hours 5–10.
- **10:00** Move to Institute of Education. Final sprint begins.
- **10:00–12:00** Rehearsals x3 on real hackathon Wi-Fi.
- **12:00–13:00** Final polish, submission uploads.
- **13:00** HARD DEADLINE. Submissions closed.
- **14:20** Check-in at demo venue W3.01. Miss this and you forfeit the demo slot.
- **14:20–15:50** Demos. 5 minutes strict.
- **15:50** Judges deliberate.
- **16:10** Awards.

## 15. Key contacts and channels

- **Wi-Fi:** UCL Guest & Eduroam
- **Staff contact:** Via Discord (unexpected disruption, transport, accommodation, catering, medical)
- **IT issues with team formation system:** contact IT team via handbook channels

## 16. The one thing a coding agent should know

If you (the coding agent) are reading this to help build Anchor, the single most important thing to internalise is:

**Every design choice serves a vulnerable user who cannot verify what you tell her.**

Margaret cannot catch a hallucination. She cannot tell you if a response felt condescending. She cannot reset the app if it crashes. She cannot read a small font. She cannot parse complex UI.

This means:
- No feature is complete until it degrades gracefully (Wi-Fi fails → offline mode; TTS fails → browser fallback; LLM fails → safe refusal).
- No response is acceptable until it's been verified (that's the critic-LLM concept from `anchor_concepts.md`).
- No UI is finished until a 74-year-old can operate it (large fonts, warm colours, serif type, no chrome).

When in doubt about any implementation choice, ask: *does this respect Margaret?* If unclear, the answer is probably to do less, not more.

---

## 17. Closing note

You have ~12 focused build hours. You have a team of 4. You have a single clear product. You have two research concepts (11 Consensus, 12 BrowseBack-lite) layered on top of a strong base. You have a four-scene demo engineered for both judge scores and peer votes.

Everything else is distraction.

Ship it warm.
