(function initializeJarvisCore(root) {
  const conversationStopCommands = [
    'goodbye jarvis',
    'good bye jarvis',
    'stop listening',
    'end conversation',
  ];

  function normalizeConversationCommand(value) {
    return value.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
  }

  // Beyond the fixed phrases above, people ask for conversation mode to end in
  // whatever words come to mind, and the recognizer's wording varies too. These
  // match on intent — a stopping verb near the thing being stopped — rather than
  // on an exact sentence.
  const CONVERSATION_STOP_VERBS =
    '(?:turn(?: it)? off|switch(?: it)? off|shut(?: it)?(?: off| down)|disable|exit|leave|quit|end|stop|cancel|close)';
  const CONVERSATION_STOP_TARGETS =
    '(?:conversation(?: mode)?|listening|voice mode|the mic|the microphone|mic|microphone)';
  const conversationStopPatterns = [
    new RegExp(`\\b${CONVERSATION_STOP_VERBS}\\b(?:\\s+\\w+){0,3}\\s+\\b${CONVERSATION_STOP_TARGETS}\\b`),
    /\b(?:go|going|switch|back)\s+(?:back\s+)?(?:to\s+)?(?:silent|quiet|text only|text)\b/,
    /\bstop\s+(?:listening|talking)\b/,
  ];

  // "How do I turn off conversation mode?" is a question about the feature, not a
  // request to use it. Only the loose intent patterns are guarded this way; the
  // fixed phrases keep their existing literal behaviour.
  function looksLikeQuestionAboutConversation(normalized) {
    return /^(?:how|what|why|when|where|which|who|can you tell me|tell me|explain|does|do you|is there|are there)\b/
      .test(normalized);
  }

  function isConversationStopCommand(value) {
    if (typeof value !== 'string') return false;
    const normalized = normalizeConversationCommand(value);
    if (conversationStopCommands.some((command) => ` ${normalized} `.includes(` ${command} `))) return true;
    if (looksLikeQuestionAboutConversation(normalized)) return false;
    return conversationStopPatterns.some((pattern) => pattern.test(normalized));
  }

  function unsupportedActionResponse(value) {
    if (typeof value !== 'string') return null;
    const requestsUnavailableTool = [
      /\b(?:set|create|schedule)\s+(?:me\s+)?(?:a\s+)?reminder\b/i,
      /\bremind\s+me\s+(?:in|at|on|after|to)\b/i,
      /\b(?:set|start|create)\s+(?:a\s+|an\s+)?(?:timer|alarm)\b/i,
    ].some((pattern) => pattern.test(value));
    if (!requestsUnavailableTool) return null;
    return 'Reminder, timer, and alarm tools are not available in this alpha, so I cannot schedule or deliver an alert yet. I will not pretend one was set.';
  }

  function isLearnModeStartCommand(value) {
    if (typeof value !== 'string') return false;
    const normalized = normalizeConversationCommand(value);
    return [
      'start learn mode',
      'start learning mode',
      'start memory capture',
      'begin learn mode',
      'begin memory capture',
    ].includes(normalized);
  }

  function isLearnModeInterviewRequest(value) {
    if (typeof value !== 'string') return false;
    const normalized = normalizeConversationCommand(value);
    return (
      /\b(?:ask|have) me\b.*\bquestions?\b.*\b(?:get to know|learn about) me\b/.test(normalized)
      || /\b(?:get to know|learn about) me\b.*\b(?:ask|asking)\b.*\bquestions?\b/.test(normalized)
    );
  }

  function isLearnModeStopCommand(value) {
    if (typeof value !== 'string') return false;
    const normalized = normalizeConversationCommand(value);
    return [
      'stop learn mode',
      'stop learning mode',
      'stop memory capture',
      'end learn mode',
      'end memory capture',
    ].includes(normalized);
  }

  function isMemoryControlCommand(value) {
    if (typeof value !== 'string') return false;
    return /^(?:remember(?:\s+that|\s+this\s+as)?|save\s+to\s+memory|forget(?:\s+that|\s+memory)?|delete\s+memory|what\s+do\s+you\s+remember|show(?:\s+me)?\s+(?:your\s+)?memories|list(?:\s+my|\s+the)?\s+memories)\b/i.test(value.trim());
  }

  function formatLearnMemory(question, answer, maxChars = 1000) {
    if (typeof answer !== 'string' || !Number.isInteger(maxChars) || maxChars < 1) return null;
    const cleanAnswer = answer.replace(/\s+/g, ' ').trim();
    if (!cleanAnswer) return null;
    const cleanQuestion = typeof question === 'string' ? question.replace(/\s+/g, ' ').trim() : '';
    if (cleanQuestion) {
      const questionParts = cleanQuestion.match(/[^.!?]{1,320}[?]/g);
      const focusedQuestion = (questionParts?.at(-1) || cleanQuestion).slice(0, 320).trim();
      const contextual = `JARVIS asked: ${focusedQuestion}\nUser answered: ${cleanAnswer}`;
      if (contextual.length <= maxChars) return contextual;
    }
    const standalone = `User said during Learn mode: ${cleanAnswer}`;
    return standalone.length <= maxChars ? standalone : null;
  }

  function shouldConsiderAutoMemory(value, precedingQuestion = '') {
    if (typeof value !== 'string') return false;
    const text = value.replace(/\s+/g, ' ').trim();
    const durableQuestion = typeof precedingQuestion === 'string' && /\b(?:what|which|how|where|when|do|are|is)\b.{0,100}\b(?:you|your|yours|preference|project|story|book|character|species|device|system|workflow|plan)\b/i.test(precedingQuestion);
    if (/\?\s*$/.test(text) || text.length < (durableQuestion ? 2 : 8) || text.length > 1000 || isMemoryControlCommand(text)) return false;
    if (isLearnModeStartCommand(text) || isLearnModeStopCommand(text) || isLearnModeInterviewRequest(text)) return false;
    const durablePattern = [
      /\b(?:i am|i'm|i prefer|i like|i love|i dislike|i hate|i want|i need|i use|i work|i have|my\s+[a-z][a-z '\-]{0,50}\s+is)\b/i,
      /\b(?:we decided|i decided|we agreed|our\s+[a-z][a-z '\-]{0,50}\s+is|let's use|we will use)\b/i,
      /\b(?:actually|correction|to correct that|the correct\s+[a-z][a-z '\-]{0,30}\s+is)\b/i,
      /\b(?:this|the)\s+(?:project|story|book|character|species|device|system|workflow|plan)\b.{0,80}\b(?:is|uses|will|has)\b/i,
    ].some((pattern) => pattern.test(text));
    const looksLikeRequest = /^(?:please\b|can\b|could\b|would\b|will you\b|what\b|why\b|how\b|when\b|where\b|who\b|tell me\b|show me\b|give me\b|write\b|create\b|explain\b|summari[sz]e\b|analy[sz]e\b|help\b)/i.test(text);
    return durableQuestion || durablePattern || (text.length >= 24 && !looksLikeRequest);
  }

  // Built-in alert sound identifiers (the audio itself is synthesized in app.js).
  const ALERT_SOUND_IDS = ['chime', 'bell', 'beep', 'arpeggio', 'alarm'];

  function resolveAlertSound(stored, fallback) {
    // A saved choice wins only while it still names a known sound; otherwise the
    // per-type fallback, then the first sound. Keeps a stale localStorage value
    // from selecting a sound that no longer exists.
    if (ALERT_SOUND_IDS.includes(stored)) return stored;
    if (ALERT_SOUND_IDS.includes(fallback)) return fallback;
    return ALERT_SOUND_IDS[0];
  }

  function formatMessageTimestamp(value) {
    // e.g. "10:30 PM · 8/5/2026". Manual formatting (not toLocaleString) so it
    // is deterministic and unit-testable regardless of the host locale.
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    let hour = date.getHours();
    const minute = String(date.getMinutes()).padStart(2, '0');
    const meridiem = hour >= 12 ? 'PM' : 'AM';
    hour = hour % 12 || 12;
    const stamp = `${date.getMonth() + 1}/${date.getDate()}/${date.getFullYear()}`;
    return `${hour}:${minute} ${meridiem} · ${stamp}`;
  }

  function formatTimerAlert(fired) {
    // Spoken/displayed text for a fired timer or reminder. Avoids "timer timer"
    // when the user's own label already contains the word "timer" or "alarm".
    if (!fired || typeof fired !== 'object') return 'Your timer is up.';
    const label = typeof fired.label === 'string' ? fired.label.trim() : '';
    if (fired.kind === 'reminder') {
      return label ? `Reminder: ${label}` : 'This is your reminder.';
    }
    if (!label) return 'Your timer is up.';
    return /\b(?:timer|alarm)\b/i.test(label) ? `Your ${label} is up.` : `Your ${label} timer is up.`;
  }

  function parseStreamLine(line) {
    // Classify one SSE line from /api/chat (or a tool resume). Content keeps the
    // OpenAI delta shape so streaming + TTS are unchanged; tool activity arrives
    // under a top-level `jarvis` envelope. Returns null for a non-data line and
    // {type:'ignore'} for a data line carrying nothing we act on.
    if (typeof line !== 'string') return null;
    if (line === 'data: [DONE]') return {type: 'done'};
    if (!line.startsWith('data: ')) return null;
    let data;
    try { data = JSON.parse(line.slice(6)); } catch { return null; }
    if (data && typeof data.jarvis === 'object' && data.jarvis) {
      const event = data.jarvis;
      if (event.kind === 'tool_result') return {type: 'tool_result', event};
      if (event.kind === 'tool_proposal') return {type: 'tool_proposal', event};
      return {type: 'ignore'};
    }
    const content = data && data.choices && data.choices[0] && data.choices[0].delta
      ? data.choices[0].delta.content : undefined;
    if (typeof content === 'string') return {type: 'content', content};
    return {type: 'ignore'};
  }

  function countUnsupportedScriptCharacters(value) {
    if (typeof value !== 'string') return 0;
    return (value.match(/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}\p{Script=Cyrillic}\p{Script=Arabic}]/gu) || []).length;
  }

  function trimConversationHistory(messages, {maxMessages = 20, maxChars = 12000} = {}) {
    if (!Array.isArray(messages) || maxMessages < 1 || maxChars < 1 || messages.length === 0) return [];
    const bounded = [];
    let totalChars = 0;
    let expectedRole = messages[messages.length - 1]?.role;
    if (expectedRole !== 'user' && expectedRole !== 'assistant') return [];
    for (let index = messages.length - 1; index >= 0; index--) {
      const message = messages[index];
      if (!message || message.role !== expectedRole || typeof message.content !== 'string') break;
      if (bounded.length >= maxMessages || totalChars + message.content.length > maxChars) break;
      bounded.unshift({role: message.role, content: message.content});
      totalChars += message.content.length;
      expectedRole = expectedRole === 'user' ? 'assistant' : 'user';
    }
    if (bounded[0]?.role === 'assistant') bounded.shift();
    return bounded;
  }

  function formatConversationTranscript(messages) {
    if (!Array.isArray(messages)) return '';
    const clean = messages.filter((message) => (
      message && (message.role === 'user' || message.role === 'assistant')
      && typeof message.content === 'string' && message.content.trim()
    )).map((message) => ({role: message.role, content: message.content.trim()}));
    const firstUser = clean.findIndex((message) => message.role === 'user');
    if (firstUser < 0) return '';
    return clean.slice(firstUser).map((message) => (
      `${message.role === 'user' ? 'You' : 'JARVIS'}:\n${message.content}`
    )).join('\n\n');
  }

  function resolveSpeechSelection(options, stored) {
    // A saved browser override applies only while it still names an installed
    // voice and the configured default it was saved against is unchanged. When
    // the owner edits the configured voice or rate, the override is reported as
    // stale so configuration changes take effect on the next reload instead of
    // being permanently shadowed by browser storage.
    if (!options || !Array.isArray(options.voices) || !options.voices.length) {
      return {voice: null, rate: null, defaultVoice: null, defaultRate: null, overridden: false, stale: []};
    }
    const names = new Set(options.voices.map((item) => (item && typeof item.name === 'string' ? item.name : null)));
    const defaultVoice = names.has(options.defaultVoice) ? options.defaultVoice : options.voices[0].name;
    const minimumRate = Number.isInteger(options.minimumRate) ? options.minimumRate : 120;
    const maximumRate = Number.isInteger(options.maximumRate) ? options.maximumRate : 350;
    const configuredRate = Number.isInteger(options.defaultRate) ? options.defaultRate : minimumRate;
    const defaultRate = Math.min(Math.max(configuredRate, minimumRate), maximumRate);
    const saved = stored || {};
    const stale = [];

    let voice = defaultVoice;
    let voiceOverridden = false;
    if (typeof saved.voice === 'string' && saved.voice) {
      if (names.has(saved.voice) && saved.voiceDefault === defaultVoice) {
        voice = saved.voice;
        voiceOverridden = saved.voice !== defaultVoice;
      } else {
        stale.push('voice');
      }
    }

    let rate = defaultRate;
    let rateOverridden = false;
    if (saved.rate !== null && saved.rate !== undefined && saved.rate !== '') {
      const savedRate = Number.parseInt(saved.rate, 10);
      const savedAgainst = Number.parseInt(saved.rateDefault, 10);
      if (Number.isInteger(savedRate) && savedRate >= minimumRate && savedRate <= maximumRate && savedAgainst === defaultRate) {
        rate = savedRate;
        rateOverridden = savedRate !== defaultRate;
      } else {
        stale.push('rate');
      }
    }

    const selected = options.voices.find((item) => item && item.name === voice);
    return {
      voice,
      rate,
      engine: selected && selected.engine === 'piper' ? 'piper' : 'say',
      defaultVoice,
      defaultRate,
      minimumRate,
      maximumRate,
      overridden: voiceOverridden || rateOverridden,
      stale,
    };
  }

  // A timer alert must not cut off a reply that is already being spoken, but the
  // server hands each fired timer over exactly once — so an alert dropped here is
  // gone for good. These two decide when a queued alert may be released; app.js
  // owns the sound and the announcement, and plays them together.
  //
  // The ceiling is a safety net for a stuck speaking state, not a normal path. It
  // was 20 s, and on-device (2026-09-10) an ordinary long reply outlasted that: the
  // sound played mid-reply while the words queued behind audio already scheduled.
  // Now an ordinary reply always finishes first; if the ceiling does trip, app.js
  // stops the speech before announcing, so the two are never split.
  const ALERT_MAX_DEFER_MS = 120000;

  function mergeFiredAlerts(queued, incoming, now) {
    const merged = Array.isArray(queued) ? queued.slice() : [];
    if (!Array.isArray(incoming)) return merged;
    const seen = new Set();
    for (const entry of merged) {
      const id = entry && entry.fired && entry.fired.id;
      if (id) seen.add(id);
    }
    for (const fired of incoming) {
      const id = fired && fired.id;
      if (id && seen.has(id)) continue;
      if (id) seen.add(id);
      merged.push({fired, queuedAt: now});
    }
    return merged;
  }

  function shouldReleaseAlerts(queued, speaking, now, maxDeferMs) {
    if (!Array.isArray(queued) || queued.length === 0) return false;
    if (!speaking) return true;
    // Speaking, so hold — but never past the deferral ceiling, or a long reply
    // (or a stuck speaking flag) would swallow the alert entirely.
    const limit = typeof maxDeferMs === 'number' ? maxDeferMs : ALERT_MAX_DEFER_MS;
    let oldest = Infinity;
    for (const entry of queued) {
      const queuedAt = entry && entry.queuedAt;
      if (typeof queuedAt === 'number' && queuedAt < oldest) oldest = queuedAt;
    }
    if (oldest === Infinity) return true;
    return now - oldest >= limit;
  }

  // Chunking for streamed speech. Fish does not stream within a single request:
  // measured on this box, an 880-character request delivers nothing for 14.9 s and
  // then all 43 s of audio in one go. Splitting a reply across several requests is
  // therefore the only way to speak before the whole thing has been synthesised.
  //
  // Two measured figures set the sizes. Time to first audio is about
  // 0.3 s + 0.0165 s per character; the audio itself runs about 0.049 s per
  // character. So any chunk over ~10 characters yields more audio than it costs to
  // render, and once playback starts the buffer only grows. What governs the
  // perceived delay is therefore the FIRST chunk, and nothing else.
  //
  // The ramp starts small so the first word arrives at ~0.8 s instead of ~2.3 s,
  // then grows, each step sized to finish rendering before the previous chunk stops
  // playing. Going straight to the steady-state size after a small first chunk
  // would reintroduce a gap: a 220-character third chunk lands about 0.8 s late.
  const SPEECH_CHUNK_RAMP = [30, 60, 120];
  const SPEECH_MIN_CHARS = 90;
  const SPEECH_MAX_CHARS = 220;

  // The first chunk also has a ceiling of its own. The ramp's 30 characters is only
  // a minimum — the chunk still runs to the first sentence end past it, and the
  // model's opening sentence is often 110-150 characters. Worse, that chunk renders
  // while llama-server is still writing the reply on the same GPU, and the sharing
  // slows Fish about 2.4x (measured 2026-09-10: 153 characters took 3.7 s alone,
  // 8.8 s alongside a generation). The first word then came 6-9 s in, after the text
  // had finished. Past this ceiling the first chunk breaks at a clause instead.
  const SPEECH_FIRST_MAX_CHARS = 80;

  // How many characters the nth chunk of one reply must reach before it may be
  // spoken. Beyond the ramp it settles at the steady-state minimum.
  function speechChunkMinChars(index) {
    const step = Number.isInteger(index) && index > 0 ? index : 0;
    return step < SPEECH_CHUNK_RAMP.length ? SPEECH_CHUNK_RAMP[step] : SPEECH_MIN_CHARS;
  }

  // How long the nth chunk may grow before it is broken at a clause or a word.
  function speechChunkMaxChars(index) {
    const step = Number.isInteger(index) && index > 0 ? index : 0;
    return step === 0 ? SPEECH_FIRST_MAX_CHARS : SPEECH_MAX_CHARS;
  }

  function speechBoundary(text, final, minChars = SPEECH_MIN_CHARS, maxChars = SPEECH_MAX_CHARS) {
    // Only sentence ends inside the ceiling count; past it, the clause break below wins.
    for (let index = 0; index < text.length && index < maxChars; index++) {
      const character = text[index];
      let end = -1;
      if (character === '\n') end = index + 1;
      else if ('.!?'.includes(character) && (index === text.length - 1 || /\s/.test(text[index + 1]))) end = index + 1;
      // A sentence end that would produce too short a chunk is skipped, so the
      // short sentence is spoken together with the text that follows it.
      if (end >= 0 && end >= minChars) return end;
    }
    if (text.length >= maxChars) {
      const window = text.slice(0, maxChars);
      let boundary = Math.max(window.lastIndexOf(', '), window.lastIndexOf('; '), window.lastIndexOf(': '));
      if (boundary < minChars) boundary = window.lastIndexOf(' ');
      if (boundary >= minChars) return boundary + 1;
    }
    // The final chunk has nothing after it, so a short one costs no gap.
    return final ? text.length : -1;
  }

  // Conversation mode ends a turn after ~0.9 s below an end threshold. Derived only
  // from the calibrated floor, that threshold goes stale the moment the room gets
  // louder — music started, a phone brought up to the mic — and the turn then never
  // ends, because nothing falls below 1.5x a floor measured in quiet. So it is also
  // measured from the background heard just before the speech began: the turn ends
  // when the level falls back to that. `ambientLevels` excludes the trigger windows.
  const CONVERSATION_MIN_END_LEVEL = 0.005;
  const CONVERSATION_MIN_AMBIENT_WINDOWS = 4;

  function conversationEndThreshold(noiseFloor, ambientLevels, startThreshold) {
    const floor = Number.isFinite(noiseFloor) && noiseFloor > 0 ? noiseFloor : 0;
    const calibrated = Math.max(CONVERSATION_MIN_END_LEVEL, floor * 1.5);
    const levels = Array.isArray(ambientLevels)
      ? ambientLevels.filter((level) => Number.isFinite(level) && level >= 0)
      : [];
    if (levels.length < CONVERSATION_MIN_AMBIENT_WINDOWS) return calibrated;
    const ordered = levels.slice().sort((left, right) => left - right);
    const ambient = ordered[Math.floor((ordered.length - 1) * 0.9)] * 1.3;
    // Kept below the start threshold, or speech that only just cleared it would
    // count as silence and end the turn after 0.9 s.
    const ceiling = Number.isFinite(startThreshold) && startThreshold > 0 ? startThreshold * 0.9 : ambient;
    return Math.max(calibrated, Math.min(ambient, ceiling));
  }

  root.JarvisCore = Object.freeze({
    ALERT_MAX_DEFER_MS,
    SPEECH_CHUNK_RAMP,
    SPEECH_FIRST_MAX_CHARS,
    SPEECH_MAX_CHARS,
    SPEECH_MIN_CHARS,
    ALERT_SOUND_IDS,
    resolveAlertSound,
    isConversationStopCommand,
    normalizeConversationCommand,
    unsupportedActionResponse,
    countUnsupportedScriptCharacters,
    formatConversationTranscript,
    formatLearnMemory,
    formatMessageTimestamp,
    formatTimerAlert,
    isLearnModeInterviewRequest,
    isLearnModeStartCommand,
    isLearnModeStopCommand,
    isMemoryControlCommand,
    mergeFiredAlerts,
    parseStreamLine,
    resolveSpeechSelection,
    shouldConsiderAutoMemory,
    shouldReleaseAlerts,
    speechBoundary,
    speechChunkMaxChars,
    speechChunkMinChars,
    conversationEndThreshold,
    trimConversationHistory,
  });
})(globalThis);
