const statusEl = document.querySelector('#status');
const messagesEl = document.querySelector('#messages');
const form = document.querySelector('#chat');
const promptEl = document.querySelector('#prompt');
const sendEl = document.querySelector('#send');
const copyChatEl = document.querySelector('#copy-chat');
const chatHintEl = document.querySelector('#chat-hint');
const voiceEl = document.querySelector('#voice');
const voiceHintEl = document.querySelector('#voice-hint');
const conversationEl = document.querySelector('#conversation');
const conversationHintEl = document.querySelector('#conversation-hint');
const speechToggleEl = document.querySelector('#speech-toggle');
const stopSpeechEl = document.querySelector('#stop-speech');
const speechHintEl = document.querySelector('#speech-hint');
const autoMemoryToggleEl = document.querySelector('#auto-memory-toggle');
const autoMemoryHintEl = document.querySelector('#auto-memory-hint');
const memoryToggleEl = document.querySelector('#memory-toggle');
const memoryBackdropEl = document.querySelector('#memory-backdrop');
const memoryCloseEl = document.querySelector('#memory-close');
const memoryFormEl = document.querySelector('#memory-form');
const memoryIdEl = document.querySelector('#memory-id');
const memoryCategoryEl = document.querySelector('#memory-category');
const memoryTextEl = document.querySelector('#memory-text');
const memoryCancelEl = document.querySelector('#memory-cancel');
const memorySaveEl = document.querySelector('#memory-save');
const memoryStatusEl = document.querySelector('#memory-status');
const memoryListEl = document.querySelector('#memory-list');
const memoryCandidatesSectionEl = document.querySelector('#memory-candidates-section');
const memoryCandidatesEl = document.querySelector('#memory-candidates');
const memoryNoticeEl = document.querySelector('#memory-notice');
const memoryNoticeTextEl = document.querySelector('#memory-notice-text');
const memoryNoticeUndoEl = document.querySelector('#memory-notice-undo');
const learnToggleEl = document.querySelector('#learn-toggle');
const learnHintEl = document.querySelector('#learn-hint');
const speechSettingsToggleEl = document.querySelector('#speech-settings-toggle');
const speechSettingsBackdropEl = document.querySelector('#speech-settings-backdrop');
const speechSettingsCloseEl = document.querySelector('#speech-settings-close');
const speechSettingsFormEl = document.querySelector('#speech-settings-form');
const speechVoiceEl = document.querySelector('#speech-voice');
const speechRateEl = document.querySelector('#speech-rate');
const speechDefaultsEl = document.querySelector('#speech-defaults');
const speechPreviewEl = document.querySelector('#speech-preview');
const speechSettingsSaveEl = document.querySelector('#speech-settings-save');
const speechSettingsStatusEl = document.querySelector('#speech-settings-status');
const fishTuningEl = document.querySelector('#fish-tuning');
const speechStreamEl = document.querySelector('#speech-stream');
// Each Fish parameter maps to a slider + a value readout, keyed by the exact
// server-side parameter name so overrides can be sent through verbatim.
const fishControls = {
  temperature: {input: document.querySelector('#fish-temperature'), value: document.querySelector('#fish-temperature-value'), integer: false},
  top_p: {input: document.querySelector('#fish-top-p'), value: document.querySelector('#fish-top-p-value'), integer: false},
  repetition_penalty: {input: document.querySelector('#fish-repetition-penalty'), value: document.querySelector('#fish-repetition-penalty-value'), integer: false},
  max_new_tokens: {input: document.querySelector('#fish-max-tokens'), value: document.querySelector('#fish-max-tokens-value'), integer: true},
};
const {
  countUnsupportedScriptCharacters,
  formatConversationTranscript,
  formatLearnMemory,
  isConversationStopCommand,
  isLearnModeInterviewRequest,
  isLearnModeStartCommand,
  isLearnModeStopCommand,
  isMemoryControlCommand,
  shouldConsiderAutoMemory,
  trimConversationHistory,
  unsupportedActionResponse,
} = globalThis.JarvisCore;
let history = [];
let chatLimits = {maxMessages: 20, maxChars: 12000, maxMessageChars: 8000};
let audioState = null;
let releaseRequested = false;
let voiceReady = false;
let speechReady = false;
let speechEnabled = true;
let speechActive = false;
let speechRequestId = 0;
// Two chains so rendering can run ahead of playback (browser mode). speechQueue
// serializes PLAYBACK (clips play strictly in order); speechRenderChain serializes
// the fetch/render of each sentence's audio, one Fish render at a time. Because the
// render chain advances independently of playback, sentence N+1 is already being
// rendered while sentence N is still speaking, so its audio is usually buffered and
// ready the instant N ends — removing the render-latency gap between sentences.
let speechQueue = Promise.resolve();
let speechRenderChain = Promise.resolve();
const pendingSpeech = new Set();
// Where reply audio is played. 'host' means the server plays it (local dev on a
// machine with audio output); 'browser' means the server returns the rendered
// WAV and this client plays it — the model for the headless LAN server. Set from
// /api/health. currentAudio holds the element playing in browser mode so a stop
// can silence it immediately.
let playbackMode = 'host';
let currentAudio = null;
// Low-latency streaming playback for the neural (Fish) voice: audio is scheduled
// through a Web Audio context as raw PCM arrives, so speech starts ~0.3s in
// instead of after the whole sentence renders. Toggleable; falls back to the blob
// path on any failure. streamState tracks the in-flight stream so a stop can end it.
let streamingEnabled = storedSpeechSetting('jarvis.speech.stream') !== '0';
let audioCtx = null;
let streamState = null;
// Shared Web Audio scheduling cursor (in AudioContext time) spanning all the
// sentences of one reply, so chunks — even across sentence boundaries — play
// back-to-back with no gap, while the next sentence is generated ahead of time.
let streamClock = 0;
let conversationEnabled = false;
let conversationStarting = false;
let conversationAudio = null;
let conversationTurnId = 0;
let memoryReady = false;
let memoryItemChars = 1000;
let autoMemoryAvailable = false;
let autoMemoryEnabled = true;
let autoMemoryInitialized = false;
let autoMemoryQueue = [];
let autoMemoryTimer = null;
let autoMemoryRunning = false;
let lastAutoMemoryId = null;
let learnModeEnabled = false;
let learnSavedCount = 0;
let speechOptionsReady = false;
let speechOptionsLoading = false;
let speechOptions = null;
// Fish parameter metadata (ranges + configured defaults) from /api/speech/options,
// and the current per-browser values sent as overrides. Null until a Fish voice
// is available.
let fishMeta = null;
let fishParams = null;
let speechOverridden = false;
let speechVoice = null;
let speechRate = null;

promptEl.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    form.requestSubmit();
  }
});

function addMessage(role, text = '') {
  const el = document.createElement('article');
  el.className = role;
  el.textContent = text;
  messagesEl.appendChild(el);
  messagesEl.scrollTo({top: messagesEl.scrollHeight, behavior: 'smooth'});
  return el;
}

function setLearnMode(enabled, message = '') {
  if (enabled && !memoryReady) {
    learnHintEl.textContent = 'Learn mode is unavailable because local memory is not ready.';
    return false;
  }
  if (enabled && !learnModeEnabled) learnSavedCount = 0;
  learnModeEnabled = enabled;
  learnToggleEl.classList.toggle('active', enabled);
  learnToggleEl.setAttribute('aria-pressed', enabled ? 'true' : 'false');
  learnToggleEl.textContent = enabled ? 'Learning on' : 'Learn mode';
  if (message) learnHintEl.textContent = message;
  else if (enabled) {
    learnHintEl.textContent = 'Learn mode is on. Each answer is saved with JARVIS’s preceding question; avoid credentials and private identifiers.';
  } else {
    learnHintEl.textContent = 'Learn mode is off. Turn it on before a guided get-to-know-you conversation.';
  }
  return true;
}

function deliverLocalResponse(userText, responseText, speechMessage) {
  addMessage('user', userText);
  history = trimConversationHistory(
    [...history, {role: 'user', content: userText}],
    {maxMessages: chatLimits.maxMessages, maxChars: chatLimits.maxChars},
  );
  addMessage('assistant', responseText);
  history = trimConversationHistory(
    [...history, {role: 'assistant', content: responseText}],
    {maxMessages: chatLimits.maxMessages, maxChars: chatLimits.maxChars},
  );
  if (speechEnabled && speechReady) {
    const requestId = ++speechRequestId;
    speechQueue = Promise.resolve();
    speechRenderChain = Promise.resolve();
    queueSpeech(responseText, requestId, speechMessage);
  }
  return true;
}

async function saveLearnAnswer(answer) {
  if (!learnModeEnabled || !memoryReady) return;
  const preceding = history.at(-1);
  const question = preceding?.role === 'assistant' ? preceding.content : '';
  const text = formatLearnMemory(question, answer, memoryItemChars);
  if (!text) {
    learnHintEl.textContent = 'That answer was too long to save safely. It remains in chat; use Memory to save a shorter fact.';
    return;
  }
  try {
    const response = await fetch('/api/memories', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({category: 'general', text}),
    });
    let payload = {};
    try { payload = await response.json(); } catch { /* status below is sufficient */ }
    if (!response.ok) {
      learnHintEl.textContent = payload.error === 'memory_duplicate'
        ? 'Learn mode is on. That answer was already saved.'
        : 'Learn mode is on, but that answer was not saved. Check Memory; sensitive or oversized entries are rejected.';
      return;
    }
    learnSavedCount++;
    learnHintEl.textContent = `Learn mode is on. ${learnSavedCount} ${learnSavedCount === 1 ? 'answer' : 'answers'} saved and reviewable in Memory.`;
  } catch {
    learnHintEl.textContent = 'Learn mode is on, but local memory was unavailable and the answer was not saved.';
  }
}

function speechIdleMessage() {
  if (typeof speechVoice !== 'string' || !Number.isInteger(speechRate)) {
    return 'JARVIS streams every reply using the configured local voice.';
  }
  return `JARVIS streams every reply using the local ${speechVoice} voice at ${speechRate} WPM.`;
}

function speechPayload(text, voice = speechVoice, rate = speechRate) {
  const payload = (typeof voice === 'string' && Number.isInteger(rate)) ? {text, voice, rate} : {text};
  // Attach live Fish tuning only when the target voice is a Fish voice, and only
  // finite values — a stray NaN would serialize to null and the server would
  // (correctly) reject the whole request, silencing speech. Omitted params fall
  // back to the server defaults.
  if (fishParams && voiceEngineOf(voice) === 'fish') {
    const fish = {};
    for (const key of Object.keys(fishParams)) {
      if (Number.isFinite(fishParams[key])) fish[key] = fishParams[key];
    }
    if (Object.keys(fish).length) payload.fish = fish;
  }
  return payload;
}

