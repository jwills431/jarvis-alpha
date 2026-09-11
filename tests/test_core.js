const assert = require('assert');

require('../static/core.js');

const {
  ALERT_MAX_DEFER_MS,
  conversationEndThreshold,
  countUnsupportedScriptCharacters,
  formatConversationTranscript,
  formatLearnMemory,
  isConversationStopCommand,
  isLearnModeInterviewRequest,
  isLearnModeStartCommand,
  isLearnModeStopCommand,
  isMemoryControlCommand,
  formatMessageTimestamp,
  formatTimerAlert,
  mergeFiredAlerts,
  parseStreamLine,
  ALERT_SOUND_IDS,
  resolveAlertSound,
  resolveSpeechSelection,
  shouldConsiderAutoMemory,
  shouldReleaseAlerts,
  speechBoundary,
  speechChunkMaxChars,
  speechChunkMinChars,
  SPEECH_CHUNK_RAMP,
  SPEECH_FIRST_MAX_CHARS,
  SPEECH_MIN_CHARS,
  SPEECH_MAX_CHARS,
  trimConversationHistory,
  unsupportedActionResponse,
} = globalThis.JarvisCore;

assert.strictEqual(isConversationStopCommand('No thanks. Goodbye, JARVIS.'), true);
assert.strictEqual(isConversationStopCommand('Please stop listening now.'), true);
assert.strictEqual(isConversationStopCommand('We can end conversation here.'), true);
assert.strictEqual(isConversationStopCommand('goodbye journalism'), false);
assert.strictEqual(isConversationStopCommand('please keep listening'), false);

// Natural ways of asking for conversation mode to end, beyond the fixed phrases.
assert.strictEqual(isConversationStopCommand('Turn off conversation mode.'), true);
assert.strictEqual(isConversationStopCommand('Can you exit conversation mode please?'), true);
assert.strictEqual(isConversationStopCommand('Disable conversation mode for now.'), true);
assert.strictEqual(isConversationStopCommand('Jarvis, I need to go silent for a bit but keep going via text.'), true);
assert.strictEqual(isConversationStopCommand('Can we switch to text only?'), true);
assert.strictEqual(isConversationStopCommand('Close the microphone.'), true);

// Questions about the feature are not requests to use it.
assert.strictEqual(isConversationStopCommand('How do I turn off conversation mode?'), false);
assert.strictEqual(isConversationStopCommand('What does conversation mode do?'), false);
assert.strictEqual(isConversationStopCommand('Conversation mode is useful.'), false);
assert.strictEqual(isConversationStopCommand('I stopped the microwave.'), false);

assert.match(unsupportedActionResponse('Set a reminder in 30 minutes.'), /not available/i);
assert.match(unsupportedActionResponse('Remind me to check the oven.'), /not available/i);
assert.match(unsupportedActionResponse('Start a timer for ten minutes.'), /not available/i);
assert.strictEqual(unsupportedActionResponse('Explain how reminder applications work.'), null);
assert.strictEqual(unsupportedActionResponse('Please remind me why this test exists.'), null);

assert.strictEqual(countUnsupportedScriptCharacters('Ordinary English response.'), 0);
assert.strictEqual(countUnsupportedScriptCharacters('测试内容'), 4);
assert.strictEqual(countUnsupportedScriptCharacters('English then тест'), 4);

let history = [];
for (let turn = 1; turn <= 15; turn++) {
  history = trimConversationHistory(
    [...history, {role: 'user', content: `user ${turn}`}],
    {maxMessages: 20, maxChars: 12000},
  );
  assert.strictEqual(history[0].role, 'user');
  assert.strictEqual(history.at(-1).role, 'user');
  history = trimConversationHistory(
    [...history, {role: 'assistant', content: `assistant ${turn}`}],
    {maxMessages: 20, maxChars: 12000},
  );
}
assert.strictEqual(history.length, 20);
assert.strictEqual(history[0].role, 'user');
assert.strictEqual(history.at(-1).role, 'assistant');
history.forEach((message, index) => {
  assert.strictEqual(message.role, index % 2 === 0 ? 'user' : 'assistant');
});

