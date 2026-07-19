const endpoint = 'http://127.0.0.1:8787/api/chat';

async function main() {
  const messages = [
    {role: 'user', content: 'I am outlining a synthetic science-fiction story with an unnamed alien species.'},
    {role: 'assistant', content: 'I will call the species the Zorans.'},
    {role: 'user', content: 'No. The correct name is spelled Q U O R I N; use my spelling exactly.'},
    {role: 'assistant', content: 'Understood. I will use Quoren.'},
    {role: 'user', content: 'What is the exact spelling I gave? Reply with that name only.'},
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
  const normalized = answer.trim().replace(/[.\s]+$/u, '');
  if (normalized !== 'QUORIN') throw new Error(`exact-spelling check failed: ${JSON.stringify(answer.trim())}`);
  console.log('exact-spelling check passed');
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