// Play one rendered phrase in browser mode and resolve when it finishes, so the
// speech queue serializes playback the same way host mode serializes afplay. A
// superseding stop (a newer requestId) drops the phrase without playing it.
function playBrowserAudio(blob, requestId) {
  return new Promise((resolve) => {
    if (requestId !== speechRequestId) { resolve(); return; }
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;
    // Optionally route the element through the analyser so the blob fallback also
    // drives the orb. Only when the context is genuinely RUNNING: tapping an
    // element diverts it from the default output, so doing this against a
    // suspended context (common on iOS) plays nothing at all. Silence is a far
    // worse outcome than an orb that does not react, so the visual is the part
    // that gets sacrificed.
    try {
      const ctx = audioCtx && audioCtx.state === 'running' ? audioCtx : null;
      const sink = ctx ? audioSink() : null;
      if (ctx && sink) { ctx.createMediaElementSource(audio).connect(sink); startAmpLoop(); }
    } catch { /* not analysable: audio still plays, the orb just idles */ }
    let settled = false;
    const cleanup = () => {
      if (settled) return;
      settled = true;
      try { URL.revokeObjectURL(url); } catch { /* url already released */ }
      if (currentAudio === audio) currentAudio = null;
      resolve();
    };
    audio.onended = cleanup;
    audio.onerror = cleanup;
    audio.play().catch(cleanup);
  });
}

function stopBrowserAudio() {
  if (currentAudio) {
    try { currentAudio.pause(); currentAudio.src = ''; } catch { /* element already torn down */ }
    currentAudio = null;
  }
  if (streamState) {
    streamState.stopped = true;
    for (const reader of streamState.readers) { try { reader.cancel(); } catch { /* already closed */ } }
    streamState.readers.clear();
    for (const source of streamState.sources) { try { source.stop(); } catch { /* already stopped */ } }
    streamState.sources.clear();
    streamState = null;
  }
  streamClock = 0;
}

// Stream one sentence of raw int16 PCM (mono, 44.1 kHz) from Fish and schedule
// each chunk onto the shared clock. Resolves when GENERATION finishes (the reader
// drains) — NOT when playback finishes — so the caller's queue can immediately
// start generating the next sentence while this one is still playing out. Audio
// keeps playing via the scheduled buffer sources. Returns false (without playing)
// if streaming can't be used, so the caller can fall back to the blob path.
const FISH_STREAM_SAMPLE_RATE = 44100;
async function streamFishSentence(payload, requestId) {
  const ctx = getAudioContext();
  if (!ctx) return false;
  // resume() is asynchronous, and on iOS a context that has not finished
  // resuming schedules silently. Wait for it before committing to this path.
  if (ctx.state === 'suspended') {
    try { await ctx.resume(); } catch { /* fall through to the blob path */ }
    if (ctx.state !== 'running') return false;
  }
  let response;
  try {
    response = await fetch('/api/speak/stream', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
  } catch { return false; }
  if (!response.ok || !response.body) return false;
  if (requestId !== speechRequestId) { try { await response.body.cancel(); } catch { /* ignore */ } return true; }

  if (!streamState) streamState = {readers: new Set(), sources: new Set(), stopped: false};
  const state = streamState;
  const reader = response.body.getReader();
  state.readers.add(reader);
  // Continue the shared clock. If playback has caught up (first sentence, or the
  // generator fell behind), start just ahead of now; otherwise append seamlessly.
  if (streamClock < ctx.currentTime + 0.05) streamClock = ctx.currentTime + 0.10;
  let leftover = null;  // carries a trailing odd byte between network chunks
  try {
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      if (state.stopped || requestId !== speechRequestId) break;
      let bytes = value;
      if (leftover) {
        const merged = new Uint8Array(leftover.length + bytes.length);
        merged.set(leftover); merged.set(bytes, leftover.length);
        bytes = merged; leftover = null;
      }
      if (bytes.length % 2 === 1) { leftover = bytes.slice(bytes.length - 1); bytes = bytes.slice(0, bytes.length - 1); }
      if (bytes.length === 0) continue;
      const aligned = new Uint8Array(bytes);  // fresh buffer, byteOffset 0, even length
      const samples = new Int16Array(aligned.buffer, 0, aligned.length >> 1);
      const channel = new Float32Array(samples.length);
      for (let i = 0; i < samples.length; i++) channel[i] = samples[i] / 32768;
      const buffer = ctx.createBuffer(1, channel.length, FISH_STREAM_SAMPLE_RATE);
      buffer.getChannelData(0).set(channel);
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(audioSink() || ctx.destination);
      startAmpLoop();
      const startAt = Math.max(streamClock, ctx.currentTime);
      source.start(startAt);
      streamClock = startAt + buffer.duration;
      state.sources.add(source);
      source.onended = () => state.sources.delete(source);
    }
  } catch { /* stream error: stop scheduling; queue continues */ }
  state.readers.delete(reader);
  return true;  // generation done; scheduled audio plays on independently
}

// Lead-in buffer: before the FIRST clip of a reply plays, wait briefly so the
// render pipeline can get ahead and build a small backlog of ready clips. That
// backlog absorbs the case where a short sentence finishes speaking before the
// next sentence has finished rendering, which is what caused the residual gaps.
// Keyed by requestId so it applies once per reply. Tunable. Kept modest so it
// buffers short-sentence gaps without adding much to time-to-first-word; the
// render pipeline (which runs ahead during playback) does most of the smoothing.
const SPEECH_LEAD_IN_MS = 600;
let speechLeadInDoneFor = -1;

// Browsers block programmatic audio that isn't tied to a recent user gesture. The
// first reply plays seconds after the send gesture (after rendering), by which
// point that activation has lapsed, so it would be silently refused. Playing a
// muted, one-frame WAV during the user's first interaction grants the page sticky
// media activation, so every later Audio.play() (including delayed ones) works.
let audioUnlocked = false;

function silentWavBlob() {
  const buf = new ArrayBuffer(46);
  const view = new DataView(buf);
  const tag = (offset, text) => { for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i)); };
  tag(0, 'RIFF'); view.setUint32(4, 38, true); tag(8, 'WAVE');
  tag(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 8000, true); view.setUint32(28, 16000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  tag(36, 'data'); view.setUint32(40, 2, true); // one 16-bit sample of silence (already zero)
  return new Blob([buf], {type: 'audio/wav'});
}

// Audio-reactive orb. An AnalyserNode sits between the speech sources and the
// speakers, so the rings are driven by the actual waveform rather than a faked
// animation. The sampling loop runs ONLY while audio is scheduled — it starts
// when playback starts and stops itself when the graph goes quiet — so an idle
// page costs nothing beyond the CSS rotations.
let analyserNode = null;
let ampRaf = 0;
let ampData = null;

function getAudioContext() {
  if (!audioCtx) {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) return null;
    try { audioCtx = new Ctor(); } catch { audioCtx = null; return null; }
  }
  if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => { /* resumes on next gesture */ });
  return audioCtx;
}

// Everything that makes sound connects here instead of straight to destination.
function audioSink() {
  const ctx = getAudioContext();
  if (!ctx) return null;
  if (!analyserNode) {
    analyserNode = ctx.createAnalyser();
    analyserNode.fftSize = 256;
    analyserNode.smoothingTimeConstant = 0.75;
    analyserNode.connect(ctx.destination);
    ampData = new Uint8Array(analyserNode.frequencyBinCount);
  }
  return analyserNode;
}

function stopAmpLoop() {
  if (ampRaf) cancelAnimationFrame(ampRaf);
  ampRaf = 0;
  document.documentElement.style.setProperty('--amp', '0');
}

function startAmpLoop() {
  if (ampRaf || !analyserNode || !ampData) return;
  let quietFrames = 0;
  const tick = () => {
    analyserNode.getByteTimeDomainData(ampData);
    // Peak deviation from the 128 midpoint, normalised and gently curved so
    // quiet speech still moves the rings a little.
    let peak = 0;
    for (let i = 0; i < ampData.length; i++) {
      const d = Math.abs(ampData[i] - 128);
      if (d > peak) peak = d;
    }
    const amp = Math.min(1, Math.pow(peak / 90, 0.8));
    document.documentElement.style.setProperty('--amp', amp.toFixed(3));
    // Stop once the graph has been silent for about a second, so the loop never
    // outlives the audio and a paused tab settles to zero cost.
    quietFrames = amp < 0.02 ? quietFrames + 1 : 0;
    if (quietFrames > 60 || document.hidden) { stopAmpLoop(); return; }
    ampRaf = requestAnimationFrame(tick);
  };
  ampRaf = requestAnimationFrame(tick);
}

// A hidden tab should never animate: browsers throttle rAF anyway, but this also
// clears the last amplitude so nothing is left mid-pulse on return.
document.addEventListener('visibilitychange', () => { if (document.hidden) stopAmpLoop(); });

// --- Spoken greeting on start-up -------------------------------------------
//
// Browsers refuse to play audio until the page has had a user gesture, so the
// greeting cannot fire on load alone: it waits until audio is unlocked AND the
// speech engine reports ready, then speaks once per page load. A different line
// is chosen each time (and never the same one twice in a row) so start-up does
// not become rote.
const GREETINGS = [
  '{t}, sir. All systems are online and functioning within normal parameters.',
  'Systems coming online. Diagnostics complete, all functions nominal. How may I assist you today, sir?',
  '{t}, sir. Local model, speech synthesis, and recognition are all resident and ready.',
  'Powering up. All subsystems report ready. What can I do for you, sir?',
  '{t}, sir. I am online and standing by.',
  'Initialization complete. Everything is running as expected, sir. How can I help?',
  'All systems tested and ready, sir. Awaiting your instruction.',
  '{t}. Local systems are green across the board. What shall we work on, sir?',
  'Online and at your service, sir. Everything checks out.',
];
let greeted = false;

function timeOfDayGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

function pickGreeting() {
  const last = storedSpeechSetting('jarvis.greeting.last');
  let choices = GREETINGS.filter((line) => line !== last);
  if (!choices.length) choices = GREETINGS;
  const line = choices[Math.floor(Math.random() * choices.length)];
  storeSpeechSetting('jarvis.greeting.last', line);
  return line.replace('{t}', timeOfDayGreeting());
}

function maybeGreet() {
  if (greeted || !audioUnlocked || !speechEnabled || !speechReady) return;
  greeted = true;
  const line = pickGreeting();
  // Shown in the transcript but deliberately NOT added to `history`: this is
  // JARVIS greeting the room, not a turn the model should later treat as context.
  addMessage('assistant', line);
  const requestId = ++speechRequestId;
  speechQueue = Promise.resolve();
  speechRenderChain = Promise.resolve();
  queueSpeech(line, requestId, 'JARVIS is coming online.');
}

function unlockAudio() {
  if (audioUnlocked) return;
  audioUnlocked = true;
  getAudioContext();  // create + resume the Web Audio context within the gesture
  setTimeout(maybeGreet, 60);  // speech may not be reported ready until the first poll
  try {
    const url = URL.createObjectURL(silentWavBlob());
    const audio = new Audio(url);
    audio.volume = 0;
    const done = () => { try { URL.revokeObjectURL(url); } catch { /* already released */ } };
    audio.play().then(() => { audio.pause(); done(); }).catch(done);
  } catch { /* best-effort; real playback will still try */ }
}

