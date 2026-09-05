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


def authorize(job: dict) -> str:
    for key in ("job_id","requirements","renderer","supplied"):
        _require(key in job, f"job missing {key}")

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
