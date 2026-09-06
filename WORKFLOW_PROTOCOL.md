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

If confirmed rules are repeatedly missed, retired decisions reappear, repository
authority conflicts with conversation claims, or artifact/approval identity is
uncertain, stop. Save the mandatory handoff fields declared in system policy and
recommend continuing in a new session. The new session must re-read repository
authority instead of relying on conversational recall.

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