function storedSpeechSetting(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function storeSpeechSetting(key, value) {
  try { localStorage.setItem(key, String(value)); } catch { /* browser persistence is optional */ }
}

function removeSpeechSetting(key) {
  try { localStorage.removeItem(key); } catch { /* browser persistence is optional */ }
}

function clearStoredSpeechOverride() {
  for (const key of ['voice', 'voiceDefault', 'rate', 'rateDefault']) removeSpeechSetting(`jarvis.speech.${key}`);
}

function setAutoMemory(enabled, message = '') {
  const nextEnabled = Boolean(enabled) && autoMemoryAvailable;
  const changed = nextEnabled !== (autoMemoryToggleEl.getAttribute('aria-pressed') === 'true');
  autoMemoryEnabled = nextEnabled;
  autoMemoryToggleEl.classList.toggle('active', autoMemoryEnabled);
  autoMemoryToggleEl.setAttribute('aria-pressed', autoMemoryEnabled ? 'true' : 'false');
  autoMemoryToggleEl.textContent = autoMemoryEnabled ? 'Auto memory on' : 'Auto memory off';
  storeSpeechSetting('jarvis.autoMemory.enabled', autoMemoryEnabled ? 'true' : 'false');
  if (!autoMemoryEnabled) {
    if (autoMemoryTimer) clearTimeout(autoMemoryTimer);
    autoMemoryTimer = null;
    autoMemoryQueue = [];
    memoryNoticeEl.hidden = true;
  }
  if (message) autoMemoryHintEl.textContent = message;
  else if (changed && autoMemoryEnabled) autoMemoryHintEl.textContent = 'Automatic memory is on. Durable user facts are assessed locally; uncertain items require review.';
  else if (changed && autoMemoryAvailable) autoMemoryHintEl.textContent = 'Automatic memory is off. Explicit Memory and Learn mode still work.';
  else if (changed) autoMemoryHintEl.textContent = 'Automatic memory is unavailable. Nothing is being captured.';
}

function showMemoryNotice(item) {
  if (!item || typeof item.id !== 'string') return;
  lastAutoMemoryId = item.id;
  const preview = typeof item.text === 'string' ? item.text.replace(/^User said:\s*/i, '').slice(0, 180) : 'a durable fact';
  memoryNoticeTextEl.textContent = `Remembered locally: ${preview}`;
  memoryNoticeEl.hidden = false;
}

function scheduleAutoMemory(question, user) {
  if (!autoMemoryEnabled || !autoMemoryAvailable || learnModeEnabled || !shouldConsiderAutoMemory(user, question)) return;
  autoMemoryQueue.push({question: typeof question === 'string' ? question : '', user});
  if (autoMemoryQueue.length > 8) autoMemoryQueue = autoMemoryQueue.slice(-8);
  if (autoMemoryTimer) clearTimeout(autoMemoryTimer);
  autoMemoryHintEl.textContent = 'A likely durable fact is queued for private local review.';
  autoMemoryTimer = setTimeout(() => { void flushAutoMemory(); }, 3000);
}

async function flushAutoMemory({keepalive = false} = {}) {
  if (autoMemoryRunning || !autoMemoryEnabled || !autoMemoryAvailable || !autoMemoryQueue.length) return;
  const turns = autoMemoryQueue.splice(0, 8);
  autoMemoryTimer = null;
  autoMemoryRunning = true;
  autoMemoryHintEl.textContent = 'Reviewing likely durable facts with the local model…';
  try {
    const response = await fetch('/api/memory/curate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({turns}),
      keepalive,
    });
    let payload = {};
    try { payload = await response.json(); } catch { /* status below is sufficient */ }
    if (response.status === 409) {
      autoMemoryQueue = [...turns, ...autoMemoryQueue].slice(0, 8);
      autoMemoryHintEl.textContent = 'Local memory review is busy; this fact will be retried shortly.';
      autoMemoryTimer = setTimeout(() => { void flushAutoMemory(); }, 2500);
      return;
    }
    if (!response.ok || !Array.isArray(payload.saved) || !Array.isArray(payload.candidates)) throw new Error('curation failed');
    if (payload.saved.length) showMemoryNotice(payload.saved.at(-1));
    if (payload.candidates.length) {
      autoMemoryHintEl.textContent = `${payload.candidates.length} uncertain or conflicting ${payload.candidates.length === 1 ? 'item needs' : 'items need'} review in Memory.`;
    } else if (payload.saved.length) {
      autoMemoryHintEl.textContent = `${payload.saved.length} durable ${payload.saved.length === 1 ? 'fact was' : 'facts were'} saved locally. Use Undo or review Memory.`;
    } else {
      autoMemoryHintEl.textContent = 'No durable fact was saved from that turn.';
    }
    if (!memoryBackdropEl.hidden) await loadMemories();
  } catch {
    autoMemoryHintEl.textContent = 'Automatic local review was unavailable; nothing from that batch was saved.';
  } finally {
    autoMemoryRunning = false;
    if (autoMemoryQueue.length && !autoMemoryTimer) autoMemoryTimer = setTimeout(() => { void flushAutoMemory(); }, 3000);
  }
}

async function loadSpeechOptions() {
  if (speechOptionsReady || speechOptionsLoading || !speechReady) return;
  speechOptionsLoading = true;
  speechSettingsStatusEl.textContent = 'Loading installed English voices…';
  try {
    const response = await fetch('/api/speech/options', {cache: 'no-store'});
    const payload = await response.json();
    if (!response.ok || !Array.isArray(payload.voices) || !payload.voices.length) throw new Error('speech options unavailable');
    const knownEngine = (engine) => (engine === 'piper' || engine === 'fish' ? engine : 'say');
    const voices = payload.voices
      .filter((item) => item && typeof item.name === 'string' && typeof item.locale === 'string')
      .map((item) => ({name: item.name, locale: item.locale, engine: knownEngine(item.engine)}));
    if (!voices.length) throw new Error('speech options unavailable');
    const minimumRate = Number.isInteger(payload.minimum_rate) ? payload.minimum_rate : 120;
    const maximumRate = Number.isInteger(payload.maximum_rate) ? payload.maximum_rate : 350;
    const defaultRate = Number.isInteger(payload.default_rate) ? payload.default_rate : 190;
    const selection = JarvisCore.resolveSpeechSelection(
      {voices, minimumRate, maximumRate, defaultRate, defaultVoice: payload.default_voice},
      {
        voice: storedSpeechSetting('jarvis.speech.voice'),
        voiceDefault: storedSpeechSetting('jarvis.speech.voiceDefault'),
        rate: storedSpeechSetting('jarvis.speech.rate'),
        rateDefault: storedSpeechSetting('jarvis.speech.rateDefault'),
      },
    );
    // A stored override that no longer matches the configured default is
    // discarded here so an edited config.local.json takes effect on reload.
    if (selection.stale.length) clearStoredSpeechOverride();
    speechOptions = {voices, minimumRate, maximumRate, defaultRate: selection.defaultRate, defaultVoice: selection.defaultVoice};
    speechVoice = selection.voice;
    speechRate = selection.rate;
    speechOverridden = selection.overridden;
    speechVoiceEl.replaceChildren();
    for (const item of voices) {
      const option = document.createElement('option');
      option.value = item.name;
      // The engine is visible so a neural voice can be compared against a
      // built-in one without guessing which is which.
      const engine = item.engine === 'piper' || item.engine === 'fish' ? 'neural' : 'built-in';
      option.textContent = `${item.name} (${item.locale.replace('_', '-')}, ${engine})`;
      speechVoiceEl.appendChild(option);
    }
    speechVoiceEl.value = speechVoice;
    speechRateEl.min = String(minimumRate);
    speechRateEl.max = String(maximumRate);
    speechRateEl.value = String(speechRate);
    initFishTuning(payload.fish);
    speechOptionsReady = true;
    const neural = voices.filter((item) => item.engine === 'piper' || item.engine === 'fish').length;
    const inventory = neural
      ? `${voices.length} voices are available, including ${neural} neural.`
      : `${voices.length} installed English voices are available.`;
    speechSettingsStatusEl.textContent = speechOverridden
      ? `${inventory} This browser overrides the configured voice.`
      : `${inventory} Using the configured voice.`;
    if (speechReady && speechEnabled && !speechActive) speechHintEl.textContent = speechIdleMessage();
  } catch {
    speechOptionsReady = false;
    speechSettingsStatusEl.textContent = 'Installed speech options are unavailable. The configured voice remains active.';
  } finally {
    speechOptionsLoading = false;
    speechSettingsToggleEl.disabled = !speechReady || !speechOptionsReady;
  }
}

async function openSpeechSettings() {
  await loadSpeechOptions();
  if (!speechOptionsReady) return;
  if (!memoryBackdropEl.hidden) closeMemoryPanel();
  speechVoiceEl.value = speechVoice;
  speechRateEl.value = String(speechRate);
  updateFishTuningVisibility();
  speechSettingsBackdropEl.hidden = false;
  speechSettingsCloseEl.focus();
}

function closeSpeechSettings() {
  speechSettingsBackdropEl.hidden = true;
  speechSettingsToggleEl.focus();
}

function fishStorageKey(name) {
  return `jarvis.speech.fish.${name}`;
}

function clampFishValue(name, raw) {
  const meta = fishMeta && fishMeta[name];
  if (!meta) return null;
  let value = fishControls[name].integer ? Number.parseInt(raw, 10) : Number.parseFloat(raw);
  if (!Number.isFinite(value)) value = Number(meta.value);
  if (!Number.isFinite(value)) return null;  // never emit NaN into fishParams
  value = Math.min(meta.max, Math.max(meta.min, value));
  return fishControls[name].integer ? Math.round(value) : value;
}

function formatFishValue(name, value) {
  return fishControls[name].integer ? String(value) : value.toFixed(2);
}

function voiceEngineOf(name) {
  const voice = speechOptions && speechOptions.voices.find((item) => item.name === name);
  return voice ? voice.engine : 'say';
}

function updateFishTuningVisibility() {
  if (!fishTuningEl) return;
  fishTuningEl.hidden = !(Boolean(fishParams) && voiceEngineOf(speechVoiceEl.value) === 'fish');
}

// Build the tuning panel from server metadata, seeding each slider from a saved
// per-browser value or the configured default. No-op (and hidden) when no Fish
// voice is available, so built-in/Piper-only setups are unaffected.
function initFishTuning(fish) {
  if (!fish || fish.available !== true || !fish.parameters) {
    fishMeta = null;
    fishParams = null;
    if (fishTuningEl) fishTuningEl.hidden = true;
    return;
  }
  fishMeta = {};
  fishParams = {};
  for (const name of Object.keys(fishControls)) {
    const meta = fish.parameters[name];
    const control = fishControls[name];
    if (!meta || !control.input || !Number.isFinite(meta.min) || !Number.isFinite(meta.max)) continue;
    fishMeta[name] = {min: meta.min, max: meta.max, step: meta.step, value: meta.value};
    control.input.min = String(meta.min);
    control.input.max = String(meta.max);
    control.input.step = String(meta.step);
    const stored = clampFishValue(name, storedSpeechSetting(fishStorageKey(name)));
    const value = stored === null ? clampFishValue(name, meta.value) : stored;
    if (value === null) continue;  // unresolvable: leave to the server default
    fishParams[name] = value;
    control.input.value = String(value);
    if (control.value) control.value.textContent = formatFishValue(name, value);
  }
  updateFishTuningVisibility();
}

