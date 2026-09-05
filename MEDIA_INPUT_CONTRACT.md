# MEDIA INPUT / RENDERER CAPABILITY CONTRACT v1.0

Purpose:
Provide one project-agnostic fail-closed contract for any generation stage that depends on images, audio, video, or other reference media.

The generic engine must not know project asset names such as REF_V2_D, CHAR_06, opening still, or voice pack.
Child projects declare requirements; renderer adapters declare capabilities; runtime evidence proves what was actually supplied.

## 1. Three separate facts

Never collapse these:

1. DECLARED — the child project says an input is required.
2. AVAILABLE — the source asset exists and is readable.
3. SUPPLIED — the renderer call actually received that asset as media input.

Only SUPPLIED satisfies a MUST_SUPPLY_MEDIA requirement.

Reading a file, summarizing it, hashing it, or mentioning its path in a prompt is not renderer conditioning.

## 2. Generic requirement model

Each generation job materializes media requirements with:

- requirement_id: stable job-local ID;
- role: semantic role such as style, character_identity, scene_anchor, first_frame, voice_identity, timing_audio, motion_reference, or another child-defined role;
- media_type: image | audio | video | other;
- source_id: repository-relative path, object-store ID, connector ID, or another stable identifier;
- conditioning: MUST_SUPPLY_MEDIA | AUTHORITY_ONLY_ALLOWED;
- required: boolean;
- expected_hash: optional integrity hash.

The engine treats role as opaque metadata. It must not encode child-specific filenames.

## 3. Renderer capability profile

Every renderer/provider adapter declares before job creation:

- renderer_id;
- supports_explicit_media_inputs: boolean;
- supported_media_types;
- max_media_inputs when known;
- supported_prompt_bindings;
- any provider-specific limitations.

Capability discovery happens before generation, not after a failed output.

## 4. Runtime supply evidence

For each actual render call, record supplied media evidence:

- requirement_id;
- source_id;
- media_type;
- actual supplied input handle when available;
- integrity hash when available.

A requirement is satisfied only when declaration, capability, and supplied evidence all agree.

## 5. Fail-closed authorization

Block the generation call when any required item fails one of these:

- source unavailable;
- renderer cannot accept its media type;
- MUST_SUPPLY_MEDIA but renderer lacks explicit media input support;
- required source is not present in supplied evidence;
- supplied source does not match the declared source;
- expected hash mismatches;
- provider media-count limit would be exceeded;
- prompt-binding mode is not allowed by the child job contract.

Do not downgrade MUST_SUPPLY_MEDIA to authority-only because of convenience, tool habit, credits, or connector limitations.

Capability mismatch means ROUTE TO ANOTHER RENDERER or BLOCK. It does not mean “generate once and QC afterward.”

## 6. Cross-project examples

Instatoon:
- style reference image → role=style, MUST_SUPPLY_MEDIA;
- recurring-character sheet → role=character_identity, MUST_SUPPLY_MEDIA;
- last-known-good repair image → role=repair_base, MUST_SUPPLY_MEDIA when the repair adapter needs it.

Talkshow:
- locked opening still → role=first_frame, MUST_SUPPLY_MEDIA;
- character master pack → role=character_identity, MUST_SUPPLY_MEDIA;
- voice reference → role=voice_identity, MUST_SUPPLY_MEDIA;
- whole-scene dialogue master → role=timing_audio, MUST_SUPPLY_MEDIA when used as timing/performance authority.

The generic engine does not special-case either project.

## 7. Ownership

AutoPipeline owns:
- the generic requirement schema;
- renderer capability schema;
- generic authorization algorithm;
- generic regression tests.

Child projects own:
- which inputs are required;
- their source IDs/paths/hashes;
- semantic role names;
- whether AUTHORITY_ONLY_ALLOWED is ever acceptable;
- project-specific creative/QC rules.

## 8. Migration rule

Existing child-specific guards may remain as adapters during transition, but:
- they must map child fields into this generic model;
- they may be stricter;
- they may not weaken MUST_SUPPLY_MEDIA;
- new provider adapters should implement the parent contract directly.

## 9. Definition of success

A clean runtime can answer, before generation:
- what media the job requires;
- which renderer can satisfy it;
- what exact media will be supplied;
- whether authorization passes;

without knowing the child project's asset naming conventions.
