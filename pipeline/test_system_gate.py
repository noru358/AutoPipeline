import copy
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.system_gate import SystemGateError, validate_system


ROOT = Path(__file__).resolve().parents[1]


def load_fixture(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


class SystemGateTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_fixture("config/system_policy.json")
        self.profiles = [
            load_fixture("profiles/instatoon.json"),
            load_fixture("profiles/jipbap.json"),
        ]

    def test_validates_subscription_first_two_family_system(self):
        self.assertEqual(validate_system(self.policy, self.profiles), ["instatoon", "jipbap"])

    def test_blocks_positive_paid_ai_budget(self):
        policy = copy.deepcopy(self.policy)
        policy["execution_policy"]["additional_paid_ai_budget_krw"] = 1
        with self.assertRaises(SystemGateError):
            validate_system(policy, self.profiles)

    def test_blocks_paid_fallback(self):
        policy = copy.deepcopy(self.policy)
        policy["execution_policy"]["allow_paid_fallback"] = True
        with self.assertRaises(SystemGateError):
            validate_system(policy, self.profiles)

    def test_requires_new_session_handoff_on_contamination(self):
        policy = copy.deepcopy(self.policy)
        policy["continuity_policy"]["context_contamination_action"] = "KEEP_GOING"
        with self.assertRaises(SystemGateError):
            validate_system(policy, self.profiles)

    def test_requires_sticky_unsafe_context(self):
        policy = copy.deepcopy(self.policy)
        policy["continuity_policy"]["unsafe_context_is_sticky"] = False
        with self.assertRaises(SystemGateError):
            validate_system(policy, self.profiles)

    def test_requires_quarantined_outputs_in_handoff(self):
        policy = copy.deepcopy(self.policy)
        policy["continuity_policy"]["handoff_required_fields"].remove("quarantined_outputs")
        with self.assertRaises(SystemGateError):
            validate_system(policy, self.profiles)

    def test_requires_shared_sequence_quality_policy(self):
        policy = copy.deepcopy(self.policy)
        policy["quality_policy"]["sequence_qc_before_raster_user_gate"] = False
        with self.assertRaises(SystemGateError):
            validate_system(policy, self.profiles)

    def test_blocks_unknown_project_stage(self):
        profiles = copy.deepcopy(self.profiles)
        profiles[0]["stage_overrides"]["ONE_OFF_FIX"] = {
            "intent": "Hard-code one episode.",
            "authority_refs": ["STYLE_LOCK.md"],
        }
        with self.assertRaises(SystemGateError):
            validate_system(self.policy, profiles)

    def test_requires_both_initial_content_families(self):
        with self.assertRaises(SystemGateError):
            validate_system(self.policy, [self.profiles[0]])

    def test_checks_materialized_creative_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for profile in self.profiles:
                authority_root = root / profile["creative_authority_root"]
                authority_root.mkdir()
                for ref in profile["creative_authority_refs"]:
                    (authority_root / ref).touch()
            self.assertEqual(validate_system(self.policy, self.profiles, root), ["instatoon", "jipbap"])


if __name__ == "__main__":
    unittest.main()
