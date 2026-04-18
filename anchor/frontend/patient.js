/* ─────────────────────────────────────────────
   Anchor — Patient-facing JavaScript
   Voice capture, latency-hiding, smooth state transitions.
   ───────────────────────────────────────────── */

const app            = document.getElementById('app');
const breathingRing  = document.getElementById('breathing-ring');
const responseScreen = document.getElementById('response-screen');
const responseCard   = document.getElementById('response-card');
const responseText   = document.getElementById('response-text');
const audioEl        = document.getElementById('anchor-voice');
const buttons        = document.querySelectorAll('#fallback-buttons button');

// ─── Demo overlay: show carer notifications if ?demo=1 ───
if (new URLSearchParams(window.location.search).has('demo')) {
  document.getElementById('carer-overlay').style.display = 'block';
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

// ─── Click the breathing ring to start listening ───
breathingRing.addEventListener('click', () => {
  if (recognition && !app.classList.contains('speaking')) {
    recognition.start();
  }
});

// Also listen on the ambient area (large click target)
document.getElementById('ambient').addEventListener('click', () => {
  if (recognition && !app.classList.contains('speaking')) {
    recognition.start();
  }
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
const ackAudio = new Audio('/static/assets/ack.mp3');
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