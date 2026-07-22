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

  function isConversationStopCommand(value) {
    if (typeof value !== 'string') return false;
    const normalized = ` ${normalizeConversationCommand(value)} `;
    return conversationStopCommands.some((command) => normalized.includes(` ${command} `));
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

  root.JarvisCore = Object.freeze({
    isConversationStopCommand,
    normalizeConversationCommand,
    unsupportedActionResponse,
    countUnsupportedScriptCharacters,
    formatConversationTranscript,
    formatLearnMemory,
    isLearnModeInterviewRequest,
    isLearnModeStartCommand,
    isLearnModeStopCommand,
    isMemoryControlCommand,
    resolveSpeechSelection,
    shouldConsiderAutoMemory,
    trimConversationHistory,
  });
})(globalThis);
