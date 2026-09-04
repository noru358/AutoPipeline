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
