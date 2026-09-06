#!/usr/bin/env python3
"""Durable subscription-first work packets and artifact registration.

The bridge deliberately does not call an AI provider. It prepares exact stage
authority, stores actual input/result bytes with hashes, binds explicit user
approval to an immutable result hash, and computes the next safe action after a
fresh process reopens the packet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.media_gate import GateError as MediaGateError, authorize as authorize_media
from pipeline.dispatch_receipt import ReceiptError as DispatchReceiptError, verify_dispatch_receipt


SCHEMA_VERSION = "1.2"
STATUSES = {
    "READY_FOR_CHATGPT",
    "DISPATCH_AUTHORIZED",
    "AWAITING_RESULT_IMPORT",
    "RESULT_REGISTERED",
    "USER_APPROVED",
    "SUSPENDED",
}
MEDIA_TYPES = {"image", "audio", "video", "other"}
ASSET_KINDS = {"input", "result"}


class BridgeError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BridgeError(message)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BridgeError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BridgeError(f"invalid JSON: {path}: {exc}") from exc
    _require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def _safe_relative_path(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise BridgeError(f"path escapes packet root: {path}") from exc
    return relative.as_posix()


def _event(packet: dict[str, Any], event_type: str, detail: dict[str, Any] | None = None) -> None:
    events = packet.setdefault("events", [])
    events.append(
        {
            "seq": len(events) + 1,
            "at_utc": _utc_now(),
            "type": event_type,
            "detail": detail or {},
        }
    )


def _validate_packet_shape(packet: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "packet_id",
        "project_id",
        "work_scope",
        "stage_id",
        "status",
        "state_revision",
        "created_at_utc",
        "updated_at_utc",
        "execution_snapshot",
        "authority_snapshot",
        "assets",
        "approvals",
        "events",
        "next_action",
    }
    _require(required <= packet.keys(), f"work packet missing: {sorted(required - packet.keys())}")
    _require(packet["schema_version"] == SCHEMA_VERSION, "unsupported work packet schema version")
    _require(packet["work_scope"] in {"PROJECT", "EPISODE"}, f"invalid work_scope: {packet['work_scope']}")
    if packet["work_scope"] == "EPISODE":
        _require(isinstance(packet.get("episode_id"), str) and packet["episode_id"], "episode scope requires episode_id")
    else:
        _require("episode_id" not in packet, "project scope must not carry episode_id")
    _require(packet["status"] in STATUSES, f"invalid work packet status: {packet['status']}")
    _require(isinstance(packet["state_revision"], int) and packet["state_revision"] >= 1, "invalid state_revision")
    _require(isinstance(packet["authority_snapshot"], list), "authority_snapshot must be a list")
    _require(isinstance(packet["assets"], list), "assets must be a list")
    _require(isinstance(packet["approvals"], list), "approvals must be a list")
    _require(isinstance(packet["events"], list), "events must be a list")
    _require(isinstance(packet["next_action"], dict), "next_action must be an object")


def load_packet(packet_path: Path | str) -> dict[str, Any]:
    packet = _load_json(Path(packet_path))
    _validate_packet_shape(packet)
    return packet


def _atomic_write_packet(
    packet_path: Path,
    packet: dict[str, Any],
    *,
    expected_revision: int | None,
    create_only: bool = False,
) -> None:
    packet_path.parent.mkdir(parents=True, exist_ok=True)

    if create_only:
        _require(not packet_path.exists(), f"work packet already exists: {packet_path}")
    elif expected_revision is not None:
        current = load_packet(packet_path)
        _require(
            current["state_revision"] == expected_revision,
            f"stale work packet write: expected revision {expected_revision}, "
            f"found {current['state_revision']}",
        )

    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{packet_path.name}.", suffix=".tmp", dir=packet_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, packet_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _advance_revision(packet: dict[str, Any]) -> None:
    packet["state_revision"] += 1
    packet["updated_at_utc"] = _utc_now()


def _compute_next_action(packet: dict[str, Any]) -> dict[str, str]:
    status = packet["status"]
    if status == "READY_FOR_CHATGPT":
        if packet.get("stage_id") == "ASSET_PRODUCTION":
            return {
                "type": "AUTHORIZE_ASSET_DISPATCH",
                "instruction": "Bind actual input assets, renderer capability and visual geometry before any raster generation.",
            }
        return {
            "type": "RUN_CHATGPT_ASSISTED_STAGE",
            "instruction": "Use the saved authority and registered inputs in a user-triggered ChatGPT session.",
        }
    if status == "DISPATCH_AUTHORIZED":
        return {
            "type": "RUN_CHATGPT_ASSISTED_STAGE",
            "instruction": "Run the renderer with exactly the authorized media bindings and record a post-dispatch receipt proving explicit media inputs before importing any result.",
        }
    if status == "AWAITING_RESULT_IMPORT":
        return {
            "type": "IMPORT_CHATGPT_RESULT",
            "instruction": "Register the actual ChatGPT-produced file bytes into this work packet.",
        }
    if status == "RESULT_REGISTERED":
        return {
            "type": "REVIEW_RESULT",
            "instruction": "Review a registered result. Explicit user approval is required before it is locked.",
        }
    if status == "USER_APPROVED":
        return {
            "type": "ADVANCE_STAGE",
            "instruction": "The selected result is hash-locked; advance without regenerating this packet.",
        }
    if status == "SUSPENDED":
        return {
            "type": "RESUME_USER_TRIGGER",
            "instruction": "Resume only after the user starts a new eligible ChatGPT interaction.",
        }
    raise BridgeError(f"cannot compute next action for status: {status}")


def create_packet(
    *,
    repo_root: Path | str,
    policy_path: Path | str,
    profile_path: Path | str,
    work_scope: str,
    episode_id: str | None,
    stage_id: str,
    packet_path: Path | str,
    packet_id: str | None = None,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    policy_file = (repo_root / policy_path).resolve()
    profile_file = (repo_root / profile_path).resolve()
    packet_file = Path(packet_path).resolve()

    policy = _load_json(policy_file)
    profile = _load_json(profile_file)

    execution = policy.get("execution_policy", {})
    _require(execution.get("ai_mode") == "CHATGPT_SUBSCRIPTION_FIRST", "policy is not subscription-first")
    _require(execution.get("additional_paid_ai_budget_krw") == 0, "paid AI budget must be zero for this bridge")
    _require(execution.get("allow_paid_fallback") is False, "paid fallback must be disabled")
    _require(execution.get("user_trigger_required") is True, "user trigger must be required")
    _require(execution.get("unattended_subscription_invocation") is False, "unattended subscription use is forbidden")
    _require(execution.get("asset_production_requires_authorized_packet") is True, "asset production authorization policy must be enabled")
    _require(execution.get("asset_production_requires_bound_media_evidence") is True, "bound media evidence policy must be enabled")
    _require(execution.get("asset_production_requires_visual_contract") is True, "visual contract policy must be enabled")
    _require(execution.get("asset_production_requires_dispatch_receipt") is True, "dispatch receipt policy must be enabled")

    stage_ids = [stage.get("id") for stage in policy.get("canonical_stages", [])]
    _require(stage_id in stage_ids, f"unknown canonical stage: {stage_id}")

    project_id = profile.get("project_id")
    _require(isinstance(project_id, str) and project_id, "profile project_id is required")
    work_scope = work_scope.upper()
    _require(work_scope in {"PROJECT", "EPISODE"}, f"invalid work_scope: {work_scope}")
    if work_scope == "EPISODE":
        _require(isinstance(episode_id, str) and episode_id, "episode scope requires episode_id")
        try:
            episode_pattern = re.compile(profile["episode_id_pattern"])
        except (KeyError, TypeError, re.error) as exc:
            raise BridgeError("profile has invalid episode_id_pattern") from exc
        _require(
            episode_pattern.fullmatch(episode_id) is not None,
            f"invalid episode_id for {project_id}: {episode_id}",
        )
    else:
        _require(episode_id is None, "project scope must not carry episode_id")

    overrides = profile.get("stage_overrides", {})
    override = overrides.get(stage_id, {})
    authority_refs = override.get("authority_refs") or profile.get("creative_authority_refs", [])
    _require(authority_refs, f"{project_id}/{stage_id}: no creative authority refs configured")

    authority_root = repo_root / profile["creative_authority_root"]
    snapshot = []
    for ref in authority_refs:
        source = authority_root / ref
        _require(source.is_file(), f"missing creative authority file: {source}")
        snapshot.append(
            {
                "path": source.resolve().relative_to(repo_root).as_posix(),
                "sha256": _sha256_file(source),
                "size_bytes": source.stat().st_size,
            }
        )

    now = _utc_now()
    scope_key = episode_id if work_scope == "EPISODE" else "PROJECT"
    packet = {
        "schema_version": SCHEMA_VERSION,
        "packet_id": packet_id or f"{project_id}:{scope_key}:{stage_id}:{uuid.uuid4().hex[:12]}",
        "project_id": project_id,
        "work_scope": work_scope,
        "stage_id": stage_id,
        "status": "READY_FOR_CHATGPT",
        "state_revision": 1,
        "created_at_utc": now,
        "updated_at_utc": now,
        "execution_snapshot": {
            "ai_mode": execution["ai_mode"],
            "additional_paid_ai_budget_krw": execution["additional_paid_ai_budget_krw"],
            "allow_paid_fallback": execution["allow_paid_fallback"],
            "user_trigger_required": execution["user_trigger_required"],
            "unattended_subscription_invocation": execution["unattended_subscription_invocation"],
            "artifact_transfer": "MANUAL_IMPORT_UNTIL_VERIFIED",
        },
        "authority_snapshot": snapshot,
        "assets": [],
        "approvals": [],
        "events": [],
        "next_action": {},
    }
    if work_scope == "EPISODE":
        packet["episode_id"] = episode_id
    _event(packet, "PACKET_CREATED", {"authority_count": len(snapshot)})
    packet["next_action"] = _compute_next_action(packet)
    _validate_packet_shape(packet)
    _atomic_write_packet(packet_file, packet, expected_revision=None, create_only=True)
    return packet


def _register_asset(
    *,
    packet_path: Path | str,
    source_path: Path | str,
    kind: str,
    role: str,
    media_type: str,
) -> dict[str, Any]:
    _require(kind in ASSET_KINDS, f"invalid asset kind: {kind}")
    _require(media_type in MEDIA_TYPES, f"invalid media type: {media_type}")
    _require(bool(role.strip()), "asset role is required")

    packet_file = Path(packet_path).resolve()
    packet = load_packet(packet_file)
    revision = packet["state_revision"]

    _require(
        packet["status"] != "USER_APPROVED",
        "approved packet is locked; no input or result assets may be changed",
    )
    if kind == "input":
        _require(
            packet["status"] == "READY_FOR_CHATGPT",
            f"input assets must be finalized before dispatch; current status is {packet['status']}",
        )
    else:
        _require(
            packet["status"] in {"AWAITING_RESULT_IMPORT", "RESULT_REGISTERED"},
            f"result import requires a dispatched packet; current status is {packet['status']}",
        )

    source = Path(source_path).resolve()
    _require(source.is_file(), f"asset source file does not exist: {source}")
    digest = _sha256_file(source)
    size = source.stat().st_size

    existing = next(
        (
            asset
            for asset in packet["assets"]
            if asset.get("kind") == kind
            and asset.get("role") == role
            and asset.get("sha256") == digest
            and asset.get("size_bytes") == size
        ),
        None,
    )
    if existing is not None:
        return existing

    suffix = source.suffix.lower()
    asset_dir = packet_file.parent / "assets" / ("inputs" if kind == "input" else "results")
    asset_dir.mkdir(parents=True, exist_ok=True)
    stored = asset_dir / f"{digest}{suffix}"
    if stored.exists():
        _require(_sha256_file(stored) == digest, f"stored asset collision: {stored}")
    else:
        shutil.copy2(source, stored)
        _require(_sha256_file(stored) == digest, f"asset copy verification failed: {stored}")

    asset = {
        "asset_id": f"{kind}:{role}:{digest[:16]}",
        "kind": kind,
        "role": role,
        "media_type": media_type,
        "original_name": source.name,
        "stored_path": _safe_relative_path(packet_file.parent, stored),
        "sha256": digest,
        "size_bytes": size,
        "locked": False,
        "registered_at_utc": _utc_now(),
    }
    packet["assets"].append(asset)

    if kind == "result":
        packet["status"] = "RESULT_REGISTERED"
    _event(packet, "ASSET_REGISTERED", {"asset_id": asset["asset_id"], "kind": kind})
    _advance_revision(packet)
    packet["next_action"] = _compute_next_action(packet)
    _atomic_write_packet(packet_file, packet, expected_revision=revision)
    return asset


def register_input_asset(
    *,
    packet_path: Path | str,
    source_path: Path | str,
    role: str,
    media_type: str,
) -> dict[str, Any]:
    return _register_asset(
        packet_path=packet_path,
        source_path=source_path,
        kind="input",
        role=role,
        media_type=media_type,
    )


def register_result_asset(
    *,
    packet_path: Path | str,
    source_path: Path | str,
    role: str,
    media_type: str,
) -> dict[str, Any]:
    return _register_asset(
        packet_path=packet_path,
        source_path=source_path,
        kind="result",
        role=role,
        media_type=media_type,
    )



def _verify_dispatch_job_against_packet(packet: dict[str, Any], job: dict[str, Any]) -> None:
    _require(job.get("packet_id") == packet["packet_id"], "dispatch job packet_id mismatch")
    _require(job.get("project_id") == packet["project_id"], "dispatch job project_id mismatch")
    _require(job.get("stage_id") == packet["stage_id"], "dispatch job stage_id mismatch")
    if packet["work_scope"] == "EPISODE":
        _require(job.get("episode_id") == packet["episode_id"], "dispatch job episode_id mismatch")

    input_assets = {
        asset["asset_id"]: asset
        for asset in packet["assets"]
        if asset.get("kind") == "input"
    }
    supplied = job.get("supplied", [])
    _require(isinstance(supplied, list), "dispatch job supplied must be a list")
    seen_asset_ids: set[str] = set()
    for evidence in supplied:
        asset_id = evidence.get("asset_id")
        _require(isinstance(asset_id, str) and asset_id, "dispatch evidence asset_id is required")
        _require(asset_id not in seen_asset_ids, f"duplicate dispatch asset_id: {asset_id}")
        seen_asset_ids.add(asset_id)
        asset = input_assets.get(asset_id)
        _require(asset is not None, f"dispatch evidence is not a registered input asset: {asset_id}")
        _require(evidence.get("source_id") == asset_id, f"{asset_id}: source_id must equal registered asset_id")
        _require(evidence.get("media_type") == asset["media_type"], f"{asset_id}: media_type mismatch")
        _require(evidence.get("actual_hash") == asset["sha256"], f"{asset_id}: actual_hash mismatch")

    try:
        authorize_media(job)
    except MediaGateError as exc:
        raise BridgeError(f"asset dispatch rejected: {exc}") from exc


def authorize_asset_dispatch(
    *,
    packet_path: Path | str,
    job_path: Path | str,
) -> dict[str, Any]:
    packet_file = Path(packet_path).resolve()
    packet = load_packet(packet_file)
    revision = packet["state_revision"]
    _require(packet["stage_id"] == "ASSET_PRODUCTION", "dispatch authorization is only for ASSET_PRODUCTION")
    _require(packet["status"] == "READY_FOR_CHATGPT", f"cannot authorize dispatch from status {packet['status']}")

    job = _load_json(Path(job_path).resolve())
    _verify_dispatch_job_against_packet(packet, job)

    authorization = {
        "status": "AUTHORIZED",
        "job_sha256": _sha256_json(job),
        "job": job,
        "authorized_at_utc": _utc_now(),
    }
    packet["dispatch_authorization"] = authorization
    packet["status"] = "DISPATCH_AUTHORIZED"
    _event(
        packet,
        "ASSET_DISPATCH_AUTHORIZED",
        {"job_id": job.get("job_id"), "job_sha256": authorization["job_sha256"]},
    )
    _advance_revision(packet)
    packet["next_action"] = _compute_next_action(packet)
    _atomic_write_packet(packet_file, packet, expected_revision=revision)
    return authorization


def mark_awaiting_result_import(
    packet_path: Path | str,
    *,
    receipt_path: Path | str | None = None,
) -> dict[str, Any]:
    packet_file = Path(packet_path).resolve()
    packet = load_packet(packet_file)
    revision = packet["state_revision"]
    required_status = "DISPATCH_AUTHORIZED" if packet["stage_id"] == "ASSET_PRODUCTION" else "READY_FOR_CHATGPT"
    _require(packet["status"] == required_status, f"cannot dispatch from status {packet['status']}; requires {required_status}")
    if packet["stage_id"] == "ASSET_PRODUCTION":
        authorization = packet.get("dispatch_authorization")
        _require(isinstance(authorization, dict), "asset production has no dispatch authorization")
        _require(authorization.get("status") == "AUTHORIZED", "asset production dispatch is not authorized")
        _require(
            authorization.get("job_sha256") == _sha256_json(authorization.get("job")),
            "asset production dispatch contract changed after authorization",
        )
        job = authorization["job"]
        _verify_dispatch_job_against_packet(packet, job)
        _require(receipt_path is not None, "asset production requires a post-dispatch media binding receipt")
        receipt = _load_json(Path(receipt_path).resolve())
        try:
            verify_dispatch_receipt(job, receipt)
        except DispatchReceiptError as exc:
            raise BridgeError(f"dispatch receipt rejected: {exc}") from exc
        packet["dispatch_receipt"] = {
            "status": "CONFIRMED",
            "receipt_sha256": _sha256_json(receipt),
            "receipt": receipt,
            "confirmed_at_utc": _utc_now(),
        }
        _event(
            packet,
            "ASSET_DISPATCH_RECEIPT_CONFIRMED",
            {
                "job_id": job.get("job_id"),
                "receipt_sha256": packet["dispatch_receipt"]["receipt_sha256"],
            },
        )
    packet["status"] = "AWAITING_RESULT_IMPORT"
    _event(packet, "CHATGPT_STAGE_STARTED")
    _advance_revision(packet)
    packet["next_action"] = _compute_next_action(packet)
    _atomic_write_packet(packet_file, packet, expected_revision=revision)
    return packet


def suspend_packet(packet_path: Path | str, reason: str) -> dict[str, Any]:
    _require(bool(reason.strip()), "suspension reason is required")
    packet_file = Path(packet_path).resolve()
    packet = load_packet(packet_file)
    revision = packet["state_revision"]
    _require(packet["status"] != "USER_APPROVED", "approved packet is already complete and locked")
    packet["suspended_from_status"] = packet["status"]
    packet["status"] = "SUSPENDED"
    _event(
        packet,
        "PACKET_SUSPENDED",
        {"reason": reason, "from_status": packet["suspended_from_status"]},
    )
    _advance_revision(packet)
    packet["next_action"] = _compute_next_action(packet)
    _atomic_write_packet(packet_file, packet, expected_revision=revision)
    return packet


def resume_suspended_packet(
    packet_path: Path | str,
    *,
    repo_root: Path | str,
) -> dict[str, Any]:
    packet_file = Path(packet_path).resolve()
    verify_packet(packet_file, repo_root=repo_root)
    packet = load_packet(packet_file)
    revision = packet["state_revision"]
    _require(packet["status"] == "SUSPENDED", f"packet is not suspended: {packet['status']}")
    prior_status = packet.get("suspended_from_status")
    _require(
        prior_status in {"READY_FOR_CHATGPT", "DISPATCH_AUTHORIZED", "AWAITING_RESULT_IMPORT", "RESULT_REGISTERED"},
        f"invalid suspended_from_status: {prior_status}",
    )
    packet["status"] = prior_status
    packet.pop("suspended_from_status", None)
    _event(packet, "PACKET_RESUMED", {"restored_status": prior_status})
    _advance_revision(packet)
    packet["next_action"] = _compute_next_action(packet)
    _atomic_write_packet(packet_file, packet, expected_revision=revision)
    return packet


def approve_result(
    *,
    packet_path: Path | str,
    asset_id: str,
    approved_by: str = "USER",
) -> dict[str, Any]:
    _require(approved_by == "USER", "only explicit USER approval can lock a result in v1")
    packet_file = Path(packet_path).resolve()
    packet = load_packet(packet_file)
    revision = packet["state_revision"]
    _require(packet["status"] == "RESULT_REGISTERED", f"cannot approve from status {packet['status']}")

    asset = next(
        (asset for asset in packet["assets"] if asset.get("asset_id") == asset_id and asset.get("kind") == "result"),
        None,
    )
    _require(asset is not None, f"unknown result asset_id: {asset_id}")

    stored = packet_file.parent / asset["stored_path"]
    _require(stored.is_file(), f"approved result bytes are missing: {stored}")
    actual_hash = _sha256_file(stored)
    _require(actual_hash == asset["sha256"], "result bytes changed before approval")

    for item in packet["assets"]:
        if item.get("kind") == "result":
            item["locked"] = item["asset_id"] == asset_id

    approval = {
        "approval_id": f"user:{asset_id}:{packet['state_revision'] + 1}",
        "actor": "USER",
        "decision": "APPROVED",
        "asset_id": asset_id,
        "sha256": asset["sha256"],
        "approved_at_utc": _utc_now(),
    }
    packet["approvals"].append(approval)
    packet["selected_result_asset_id"] = asset_id
    packet["status"] = "USER_APPROVED"
    _event(packet, "USER_APPROVAL_RECORDED", {"asset_id": asset_id, "sha256": asset["sha256"]})
    _advance_revision(packet)
    packet["next_action"] = _compute_next_action(packet)
    _atomic_write_packet(packet_file, packet, expected_revision=revision)
    return approval


def verify_packet(packet_path: Path | str, *, repo_root: Path | str) -> dict[str, Any]:
    packet_file = Path(packet_path).resolve()
    repo_root = Path(repo_root).resolve()
    packet = load_packet(packet_file)

    for authority in packet["authority_snapshot"]:
        source = repo_root / authority["path"]
        _require(source.is_file(), f"authority file missing on resume: {authority['path']}")
        _require(
            _sha256_file(source) == authority["sha256"],
            f"authority drift detected on resume: {authority['path']}",
        )

    seen_ids: set[str] = set()
    for asset in packet["assets"]:
        asset_id = asset.get("asset_id")
        _require(asset_id and asset_id not in seen_ids, f"duplicate/invalid asset_id: {asset_id}")
        seen_ids.add(asset_id)
        stored = packet_file.parent / asset["stored_path"]
        _safe_relative_path(packet_file.parent, stored)
        _require(stored.is_file(), f"registered asset bytes are missing: {asset_id}")
        _require(stored.stat().st_size == asset["size_bytes"], f"registered asset size changed: {asset_id}")
        _require(_sha256_file(stored) == asset["sha256"], f"registered asset hash changed: {asset_id}")


    if packet["stage_id"] == "ASSET_PRODUCTION" and packet["status"] in {
        "DISPATCH_AUTHORIZED",
        "AWAITING_RESULT_IMPORT",
        "RESULT_REGISTERED",
        "USER_APPROVED",
    }:
        authorization = packet.get("dispatch_authorization")
        _require(isinstance(authorization, dict), "asset production packet is missing dispatch_authorization")
        _require(authorization.get("status") == "AUTHORIZED", "asset production dispatch authorization is invalid")
        job = authorization.get("job")
        _require(isinstance(job, dict), "asset production dispatch job is missing")
        _require(
            authorization.get("job_sha256") == _sha256_json(job),
            "asset production dispatch contract changed after authorization",
        )
        _verify_dispatch_job_against_packet(packet, job)

        if packet["status"] in {"AWAITING_RESULT_IMPORT", "RESULT_REGISTERED", "USER_APPROVED"}:
            receipt_record = packet.get("dispatch_receipt")
            _require(isinstance(receipt_record, dict), "asset production packet is missing dispatch_receipt")
            _require(receipt_record.get("status") == "CONFIRMED", "asset production dispatch receipt is not confirmed")
            receipt = receipt_record.get("receipt")
            _require(isinstance(receipt, dict), "asset production dispatch receipt payload is missing")
            _require(
                receipt_record.get("receipt_sha256") == _sha256_json(receipt),
                "asset production dispatch receipt changed after confirmation",
            )
            try:
                verify_dispatch_receipt(job, receipt)
            except DispatchReceiptError as exc:
                raise BridgeError(f"dispatch receipt rejected on resume: {exc}") from exc

    if packet["status"] == "USER_APPROVED":
        selected_id = packet.get("selected_result_asset_id")
        _require(bool(selected_id), "approved packet has no selected_result_asset_id")
        selected = next((asset for asset in packet["assets"] if asset.get("asset_id") == selected_id), None)
        _require(selected is not None and selected.get("kind") == "result", "approved result asset is missing")
        _require(selected.get("locked") is True, "approved result is not locked")
        approval = next(
            (
                item
                for item in reversed(packet["approvals"])
                if item.get("actor") == "USER"
                and item.get("decision") == "APPROVED"
                and item.get("asset_id") == selected_id
            ),
            None,
        )
        _require(approval is not None, "approved packet has no explicit USER approval record")
        _require(approval.get("sha256") == selected.get("sha256"), "approval hash does not match selected result")

    packet["next_action"] = _compute_next_action(packet)
    return packet


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a durable stage work packet")
    init.add_argument("--repo-root", default=".")
    init.add_argument("--policy", default="config/system_policy.json")
    init.add_argument("--profile", required=True)
    init.add_argument("--scope", choices=["project", "episode"], default="episode")
    init.add_argument("--episode")
    init.add_argument("--stage", required=True)
    init.add_argument("--packet", required=True)

    add_input = sub.add_parser("add-input", help="Copy and hash a real input asset")
    add_input.add_argument("--packet", required=True)
    add_input.add_argument("--file", required=True)
    add_input.add_argument("--role", required=True)
    add_input.add_argument("--media-type", choices=sorted(MEDIA_TYPES), required=True)

    authorize_dispatch = sub.add_parser("authorize-dispatch", help="Authorize ASSET_PRODUCTION using bound media and visual contract")
    authorize_dispatch.add_argument("--packet", required=True)
    authorize_dispatch.add_argument("--job", required=True)

    dispatched = sub.add_parser("dispatched", help="Confirm renderer dispatch and move to result import")
    dispatched.add_argument("--packet", required=True)
    dispatched.add_argument("--receipt", help="Post-dispatch receipt JSON; required for ASSET_PRODUCTION")

    add_result = sub.add_parser("add-result", help="Copy and hash a real ChatGPT-produced result")
    add_result.add_argument("--packet", required=True)
    add_result.add_argument("--file", required=True)
    add_result.add_argument("--role", required=True)
    add_result.add_argument("--media-type", choices=sorted(MEDIA_TYPES), required=True)

    approve = sub.add_parser("approve", help="Bind explicit USER approval to one result hash")
    approve.add_argument("--packet", required=True)
    approve.add_argument("--asset-id", required=True)

    suspend = sub.add_parser("suspend", help="Persist a subscription/tool interruption")
    suspend.add_argument("--packet", required=True)
    suspend.add_argument("--reason", required=True)

    resume_suspended = sub.add_parser("resume-suspended", help="Verify and resume a user-triggered suspended packet")
    resume_suspended.add_argument("--packet", required=True)
    resume_suspended.add_argument("--repo-root", default=".")

    verify = sub.add_parser("verify", help="Reopen and verify authority/assets/approval before resuming")
    verify.add_argument("--packet", required=True)
    verify.add_argument("--repo-root", default=".")

    args = parser.parse_args()
    try:
        if args.command == "init":
            result = create_packet(
                repo_root=args.repo_root,
                policy_path=args.policy,
                profile_path=args.profile,
                work_scope=args.scope.upper(),
                episode_id=args.episode,
                stage_id=args.stage,
                packet_path=args.packet,
            )
        elif args.command == "add-input":
            result = register_input_asset(
                packet_path=args.packet,
                source_path=args.file,
                role=args.role,
                media_type=args.media_type,
            )
        elif args.command == "authorize-dispatch":
            result = authorize_asset_dispatch(packet_path=args.packet, job_path=args.job)
        elif args.command == "dispatched":
            result = mark_awaiting_result_import(args.packet, receipt_path=args.receipt)
        elif args.command == "add-result":
            result = register_result_asset(
                packet_path=args.packet,
                source_path=args.file,
                role=args.role,
                media_type=args.media_type,
            )
        elif args.command == "approve":
            result = approve_result(packet_path=args.packet, asset_id=args.asset_id)
        elif args.command == "suspend":
            result = suspend_packet(args.packet, args.reason)
        elif args.command == "resume-suspended":
            result = resume_suspended_packet(args.packet, repo_root=args.repo_root)
        elif args.command == "verify":
            result = verify_packet(args.packet, repo_root=args.repo_root)
        else:
            raise AssertionError(args.command)
    except BridgeError as exc:
        print(f"ARTIFACT_BRIDGE_FAIL: {exc}")
        raise SystemExit(2)
    _print_json(result)


if __name__ == "__main__":
    main()
