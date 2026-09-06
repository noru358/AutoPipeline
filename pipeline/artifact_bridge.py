#!/usr/bin/env python3
"""Persist and resume user-triggered ChatGPT production work.

The bridge never invokes a model. It creates a versioned work packet, snapshots
the applicable creative authority, imports an actual result file, and verifies
all hashes before resuming.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pipeline.system_gate import SystemGateError, load_json, validate_system


class ArtifactBridgeError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ArtifactBridgeError(message)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member(root: Path, relative_value: str, label: str) -> Path:
    _require(isinstance(relative_value, str) and relative_value.strip() != "", f"{label} path is required")
    relative_path = Path(relative_value)
    _require(not relative_path.is_absolute(), f"{label} path must be relative: {relative_value}")
    root = root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ArtifactBridgeError(f"{label} path escapes its root: {relative_value}") from exc
    return candidate


def _git(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ArtifactBridgeError(f"git command failed: {' '.join(args)}") from exc
    return result.stdout.strip()


def _atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name and Path(temporary_name).exists():
            Path(temporary_name).unlink()


def _load_system(repo_root: Path) -> tuple[dict, dict, list[str]]:
    try:
        policy = load_json(repo_root / "config/system_policy.json")
        profile_paths = sorted((repo_root / "profiles").glob("*.json"))
        profiles = [load_json(path) for path in profile_paths]
        stage_ids = [stage["id"] for stage in policy["canonical_stages"]]
        validate_system(policy, profiles, repo_root)
    except (KeyError, SystemGateError) as exc:
        raise ArtifactBridgeError(str(exc)) from exc
    return policy, {profile["project_id"]: profile for profile in profiles}, stage_ids


def _authority_snapshot(repo_root: Path, profile: dict, stage: str) -> list[dict]:
    override = profile.get("stage_overrides", {}).get(stage)
    refs = override["authority_refs"] if override else profile["creative_authority_refs"]
    root_name = profile["creative_authority_root"]
    snapshot = []
    for ref in refs:
        relative_path = Path(root_name) / ref
        actual_path = _safe_member(repo_root, relative_path.as_posix(), "authority")
        _require(actual_path.is_file(), f"missing authority file: {relative_path.as_posix()}")
        snapshot.append({"path": relative_path.as_posix(), "sha256": _sha256(actual_path)})
    return snapshot


def _copy_packet_file(source_path: Path, packet_path: Path, subdirectory: str, prefix: str) -> tuple[Path, str, int]:
    _require(source_path.is_file(), f"source file is missing: {source_path}")
    _require(source_path.stat().st_size > 0, f"source file is empty: {source_path}")
    digest = _sha256(source_path)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", source_path.name).strip("._") or "file"
    relative_path = Path(subdirectory) / f"{prefix}-{digest[:16]}-{uuid.uuid4().hex[:8]}-{safe_name}"
    target = packet_path.parent / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    _require(not target.exists(), f"packet file target already exists: {target}")
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        shutil.copyfile(source_path, temporary)
        _require(_sha256(temporary) == digest, "packet file copy verification failed")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return relative_path, digest, target.stat().st_size


def create_packet(
    repo_root: Path,
    packet_path: Path,
    project_id: str,
    episode_id: str,
    stage: str,
    next_action: str,
    transfer_mode: str = "MANUAL_IMPORT",
    input_files: list[tuple[str, Path]] | None = None,
) -> dict:
    policy, profiles, stage_ids = _load_system(repo_root)
    _require(project_id in profiles, f"unknown project: {project_id}")
    profile = profiles[project_id]
    _require(re.fullmatch(profile["episode_id_pattern"], episode_id) is not None, f"invalid episode ID for {project_id}: {episode_id}")
    _require(stage in stage_ids, f"unknown canonical stage: {stage}")
    _require(transfer_mode in {"MANUAL_IMPORT", "DIRECT_INTEGRATION"}, "invalid transfer mode")
    _require(next_action.strip() != "", "next action is required")
    _require(not packet_path.exists(), f"packet already exists: {packet_path}")

    now = _now()
    inputs = []
    for role, source_path in input_files or []:
        _require(role.strip() != "", "input role is required")
        relative_path, digest, size_bytes = _copy_packet_file(source_path, packet_path, "inputs", "input")
        inputs.append(
            {
                "input_id": f"{digest[:16]}-{uuid.uuid4().hex[:8]}",
                "role": role.strip(),
                "path": relative_path.as_posix(),
                "sha256": digest,
                "size_bytes": size_bytes,
                "source": "EXPLICIT_IMPORT",
                "captured_at": now,
            }
        )
    child_root = repo_root / profile["creative_authority_root"]
    packet = {
        "packet_version": "1.0",
        "packet_id": uuid.uuid4().hex,
        "revision": 1,
        "project_id": project_id,
        "episode_id": episode_id,
        "stage": stage,
        "status": "AWAITING_CHATGPT",
        "execution_mode": policy["execution_policy"]["ai_mode"],
        "transfer_mode": transfer_mode,
        "created_at": now,
        "updated_at": now,
        "source_control": {
            "parent_commit": _git(repo_root, "rev-parse", "HEAD"),
            "child_commit": _git(child_root, "rev-parse", "HEAD"),
        },
        "authority_snapshot": _authority_snapshot(repo_root, profile, stage),
        "inputs": inputs,
        "artifacts": [],
        "events": [{"type": "CREATED", "at": now, "detail": f"{project_id}/{episode_id}/{stage}:inputs={len(inputs)}"}],
        "suspension_reason": None,
        "next_action": next_action.strip(),
    }
    _atomic_write(packet_path, packet)
    return packet


def load_packet(packet_path: Path) -> dict:
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactBridgeError(f"missing work packet: {packet_path}") from exc
    except json.JSONDecodeError as exc:
        raise ArtifactBridgeError(f"invalid work packet JSON: {packet_path}") from exc
    _require(isinstance(packet, dict), "work packet root must be an object")
    return packet


def _check_revision(packet: dict, expected_revision: int) -> None:
    _require(packet.get("revision") == expected_revision, f"stale packet revision: expected {expected_revision}, actual {packet.get('revision')}")


def verify_packet(repo_root: Path, packet_path: Path) -> dict:
    packet = load_packet(packet_path)
    required = {
        "packet_version",
        "packet_id",
        "revision",
        "project_id",
        "episode_id",
        "stage",
        "status",
        "execution_mode",
        "transfer_mode",
        "source_control",
        "authority_snapshot",
        "inputs",
        "artifacts",
        "events",
        "next_action",
    }
    _require(required <= packet.keys(), f"work packet missing fields: {sorted(required - packet.keys())}")
    _require(packet.get("packet_version") == "1.0", "unsupported work packet version")
    _require(isinstance(packet.get("packet_id"), str) and packet["packet_id"], "invalid packet ID")
    _require(packet.get("execution_mode") == "CHATGPT_SUBSCRIPTION_FIRST", "packet execution mode changed")
    _require(packet.get("transfer_mode") in {"MANUAL_IMPORT", "DIRECT_INTEGRATION"}, "invalid transfer mode")
    _require(packet.get("status") in {"AWAITING_CHATGPT", "RESULT_REGISTERED", "SUSPENDED"}, "invalid packet status")
    _require(isinstance(packet.get("revision"), int) and packet["revision"] >= 1, "invalid packet revision")
    _require(isinstance(packet.get("next_action"), str) and packet["next_action"].strip(), "next action is required")
    source_control = packet.get("source_control")
    _require(isinstance(source_control, dict), "source_control must be an object")
    for commit_name in ("parent_commit", "child_commit"):
        _require(re.fullmatch(r"[0-9a-f]{40}", str(source_control.get(commit_name))) is not None, f"invalid {commit_name}")

    authorities = packet.get("authority_snapshot")
    _require(isinstance(authorities, list) and authorities, "authority snapshot must be a non-empty list")
    for authority in authorities:
        _require(isinstance(authority, dict), "authority record must be an object")
        _require(re.fullmatch(r"[0-9a-f]{64}", str(authority.get("sha256"))) is not None, "invalid authority hash")
        path = _safe_member(repo_root, authority.get("path"), "authority")
        _require(path.is_file(), f"authority file missing during resume: {authority['path']}")
        _require(_sha256(path) == authority["sha256"], f"authority file changed during resume: {authority['path']}")

    packet_root = packet_path.parent
    for record_type, records in (("input", packet.get("inputs", [])), ("artifact", packet.get("artifacts", []))):
        _require(isinstance(records, list), f"packet {record_type} records must be a list")
        for record in records:
            _require(isinstance(record, dict), f"{record_type} record must be an object")
            _require(isinstance(record.get("size_bytes"), int) and record["size_bytes"] > 0, f"invalid {record_type} size")
            _require(re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256"))) is not None, f"invalid {record_type} hash")
            path = _safe_member(packet_root, record.get("path"), record_type)
            _require(path.is_file(), f"registered {record_type} missing: {record['path']}")
            _require(path.stat().st_size == record["size_bytes"], f"registered {record_type} size changed: {record['path']}")
            _require(_sha256(path) == record["sha256"], f"registered {record_type} hash changed: {record['path']}")
    return packet


def register_artifact(
    repo_root: Path,
    packet_path: Path,
    source_path: Path,
    role: str,
    expected_revision: int,
    next_action: str,
) -> dict:
    packet = verify_packet(repo_root, packet_path)
    _check_revision(packet, expected_revision)
    _require(role.strip() != "", "artifact role is required")
    _require(next_action.strip() != "", "next action is required")

    relative_path, digest, size_bytes = _copy_packet_file(source_path, packet_path, "artifacts", "artifact")
    artifact_id = f"{digest[:16]}-{uuid.uuid4().hex[:8]}"

    now = _now()
    packet["artifacts"].append(
        {
            "artifact_id": artifact_id,
            "role": role.strip(),
            "path": relative_path.as_posix(),
            "sha256": digest,
            "size_bytes": size_bytes,
            "source": "CHATGPT_IMPORT",
            "registered_at": now,
        }
    )
    packet["revision"] += 1
    packet["status"] = "RESULT_REGISTERED"
    packet["updated_at"] = now
    packet["next_action"] = next_action.strip()
    packet["events"].append({"type": "ARTIFACT_REGISTERED", "at": now, "detail": f"{role.strip()}:{artifact_id}"})
    _atomic_write(packet_path, packet)
    return packet


def suspend_packet(repo_root: Path, packet_path: Path, reason: str, next_action: str, expected_revision: int) -> dict:
    packet = verify_packet(repo_root, packet_path)
    _check_revision(packet, expected_revision)
    _require(reason.strip() != "", "suspension reason is required")
    _require(next_action.strip() != "", "next action is required")
    now = _now()
    packet["revision"] += 1
    packet["status"] = "SUSPENDED"
    packet["suspension_reason"] = reason.strip()
    packet["next_action"] = next_action.strip()
    packet["updated_at"] = now
    packet["events"].append({"type": "SUSPENDED", "at": now, "detail": reason.strip()})
    _atomic_write(packet_path, packet)
    return packet


def resume_packet(repo_root: Path, packet_path: Path, expected_revision: int) -> dict:
    packet = verify_packet(repo_root, packet_path)
    _check_revision(packet, expected_revision)
    _require(packet["status"] == "SUSPENDED", "only a suspended packet can be resumed")
    now = _now()
    packet["revision"] += 1
    packet["status"] = "RESULT_REGISTERED" if packet["artifacts"] else "AWAITING_CHATGPT"
    packet["suspension_reason"] = None
    packet["updated_at"] = now
    packet["events"].append({"type": "RESUMED", "at": now, "detail": packet["next_action"]})
    _atomic_write(packet_path, packet)
    return packet


def _summary(packet: dict) -> dict:
    return {
        "packet_id": packet["packet_id"],
        "revision": packet["revision"],
        "project_id": packet["project_id"],
        "episode_id": packet["episode_id"],
        "stage": packet["stage"],
        "status": packet["status"],
        "input_count": len(packet.get("inputs", [])),
        "artifact_count": len(packet["artifacts"]),
        "next_action": packet["next_action"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--packet", required=True)
    create.add_argument("--project", required=True)
    create.add_argument("--episode", required=True)
    create.add_argument("--stage", required=True)
    create.add_argument("--next-action", required=True)
    create.add_argument("--transfer-mode", default="MANUAL_IMPORT", choices=["MANUAL_IMPORT", "DIRECT_INTEGRATION"])
    create.add_argument("--input", action="append", default=[], metavar="ROLE=PATH")

    register = subparsers.add_parser("register")
    register.add_argument("--packet", required=True)
    register.add_argument("--file", required=True)
    register.add_argument("--role", required=True)
    register.add_argument("--expected-revision", required=True, type=int)
    register.add_argument("--next-action", required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--packet", required=True)

    suspend = subparsers.add_parser("suspend")
    suspend.add_argument("--packet", required=True)
    suspend.add_argument("--reason", required=True)
    suspend.add_argument("--next-action", required=True)
    suspend.add_argument("--expected-revision", required=True, type=int)

    resume = subparsers.add_parser("resume")
    resume.add_argument("--packet", required=True)
    resume.add_argument("--expected-revision", required=True, type=int)

    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    packet_path = Path(args.packet).resolve()
    try:
        if args.command == "create":
            input_files = []
            for specification in args.input:
                role, separator, raw_path = specification.partition("=")
                _require(bool(separator and role.strip() and raw_path.strip()), f"invalid input specification: {specification}")
                input_files.append((role.strip(), Path(raw_path).resolve()))
            packet = create_packet(
                repo_root,
                packet_path,
                args.project,
                args.episode,
                args.stage,
                args.next_action,
                args.transfer_mode,
                input_files,
            )
        elif args.command == "register":
            packet = register_artifact(repo_root, packet_path, Path(args.file).resolve(), args.role, args.expected_revision, args.next_action)
        elif args.command == "verify":
            packet = verify_packet(repo_root, packet_path)
        elif args.command == "suspend":
            packet = suspend_packet(repo_root, packet_path, args.reason, args.next_action, args.expected_revision)
        else:
            packet = resume_packet(repo_root, packet_path, args.expected_revision)
    except ArtifactBridgeError as exc:
        print(f"ARTIFACT_BRIDGE_FAIL: {exc}")
        raise SystemExit(2)
    print(json.dumps(_summary(packet), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
