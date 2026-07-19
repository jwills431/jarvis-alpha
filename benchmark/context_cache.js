const {performance} = require('perf_hooks');

require('../static/core.js');

const {trimConversationHistory} = globalThis.JarvisCore;
const endpoint = 'http://127.0.0.1:8787/api/chat';
const limits = {maxMessages: 20, maxChars: 12000};
const filler = 'This is neutral synthetic context used only to measure rolling prompt-cache behavior. '.repeat(4);

async function request(messages) {
  const started = performance.now();
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({messages}),
  });
  const raw = await response.text();
  const elapsedMs = performance.now() - started;
  if (!response.ok || !raw.includes('data: [DONE]')) throw new Error(`incomplete response: HTTP ${response.status}`);
  let answer = '';
  for (const line of raw.split('\n')) {
    if (!line.startsWith('data: ') || line === 'data: [DONE]') continue;
    const event = JSON.parse(line.slice(6));
    answer += event.choices?.[0]?.delta?.content || '';
  }
  if (!answer.trim()) throw new Error('empty response');
  return {answer, elapsedMs};
}

async function main() {
  let history = [];
  for (let turn = 1; turn <= 9; turn++) {
    history.push({role: 'user', content: `Synthetic user turn ${turn}. ${filler}`});
    history.push({role: 'assistant', content: `Synthetic assistant proposal ${turn}. ${filler}`});
  }
  history = trimConversationHistory(
    [...history, {role: 'user', content: 'Synthetic turn 10. Reply only ACK TEN.'}],
    limits,
  );
  const first = await request(history);
  history = trimConversationHistory([...history, {role: 'assistant', content: first.answer}], limits);
  history = trimConversationHistory(
    [...history, {role: 'user', content: 'Synthetic turn 11. Reply only ACK ELEVEN.'}],
    limits,
  );
  const second = await request(history);
  console.log(JSON.stringify({
    first_ms: Math.round(first.elapsedMs),
    second_ms: Math.round(second.elapsedMs),
    second_to_first_ratio: Number((second.elapsedMs / first.elapsedMs).toFixed(3)),
    retained_messages: history.length,
  }));
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
