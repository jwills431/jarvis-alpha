const {performance} = require('perf_hooks');

const chatEndpoint = 'http://127.0.0.1:8787/api/chat';
const healthEndpoint = 'http://127.0.0.1:8787/api/health';
const requestCount = 4;

async function healthReady() {
  const response = await fetch(healthEndpoint, {cache: 'no-store'});
  if (!response.ok) return false;
  const state = await response.json();
  return state.status === 'ready' && state.backend === 'ok';
}

async function runRequest(index) {
  const prompt = [
    `Synthetic sustained-generation reliability request ${index} of ${requestCount}.`,
    'Write a long English technical checklist for maintaining a fictional deep-space research vessel.',
    'Use numbered sections, complete sentences, no non-English scripts, and continue until the response limit.',
  ].join(' ');
  const started = performance.now();
  const response = await fetch(chatEndpoint, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({messages: [{role: 'user', content: prompt}]}),
  });
  if (!response.ok || !response.body) throw new Error(`request ${index} returned HTTP ${response.status}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let characters = 0;
  let completed = false;
  while (true) {
    const {value, done} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream: true});
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (line === 'data: [DONE]') {
        completed = true;
        continue;
      }
      if (!line.startsWith('data: ')) continue;
      const event = JSON.parse(line.slice(6));
      characters += (event.choices?.[0]?.delta?.content || '').length;
    }
  }
  const elapsedMs = Math.round(performance.now() - started);
  if (!completed || characters < 500) throw new Error(`request ${index} was incomplete`);
  return {request: index, elapsed_ms: elapsedMs, characters, completed};
}

async function main() {
  if (!(await healthReady())) throw new Error('pre-soak health is not ready');
  const results = [];
  for (let index = 1; index <= requestCount; index++) {
    const result = await runRequest(index);
    results.push(result);
    console.log(JSON.stringify(result));
    if (!(await healthReady())) throw new Error(`health failed after request ${index}`);
  }
  const elapsed = results.map((result) => result.elapsed_ms);
  console.log(JSON.stringify({
    summary: 'pass',
    requests: results.length,
    min_ms: Math.min(...elapsed),
    max_ms: Math.max(...elapsed),
    mean_ms: Math.round(elapsed.reduce((sum, value) => sum + value, 0) / elapsed.length),
  }));
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
