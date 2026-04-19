/* ─────────────────────────────────────────────
   Anchor — Patient-facing JavaScript
   Voice capture, latency-hiding, smooth state transitions.
   ───────────────────────────────────────────── */

// ─── PWA service worker registration (offline shell + installable icon) ───
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .then(reg => console.log('[Anchor] SW registered, scope:', reg.scope))
      .catch(err => console.warn('[Anchor] SW registration failed:', err));
  });
}

const app            = document.getElementById('app');
const breathingRing  = document.getElementById('breathing-ring');
const responseScreen = document.getElementById('response-screen');
const responseCard   = document.getElementById('response-card');
const responseText   = document.getElementById('response-text');
const audioEl        = document.getElementById('anchor-voice');
const buttons        = document.querySelectorAll('#fallback-buttons button');

// ─── Ambient audio cues ────────────────────────────────────────────────
// Presence cues, not alerts. Volume is low and throttled so they never
// compete with Margaret's TTS voice or startle her. The chime plays when
// a reminder appears; the ack plays briefly when the mic opens.
const chimeEl = new Audio('/static/assets/chime.wav');
const ackEl   = new Audio('/static/assets/ack.wav');
chimeEl.volume = 0.35;
ackEl.volume   = 0.22;
let lastCueAt = 0;
function playCue(el) {
  const now = Date.now();
  if (now - lastCueAt < 1200) return;  // debounce — never two cues in rapid sequence
  lastCueAt = now;
  try {
    el.currentTime = 0;
    el.play().catch(() => { /* autoplay policy — ignore silently */ });
  } catch (_) { /* ignore */ }
}

// ─── Demo overlay: show carer notifications if ?demo=1 ───
if (new URLSearchParams(window.location.search).has('demo')) {
  document.getElementById('carer-overlay').style.display = 'block';
}

// ─── Daily brief — proactive "what's today" card ───
async function loadDailyBrief() {
  try {
    const res = await fetch('/api/daily_brief');
    const d = await res.json();
    const greetings = { morning: 'Good morning, love', afternoon: 'Good afternoon, love', evening: 'Good evening, love' };
    document.getElementById('brief-greeting').textContent = greetings[d.part_of_day] || 'Hello, love';
    document.getElementById('brief-date').textContent = `${d.day}, ${d.date}`;
    if (d.next_event) {
      document.getElementById('brief-next').innerHTML =
        `Coming up — <strong>${d.next_event.when}</strong>: ${d.next_event.what}`;
    }
  } catch (e) {
    console.warn('[Anchor] Daily brief unavailable:', e);
  }
}
loadDailyBrief();

// ─── Proactive reminder overlay ───
const reminderOverlay = document.getElementById('reminder-overlay');
const reminderKind    = document.getElementById('reminder-kind');
const reminderLabel   = document.getElementById('reminder-label');
const reminderDetail  = document.getElementById('reminder-detail');
const reminderConfirm = document.getElementById('reminder-confirm');
const reminderDismiss = document.getElementById('reminder-dismiss');

const KIND_TITLES = {
  medication: 'Time for your medicine',
  meal:       'Time for a meal',
  water:      'A little drink of water',
};

let currentReminder = null;

// Dismissals persist across page reloads for the current day. Cleared
// automatically when the date rolls over so the next morning starts fresh.
const dismissKey = () => `anchor-dismissed-${new Date().toISOString().slice(0, 10)}`;
function loadDismissed() {
  try { return new Set(JSON.parse(localStorage.getItem(dismissKey()) || '[]')); }
  catch { return new Set(); }
}
function saveDismissed(set) {
  try { localStorage.setItem(dismissKey(), JSON.stringify([...set])); }
  catch { /* quota / disabled — fall through to in-memory-only */ }
}
function cleanOldDismissals() {
  try {
    const today = dismissKey();
    const toRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith('anchor-dismissed-') && k !== today) toRemove.push(k);
    }
    toRemove.forEach(k => localStorage.removeItem(k));
  } catch { /* non-fatal */ }
}
cleanOldDismissals();
let dismissedThisSession = loadDismissed();

function speakReminder(r) {
  if (!('speechSynthesis' in window)) return;
  speechSynthesis.cancel();
  const phrases = {
    medication: `It's time for your medicine, love. ${r.label}.`,
    meal:       `It's time for ${r.label.toLowerCase()}, love.`,
    water:      `A little drink of water when you're ready, love.`,
  };
  const text = phrases[r.kind] || `Gentle reminder, love — ${r.label}.`;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'en-GB';
  u.rate = 0.92;
  u.pitch = 1.05;
  speechSynthesis.speak(u);
}

