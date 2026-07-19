const assert = require('assert');

require('../static/core.js');

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

assert.strictEqual(isConversationStopCommand('No thanks. Goodbye, JARVIS.'), true);
assert.strictEqual(isConversationStopCommand('Please stop listening now.'), true);
assert.strictEqual(isConversationStopCommand('We can end conversation here.'), true);
assert.strictEqual(isConversationStopCommand('goodbye journalism'), false);
assert.strictEqual(isConversationStopCommand('please keep listening'), false);

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
