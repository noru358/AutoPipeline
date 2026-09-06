import json
import tempfile
import unittest
from pathlib import Path

from pipeline.artifact_bridge import (
    BridgeError,
    approve_result,
    create_packet,
    load_packet,
    mark_awaiting_result_import,
    register_input_asset,
    register_result_asset,
    resume_suspended_packet,
    suspend_packet,
    verify_packet,
)


class ArtifactBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "profiles").mkdir()
        (self.root / "instatoon").mkdir()

        policy = {
            "schema_version": "1.0",
            "system_id": "test",
            "execution_policy": {
                "ai_mode": "CHATGPT_SUBSCRIPTION_FIRST",
                "additional_paid_ai_budget_krw": 0,
                "allow_paid_fallback": False,
                "on_subscription_limit": "SUSPEND_AND_RESUME",
                "user_trigger_required": True,
                "unattended_subscription_invocation": False,
            },
            "canonical_stages": [
                {"id": "EDITORIAL", "order": 1, "owner": "CHATGPT_ASSISTED"},
                {"id": "ASSET_PRODUCTION", "order": 2, "owner": "HYBRID"},
            ],
        }
        profile = {
            "project_id": "instatoon",
            "episode_id_pattern": "^E[0-9]{3,}$",
            "creative_authority_root": "instatoon",
            "creative_authority_refs": ["STYLE_LOCK.md", "VISUAL_GRAMMAR.md"],
            "stage_overrides": {
                "EDITORIAL": {
                    "authority_refs": ["VISUAL_GRAMMAR.md"],
                },
                "ASSET_PRODUCTION": {
                    "authority_refs": ["STYLE_LOCK.md"],
                },
            },
        }
        (self.root / "config" / "system_policy.json").write_text(
            json.dumps(policy), encoding="utf-8"
        )
        (self.root / "profiles" / "instatoon.json").write_text(
            json.dumps(profile), encoding="utf-8"
        )
        (self.root / "instatoon" / "STYLE_LOCK.md").write_text(
            "style-v1", encoding="utf-8"
        )
        (self.root / "instatoon" / "VISUAL_GRAMMAR.md").write_text(
            "grammar-v1", encoding="utf-8"
        )
        self.packet = (
            self.root / "workspaces" / "instatoon" / "E001" / "ASSET_PRODUCTION" / "packet.json"
        )

    def tearDown(self):
        self.temp.cleanup()

    def _create(self):
        return create_packet(
            repo_root=self.root,
            policy_path="config/system_policy.json",
            profile_path="profiles/instatoon.json",
            episode_id="E001",
            stage_id="ASSET_PRODUCTION",
            packet_path=self.packet,
            packet_id="packet-test",
        )

    def test_create_packet_snapshots_only_stage_authority(self):
        packet = self._create()
        self.assertEqual(packet["status"], "READY_FOR_CHATGPT")
        self.assertEqual(packet["next_action"]["type"], "RUN_CHATGPT_ASSISTED_STAGE")
        self.assertEqual(
            [item["path"] for item in packet["authority_snapshot"]],
            ["instatoon/STYLE_LOCK.md"],
        )
        self.assertEqual(
            packet["execution_snapshot"]["artifact_transfer"],
            "MANUAL_IMPORT_UNTIL_VERIFIED",
        )

    def test_registers_actual_input_and_result_bytes(self):
        self._create()
        source_input = self.root / "style.png"
        source_input.write_bytes(b"actual-style-bytes")
        input_asset = register_input_asset(
            packet_path=self.packet,
            source_path=source_input,
            role="style_reference",
            media_type="image",
        )
        stored_input = self.packet.parent / input_asset["stored_path"]
        self.assertTrue(stored_input.is_file())
        self.assertEqual(stored_input.read_bytes(), b"actual-style-bytes")

        mark_awaiting_result_import(self.packet)
        result_file = self.root / "result.png"
        result_file.write_bytes(b"chatgpt-result")
        result_asset = register_result_asset(
            packet_path=self.packet,
            source_path=result_file,
            role="representative_frame",
            media_type="image",
        )
        packet = load_packet(self.packet)
        self.assertEqual(packet["status"], "RESULT_REGISTERED")
        self.assertEqual(packet["next_action"]["type"], "REVIEW_RESULT")
        self.assertEqual(
            (self.packet.parent / result_asset["stored_path"]).read_bytes(),
            b"chatgpt-result",
        )

    def test_explicit_user_approval_locks_hash_and_blocks_replacement(self):
        self._create()
        mark_awaiting_result_import(self.packet)
        result_file = self.root / "result.png"
        result_file.write_bytes(b"approved-result")
        result_asset = register_result_asset(
            packet_path=self.packet,
            source_path=result_file,
            role="representative_frame",
            media_type="image",
        )
        approval = approve_result(
            packet_path=self.packet,
            asset_id=result_asset["asset_id"],
        )
        self.assertEqual(approval["actor"], "USER")
        packet = load_packet(self.packet)
        self.assertEqual(packet["status"], "USER_APPROVED")
        self.assertTrue(
            next(
                a for a in packet["assets"]
                if a["asset_id"] == result_asset["asset_id"]
            )["locked"]
        )
        self.assertEqual(packet["next_action"]["type"], "ADVANCE_STAGE")

        replacement = self.root / "replacement.png"
        replacement.write_bytes(b"replacement")
        with self.assertRaises(BridgeError):
            register_result_asset(
                packet_path=self.packet,
                source_path=replacement,
                role="representative_frame",
                media_type="image",
            )

        late_input = self.root / "late-input.png"
        late_input.write_bytes(b"late")
        with self.assertRaises(BridgeError):
            register_input_asset(
                packet_path=self.packet,
                source_path=late_input,
                role="late_reference",
                media_type="image",
            )

    def test_resume_fails_closed_if_registered_asset_bytes_change(self):
        self._create()
        mark_awaiting_result_import(self.packet)
        result_file = self.root / "result.png"
        result_file.write_bytes(b"result-v1")
        result_asset = register_result_asset(
            packet_path=self.packet,
            source_path=result_file,
            role="frame",
            media_type="image",
        )
        stored = self.packet.parent / result_asset["stored_path"]
        stored.write_bytes(b"tampered")
        with self.assertRaisesRegex(BridgeError, "hash changed|size changed"):
            verify_packet(self.packet, repo_root=self.root)

    def test_resume_fails_closed_if_authority_changes(self):
        self._create()
        (self.root / "instatoon" / "STYLE_LOCK.md").write_text(
            "style-v2", encoding="utf-8"
        )
        with self.assertRaisesRegex(BridgeError, "authority drift"):
            verify_packet(self.packet, repo_root=self.root)

    def test_suspend_resume_restores_exact_prior_status_after_verification(self):
        self._create()
        mark_awaiting_result_import(self.packet)
        suspended = suspend_packet(self.packet, "subscription limit")
        self.assertEqual(suspended["status"], "SUSPENDED")
        resumed = resume_suspended_packet(self.packet, repo_root=self.root)
        self.assertEqual(resumed["status"], "AWAITING_RESULT_IMPORT")
        self.assertEqual(resumed["next_action"]["type"], "IMPORT_CHATGPT_RESULT")

    def test_invalid_episode_id_is_rejected(self):
        with self.assertRaises(BridgeError):
            create_packet(
                repo_root=self.root,
                policy_path="config/system_policy.json",
                profile_path="profiles/instatoon.json",
                episode_id="002",
                stage_id="ASSET_PRODUCTION",
                packet_path=self.packet,
            )


if __name__ == "__main__":
    unittest.main()
