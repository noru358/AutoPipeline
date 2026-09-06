#!/usr/bin/env python3
"""Validate the common production policy and child project profiles.

This deliberately uses only the Python standard library so a clean clone can
run the gate before optional production dependencies are installed.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


class SystemGateError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemGateError(message)


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemGateError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemGateError(f"invalid JSON: {path}: {exc}") from exc
    _require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def validate_policy(policy: dict) -> list[str]:
    required = {
        "schema_version",
        "system_id",
        "execution_policy",
        "continuity_policy",
        "canonical_stages",
        "program_responsibilities",
        "chatgpt_responsibilities",
        "quality_policy",
    }
    _require(required <= policy.keys(), f"system policy missing: {sorted(required - policy.keys())}")
    _require(policy["schema_version"] == "1.0", "unsupported system policy version")

    execution = policy["execution_policy"]
    _require(execution.get("ai_mode") == "CHATGPT_SUBSCRIPTION_FIRST", "AI mode must be subscription-first")
    _require(execution.get("additional_paid_ai_budget_krw") == 0, "initial additional paid AI budget must be zero")
    _require(execution.get("allow_paid_fallback") is False, "paid fallback must be disabled")
    _require(execution.get("on_subscription_limit") == "SUSPEND_AND_RESUME", "subscription limit must suspend and resume")
    _require(execution.get("user_trigger_required") is True, "subscription work must require a user trigger")
    _require(execution.get("unattended_subscription_invocation") is False, "unattended subscription invocation cannot be assumed")
    _require(execution.get("asset_production_requires_authorized_packet") is True, "asset production must require an authorized packet")
    _require(execution.get("asset_production_requires_bound_media_evidence") is True, "asset production must bind actual media evidence")
    _require(execution.get("asset_production_requires_visual_contract") is True, "asset production must bind a visual contract")

    continuity = policy["continuity_policy"]
    _require(
        continuity.get("context_contamination_action") == "HANDOFF_TO_NEW_SESSION",
        "context contamination must trigger a new-session handoff",
    )
    _require(bool(continuity.get("contamination_signals")), "context contamination signals are required")
    _require(continuity.get("unsafe_context_is_sticky") is True, "unsafe render context must remain sticky until clean handoff")
    _require(continuity.get("post_threshold_outputs_quarantined") is True, "post-threshold outputs must be quarantined")
    handoff_fields = set(continuity.get("handoff_required_fields", []))
    _require(
        {"verified_repository_heads", "active_decisions", "open_blockers", "next_single_action", "quarantined_outputs"} <= handoff_fields,
        "handoff is missing minimum continuity fields",
    )

    quality = policy["quality_policy"]
    required_quality = {
        "hard_contract_qc_precedes_subjective_qc",
        "sequence_qc_before_raster_user_gate",
        "fixed_direction_quotas_forbidden",
        "viewer_perceived_redundancy_review",
        "declared_semantic_intent_qc",
        "high_risk_interaction_geometry_qc",
        "rejected_output_quarantine",
        "minimal_repair_scope",
    }
    _require(isinstance(quality, dict), "quality_policy must be an object")
    _require(required_quality <= quality.keys(), f"quality_policy missing: {sorted(required_quality - quality.keys())}")
    _require(all(quality.get(key) is True for key in required_quality), "all shared quality-policy invariants must be enabled")

    stages = policy["canonical_stages"]
    _require(isinstance(stages, list) and stages, "canonical stages must be a non-empty list")
    stage_ids = [stage.get("id") for stage in stages]
    orders = [stage.get("order") for stage in stages]
    _require(len(stage_ids) == len(set(stage_ids)), "canonical stage IDs must be unique")
    _require(orders == list(range(1, len(stages) + 1)), "canonical stage order must be contiguous and ordered")
    _require(all(stage.get("owner") in {"CHATGPT_ASSISTED", "PROGRAM", "HYBRID"} for stage in stages), "invalid stage owner")

    program_work = set(policy["program_responsibilities"])
    _require("persistent_project_state" in program_work, "program must own persistent project state")
    _require("approval_version_binding" in program_work, "program must bind approvals to versions")
    _require("editable_text_ui_and_layout" in program_work, "program must own editable text/UI/layout")
    _require("export" in program_work, "program must own export")
    return stage_ids


def validate_profile(profile: dict, stage_ids: list[str], repo_root: Path | None = None) -> str:
    required = {
        "profile_version",
        "project_id",
        "content_family",
        "creative_authority_root",
        "creative_authority_refs",
        "episode_id_pattern",
        "products",
        "stage_overrides",
    }
    _require(required <= profile.keys(), f"project profile missing: {sorted(required - profile.keys())}")
    _require(profile["profile_version"] == "1.0", "unsupported project profile version")
    project_id = profile["project_id"]
    _require(isinstance(project_id, str) and re.fullmatch(r"[a-z][a-z0-9_-]+", project_id), "invalid project_id")
    _require(profile["content_family"] in {"STORY_EMPATHY", "OBSERVATION_SENSORY"}, f"{project_id}: invalid content family")

    authority_refs = profile["creative_authority_refs"]
    _require(isinstance(authority_refs, list) and authority_refs, f"{project_id}: creative authority refs are required")
    _require(len(authority_refs) == len(set(authority_refs)), f"{project_id}: duplicate creative authority ref")
    try:
        re.compile(profile["episode_id_pattern"])
    except (re.error, TypeError) as exc:
        raise SystemGateError(f"{project_id}: invalid episode ID pattern") from exc

    products = profile["products"]
    _require(isinstance(products, list) and products, f"{project_id}: at least one product is required")
    product_ids = [product.get("id") for product in products]
    _require(len(product_ids) == len(set(product_ids)), f"{project_id}: product IDs must be unique")
    active_carousel = [product for product in products if product.get("kind") == "CAROUSEL" and product.get("status") == "ACTIVE"]
    _require(len(active_carousel) == 1, f"{project_id}: exactly one active carousel product is required")
    for product in products:
        _require(product.get("kind") in {"CAROUSEL", "VERTICAL_MOTION"}, f"{project_id}: invalid product kind")
        _require(product.get("status") in {"ACTIVE", "PLANNED", "DISABLED"}, f"{project_id}: invalid product status")
        _require(re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", str(product.get("aspect_ratio"))), f"{project_id}: invalid aspect ratio")

    overrides = profile["stage_overrides"]
    _require(isinstance(overrides, dict), f"{project_id}: stage_overrides must be an object")
    unknown = set(overrides) - set(stage_ids)
    _require(not unknown, f"{project_id}: unknown stage overrides: {sorted(unknown)}")
    for stage_id, override in overrides.items():
        _require(isinstance(override.get("intent"), str) and override["intent"].strip(), f"{project_id}/{stage_id}: intent is required")
        refs = override.get("authority_refs")
        _require(isinstance(refs, list) and refs, f"{project_id}/{stage_id}: authority refs are required")
        _require(set(refs) <= set(authority_refs), f"{project_id}/{stage_id}: undeclared authority ref")

    if repo_root is not None:
        authority_root = repo_root / profile["creative_authority_root"]
        _require(authority_root.is_dir(), f"{project_id}: authority root is not materialized: {authority_root}")
        missing = [ref for ref in authority_refs if not (authority_root / ref).is_file()]
        _require(not missing, f"{project_id}: missing authority files: {missing}")

    return project_id


def validate_system(policy: dict, profiles: list[dict], repo_root: Path | None = None) -> list[str]:
    stage_ids = validate_policy(policy)
    project_ids = [validate_profile(profile, stage_ids, repo_root) for profile in profiles]
    _require(len(project_ids) == len(set(project_ids)), "project IDs must be unique")
    _require(
        {profile["content_family"] for profile in profiles} >= {"STORY_EMPATHY", "OBSERVATION_SENSORY"},
        "initial system must include both story-empathy and observation-sensory families",
    )
    return project_ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="config/system_policy.json")
    parser.add_argument("--profiles", nargs="+", default=["profiles/instatoon.json", "profiles/jipbap.json"])
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    try:
        policy = load_json(repo_root / args.policy)
        profiles = [load_json(repo_root / path) for path in args.profiles]
        project_ids = validate_system(policy, profiles, repo_root)
    except SystemGateError as exc:
        print(f"SYSTEM_GATE_FAIL: {exc}")
        raise SystemExit(2)
    print(f"SYSTEM_POLICY_VALID: {','.join(project_ids)}")


if __name__ == "__main__":
    main()
