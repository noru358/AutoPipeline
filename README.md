# AutoPipeline

Parent superproject for reusable content-production automation.

Child projects remain independent Git repositories and creative authorities.

Current children:
- instatoon -> noru358/instatoon
- talkshow -> noru358/talkshow
- jipbap -> noru358/jipbap

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

## Toon production system

The shared subscription-first architecture for instatoon and jipbap is governed by:

- `SYSTEM_ARCHITECTURE.md`
- `config/system_policy.json`
- `profiles/instatoon.json`
- `profiles/jipbap.json`
- `schemas/system_policy.schema.json`
- `schemas/project_profile.schema.json`
- `pipeline/system_gate.py`

Validate the system contract and all current Python gates:

```bash
python -m pipeline.system_gate
python -m unittest discover -s pipeline -p 'test_*.py'
```

The initial policy uses user-triggered ChatGPT subscription work, sets additional paid AI budget to KRW 0, disables paid fallback, and requires suspend/resume when subscription usage is unavailable.
