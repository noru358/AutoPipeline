import json
import tempfile
import unittest
from pathlib import Path

from pipeline.artifact_bridge import (
    ArtifactBridgeError,
    create_packet,
    register_artifact,
    resume_packet,
    suspend_packet,
    verify_packet,
)


ROOT = Path(__file__).resolve().parents[1]


class ArtifactBridgeTests(unittest.TestCase):
    def test_create_snapshots_stage_authority_and_commits(self):
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            packet = create_packet(
                ROOT,
                packet_path,
                "instatoon",
                "E002",
                "STORYBOARD",
                "Ask ChatGPT to draft the storyboard.",
            )
            self.assertEqual(packet["status"], "AWAITING_CHATGPT")
            self.assertEqual(packet["revision"], 1)
            self.assertEqual(packet["transfer_mode"], "MANUAL_IMPORT")
            self.assertRegex(packet["source_control"]["parent_commit"], r"^[0-9a-f]{40}$")
            self.assertRegex(packet["source_control"]["child_commit"], r"^[0-9a-f]{40}$")
            self.assertEqual(
                [item["path"] for item in packet["authority_snapshot"]],
                ["instatoon/VISUAL_GRAMMAR.md"],
            )
            self.assertEqual(packet, json.loads(packet_path.read_text(encoding="utf-8")))

    def test_rejects_wrong_project_episode_id(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ArtifactBridgeError):
                create_packet(
                    ROOT,
                    Path(directory) / "packet.json",
                    "instatoon",
                    "002",
                    "STORYBOARD",
                    "Draft storyboard.",
                )

    def test_registers_actual_file_and_verifies_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            result_path = root / "chatgpt result.png"
            result_path.write_bytes(b"test-image-bytes")
            create_packet(ROOT, packet_path, "jipbap", "003", "ASSET_PRODUCTION", "Generate one asset.")
            packet = register_artifact(
                ROOT,
                packet_path,
                result_path,
                "TEXT_FREE_RASTER",
                1,
                "Review the registered image.",
            )
            self.assertEqual(packet["status"], "RESULT_REGISTERED")
            self.assertEqual(packet["revision"], 2)
            self.assertEqual(len(packet["artifacts"]), 1)
            stored = packet_path.parent / packet["artifacts"][0]["path"]
            self.assertEqual(stored.read_bytes(), b"test-image-bytes")
            self.assertEqual(verify_packet(ROOT, packet_path)["packet_id"], packet["packet_id"])

    def test_create_copies_and_hashes_explicit_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            source = root / "episode-plan.json"
            source.write_bytes(b'{"episode":"E002"}')
            packet = create_packet(
                ROOT,
                packet_path,
                "instatoon",
                "E002",
                "STORYBOARD",
                "Draft storyboard.",
                input_files=[("EPISODE_PLAN", source)],
            )
            self.assertEqual(len(packet["inputs"]), 1)
            captured = packet_path.parent / packet["inputs"][0]["path"]
            self.assertEqual(captured.read_bytes(), source.read_bytes())
            self.assertEqual(verify_packet(ROOT, packet_path)["inputs"][0]["role"], "EPISODE_PLAN")

    def test_blocks_stale_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            result_path = root / "result.bin"
            result_path.write_bytes(b"result")
            create_packet(ROOT, packet_path, "jipbap", "003", "ASSET_PRODUCTION", "Generate one asset.")
            suspend_packet(ROOT, packet_path, "usage limit", "Resume generation.", 1)
            with self.assertRaises(ArtifactBridgeError):
                register_artifact(ROOT, packet_path, result_path, "RASTER", 1, "Review.")

    def test_tampered_artifact_blocks_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            result_path = root / "result.bin"
            result_path.write_bytes(b"result")
            create_packet(ROOT, packet_path, "jipbap", "003", "ASSET_PRODUCTION", "Generate one asset.")
            packet = register_artifact(ROOT, packet_path, result_path, "RASTER", 1, "Review.")
            stored = packet_path.parent / packet["artifacts"][0]["path"]
            stored.write_bytes(b"tampered")
            with self.assertRaises(ArtifactBridgeError):
                verify_packet(ROOT, packet_path)

    def test_suspend_and_resume_preserves_next_action(self):
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            create_packet(ROOT, packet_path, "instatoon", "E002", "STORYBOARD", "Draft storyboard.")
            suspended = suspend_packet(ROOT, packet_path, "subscription limit", "Continue storyboard draft.", 1)
            self.assertEqual(suspended["status"], "SUSPENDED")
            resumed = resume_packet(ROOT, packet_path, 2)
            self.assertEqual(resumed["status"], "AWAITING_CHATGPT")
            self.assertEqual(resumed["next_action"], "Continue storyboard draft.")
            self.assertEqual(resumed["revision"], 3)

    def test_changed_authority_blocks_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            packet = create_packet(ROOT, packet_path, "instatoon", "E002", "STORYBOARD", "Draft storyboard.")
            packet["authority_snapshot"][0]["sha256"] = "0" * 64
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            with self.assertRaises(ArtifactBridgeError):
                verify_packet(ROOT, packet_path)

    def test_tampered_input_blocks_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            source = root / "reference.png"
            source.write_bytes(b"reference")
            packet = create_packet(
                ROOT,
                packet_path,
                "jipbap",
                "003",
                "ASSET_PRODUCTION",
                "Generate one asset.",
                input_files=[("MEAL_REFERENCE", source)],
            )
            captured = packet_path.parent / packet["inputs"][0]["path"]
            captured.write_bytes(b"changed")
            with self.assertRaises(ArtifactBridgeError):
                resume_packet(ROOT, packet_path, 1)

    def test_packet_member_cannot_escape_packet_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            source = root / "reference.png"
            source.write_bytes(b"reference")
            packet = create_packet(
                ROOT,
                packet_path,
                "jipbap",
                "003",
                "ASSET_PRODUCTION",
                "Generate one asset.",
                input_files=[("MEAL_REFERENCE", source)],
            )
            packet["inputs"][0]["path"] = "../reference.png"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            with self.assertRaises(ArtifactBridgeError):
                verify_packet(ROOT, packet_path)

    def test_authority_snapshot_cannot_be_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            packet = create_packet(ROOT, packet_path, "instatoon", "E002", "STORYBOARD", "Draft storyboard.")
            packet["authority_snapshot"] = []
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            with self.assertRaises(ArtifactBridgeError):
                verify_packet(ROOT, packet_path)


if __name__ == "__main__":
    unittest.main()
