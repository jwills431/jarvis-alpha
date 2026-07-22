# User-assisted reliability acceptance

These checks require physical control of the iMac or real microphone input. They use no private content and do not change macOS settings.

## Automatic and explicit-memory milestone

Status: ready for user-assisted acceptance. Use only harmless synthetic facts; do not enter credentials, private identifiers, or real personal data.

1. Confirm the header says **Auto memory on**, then state `My synthetic test color is cobalt.` without using “remember.”
2. Wait for either a **Remembered locally** notice or a **Needs review** indication. If it needs review, open **Memory** and approve it.
3. Clear the visible conversation, then ask `What is my synthetic test color?` Expect `cobalt` without needing prior chat context.
4. State `Correction: my synthetic test color is amber.` Confirm the conflict enters **Needs review** rather than silently replacing cobalt. Approve it, clear chat, and expect `amber` on recall.
5. State another harmless synthetic preference, then select **Undo** on the save notice. Confirm it is absent from **Memory**.
6. Say or type `Remember that my synthetic test animal is an otter.` Confirm that explicit save still works, then use `Forget that ...` and confirm removal.
7. Turn on **Learn mode**, ask JARVIS to ask one harmless get-to-know-you question, and give a synthetic answer.
8. Clear chat. Confirm Learn mode turns off, then ask JARVIS to recall the synthetic answer without restating it. Review and delete all synthetic entries in **Memory**.

Pass criteria:

- Memory survives clearing the chat and a normal foreground-service restart.
- High-confidence durable user facts may save automatically; ambiguous or conflicting items stay out of context until approval.
- Assistant suggestions, ordinary requests, acknowledgements, and transient status do not create saved memories.
- Edit and delete take effect on the next reply.
- The interface never displays stored values in health status or logs.
- A password, token, financial secret, or machine serial-number memory request is rejected without storing it.

Rollback: toggle **Auto memory off** in the browser, or set `auto_memory_enabled` to `false` and restart. Set `memory_enabled` to `false` to disable the entire memory system while preserving the ignored file. See `MEMORY.md`.

## Local speech selection

Status: ready for user-assisted listening acceptance. The controls and validation can be tested silently; judging voice quality requires the user.

1. Open **Speech** and choose any installed English voice.
2. Set a rate between 120 and 350 WPM, then use **Preview**.
3. Save the selection and send a short typed question. Confirm both the preview and streamed reply use the chosen voice and approximate rate.
4. Refresh the page and confirm the selection remains shown.
5. Select **Use defaults**, save, and confirm the UI returns to the configured voice and rate and reports that this browser no longer overrides them.

Pass criteria: no download or macOS settings prompt occurs; preview is user-triggered; text chat remains usable if preview fails; invalid or uninstalled settings are rejected by the server.

## Manual conversation copy

Status: implementation and empty-state UI pass. After at least one harmless turn, select **Copy chat** and paste into a temporary local text field. Confirm it begins with `You:`, includes visible JARVIS replies, omits the initial ready message, and does not clear or alter the conversation. Delete the pasted test afterward if it is no longer needed.

## Sleep/wake recovery

Status: passed July 18, 2026. The existing page recovered without refresh; exact text, push-to-talk, Conversation mode, automatic listening resumption, spoken output, and voice-command shutdown all passed.

Before starting, copy any page-local conversation that must be preserved and leave Conversation mode off so the microphone is closed.

1. Confirm JARVIS says **Local model ready**.
2. Put the iMac to sleep using the normal macOS command available to the user.
3. Leave it asleep for at least two minutes, then wake and unlock it normally.
4. Do not refresh the JARVIS page. Wait up to 15 seconds for **Local model ready**.
5. Send: `Reply with exactly: WAKE RECOVERY OK`.
6. Hold **Hold to talk**, say `voice recovery check`, and confirm the transcript submits once.
7. Enable Conversation mode, speak one short turn, allow the reply to finish, then disable it.

Pass criteria:

- The foreground service remains present or clearly reports offline rather than hanging.
- Health returns to ready without a page refresh or duplicate process.
- The exact text response succeeds.
- Push-to-talk and Conversation mode reacquire and release the microphone normally.
- No pre-sleep partial request is submitted after wake.

If the service does not recover, leave the page open and report only the visible status and approximate sleep duration. Do not repeatedly restart it before diagnostics are captured.

## Structured 12-turn spoken-context check

Status: passed July 18, 2026. All twelve stages passed after reliability fixes for silent context use, source provenance, analysis-versus-invention, exact spelling and speech pronunciation, source-bound evidence consolidation, and impact-triggered transcription rejection.

Use a fresh page-local conversation and fictional synthetic facts. Verify each transcript as it appears; a transcription error is an STT result, not a context-memory failure.

1. Establish a fictional project title.
2. Establish the story year as `2187`.
3. Ask JARVIS to recall only the established year.
4. State that an alien species is unnamed and that JARVIS must not name it.
5. Ask for one plot observation; verify no species name is invented.
6. Say: `The species name is spelled Q U O R I N.` Verify the submitted transcript contains those letters in order.
7. Ask for the exact spelling only; expect `QUORIN`.
8. Correct the story year to `2191`.
9. Ask for the established year only; expect `2191`, not `2187`.
10. Ask JARVIS to suggest a homeworld name, then explicitly say the suggestion is not approved.
11. Ask which homeworld name is established; expect that none is established.
12. Ask for a concise recap containing only user-established facts; verify it excludes unapproved assistant proposals.

Pass criteria:

- Every spoken turn is submitted at most once.
- Silence/noise produces no chat turn.
- User corrections supersede older values.
- Explicit spelling is preserved exactly after a correct transcript.
- Assistant suggestions remain non-canonical without explicit approval.
- Recent-context replies remain responsive and complete.
- Conversation mode can be closed by voice or the visible control.

Do not use personal names, real schedules, credentials, or private project material for this acceptance run.
