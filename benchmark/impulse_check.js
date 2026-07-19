const endpoint = 'http://127.0.0.1:8787/api/transcribe';

function impactWav() {
  const frames = 16000;
  const buffer = new ArrayBuffer(44 + frames * 2);
  const view = new DataView(buffer);
  const writeText = (offset, value) => [...value].forEach((character, index) => view.setUint8(offset + index, character.charCodeAt(0)));
  writeText(0, 'RIFF'); view.setUint32(4, 36 + frames * 2, true); writeText(8, 'WAVE'); writeText(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  writeText(36, 'data'); view.setUint32(40, frames * 2, true);
  const levels = [12000, 8000, 5000, 3000, 1800, 900, 400, 200];
  const start = frames / 2;
  for (let windowIndex = 0; windowIndex < levels.length; windowIndex++) {
    const offset = start + windowIndex * 320;
    for (let sample = offset; sample < offset + 320; sample++) {
      view.setInt16(44 + sample * 2, sample % 2 ? -levels[windowIndex] : levels[windowIndex], true);
    }
  }
  return buffer;
}

async function main() {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {'Content-Type': 'audio/wav', 'X-JARVIS-Capture': 'conversation'},
    body: impactWav(),
  });
  const body = await response.json();
  if (response.status !== 422 || body.error !== 'no_speech_detected') {
    throw new Error(`impact rejection failed: HTTP ${response.status} ${JSON.stringify(body)}`);
  }
  console.log('impact-noise rejection check passed');
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
