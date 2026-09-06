# ASSET_COMPOSITION_CONTRACT.md

Version: 1.0
Updated: 2026-09-07
Scope: shared toon-production runtime

## 1. Shared rendering boundary

For toon-family projects, the program must distinguish **asset authoring** from **final scene rendering**.

Default architecture:

`STORYBOARD → ASSET_RESOLUTION → ASSET_GAP_AUTHORING → APPROVED ASSET SET → DETERMINISTIC COMPOSITION → EDITABLE TEXT/UI → QC → EXPORT`

A stochastic image model may create or repair a visual asset. It is not, by default, the owner of the complete final frame.

This contract does not require every child project to use the same degree of modularity. It requires the final renderer boundary to be explicit and project-configurable.

## 2. Shared invariants

1. **Approved pixels are not re-sampled without cause.**
   A new dialogue line, crop or neighboring beat must not force regeneration of an already-approved identity/background/prop asset.

2. **Missing capability is an ASSET_GAP.**
   If the storyboard needs a pose, expression, prop, food state or location element absent from the approved library, the runtime routes that missing element to asset authoring before final composition.

3. **Only approved/hash-bound assets compose.**
   Final composition fails closed on missing, rejected, retired, stale or hash-mismatched assets.

4. **Final layout is deterministic.**
   Asset IDs, source hashes, layer order, transforms, crop/mask and text/UI plans are durable scene data.

5. **Text/UI stays editable.**
   Meaning-bearing lettering and deterministic interface state are not baked into generative visual assets by default.

6. **Regeneration scope is minimal.**
   A bad asset invalidates that asset and dependent scenes, not unrelated approved scenes.

7. **Generation is retained as an exception lane.**
   Full-frame generation may be used when a child declares that composition is materially inadequate for a shot. The exception must be explicit, bounded and non-promoting by default.

## 3. Asset scopes

The shared runtime recognizes these generic scopes:
- `PROJECT_CANONICAL`
- `PROJECT_REUSABLE`
- `EPISODE_LOCAL`
- `EXCEPTION_OUTPUT`

Children own domain-specific asset categories such as CHARACTER_POSE, FOOD_STATE or LOCATION_PLATE.

Promotion from episode-local to reusable/canonical is an approval event, not an automatic side effect of successful generation.

## 4. Project routing

### instatoon

Default: **COMPOSITION_FIRST_STRICT**

- recurring character identity should be preserved by reusing approved assets;
- backgrounds/props/extras should resolve from reusable or episode-local libraries;
- fresh generation should normally produce the missing asset only;
- full-frame generation is exceptional.

### jipbap

Default: **COMPOSITION_FIRST_HYBRID_FOOD**

- person/body identity and reusable environment components should be asset-composed when practical;
- menu-specific FOOD/FOOD_STATE assets may be authored per episode because food state is core semantic content;
- hand/utensil/contact assets may be episode-local when needed;
- final lettering/cover composition remains deterministic;
- full-frame generation remains an explicit exception, not the automatic default.

The hybrid policy must not turn into “regenerate the person with the meal every shot.” Food variability does not reopen accepted person identity.

## 5. Relation to ASSET_PRODUCTION and COMPOSITION stages

`ASSET_PRODUCTION` means:
- resolve the approved registry;
- author only missing required assets;
- bind actual reference media;
- QC and register immutable accepted bytes.

`COMPOSITION` means:
- build editable scene specifications from registered asset IDs;
- apply deterministic placement/transforms/layering;
- add editable text/UI in the project-owned composition layer;
- export previews/finals without invoking a stochastic renderer unless an exception is explicitly declared.

## 6. Exception record

A full-frame stochastic exception must persist:
- project/episode/scene ID;
- reason composition was insufficient;
- bound authorities/media;
- output hash;
- approval scope;
- retry/cost cap;
- promotion policy, default `EPISODE_LOCAL_ONLY`.

A rejected exception output is quarantined exactly like any rejected generated asset.

## 7. Migration rule

Existing child generation prompts, reference contracts and image QC are not discarded. They move down one layer and govern:
- asset authoring;
- asset repair;
- full-frame exception shots.

Any old document that says every final frame should be generated independently is superseded by this contract once the child has opted into an asset-composition profile.
