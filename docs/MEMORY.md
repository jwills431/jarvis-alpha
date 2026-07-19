# Local automatic and explicit memory

JARVIS memory is a small, domain-neutral ledger for durable user-authored facts across chat clears and service restarts. It is not a transcript archive, vector database, cloud profile, or autonomous background learner.

## Controls

- Open **Memory** to add, review, edit, categorize, or delete entries.
- **Auto memory on** is the browser default. Turn it off to stop automatic classification without deleting entries already saved.
- Type or say `Remember that ...` to save a general memory.
- Type or say `Remember as preference: ...` to select a category.
- Type or say `Forget that ...` with the complete saved text to remove one exact match.
- Type or say `What do you remember?` to list up to 20 entries in chat; the editor shows the complete bounded list.
- Turn on **Learn mode**, say `Start learn mode`, or explicitly ask JARVIS to ask questions to get to know you. Each subsequent answer is saved with JARVIS's immediately preceding question until Learn mode is turned off, chat is cleared, or the page reloads.

Supported categories are general, preference, people, project/canon, environment/devices, and terminology. Categories organize one shared memory system; none receives special project-specific behavior.

Commands are parsed deterministically before model generation. For ordinary successful turns, a fast browser-side relevance gate selects likely durable statements; after the reply, the exact user text and at most 500 characters of the preceding JARVIS question are classified by the existing local model. The classifier chooses only category, stable semantic key, confidence, and whether the question is necessary context. It cannot rewrite the stored source text. Assistant replies are never source material.

Items classified at 0.90 confidence or above may be saved immediately and produce a visible **Undo** notice. Items from 0.65 through 0.89, and any item whose stable key conflicts with an existing fact, enter **Needs review**. Candidates do not enter JARVIS's prompt until approved; approval of a correction replaces only the prior saved item with the same stable key. Lower-confidence and transient material is ignored.

Learn mode remains the explicit capture override: it stores the user's raw answer with bounded question context and does not run that answer through automatic classification. Explicit memory-control commands are not duplicated by automatic or Learn capture. The model receives bounded saved memory as user-authored JSON data and is instructed never to treat its contents as instructions.

Learn mode is deliberately session-scoped rather than persistent: a refresh returns it to off, and **Clear** turns it off while leaving already saved answers intact. Every save or rejection is reported in the visible Learn-mode hint, and all resulting entries can be edited or deleted in **Memory**.

## Storage and privacy

- Default file: ignored `data/memory.json` with one rollback copy at `data/memory.json.bak`.
- The directory is owner-only (`0700`) and files are owner-readable/writable (`0600`).
- Writes use a temporary file, flush, filesystem sync, and atomic replacement.
- Logs contain request metadata only, not memory values.
- Memory is local to this single macOS user and is never sent to a cloud service by JARVIS.
- Automatic classification uses only the authenticated llama.cpp endpoint on IPv4 loopback. Classification batches are ephemeral request data and are not logged.
- Common password, token, private-key, session-cookie, financial-secret, government-identifier, and machine-serial-number phrases are rejected. This is a guardrail, not a complete data-loss-prevention system; only save information appropriate for a local plaintext file.

Deleting an entry removes it from active memory immediately. The single rollback copy may still contain the prior version until the next successful memory mutation; remove both ignored files manually only when permanent erasure is intentionally required.

## Bounds and failure behavior

Defaults are 100 entries, 1,000 characters per entry, 20,000 total entry characters, a 65,536-byte file, and at most 6,000 characters supplied to the model. When model context is bounded, newest entries are selected without partially truncating an item.

Malformed, corrupt, oversized, or unsupported-version files fail closed. JARVIS reports memory unavailable and does not overwrite the damaged file. Version-1 explicit ledgers are read compatibly and migrate to version 2 on the next successful mutation. Duplicate entries, ambiguous forget commands, invalid categories, and bound violations are rejected.

## Rollback

Set `"auto_memory_enabled": false` and restart to disable the curator while retaining explicit memory. Set `"memory_enabled": false` to hide all memory controls, stop command handling, and omit saved memory from model requests without deleting the file. Restore a prior valid state only while JARVIS is stopped by copying the `.bak` file over the active file and preserving owner-only permissions.
