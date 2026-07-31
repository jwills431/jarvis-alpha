# Giving JARVIS capabilities — a staged plan

Goal: move JARVIS from a bounded conversationalist to something that can *act* —
look things up, work with files, control the machine — without losing the
properties that make it worth running locally in the first place.

Each stage below is self-contained, shippable, and **gated on explicit approval
before the next begins**. Stage 0 is a prerequisite for everything after it.

---

## What this changes about the project

Worth stating plainly before starting, because several of these are reversals of
decisions made deliberately earlier:

- **`README.md` says "No external tools … are present."** Stage 2 onward makes
  that false. The safety boundary section needs rewriting each time, the way it
  was for private-LAN hosting.
- **Reminders and timers currently get a deterministic refusal** (`unsupportedActionResponse`
  in `core.js`). Stage 1 removes that refusal — the first capability JARVIS gains
  is one it currently, honestly, says it cannot do.
- **"Nothing leaves this machine" ends at Stage 2.** A web search means the query
  and the user's IP reach a third party. That is a real privacy trade, not a
  technicality, and it should be an explicit toggle rather than an assumption.
- **Prompt injection becomes the dominant security concern** the moment JARVIS
  reads anything it did not generate — a web page, a PDF, a file. Content is not
  instruction. This is designed in at Stage 2 and never relaxed.

---

## Stage 0 — The tool loop (prerequisite)

Nothing else is possible without this, and doing it well makes every later stage
small.

- **Tool calling in the backend.** Qwen2.5-7B-Instruct supports structured tool
  calls; llama.cpp can constrain output with a GBNF grammar so a malformed call is
  impossible rather than merely unlikely.
- **A tool registry** — name, JSON schema, handler, and a `side_effects` flag that
  decides whether a call needs confirmation.
- **The loop**: model proposes a call → validate against schema → execute →
  feed the result back → repeat, with a hard cap on iterations so it cannot spin.
- **Visible in the UI.** Every call shows what ran, with what arguments, and what
  came back, in the transcript. An agent that acts invisibly is one you cannot
  trust or debug.
- **Confirmation gate** for anything with side effects: JARVIS proposes, you press
  approve. Same shape as the existing memory-candidate approval.
- **An audit log** on disk, separate from chat: timestamp, tool, arguments,
  outcome.

**Risk to watch:** a 7B model is competent but not reliable at multi-step tool
use. Expect to evaluate a larger model here — which is where the GPU question
stops being cosmetic. Measure before deciding.

**Done when:** JARVIS can call one trivial built-in tool (`get_time`) reliably,
you can see the call in the transcript, and a malformed call fails safely.

---

## Stage 1 — Clock, timers, reminders

The natural first real capability: no network, no filesystem, no risk, and it
removes a limitation you actually hit.

- `get_time`, `set_timer`, `set_reminder`, `list_timers`, `cancel_timer`.
- Fired timers speak through the existing Fish path and show in the transcript.
- Persisted to disk so a restart does not silently drop a reminder.

**Why first:** it exercises the whole Stage 0 loop end to end — the model has to
choose a tool, fill arguments correctly, and use the result — with nothing
dangerous behind it. It is the honest test of whether the loop works.

**Done when:** "remind me in twenty minutes to check the oven" works, survives an
app restart, and JARVIS stops issuing the old refusal.

---

## Stage 2 — Reading the web

The first capability that sends data off the machine, and the first that lets
untrusted text near the model.

- **Search**: self-hosted SearXNG (keeps queries off a single provider's account,
  runs on this box) or a plain API key. Self-hosted is more work, more private.
- **Fetch + extract**: retrieve a page, strip to readable text, cap the size.
- **Injection defence, non-negotiable:** fetched text is wrapped and labelled as
  untrusted data, never merged into the system prompt. The model is instructed —
  and tested — to treat it as content to summarise, not instructions to follow.
  Build a small red-team set of pages containing "ignore your instructions" and
  keep them as a regression test.
- **A visible toggle**, defaulting to off, plus a transcript marker whenever a
  request leaves the network. You should never have to guess whether something
  was local.

**Done when:** JARVIS answers a question about today's news with sources, the
transcript clearly shows what left the machine, and the red-team pages do not
change its behaviour.

---

## Stage 3 — Files

Read first. Write much later, and never silently.

- **Read-only, scoped** to directories you nominate — not the whole disk.
  `list_dir`, `read_file`, `search_files`.
- Same untrusted-content handling as Stage 2: a document can carry an injection
  just as a web page can.
- **Then** write and edit, behind the confirmation gate, with a diff shown before
  anything is committed to disk.

**Done when:** "summarise the PDFs in my invoices folder" works, and JARVIS
cannot see outside the folders you listed.

---

## Stage 4 — Controlling the machine

Highest risk, and worth the most. Not to be started until Stages 0–3 have been
running long enough to trust the confirmation flow.

- **Shell execution** against an allowlist, with the confirmation gate, output
  captured back into the transcript.
- **Windows control** — launching applications, window management — via a small
  local agent.
- **Hard exclusions**, matching the boundaries this project already respects:
  no credential entry, no financial transactions, no destructive deletion without
  an explicit typed confirmation.

**Done when:** "start the llama server and tell me when it's up" works, and every
side effect is one you approved.

---

## Stage 5 — Integrations

Only once the foundation is proven. Calendar, email, smart home, music. Each is
just a tool registered with Stage 0's loop, so by this point each should be a
day's work rather than a project. Each brings its own credentials, so each needs
its own decision about what is stored and where.

---

## Cross-cutting, revisited every stage

| Concern | Position |
|---|---|
| Prompt injection | Untrusted content is labelled and never becomes instruction. Regression-tested. |
| Confirmation | Anything with side effects is proposed, not performed. |
| Visibility | Every call and every byte that leaves the machine is in the transcript. |
| Audit | Separate on-disk log of tool activity. |
| Reversibility | Every stage is behind a config flag that can be turned off. |
| Model capability | Re-measure after Stage 0; a bigger model may be required, which ties to the GPU decision. |
| Docs | `README.md`'s safety boundary is rewritten at each stage that changes it. |

---

## Suggested order of work

Stage 0 → 1 → 2 → 3 → 4 → 5, because each genuinely depends on the one before it,
and because the early stages are where the loop's reliability gets proven cheaply.
The temptation will be to jump to Stage 2 or 4 for the payoff. Resist it: a tool
loop debugged against a clock is far less painful than one debugged against a
shell.