function onFishParamInput(name) {
  const control = fishControls[name];
  const value = clampFishValue(name, control.input.value);
  if (value === null || !fishParams) return;
  fishParams[name] = value;
  if (control.value) control.value.textContent = formatFishValue(name, value);
  storeSpeechSetting(fishStorageKey(name), value);
}

function resetFishDefaults() {
  if (!fishMeta || !fishParams) return;
  for (const name of Object.keys(fishControls)) {
    if (!fishMeta[name]) continue;
    const value = clampFishValue(name, fishMeta[name].value);
    fishParams[name] = value;
    fishControls[name].input.value = String(value);
    if (fishControls[name].value) fishControls[name].value.textContent = formatFishValue(name, value);
    storeSpeechSetting(fishStorageKey(name), value);
  }
}

function selectedSpeechSettings() {
  if (!speechOptions) return null;
  const voice = speechVoiceEl.value;
  const rate = Number.parseInt(speechRateEl.value, 10);
  if (!speechOptions.voices.some((item) => item.name === voice)) return null;
  if (!Number.isInteger(rate) || rate < speechOptions.minimumRate || rate > speechOptions.maximumRate) return null;
  return {voice, rate};
}

async function previewSpeechSettings() {
  const selected = selectedSpeechSettings();
  if (!selected || speechPreviewEl.disabled) {
    speechSettingsStatusEl.textContent = 'Choose an installed voice and a valid speaking rate.';
    return;
  }
  speechPreviewEl.disabled = true;
  await stopSpeech();
  const previewRequestId = speechRequestId;
  speechActive = true;
  stopSpeechEl.disabled = false;
  speechSettingsStatusEl.textContent = 'Playing a preview…';
  try {
    const response = await fetch('/api/speak', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(speechPayload('At your service. Local speech settings are ready.', selected.voice, selected.rate)),
    });
    if (!response.ok) throw new Error('preview failed');
    if (playbackMode === 'browser') {
      const blob = await response.blob();
      await playBrowserAudio(blob, previewRequestId);
    }
    speechSettingsStatusEl.textContent = 'Preview complete. Save to use these settings for replies.';
  } catch {
    speechSettingsStatusEl.textContent = 'The local speech preview was unavailable.';
  } finally {
    speechActive = false;
    stopSpeechEl.disabled = true;
    speechPreviewEl.disabled = false;
    speechHintEl.textContent = speechEnabled ? speechIdleMessage() : 'JARVIS voice is muted.';
  }
}

async function checkHealth() {
  try {
    const response = await fetch('/api/health', {cache: 'no-store'});
    const state = await response.json();
    const limits = state.limits;
    if (limits && Number.isInteger(limits.history_messages) && Number.isInteger(limits.history_chars) && Number.isInteger(limits.message_chars)) {
      chatLimits = {maxMessages: limits.history_messages, maxChars: limits.history_chars, maxMessageChars: limits.message_chars};
      promptEl.maxLength = chatLimits.maxMessageChars;
    }
    statusEl.textContent = response.ok ? 'Local model ready' : 'Model offline';
    statusEl.className = response.ok ? 'ready' : 'offline';
    voiceReady = response.ok && state.stt === 'ready' && Boolean(navigator.mediaDevices?.getUserMedia);
    if (!voiceReady && audioState) discardRecording('Recording stopped because local speech recognition is unavailable.');
    if (!voiceReady && conversationEnabled) stopConversation('Conversation mode stopped because the local model or speech recognition is unavailable.');
    if (!audioState && !voiceEl.classList.contains('transcribing')) voiceEl.disabled = !voiceReady || sendEl.disabled || conversationEnabled;
    conversationEl.disabled = !voiceReady || conversationStarting || (!conversationEnabled && sendEl.disabled);
    speechReady = response.ok && state.tts === 'ready';
    speechToggleEl.disabled = !speechReady;
    speechSettingsToggleEl.disabled = !speechReady || !speechOptionsReady;
    if (speechReady && !speechOptionsReady) void loadSpeechOptions();
    speechToggleEl.textContent = speechEnabled ? 'Voice on' : 'Voice muted';
    speechToggleEl.setAttribute('aria-pressed', speechEnabled ? 'true' : 'false');
    playbackMode = state.playback === 'browser' ? 'browser' : 'host';
    // Greet only AFTER playbackMode is known. Greeting earlier queued speech
    // while the mode was still its 'host' default, so the client asked for the
    // audio and then discarded it, expecting a server-side device to play it —
    // the greeting appeared in the transcript but was never heard.
    if (speechReady) maybeGreet();
    // In browser mode the server's own "speaking" flag stays false (no host
    // channel is used), so local pending/playing state is the source of truth.
    const streamPlaying = Boolean(audioCtx) && streamClock > audioCtx.currentTime;
    const browserSpeaking = playbackMode === 'browser' && (pendingSpeech.size > 0 || currentAudio !== null || streamPlaying);
    speechActive = Boolean(state.speaking) || pendingSpeech.size > 0 || browserSpeaking;
    stopSpeechEl.disabled = !speechActive;
    if (!speechReady) speechHintEl.textContent = 'Local speech is unavailable. Text and speech input still work.';
    else if (!speechEnabled) speechHintEl.textContent = 'JARVIS voice is muted.';
    else if (speechActive) speechHintEl.textContent = playbackMode === 'browser' ? 'JARVIS is speaking on this device.' : 'JARVIS is speaking locally.';
    else speechHintEl.textContent = speechIdleMessage();
    if (!speechReady && !speechSettingsBackdropEl.hidden) closeSpeechSettings();
    memoryReady = response.ok && state.memory === 'ready';
    autoMemoryAvailable = memoryReady && state.auto_memory === 'ready';
    if (!autoMemoryInitialized) {
      autoMemoryEnabled = storedSpeechSetting('jarvis.autoMemory.enabled') !== 'false';
      autoMemoryInitialized = true;
    }
    autoMemoryToggleEl.disabled = !autoMemoryAvailable;
    if (autoMemoryAvailable) setAutoMemory(autoMemoryEnabled);
    else {
      autoMemoryToggleEl.classList.remove('active');
      autoMemoryToggleEl.setAttribute('aria-pressed', 'false');
      autoMemoryToggleEl.textContent = 'Auto memory unavailable';
      autoMemoryHintEl.textContent = 'Automatic memory is unavailable. Nothing is being captured.';
    }
    memoryToggleEl.disabled = !memoryReady;
    learnToggleEl.disabled = !memoryReady;
    if (limits && Number.isInteger(limits.memory_item_chars)) {
      memoryItemChars = limits.memory_item_chars;
      memoryTextEl.maxLength = memoryItemChars;
    }
    if (!memoryReady && learnModeEnabled) setLearnMode(false, 'Learn mode stopped because local memory is unavailable.');
    if (!memoryReady && !memoryBackdropEl.hidden) closeMemoryPanel();
    return response.ok;
  } catch {
    voiceReady = false;
    speechReady = false;
    if (audioState) discardRecording('Recording stopped because the application is unavailable.');
    else voiceEl.disabled = true;
    if (conversationEnabled) stopConversation('Conversation mode stopped because the application is unavailable.');
    conversationEl.disabled = true;
    speechToggleEl.disabled = true;
    speechSettingsToggleEl.disabled = true;
    stopSpeechEl.disabled = true;
    statusEl.textContent = 'App offline'; statusEl.className = 'offline';
    memoryReady = false;
    autoMemoryAvailable = false;
    autoMemoryToggleEl.disabled = true;
    autoMemoryToggleEl.classList.remove('active');
    autoMemoryToggleEl.setAttribute('aria-pressed', 'false');
    autoMemoryToggleEl.textContent = 'Auto memory unavailable';
    autoMemoryHintEl.textContent = 'Automatic memory is unavailable. Nothing is being captured.';
    memoryToggleEl.disabled = true;
    learnToggleEl.disabled = true;
    if (learnModeEnabled) setLearnMode(false, 'Learn mode stopped because the application is unavailable.');
    if (!memoryBackdropEl.hidden) closeMemoryPanel();
    if (!speechSettingsBackdropEl.hidden) closeSpeechSettings();
    return false;
  }
}

function resetMemoryForm() {
  memoryIdEl.value = '';
  memoryCategoryEl.value = 'general';
  memoryTextEl.value = '';
  memoryCancelEl.hidden = true;
  memorySaveEl.textContent = 'Save memory';
}

async function deleteMemoryItem(item, noun = 'saved memory') {
  if (!window.confirm(`Delete this ${noun}? This cannot be undone from the chat.`)) return;
  memoryStatusEl.textContent = 'Deleting local memory…';
  try {
    const response = await fetch(`/api/memories/${encodeURIComponent(item.id)}`, {method: 'DELETE'});
    if (!response.ok) throw new Error('delete failed');
    if (memoryIdEl.value === item.id) resetMemoryForm();
    if (lastAutoMemoryId === item.id) memoryNoticeEl.hidden = true;
    await loadMemories('Memory deleted.');
  } catch {
    memoryStatusEl.textContent = 'Memory could not be deleted. Nothing changed.';
  }
}

function renderMemories(items, candidates = []) {
  memoryListEl.replaceChildren();
  if (!items.length) {
    const empty = document.createElement('p');
    empty.className = 'memory-empty';
    empty.textContent = 'No memories are saved yet.';
    memoryListEl.appendChild(empty);
  }
  for (const item of items) {
    const container = document.createElement('section');
    container.className = 'memory-item';
    container.dataset.id = item.id;
    const meta = document.createElement('div');
    meta.className = 'memory-meta';
    const category = document.createElement('span');
    category.textContent = `${item.category} · ${item.origin || 'explicit'}`;
    const updated = document.createElement('span');
    updated.textContent = item.updated_at === item.created_at ? 'saved' : 'updated';
    meta.append(category, updated);
    const text = document.createElement('p');
    text.textContent = item.text;
    const actions = document.createElement('div');
    actions.className = 'memory-actions';
    const edit = document.createElement('button');
    edit.type = 'button'; edit.dataset.action = 'edit'; edit.textContent = 'Edit';
    edit.addEventListener('click', () => {
      memoryIdEl.value = item.id;
      memoryCategoryEl.value = item.category;
      memoryTextEl.value = item.text;
      memoryCancelEl.hidden = false;
      memorySaveEl.textContent = 'Update memory';
      memoryTextEl.focus();
    });
    const remove = document.createElement('button');
    remove.type = 'button'; remove.dataset.action = 'delete'; remove.textContent = 'Delete';
    remove.addEventListener('click', () => { void deleteMemoryItem(item); });
    actions.append(edit, remove);
    container.append(meta, text, actions);
    memoryListEl.appendChild(container);
  }

  memoryCandidatesEl.replaceChildren();
  memoryCandidatesSectionEl.hidden = candidates.length === 0;
  for (const item of candidates) {
    const container = document.createElement('section');
    container.className = 'memory-item candidate';
    container.dataset.id = item.id;
    const meta = document.createElement('div');
    meta.className = 'memory-meta';
    const category = document.createElement('span');
    category.textContent = `${item.category} · review`;
    const confidence = document.createElement('span');
    confidence.textContent = Number.isFinite(item.confidence) ? `${Math.round(item.confidence * 100)}% confidence` : 'uncertain';
    meta.append(category, confidence);
    const text = document.createElement('p');
    text.textContent = item.text;
    const actions = document.createElement('div');
    actions.className = 'memory-actions';
    const approve = document.createElement('button');
    approve.type = 'button'; approve.dataset.action = 'approve'; approve.textContent = 'Approve';
    approve.addEventListener('click', async () => {
      memoryStatusEl.textContent = 'Approving local memory…';
      try {
        const response = await fetch(`/api/memories/${encodeURIComponent(item.id)}`, {
          method: 'PATCH',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({action: 'approve'}),
        });
        if (!response.ok) throw new Error('approve failed');
        await loadMemories('Memory approved and available to JARVIS.');
      } catch {
        memoryStatusEl.textContent = 'Memory could not be approved. Nothing changed.';
      }
    });
    const remove = document.createElement('button');
    remove.type = 'button'; remove.dataset.action = 'delete'; remove.textContent = 'Reject';
    remove.addEventListener('click', () => { void deleteMemoryItem(item, 'memory candidate'); });
    actions.append(approve, remove);
    container.append(meta, text, actions);
    memoryCandidatesEl.appendChild(container);
  }
}

