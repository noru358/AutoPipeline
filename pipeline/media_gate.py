#!/usr/bin/env python3
"""Project-agnostic media-conditioning authorization gate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


class GateError(RuntimeError):
    pass


def _require(cond: bool, msg: str):
    if not cond:
        raise GateError(msg)


def load_job(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateError(f"missing job file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GateError(f"invalid JSON: {path}: {exc}") from exc


VISUAL_INFORMATION_OWNERS = {
    "CHARACTER_REACTION",
    "SCREEN_INFORMATION",
    "PHYSICAL_ACTION",
    "MIXED_WITH_DECLARED_PRIORITY",
}
SUBJECT_SCREEN_RELATIONS = {
    "LOOKING_AT_SCREEN",
    "HOLDING_NOT_LOOKING",
    "NOT_APPLICABLE",
}
CAMERA_SCREEN_RELATIONS = {
    "FRONT_OF_SUBJECT",
    "OVER_SHOULDER",
    "SUBJECT_POV",
    "SIDE_OBLIQUE",
    "REAR_OF_SUBJECT",
    "SCREEN_CLOSEUP",
}
VIEWER_SCREEN_VISIBILITY = {"REQUIRED", "OPTIONAL", "FORBIDDEN"}
UI_DELIVERY_MODES = {"RASTER_SHELL_ONLY", "VECTOR_OVERLAY", "NONE"}


def _validate_visual_contract(job: dict) -> None:
    contract = job.get("visual_contract")
    _require(isinstance(contract, dict), "visual_contract is required")
    owner = contract.get("visual_information_owner")
    _require(owner in VISUAL_INFORMATION_OWNERS, "visual_contract: invalid visual_information_owner")

    screen_bearing = contract.get("screen_bearing_prop")
    _require(isinstance(screen_bearing, bool), "visual_contract: screen_bearing_prop must be boolean")
    screen = contract.get("screen_contract")

    if not screen_bearing:
        _require(screen is None, "visual_contract: non-screen job must use screen_contract=null")
        return

    _require(isinstance(screen, dict), "visual_contract: screen-bearing job requires screen_contract")
    _require(isinstance(screen.get("prop_id"), str) and screen["prop_id"].strip(), "screen_contract: prop_id required")
    _require(screen.get("display_surface") == "FRONT", "screen_contract: display_surface must be FRONT")
    _require(
        screen.get("subject_screen_relation") in SUBJECT_SCREEN_RELATIONS,
        "screen_contract: invalid subject_screen_relation",
    )
    _require(
        screen.get("camera_screen_relation") in CAMERA_SCREEN_RELATIONS,
        "screen_contract: invalid camera_screen_relation",
    )
    _require(
        screen.get("viewer_screen_visibility") in VIEWER_SCREEN_VISIBILITY,
        "screen_contract: invalid viewer_screen_visibility",
    )
    _require(
        screen.get("ui_delivery_mode") in UI_DELIVERY_MODES,
        "screen_contract: invalid ui_delivery_mode",
    )
    _require(
        isinstance(screen.get("geometry_rule"), str) and screen["geometry_rule"].strip(),
        "screen_contract: geometry_rule required",
    )

    # Generic physical invariant: if the subject is looking at a private screen and
    # the camera is directly in front of the subject, requiring the audience to see
    # that same display surface is contradictory. Use over-shoulder/POV/oblique
    # geometry or keep audience screen visibility non-required.
    if (
        screen["subject_screen_relation"] == "LOOKING_AT_SCREEN"
        and screen["camera_screen_relation"] == "FRONT_OF_SUBJECT"
        and screen["viewer_screen_visibility"] == "REQUIRED"
    ):
        raise GateError(
            "screen_contract: impossible shared visibility; subject looks at screen "
            "while front camera also requires audience to see the display"
        )

    if owner == "SCREEN_INFORMATION":
        _require(
            screen["viewer_screen_visibility"] == "REQUIRED",
            "screen_contract: SCREEN_INFORMATION requires viewer_screen_visibility=REQUIRED",
        )


def authorize(job: dict) -> str:
    for key in ("job_id","requirements","renderer","supplied","visual_contract"):
        _require(key in job, f"job missing {key}")

    _validate_visual_contract(job)

    renderer = job["renderer"]
    supported_types = set(renderer.get("supported_media_types", []))
    supplied = job.get("supplied", [])
    supplied_by_id = {x.get("requirement_id"): x for x in supplied}

    max_inputs = renderer.get("max_media_inputs")
    if max_inputs is not None:
        _require(len(supplied) <= max_inputs, "supplied media exceeds renderer max_media_inputs")

    prompt_binding = job.get("prompt_binding")
    if prompt_binding is not None:
        _require(
            prompt_binding in renderer.get("supported_prompt_bindings", []),
            f"renderer does not support prompt binding: {prompt_binding}",
        )

    seen = set()
    for req in job["requirements"]:
        rid = req.get("requirement_id")
        _require(rid and rid not in seen, f"duplicate/invalid requirement_id: {rid}")
        seen.add(rid)

        required = req.get("required") is True
        conditioning = req.get("conditioning")
        media_type = req.get("media_type")
        source_id = req.get("source_id")

        _require(
            conditioning in {"MUST_SUPPLY_MEDIA","AUTHORITY_ONLY_ALLOWED"},
            f"{rid}: invalid conditioning",
        )

        if not required:
            continue

        if conditioning == "AUTHORITY_ONLY_ALLOWED":
            continue

        _require(
            renderer.get("supports_explicit_media_inputs") is True,
            f"{rid}: renderer cannot accept explicit media inputs",
        )
        _require(media_type in supported_types, f"{rid}: renderer does not support media type {media_type}")

        evidence = supplied_by_id.get(rid)
        _require(evidence is not None, f"{rid}: required media was not supplied")
        _require(evidence.get("source_id") == source_id, f"{rid}: supplied source_id mismatch")
        _require(evidence.get("media_type") == media_type, f"{rid}: supplied media_type mismatch")

        expected_hash = req.get("expected_hash")
        if expected_hash:
            _require(evidence.get("actual_hash") == expected_hash, f"{rid}: supplied media hash mismatch")

        coverage_scope = req.get("coverage_scope")
        allowed_influence = req.get("allowed_influence")
        requested_influence = req.get("requested_influence")

        if coverage_scope is not None:
            _require(
                isinstance(coverage_scope, list) and coverage_scope
                and all(isinstance(x, str) and x.strip() for x in coverage_scope),
                f"{rid}: coverage_scope must be a non-empty string list",
            )
        if allowed_influence is not None:
            _require(
                isinstance(allowed_influence, list) and allowed_influence
                and all(isinstance(x, str) and x.strip() for x in allowed_influence),
                f"{rid}: allowed_influence must be a non-empty string list",
            )
        if requested_influence is not None:
            _require(
                isinstance(requested_influence, list) and requested_influence
                and all(isinstance(x, str) and x.strip() for x in requested_influence),
                f"{rid}: requested_influence must be a non-empty string list",
            )
            requested = set(requested_influence)
            if coverage_scope is not None:
                _require(
                    requested <= set(coverage_scope),
                    f"{rid}: requested influence exceeds reference coverage_scope",
                )
            if allowed_influence is not None:
                _require(
                    requested <= set(allowed_influence),
                    f"{rid}: requested influence exceeds allowed_influence",
                )

    return "AUTHORIZED"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job")
    args = parser.parse_args()
    try:
        job = load_job(Path(args.job))
        print(authorize(job))
    except GateError as exc:
        print(f"MEDIA_GATE_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