const charBounded = trimConversationHistory([
  {role: 'user', content: 'a'.repeat(4000)},
  {role: 'assistant', content: 'b'.repeat(4000)},
  {role: 'user', content: 'c'.repeat(4000)},
], {maxMessages: 20, maxChars: 9000});
assert.deepStrictEqual(charBounded, [{role: 'user', content: 'c'.repeat(4000)}]);

const malformedSuffix = trimConversationHistory([
  {role: 'user', content: 'valid old user'},
  {role: 'assistant', content: 'valid old assistant'},
  {role: 'assistant', content: 'orphan assistant'},
  {role: 'user', content: 'latest user'},
], {maxMessages: 20, maxChars: 12000});
assert.deepStrictEqual(malformedSuffix, [{role: 'user', content: 'latest user'}]);

assert.strictEqual(formatConversationTranscript([
  {role: 'assistant', content: 'Ready when online.'},
  {role: 'user', content: 'Hello there.'},
  {role: 'assistant', content: 'At your service.'},
]), 'You:\nHello there.\n\nJARVIS:\nAt your service.');
assert.strictEqual(formatConversationTranscript([{role: 'assistant', content: 'No user turn.'}]), '');
assert.strictEqual(formatConversationTranscript(null), '');

assert.strictEqual(isLearnModeStartCommand('Start learning mode.'), true);
assert.strictEqual(isLearnModeStartCommand('Please teach me how learning modes work.'), false);
assert.strictEqual(isLearnModeInterviewRequest('Ask me a few questions to get to know me.'), true);
assert.strictEqual(isLearnModeInterviewRequest('How do people get to know one another?'), false);
assert.strictEqual(isLearnModeStopCommand('Stop memory capture.'), true);
assert.strictEqual(isLearnModeStopCommand('Do not stop learning about this subject.'), false);
assert.strictEqual(isMemoryControlCommand('Remember that my test color is blue.'), true);
assert.strictEqual(isMemoryControlCommand('What do you remember?'), true);
assert.strictEqual(isMemoryControlCommand('I remember that movie.'), false);

assert.strictEqual(
  formatLearnMemory('What is your favorite color?', 'Cobalt.', 1000),
  'JARVIS asked: What is your favorite color?\nUser answered: Cobalt.',
);
assert.strictEqual(
  formatLearnMemory('I can help. What is your favorite color? Anything else?', 'Cobalt.', 1000),
  'JARVIS asked: Anything else?\nUser answered: Cobalt.',
);
assert.strictEqual(formatLearnMemory('', 'A standalone fact.', 1000), 'User said during Learn mode: A standalone fact.');
assert.strictEqual(formatLearnMemory('Question?', 'x'.repeat(1001), 1000), null);

assert.strictEqual(shouldConsiderAutoMemory('I prefer concise answers with examples.'), true);
assert.strictEqual(shouldConsiderAutoMemory('My favorite test color is cobalt.'), true);
assert.strictEqual(shouldConsiderAutoMemory('We decided the synthetic project year is 2191.'), true);
assert.strictEqual(shouldConsiderAutoMemory('The synthetic team meets every Tuesday at noon.'), true);
assert.strictEqual(shouldConsiderAutoMemory('Cobalt.', 'What is your favorite color?'), true);
assert.strictEqual(shouldConsiderAutoMemory('What color should I choose?'), false);
assert.strictEqual(shouldConsiderAutoMemory('Which color do I prefer?', 'Do you have a preference?'), false);
assert.strictEqual(shouldConsiderAutoMemory('Remember that my test color is blue.'), false);
assert.strictEqual(shouldConsiderAutoMemory('Thanks!'), false);
assert.strictEqual(shouldConsiderAutoMemory('Explain the synthetic team meeting schedule.'), false);

console.log('browser core logic: ok');

