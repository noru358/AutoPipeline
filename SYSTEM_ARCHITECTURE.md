# TOON PRODUCTION SYSTEM ARCHITECTURE v1.0

## 1. Decision

AutoPipeline is the shared production system for `instatoon` and `jipbap`.
It owns repeatable execution, not either project's creative voice.

The system is organized into three levels:

1. **System level (what):** content families, products, tool ownership, cost policy, continuity policy.
2. **Workflow level (when):** the canonical production stages and their saved outputs.
3. **Method level (how):** project-specific research routes, voice examples, visual references, generation instructions and QC criteria.

Episode facts are data that use these levels. A meal, character, line or one-off
mistake must not become a shared system rule merely because it appeared once.

Machine-readable authority:

- `config/system_policy.json` — shared system and operating policy;
- `profiles/instatoon.json` — story/empathy project routing;
- `profiles/jipbap.json` — observation/sensory project routing;
- child repository documents referenced by each profile — creative authority.

## 2. Content and product boundary

The two initial content families are deliberately different.

| Project | Content family | Audience experience |
|---|---|---|
| instatoon | `STORY_EMPATHY` | Understand an event, relationship and emotional change |
| jipbap | `OBSERVATION_SENSORY` | Notice a meal, texture, action and food-state change |

Both initially produce an active 4:5 carousel and keep a 9:16 vertical-motion
product as planned. The planned product is not authorization to implement paid
TTS, generative video, publishing or full animation.

Shared code must not force story reversal, recurring cast, community voice or
recipe exposition across projects. Those choices belong to child authority.

## 3. Canonical workflow

The common stage IDs are stable routing names, not a demand for one AI agent or
one user approval per stage.

| Order | Stage | Required durable result |
|---:|---|---|
| 1 | `WORK_RESEARCH` | Directly inspected work observations with source and scope |
| 2 | `RADAR` | Candidate material, provenance and selection evidence |
| 3 | `EDITORIAL` | Intended audience experience and content structure |
| 4 | `STORYBOARD` | Frame roles, visual change and text/image layout plan |
| 5 | `ASSET_PRODUCTION` | Bound references and versioned generated/reused assets |
| 6 | `COMPOSITION` | Editable scene source and deterministic preview |
| 7 | `QC` | Defect location, owner, repair scope and version-bound result |
| 8 | `EXPORT` | Target-specific deliverables derived from the editable source |
| 9 | `RETROSPECTIVE` | Human time, retries, cost, recovery and response observations |

A runtime may combine adjacent ChatGPT-assisted stages in one user-triggered
session. It must still save the result needed to resume without relying on chat
memory.

## 4. Tool ownership

ChatGPT is preferred for research, editorial reasoning, drafts, image work when
available, and visual review when it has the actual media. The program owns
persistent state, actual asset identity, approval binding, editable text/UI and
layout, deterministic composition, targeted invalidation, resume and export.

ChatGPT subscription billing and API billing are different systems. Therefore:

- paid provider fallback is disabled;
- additional paid AI budget starts at KRW 0;
- subscription usage requires a user-triggered ChatGPT session;
- a usage limit suspends the job at its last durable result;
- external code must not treat the subscription as an unattended model API;
- unavailable direct artifact transfer is represented as an explicit import
  step until an integration is verified.

Existing paid-provider adapters may remain in child code for future controlled
use. They are not the default execution path and must not be invoked by a
subscription-limit fallback.

## 5. Rule promotion

Apply feedback at the narrowest correct scope:

1. Fix a one-off line, menu, prop or pose in the episode source.
2. Promote a repeated creative pattern to the child project's examples or method.
3. Promote a cross-project objective failure to shared program logic.
4. Promote a data-loss, stale-write, duplicate-execution or approval-identity
   defect to shared program logic immediately.

This is how the system preserves detail without growing a universal prompt that
must remember every past episode.

## 6. Context contamination and handoff

Context continuity is a top-level operating constraint. Stop the active creative
or implementation task when any configured contamination signal is observed.
Do not reconstruct certainty from conversation alone.

Before recommending a new session:

1. verify the current repository heads and dirty state;
2. save completed work and version-bound approvals;
3. record active decisions, blockers and discarded alternatives;
4. name exactly one next action;
5. state clearly that a new session is required because context confidence has
   fallen below the level needed for safe continuation.

The handoff fields in `config/system_policy.json` are mandatory. A new session
must re-read repository authority and validate the system contract before work.

## 7. Validation and change control

Run from the superproject root:

```bash
python -m pipeline.system_gate
python -m unittest discover -s pipeline -p 'test_*.py'
```

The system gate checks the zero-paid-fallback policy, continuity action,
canonical stage ordering, content-family coverage, profile references and
materialized creative authority files.

Change order:

1. update and verify the child creative authority when creative behavior changes;
2. update a parent profile only when routing or product definition changes;
3. update shared policy/code only for a genuine cross-project invariant;
4. verify child commits, then advance superproject submodule pointers.

## 8. Implemented artifact-bridge milestone

The first subscription-first artifact bridge is implemented in
`pipeline/artifact_bridge.py` and governed by `schemas/work_packet.schema.json`.
It can:

1. create a saved work packet for one selected stage;
2. supply the exact child authority and actual media required for that packet;
3. register a ChatGPT-produced result as a real asset with identity and hash;
4. reopen it in a new process and resume from the saved next action;
5. keep manual import visible if direct transfer is unavailable;
6. reject a stale revision or modified authority/artifact bytes.

The bridge itself does not invoke ChatGPT and direct artifact transfer remains
unverified. `ARTIFACT_BRIDGE.md` defines the current explicit-import workflow.

The next editor milestone follows the bridge: editable lettering/layout,
candidate replacement, undo/redo, save/reopen and separate-frame export.
