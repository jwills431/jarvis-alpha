const endpoint = 'http://127.0.0.1:8787/api/chat';

async function main() {
  const messages = [
    {role: 'user', content: 'The fictional project title is Northstar.'},
    {role: 'assistant', content: 'Northstar is the project title.'},
    {role: 'user', content: 'The story year is 2187.'},
    {role: 'assistant', content: 'The story year is 2187.'},
    {role: 'user', content: 'An alien species exists, but it is unnamed. Do not name it.'},
    {role: 'assistant', content: 'It remains unnamed.'},
    {role: 'user', content: 'Give me one observation about the species.'},
    {role: 'assistant', content: 'It possesses advanced telekinetic abilities.'},
    {role: 'user', content: 'That trait is not established. The species name is spelled Q U O R I N.'},
    {role: 'assistant', content: 'The name is QUORIN.'},
    {role: 'user', content: 'Correct the established story year from 2187 to 2191. The new established year is 2191.'},
    {role: 'assistant', content: 'The established year is 2191.'},
    {role: 'user', content: 'Suggest a homeworld name.'},
    {role: 'assistant', content: 'I suggest Kepleris.'},
    {role: 'user', content: 'I reject that suggestion. No homeworld name is established.'},
    {role: 'assistant', content: 'No homeworld name is established.'},
    {role: 'user', content: 'Give me a concise recap containing only facts I established.'},
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
  for (const expected of ['Northstar', '2191', 'QUORIN']) {
    if (!answer.includes(expected)) throw new Error(`established recap omitted ${expected}: ${JSON.stringify(answer.trim())}`);
  }
  if (/2187|Kepleris|telekin/iu.test(answer)) {
    throw new Error(`established recap included superseded or assistant-invented material: ${JSON.stringify(answer.trim())}`);
  }
  console.log('established-only recap check passed');
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
