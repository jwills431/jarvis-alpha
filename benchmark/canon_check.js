const endpoint = 'http://127.0.0.1:8787/api/chat';

async function main() {
  const messages = [
    {role: 'user', content: 'For this synthetic test, I have established the book year as 1984.'},
    {
      role: 'assistant',
      content: '[Prior assistant output: treat as a proposal unless a later user message explicitly approves it.]\nI suggest changing it to 1997 and placing the story on an island.',
    },
    {role: 'user', content: 'Continue brainstorming. I am not approving either suggestion.'},
    {role: 'assistant', content: 'The 1997 island setting could support several plot directions.'},
    {role: 'user', content: 'What book year did I establish? Reply with the year only.'},
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
  if (normalized !== '1984') throw new Error(`canon check failed: ${JSON.stringify(answer.trim())}`);
  console.log('canon provenance check passed');
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