// Speech selection: configuration is authoritative unless a still-current
// browser override exists.
const installedVoices = [
  {name: 'Daniel', locale: 'en_GB'},
  {name: 'Jamie (Premium)', locale: 'en_GB'},
  {name: 'Samantha', locale: 'en_US'},
];
const speechOptions = {
  voices: installedVoices,
  minimumRate: 120,
  maximumRate: 350,
  defaultRate: 190,
  defaultVoice: 'Jamie (Premium)',
};

// No stored override: the configured voice is used.
let selection = resolveSpeechSelection(speechOptions, {});
assert.strictEqual(selection.voice, 'Jamie (Premium)');
assert.strictEqual(selection.rate, 190);
assert.strictEqual(selection.overridden, false);
assert.deepStrictEqual(selection.stale, []);

// A legacy override with no recorded default is stale; configuration wins.
selection = resolveSpeechSelection(speechOptions, {voice: 'Daniel', rate: '210'});
assert.strictEqual(selection.voice, 'Jamie (Premium)');
assert.strictEqual(selection.rate, 190);
assert.strictEqual(selection.overridden, false);
assert.deepStrictEqual(selection.stale.sort(), ['rate', 'voice']);

// An override saved against the current configured default still applies.
selection = resolveSpeechSelection(speechOptions, {
  voice: 'Samantha',
  voiceDefault: 'Jamie (Premium)',
  rate: '210',
  rateDefault: '190',
});
assert.strictEqual(selection.voice, 'Samantha');
assert.strictEqual(selection.rate, 210);
assert.strictEqual(selection.overridden, true);
assert.deepStrictEqual(selection.stale, []);

// Changing the configured voice discards the override saved against the old one.
selection = resolveSpeechSelection(
  {...speechOptions, defaultVoice: 'Daniel'},
  {voice: 'Samantha', voiceDefault: 'Jamie (Premium)', rate: '210', rateDefault: '190'},
);
assert.strictEqual(selection.voice, 'Daniel');
assert.strictEqual(selection.rate, 210);
assert.deepStrictEqual(selection.stale, ['voice']);

// An override naming a voice that is no longer installed is discarded.
selection = resolveSpeechSelection(speechOptions, {voice: 'Alex', voiceDefault: 'Jamie (Premium)'});
assert.strictEqual(selection.voice, 'Jamie (Premium)');
assert.deepStrictEqual(selection.stale, ['voice']);

// A configured voice that is not installed falls back to an installed voice.
selection = resolveSpeechSelection({...speechOptions, defaultVoice: 'Jamie'}, {});
assert.strictEqual(selection.voice, 'Daniel');
assert.strictEqual(selection.defaultVoice, 'Daniel');

// Out-of-range rates are rejected rather than sent to the server.
selection = resolveSpeechSelection(speechOptions, {voice: null, rate: '900', rateDefault: '190'});
assert.strictEqual(selection.rate, 190);
assert.deepStrictEqual(selection.stale, ['rate']);

// Without installed voices nothing is invented.
selection = resolveSpeechSelection({voices: []}, {voice: 'Daniel', voiceDefault: 'Daniel'});
assert.strictEqual(selection.voice, null);
assert.strictEqual(selection.rate, null);

// ---------- parseStreamLine (SSE classification for the tool loop) ----------
assert.deepStrictEqual(parseStreamLine('data: [DONE]'), {type: 'done'});
assert.strictEqual(parseStreamLine('event: ping'), null);
assert.strictEqual(parseStreamLine('data: not json'), null);
assert.deepStrictEqual(
  parseStreamLine('data: ' + JSON.stringify({choices: [{delta: {content: 'Hi'}}]})),
  {type: 'content', content: 'Hi'},
);
// A content delta with no content (e.g. a finish-reason-only frame) is ignored.
assert.deepStrictEqual(
  parseStreamLine('data: ' + JSON.stringify({choices: [{delta: {}, finish_reason: 'stop'}]})),
  {type: 'ignore'},
);
// Tool events arrive under the jarvis envelope.
const resultLine = parseStreamLine('data: ' + JSON.stringify({
  jarvis: {kind: 'tool_result', id: 'c1', name: 'get_time', arguments: {}, status: 'ok', result: {time: '10:00:00'}},
}));
assert.strictEqual(resultLine.type, 'tool_result');
assert.strictEqual(resultLine.event.name, 'get_time');
const proposalLine = parseStreamLine('data: ' + JSON.stringify({
  jarvis: {kind: 'tool_proposal', id: 'abc', name: 'set_timer', arguments: {minutes: 5}},
}));
assert.strictEqual(proposalLine.type, 'tool_proposal');
assert.strictEqual(proposalLine.event.id, 'abc');
// An unknown jarvis kind is ignored, not misrouted.
assert.deepStrictEqual(
  parseStreamLine('data: ' + JSON.stringify({jarvis: {kind: 'mystery'}})),
  {type: 'ignore'},
);

