# AutoPipeline superproject workflow

The child repositories are the creative/project authorities.

Current children:
- instatoon
- talkshow

## Update order

When a child changes:
1. finish and verify the child repository first;
2. record the verified child HEAD;
3. update this superproject's submodule pointer;
4. push/verify this repository.

Do not copy child Markdown/prompt state into the parent.

The parent exists to pin an exact compatible combination of child commits and later host generic automation code.

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
