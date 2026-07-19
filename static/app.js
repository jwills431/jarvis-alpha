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
let speechQueue = Promise.resolve();
const pendingSpeech = new Set();
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
let speechVoice = 'Daniel';
let speechRate = 190;

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
  return `JARVIS streams every reply using the local ${speechVoice} voice at ${speechRate} WPM.`;
}

function speechPayload(text, voice = speechVoice, rate = speechRate) {
  return {text, voice, rate};
}

function storedSpeechSetting(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function storeSpeechSetting(key, value) {
  try { localStorage.setItem(key, String(value)); } catch { /* browser persistence is optional */ }
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
    const voices = payload.voices.filter((item) => item && typeof item.name === 'string' && typeof item.locale === 'string');
    if (!voices.length) throw new Error('speech options unavailable');
    const minimumRate = Number.isInteger(payload.minimum_rate) ? payload.minimum_rate : 120;
    const maximumRate = Number.isInteger(payload.maximum_rate) ? payload.maximum_rate : 350;
    const defaultRate = Number.isInteger(payload.default_rate) ? payload.default_rate : 190;
    const defaultVoice = voices.some((item) => item.name === payload.default_voice) ? payload.default_voice : voices[0].name;
    speechOptions = {voices, minimumRate, maximumRate, defaultRate, defaultVoice};
    const savedVoice = storedSpeechSetting('jarvis.speech.voice');
    const savedRate = Number.parseInt(storedSpeechSetting('jarvis.speech.rate') || '', 10);
    speechVoice = voices.some((item) => item.name === savedVoice) ? savedVoice : defaultVoice;
    speechRate = Number.isInteger(savedRate) && savedRate >= minimumRate && savedRate <= maximumRate ? savedRate : defaultRate;
    speechVoiceEl.replaceChildren();
    for (const item of voices) {
      const option = document.createElement('option');
      option.value = item.name;
      option.textContent = `${item.name} (${item.locale.replace('_', '-')})`;
      speechVoiceEl.appendChild(option);
    }
    speechVoiceEl.value = speechVoice;
    speechRateEl.min = String(minimumRate);
    speechRateEl.max = String(maximumRate);
    speechRateEl.value = String(speechRate);
    speechOptionsReady = true;
    speechSettingsStatusEl.textContent = `${voices.length} installed English voices are available.`;
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
  speechSettingsBackdropEl.hidden = false;
  speechSettingsCloseEl.focus();
}

function closeSpeechSettings() {
  speechSettingsBackdropEl.hidden = true;
  speechSettingsToggleEl.focus();
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
  speechActive = true;
  stopSpeechEl.disabled = false;
  speechSettingsStatusEl.textContent = 'Playing a local preview…';
  try {
    const response = await fetch('/api/speak', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(speechPayload('At your service. Local speech settings are ready.', selected.voice, selected.rate)),
    });
    if (!response.ok) throw new Error('preview failed');
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
    speechActive = Boolean(state.speaking) || pendingSpeech.size > 0;
    stopSpeechEl.disabled = !speechActive;
    if (!speechReady) speechHintEl.textContent = 'Local speech is unavailable. Text and speech input still work.';
    else if (!speechEnabled) speechHintEl.textContent = 'JARVIS voice is muted.';
    else if (speechActive) speechHintEl.textContent = 'JARVIS is speaking locally.';
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
  stopSpeechEl.disabled = true;
  try { await fetch('/api/speak/stop', {method: 'POST'}); } catch { /* health polling will report availability */ }
  if (message) speechHintEl.textContent = message;
}

function queueSpeech(text, requestId, activeMessage = 'JARVIS is speaking while the reply is generated.') {
  const spokenText = text.replace(/[`*_#>]/g, ' ').replace(/\s+/g, ' ').trim();
  if (!spokenText || requestId !== speechRequestId) return;
  const pending = {};
  pendingSpeech.add(pending);
  const task = speechQueue.then(async () => {
    if (!speechEnabled || !speechReady || requestId !== speechRequestId) return;
    speechActive = true;
    stopSpeechEl.disabled = false;
    speechHintEl.textContent = activeMessage;
    const response = await fetch('/api/speak', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(speechPayload(spokenText)),
    });
    if (!response.ok) throw new Error('speech failed');
  });
  speechQueue = task.catch(() => {
    if (requestId === speechRequestId) speechHintEl.textContent = 'Speech was unavailable. The written reply will continue.';
  }).finally(() => {
    pendingSpeech.delete(pending);
    if (pendingSpeech.size === 0 && requestId === speechRequestId) {
      speechActive = false;
      stopSpeechEl.disabled = true;
      speechHintEl.textContent = speechIdleMessage();
    }
  });
}

function speechBoundary(text, final) {
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    if (character === '\n') return index + 1;
    if ('.!?'.includes(character) && (index === text.length - 1 || /\s/.test(text[index + 1]))) return index + 1;
  }
  if (text.length >= 220) {
    const window = text.slice(0, 220);
    let boundary = Math.max(window.lastIndexOf(', '), window.lastIndexOf('; '), window.lastIndexOf(': '));
    if (boundary < 80) boundary = window.lastIndexOf(' ');
    if (boundary >= 80) return boundary + 1;
  }
  return final ? text.length : -1;
}

function feedSpeech(stream, value, final = false) {
  if (!stream || stream.requestId !== speechRequestId) return;
  stream.buffer += value;
  while (stream.buffer) {
    const boundary = speechBoundary(stream.buffer, final);
    if (boundary < 0) break;
    const chunk = stream.buffer.slice(0, boundary).trim();
    stream.buffer = stream.buffer.slice(boundary).trimStart();
    queueSpeech(chunk, stream.requestId);
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
  speechSettingsStatusEl.textContent = 'Default settings selected. Save to apply them.';
});
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
  storeSpeechSetting('jarvis.speech.voice', speechVoice);
  storeSpeechSetting('jarvis.speech.rate', speechRate);
  speechSettingsStatusEl.textContent = 'Speech settings saved in this browser.';
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
checkHealth();
setInterval(checkHealth, 5000);
