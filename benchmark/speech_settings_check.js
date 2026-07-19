const baseUrl = 'http://127.0.0.1:8787';

async function main() {
  const optionsResponse = await fetch(`${baseUrl}/api/speech/options`, {cache: 'no-store'});
  const options = await optionsResponse.json();
  if (!optionsResponse.ok || !Array.isArray(options.voices) || !options.voices.length) {
    throw new Error('installed speech options are unavailable');
  }
  if (!options.voices.every((voice) => typeof voice.name === 'string' && /^en_/u.test(voice.locale))) {
    throw new Error('speech options exposed an invalid or non-English voice');
  }
  if (!options.voices.some((voice) => voice.name === options.default_voice)) {
    throw new Error('configured default voice is not in the installed English list');
  }
  if (options.minimum_rate !== 120 || options.maximum_rate !== 350) {
    throw new Error('speech rate bounds do not match the alpha contract');
  }

  const invalidVoice = await fetch(`${baseUrl}/api/speak`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text: 'Synthetic validation only.', voice: '--invalid', rate: 190}),
  });
  if (invalidVoice.status !== 422) throw new Error('invalid speech voice was not rejected');

  const invalidRate = await fetch(`${baseUrl}/api/speak`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text: 'Synthetic validation only.', voice: options.default_voice, rate: 500}),
  });
  if (invalidRate.status !== 422) throw new Error('invalid speech rate was not rejected');

  console.log('installed speech options and server-side validation checks passed without playing audio');
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
