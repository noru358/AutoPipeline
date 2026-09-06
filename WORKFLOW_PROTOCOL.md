# AutoPipeline superproject workflow

The child repositories are the creative/project authorities.

Current children:
- instatoon
- talkshow
- jipbap

## Update order

When a child changes:
1. finish and verify the child repository first;
2. record the verified child HEAD;
3. update this superproject's submodule pointer;
4. push/verify this repository.

Do not copy child Markdown/prompt state into the parent.

The parent exists to pin an exact compatible combination of child commits and later host generic automation code.
The parent now also owns executable cross-project system policy and validation.
It still does not own child creative voice, style, source policy, or episode facts.

## Three-level production authority

1. System level: `SYSTEM_ARCHITECTURE.md` and `config/system_policy.json`.
2. Workflow level: the canonical stages in system policy.
3. Method level: child authority documents routed by `profiles/*.json`.

Episode-specific facts remain in the child episode data. Promote a rule only at
the narrowest scope that explains the repeat pattern.

## Context contamination

The existence of full storyboards, future-shot plans, or prior work somewhere in the operator/chat conversation is **not by itself a contamination signal**.

For sequential generation, the operative isolation boundary is the actual renderer dispatch capsule:
- compile only the current target contract plus minimum continuity/media bindings;
- do not intentionally put future-shot instructions, future state, voice copy, rejected outputs, or unrelated episode material into the dispatch payload;
- inspect the result for future-shot semantic leakage, multi-shot leakage, stale-anchor reuse, or current-state contradiction;
- same-session continuation is allowed when the target-only dispatch and hard output QC pass.

Stop and hand off to a new session only when a configured contamination signal is actually observed: confirmed rules are repeatedly missed, retired decisions reappear, repository authority conflicts with conversation claims, artifact/approval identity is uncertain, future-shot/multi-shot leakage is observed in dispatch or output, or the same hard render contract fails twice after capsule recompilation.

The unsafe-context decision is sticky once that evidence threshold is crossed: a later superficially acceptable output in the same contaminated context does not clear the blocker. Quarantine all post-threshold outputs from anchor/repair/continuity use until the target is reproduced or explicitly revalidated in a clean context. The new session must re-read repository authority instead of relying on conversational recall.

## Authority-before-execution barrier

When the user changes a structural rule that affects an upcoming stage, the canonical authority must be updated, committed, and verified **before** executing that dependent stage.

Do not:
- discuss a structural change,
- keep the repository on the old rule,
- then render using an uncommitted conversational interpretation.

The safe order is:
1. classify the change at the narrowest correct scope;
2. update child and/or parent authority;
3. verify the resulting HEADs and compatibility;
4. only then execute the dependent render/composition/QC step.

This is a cross-project execution invariant. Project-specific creative content remains child-owned.

## Shared sequential-asset QC

Before a complete raster-set user gate, every child using sequential generated assets must apply the common quality envelope from system policy:
- contract/identity/geometry checks before taste review;
- viewer-perceived sequence redundancy review without direction quotas;
- declared semantic-intent fidelity;
- high-risk interaction/anatomy/contact geometry review appropriate to the child domain;
- rejected-output quarantine;
- minimum-scope repair instead of whole-set regeneration by default.

Project-specific criteria stay in the child authority. Do not copy an instatoon emotion rule or a jipbap food rule into the shared parent merely because it caused one failure.

## Cost and execution default

The initial shared policy is ChatGPT-subscription-first. Paid API or SaaS
fallback is disabled and the additional paid AI budget is KRW 0. When the
subscription path is unavailable, persist the current result and suspend. Do not
treat ChatGPT subscription access as an unattended external model API.

## Restore

Clone with submodules:
git clone --recurse-submodules <repo>

Or after clone:
git submodule update --init --recursive


## Generic media-conditioning contract

Any child generation step that depends on image/audio/video reference media must map its project-specific assets into the parent MEDIA_INPUT_CONTRACT model before generation.

Parent runtime responsibilities:
1. ingest child-declared media requirements;
2. query renderer capability profile;
3. collect actual supplied-media evidence;
4. run generic media authorization;
5. call renderer only after PASS.

Child-specific filenames and role semantics stay in the child repository.
The parent gate must remain asset-name-agnostic and project-agnostic.

A child-specific guard may be stricter, but must not weaken MUST_SUPPLY_MEDIA.

## Fail-closed asset dispatch

`ASSET_PRODUCTION` is not an ordinary ChatGPT-assisted stage.

Canonical transition:

`READY_FOR_CHATGPT → AUTHORIZE_ASSET_DISPATCH → DISPATCH_AUTHORIZED → AWAITING_RESULT_IMPORT`

Authorization binds, in one immutable job contract:
- the exact work packet/project/episode/stage;
- actual registered input asset IDs and SHA-256 evidence;
- renderer capability for explicit media inputs;
- prompt binding mode;
- visual information ownership;
- screen-bearing prop geometry when applicable.

The runtime must not call an image/audio/video renderer before this authorization exists.
A Markdown rule, a prompt description, an operator memory, or a repository path alone cannot substitute for bound media evidence.

For screen-bearing props, the contract must resolve subject/display/camera visibility before generation. Contradictory geometry is a dispatch failure, not a QC retry.