function showReminder(r) {
  if (dismissedThisSession.has(r.slot)) return;
  if (currentReminder && currentReminder.slot === r.slot) return;
  currentReminder = r;
  reminderKind.textContent = KIND_TITLES[r.kind] || 'A gentle reminder';
  reminderLabel.textContent = r.label;
  reminderDetail.textContent = r.detail || `Scheduled ${r.time}`;
  reminderOverlay.hidden = false;
  playCue(chimeEl);
  // Give the chime a beat to land before TTS starts talking
  setTimeout(() => speakReminder(r), 450);
}

function hideReminder() {
  reminderOverlay.hidden = true;
  currentReminder = null;
}

reminderConfirm.addEventListener('click', async () => {
  if (!currentReminder) return hideReminder();
  const { kind, slot } = currentReminder;
  reminderConfirm.disabled = true;
  try {
    await fetch('/api/reminders/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slot, kind, marked_by: 'patient' }),
    });
  } catch (e) {
    console.warn('[Anchor] Reminder confirm failed:', e);
  } finally {
    reminderConfirm.disabled = false;
    hideReminder();
  }
});

reminderDismiss.addEventListener('click', () => {
  if (currentReminder) {
    dismissedThisSession.add(currentReminder.slot);
    saveDismissed(dismissedThisSession);
  }
  hideReminder();
});

async function checkReminders() {
  try {
    const res = await fetch('/api/reminders/due');
    const data = await res.json();
    // Fire the first pending reminder; one at a time keeps the UI calm
    const next = (data.due || [])[0];
    if (next) {
      showReminder(next);
    } else if (currentReminder) {
      // nothing due and we have one showing for a slot no longer in the window
      hideReminder();
    }
    // Opportunistically trigger missed-med check so overdue doses page Priya
    fetch('/api/missed_check', { method: 'POST' }).catch(() => {});
  } catch (e) {
    /* non-fatal; next tick retries */
  }
}

checkReminders();
setInterval(checkReminders, 30000);  // every 30s — good enough, low-noise

// ─── Location sharing (quiet background, foreground-only) ───
// Browsers block background tracking without permission; that's fine for
// this use case — the device is typically on and foreground. If the user
// denies permission, we quietly stop and the carer safety page shows
// "no location shared".
if ('geolocation' in navigator) {
  const postPos = (pos) => {
    fetch('/api/location/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
      }),
    }).catch(() => { /* non-fatal */ });
  };
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      postPos(pos);
      navigator.geolocation.watchPosition(postPos, () => {}, {
        enableHighAccuracy: true,
        maximumAge: 15000,
        timeout: 20000,
      });
    },
    () => { /* permission denied — silently skip */ },
    { enableHighAccuracy: true, timeout: 10000 }
  );
}

// ─── Button fallback ───
buttons.forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.stopPropagation(); // Don't trigger ring click
    handleInput(btn.dataset.prompt);
  });
});

// ─── Voice input ───
let recognition = null;
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'en-GB';

  recognition.onstart = () => {
    app.classList.add('listening');
    playCue(ackEl);
    console.log('[Anchor] Listening...');
  };
  recognition.onend = () => {
    app.classList.remove('listening');
    console.log('[Anchor] Stopped listening.');
  };
  recognition.onresult = (e) => {
    const transcript = e.results[0][0].transcript;
    handleInput(transcript);
  };
  recognition.onerror = (e) => {
    console.warn('[Anchor] Speech error:', e.error);
    app.classList.remove('listening');
  };
}

// ─── Typed-input overlay — long-press or double-click the ring to reveal ───
const textOverlay = document.getElementById('text-input-overlay');
const textField   = document.getElementById('text-input-field');
const textForm    = document.getElementById('text-input-form');
const textClose   = document.getElementById('text-input-close');
const textSend    = document.getElementById('text-input-send');

const LONG_PRESS_MS = 500;
let longPressTimer = null;
let longPressTriggered = false;

function openTextInput() {
  textOverlay.hidden = false;
  requestAnimationFrame(() => textField.focus());
}
function closeTextInput() {
  textOverlay.hidden = true;
  textField.value = '';
  textSend.disabled = false;
}

