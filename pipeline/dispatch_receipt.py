#!/usr/bin/env python3
"""Post-dispatch proof that required media was actually bound to the renderer call."""
from __future__ import annotations

from typing import Any


class ReceiptError(RuntimeError):
    pass


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ReceiptError(msg)


def verify_dispatch_receipt(job: dict[str, Any], receipt: dict[str, Any]) -> str:
    _require(isinstance(job, dict), "job must be an object")
    _require(isinstance(receipt, dict), "receipt must be an object")
    _require(receipt.get("job_id") == job.get("job_id"), "receipt job_id mismatch")

    renderer = job.get("renderer") or {}
    _require(
        receipt.get("renderer_id") == renderer.get("renderer_id"),
        "receipt renderer_id mismatch",
    )

    bindings = receipt.get("bindings")
    _require(isinstance(bindings, list), "receipt bindings must be a list")
    by_req: dict[str, dict[str, Any]] = {}
    for binding in bindings:
        _require(isinstance(binding, dict), "receipt binding must be an object")
        rid = binding.get("requirement_id")
        _require(isinstance(rid, str) and rid, "receipt requirement_id required")
        _require(rid not in by_req, f"duplicate receipt requirement_id: {rid}")
        by_req[rid] = binding

    planned = job.get("supplied") or []
    planned_by_req = {
        item.get("requirement_id"): item
        for item in planned
        if isinstance(item, dict) and item.get("requirement_id")
    }

    required_ids: set[str] = set()
    for req in job.get("requirements") or []:
        if not isinstance(req, dict):
            continue
        if req.get("required") is not True:
            continue
        if req.get("conditioning") != "MUST_SUPPLY_MEDIA":
            continue

        rid = req.get("requirement_id")
        _require(isinstance(rid, str) and rid, "required media requirement_id missing")
        required_ids.add(rid)

        binding = by_req.get(rid)
        _require(binding is not None, f"{rid}: dispatch receipt missing required binding")
        _require(
            binding.get("binding_method") == "EXPLICIT_MEDIA_INPUT",
            f"{rid}: binding_method must be EXPLICIT_MEDIA_INPUT",
        )
        handle = binding.get("input_handle")
        _require(isinstance(handle, str) and handle.strip(), f"{rid}: input_handle required")

        _require(binding.get("source_id") == req.get("source_id"), f"{rid}: source_id mismatch")
        _require(binding.get("media_type") == req.get("media_type"), f"{rid}: media_type mismatch")

        expected_hash = req.get("expected_hash")
        if expected_hash:
            _require(binding.get("actual_hash") == expected_hash, f"{rid}: actual_hash mismatch")

        planned_item = planned_by_req.get(rid)
        if planned_item is not None:
            if planned_item.get("asset_id") is not None:
                _require(
                    binding.get("asset_id") == planned_item.get("asset_id"),
                    f"{rid}: asset_id differs from authorized binding plan",
                )
            _require(
                binding.get("source_id") == planned_item.get("source_id"),
                f"{rid}: source_id differs from authorized binding plan",
            )
            _require(
                binding.get("actual_hash") == planned_item.get("actual_hash"),
                f"{rid}: hash differs from authorized binding plan",
            )

    extras = set(by_req) - {
        req.get("requirement_id")
        for req in job.get("requirements") or []
        if isinstance(req, dict)
    }
    _require(not extras, f"receipt has unknown requirement bindings: {sorted(extras)}")

    if required_ids:
        _require(
            receipt.get("explicit_media_binding_confirmed") is True,
            "receipt must confirm explicit_media_binding_confirmed=true",
        )

    return "CONFIRMED"