async function loadMemories(successMessage = '') {
  if (!memoryReady) return;
  try {
    const response = await fetch('/api/memories', {cache: 'no-store'});
    const payload = await response.json();
    if (!response.ok || !Array.isArray(payload.items) || !Array.isArray(payload.candidates)) throw new Error('memory unavailable');
    renderMemories(payload.items, payload.candidates);
    memoryStatusEl.textContent = successMessage || `${payload.items.length} saved ${payload.items.length === 1 ? 'memory' : 'memories'} · ${payload.candidates.length} awaiting review.`;
  } catch {
    memoryStatusEl.textContent = 'Memory is unavailable. No changes were made.';
  }
}

async function openMemoryPanel() {
  if (!memoryReady) return;
  if (!speechSettingsBackdropEl.hidden) closeSpeechSettings();
  memoryBackdropEl.hidden = false;
  memoryCloseEl.focus();
  await loadMemories();
}

function closeMemoryPanel() {
  memoryBackdropEl.hidden = true;
  resetMemoryForm();
  memoryToggleEl.focus();
}

async function stopSpeech(message = '') {
  speechRequestId++;
  speechActive = false;
  pendingSpeech.clear();
  speechQueue = Promise.resolve();
  speechRenderChain = Promise.resolve();
  stopSpeechEl.disabled = true;
  // Silence browser-mode playback locally; the server call stops any host-mode
  // afplay. Both run so a stop works regardless of the current playback mode.
  stopBrowserAudio();
  try { await fetch('/api/speak/stop', {method: 'POST'}); } catch { /* health polling will report availability */ }
  if (message) speechHintEl.textContent = message;
}

function speakActiveStatus(requestId, activeMessage) {
  if (requestId !== speechRequestId) return;
  speechActive = true;
  stopSpeechEl.disabled = false;
  speechHintEl.textContent = activeMessage;
}

function speechTaskFailed(requestId) {
  if (requestId === speechRequestId) speechHintEl.textContent = 'Speech was unavailable. The written reply will continue.';
}

function speechTaskSettled(requestId, pending) {
  pendingSpeech.delete(pending);
  if (pendingSpeech.size === 0 && requestId === speechRequestId) {
    speechActive = false;
    stopSpeechEl.disabled = true;
    speechHintEl.textContent = speechIdleMessage();
  }
}

// Streaming tasks resolve when a sentence finishes GENERATING, but its audio is
// still playing out on the shared clock. When the last sentence's generation is
// done, defer the return-to-idle until the scheduled audio has actually finished,
// so the "speaking" state and Stop button stay accurate through the tail.
function streamTaskSettled(requestId, pending) {
  pendingSpeech.delete(pending);
  if (pendingSpeech.size !== 0 || requestId !== speechRequestId) return;
  const remainingMs = audioCtx ? Math.max(0, (streamClock - audioCtx.currentTime) * 1000) : 0;
  setTimeout(() => {
    // Only return to idle once the scheduled audio has really finished. Do NOT
    // reset streamClock here: sentences can settle between the LLM producing the
    // next one, and zeroing the clock while audio is still queued would make the
    // following sentence schedule at "now" — playing ON TOP of what is still
    // speaking (heard as a sentence cutting off mid-word). A clock already in the
    // past is handled naturally where the next sentence starts scheduling.
    if (requestId === speechRequestId && pendingSpeech.size === 0
        && (!audioCtx || streamClock <= audioCtx.currentTime + 0.05)) {
      speechActive = false;
      stopSpeechEl.disabled = true;
      speechHintEl.textContent = speechIdleMessage();
    }
  }, remainingMs + 80);
}

