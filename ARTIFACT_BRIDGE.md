# SUBSCRIPTION ARTIFACT BRIDGE v1.0

## Purpose

This bridge makes user-triggered ChatGPT work resumable without pretending that
a ChatGPT subscription is an unattended API. It does not call a model.

It provides four guarantees:

1. the applicable child creative authority is snapshotted by path and SHA-256;
2. imported output is copied into the packet and bound to its SHA-256;
3. every write uses an expected revision so a stale session cannot overwrite a
   newer packet;
4. resume fails when authority or registered artifact bytes changed.

`MANUAL_IMPORT` is the honest initial transfer mode. Use
`DIRECT_INTEGRATION` only after the exact ChatGPT environment and asset transfer
path have been verified.

## Create a work packet

Run from the AutoPipeline root. Keep live runs outside Git, for example under
`.autopipeline-runs/`.

```bash
python -m pipeline.artifact_bridge create \
  --packet .autopipeline-runs/instatoon-E002-storyboard/packet.json \
  --project instatoon \
  --episode E002 \
  --stage STORYBOARD \
  --input EPISODE_PLAN=/absolute/path/to/episode-plan.json \
  --input SOURCE_PACK=/absolute/path/to/source-pack.md \
  --next-action "Ask ChatGPT to draft the storyboard from this packet."
```

The packet copies each explicit input into its own `inputs/` directory and
records its role, hash and size. It also records the parent and child commits,
stage-specific authority hashes, execution/transfer mode and the next action.
Do not rely on an original path remaining available in the next session.

## Register an actual ChatGPT result

Export or download the result from the active ChatGPT session, then register the
real file. Use the packet revision printed by the previous command.

```bash
python -m pipeline.artifact_bridge register \
  --packet .autopipeline-runs/instatoon-E002-storyboard/packet.json \
  --file /absolute/path/to/result.png \
  --role TEXT_FREE_RASTER \
  --expected-revision 1 \
  --next-action "Review the registered image against the storyboard."
```

Registration copies the bytes into the packet's `artifacts/` directory. A path,
filename or conversational statement alone is not an artifact.

## Suspend and resume

```bash
python -m pipeline.artifact_bridge suspend \
  --packet .autopipeline-runs/instatoon-E002-storyboard/packet.json \
  --reason "ChatGPT subscription limit reached" \
  --next-action "Continue from the saved storyboard result." \
  --expected-revision 2

python -m pipeline.artifact_bridge resume \
  --packet .autopipeline-runs/instatoon-E002-storyboard/packet.json \
  --expected-revision 3
```

Resume verifies every authority and artifact hash before changing state. It
returns `AWAITING_CHATGPT` when no result exists and `RESULT_REGISTERED` when a
valid result is already stored.

## Verify without changing state

```bash
python -m pipeline.artifact_bridge verify \
  --packet .autopipeline-runs/instatoon-E002-storyboard/packet.json
```

Work packets are operational state, not Git source. Archive or sync their entire
directory—including `packet.json` and `artifacts/`—through an approved storage
path when cross-device recovery is required.