console.log('tool-loop stream parsing: ok');

// ---------- formatTimerAlert (no "timer timer" duplication) ----------
assert.strictEqual(formatTimerAlert({kind: 'timer', label: 'tea'}), 'Your tea timer is up.');
assert.strictEqual(formatTimerAlert({kind: 'timer', label: 'one minute timer'}), 'Your one minute timer is up.');
assert.strictEqual(formatTimerAlert({kind: 'timer', label: 'kitchen alarm'}), 'Your kitchen alarm is up.');
assert.strictEqual(formatTimerAlert({kind: 'timer', label: ''}), 'Your timer is up.');
assert.strictEqual(formatTimerAlert({kind: 'timer'}), 'Your timer is up.');
assert.strictEqual(formatTimerAlert({kind: 'reminder', label: 'check the oven'}), 'Reminder: check the oven');
assert.strictEqual(formatTimerAlert({kind: 'reminder', label: ''}), 'This is your reminder.');
console.log('timer alert formatting: ok');

// ---------- formatMessageTimestamp (deterministic, locale-independent) ----------
assert.strictEqual(formatMessageTimestamp(new Date(2026, 7, 5, 22, 30)), '10:30 PM · 8/5/2026');
assert.strictEqual(formatMessageTimestamp(new Date(2026, 0, 9, 9, 5)), '9:05 AM · 1/9/2026');
assert.strictEqual(formatMessageTimestamp(new Date(2026, 7, 5, 0, 0)), '12:00 AM · 8/5/2026');
assert.strictEqual(formatMessageTimestamp(new Date(2026, 7, 5, 12, 0)), '12:00 PM · 8/5/2026');
assert.strictEqual(formatMessageTimestamp('not a date'), '');
console.log('message timestamp formatting: ok');

// ---------- resolveAlertSound (stored choice validated against known ids) ----------
assert.ok(ALERT_SOUND_IDS.includes('chime') && ALERT_SOUND_IDS.includes('alarm'));
assert.strictEqual(resolveAlertSound('bell', 'chime'), 'bell');          // valid stored wins
assert.strictEqual(resolveAlertSound('nonexistent', 'chime'), 'chime');  // fall back to per-type default
assert.strictEqual(resolveAlertSound(null, 'beep'), 'beep');             // no stored -> fallback
assert.strictEqual(resolveAlertSound('nope', 'alsobad'), ALERT_SOUND_IDS[0]); // both invalid -> first
console.log('alert sound selection: ok');

// ---------- fired-alert queue (never interrupt a reply, never lose an alert) ----------
const t0 = 1_000_000;

// Merging stamps each new alert with its arrival time and keeps the queue in order.
let queue = mergeFiredAlerts([], [{id: 'a'}, {id: 'b'}], t0);
assert.strictEqual(queue.length, 2);
assert.strictEqual(queue[0].fired.id, 'a');
assert.strictEqual(queue[0].queuedAt, t0);

// The server hands each fired timer over once, but a re-delivered id must not double.
queue = mergeFiredAlerts(queue, [{id: 'b'}, {id: 'c'}], t0 + 4000);
assert.deepStrictEqual(queue.map((entry) => entry.fired.id), ['a', 'b', 'c']);
assert.strictEqual(queue[2].queuedAt, t0 + 4000);

// Nothing queued: nothing to release.
assert.strictEqual(shouldReleaseAlerts([], false, t0), false);
assert.strictEqual(shouldReleaseAlerts(null, false, t0), false);

