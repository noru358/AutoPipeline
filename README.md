# AutoPipeline

Parent superproject for reusable content-production automation.

Child projects remain independent Git repositories and creative authorities.

Current children:
- instatoon -> noru358/instatoon
- talkshow -> noru358/talkshow

Use Git submodules so this repository records the exact child commit combination without copying child history.

Clone:
git clone --recurse-submodules <repo>

Restore:
git submodule update --init --recursive


## Generic generation preflight

Cross-project media-conditioned generation is governed by:
- MEDIA_INPUT_CONTRACT.md
- schemas/media_job.schema.json
- pipeline/media_gate.py

Child projects declare requirements; renderer adapters declare capabilities; the generic gate authorizes only when required media is actually supplied.
