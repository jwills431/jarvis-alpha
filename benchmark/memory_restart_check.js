const baseUrl = 'http://127.0.0.1:8787';
const marker = 'RESTART-ASTER-260718';
const text = `The synthetic restart acceptance marker is ${marker}.`;

async function jsonRequest(path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, options);
  const body = await response.json();
  return {response, body};
}

async function chat(content) {
  const response = await fetch(`${baseUrl}/api/chat`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({messages: [{role: 'user', content}]}),
  });
  const raw = await response.text();
  if (!response.ok || !raw.includes('data: [DONE]')) {
    throw new Error(`incomplete chat response: HTTP ${response.status}`);
  }
  let answer = '';
  for (const line of raw.split('\n')) {
    if (!line.startsWith('data: ') || line === 'data: [DONE]') continue;
    const event = JSON.parse(line.slice(6));
    answer += event.choices?.[0]?.delta?.content || '';
  }
  return answer;
}

async function seed() {
  const current = await jsonRequest('/api/memories');
  if (!current.response.ok) throw new Error('memory list unavailable before restart');
  if (current.body.items.some((item) => item.text === text)) {
    throw new Error('restart test marker already exists; cleanup is required');
  }
  const added = await jsonRequest('/api/memories', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({category: 'environment', text}),
  });
  if (added.response.status !== 201) throw new Error('restart test seed failed');
  console.log('explicit-memory restart seed created');
}

async function verify() {
  const current = await jsonRequest('/api/memories');
  if (!current.response.ok) throw new Error('memory list unavailable after restart');
  const item = current.body.items.find((candidate) => candidate.text === text);
  if (!item) throw new Error('memory did not persist across the foreground restart');
  try {
    const recall = await chat('Recall the synthetic restart acceptance marker. Reply with the marker only.');
    if (!recall.toUpperCase().includes(marker)) {
      throw new Error('persisted memory was not available to the model after restart');
    }
  } finally {
    await jsonRequest(`/api/memories/${item.id}`, {method: 'DELETE'});
  }
  const afterDelete = await jsonRequest('/api/memories');
  if (afterDelete.body.items.some((candidate) => candidate.text === text)) {
    throw new Error('restart test cleanup failed');
  }
  console.log('explicit-memory foreground-restart persistence and cleanup check passed');
}

const action = process.argv[2];
const operation = action === 'seed' ? seed : action === 'verify' ? verify : null;
if (!operation) {
  console.error('usage: node benchmark/memory_restart_check.js seed|verify');
  process.exitCode = 2;
} else {
  operation().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