// Silent: release at once.
assert.strictEqual(shouldReleaseAlerts(queue, false, t0), true);

// Speaking: hold, so the alert does not cut the reply off mid-sentence.
assert.strictEqual(shouldReleaseAlerts(queue, true, t0 + 1000), false);

// Still speaking past the ceiling: release anyway rather than lose it. The oldest
// entry governs, so a newer alert cannot keep resetting the clock. The ceiling is a
// safety net for a stuck speaking state: an ordinary long reply must finish first
// (on-device, a 20 s ceiling tripped mid-reply and split the sound from the words).
assert.ok(ALERT_MAX_DEFER_MS >= 60_000);
assert.strictEqual(shouldReleaseAlerts(queue, true, t0 + 20_000), false);
assert.strictEqual(shouldReleaseAlerts(queue, true, t0 + ALERT_MAX_DEFER_MS - 1), false);
assert.strictEqual(shouldReleaseAlerts(queue, true, t0 + ALERT_MAX_DEFER_MS), true);
assert.strictEqual(shouldReleaseAlerts(queue, true, t0 + 1000, 500), true);

// A malformed entry must not strand the queue forever.
assert.strictEqual(shouldReleaseAlerts([{fired: {id: 'x'}}], true, t0), true);
console.log('fired-alert queue: ok');

// ---------- speech chunking (first word fast, then ramp up to build buffer) ----------
// Fish does not stream within a request, so the first chunk alone decides how long
// the wait for the first word is. The ramp must start small and grow.
assert.deepStrictEqual(SPEECH_CHUNK_RAMP, [30, 60, 120]);
assert.strictEqual(speechChunkMinChars(0), 30);
assert.strictEqual(speechChunkMinChars(1), 60);
assert.strictEqual(speechChunkMinChars(2), 120);
assert.strictEqual(speechChunkMinChars(3), SPEECH_MIN_CHARS);   // settles at steady state
assert.strictEqual(speechChunkMinChars(99), SPEECH_MIN_CHARS);
assert.strictEqual(speechChunkMinChars(undefined), 30);         // malformed -> first step
assert.strictEqual(speechChunkMinChars(-1), 30);

// Each ramp step must render before the previous chunk finishes playing, or the
// gap the chunking exists to avoid comes straight back. Measured on this box:
// render = 0.3s + 0.0165s/char, audio = 0.049s/char.
const renderCost = (chars) => 0.3 + 0.0165 * chars;
const audioLength = (chars) => 0.049 * chars;
for (let step = 1; step < SPEECH_CHUNK_RAMP.length; step++) {
  const previous = SPEECH_CHUNK_RAMP[step - 1];
  assert.ok(
    renderCost(SPEECH_CHUNK_RAMP[step]) <= audioLength(previous),
    `ramp step ${step} (${SPEECH_CHUNK_RAMP[step]} chars) cannot render inside ` +
    `the ${audioLength(previous).toFixed(2)}s of audio from ${previous} chars`,
  );
}
// The steady-state minimum must also be reachable from the last ramp step.
assert.ok(renderCost(SPEECH_MIN_CHARS) <= audioLength(SPEECH_CHUNK_RAMP.at(-1)));

// A sentence ending before the minimum is merged forward rather than spoken alone.
const two = 'Timer set. I will let you know the moment that minute is up, sir.';
assert.strictEqual(speechBoundary(two, false, 30), two.indexOf('up, sir.') + 'up, sir.'.length);
// Once the text reaches the minimum, the first sentence end past it wins.
assert.strictEqual(speechBoundary('A'.repeat(28) + '. tail here.', false, 30), 40);
// Nothing is emitted mid-reply until a boundary qualifies...
assert.strictEqual(speechBoundary('Timer set.', false, 30), -1);
// ...but the final flush always speaks what is left, however short.
assert.strictEqual(speechBoundary('Timer set.', true, 30), 10);
// A run with no sentence end at all breaks at the cap rather than growing forever.
assert.ok(speechBoundary('word '.repeat(80), false, 30) <= SPEECH_MAX_CHARS);