function queueSpeech(text, requestId, activeMessage = 'JARVIS is speaking while the reply is generated.') {
  const spokenText = text.replace(/[`*_#>]/g, ' ').replace(/\s+/g, ' ').trim();
  if (!spokenText || requestId !== speechRequestId) return;
  const pending = {};
  pendingSpeech.add(pending);
  const requestSpeech = () => fetch('/api/speak', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(speechPayload(spokenText)),
  });

  if (playbackMode === 'browser' && streamingEnabled && voiceEngineOf(speechVoice) === 'fish') {
    // Low-latency streaming path: each sentence is one progressive stream that
    // starts playing almost immediately. Serialized on the play chain; on any
    // failure it falls back to a one-off blob render so speech never just stops.
    const task = speechQueue.then(async () => {
      if (!speechEnabled || requestId !== speechRequestId) return;
      speakActiveStatus(requestId, activeMessage);
      const streamed = await streamFishSentence(speechPayload(spokenText), requestId);
      if (streamed === false) {
        const response = await requestSpeech();
        if (!response.ok) throw new Error('speech failed');
        if (requestId !== speechRequestId) return;
        const blob = await response.blob();
        await playBrowserAudio(blob, requestId);
      }
    });
    speechQueue = task.catch(() => speechTaskFailed(requestId)).finally(() => streamTaskSettled(requestId, pending));
    return;
  }

  if (playbackMode === 'browser') {
    // Render this sentence on the render chain (sequential, one Fish render at a
    // time, preserving order) so it runs ahead while earlier sentences play.
    const renderPromise = speechRenderChain.then(async () => {
      // Do NOT gate on speechReady here: it is driven by the periodic health poll,
      // which can briefly flip to unavailable while Fish is busy rendering. Gating
      // on it would silently drop a mid-reply sentence. Stop/mute/newer-reply are
      // still honored via speechEnabled and the requestId check; a genuine outage
      // surfaces as a failed fetch below.
      if (!speechEnabled || requestId !== speechRequestId) return null;
      const response = await requestSpeech();
      if (!response.ok) throw new Error('speech failed');
      return await response.blob();
    });
    // A failed render must not stall later sentences' renders.
    speechRenderChain = renderPromise.catch(() => null);
    // Play in order: after the previous clip finishes AND this clip is rendered.
    const task = Promise.all([speechQueue, renderPromise]).then(async ([, blob]) => {
      if (!blob || !speechEnabled || requestId !== speechRequestId) return;
      speakActiveStatus(requestId, activeMessage);
      // Lead-in: delay only the first clip of this reply so a buffer forms behind it.
      if (speechLeadInDoneFor !== requestId) {
        speechLeadInDoneFor = requestId;
        await new Promise((resolve) => setTimeout(resolve, SPEECH_LEAD_IN_MS));
        if (requestId !== speechRequestId) return;
      }
      await playBrowserAudio(blob, requestId);
    });
    speechQueue = task.catch(() => speechTaskFailed(requestId)).finally(() => speechTaskSettled(requestId, pending));
    return;
  }

  // Host mode: the server plays through afplay and /api/speak only returns once
  // playback finishes, so requests must stay strictly serial (no rendering ahead).
  const task = speechQueue.then(async () => {
    if (!speechEnabled || requestId !== speechRequestId) return;
    speakActiveStatus(requestId, activeMessage);
    const response = await requestSpeech();
    if (!response.ok) throw new Error('speech failed');
  });
  speechQueue = task.catch(() => speechTaskFailed(requestId)).finally(() => speechTaskSettled(requestId, pending));
}

// Chunking for streamed speech. Every chunk pays a fixed startup cost in the TTS
// engine (text encoding + first tokens) — measured at ~1.8 s — before ANY of its
// audio arrives. So a chunk whose spoken audio is shorter than the next chunk's
// startup drains the buffer and leaves an audible gap: "You're welcome!" is 15
// characters ≈ 0.8 s of speech, which cannot cover the following 1.8 s wait.
// At the measured ~19 characters/second of speech, ~90 characters (≈4.7 s) covers
// it comfortably, so short sentences are merged forward rather than spoken alone.
// The first chunk of a reply uses a smaller minimum so speech still starts
// promptly (~50 chars ≈ 2.6 s, still longer than the next chunk's startup).
const SPEECH_MIN_CHARS = 90;
const SPEECH_FIRST_MIN_CHARS = 50;
const SPEECH_MAX_CHARS = 220;

function speechBoundary(text, final, minChars = SPEECH_MIN_CHARS) {
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    let end = -1;
    if (character === '\n') end = index + 1;
    else if ('.!?'.includes(character) && (index === text.length - 1 || /\s/.test(text[index + 1]))) end = index + 1;
    // A sentence end that would produce too short a chunk is skipped, so the
    // short sentence is spoken together with the text that follows it.
    if (end >= 0 && end >= minChars) return end;
  }
  if (text.length >= SPEECH_MAX_CHARS) {
    const window = text.slice(0, SPEECH_MAX_CHARS);
    let boundary = Math.max(window.lastIndexOf(', '), window.lastIndexOf('; '), window.lastIndexOf(': '));
    if (boundary < minChars) boundary = window.lastIndexOf(' ');
    if (boundary >= minChars) return boundary + 1;
  }
  // The final chunk has nothing after it, so a short one costs no gap.
  return final ? text.length : -1;
}

function feedSpeech(stream, value, final = false) {
  if (!stream || stream.requestId !== speechRequestId) return;
  stream.buffer += value;
  while (stream.buffer) {
    const minChars = stream.spoken ? SPEECH_MIN_CHARS : SPEECH_FIRST_MIN_CHARS;
    const boundary = speechBoundary(stream.buffer, final, minChars);
    if (boundary < 0) break;
    const chunk = stream.buffer.slice(0, boundary).trim();
    stream.buffer = stream.buffer.slice(boundary).trimStart();
    if (!chunk) continue;
    queueSpeech(chunk, stream.requestId);
    stream.spoken = true;
  }
}

function setVoiceState(state, message) {
  voiceEl.classList.toggle('listening', state === 'listening');
  voiceEl.classList.toggle('transcribing', state === 'transcribing');
  voiceEl.setAttribute('aria-pressed', state === 'listening' ? 'true' : 'false');
  voiceEl.textContent = state === 'listening' ? 'Listening… release to transcribe' : state === 'transcribing' ? 'Transcribing…' : 'Hold to talk';
  voiceEl.disabled = conversationEnabled || state === 'transcribing' || (state === 'idle' && (!voiceReady || sendEl.disabled));
  voiceHintEl.textContent = message;
}

async function closeRecordingState(state) {
  clearTimeout(state.timer);
  state.processor.onaudioprocess = null;
  for (const node of [state.source, state.processor, state.silence]) {
    try { node.disconnect(); } catch { /* already disconnected */ }
  }
  state.stream.getTracks().forEach((track) => { try { track.stop(); } catch { /* already stopped */ } });
  try { await state.context.close(); } catch { /* already closed */ }
}

function discardRecording(message = '') {
  releaseRequested = false;
  const state = audioState;
  audioState = null;
  if (!state) return;
  void closeRecordingState(state).catch(() => {});
  if (message) setVoiceState('idle', message);
}

async function startRecording(event) {
  event.preventDefault();
  if (!voiceReady || conversationEnabled || audioState || voiceEl.classList.contains('transcribing')) return;
  if (speechActive || pendingSpeech.size > 0) await stopSpeech();
  releaseRequested = false;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true}, video: false});
    const context = new AudioContext();
    await context.resume();
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(4096, 1, 1);
    const silence = context.createGain();
    silence.gain.value = 0;
    const chunks = [];
    processor.onaudioprocess = (audioEvent) => chunks.push(new Float32Array(audioEvent.inputBuffer.getChannelData(0)));
    source.connect(processor);
    processor.connect(silence);
    silence.connect(context.destination);
    const timer = setTimeout(() => { releaseRequested = true; stopRecording(); }, 30000);
    audioState = {stream, context, source, processor, silence, chunks, timer};
    setVoiceState('listening', 'Listening locally. Release to stop; recording ends automatically after 30 seconds.');
    if (releaseRequested) stopRecording();
  } catch {
    releaseRequested = false;
    setVoiceState('idle', 'Microphone access was unavailable. Text chat still works.');
  }
}

async function stopRecording() {
  releaseRequested = true;
  if (!audioState) return;
  const state = audioState;
  audioState = null;
  const inputRate = state.context.sampleRate;
  await closeRecordingState(state);
  setVoiceState('transcribing', 'Transcribing locally. Audio is deleted immediately after this request.');
  try {
    const transcript = await transcribeChunks(state.chunks, inputRate);
    setVoiceState('idle', 'Speech recognized locally and submitted.');
    if (!(await submitMessage(transcript))) throw new Error('submission unavailable');
  } catch (error) {
    if (error.message === 'no_speech_detected') setVoiceState('idle', 'No speech detected. Nothing was submitted.');
    else if (error.message === 'transcription_timed_out') setVoiceState('idle', 'The long recording timed out during local transcription. Audio was discarded; text chat still works.');
    else if (error.message === 'transcription_failed') setVoiceState('idle', 'Local transcription failed twice. Audio was discarded; text chat still works.');
    else setVoiceState('idle', 'Local transcription was unavailable. Audio was discarded; text chat still works.');
  }
}

async function requestTranscript(wav, headers) {
  const response = await fetch('/api/transcribe', {method: 'POST', headers, body: wav});
  let result;
  try { result = await response.json(); }
  catch { throw new Error('transcription_unavailable'); }
  if (result.error === 'no_speech_detected') throw new Error('no_speech_detected');
  if (result.error === 'transcription_timed_out') throw new Error('transcription_timed_out');
  if (!response.ok || result.error === 'transcription_failed') throw new Error('transcription_failed');
  if (typeof result.transcript !== 'string') throw new Error('transcription_unavailable');
  return result.transcript;
}

async function transcribeChunks(chunks, inputRate, captureMode = 'push-to-talk') {
  const samples = mergeSamples(chunks);
  const resampled = resample(samples, inputRate, 16000);
  const conversationMode = captureMode === 'conversation';
  const energyOptions = conversationMode
    ? {minPeakToFloorRatio: 2.4, minActiveWindows: 6}
    : {minPeakToFloorRatio: 1.6, minActiveWindows: 4};
  if (resampled.length < 4800 || !hasSpeechEnergy(resampled, 16000, energyOptions)) throw new Error('no_speech_detected');
  const wav = encodeWav(resampled, 16000);
  const headers = {'Content-Type': 'audio/wav'};
  if (conversationMode) headers['X-JARVIS-Capture'] = 'conversation';
  for (let attempt = 0; attempt < 2; attempt++) {
    try { return await requestTranscript(wav, headers); }
    catch (error) {
      if (attempt === 0 && error.message === 'transcription_failed') {
        if (conversationMode) setConversationState('processing', 'Local transcription failed once; retrying the same in-memory audio.');
        else setVoiceState('transcribing', 'Local transcription failed once; retrying the same in-memory audio.');
        await new Promise((resolve) => setTimeout(resolve, 250));
        continue;
      }
      throw error;
    }
  }
  throw new Error('transcription_failed');
}

function mergeSamples(chunks) {
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const result = new Float32Array(total);
  let offset = 0;
  for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.length; }
  return result;
}

function resample(input, sourceRate, targetRate) {
  if (sourceRate === targetRate) return input;
  const output = new Float32Array(Math.floor(input.length * targetRate / sourceRate));
  const ratio = sourceRate / targetRate;
  for (let index = 0; index < output.length; index++) {
    const position = index * ratio;
    const left = Math.floor(position);
    const right = Math.min(left + 1, input.length - 1);
    const fraction = position - left;
    output[index] = input[left] * (1 - fraction) + input[right] * fraction;
  }
  return output;
}

function hasSpeechEnergy(samples, sampleRate, {minPeakToFloorRatio = 1.6, minActiveWindows = 4} = {}) {
  const windowSize = Math.round(sampleRate * 0.02);
  const windowLevels = [];
  for (let offset = 0; offset < samples.length; offset += windowSize) {
    const end = Math.min(offset + windowSize, samples.length);
    if (end - offset < windowSize / 2) continue;
    let sum = 0, sumSquares = 0;
    for (let index = offset; index < end; index++) {
      sum += samples[index];
      sumSquares += samples[index] * samples[index];
    }
    const count = end - offset;
    const mean = sum / count;
    const rms = Math.sqrt(Math.max(0, sumSquares / count - mean * mean));
    windowLevels.push(rms);
  }
  if (!windowLevels.length) return false;
  const ordered = [...windowLevels].sort((left, right) => left - right);
  const noiseFloor = ordered[Math.floor((ordered.length - 1) * 0.2)];
  const activityThreshold = Math.max(0.006, noiseFloor * minPeakToFloorRatio);
  return windowLevels.filter((level) => level >= activityThreshold).length >= minActiveWindows;
}

function chunkRms(samples) {
  let sum = 0, sumSquares = 0;
  for (const sample of samples) { sum += sample; sumSquares += sample * sample; }
  const mean = sum / samples.length;
  return Math.sqrt(Math.max(0, sumSquares / samples.length - mean * mean));
}

function setConversationState(state, message) {
  conversationEl.classList.toggle('active', state !== 'off');
  conversationEl.classList.toggle('hearing', state === 'hearing');
  conversationEl.setAttribute('aria-pressed', conversationEnabled ? 'true' : 'false');
  conversationEl.textContent = state === 'hearing' ? 'Hearing you…' : state === 'processing' ? 'JARVIS responding…' : conversationEnabled ? 'Hands-free on' : 'Conversation mode';
  conversationHintEl.textContent = message;
}

function stopConversationByVoiceCommand() {
  stopConversation('Conversation mode is off. Voice command recognized; the microphone is closed.');
  if (!speechEnabled || !speechReady) return;
  const requestId = ++speechRequestId;
  speechQueue = Promise.resolve();
  queueSpeech('Goodbye.', requestId, 'JARVIS is acknowledging the voice command.');
}

function closeConversationAudio() {
  const state = conversationAudio;
  conversationAudio = null;
  if (!state) return;
  state.processor.onaudioprocess = null;
  for (const node of [state.source, state.processor, state.silence]) {
    try { node.disconnect(); } catch { /* already disconnected */ }
  }
  state.stream.getTracks().forEach((track) => { try { track.stop(); } catch { /* already stopped */ } });
  void state.context.close().catch(() => {});
}

function resetConversationDetector(message = 'Listening locally. Speak naturally; say “Goodbye, JARVIS” to stop.') {
  if (!conversationEnabled || !conversationAudio) return;
  const state = conversationAudio;
  state.processing = false;
  state.speaking = false;
  state.chunks = [];
  state.preRoll = [];
  state.preRollSamples = 0;
  state.highWindows = 0;
  state.silenceMs = 0;
  state.utteranceMs = 0;
  state.calibrationLevels = [];
  state.calibratingUntil = performance.now() + 1000;
  setConversationState('active', message);
}

function processConversationAudio(state, audioEvent) {
  if (!conversationEnabled || state !== conversationAudio || state.processing) return;
  const chunk = new Float32Array(audioEvent.inputBuffer.getChannelData(0));
  const level = chunkRms(chunk);
  const durationMs = chunk.length / state.context.sampleRate * 1000;
  if (performance.now() < state.calibratingUntil) {
    state.calibrationLevels.push(level);
    return;
  }
  if (state.calibrationLevels.length) {
    const ordered = [...state.calibrationLevels].sort((left, right) => left - right);
    state.noiseFloor = ordered[Math.floor((ordered.length - 1) * 0.8)];
    state.calibrationLevels = [];
  }
  const startThreshold = Math.max(0.008, state.noiseFloor * 2.4);
  const stopThreshold = Math.max(0.005, state.noiseFloor * 1.5);
  if (!state.speaking) {
    state.preRoll.push(chunk);
    state.preRollSamples += chunk.length;
    while (state.preRollSamples > state.context.sampleRate * 0.35 && state.preRoll.length > 1) {
      state.preRollSamples -= state.preRoll.shift().length;
    }
    if (level >= startThreshold) state.highWindows++;
    else {
      state.highWindows = 0;
      state.noiseFloor = state.noiseFloor * 0.98 + level * 0.02;
    }
    if (state.highWindows >= 3) {
      state.speaking = true;
      state.chunks = state.preRoll;
      state.utteranceMs = state.preRollSamples / state.context.sampleRate * 1000;
      state.preRoll = [];
      state.preRollSamples = 0;
      state.silenceMs = 0;
      setConversationState('hearing', 'Hearing speech locally. Pause for about one second to submit.');
    }
    return;
  }
  state.chunks.push(chunk);
  state.utteranceMs += durationMs;
  state.silenceMs = level <= stopThreshold ? state.silenceMs + durationMs : 0;
  if ((state.utteranceMs >= 400 && state.silenceMs >= 900) || state.utteranceMs >= 30000) {
    state.processing = true;
    state.speaking = false;
    void finishConversationUtterance(state);
  }
}

async function startConversation() {
  if (!voiceReady || conversationStarting || conversationEnabled || audioState || sendEl.disabled) return;
  conversationStarting = true;
  conversationEl.disabled = true;
  if (speechActive || pendingSpeech.size > 0) await stopSpeech();
  let stream = null;
  let context = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true}, video: false});
    context = new AudioContext();
    await context.resume();
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(4096, 1, 1);
    const silence = context.createGain();
    silence.gain.value = 0;
    const state = {
      stream, context, source, processor, silence,
      noiseFloor: 0.002, calibrationLevels: [], calibratingUntil: performance.now() + 2000,
      processing: false, speaking: false, chunks: [], preRoll: [], preRollSamples: 0,
      highWindows: 0, silenceMs: 0, utteranceMs: 0,
    };
    processor.onaudioprocess = (audioEvent) => processConversationAudio(state, audioEvent);
    source.connect(processor);
    processor.connect(silence);
    silence.connect(context.destination);
    conversationAudio = state;
    conversationEnabled = true;
    conversationStarting = false;
    conversationEl.disabled = false;
    voiceEl.disabled = true;
    setConversationState('active', 'Calibrating to the local room noise, then listening continuously.');
    setTimeout(() => {
      if (conversationEnabled && conversationAudio === state && !state.processing && !state.speaking) {
        setConversationState('active', 'Listening locally. Speak naturally; say “Goodbye, JARVIS” to stop.');
      }
    }, 2000);
  } catch {
    if (!conversationAudio) {
      stream?.getTracks().forEach((track) => track.stop());
      if (context) void context.close();
    }
    conversationEnabled = false;
    conversationStarting = false;
    closeConversationAudio();
    conversationEl.disabled = !voiceReady;
    setConversationState('off', 'Conversation mode could not access the microphone. Push-to-talk and text still work.');
  }
}

function stopConversation(message = 'Conversation mode is off. The microphone is closed.') {
  conversationTurnId++;
  conversationEnabled = false;
  closeConversationAudio();
  conversationEl.disabled = !voiceReady || sendEl.disabled;
  voiceEl.disabled = !voiceReady || sendEl.disabled;
  setConversationState('off', message);
}

function pauseConversation(message) {
  if (!conversationEnabled || !conversationAudio) return;
  conversationAudio.processing = true;
  conversationAudio.speaking = false;
  conversationAudio.chunks = [];
  conversationAudio.preRoll = [];
  conversationAudio.preRollSamples = 0;
  setConversationState('processing', message);
}

async function runConversationTurn(text) {
  if (!conversationEnabled) return submitMessage(text);
  const turnId = ++conversationTurnId;
  pauseConversation('Microphone paused while JARVIS responds.');
  const submitted = await submitMessage(text);
  if (!submitted) {
    const healthy = await checkHealth();
    if (healthy && turnId === conversationTurnId) resetConversationDetector('Request failed safely; listening again.');
    return false;
  }
  await speechQueue;
  await new Promise((resolve) => setTimeout(resolve, 350));
  if (conversationEnabled && turnId === conversationTurnId) resetConversationDetector();
  return true;
}

async function finishConversationUtterance(state) {
  if (!conversationEnabled || state !== conversationAudio) return;
  const chunks = state.chunks;
  state.chunks = [];
  setConversationState('processing', 'Transcribing locally. Nothing has been submitted yet.');
  try {
    const transcript = await transcribeChunks(chunks, state.context.sampleRate, 'conversation');
    if (!conversationEnabled || state !== conversationAudio) return;
    if (isConversationStopCommand(transcript)) {
      stopConversationByVoiceCommand();
      return;
    }
    await runConversationTurn(transcript);
  } catch (error) {
    if (!conversationEnabled || state !== conversationAudio) return;
    if (error.message === 'no_speech_detected') resetConversationDetector('No speech detected. Nothing was submitted; listening again.');
    else if (error.message === 'transcription_timed_out') resetConversationDetector('The long recording timed out locally and was discarded; listening again.');
    else if (error.message === 'transcription_failed') resetConversationDetector('Local transcription failed twice and audio was discarded; listening again.');
    else resetConversationDetector('Transcription was unavailable and audio was discarded; listening again.');
  }
}

function encodeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset, value) => [...value].forEach((character, index) => view.setUint8(offset + index, character.charCodeAt(0)));
  text(0, 'RIFF'); view.setUint32(4, 36 + samples.length * 2, true); text(8, 'WAVE'); text(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true); text(36, 'data'); view.setUint32(40, samples.length * 2, true);
  for (let index = 0; index < samples.length; index++) {
    const sample = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(44 + index * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return buffer;
}

voiceEl.addEventListener('pointerdown', startRecording);
window.addEventListener('pointerup', stopRecording);
voiceEl.addEventListener('keydown', (event) => {
  if ((event.key === ' ' || event.key === 'Enter') && !event.repeat) startRecording(event);
});
voiceEl.addEventListener('keyup', (event) => {
  if (event.key === ' ' || event.key === 'Enter') stopRecording();
});
voiceEl.addEventListener('click', (event) => event.preventDefault());

async function submitMessage(value) {
  const text = value.trim();
  if (!text || sendEl.disabled) return false;
  if (autoMemoryTimer) {
    clearTimeout(autoMemoryTimer);
    autoMemoryTimer = null;
  }
  if (text.length > chatLimits.maxMessageChars) {
    addMessage('assistant', `That message exceeds the local ${chatLimits.maxMessageChars}-character context limit and was not submitted.`);
    return false;
  }
  if (speechActive || pendingSpeech.size > 0) await stopSpeech();
  if (isLearnModeStopCommand(text)) {
    const saved = learnSavedCount;
    const wasEnabled = learnModeEnabled;
    setLearnMode(false, wasEnabled
      ? `Learn mode is off. ${saved} ${saved === 1 ? 'answer was' : 'answers were'} saved and remain reviewable in Memory.`
      : 'Learn mode was already off.');
    return deliverLocalResponse(
      text,
      wasEnabled ? 'Learn mode is off. The answers already saved remain in Memory.' : 'Learn mode was already off.',
      'JARVIS is confirming the learning state.',
    );
  }
  if (isLearnModeStartCommand(text)) {
    const started = setLearnMode(true);
    return deliverLocalResponse(
      text,
      started
        ? 'Learn mode is on. Ask me to interview you, and each answer will be saved with my preceding question for review in Memory.'
        : 'Learn mode could not start because local memory is unavailable.',
      'JARVIS is confirming the learning state.',
    );
  }
  const interviewRequest = isLearnModeInterviewRequest(text);
  if (interviewRequest && !learnModeEnabled) {
    setLearnMode(true, 'Learn mode is on for this interview. Each answer will be saved with JARVIS’s preceding question and remain reviewable in Memory.');
  }
  const localResponse = unsupportedActionResponse(text);
  if (localResponse) {
    return deliverLocalResponse(text, localResponse, 'JARVIS is explaining a current capability limit.');
  }
  const autoMemoryQuestion = history.at(-1)?.role === 'assistant' ? history.at(-1).content : '';
  const autoMemoryEligible = !learnModeEnabled && !interviewRequest;
  if (learnModeEnabled && !interviewRequest && !isMemoryControlCommand(text)) await saveLearnAnswer(text);
  const previousHistory = history;
  addMessage('user', text);
  history = trimConversationHistory(
    [...history, {role: 'user', content: text}],
    {maxMessages: chatLimits.maxMessages, maxChars: chatLimits.maxChars},
  );
  const output = addMessage('assistant', '');
  sendEl.disabled = true;
  voiceEl.disabled = true;
  let succeeded = false;
  const speechStream = speechEnabled && speechReady ? {requestId: ++speechRequestId, buffer: ''} : null;
  if (speechStream) {
    speechQueue = Promise.resolve();
    speechHintEl.textContent = 'Waiting for the first complete phrase…';
  }
  try {
    const response = await fetch('/api/chat', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({messages: history})});
    if (!response.ok || !response.body) throw new Error('request failed');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '', answer = '', completed = false, unsupportedScriptChars = 0;
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const lines = buffer.split('\n'); buffer = lines.pop() || '';
      for (const line of lines) {
        if (line === 'data: [DONE]') { completed = true; continue; }
        if (!line.startsWith('data: ')) continue;
        let data;
        try { data = JSON.parse(line.slice(6)); }
        catch { continue; }
        const content = data.choices?.[0]?.delta?.content || '';
        unsupportedScriptChars += countUnsupportedScriptCharacters(content);
        if (unsupportedScriptChars >= 3) {
          await reader.cancel();
          throw new Error('unsupported language generation');
        }
        answer += content;
        output.textContent = answer;
        messagesEl.scrollTop = messagesEl.scrollHeight;
        feedSpeech(speechStream, content);
      }
    }
    if (!answer || !completed) throw new Error('incomplete response');
    feedSpeech(speechStream, '', true);
    history = trimConversationHistory(
      [...history, {role: 'assistant', content: answer}],
      {maxMessages: chatLimits.maxMessages, maxChars: chatLimits.maxChars},
    );
    succeeded = true;
    if (autoMemoryEligible) scheduleAutoMemory(autoMemoryQuestion, text);
  } catch (error) {
    history = previousHistory;
    output.textContent = error.message === 'unsupported language generation'
      ? 'JARVIS generated unsupported non-English text. The turn was discarded from context; you can retry safely.'
      : 'The local model could not complete that request. This turn was not retained in context; you can retry safely.';
    if (speechStream) void stopSpeech('Speech stopped because response generation failed.');
  }
  finally {
    sendEl.disabled = false;
    promptEl.focus();
    void checkHealth();
    if (!memoryBackdropEl.hidden) void loadMemories();
    if (autoMemoryQueue.length && !autoMemoryRunning && !autoMemoryTimer) autoMemoryTimer = setTimeout(() => { void flushAutoMemory(); }, 3000);
  }
  return succeeded;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const text = promptEl.value;
  if (!text.trim() || sendEl.disabled) return;
  promptEl.value = '';
  if (conversationEnabled) await runConversationTurn(text);
  else await submitMessage(text);
});

copyChatEl.addEventListener('click', async () => {
  const messages = Array.from(messagesEl.querySelectorAll('article')).map((item) => ({
    role: item.classList.contains('user') ? 'user' : 'assistant',
    content: item.textContent || '',
  }));
  const transcript = formatConversationTranscript(messages);
  if (!transcript) {
    chatHintEl.textContent = 'There is no user conversation to copy yet.';
    return;
  }
  try {
    if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
    await navigator.clipboard.writeText(transcript);
    chatHintEl.textContent = 'Visible conversation copied to the clipboard by your request.';
  } catch {
    chatHintEl.textContent = 'The browser could not copy this conversation. Nothing was sent elsewhere.';
  }
});
document.querySelector('#clear').addEventListener('click', () => {
  void flushAutoMemory();
  void stopSpeech();
  if (learnModeEnabled) {
    const saved = learnSavedCount;
    setLearnMode(false, `Learn mode stopped when chat was cleared. ${saved} ${saved === 1 ? 'answer remains' : 'answers remain'} saved in Memory.`);
  }
  history = []; messagesEl.replaceChildren(); addMessage('assistant', 'Conversation cleared from this page.');
  if (conversationEnabled) resetConversationDetector();
});
conversationEl.addEventListener('click', async () => {
  if (conversationEnabled) stopConversation();
  else await startConversation();
});
speechToggleEl.addEventListener('click', async () => {
  speechEnabled = !speechEnabled;
  speechToggleEl.textContent = speechEnabled ? 'Voice on' : 'Voice muted';
  speechToggleEl.setAttribute('aria-pressed', speechEnabled ? 'true' : 'false');
  if (!speechEnabled) await stopSpeech('JARVIS voice is muted.');
  else speechHintEl.textContent = speechIdleMessage();
});
stopSpeechEl.addEventListener('click', () => stopSpeech('Speech stopped. JARVIS voice remains on.'));
autoMemoryToggleEl.addEventListener('click', () => {
  if (!autoMemoryAvailable) return;
  setAutoMemory(!autoMemoryEnabled);
});
memoryNoticeUndoEl.addEventListener('click', async () => {
  const memoryId = lastAutoMemoryId;
  if (!memoryId) return;
  memoryNoticeUndoEl.disabled = true;
  try {
    const response = await fetch(`/api/memories/${encodeURIComponent(memoryId)}`, {method: 'DELETE'});
    if (!response.ok) throw new Error('undo failed');
    lastAutoMemoryId = null;
    memoryNoticeEl.hidden = true;
    autoMemoryHintEl.textContent = 'The last automatically saved memory was undone.';
    if (!memoryBackdropEl.hidden) await loadMemories();
  } catch {
    memoryNoticeTextEl.textContent = 'Undo was unavailable. Review the item in Memory.';
  } finally {
    memoryNoticeUndoEl.disabled = false;
  }
});
learnToggleEl.addEventListener('click', () => {
  if (learnModeEnabled) {
    const saved = learnSavedCount;
    setLearnMode(false, `Learn mode is off. ${saved} ${saved === 1 ? 'answer was' : 'answers were'} saved and remain reviewable in Memory.`);
  } else {
    setLearnMode(true);
  }
});
speechSettingsToggleEl.addEventListener('click', openSpeechSettings);
speechSettingsCloseEl.addEventListener('click', closeSpeechSettings);
speechSettingsBackdropEl.addEventListener('click', (event) => {
  if (event.target === speechSettingsBackdropEl) closeSpeechSettings();
});
speechDefaultsEl.addEventListener('click', () => {
  if (!speechOptions) return;
  speechVoiceEl.value = speechOptions.defaultVoice;
  speechRateEl.value = String(speechOptions.defaultRate);
  resetFishDefaults();
  updateFishTuningVisibility();
  speechSettingsStatusEl.textContent = 'Default settings selected. Save to apply them.';
});
speechVoiceEl.addEventListener('change', updateFishTuningVisibility);
if (speechStreamEl) {
  speechStreamEl.checked = streamingEnabled;
  speechStreamEl.addEventListener('change', () => {
    streamingEnabled = speechStreamEl.checked;
    storeSpeechSetting('jarvis.speech.stream', streamingEnabled ? '1' : '0');
  });
}
for (const name of Object.keys(fishControls)) {
  const control = fishControls[name];
  if (control.input) control.input.addEventListener('input', () => onFishParamInput(name));
}
speechPreviewEl.addEventListener('click', previewSpeechSettings);
speechSettingsFormEl.addEventListener('submit', (event) => {
  event.preventDefault();
  const selected = selectedSpeechSettings();
  if (!selected) {
    speechSettingsStatusEl.textContent = 'Choose an installed voice and a valid speaking rate.';
    return;
  }
  speechVoice = selected.voice;
  speechRate = selected.rate;
  speechOverridden = speechVoice !== speechOptions.defaultVoice || speechRate !== speechOptions.defaultRate;
  if (speechOverridden) {
    storeSpeechSetting('jarvis.speech.voice', speechVoice);
    storeSpeechSetting('jarvis.speech.voiceDefault', speechOptions.defaultVoice);
    storeSpeechSetting('jarvis.speech.rate', speechRate);
    storeSpeechSetting('jarvis.speech.rateDefault', speechOptions.defaultRate);
    speechSettingsStatusEl.textContent = 'Speech settings saved in this browser. They override the configured voice until it changes.';
  } else {
    clearStoredSpeechOverride();
    speechSettingsStatusEl.textContent = 'Configured defaults restored. This browser no longer overrides them.';
  }
  speechHintEl.textContent = speechEnabled ? speechIdleMessage() : 'JARVIS voice is muted.';
  closeSpeechSettings();
});
memoryToggleEl.addEventListener('click', openMemoryPanel);
memoryCloseEl.addEventListener('click', closeMemoryPanel);
memoryCancelEl.addEventListener('click', () => { resetMemoryForm(); memoryTextEl.focus(); });
memoryBackdropEl.addEventListener('click', (event) => {
  if (event.target === memoryBackdropEl) closeMemoryPanel();
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !memoryBackdropEl.hidden) closeMemoryPanel();
  if (event.key === 'Escape' && !speechSettingsBackdropEl.hidden) closeSpeechSettings();
});
memoryFormEl.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!memoryReady || memorySaveEl.disabled) return;
  const id = memoryIdEl.value;
  const text = memoryTextEl.value.trim();
  if (!text) return;
  memorySaveEl.disabled = true;
  memoryStatusEl.textContent = id ? 'Updating local memory…' : 'Saving local memory…';
  try {
    const response = await fetch(id ? `/api/memories/${encodeURIComponent(id)}` : '/api/memories', {
      method: id ? 'PATCH' : 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({category: memoryCategoryEl.value, text}),
    });
    let payload = {};
    try { payload = await response.json(); } catch { /* status text below is sufficient */ }
    if (!response.ok) {
      memoryStatusEl.textContent = payload.error === 'memory_duplicate'
        ? 'That exact memory is already saved.'
        : 'Memory was rejected. Check its size and remove any credentials or sensitive secrets.';
      return;
    }
    resetMemoryForm();
    await loadMemories(id ? 'Memory updated.' : 'Memory saved.');
  } catch {
    memoryStatusEl.textContent = 'Memory is unavailable. Nothing was saved.';
  } finally {
    memorySaveEl.disabled = false;
  }
});
window.addEventListener('pagehide', () => {
  void flushAutoMemory({keepalive: true});
  closeConversationAudio();
  discardRecording();
  void fetch('/api/speak/stop', {method: 'POST', keepalive: true}).catch(() => {});
});
// --- Mobile: transient status toast + collapsible memory menu -----------------
//
// The status hints are permanent aria-live paragraphs under the composer. On a
// phone that is space the conversation needs, so they are visually hidden there
// and their CHANGES are surfaced briefly in a floating toast instead. Watching
// the existing elements (rather than rerouting every call site) keeps a single
// source of truth and cannot miss a status update.
const toastEl = document.querySelector('#toast');
const memoryMenuToggleEl = document.querySelector('#memory-menu-toggle');
const memoryGroupEl = document.querySelector('#memory-group');
let toastTimer = null;

function showToast(message) {
  if (!toastEl || !message) return;
  toastEl.textContent = message;
  toastEl.hidden = false;
  // Force a frame so the transition runs when re-showing an already-visible toast.
  void toastEl.offsetWidth;
  toastEl.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.classList.remove('visible');
    setTimeout(() => { if (!toastEl.classList.contains('visible')) toastEl.hidden = true; }, 260);
  }, 4200);
}

function watchStatusHints() {
  if (!toastEl || typeof MutationObserver !== 'function') return;
  const hints = ['#voice-hint', '#conversation-hint', '#speech-hint', '#auto-memory-hint', '#learn-hint']
    .map((selector) => document.querySelector(selector))
    .filter(Boolean);
  // Seed with the initial text so the first render does not fire a toast.
  const seen = new Map(hints.map((el) => [el, el.textContent.trim()]));
  const observer = new MutationObserver((records) => {
    // Only toast on small screens, where the hints are hidden.
    if (!window.matchMedia('(max-width:700px)').matches) return;
    for (const record of records) {
      const el = record.target.nodeType === 1 ? record.target : record.target.parentElement;
      if (!el || !seen.has(el)) continue;
      const text = el.textContent.trim();
      if (text && text !== seen.get(el)) {
        seen.set(el, text);
        showToast(text);
      }
    }
  });
  for (const el of hints) observer.observe(el, {childList: true, characterData: true, subtree: true});
}

function closeMemoryMenu() {
  if (!memoryGroupEl || !memoryMenuToggleEl) return;
  memoryGroupEl.classList.remove('open');
  memoryMenuToggleEl.setAttribute('aria-expanded', 'false');
}

function setupMemoryMenu() {
  if (!memoryGroupEl || !memoryMenuToggleEl) return;
  const mobile = window.matchMedia('(max-width:700px)');
  const sync = () => {
    memoryMenuToggleEl.hidden = !mobile.matches;
    if (!mobile.matches) closeMemoryMenu();
  };
  sync();
  mobile.addEventListener('change', sync);
  memoryMenuToggleEl.addEventListener('click', (event) => {
    event.stopPropagation();
    const open = memoryGroupEl.classList.toggle('open');
    memoryMenuToggleEl.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  // Choosing an item, tapping elsewhere, or Escape all dismiss the menu.
  memoryGroupEl.addEventListener('click', (event) => {
    if (event.target.closest('button')) closeMemoryMenu();
  });
  document.addEventListener('click', (event) => {
    if (!memoryGroupEl.contains(event.target) && event.target !== memoryMenuToggleEl) closeMemoryMenu();
  });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeMemoryMenu(); });
}

// Unlock audio playback on the first real user interaction (typing counts), so the
// first spoken reply isn't silently blocked by the browser's autoplay policy.
document.addEventListener('pointerdown', unlockAudio, {once: true});
document.addEventListener('keydown', unlockAudio, {once: true});
// The boot overlay is the unlocking gesture: dismissing it is what permits the
// spoken greeting. It is decorative, so it is removed outright when motion is
// reduced or if scripting somehow fails to reach this point.
(() => {
  const boot = document.querySelector('#boot');
  const start = document.querySelector('#boot-start');
  if (!boot || !start) return;
  // Reduced motion suppresses the ANIMATION, not the control: the button is how
  // audio gets unlocked, so removing it would leave no way to start the greeting.
  // With motion reduced the overlay simply appears complete and ready at once.
  const reduced = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  if (reduced) boot.classList.add('static');
  const activate = () => {
    unlockAudio();
    boot.classList.add('dismissed');
    setTimeout(() => boot.remove(), reduced ? 0 : 700);
    promptEl.focus();
  };
  start.addEventListener('click', activate, {once: true});
  // Focus the control once it is visible: Enter and Space then activate it, so the
  // overlay is never a keyboard trap and needs no document-wide handler.
  setTimeout(() => { try { start.focus(); } catch { /* focus is best-effort */ } }, reduced ? 0 : 2600);
})();
setupMemoryMenu();
watchStatusHints();
// Mirror the speaking state onto <body> so the arc reactor can pulse while JARVIS
// talks. Polled rather than hooked into each assignment of speechActive, so no
// call site can be missed and the speech logic stays untouched.
setInterval(() => document.body.classList.toggle('jarvis-speaking', speechActive), 200);
checkHealth();
setInterval(checkHealth, 5000);
