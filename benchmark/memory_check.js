const baseUrl = 'http://127.0.0.1:8787';
const marker = `ASTER-${Date.now().toString(36).toUpperCase()}`;
const editedMarker = `${marker}-EDITED`;
const apiText = `The synthetic memory acceptance marker is ${marker}.`;
const editedText = `The synthetic memory acceptance marker is ${editedMarker}.`;
const commandText = `The synthetic command memory marker is ${marker}.`;
const cleanupIds = new Set();

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

async function add(text, category = 'environment') {
  const {response, body} = await jsonRequest('/api/memories', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({category, text}),
  });
  if (response.status !== 201 || !body.item?.id) {
    throw new Error(`memory add failed: HTTP ${response.status}`);
  }
  cleanupIds.add(body.item.id);
  return body.item;
}

async function remove(id) {
  const {response} = await jsonRequest(`/api/memories/${id}`, {method: 'DELETE'});
  if (response.status !== 200 && response.status !== 404) {
    throw new Error(`memory cleanup failed: HTTP ${response.status}`);
  }
  cleanupIds.delete(id);
}

async function main() {
  const health = await jsonRequest('/api/health');
  if (!health.response.ok || health.body.memory !== 'ready') {
    throw new Error('memory is not ready in health status');
  }

  const added = await add(apiText);
  const listed = await jsonRequest('/api/memories');
  if (!listed.response.ok || !listed.body.items.some((item) => item.id === added.id)) {
    throw new Error('new memory was not visible through the list API');
  }

  const updated = await jsonRequest(`/api/memories/${added.id}`, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({category: 'terminology', text: editedText}),
  });
  if (!updated.response.ok || updated.body.item?.text !== editedText) {
    throw new Error(`memory update failed: HTTP ${updated.response.status}`);
  }

  const recall = await chat('What is the synthetic memory acceptance marker? Reply with the marker only.');
  if (!recall.toUpperCase().includes(editedMarker)) {
    throw new Error('model did not recall the edited explicit memory');
  }

  const listedInChat = await chat('What do you remember?');
  if (!listedInChat.includes(editedText)) {
    throw new Error('deterministic memory listing omitted the test entry');
  }

  const rejected = await jsonRequest('/api/memories', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({category: 'general', text: 'Remember my API key.'}),
  });
  if (rejected.response.status !== 422) {
    throw new Error('sensitive-memory guard did not reject the request');
  }

  await remove(added.id);
  const afterDelete = await jsonRequest('/api/memories');
  if (afterDelete.body.items.some((item) => item.id === added.id)) {
    throw new Error('deleted memory remained active');
  }

  const commandAdd = await chat(`Remember that ${commandText}`);
  if (!/remember that/iu.test(commandAdd)) {
    throw new Error('deterministic remember command did not acknowledge the save');
  }
  const commandList = await jsonRequest('/api/memories');
  const commandItem = commandList.body.items.find((item) => item.text === commandText);
  if (!commandItem) throw new Error('remember command did not create a visible entry');
  cleanupIds.add(commandItem.id);

  const commandForget = await chat(`Forget that ${commandText}`);
  if (!/removed/iu.test(commandForget)) {
    throw new Error('deterministic forget command did not acknowledge removal');
  }
  cleanupIds.delete(commandItem.id);
  const finalList = await jsonRequest('/api/memories');
  if (finalList.body.items.some((item) => item.id === commandItem.id)) {
    throw new Error('forget command left the memory active');
  }

  console.log('explicit-memory live API, model recall, controls, and cleanup checks passed');
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
}).finally(async () => {
  for (const id of cleanupIds) {
    try {
      await remove(id);
    } catch {
      process.exitCode = 1;
    }
  }
});