// The first chunk has a ceiling of its own: a long opening sentence breaks at a
// clause instead of waiting for its full stop, because that chunk renders while the
// model still holds the GPU (measured ~2.4x slower: 153 chars, 3.7 s alone, 8.8 s shared).
assert.strictEqual(speechChunkMaxChars(0), SPEECH_FIRST_MAX_CHARS);
assert.strictEqual(speechChunkMaxChars(1), SPEECH_MAX_CHARS);
assert.strictEqual(speechChunkMaxChars(undefined), SPEECH_FIRST_MAX_CHARS);
assert.ok(SPEECH_FIRST_MAX_CHARS > SPEECH_CHUNK_RAMP[0] && SPEECH_FIRST_MAX_CHARS < SPEECH_MAX_CHARS);
assert.ok(renderCost(SPEECH_FIRST_MAX_CHARS) * 2.4 <= 4, 'first chunk must render within ~4 s on a shared GPU');
const opening = 'A jet engine pulls air in at the front, squeezes it hard with a compressor, then mixes it with fuel and ignites it.';
const clauseCut = speechBoundary(opening, false, 30, SPEECH_FIRST_MAX_CHARS);
assert.strictEqual(clauseCut, opening.slice(0, SPEECH_FIRST_MAX_CHARS).lastIndexOf(', ') + 1);
assert.ok(clauseCut >= 30 && clauseCut <= SPEECH_FIRST_MAX_CHARS);
// A full stop past the ceiling does not win over the clause break inside it.
assert.ok(speechBoundary(opening, true, 30, SPEECH_FIRST_MAX_CHARS) < opening.length);
// A short opening sentence still ends at its own full stop.
const shortOpening = 'Certainly, sir, here is how it works. A jet engine pulls air in at the front.';
assert.strictEqual(speechBoundary(shortOpening, false, 30, SPEECH_FIRST_MAX_CHARS), shortOpening.indexOf('works.') + 'works.'.length);
// No clause mark in range: break between words, never inside one.
const unpunctuated = 'word '.repeat(30);
const wordCut = speechBoundary(unpunctuated, false, 30, SPEECH_FIRST_MAX_CHARS);
assert.ok(wordCut >= 30 && wordCut <= SPEECH_FIRST_MAX_CHARS);
assert.strictEqual(unpunctuated[wordCut - 1], ' ');
// Under the ceiling with no full stop yet: keep waiting for more text.
assert.strictEqual(speechBoundary(opening.slice(0, 70), false, 30, SPEECH_FIRST_MAX_CHARS), -1);
console.log('speech chunking ramp: ok');

// ---------- conversation end-of-turn threshold ----------
// Too little background heard, or a quiet one: the calibrated rule stands.
assert.strictEqual(conversationEndThreshold(0.002, [], 0.008), 0.005);
assert.strictEqual(conversationEndThreshold(0.01, [0.001, 0.001], 0.024), 0.015);
assert.strictEqual(conversationEndThreshold(0.01, Array(10).fill(0.001), 0.024), 0.015);
// Malformed levels are ignored rather than trusted.
assert.strictEqual(conversationEndThreshold(0.002, [NaN, -1, 'x', 0.001], 0.008), 0.005);
// The room is louder than calibration measured (music by the mic): the turn ends
// when the level falls back to that background, not to the stale quiet floor.
const music = [0.012, 0.013, 0.014, 0.015, 0.016, 0.012, 0.013, 0.014, 0.015, 0.016];
const musicEnd = conversationEndThreshold(0.01, music, 0.024);
assert.ok(Math.abs(musicEnd - 0.016 * 1.3) < 1e-9);
assert.ok(musicEnd > 0.015);
// Never at or above the start threshold, or barely-audible speech would end the turn.
const nearStart = conversationEndThreshold(0.002, Array(10).fill(0.0079), 0.008);
assert.ok(Math.abs(nearStart - 0.008 * 0.9) < 1e-9);
assert.ok(nearStart < 0.008);
console.log('conversation end threshold: ok');
