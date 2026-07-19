const endpoint = 'http://127.0.0.1:8787/api/chat';

async function main() {
  const messages = [
    {role: 'user', content: 'For this synthetic test, the project title is Northstar.'},
    {role: 'assistant', content: 'The project title is Northstar.'},
    {role: 'user', content: 'The established story year is 2187.'},
    {role: 'assistant', content: 'Northstar is established in the year 2187.'},
    {role: 'user', content: 'Suggest one mood word for the opening scene.'},
  ];
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({messages}),
  });
  const raw = await response.text();
  if (!response.ok || !raw.includes('data: [DONE]')) {
    throw new Error(`incomplete response: HTTP ${response.status}`);
  }
  let answer = '';
  for (const line of raw.split('\n')) {
    if (!line.startsWith('data: ') || line === 'data: [DONE]') continue;
    const event = JSON.parse(line.slice(6));
    answer += event.choices?.[0]?.delta?.content || '';
  }
  const normalized = answer.trim().replace(/[.!?]+$/u, '');
  const words = normalized.match(/[A-Za-z-]+/gu) || [];
  // This check guards against recap content, not harmless presentation variance
  // between one word, a short label, and a concise recommendation sentence.
  if (!normalized || words.length > 15) {
    throw new Error(`focused-response check failed: ${JSON.stringify(answer.trim())}`);
  }
  if (/Northstar|2187/iu.test(answer)) {
    throw new Error('focused-response check repeated prior facts');
  }
  console.log('focused no-recap check passed');
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
