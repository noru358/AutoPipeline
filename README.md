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
- `ASSET_COMPOSITION_CONTRACT.md`
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

## Rendering architecture ownership

The parent provides reusable execution methods; **each child chooses its canonical render architecture**.

- `instatoon` may opt into the asset-composition boundary where its child authority says so.
- `jipbap` V1 explicitly uses **SIX_PANEL_BOARD_FIRST**: one text-free six-panel board is generated jointly, then extraction / 4:5 page assembly / cover / lettering are deterministic.
- `ASSET_COMPOSITION_CONTRACT.md` applies only to children or stages that explicitly opt into it. It is not a cross-project creative default.

Shared compositor remains available for deterministic post-processing when a child uses it:

```bash
python -m pipeline.compositor \
  --project-root instatoon \
  --registry assets/production/registry.json \
  --scene instatoon/episodes/E001/composition/slide_01.json \
  --output instatoon/episodes/E001/renders/slide_01_art.png
```

For jipbap V1, do not interpret the compositor as permission to rebuild BODY art from PERSON/FOOD part assets. It may be used only for the deterministic presentation shell declared by `jipbap/JIPBAP_V1_SPEC.md`.

### Deterministic lettering

Meaning-bearing copy remains editable source data. `pipeline/lettering.py` renders a
versioned JSON lettering plan into a deterministic PNG preview and hash receipt.

- `PIL_DEFAULT` is allowed only for `CALIBRATION_PLACEHOLDER` plans.
- Production plans must bind a project font file by path and SHA-256.
- Base artwork, when supplied, is also SHA-256 verified before lettering.
- Text line breaks and positions are explicit plan data rather than model-generated pixels.

Schema: `schemas/lettering_plan.schema.json`.

## Durable artifact bridge

`pipeline/artifact_bridge.py` is the first executable subscription-first runtime layer.
It does not call a model API. It creates a stage work packet, snapshots the exact
creative authority used by that stage, copies actual input/result bytes into the
packet package, records SHA-256 identity, binds explicit user approval to one
result hash, and verifies all of it again before resume.

The runtime packet format is `schemas/work_packet.schema.json` (v1.1). A packet
is explicitly `PROJECT`-scoped or `EPISODE`-scoped, so research and channel
design are not forced into a fake episode. Generated workspaces are local runtime
data and are ignored by Git.

Example:

```bash
# Project-level work such as channel/work research does not need a fake episode ID.
python -m pipeline.artifact_bridge init \
  --profile profiles/instatoon.json \
  --scope project \
  --stage WORK_RESEARCH \
  --packet workspaces/instatoon/PROJECT/WORK_RESEARCH/packet.json

# Episode-level production binds the packet to a real episode.
python -m pipeline.artifact_bridge init \
  --profile profiles/instatoon.json \
  --scope episode \
  --episode E001 \
  --stage ASSET_PRODUCTION \
  --packet workspaces/instatoon/E001/ASSET_PRODUCTION/packet.json

python -m pipeline.artifact_bridge add-input \
  --packet workspaces/instatoon/E001/ASSET_PRODUCTION/packet.json \
  --file /path/to/reference.png \
  --role style_reference \
  --media-type image

python -m pipeline.artifact_bridge dispatched \
  --packet workspaces/instatoon/E001/ASSET_PRODUCTION/packet.json

python -m pipeline.artifact_bridge add-result \
  --packet workspaces/instatoon/E001/ASSET_PRODUCTION/packet.json \
  --file /path/to/approved-character-pose.png \
  --role character_pose \
  --media-type image

python -m pipeline.artifact_bridge approve \
  --packet workspaces/instatoon/E001/ASSET_PRODUCTION/packet.json \
  --asset-id result:character_pose:<hash-prefix>

python -m pipeline.artifact_bridge verify \
  --packet workspaces/instatoon/E001/ASSET_PRODUCTION/packet.json
```

An approved packet is locked against replacement result registration. Resume
fails closed if registered bytes or the snapshotted creative authority changed.
Direct ChatGPT-to-runtime artifact transfer remains an integration to verify;
until then the packet explicitly records manual import rather than pretending an
unattended subscription API exists.