breathingRing.addEventListener('pointerdown', () => {
  longPressTriggered = false;
  longPressTimer = setTimeout(() => {
    longPressTriggered = true;
    openTextInput();
  }, LONG_PRESS_MS);
});
['pointerup', 'pointerleave', 'pointercancel'].forEach(evt => {
  breathingRing.addEventListener(evt, () => {
    if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }
  });
});
breathingRing.addEventListener('dblclick', (e) => {
  e.preventDefault();
  e.stopPropagation();
  longPressTriggered = true;  // also suppresses the follow-on click
  openTextInput();
});

// ─── Click the breathing ring to start listening ───
breathingRing.addEventListener('click', (e) => {
  if (longPressTriggered) {
    longPressTriggered = false;
    return;
  }
  if (recognition && !app.classList.contains('speaking')) {
    recognition.start();
  }
});

// Also listen on the ambient area (large click target)
document.getElementById('ambient').addEventListener('click', () => {
  if (longPressTriggered) return;
  if (recognition && !app.classList.contains('speaking')) {
    recognition.start();
  }
});

// Submit typed input through the same pipeline as voice and buttons
textForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = textField.value.trim();
  if (!text) return;
  textSend.disabled = true;
  closeTextInput();
  handleInput(text);
});

// Close via button, Escape, or clicking outside the form
textClose.addEventListener('click', closeTextInput);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !textOverlay.hidden) {
    e.preventDefault();
    closeTextInput();
  }
});
textOverlay.addEventListener('click', (e) => {
  if (e.target === textOverlay) closeTextInput();
});

// ─── Auto-listen after response finishes ───
audioEl.addEventListener('ended', () => {
  setTimeout(() => {
    showResting();
    if (recognition) {
      try { recognition.start(); } catch(e) { /* already started */ }
    }
  }, 600);
});

// ─── Keyboard: spacebar to trigger listening ───
document.addEventListener('keydown', (e) => {
  if (e.code === 'Space' && !app.classList.contains('speaking')) {
    e.preventDefault();
    if (recognition) {
      try { recognition.start(); } catch(e) { /* already started */ }
    }
  }
});


// ─── Main input handler ───
async function handleInput(text) {
  if (!text || !text.trim()) return;

  console.log('[Anchor] Margaret said:', text);
  playAcknowledgement();

  try {
    const res = await fetch('/api/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    const data = await res.json();
    showResponse(data.response_text);

    if (data.audio_url) {
      audioEl.src = data.audio_url;
      audioEl.play().catch(() => {
        // Autoplay blocked — fall back to browser TTS
        browserFallback(data.response_text);
      });
    } else {
      browserFallback(data.response_text);
    }
  } catch (err) {
    console.error('[Anchor] Error:', err);
    showResponse("I'm having a little trouble — let's try again in a moment.");
    setTimeout(() => showResting(), 3000);
  }
}

function browserFallback(text) {
  if ('speechSynthesis' in window) {
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 0.92;
    utter.pitch = 1.05;
    utter.lang = 'en-GB';
    utter.onend = () => audioEl.dispatchEvent(new Event('ended'));
    speechSynthesis.speak(utter);
  } else {
    // No TTS at all — just show the text and return to resting after a pause
    setTimeout(() => showResting(), 5000);
  }
}

// ─── Acknowledgement sound (soft "mmm" placeholder) ───
const ackAudio = new Audio('/static/assets/ack.wav');
ackAudio.volume = 0.4;
function playAcknowledgement() {
  ackAudio.currentTime = 0;
  ackAudio.play().catch(() => { /* autoplay policy */ });
}

// ─── State transitions ───
function showResponse(text) {
  app.classList.remove('resting');
  app.classList.add('speaking');

  // Re-trigger the card animation by removing & re-adding
  responseCard.style.animation = 'none';
  responseCard.offsetHeight; // force reflow
  responseCard.style.animation = '';

  responseText.textContent = text;
  responseScreen.hidden = false;
}

function showResting() {
  app.classList.remove('speaking');
  app.classList.add('resting');

  // Fade out the response screen
  responseScreen.style.opacity = '0';
  responseScreen.style.transition = 'opacity 0.6s ease';

  setTimeout(() => {
    responseScreen.hidden = true;
    responseScreen.style.opacity = '';
    responseScreen.style.transition = '';
  }, 600);
}