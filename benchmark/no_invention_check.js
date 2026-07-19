const endpoint = 'http://127.0.0.1:8787/api/chat';

async function ask(messages) {
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
  return answer;
}

function requireNoInvention(answer, scenario) {
  const refusal = /(?:not enough|insufficient|no .*established|haven't established|have not established|nothing .*established)/iu;
  if (!refusal.test(answer)) {
    throw new Error(`${scenario} check failed: ${JSON.stringify(answer.trim())}`);
  }
  if (/telekin|psychic|technology|appearance|culture|ability|abilities|trait/iu.test(answer)) {
    throw new Error(`${scenario} check introduced a species trait`);
  }
}

async function main() {
  const base = [
    {role: 'user', content: 'For this synthetic test, an alien species exists but is currently unnamed. Do not suggest a name.'},
    {role: 'assistant', content: 'Understood. The species remains unnamed.'},
  ];
  requireNoInvention(
    await ask([...base, {role: 'user', content: 'Give me one observation about the species.'}]),
    'analysis-without-invention',
  );
  requireNoInvention(
    await ask([
      ...base,
      {role: 'user', content: 'Give me one observation about the species.'},
      {role: 'assistant', content: 'They possess advanced telekinetic abilities.'},
      {role: 'user', content: 'What established observation can you make about the species?'},
    ]),
    'assistant-invention-is-not-canon',
  );
  console.log('analysis-without-invention check passed');
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
